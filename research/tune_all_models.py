# research/tune_all_models.py
"""
WIN×WDO — Comprehensive 70/30 Grid Search for HMM, LSTM, XGBoost
===================================================================
Split: 70% train / 30% test (chronological)
Z-Score: Fixed at 1.8
Optimizes Calmar Ratio = PnL / |MaxDD|
"""
import os, sys, time, itertools, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_PROC = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

Z_THRESHOLD = 1.8
TARGET_THR = 100  # fixed for LSTM/XGB target labeling
TRAIN_RATIO = 0.70
MAX_WORKERS = max(1, os.cpu_count() - 2)

# ═══════════════════════════════════════════════════════════════════════
# GRID DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════
HMM_GRID = {
    "ret_threshold": [0.0001, 0.0005, 0.001, 0.002, 0.0025, 0.003, 0.0035, 0.004, 0.0045, 0.005],
    "covariance_type": ["full", "diag", "tied"],
    "n_iter": [50, 100, 150, 200, 250, 300, 350, 400, 450, 500],
}

LSTM_GRID = {
    "seq_len": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
    "hidden_dim": [32, 64, 96, 128, 160, 192, 224, 256, 288, 320],
    "dropout": [0.1, 0.3, 0.5, 0.7, 0.9],
}

XGB_GRID = {
    "max_depth": [3, 5, 7, 9, 11, 13, 15, 17, 19, 21],
    "n_estimators": [100, 150, 200, 250, 300, 350, 400, 450, 500, 550],
    "learning_rate": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
}


def load_data():
    """Load M30 dataset and M5 dataset, compute 70/30 split."""
    from research.models.features import compute_features
    parquet = DATA_PROC / "dataset_m30.parquet"
    df = pd.read_parquet(parquet)
    df = compute_features(df)

    split_idx = int(len(df) * TRAIN_RATIO)
    split_date = df["dt"].iloc[split_idx]
    df_train = df.iloc[:split_idx].copy()
    df_test = df.iloc[split_idx:].copy()

    return df, df_train, df_test, split_date


def backtest_predictions(predictions, m5, z_thr=Z_THRESHOLD):
    """Run backtest with ML directions on M5 data."""
    from research.backtest_ml_zscore import simulate_trades, compute_metrics
    trades = simulate_trades(predictions, m5, z_thr, use_ml=True)
    metrics = compute_metrics(trades)
    dd = abs(metrics["max_drawdown"]) if metrics["max_drawdown"] != 0 else 1.0
    metrics["calmar_ratio"] = round(metrics["total_pnl"] / dd, 2)
    return metrics


