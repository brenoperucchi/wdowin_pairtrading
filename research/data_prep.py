# research/data_prep.py
"""
WIN×WDO ML Direction — Data Preparation
=========================================
Builds the unified M30 dataset from multiple sources:
  - WIN M1 + WDO M1 (local CSVs, resampled to M30)
  - VIX M30 + DXY M30 (from Tickmill MT5 or local CSVs)

Output: data/processed/dataset_m30.parquet
"""
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ─── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_HIST = PROJECT_ROOT / "data" / "historical"
DATA_PROC = PROJECT_ROOT / "data" / "processed"
DATA_PROC.mkdir(parents=True, exist_ok=True)

# MT5 Tickmill for VIX/DXY
TICKMILL_PATH = "C:/Program Files/Tickmill MT5 Terminal/terminal64.exe"

# Symbol names in Tickmill MT5 (may vary by broker)
VIX_SYMBOL = "VIXM"       # Adjust if different, common: VIX, VIXM, VIX.a
DXY_SYMBOL = "USDX"       # Adjust if different, common: DXY, USDX, DX.f


def load_mt5_csv(filepath: Path) -> pd.DataFrame:
    """Load a MetaTrader 5 exported CSV (tab-separated)."""
    df = pd.read_csv(
        filepath, sep="\t",
        names=["date", "time", "open", "high", "low", "close", "tickvol", "vol", "spread"],
        skiprows=1, dtype={"date": str, "time": str}
    )
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"])
    df = df[["dt", "open", "high", "low", "close", "vol"]].copy()
    df = df.sort_values("dt").reset_index(drop=True)
    return df


def resample_m1_to_m30(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-minute bars to 30-minute bars."""
    df = df.set_index("dt")
    resampled = df.resample("30min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "vol": "sum",
    }).dropna()
    return resampled.reset_index()


def fetch_macro_from_mt5(symbol: str, n_bars: int = 50000) -> pd.DataFrame | None:
    """
    Fetch M30 bars from Tickmill MT5 for macro instruments (VIX, DXY).
    Returns None if MT5 connection fails.
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize(path=TICKMILL_PATH):
            print(f"[WARN] Cannot connect to Tickmill MT5 at {TICKMILL_PATH}")
            print(f"       Error: {mt5.last_error()}")
            return None

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, n_bars)
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            print(f"[WARN] No data for {symbol}. Available symbols may differ.")
            return None

        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s")
        df = df[["dt", "open", "high", "low", "close", "tick_volume"]].copy()
        df.columns = ["dt", "open", "high", "low", "close", "vol"]
        print(f"[OK] {symbol}: {len(df)} bars from {df['dt'].iloc[0]} to {df['dt'].iloc[-1]}")
        return df

    except Exception as e:
        print(f"[ERROR] MT5 fetch for {symbol}: {e}")
        return None


def load_macro_csv(filepath: Path) -> pd.DataFrame | None:
    """Fallback: load macro data from CSV if MT5 is unavailable."""
    if not filepath.exists():
        return None
    return load_mt5_csv(filepath)


