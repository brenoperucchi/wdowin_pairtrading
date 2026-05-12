"""Recompute bar_history.z_di using OLS pipeline (matches /api/di-regime).

Earlier polls saved z_di computed via Kalman, which forces a positive beta
on a negatively-correlated pair (WIN×DI) and flips the z sign. This script
overwrites z_di for the requested dates using calc_beta_ols + calc_zscore
on the WIN/DI closes already persisted in bar_history.

Backend is dispatched through `core.bar_history_db` (TASK-14 Slice 6), so
this script honors BAR_HISTORY_BACKEND={sqlite,dual,postgres}.

Usage:
    BAR_HISTORY_BACKEND=postgres python3 scripts/backfill_z_di.py \\
        --dates 2026-05-06,2026-05-07,2026-05-08
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core import bar_history_db as bhdb
from core.config import DI_BETA_REF_BARS, DI_KALMAN_W
from core.signals import calc_beta_ols, calc_zscore


def _load_window(target_date: str) -> tuple[list[int], np.ndarray, np.ndarray]:
    """Pull all bars up to and including target_date so the OLS window is honest."""
    rows = bhdb.select_di_warmup(target_date)
    if not rows:
        return [], np.array([]), np.array([])
    timestamps = [int(r["timestamp"]) for r in rows]
    win = np.asarray([float(r["win_price"]) for r in rows])
    di = np.asarray([float(r["di_price"]) for r in rows])
    return timestamps, win, di


def backfill_date(target_date: str) -> int:
    timestamps, win, di = _load_window(target_date)
    if win.size < DI_KALMAN_W + 1:
        print(f"  {target_date}: skipped (only {win.size} bars, need >= {DI_KALMAN_W + 1})")
        return 0

    ref_window = min(DI_BETA_REF_BARS, win.size)
    beta_di = calc_beta_ols(win[-ref_window:], di[-ref_window:], window=ref_window)
    _, z_di_arr, _ = calc_zscore(win, di, beta=beta_di, window=DI_KALMAN_W, max_bars=win.size)

    # Only update timestamps that belong to target_date (not the prior history).
    target_ts = set(bhdb.select_timestamps_by_date(target_date))

    updates: list[tuple[float, int]] = []
    for ts, z in zip(timestamps, z_di_arr):
        if ts in target_ts:
            updates.append((round(float(z), 3), ts))
    bhdb.update_columns_batch("z_di", updates)
    print(f"  {target_date}: updated {len(updates)} bars (beta_di={beta_di:.4f}, ref_window={ref_window})")
    return len(updates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", required=True, help="Comma-separated YYYY-MM-DD list")
    args = parser.parse_args(argv)

    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    if not dates:
        print("ERROR: --dates is empty", file=sys.stderr)
        return 2

    backend = bhdb.get_backend()
    print(f"Backfilling z_di via backend={backend}")
    total = 0
    for d in dates:
        total += backfill_date(d)
    print(f"Done. Total rows updated: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
