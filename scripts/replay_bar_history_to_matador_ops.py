#!/usr/bin/env python3
"""Replay local bar_history into matador_ops for dashboard inspection.

This intentionally writes synthetic rows only when --commit is passed. Rows are
tagged with z_source='REPLAY_*' so they can be distinguished from real paper/live
trades and safely replaced later.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config as cfg


STRATEGIES = ("CONS_BASE", "WDO_NWE", "DI_NWE")


@dataclass
class Trade:
    strategy: str
    direction: str
    timestamp_in: str
    z_in: float
    z_source: str
    qty_win: int
    price_win_in: float
    price_wdo_in: float | None
    max_pts_favor: float = 0.0
    be_active: bool = False
    timestamp_out: str | None = None
    exit_reason: str | None = None
    price_win_out: float | None = None
    price_wdo_out: float | None = None
    pnl_brl: float | None = None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Replay one date from bar_history into matador_ops."
    )
    p.add_argument("--date", required=True, help="Date to replay, YYYY-MM-DD")
    p.add_argument("--db", default="trades.db", help="SQLite DB path")
    p.add_argument(
        "--mode",
        choices=("signal-only", "z-anomaly", "ops"),
        default="ops",
        help=(
            "Replay strictness. ops applies session, z-anomaly, max trades, "
            "daily loss and loss cooldown; it cannot reconstruct rho/EG/beta."
        ),
    )
    p.add_argument(
        "--replace-replay",
        action="store_true",
        help="Delete existing REPLAY_* rows for the date before inserting.",
    )
    p.add_argument(
        "--allow-mix-real",
        action="store_true",
        help="Allow inserting replay rows when non-replay rows already exist for the date.",
    )
    p.add_argument("--commit", action="store_true", help="Write rows to matador_ops")
    return p.parse_args()


def bar_minutes(row: sqlite3.Row) -> int:
    hour, minute = [int(x) for x in row["bar_time"].split(":")[:2]]
    return hour * 60 + minute


def timestamp_for(row: sqlite3.Row) -> str:
    return f"{row['date_str']} {row['bar_time']}:00"


def in_entry_session(row: sqlite3.Row) -> bool:
    t = bar_minutes(row)
    start = cfg.ENTRY_START_H * 60 + cfg.ENTRY_START_M
    end = cfg.ENTRY_END_H * 60 + cfg.ENTRY_END_M
    return start <= t <= end


def is_force_close(row: sqlite3.Row) -> bool:
    t = bar_minutes(row)
    fc = cfg.FORCE_CLOSE_H * 60 + cfg.FORCE_CLOSE_M
    return t >= fc


def nwe_pass(row: sqlite3.Row, direction: str) -> bool:
    win_price = float(row["win_price"])
    upper = float(row["nwe_upper"] or 0.0)
    lower = float(row["nwe_lower"] or 0.0)
    is_up = bool(row["nwe_is_up"])
    band_width = upper - lower if upper > 0 and lower > 0 else 1.0
    if band_width < 1e-10:
        band_width = 1.0

    if direction == "BUY":
        if is_up:
            return False
        if lower > 0 and win_price > lower + band_width * cfg.NWE_BAND_MULT:
            return False
    else:
        if not is_up:
            return False
        if upper > 0 and win_price < upper - band_width * cfg.NWE_BAND_MULT:
            return False
    return True


def signal_for(row: sqlite3.Row, strategy: str) -> tuple[str, float, str] | None:
    z_wdo = float(row["z_wdo"])
    z_di = float(row["z_di"] or 0.0)

    if strategy == "CONS_BASE":
        if (
            (z_wdo <= -cfg.Z_ENTRY and z_di <= -cfg.Z_ATTENTION)
            or (z_wdo <= -cfg.Z_ATTENTION and z_di <= -cfg.Z_ENTRY)
        ):
            return "BUY", z_wdo, "REPLAY_CONSENSO"
        if (
            (z_wdo >= cfg.Z_ENTRY and z_di >= cfg.Z_ATTENTION)
            or (z_wdo >= cfg.Z_ATTENTION and z_di >= cfg.Z_ENTRY)
        ):
            return "SELL", z_wdo, "REPLAY_CONSENSO"

    if strategy == "WDO_NWE":
        if z_wdo <= -cfg.Z_ENTRY and nwe_pass(row, "BUY"):
            return "BUY", z_wdo, "REPLAY_WDO_KALMAN"
        if z_wdo >= cfg.Z_ENTRY and nwe_pass(row, "SELL"):
            return "SELL", z_wdo, "REPLAY_WDO_KALMAN"

    if strategy == "DI_NWE":
        if z_di <= -cfg.Z_ENTRY and nwe_pass(row, "BUY"):
            return "BUY", z_di, "REPLAY_DI_JOHANSEN"
        if z_di >= cfg.Z_ENTRY and nwe_pass(row, "SELL"):
            return "SELL", z_di, "REPLAY_DI_JOHANSEN"

    return None


def close_if_needed(trade: Trade, row: sqlite3.Row) -> bool:
    is_buy = trade.direction == "BUY"
    win_price = float(row["win_price"])
    pts_favor = (
        win_price - trade.price_win_in if is_buy else trade.price_win_in - win_price
    )

    if pts_favor > trade.max_pts_favor:
        trade.max_pts_favor = pts_favor

    be_act = cfg.BUY_BE_ACT if is_buy else cfg.SELL_BE_ACT
    be_lock = cfg.BUY_BE_LOCK if is_buy else cfg.SELL_BE_LOCK
    tp = cfg.BUY_TP if is_buy else cfg.SELL_TP
    sl = cfg.BUY_SL if is_buy else cfg.SELL_SL

    if not trade.be_active and trade.max_pts_favor >= be_act:
        trade.be_active = True

    reason = None
    if pts_favor >= tp:
        reason = "TARGET"
    elif trade.be_active and pts_favor <= be_lock:
        reason = "BE_STOP"
    elif not trade.be_active and pts_favor <= -sl:
        reason = "STOP_LOSS"

    if is_force_close(row):
        reason = "FORCE_CLOSE"

    if not reason:
        return False

    trade.timestamp_out = timestamp_for(row)
    trade.exit_reason = reason
    trade.price_win_out = win_price
    trade.price_wdo_out = row["wdo_price"]
    trade.pnl_brl = round(pts_favor * cfg.WIN_CONTRACTS * cfg.WIN_PV, 2)
    return True


def load_rows(conn: sqlite3.Connection, date_str: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT * FROM bar_history WHERE date_str = ? ORDER BY timestamp ASC",
        (date_str,),
    ).fetchall()


def replay(rows: list[sqlite3.Row], mode: str) -> tuple[list[Trade], list[Trade]]:
    open_trades: dict[str, Trade | None] = {s: None for s in STRATEGIES}
    closed: list[Trade] = []
    entries_today = 0
    daily_pnl = 0.0
    last_loss_min: int | None = None

    for row in rows:
        # Phase 1: exits first, matching TradeEngine.evaluate().
        for strategy, trade in list(open_trades.items()):
            if trade is None:
                continue
            if close_if_needed(trade, row):
                closed.append(trade)
                daily_pnl += trade.pnl_brl or 0.0
                if (trade.pnl_brl or 0.0) < 0:
                    last_loss_min = bar_minutes(row)
                open_trades[strategy] = None

        if not in_entry_session(row):
            continue

        if mode in ("z-anomaly", "ops"):
            if abs(float(row["z_wdo"])) >= cfg.Z_ANOMALY:
                continue
            if row["z_di"] is not None and abs(float(row["z_di"])) >= cfg.Z_ANOMALY:
                continue

        if mode == "ops":
            if entries_today >= cfg.MAX_TRADES_PER_DAY:
                continue
            if daily_pnl <= -cfg.DAILY_LOSS_LIMIT_BRL:
                continue
            if last_loss_min is not None:
                if bar_minutes(row) - last_loss_min < cfg.LOSS_COOLDOWN_MIN:
                    continue

        # Phase 2: entries per independent slot.
        for strategy in STRATEGIES:
            if open_trades[strategy] is not None:
                continue
            if mode == "ops" and entries_today >= cfg.MAX_TRADES_PER_DAY:
                break
            sig = signal_for(row, strategy)
            if sig is None:
                continue
            direction, z_in, z_source = sig
            open_trades[strategy] = Trade(
                strategy=strategy,
                direction=direction,
                timestamp_in=timestamp_for(row),
                z_in=round(float(z_in), 4),
                z_source=z_source,
                qty_win=cfg.WIN_CONTRACTS,
                price_win_in=float(row["win_price"]),
                price_wdo_in=row["wdo_price"],
            )
            entries_today += 1

    still_open = [t for t in open_trades.values() if t is not None]
    return closed, still_open


def summarize(closed: list[Trade], still_open: list[Trade]) -> None:
    target_wins = sum(1 for t in closed if t.exit_reason == "TARGET")
    profitable = sum(1 for t in closed if (t.pnl_brl or 0.0) > 0.0)
    pnl = sum(t.pnl_brl or 0.0 for t in closed)
    target_wr = (target_wins / len(closed) * 100.0) if closed else 0.0
    profitable_wr = (profitable / len(closed) * 100.0) if closed else 0.0
    print(
        f"Replay result: closed={len(closed)} open={len(still_open)} "
        f"target_wins={target_wins} target_wr={target_wr:.1f}% "
        f"profitable={profitable} profitable_wr={profitable_wr:.1f}% "
        f"pnl=R${pnl:.2f}"
    )
    for t in closed:
        print(
            f"  {t.strategy:9s} {t.direction:4s} {t.timestamp_in[11:16]} "
            f"@{t.price_win_in:.0f} -> {t.timestamp_out[11:16]} "
            f"@{t.price_win_out:.0f} {t.exit_reason:11s} "
            f"pnl=R${t.pnl_brl:.2f}"
        )
    for t in still_open:
        print(
            f"  OPEN {t.strategy:9s} {t.direction:4s} "
            f"{t.timestamp_in[11:16]} @{t.price_win_in:.0f}"
        )


def backup_db(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_suffix(db_path.suffix + f".bak-{stamp}")
    shutil.copy2(db_path, backup)
    return backup


def assert_can_write(
    conn: sqlite3.Connection,
    date_str: str,
    *,
    replace_replay: bool,
    allow_mix_real: bool,
) -> None:
    replay_count = conn.execute(
        "SELECT COUNT(*) FROM matador_ops WHERE date(timestamp_in)=? "
        "AND z_source LIKE 'REPLAY_%'",
        (date_str,),
    ).fetchone()[0]
    real_count = conn.execute(
        "SELECT COUNT(*) FROM matador_ops WHERE date(timestamp_in)=? "
        "AND (z_source IS NULL OR z_source NOT LIKE 'REPLAY_%')",
        (date_str,),
    ).fetchone()[0]

    if replay_count and not replace_replay:
        raise SystemExit(
            f"Refusing to duplicate {replay_count} existing replay rows. "
            "Use --replace-replay."
        )
    if real_count and not allow_mix_real:
        raise SystemExit(
            f"Refusing to mix replay with {real_count} non-replay rows. "
            "Use --allow-mix-real if this is intentional."
        )


def insert_trades(
    conn: sqlite3.Connection,
    date_str: str,
    closed: list[Trade],
    still_open: list[Trade],
    *,
    replace_replay: bool,
) -> None:
    if replace_replay:
        conn.execute(
            "DELETE FROM matador_ops WHERE date(timestamp_in)=? "
            "AND z_source LIKE 'REPLAY_%'",
            (date_str,),
        )

    rows = closed + still_open
    for t in rows:
        conn.execute(
            """
            INSERT INTO matador_ops (
                timestamp_in, status, direction, z_in, z_source, strategy,
                rho_in, beta_in, qty_win, price_win_in, price_wdo_in,
                timestamp_out, exit_reason, price_win_out, price_wdo_out,
                pnl_brl, max_pts_favor, be_active, hmm_state
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                t.timestamp_in,
                "CLOSED" if t.timestamp_out else "OPEN",
                t.direction,
                t.z_in,
                t.z_source,
                t.strategy,
                t.qty_win,
                t.price_win_in,
                t.price_wdo_in,
                t.timestamp_out,
                t.exit_reason,
                t.price_win_out,
                t.price_wdo_out,
                t.pnl_brl,
                t.max_pts_favor,
                1 if t.be_active else 0,
                "REPLAY_BAR_HISTORY",
            ),
        )
    conn.commit()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    conn = sqlite3.connect(db_path)

    rows = load_rows(conn, args.date)
    if not rows:
        raise SystemExit(f"No bar_history rows found for {args.date} in {db_path}")

    print(
        "WARNING: this replay cannot reconstruct rho/EG/beta/bar-close state "
        "from bar_history; use it for dashboard trajectory inspection only."
    )
    print(
        f"Source: {db_path} bar_history date={args.date} bars={len(rows)} "
        f"first={rows[0]['bar_time']} last={rows[-1]['bar_time']} mode={args.mode}"
    )
    closed, still_open = replay(rows, args.mode)
    summarize(closed, still_open)

    if not args.commit:
        print("\nDry-run only. Re-run with --commit to populate matador_ops.")
        conn.close()
        return 0

    assert_can_write(
        conn,
        args.date,
        replace_replay=args.replace_replay,
        allow_mix_real=args.allow_mix_real,
    )
    backup = backup_db(db_path)
    insert_trades(
        conn,
        args.date,
        closed,
        still_open,
        replace_replay=args.replace_replay,
    )
    conn.close()
    print(f"\nInserted {len(closed) + len(still_open)} REPLAY rows.")
    print(f"Backup created: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
