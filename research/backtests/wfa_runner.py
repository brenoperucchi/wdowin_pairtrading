# research/wfa_runner.py
"""
WIN×WDO ML Direction — Walk-Forward Analysis Runner
=====================================================
Orchestrates WFA for all 3 directional models (HMM, LSTM, XGBoost).

Train: 12 months rolling
Test:  3 months OOS
Step:  3 months

Outputs OOS predictions for each model to data/processed/wfa_results/
"""
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from research.models.features import (
    compute_features, make_target,
    ALL_FEATURES, HMM_FEATURES, LOCAL_FEATURES, MACRO_FEATURES, SPREAD_FEATURES,
)
from research.models.hmm_direction import HMMDirection
from research.models.lstm_direction import LSTMDirection
from research.models.xgb_direction import XGBDirection

# ─── Config ──────────────────────────────────────────────────────────────────
TRAIN_MONTHS = 12
TEST_MONTHS = 3
STEP_MONTHS = 3

DATA_PROC = PROJECT_ROOT / "data" / "processed"
WFA_DIR = DATA_PROC / "wfa_results"

# Features for each model
FEATURE_SETS = {
    "hmm": HMM_FEATURES,
    "lstm": ALL_FEATURES,
    "xgb": ALL_FEATURES,
}


def generate_windows(df: pd.DataFrame) -> list[dict]:
    """Generate WFA train/test windows from the dataset."""
    min_date = df["dt"].min()
    max_date = df["dt"].max()

    # Start first window so test period starts after at least TRAIN_MONTHS
    window_start = min_date
    windows = []

    while True:
        train_end = window_start + relativedelta(months=TRAIN_MONTHS)
        test_end = train_end + relativedelta(months=TEST_MONTHS)

        if test_end > max_date:
            break

        windows.append({
            "train_start": window_start,
            "train_end": train_end,
            "test_start": train_end,
            "test_end": test_end,
        })

        window_start += relativedelta(months=STEP_MONTHS)

    return windows


def run_model_wfa(model_name: str, df_features: pd.DataFrame,
                  windows: list[dict]) -> pd.DataFrame:
    """
    Run WFA for a single model across all windows.

    Returns:
        DataFrame with columns [dt, direction, window_idx] for OOS predictions
    """
    features = FEATURE_SETS[model_name]
    all_oos = []

    for i, w in enumerate(windows):
        print(f"\n  Window {i + 1}/{len(windows)}: "
              f"Train [{w['train_start'].strftime('%Y-%m')} → {w['train_end'].strftime('%Y-%m')}] | "
              f"Test [{w['test_start'].strftime('%Y-%m')} → {w['test_end'].strftime('%Y-%m')}]")

        # Split
        mask_train = (df_features["dt"] >= w["train_start"]) & (df_features["dt"] < w["train_end"])
        mask_test = (df_features["dt"] >= w["test_start"]) & (df_features["dt"] < w["test_end"])

        df_train = df_features[mask_train].copy()
        df_test = df_features[mask_test].copy()

        if len(df_train) < 100 or len(df_test) < 20:
            print(f"  [SKIP] Not enough data: train={len(df_train)}, test={len(df_test)}")
            continue

        # Features & target
        X_train = df_train[features].values
        X_test = df_test[features].values
        y_train = make_target(df_train["fwd_ret_pts"]).values

        # Remove NaN target rows from training
        valid = df_train["fwd_ret_pts"].notna().values
        X_train = X_train[valid]
        y_train = y_train[valid]

        # Handle NaN in features
        X_train = np.nan_to_num(X_train, nan=0.0)
        X_test = np.nan_to_num(X_test, nan=0.0)

        t0 = time.time()

        # ── Train & predict ──────────────────────────────────────────────────
        try:
            if model_name == "hmm":
                model = HMMDirection(n_components=3)
                model.fit(X_train)
                preds = model.predict(X_test)

            elif model_name == "lstm":
                model = LSTMDirection(seq_len=45, hidden_dim=96, dropout_rate=0.7, epochs=50, patience=10)
                model.fit(X_train, y_train)
                preds = model.predict(X_test)

            elif model_name == "xgb":
                model = XGBDirection(max_depth=5, n_estimators=300)
                model.fit(X_train, y_train, feature_names=features)
                preds = model.predict(X_test)

                # Print feature importance for the first window
                if i == 0:
                    imp = model.feature_importance(top_n=10)
                    print(f"  [XGB] Top features: {dict(zip(imp['feature'], imp['importance'].round(3)))}")
            else:
                raise ValueError(f"Unknown model: {model_name}")

        except Exception as e:
            print(f"  [ERROR] {model_name} failed: {e}")
            continue

        elapsed = time.time() - t0
        print(f"  {model_name.upper()}: {len(preds)} predictions in {elapsed:.1f}s")

        # ── Collect OOS predictions ──────────────────────────────────────────
        oos = pd.DataFrame({
            "dt": df_test["dt"].values[:len(preds)],
            "direction": preds[:len(df_test)],
            "window_idx": i,
            "close": df_test["close"].values[:len(preds)],
            "fwd_ret_pts": df_test["fwd_ret_pts"].values[:len(preds)],
            "zscore_ols": df_test["zscore_ols"].values[:len(preds)],
            "rho": df_test["rho"].values[:len(preds)],
        })
        all_oos.append(oos)

    if not all_oos:
        print(f"  [WARN] No OOS results for {model_name}")
        return pd.DataFrame()

    result = pd.concat(all_oos, ignore_index=True)

    # Deduplicate overlapping windows (keep last window's prediction)
    result = result.drop_duplicates(subset="dt", keep="last").sort_values("dt").reset_index(drop=True)

    return result


