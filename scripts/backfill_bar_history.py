"""Backfill bar_history from MT5 (fresh fetch, full indicator recompute).

Reads WIN/WDO/DI M5 closes from MetaTrader 5 for the last N days, recomputes
every indicator the replay engine reads (z_wdo, z_di, rho, rho_level,
beta_value, beta_delta_pct, NWE bands), and UPSERTs each session bar into
`bar_history`. Default behaviour is `force=True`: existing indicator columns
are overwritten with the freshly computed values.

Why a script and not an endpoint: the server already restricts the live
ingestion path to persist only the just-closed bar each poll. A multi-day
backfill (for replay/TASK-11 validation) is a one-shot operator action — no
reason to expose it as an HTTP route. Run this from the Windows host that has
MT5 installed; WSL has no MT5 access.

Usage:
    python scripts/backfill_bar_history.py [--days 30] [--no-force] [--db-path trades.db]

`eg_pvalue` is intentionally left NULL — ReplayEgComputer recomputes it from
raw win/wdo prices using the active runtime profile's eg_bars/eg_recalc, so
persisting a single static pvalue per bar would be wrong.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.config import (  # noqa: E402
    BETA_INITIAL,
    DI_BETA_REF_BARS,
    DI_KALMAN_W,
    DI_SYMBOL,
    KALMAN_BURN_IN,
    NWE_BANDWIDTH,
    NWE_LOOKBACK,
    NWE_MULT_MAE,
    SYMBOL_A,
    SYMBOL_B,
    TIME_OFFSET,
    WDO_KALMAN_Q,
    WDO_KALMAN_R,
    WDO_KALMAN_W,
    WINDOW,
)
from core.kalman_filter import KalmanBetaFilter  # noqa: E402
from core.mt5_client import connect_mt5, fetch_bars  # noqa: E402
from core.signals import (  # noqa: E402
    calc_beta_ols,
    calc_nwe_with_bands,
    calc_zscore,
    get_rho_status,
)


SESSION_START = 8 * 60 + 50   # 08:50
SESSION_END = 18 * 60 + 20    # 18:20
BARS_PER_DAY = 108            # ~108 M5 bars per B3 session day


def _upsert_bar(
    conn: sqlite3.Connection,
    *,
    timestamp: int,
    date_str: str,
    bar_time: str,
    win_price: float,
    wdo_price: float,
    di_price: float | None,
    spread_wdo: float,
    spread_di: float | None,
    z_wdo: float,
    z_di: float,
    nwe_center: float | None,
    nwe_upper: float | None,
    nwe_lower: float | None,
    nwe_is_up: bool | None,
    rho: float | None,
    rho_level: int | None,
    beta_value: float,
    beta_delta_pct: float | None,
    force: bool,
) -> None:
    """Mirror server.save_bar_history's UPSERT semantics.

    `force=True` overwrites every indicator column (the backfill is
    authoritative). `force=False` falls back to COALESCE so the script can
    fill-in-only without erasing existing rows.
    """
    nwe_is_up_val = int(bool(nwe_is_up)) if nwe_is_up is not None else None
    rho_level_val = int(rho_level) if rho_level is not None else None
    if force:
        on_conflict = """
            ON CONFLICT(timestamp) DO UPDATE SET
                win_price = excluded.win_price,
                wdo_price = excluded.wdo_price,
                di_price = excluded.di_price,
                spread_wdo = excluded.spread_wdo,
                spread_di = excluded.spread_di,
                z_wdo = excluded.z_wdo,
                z_di = excluded.z_di,
                nwe_center = excluded.nwe_center,
                nwe_upper = excluded.nwe_upper,
                nwe_lower = excluded.nwe_lower,
                nwe_is_up = excluded.nwe_is_up,
                eg_pvalue = excluded.eg_pvalue,
                rho = excluded.rho,
                rho_level = excluded.rho_level,
                beta_value = excluded.beta_value,
                beta_delta_pct = excluded.beta_delta_pct
        """
    else:
        on_conflict = """
            ON CONFLICT(timestamp) DO UPDATE SET
                wdo_price = COALESCE(bar_history.wdo_price, excluded.wdo_price),
                di_price = COALESCE(bar_history.di_price, excluded.di_price),
                z_di = COALESCE(excluded.z_di, bar_history.z_di),
                eg_pvalue = COALESCE(bar_history.eg_pvalue, excluded.eg_pvalue),
                rho = COALESCE(bar_history.rho, excluded.rho),
                rho_level = COALESCE(bar_history.rho_level, excluded.rho_level),
                beta_value = COALESCE(bar_history.beta_value, excluded.beta_value),
                beta_delta_pct = COALESCE(bar_history.beta_delta_pct, excluded.beta_delta_pct)
        """
    conn.execute(
        f"""
        INSERT INTO bar_history
            (timestamp, date_str, bar_time, win_price, wdo_price, di_price,
             spread_wdo, spread_di, z_wdo, z_di,
             nwe_center, nwe_upper, nwe_lower, nwe_is_up,
             eg_pvalue, rho, rho_level, beta_value, beta_delta_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        {on_conflict}
        """,
        (
            int(timestamp), date_str, bar_time,
            win_price, wdo_price, di_price,
            spread_wdo, spread_di, z_wdo, z_di,
            nwe_center, nwe_upper, nwe_lower, nwe_is_up_val,
            None, rho, rho_level_val, beta_value, beta_delta_pct,
        ),
    )


def run_backfill(days: int, force: bool, db_path: str, rho_window: int | None = None) -> dict:
    if not connect_mt5():
        return {"error": "MT5_UNAVAILABLE", "bars_written": 0}

    # `rho_window` overrides the default (WINDOW=90) used inside calc_zscore for
    # the rolling rho/OLS-z. Per the gate-relaxation experiment (Abril 2026):
    # a 90-bar window oscillates between strong & weak correlation inside a
    # single session, while a 240–480-bar window better matches the EG
    # cointegration timescale (2240 bars). `None` keeps the historic behaviour.
    effective_rho_window = int(rho_window) if rho_window else WINDOW

    # Need enough warmup for Kalman convergence + rho rolling window + replay's
    # eg_bars=2240 context (so ReplayEgComputer has the bars it needs).
    bars_needed = max(
        days * BARS_PER_DAY + effective_rho_window + 50,
        KALMAN_BURN_IN,
        2240 + 100,
    )

    closes_a, times_a = fetch_bars(SYMBOL_A, bars_needed)
    closes_b, times_b = fetch_bars(SYMBOL_B, bars_needed)
    closes_di, times_di = fetch_bars(DI_SYMBOL, bars_needed)
    if closes_a is None or closes_b is None:
        return {"error": "MT5_NO_WIN_OR_WDO", "bars_written": 0}

    min_len = min(len(closes_a), len(closes_b))
    ac = np.asarray(closes_a[-min_len:], dtype=float)
    bc = np.asarray(closes_b[-min_len:], dtype=float)
    tc = times_a[-min_len:]

    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
    kf_spreads: list[float] = []
    kf_betas: list[float] = []
    for y, x in zip(ac, bc):
        beta_t, spread_t, _ = kf.update(float(y), float(x))
        kf_spreads.append(spread_t)
        kf_betas.append(beta_t)
    z_kalman = KalmanBetaFilter.rolling_zscore(kf_spreads, window=WDO_KALMAN_W)

    beta_ols_val = calc_beta_ols(ac, bc, window=effective_rho_window)
    _, _, rho_arr = calc_zscore(
        ac, bc, beta=beta_ols_val,
        window=effective_rho_window, max_bars=min_len,
    )

    nwe_line, nwe_u, nwe_l, nwe_is_up = calc_nwe_with_bands(
        ac, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
    )

    # DI z-score uses OLS beta — Kalman flips sign on negatively-correlated pairs.
    z_di_map: dict[int, float] = {}
    spread_di_map: dict[int, float] = {}
    di_price_map: dict[int, float] = {}
    if closes_di is not None and len(closes_di) > 0:
        min_di = min(len(ac), len(closes_di))
        di_c = np.asarray(closes_di[-min_di:], dtype=float)
        di_t = times_di[-min_di:]
        win_for_di = ac[-min_di:]
        ref_window = min(DI_BETA_REF_BARS, len(win_for_di))
        beta_di = calc_beta_ols(
            win_for_di[-ref_window:], di_c[-ref_window:], window=ref_window
        )
        spread_di_arr, z_di_arr, _ = calc_zscore(
            win_for_di, di_c, beta=beta_di,
            window=DI_KALMAN_W, max_bars=len(win_for_di),
        )
        for i, t in enumerate(di_t):
            local_ts = int(t) + TIME_OFFSET
            di_price_map[local_ts] = float(di_c[i])
            if i < len(z_di_arr):
                z_di_map[local_ts] = round(float(z_di_arr[i]), 3)
            if i < len(spread_di_arr):
                spread_di_map[local_ts] = float(spread_di_arr[i])

    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        bars_written = 0
        dates_touched: set[str] = set()
        first_ts: int | None = None
        last_ts: int | None = None

        for i in range(len(ac)):
            local_ts = int(tc[i]) + TIME_OFFSET
            dt = datetime.fromtimestamp(local_ts)
            t_min = dt.hour * 60 + dt.minute
            if not (SESSION_START <= t_min <= SESSION_END):
                continue

            win_price = float(ac[i])
            wdo_price = float(bc[i])
            beta_value = float(kf_betas[i])
            spread_wdo = win_price - beta_value * wdo_price
            z_wdo_val = float(z_kalman[i]) if i < len(z_kalman) else 0.0

            # rho_arr is 0 inside the rolling-warmup zone — treat as not-measurable.
            if i < effective_rho_window:
                rho_val: float | None = None
                rho_level_val: int | None = None
            else:
                rho_raw = float(rho_arr[i]) if i < len(rho_arr) else 0.0
                rho_val = rho_raw
                rho_level_val = get_rho_status(rho_raw)["level"]

            # beta_ref_20d: 40-bar window ending 40 bars before "now" (mirrors V2).
            if i >= 80:
                ref_slice = kf_betas[i - 80:i - 40]
                beta_ref_20d = float(np.mean(ref_slice)) if ref_slice else 0.0
                beta_delta_pct_val = (
                    (beta_value - beta_ref_20d) / abs(beta_ref_20d) * 100
                    if beta_ref_20d != 0 else 0.0
                )
            else:
                beta_delta_pct_val = None

            nwe_center_val = float(nwe_line[i]) if i < len(nwe_line) else None
            nwe_upper_val = float(nwe_u[i]) if i < len(nwe_u) else None
            nwe_lower_val = float(nwe_l[i]) if i < len(nwe_l) else None
            nwe_is_up_val = bool(nwe_is_up[i]) if i < len(nwe_is_up) else None

            _upsert_bar(
                conn,
                timestamp=local_ts,
                date_str=dt.strftime("%Y-%m-%d"),
                bar_time=dt.strftime("%H:%M"),
                win_price=win_price,
                wdo_price=wdo_price,
                di_price=di_price_map.get(local_ts),
                spread_wdo=spread_wdo,
                spread_di=spread_di_map.get(local_ts),
                z_wdo=z_wdo_val,
                z_di=z_di_map.get(local_ts, 0.0),
                nwe_center=nwe_center_val,
                nwe_upper=nwe_upper_val,
                nwe_lower=nwe_lower_val,
                nwe_is_up=nwe_is_up_val,
                rho=rho_val,
                rho_level=rho_level_val,
                beta_value=beta_value,
                beta_delta_pct=beta_delta_pct_val,
                force=force,
            )
            bars_written += 1
            dates_touched.add(dt.strftime("%Y-%m-%d"))
            if first_ts is None or local_ts < first_ts:
                first_ts = local_ts
            if last_ts is None or local_ts > last_ts:
                last_ts = local_ts

        conn.commit()
    finally:
        conn.close()

    return {
        "bars_written": bars_written,
        "days_requested": days,
        "days_touched": sorted(dates_touched),
        "from": datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d %H:%M") if first_ts else None,
        "to": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M") if last_ts else None,
        "force": force,
        "db_path": db_path,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int, default=30, help="Trading days to backfill (default: 30)")
    p.add_argument(
        "--no-force", dest="force", action="store_false",
        help="Fill-in-only mode: COALESCE on existing indicator columns instead of overwriting.",
    )
    p.add_argument("--db-path", default="trades.db", help="Path to trades.db (default: trades.db)")
    p.add_argument(
        "--rho-window", type=int, default=None,
        help=(
            "Rolling window for rho/OLS-z computation. Defaults to core.config.WINDOW "
            "(90). Use 240+ to align the rho timescale to the EG cointegration window."
        ),
    )
    p.set_defaults(force=True)
    args = p.parse_args()

    result = run_backfill(
        days=args.days, force=args.force, db_path=args.db_path,
        rho_window=args.rho_window,
    )

    if "error" in result:
        print(f"ERROR: {result['error']}")
        return 1

    print(f"bars_written:  {result['bars_written']}")
    print(f"days_touched:  {len(result['days_touched'])} sessions")
    print(f"  first:       {result['from']}")
    print(f"  last:        {result['to']}")
    print(f"force:         {result['force']}")
    print(f"db_path:       {result['db_path']}")
    if args.rho_window:
        print(f"rho_window:    {args.rho_window} (override, default={WINDOW})")
    print("eg_pvalue:     left NULL (ReplayEgComputer recomputes from win/wdo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