def build_dataset() -> pd.DataFrame:
    """Build the unified M30 dataset."""
    print("=" * 60)
    print("Building unified M30 dataset")
    print("=" * 60)

    # ── 1. Load & resample WIN M1 → M30 ─────────────────────────────────────
    win_files = list(DATA_HIST.glob("WIN*M1*.csv"))
    if not win_files:
        print("[ERROR] No WIN M1 CSV found in data/historical/")
        sys.exit(1)
    print(f"\n[1/4] Loading WIN: {win_files[0].name}")
    win_m1 = load_mt5_csv(win_files[0])
    win_m30 = resample_m1_to_m30(win_m1)
    print(f"  Resampled: {len(win_m1)} M1 bars → {len(win_m30)} M30 bars")
    print(f"  Range: {win_m30['dt'].iloc[0]} → {win_m30['dt'].iloc[-1]}")

    # ── 2. Load & resample WDO M1 → M30 ─────────────────────────────────────
    wdo_files = list(DATA_HIST.glob("WDO*M1*.csv"))
    if not wdo_files:
        print("[ERROR] No WDO M1 CSV found in data/historical/")
        sys.exit(1)
    print(f"\n[2/4] Loading WDO: {wdo_files[0].name}")
    wdo_m1 = load_mt5_csv(wdo_files[0])
    wdo_m30 = resample_m1_to_m30(wdo_m1)
    print(f"  Resampled: {len(wdo_m1)} M1 bars → {len(wdo_m30)} M30 bars")

    # ── 3. Load VIX M30 (CSV M1 → resample, or MT5 fallback) ──────────────
    print(f"\n[3/4] Loading VIX...")
    vix = None
    vix_m1_csvs = list(DATA_HIST.glob("VIX*M1*.csv")) + list(DATA_HIST.glob("vix*M1*.csv"))
    if vix_m1_csvs:
        print(f"  Found M1 CSV: {vix_m1_csvs[0].name}")
        vix_m1 = load_mt5_csv(vix_m1_csvs[0])
        vix = resample_m1_to_m30(vix_m1)
        print(f"  Resampled: {len(vix_m1)} M1 → {len(vix)} M30 bars")
    else:
        vix_df = fetch_macro_from_mt5(VIX_SYMBOL)
        if vix_df is not None:
            vix = vix_df
    if vix is not None:
        vix = vix.rename(columns={
            "close": "vix_close", "high": "vix_high", "low": "vix_low"
        })[["dt", "vix_close", "vix_high", "vix_low"]]
        print(f"  VIX: {len(vix)} M30 bars loaded")
    else:
        print("  [WARN] VIX not available — macro features will be NaN")

    # ── 4. Load DXY M30 (CSV M1 → resample, or MT5 fallback) ──────────────
    print(f"\n[4/4] Loading DXY...")
    dxy = None
    dxy_m1_csvs = list(DATA_HIST.glob("DXY*M1*.csv")) + list(DATA_HIST.glob("dxy*M1*.csv")) + \
                  list(DATA_HIST.glob("USDX*M1*.csv"))
    if dxy_m1_csvs:
        print(f"  Found M1 CSV: {dxy_m1_csvs[0].name}")
        dxy_m1 = load_mt5_csv(dxy_m1_csvs[0])
        dxy = resample_m1_to_m30(dxy_m1)
        print(f"  Resampled: {len(dxy_m1)} M1 → {len(dxy)} M30 bars")
    else:
        dxy_df = fetch_macro_from_mt5(DXY_SYMBOL)
        if dxy_df is not None:
            dxy = dxy_df
    if dxy is not None:
        dxy = dxy.rename(columns={
            "close": "dxy_close", "high": "dxy_high", "low": "dxy_low"
        })[["dt", "dxy_close", "dxy_high", "dxy_low"]]
        print(f"  DXY: {len(dxy)} M30 bars loaded")
    else:
        print("  [WARN] DXY not available — macro features will be NaN")

    # ── 5. Merge everything on datetime ──────────────────────────────────────
    print("\n[MERGE] Joining datasets on datetime...")

    # WIN as base
    merged = win_m30.rename(columns={
        "open": "open", "high": "high", "low": "low",
        "close": "close", "vol": "volume"
    })

    # WDO (inner join — only bars where both exist)
    wdo_slim = wdo_m30[["dt", "close"]].rename(columns={"close": "wdo_close"})
    merged = merged.merge(wdo_slim, on="dt", how="inner")

    # VIX (left join — NaN where VIX not available)
    if vix is not None:
        # Round to nearest 30-min to handle timezone mismatches
        vix["dt"] = vix["dt"].dt.round("30min")
        vix = vix.drop_duplicates(subset="dt", keep="last")
        merged = merged.merge(vix, on="dt", how="left")
        # Forward-fill macro data (they update less frequently)
        for col in ["vix_close", "vix_high", "vix_low"]:
            merged[col] = merged[col].ffill()
    else:
        merged["vix_close"] = np.nan
        merged["vix_high"] = np.nan
        merged["vix_low"] = np.nan

    # DXY (left join)
    if dxy is not None:
        dxy["dt"] = dxy["dt"].dt.round("30min")
        dxy = dxy.drop_duplicates(subset="dt", keep="last")
        merged = merged.merge(dxy, on="dt", how="left")
        for col in ["dxy_close", "dxy_high", "dxy_low"]:
            merged[col] = merged[col].ffill()
    else:
        merged["dxy_close"] = np.nan
        merged["dxy_high"] = np.nan
        merged["dxy_low"] = np.nan

    merged = merged.sort_values("dt").reset_index(drop=True)

    # ── 6. Save ──────────────────────────────────────────────────────────────
    out_path = DATA_PROC / "dataset_m30.parquet"
    merged.to_parquet(out_path, index=False)

    print(f"\n{'=' * 60}")
    print(f"Dataset saved: {out_path}")
    print(f"Shape: {merged.shape}")
    print(f"Range: {merged['dt'].iloc[0]} → {merged['dt'].iloc[-1]}")
    print(f"WIN bars:  {merged['close'].notna().sum()}")
    print(f"WDO bars:  {merged['wdo_close'].notna().sum()}")
    print(f"VIX bars:  {merged['vix_close'].notna().sum()}")
    print(f"DXY bars:  {merged['dxy_close'].notna().sum()}")
    print(f"NaN cols:  {merged.isna().sum().to_dict()}")
    print(f"{'=' * 60}")

    return merged


if __name__ == "__main__":
    build_dataset()