def run_all():
    """Run WFA for all 3 models and save results."""
    # Load dataset
    parquet_path = DATA_PROC / "dataset_m30.parquet"
    if not parquet_path.exists():
        print(f"[ERROR] Dataset not found: {parquet_path}")
        print("Run `python research/data_prep.py` first.")
        sys.exit(1)

    print("Loading dataset...")
    df_raw = pd.read_parquet(parquet_path)
    print(f"Raw: {len(df_raw)} bars, {df_raw['dt'].iloc[0]} → {df_raw['dt'].iloc[-1]}")

    print("\nComputing features...")
    df = compute_features(df_raw)
    print(f"With features: {len(df)} bars, {len(df.columns)} columns")

    # Generate windows
    windows = generate_windows(df)
    print(f"\nWFA windows: {len(windows)}")
    for i, w in enumerate(windows):
        print(f"  [{i + 1}] Train {w['train_start'].strftime('%Y-%m')} → "
              f"{w['train_end'].strftime('%Y-%m')} | "
              f"Test {w['test_start'].strftime('%Y-%m')} → "
              f"{w['test_end'].strftime('%Y-%m')}")

    # Run only LSTM with the optimized hyperparams for the final evidence
    for model_name in ["lstm"]:
        print(f"\n{'=' * 60}")
        print(f"Running WFA: {model_name.upper()}")
        print(f"{'=' * 60}")

        out_dir = WFA_DIR / model_name
        out_dir.mkdir(parents=True, exist_ok=True)

        result = run_model_wfa(model_name, df, windows)

        if len(result) > 0:
            out_path = out_dir / "predictions_oos.parquet"
            result.to_parquet(out_path, index=False)
            print(f"\nSaved: {out_path} ({len(result)} predictions)")

            # Quick accuracy
            valid = result["fwd_ret_pts"].notna()
            if valid.sum() > 0:
                actual = make_target(result.loc[valid, "fwd_ret_pts"])
                correct = (result.loc[valid, "direction"].values == actual.values).sum()
                acc = correct / len(actual) * 100
                print(f"OOS Accuracy: {acc:.1f}% ({correct}/{len(actual)})")

                # Direction distribution
                dist = result["direction"].value_counts()
                print(f"Distribution: {dict(dist)}")

    print(f"\n{'=' * 60}")
    print("WFA complete. Run `python research/backtest_ml_zscore.py` next.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_all()
