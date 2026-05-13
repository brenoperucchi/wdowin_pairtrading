"""Backfill OHLC (open/high/low) on historical bar_history rows.

A.3 made `server.py` capture OHLC live going forward, but every row written
before that point holds only `win_price/wdo_price/di_price` (the close). This
script reads `bar_history` rows in a date range, fetches the corresponding M5
rates from MT5 via `fetch_rates_range`, and UPDATEs only the 9 OHLC columns
(`{win,wdo,di}_{open,high,low}`). Existing close columns and all indicators
are preserved.

Honors `BAR_HISTORY_BACKEND={sqlite,dual,postgres}` via `core.bar_history_db`.

Idempotent — default merge mode skips cells already populated; `--force-refresh`
rewrites them. Without `--commit` the script is a dry-run: it prints the plan
(rows in scope, cells that would change) and exits without writing.

Cell-level integrity check: SHA-256 over (timestamp, win_price, wdo_price,
di_price, z_wdo, z_di, eg_pvalue, rho, beta_value) computed before and after
the write. The script aborts if the checksum drifts (would mean a non-OHLC
column was touched by mistake — see [[feedback_migration_cell_checksum]]).

Run from Windows host (MT5 API is Windows-only); WSL has no MT5 access.

Usage:
    py.exe -3.12 scripts/backfill_bar_history_ohlc.py --start 2026-04-01 --end 2026-05-09 [--commit] [--force-refresh] [--symbols WIN,WDO]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core import bar_history_db as bhdb  # noqa: E402
from core.config import (  # noqa: E402
    DI_SYMBOL,
    SYMBOL_A,
    SYMBOL_B,
    TIME_OFFSET,
)


# Map symbol-alias → (mt5_symbol, ohlc_column_names)
SYMBOL_ALIASES: dict[str, tuple[str, tuple[str, str, str]]] = {
    "WIN": (SYMBOL_A, ("win_open", "win_high", "win_low")),
    "WDO": (SYMBOL_B, ("wdo_open", "wdo_high", "wdo_low")),
    "DI":  (DI_SYMBOL, ("di_open", "di_high", "di_low")),
}

ALL_OHLC_COLUMNS: tuple[str, ...] = tuple(
    c for _, cols in SYMBOL_ALIASES.values() for c in cols
)

# Columns that this script must NEVER touch — they are part of the integrity
# checksum so a drift here triggers a hard abort.
INTEGRITY_COLUMNS: tuple[str, ...] = (
    "win_price", "wdo_price", "di_price",
    "z_wdo", "z_di", "spread_wdo", "spread_di",
    "eg_pvalue", "rho", "rho_level", "beta_value", "beta_delta_pct",
)


# Fetcher returns the raw MT5 structured array (or None) — same contract as
# `core.mt5_client.fetch_rates_range`.
Mt5RatesFetcher = Callable[[str, datetime, datetime], "np.ndarray | None"]


def _default_mt5_fetcher(symbol: str, dt_start: datetime, dt_end: datetime):
    """Read historical OHLC from MT5. Lazy-imported so offline tests stay CI-safe."""
    from core.mt5_client import connect_mt5, fetch_rates_range  # noqa: PLC0415

    if not connect_mt5():
        raise RuntimeError("MT5 unavailable; cannot fetch historical rates")
    return fetch_rates_range(symbol, dt_start, dt_end)


def _date_range(start: str, end: str) -> list[str]:
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    if e < s:
        raise ValueError(f"--end {end} precedes --start {start}")
    out: list[str] = []
    d = s
    while d <= e:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _mt5_bounds_for_date(date_str: str) -> tuple[datetime, datetime]:
    """Return MT5-local datetimes covering [date 00:00, date+1 00:00).

    MT5 timestamps live in UTC offset by TIME_OFFSET versus our local stored
    timestamps. We feed datetime objects (not epoch) directly to copy_rates_range,
    which interprets them in MT5's server zone — using local midnight as a
    bound is what fetch_bars-driven backfills do too.
    """
    target = datetime.strptime(date_str, "%Y-%m-%d")
    return target, target + timedelta(days=1)


def _checksum(rows: Iterable[dict]) -> str:
    """SHA-256 over INTEGRITY_COLUMNS (drift detector for non-OHLC cells)."""
    h = hashlib.sha256()
    for r in rows:
        h.update(str(int(r["timestamp"])).encode())
        for col in INTEGRITY_COLUMNS:
            v = r.get(col)
            h.update(b"|")
            h.update(b"NULL" if v is None else repr(v).encode())
        h.update(b"\n")
    return h.hexdigest()


def _build_ohlc_map(
    rates: "np.ndarray | None",
    *,
    cols: tuple[str, str, str],
) -> dict[int, dict[str, float]]:
    """Index a rates array by local_ts (= MT5 ts + TIME_OFFSET) → {open/high/low}."""
    if rates is None or len(rates) == 0:
        return {}
    col_open, col_high, col_low = cols
    out: dict[int, dict[str, float]] = {}
    for r in rates:
        local_ts = int(r["time"]) + TIME_OFFSET
        out[local_ts] = {
            col_open: float(r["open"]),
            col_high: float(r["high"]),
            col_low: float(r["low"]),
        }
    return out


def _plan_updates_for_row(
    row: dict,
    ohlc_for_ts: dict[str, float] | None,
    *,
    force_refresh: bool,
) -> dict[str, float]:
    """Return columns this row should be updated with (empty if no change)."""
    if not ohlc_for_ts:
        return {}
    cols_to_set: dict[str, float] = {}
    for col, value in ohlc_for_ts.items():
        existing = row.get(col)
        if force_refresh or existing is None:
            if existing != value:
                cols_to_set[col] = value
    return cols_to_set


def run_backfill(
    *,
    start: str,
    end: str,
    symbols: tuple[str, ...],
    commit: bool,
    force_refresh: bool,
    mt5_fetcher: Mt5RatesFetcher | None = None,
    backend: str | None = None,
) -> dict:
    fetcher = mt5_fetcher or _default_mt5_fetcher
    effective_backend = (backend or bhdb.get_backend()).lower()

    rows_scanned = 0
    rows_updated = 0
    cells_updated = 0
    rows_missing_mt5_data = 0
    cells_missing_mt5_data = 0
    rows_partial_mt5_data = 0
    dates_processed: list[str] = []

    integrity_before = ""
    integrity_after = ""
    all_existing_rows: list[dict] = []

    for date_str in _date_range(start, end):
        existing_rows = bhdb.select_by_date(date_str, backend=backend)
        if not existing_rows:
            continue
        dates_processed.append(date_str)
        rows_scanned += len(existing_rows)
        all_existing_rows.extend(existing_rows)

        dt_start, dt_end = _mt5_bounds_for_date(date_str)
        ohlc_by_ts: dict[int, dict[str, float]] = {}
        for alias in symbols:
            mt5_symbol, ohlc_cols = SYMBOL_ALIASES[alias]
            rates = fetcher(mt5_symbol, dt_start, dt_end)
            symbol_map = _build_ohlc_map(rates, cols=ohlc_cols)
            for ts, cols in symbol_map.items():
                ohlc_by_ts.setdefault(ts, {}).update(cols)

        for row in existing_rows:
            ts = int(row["timestamp"])
            ohlc_for_ts = ohlc_by_ts.get(ts)
            expected_cols_for_ts = [
                col
                for alias in symbols
                for col in SYMBOL_ALIASES[alias][1]
            ]
            missing_cols_for_ts = (
                expected_cols_for_ts if ohlc_for_ts is None
                else [col for col in expected_cols_for_ts if col not in ohlc_for_ts]
            )
            if missing_cols_for_ts:
                cells_missing_mt5_data += len(missing_cols_for_ts)
                if len(missing_cols_for_ts) == len(expected_cols_for_ts):
                    rows_missing_mt5_data += 1
                else:
                    rows_partial_mt5_data += 1
            cols_to_set = _plan_updates_for_row(
                row, ohlc_for_ts, force_refresh=force_refresh,
            )
            if not cols_to_set:
                continue
            rows_updated += 1
            cells_updated += len(cols_to_set)
            if commit:
                bhdb.update_columns(ts, backend=backend, **cols_to_set)

    integrity_before = _checksum(all_existing_rows)

    if commit and dates_processed:
        # Re-read the same window to confirm INTEGRITY_COLUMNS are bit-exact.
        post_rows: list[dict] = []
        for date_str in dates_processed:
            post_rows.extend(bhdb.select_by_date(date_str, backend=backend))
        integrity_after = _checksum(post_rows)
        if integrity_after != integrity_before:
            raise RuntimeError(
                "non-OHLC cell drift detected after backfill — "
                "an update touched a column outside the 9-column OHLC set. "
                f"checksum_before={integrity_before[:12]}... "
                f"checksum_after={integrity_after[:12]}..."
            )

    return {
        "start": start,
        "end": end,
        "symbols": list(symbols),
        "commit": commit,
        "force_refresh": force_refresh,
        "dates_processed": dates_processed,
        "rows_scanned": rows_scanned,
        "rows_updated": rows_updated,
        "cells_updated": cells_updated,
        "rows_missing_mt5_data": rows_missing_mt5_data,
        "rows_partial_mt5_data": rows_partial_mt5_data,
        "cells_missing_mt5_data": cells_missing_mt5_data,
        "integrity_before_sha256": integrity_before,
        "integrity_after_sha256": integrity_after or None,
        "backend": effective_backend,
    }


def _parse_symbols(raw: str) -> tuple[str, ...]:
    parts = [s.strip().upper() for s in raw.split(",") if s.strip()]
    for p in parts:
        if p not in SYMBOL_ALIASES:
            raise argparse.ArgumentTypeError(
                f"unknown symbol alias {p!r} — expected one of {list(SYMBOL_ALIASES)}"
            )
    return tuple(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--start", required=True, help="Inclusive start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="Inclusive end date YYYY-MM-DD")
    p.add_argument(
        "--symbols", type=_parse_symbols, default=tuple(SYMBOL_ALIASES.keys()),
        help="Comma-separated aliases: WIN,WDO,DI (default: all three)",
    )
    p.add_argument(
        "--commit", action="store_true",
        help="Apply UPDATEs. Without this flag the script is a dry-run.",
    )
    p.add_argument(
        "--force-refresh", action="store_true",
        help="Rewrite OHLC cells even when already populated.",
    )
    args = p.parse_args(argv)

    try:
        result = run_backfill(
            start=args.start, end=args.end, symbols=args.symbols,
            commit=args.commit, force_refresh=args.force_refresh,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"start:                  {result['start']}")
    print(f"end:                    {result['end']}")
    print(f"symbols:                {','.join(result['symbols'])}")
    print(f"backend:                {result['backend']}")
    print(f"force_refresh:          {result['force_refresh']}")
    print(f"dry_run:                {not result['commit']}")
    print(f"dates_processed:        {len(result['dates_processed'])}")
    print(f"rows_scanned:           {result['rows_scanned']}")
    print(f"rows_updated:           {result['rows_updated']}")
    print(f"cells_updated:          {result['cells_updated']}")
    print(f"rows_missing_mt5_data:  {result['rows_missing_mt5_data']}")
    print(f"rows_partial_mt5_data:  {result['rows_partial_mt5_data']}")
    print(f"cells_missing_mt5_data: {result['cells_missing_mt5_data']}")
    print(f"integrity_sha256:       {result['integrity_before_sha256'][:16]}...")
    if result["integrity_after_sha256"]:
        print(f"integrity_after_sha256: {result['integrity_after_sha256'][:16]}...")
        print("integrity check:        OK (non-OHLC cells bit-exact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