# ═══════════════════════════════════════════════════════════════════════
# HMM WORKER
# ═══════════════════════════════════════════════════════════════════════
def run_hmm(args):
    ret_thr, cov_type, n_iter, parquet_path, idx, total = args
    import warnings; warnings.filterwarnings("ignore")

    try:
        from research.models.features import compute_features, make_target, HMM_FEATURES
        from hmmlearn.hmm import GaussianHMM

        df = pd.read_parquet(parquet_path)
        df = compute_features(df)
        split_idx = int(len(df) * TRAIN_RATIO)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        features = HMM_FEATURES
        X_train = np.nan_to_num(df_train[features].values, nan=0.0)
        X_test = np.nan_to_num(df_test[features].values, nan=0.0)

        # Normalize
        mean = X_train.mean(axis=0)
        std = X_train.std(axis=0) + 1e-8
        X_train_n = (X_train - mean) / std
        X_test_n = (X_test - mean) / std

        n_components = 3
        transmat_prior = np.ones((n_components, n_components)) + np.eye(n_components) * 5.0

        model = GaussianHMM(
            n_components=n_components,
            covariance_type=cov_type,
            n_iter=n_iter,
            random_state=42,
            transmat_prior=transmat_prior,
        )
        model.fit(X_train_n)

        # Map states to directions
        means = model.means_
        state_scores = means[:, 0]  # trend_pos
        idx_bull = np.argmax(state_scores)
        idx_bear = np.argmin(state_scores)
        idx_chop = [i for i in range(n_components) if i not in [idx_bull, idx_bear]][0]

        state_map = {idx_bull: "SELL", idx_bear: "BUY", idx_chop: "FLAT"}

        # Predict on test
        hidden_test = model.predict(X_test_n)
        preds = np.array([state_map[s] for s in hidden_test])

        # Apply ret_threshold: override to FLAT if state mean is below threshold
        for s_idx in range(n_components):
            if abs(means[s_idx, 0]) < ret_thr:
                mask = hidden_test == s_idx
                preds[mask] = "FLAT"

        # OOS accuracy
        y_test = make_target(df_test["fwd_ret_pts"], threshold_pts=TARGET_THR)
        valid = df_test["fwd_ret_pts"].notna().values
        acc = (preds[valid] == y_test.values[valid]).mean() * 100 if valid.sum() > 0 else 0

        predictions = pd.DataFrame({
            "dt": df_test["dt"].values,
            "direction": preds,
            "close": df_test["close"].values,
            "fwd_ret_pts": df_test["fwd_ret_pts"].values,
            "zscore_ols": df_test["zscore_ols"].values,
        })

        print(f"  HMM [{idx}/{total}] ret={ret_thr} cov={cov_type} iter={n_iter} → acc={acc:.1f}%", flush=True)

        return {
            "model": "HMM",
            "ret_threshold": ret_thr,
            "covariance_type": cov_type,
            "n_iter": n_iter,
            "oos_accuracy": round(acc, 1),
            "predictions": predictions,
        }
    except Exception as e:
        print(f"  HMM [{idx}/{total}] ERROR: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# LSTM WORKER
# ═══════════════════════════════════════════════════════════════════════
def run_lstm(args):
    seq_len, hidden_dim, dropout, parquet_path, idx, total = args
    import warnings; warnings.filterwarnings("ignore")
    import torch
    torch.set_num_threads(2)

    try:
        from research.models.features import compute_features, make_target, ALL_FEATURES

        df = pd.read_parquet(parquet_path)
        df = compute_features(df)
        split_idx = int(len(df) * TRAIN_RATIO)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        features = ALL_FEATURES
        X_train = np.nan_to_num(df_train[features].values, nan=0.0)
        X_test = np.nan_to_num(df_test[features].values, nan=0.0)
        y_train = make_target(df_train["fwd_ret_pts"], threshold_pts=TARGET_THR).values
        valid_train = df_train["fwd_ret_pts"].notna().values
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]

        # Build LSTM with custom dropout
        from research.models.lstm_direction import LSTMDirection, _LSTMNet, CLASS_INV, CLASS_MAP

        model = LSTMDirection(seq_len=seq_len, hidden_dim=hidden_dim, epochs=50, patience=10)

        # Override dropout in the network
        class _LSTMNetCustom(torch.nn.Module):
            def __init__(self, input_dim, hidden_dim, dropout_rate, n_classes=3):
                super().__init__()
                self.lstm = torch.nn.LSTM(input_dim, hidden_dim, batch_first=True, num_layers=1)
                self.dropout = torch.nn.Dropout(dropout_rate)
                self.fc1 = torch.nn.Linear(hidden_dim, 32)
                self.relu = torch.nn.ReLU()
                self.fc2 = torch.nn.Linear(32, n_classes)

            def forward(self, x):
                _, (h_n, _) = self.lstm(x)
                out = self.dropout(h_n.squeeze(0))
                out = self.relu(self.fc1(out))
                return self.fc2(out)

        # Normalize
        mean = X_train.mean(axis=0)
        std = X_train.std(axis=0) + 1e-8
        X_train_n = (X_train - mean) / std
        X_test_n = (X_test - mean) / std

        # Make sequences
        y_enc = np.array([CLASS_INV[v] for v in y_train])
        seqs, labels = [], []
        for i in range(seq_len, len(X_train_n)):
            seqs.append(X_train_n[i - seq_len:i])
            labels.append(y_enc[i])
        X_seq = np.array(seqs, dtype=np.float32)
        y_seq = np.array(labels, dtype=np.int64)

        if len(X_seq) < 50:
            return None

        # Class weights
        counts = np.bincount(y_seq, minlength=3)
        weights = len(y_seq) / (3.0 * counts + 1e-8)
        class_weights = torch.FloatTensor(weights)

        dataset = torch.utils.data.TensorDataset(
            torch.FloatTensor(X_seq), torch.LongTensor(y_seq))
        loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True)

        val_size = max(1, len(X_seq) // 5)
        X_val = torch.FloatTensor(X_seq[-val_size:])
        y_val = torch.LongTensor(y_seq[-val_size:])

        net = _LSTMNetCustom(X_train.shape[1], hidden_dim, dropout)
        optimizer = torch.optim.Adam(net.parameters(), lr=1e-3)
        criterion = torch.nn.CrossEntropyLoss(weight=class_weights)

        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None

        for epoch in range(50):
            net.train()
            for xb, yb in loader:
                optimizer.zero_grad()
                loss = criterion(net(xb), yb)
                loss.backward()
                optimizer.step()

            net.eval()
            with torch.no_grad():
                val_loss = criterion(net(X_val), y_val).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
            if patience_counter >= 10:
                break

        if best_state:
            net.load_state_dict(best_state)

        # Predict test
        net.eval()
        seqs_test = []
        for i in range(seq_len, len(X_test_n)):
            seqs_test.append(X_test_n[i - seq_len:i])
        X_test_seq = np.array(seqs_test, dtype=np.float32) if seqs_test else np.array([], dtype=np.float32).reshape(0, seq_len, X_train.shape[1])

        if len(X_test_seq) == 0:
            return None

        with torch.no_grad():
            preds_enc = []
            for bi in range(0, len(X_test_seq), 64):
                batch = torch.FloatTensor(X_test_seq[bi:bi+64])
                preds_enc.append(net(batch).argmax(dim=1).numpy())
            pred_classes = np.concatenate(preds_enc)

        # Pad first seq_len bars with FLAT
        pad = np.full(seq_len, CLASS_INV["FLAT"])
        full_preds = np.concatenate([pad, pred_classes])[:len(df_test)]
        preds = np.array([CLASS_MAP[c] for c in full_preds])

        # OOS accuracy
        y_test = make_target(df_test["fwd_ret_pts"], threshold_pts=TARGET_THR)
        valid = df_test["fwd_ret_pts"].notna().values
        acc = (preds[valid] == y_test.values[valid]).mean() * 100 if valid.sum() > 0 else 0

        predictions = pd.DataFrame({
            "dt": df_test["dt"].values[:len(preds)],
            "direction": preds,
            "close": df_test["close"].values[:len(preds)],
            "fwd_ret_pts": df_test["fwd_ret_pts"].values[:len(preds)],
            "zscore_ols": df_test["zscore_ols"].values[:len(preds)],
        })

        print(f"  LSTM [{idx}/{total}] seq={seq_len} hid={hidden_dim} drop={dropout} → acc={acc:.1f}%", flush=True)

        return {
            "model": "LSTM",
            "seq_len": seq_len,
            "hidden_dim": hidden_dim,
            "dropout": dropout,
            "oos_accuracy": round(acc, 1),
            "predictions": predictions,
        }
    except Exception as e:
        print(f"  LSTM [{idx}/{total}] ERROR: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# XGB WORKER
# ═══════════════════════════════════════════════════════════════════════
def run_xgb(args):
    max_depth, n_estimators, lr, parquet_path, idx, total = args
    import warnings; warnings.filterwarnings("ignore")

    try:
        from research.models.features import compute_features, make_target, ALL_FEATURES
        from xgboost import XGBClassifier

        df = pd.read_parquet(parquet_path)
        df = compute_features(df)
        split_idx = int(len(df) * TRAIN_RATIO)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        features = ALL_FEATURES
        X_train = np.nan_to_num(df_train[features].values, nan=0.0)
        X_test = np.nan_to_num(df_test[features].values, nan=0.0)
        y_train_raw = make_target(df_train["fwd_ret_pts"], threshold_pts=TARGET_THR).values
        valid_train = df_train["fwd_ret_pts"].notna().values
        X_train = X_train[valid_train]
        y_train_raw = y_train_raw[valid_train]

        CLASS_INV = {"BUY": 0, "FLAT": 1, "SELL": 2}
        CLASS_MAP = {0: "BUY", 1: "FLAT", 2: "SELL"}
        y_enc = np.array([CLASS_INV[v] for v in y_train_raw])

        # Class weights
        counts = np.bincount(y_enc, minlength=3)
        sample_weights = np.array([len(y_enc) / (3.0 * counts[c] + 1e-8) for c in y_enc])

        model = XGBClassifier(
            max_depth=max_depth,
            n_estimators=n_estimators,
            learning_rate=lr,
            objective="multi:softmax",
            num_class=3,
            random_state=42,
            use_label_encoder=False,
            eval_metric="mlogloss",
            verbosity=0,
            n_jobs=2,
        )
        model.fit(X_train, y_enc, sample_weight=sample_weights)

        pred_classes = model.predict(X_test)
        preds = np.array([CLASS_MAP[int(c)] for c in pred_classes])

        # OOS accuracy
        y_test = make_target(df_test["fwd_ret_pts"], threshold_pts=TARGET_THR)
        valid = df_test["fwd_ret_pts"].notna().values
        acc = (preds[valid] == y_test.values[valid]).mean() * 100 if valid.sum() > 0 else 0

        predictions = pd.DataFrame({
            "dt": df_test["dt"].values[:len(preds)],
            "direction": preds,
            "close": df_test["close"].values[:len(preds)],
            "fwd_ret_pts": df_test["fwd_ret_pts"].values[:len(preds)],
            "zscore_ols": df_test["zscore_ols"].values[:len(preds)],
        })

        print(f"  XGB [{idx}/{total}] depth={max_depth} trees={n_estimators} lr={lr} → acc={acc:.1f}%", flush=True)

        return {
            "model": "XGBoost",
            "max_depth": max_depth,
            "n_estimators": n_estimators,
            "learning_rate": lr,
            "oos_accuracy": round(acc, 1),
            "predictions": predictions,
        }
    except Exception as e:
        print(f"  XGB [{idx}/{total}] ERROR: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    from research.backtest_ml_zscore import load_m5_dataset

    n_hmm = len(HMM_GRID["ret_threshold"]) * len(HMM_GRID["covariance_type"]) * len(HMM_GRID["n_iter"])
    n_lstm = len(LSTM_GRID["seq_len"]) * len(LSTM_GRID["hidden_dim"]) * len(LSTM_GRID["dropout"])
    n_xgb = len(XGB_GRID["max_depth"]) * len(XGB_GRID["n_estimators"]) * len(XGB_GRID["learning_rate"])
    total = n_hmm + n_lstm + n_xgb

    print("=" * 70)
    print("COMPREHENSIVE 70/30 GRID SEARCH — HMM, LSTM, XGBoost")
    print(f"Split: 70% train / 30% test | Z-Score: {Z_THRESHOLD} (fixed)")
    print(f"HMM:     {n_hmm:5d} configs (ret_thr × cov_type × n_iter)")
    print(f"LSTM:    {n_lstm:5d} configs (seq_len × hidden_dim × dropout)")
    print(f"XGBoost: {n_xgb:5d} configs (max_depth × n_estimators × lr)")
    print(f"TOTAL:   {total:5d} configs")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 70)

    m5 = load_m5_dataset()
    parquet_path = str(DATA_PROC / "dataset_m30.parquet")

    all_results = []

    # ── 1. HMM ────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"PHASE 1/3: HMM ({n_hmm} configs)")
    print(f"{'='*70}")
    t0 = time.time()

    hmm_jobs = []
    for i, (ret_thr, cov, n_iter) in enumerate(
        itertools.product(HMM_GRID["ret_threshold"], HMM_GRID["covariance_type"], HMM_GRID["n_iter"]), 1
    ):
        hmm_jobs.append((ret_thr, cov, n_iter, parquet_path, i, n_hmm))

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_hmm, j): j for j in hmm_jobs}
        for f in as_completed(futures):
            r = f.result()
            if r is not None:
                metrics = backtest_predictions(r["predictions"], m5)
                dist = r["predictions"]["direction"].value_counts()
                flat_pct = dist.get("FLAT", 0) / len(r["predictions"]) * 100
                all_results.append({
                    "model": "HMM",
                    "param1_name": "ret_threshold", "param1_value": r["ret_threshold"],
                    "param2_name": "covariance_type", "param2_value": r["covariance_type"],
                    "param3_name": "n_iter", "param3_value": r["n_iter"],
                    "oos_accuracy": r["oos_accuracy"], "flat_pct": round(flat_pct, 1),
                    **metrics,
                })

    hmm_time = time.time() - t0
    print(f"HMM done: {hmm_time/60:.1f} min")

    # ── 2. LSTM ───────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"PHASE 2/3: LSTM ({n_lstm} configs)")
    print(f"{'='*70}")
    t0 = time.time()

    lstm_jobs = []
    for i, (seq, hid, drop) in enumerate(
        itertools.product(LSTM_GRID["seq_len"], LSTM_GRID["hidden_dim"], LSTM_GRID["dropout"]), 1
    ):
        lstm_jobs.append((seq, hid, drop, parquet_path, i, n_lstm))

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_lstm, j): j for j in lstm_jobs}
        for f in as_completed(futures):
            r = f.result()
            if r is not None:
                metrics = backtest_predictions(r["predictions"], m5)
                dist = r["predictions"]["direction"].value_counts()
                flat_pct = dist.get("FLAT", 0) / len(r["predictions"]) * 100
                all_results.append({
                    "model": "LSTM",
                    "param1_name": "seq_len", "param1_value": r["seq_len"],
                    "param2_name": "hidden_dim", "param2_value": r["hidden_dim"],
                    "param3_name": "dropout", "param3_value": r["dropout"],
                    "oos_accuracy": r["oos_accuracy"], "flat_pct": round(flat_pct, 1),
                    **metrics,
                })

    lstm_time = time.time() - t0
    print(f"LSTM done: {lstm_time/60:.1f} min")

    # ── 3. XGBoost ────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"PHASE 3/3: XGBoost ({n_xgb} configs)")
    print(f"{'='*70}")
    t0 = time.time()

    xgb_jobs = []
    for i, (depth, trees, lr) in enumerate(
        itertools.product(XGB_GRID["max_depth"], XGB_GRID["n_estimators"], XGB_GRID["learning_rate"]), 1
    ):
        xgb_jobs.append((depth, trees, lr, parquet_path, i, n_xgb))

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_xgb, j): j for j in xgb_jobs}
        for f in as_completed(futures):
            r = f.result()
            if r is not None:
                metrics = backtest_predictions(r["predictions"], m5)
                dist = r["predictions"]["direction"].value_counts()
                flat_pct = dist.get("FLAT", 0) / len(r["predictions"]) * 100
                all_results.append({
                    "model": "XGBoost",
                    "param1_name": "max_depth", "param1_value": r["max_depth"],
                    "param2_name": "n_estimators", "param2_value": r["n_estimators"],
                    "param3_name": "learning_rate", "param3_value": r["learning_rate"],
                    "oos_accuracy": r["oos_accuracy"], "flat_pct": round(flat_pct, 1),
                    **metrics,
                })

    xgb_time = time.time() - t0
    print(f"XGBoost done: {xgb_time/60:.1f} min")

    # ── RESULTS ───────────────────────────────────────────────────────────
    summary = pd.DataFrame(all_results)
    summary = summary.sort_values("calmar_ratio", ascending=False)

    out_path = REPORT_DIR / "grid_search_all_models.csv"
    summary.to_csv(out_path, index=False)
    print(f"\nSaved {len(summary)} results to {out_path}")

    # Print top per model
    for model_name in ["HMM", "LSTM", "XGBoost"]:
        subset = summary[summary["model"] == model_name].head(5)
        print(f"\n{'='*70}")
        print(f"TOP 5 — {model_name} (by Calmar)")
        print(f"{'='*70}")
        for _, r in subset.iterrows():
            print(f"  {r.param1_name}={r.param1_value} {r.param2_name}={r.param2_value} "
                  f"{r.param3_name}={r.param3_value} | "
                  f"Calmar={r.calmar_ratio:5.2f} PnL=R${r.total_pnl:8.0f} DD=R${r.max_drawdown:8.0f} "
                  f"PF={r.profit_factor:.2f} Trades={int(r.total_trades)} Acc={r.oos_accuracy}%")

    # Overall top 10
    print(f"\n{'='*70}")
    print(f"TOP 10 OVERALL (all models)")
    print(f"{'='*70}")
    for _, r in summary.head(10).iterrows():
        print(f"  [{r.model:7s}] {r.param1_name}={r.param1_value} {r.param2_name}={r.param2_value} "
              f"{r.param3_name}={r.param3_value} | "
              f"Calmar={r.calmar_ratio:5.2f} PnL=R${r.total_pnl:8.0f} DD=R${r.max_drawdown:8.0f} "
              f"PF={r.profit_factor:.2f} Trades={int(r.total_trades)}")


if __name__ == "__main__":
    main()
