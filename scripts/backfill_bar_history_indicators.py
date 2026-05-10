"""Backfill replay-required indicators into bar_history.

This is a repair tool for bars captured before TASK-8 Slice A started
persisting `eg_pvalue`, `rho`, `rho_level`, `beta_value`, and
`beta_delta_pct`. It reads local `bar_history`, recomputes the indicators from
persisted WIN/WDO closes, and writes only missing indicator fields by default.

By default it is fully offline. With `--fetch-mt5`, it also reads historical
WIN/WDO/DI M5 closes from MT5 to fill missing prices and warm-up context before
recomputing indicators. It never sends orders and does not touch
execution_timeline or matador_ops.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

# Allow `python scripts/backfill_bar_history_indicators.py ...` from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.config import (  # noqa: E402
    BARS,
    BETA_INITIAL,
    BETA_REF_WINDOW,
    DI_SYMBOL,
    SYMBOL_A,
    SYMBOL_B,
    TIMEFRAME,
    TIME_OFFSET,
    WDO_KALMAN_Q,
    WDO_KALMAN_R,
    WDO_KALMAN_W,
    WINDOW,
)
from core.kalman_filter import KalmanBetaFilter  # noqa: E402
from core.risk_gate import EG_MIN_BARS, compute_engle_granger_pvalue  # noqa: E402
from core.signals import calc_beta_ols, calc_zscore, get_rho_status  # noqa: E402


INDICATOR_COLUMNS = (
    "eg_pvalue",
    "rho",
    "rho_level",
    "beta_value",
    "beta_delta_pct",
)
PRICE_COLUMNS = ("win_price", "wdo_price", "di_price")
MT5_SYMBOL_BY_PRICE_FIELD = {
    "win_price": SYMBOL_A,
    "wdo_price": SYMBOL_B,
    "di_price": DI_SYMBOL,
}


@dataclass
class BackfillStats:
    rows_total: int = 0
    rows_in_scope: int = 0
    rows_with_pair_prices: int = 0
    rows_missing_pair_prices: int = 0
    rows_insufficient_history: int = 0
    rows_eg_unavailable: int = 0
    rows_computed: int = 0
    rows_updated: int = 0
    dry_run: bool = False
    overwrite: bool = False
    source_db: str = "trades.db"
    date: str | None = None
    backup_path: str | None = None
    fetch_mt5: bool = False
    mt5_warmup_days: int = 0
    mt5_price_rows: int = 0
    price_rows_inserted: int = 0
    price_rows_updated: int = 0
    price_fields_updated: int = 0


def ensure_indicator_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add replay indicator columns to an existing bar_history."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(bar_history)").fetchall()}
    alters = {
        "eg_pvalue": "ALTER TABLE bar_history ADD COLUMN eg_pvalue REAL",
        "rho": "ALTER TABLE bar_history ADD COLUMN rho REAL",
        "rho_level": "ALTER TABLE bar_history ADD COLUMN rho_level INTEGER",
        "beta_value": "ALTER TABLE bar_history ADD COLUMN beta_value REAL",
        "beta_delta_pct": "ALTER TABLE bar_history ADD COLUMN beta_delta_pct REAL",
    }
    for col, sql in alters.items():
        if col not in existing:
            conn.execute(sql)


def load_rows(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM bar_history ORDER BY timestamp ASC").fetchall()
    return [dict(r) for r in rows]


# ─── Optional MT5 price backfill ────────────────────────────────────────────

Mt5Fetcher = Callable[[str, int, int], tuple[np.ndarray | None, np.ndarray | None]]


def _date_bounds_as_mt5_timestamps(date: str, warmup_days: int) -> tuple[int, int]:
    """Return [start, end) MT5 timestamps for local target date + warmup."""
    target = datetime.strptime(date, "%Y-%m-%d")
    start_local = target - timedelta(days=warmup_days)
    end_local = target + timedelta(days=1)
    return (
        int(start_local.timestamp()) - TIME_OFFSET,
        int(end_local.timestamp()) - TIME_OFFSET,
    )


def _default_mt5_fetcher(symbol: str, start_ts: int, end_ts: int):
    """Read historical bars from MT5. Lazy-imported so offline mode stays CI-safe."""
    import MetaTrader5 as mt5  # noqa: PLC0415
    from core.mt5_client import connect_mt5  # noqa: PLC0415

    if not connect_mt5():
        raise RuntimeError("MT5 unavailable; cannot fetch historical bars")
    rates = mt5.copy_rates_range(
        symbol,
        TIMEFRAME,
        datetime.fromtimestamp(start_ts),
        datetime.fromtimestamp(end_ts),
    )
    if rates is None or len(rates) == 0:
        return None, None
    closes = np.array([r["close"] for r in rates], dtype=float)
    times = np.array([r["time"] for r in rates], dtype=np.int64)
    return closes, times


def fetch_mt5_price_rows(
    *,
    date: str,
    warmup_days: int,
    mt5_fetcher: Mt5Fetcher | None = None,
) -> list[dict]:
    """Fetch WIN/WDO/DI closes and map them to local bar_history timestamps."""
    fetcher = mt5_fetcher or _default_mt5_fetcher
    start_ts, end_ts = _date_bounds_as_mt5_timestamps(date, warmup_days)
    rows_by_ts: dict[int, dict] = {}

    for field, symbol in MT5_SYMBOL_BY_PRICE_FIELD.items():
        closes, times = fetcher(symbol, start_ts, end_ts)
        if closes is None or times is None:
            continue
        for close, mt5_ts in zip(closes, times):
            local_ts = int(mt5_ts) + TIME_OFFSET
            dt = datetime.fromtimestamp(local_ts)
            if not (start_ts <= int(mt5_ts) < end_ts):
                continue
            entry = rows_by_ts.setdefault(
                local_ts,
                {
                    "timestamp": local_ts,
                    "date_str": dt.strftime("%Y-%m-%d"),
                    "bar_time": dt.strftime("%H:%M"),
                    "win_price": None,
                    "wdo_price": None,
                    "di_price": None,
                },
            )
            entry[field] = float(close)

    return [rows_by_ts[k] for k in sorted(rows_by_ts)]


def _price_change_plan(
    rows: list[dict],
    price_rows: list[dict],
    *,
    overwrite: bool = False,
) -> dict:
    existing = {int(r["timestamp"]): r for r in rows}
    rows_inserted = 0
    rows_updated = 0
    fields_updated = 0

    for item in price_rows:
        ts = int(item["timestamp"])
        row = existing.get(ts)
        non_null_fields = [f for f in PRICE_COLUMNS if item.get(f) is not None]
        if row is None:
            if non_null_fields:
                rows_inserted += 1
                fields_updated += len(non_null_fields)
            continue

        row_changed = False
        for field in non_null_fields:
            if overwrite or row.get(field) is None:
                row_changed = True
                fields_updated += 1
        if row_changed:
            rows_updated += 1

    return {
        "price_rows_inserted": rows_inserted,
        "price_rows_updated": rows_updated,
        "price_fields_updated": fields_updated,
    }


def merge_rows_with_prices(
    rows: list[dict],
    price_rows: list[dict],
    *,
    overwrite: bool = False,
) -> list[dict]:
    """Return an in-memory view of bar_history after applying price rows."""
    rows_by_ts = {int(r["timestamp"]): dict(r) for r in rows}
    for item in price_rows:
        ts = int(item["timestamp"])
        row = rows_by_ts.setdefault(
            ts,
            {
                "timestamp": ts,
                "date_str": item["date_str"],
                "bar_time": item["bar_time"],
                "win_price": None,
                "wdo_price": None,
                "di_price": None,
                "eg_pvalue": None,
                "rho": None,
                "rho_level": None,
                "beta_value": None,
                "beta_delta_pct": None,
            },
        )
        row.setdefault("date_str", item["date_str"])
        row.setdefault("bar_time", item["bar_time"])
        for field in PRICE_COLUMNS:
            if item.get(field) is not None and (overwrite or row.get(field) is None):
                row[field] = item[field]
    return [rows_by_ts[k] for k in sorted(rows_by_ts)]


def apply_price_rows(
    conn: sqlite3.Connection,
    rows: list[dict],
    price_rows: list[dict],
    *,
    overwrite: bool = False,
) -> dict:
    """Insert/update price rows. Default preserves existing non-NULL prices."""
    plan = _price_change_plan(rows, price_rows, overwrite=overwrite)
    existing = {int(r["timestamp"]): r for r in rows}

    for item in price_rows:
        ts = int(item["timestamp"])
        row = existing.get(ts)
        if row is None:
            conn.execute(
                """
                INSERT INTO bar_history
                (timestamp, date_str, bar_time, win_price, wdo_price, di_price)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(timestamp) DO NOTHING
                """,
                (
                    ts,
                    item["date_str"],
                    item["bar_time"],
                    item.get("win_price"),
                    item.get("wdo_price"),
                    item.get("di_price"),
                ),
            )
            continue

        set_parts: list[str] = []
        params: list[float] = []
        for field in PRICE_COLUMNS:
            value = item.get(field)
            if value is None:
                continue
            if overwrite or row.get(field) is None:
                set_parts.append(f"{field} = ?")
                params.append(value)
        if set_parts:
            params.append(ts)
            conn.execute(
                f"UPDATE bar_history SET {', '.join(set_parts)} WHERE timestamp = ?",
                params,
            )

    return plan


def compute_backfill_updates(rows: list[dict], date: str | None = None) -> tuple[list[dict], BackfillStats]:
    """Compute indicator values using only rows up to each bar timestamp."""
    stats = BackfillStats(rows_total=len(rows), date=date)
    updates: list[dict] = []

    kf = KalmanBetaFilter(
        initial_beta=BETA_INITIAL,
        trans_cov=WDO_KALMAN_Q,
        obs_cov=WDO_KALMAN_R,
    )
    wins: list[float] = []
    wdos: list[float] = []
    kf_betas: list[float] = []

    for row in rows:
        in_scope = date is None or row.get("date_str") == date
        if in_scope:
            stats.rows_in_scope += 1

        win_price = row.get("win_price")
        wdo_price = row.get("wdo_price")
        if win_price is None or wdo_price is None:
            if in_scope:
                stats.rows_missing_pair_prices += 1
            continue

        win = float(win_price)
        wdo = float(wdo_price)
        beta, _spread, _var = kf.update(win, wdo)
        wins.append(win)
        wdos.append(wdo)
        kf_betas.append(float(beta))

        if not in_scope:
            continue
        stats.rows_with_pair_prices += 1

        # Rho uses a rolling WINDOW and EG needs EG_MIN_BARS. We only write a
        # complete indicator set when all fields are meaningful enough for the
        # replay gate.
        if len(wins) <= WINDOW or len(wins) < EG_MIN_BARS:
            stats.rows_insufficient_history += 1
            continue

        win_arr = np.asarray(wins[-BARS:], dtype=float)
        wdo_arr = np.asarray(wdos[-BARS:], dtype=float)
        beta_ols = calc_beta_ols(win_arr, wdo_arr, window=min(WINDOW, len(win_arr)))
        _spread_arr, _z_arr, rho_arr = calc_zscore(
            win_arr,
            wdo_arr,
            beta=beta_ols,
            max_bars=len(win_arr),
        )
        rho = float(rho_arr[-1])
        rho_level = int(get_rho_status(rho)["level"])

        beta_value = float(kf_betas[-1])
        if len(kf_betas) > BETA_REF_WINDOW:
            beta_ref = float(np.mean(kf_betas[-BETA_REF_WINDOW:-WDO_KALMAN_W]))
        else:
            beta_ref = float(kf_betas[0])
        beta_delta_pct = (
            (beta_value - beta_ref) / abs(beta_ref) * 100.0
            if beta_ref != 0 else 0.0
        )

        eg_pvalue = compute_engle_granger_pvalue(win_arr, wdo_arr, int(row["timestamp"]))
        if eg_pvalue is None:
            stats.rows_eg_unavailable += 1
            continue

        stats.rows_computed += 1
        updates.append(
            {
                "timestamp": int(row["timestamp"]),
                "eg_pvalue": float(eg_pvalue),
                "rho": rho,
                "rho_level": rho_level,
                "beta_value": beta_value,
                "beta_delta_pct": beta_delta_pct,
            }
        )

    return updates, stats


def apply_updates(
    conn: sqlite3.Connection,
    updates: list[dict],
    *,
    overwrite: bool = False,
) -> int:
    """Write computed indicators. Default preserves existing non-NULL values."""
    updated = 0
    for item in updates:
        params = (
            item["eg_pvalue"],
            item["rho"],
            item["rho_level"],
            item["beta_value"],
            item["beta_delta_pct"],
            item["timestamp"],
        )
        if overwrite:
            cur = conn.execute(
                """
                UPDATE bar_history
                SET eg_pvalue = ?,
                    rho = ?,
                    rho_level = ?,
                    beta_value = ?,
                    beta_delta_pct = ?
                WHERE timestamp = ?
                """,
                params,
            )
        else:
            cur = conn.execute(
                """
                UPDATE bar_history
                SET eg_pvalue = COALESCE(eg_pvalue, ?),
                    rho = COALESCE(rho, ?),
                    rho_level = COALESCE(rho_level, ?),
                    beta_value = COALESCE(beta_value, ?),
                    beta_delta_pct = COALESCE(beta_delta_pct, ?)
                WHERE timestamp = ?
                  AND (
                    eg_pvalue IS NULL OR rho IS NULL OR rho_level IS NULL
                    OR beta_value IS NULL OR beta_delta_pct IS NULL
                  )
                """,
                params,
            )
        updated += cur.rowcount
    return updated


def create_backup(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{db_path}.backfill-{ts}.bak"
    shutil.copy2(db_path, backup_path)
    return backup_path


def run_backfill(
    *,
    source_db: str = "trades.db",
    date: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    backup: bool = True,
    fetch_mt5: bool = False,
    mt5_warmup_days: int = 3,
    mt5_fetcher: Mt5Fetcher | None = None,
) -> dict:
    if not os.path.exists(source_db):
        raise FileNotFoundError(source_db)
    if fetch_mt5 and date is None:
        raise ValueError("--fetch-mt5 requires --date")

    backup_path = None
    if backup and not dry_run:
        backup_path = create_backup(source_db)

    conn = sqlite3.connect(source_db, timeout=30.0)
    try:
        ensure_indicator_columns(conn)
        rows = load_rows(conn)
        price_rows: list[dict] = []
        price_plan = {
            "price_rows_inserted": 0,
            "price_rows_updated": 0,
            "price_fields_updated": 0,
        }

        if fetch_mt5:
            price_rows = fetch_mt5_price_rows(
                date=date,
                warmup_days=mt5_warmup_days,
                mt5_fetcher=mt5_fetcher,
            )
            price_plan = _price_change_plan(rows, price_rows, overwrite=overwrite)
            if not dry_run:
                price_plan = apply_price_rows(
                    conn,
                    rows,
                    price_rows,
                    overwrite=overwrite,
                )
                # The indicator pass below must see the freshly inserted warmup rows.
                rows = load_rows(conn)
            else:
                rows = merge_rows_with_prices(rows, price_rows, overwrite=overwrite)

        updates, stats = compute_backfill_updates(rows, date=date)
        stats.source_db = source_db
        stats.dry_run = dry_run
        stats.overwrite = overwrite
        stats.backup_path = backup_path
        stats.fetch_mt5 = fetch_mt5
        stats.mt5_warmup_days = mt5_warmup_days if fetch_mt5 else 0
        stats.mt5_price_rows = len(price_rows)
        stats.price_rows_inserted = price_plan["price_rows_inserted"]
        stats.price_rows_updated = price_plan["price_rows_updated"]
        stats.price_fields_updated = price_plan["price_fields_updated"]
        if not dry_run:
            stats.rows_updated = apply_updates(conn, updates, overwrite=overwrite)
            conn.commit()
        else:
            stats.rows_updated = 0
        return asdict(stats)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _print_summary(summary: dict) -> None:
    print()
    print("=" * 72)
    print("bar_history indicator backfill")
    print("=" * 72)
    for key in (
        "source_db",
        "date",
        "dry_run",
        "overwrite",
        "fetch_mt5",
        "mt5_warmup_days",
        "backup_path",
        "mt5_price_rows",
        "price_rows_inserted",
        "price_rows_updated",
        "price_fields_updated",
        "rows_total",
        "rows_in_scope",
        "rows_with_pair_prices",
        "rows_missing_pair_prices",
        "rows_insufficient_history",
        "rows_eg_unavailable",
        "rows_computed",
        "rows_updated",
    ):
        print(f"  {key:28s} {summary.get(key)}")
    print("=" * 72)
    print("JSON:", json.dumps(summary, sort_keys=True))


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill eg/rho/beta indicator columns in bar_history."
    )
    parser.add_argument("--source", default="trades.db", help="SQLite DB path (default: trades.db)")
    parser.add_argument("--date", help="Optional date_str filter, YYYY-MM-DD")
    parser.add_argument(
        "--fetch-mt5",
        action="store_true",
        help="Fetch historical WIN/WDO/DI closes from MT5 before recomputing indicators",
    )
    parser.add_argument(
        "--mt5-warmup-days",
        type=int,
        default=3,
        help="Calendar days before --date to fetch as indicator warmup context (default: 3)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing non-NULL indicators")
    parser.add_argument("--no-backup", action="store_true", help="Do not create .bak before writing")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.date is not None:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"[ERRO] --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
            return 2

    summary = run_backfill(
        source_db=args.source,
        date=args.date,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        backup=not args.no_backup,
        fetch_mt5=args.fetch_mt5,
        mt5_warmup_days=args.mt5_warmup_days,
    )
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
