"""Seed synthetic trades into matador_ops for TASK-1 visual validation.

Inserts two DEMO trades into the live `matador_ops` table so the dashboard's
trade markers (▲ BUY / ▼ SELL entry, ■ exit) can be verified end-to-end
without waiting for a real session.

- Marked with `z_source='REPLAY_DEMO_*'` so the paper-vs-backtest reconciler
  ignores them (TASK-3 slice 8 added the `z_source NOT LIKE 'REPLAY_%'` guard).
- Use `--undo` to remove every REPLAY_DEMO_* row.
- Markers only render in LIVE view (no historical date selected) AND when the
  trade times fall inside a bar that exists in `bar_history` for the same date.
  Run this during a live session so the alignment finds real bars.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = str(_REPO_ROOT / "trades.db")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _has_bars(db_path: str, date_str: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM bar_history WHERE date_str = ?",
                (date_str,),
            ).fetchone()[0]
        )
    finally:
        conn.close()


def _bar_window(db_path: str, date_str: str) -> tuple[str, str] | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT MIN(bar_time), MAX(bar_time) FROM bar_history WHERE date_str = ?",
            (date_str,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0] or not row[1]:
        return None
    return row[0], row[1]


def seed(db_path: str, date_str: str) -> list[int]:
    """Insert 2 demo trades and return the new row ids."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        rows = [
            # CLOSED BUY: entry 10:00, exit 11:30, +TP, CONS_BASE
            (
                f"{date_str} 10:00:00", "CLOSED", "BUY", -2.10, "REPLAY_DEMO_CONS_TP",
                "CONS_BASE", -0.62, 1.18, 2,
                129500.0, 5500.0,
                f"{date_str} 11:30:00", "TAKE_PROFIT", 130100.0, 5520.0, 240.0,
                60.0, 1, "BULL", 0,
            ),
            # OPEN SELL: entry 14:00, no exit, WDO_NWE
            (
                f"{date_str} 14:00:00", "OPEN", "SELL", 2.45, "REPLAY_DEMO_WDO_OPEN",
                "WDO_NWE", -0.58, 1.22, 2,
                130200.0, 5530.0,
                None, None, None, None, None,
                0.0, 0, "CHOP", 0,
            ),
        ]
        ids: list[int] = []
        for row in rows:
            cur.execute(
                """
                INSERT INTO matador_ops (
                    timestamp_in, status, direction, z_in, z_source,
                    strategy, rho_in, beta_in, qty_win,
                    price_win_in, price_wdo_in,
                    timestamp_out, exit_reason, price_win_out, price_wdo_out, pnl_brl,
                    max_pts_favor, be_active, hmm_state, live
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            ids.append(cur.lastrowid)
        conn.commit()
        return ids
    finally:
        conn.close()


def undo(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM matador_ops WHERE z_source LIKE 'REPLAY_DEMO_%'"
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--date", default=_today_str(), help="YYYY-MM-DD (default: today)")
    parser.add_argument("--undo", action="store_true", help="Remove all DEMO_* rows")
    args = parser.parse_args(argv)

    if args.undo:
        n = undo(args.db)
        print(f"removed {n} DEMO_* row(s) from {args.db}")
        return 0

    bars = _has_bars(args.db, args.date)
    print(f"date={args.date} bar_history rows={bars}", file=sys.stderr)
    if bars == 0:
        print(
            "warning: no bar_history for this date. Markers will only render "
            "after live bars accumulate or you backfill via "
            "scripts/backfill_bar_history_indicators.py --fetch-mt5 --date "
            f"{args.date}",
            file=sys.stderr,
        )
    else:
        window = _bar_window(args.db, args.date)
        if window:
            print(f"bar window {window[0]}–{window[1]}", file=sys.stderr)

    ids = seed(args.db, args.date)
    print(f"inserted {len(ids)} REPLAY_DEMO trade(s): ids={ids}")
    print("revert with: python scripts/seed_dashboard_demo_trades.py --undo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
