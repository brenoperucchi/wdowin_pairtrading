"""Replay the Execution Timeline funnel for a given date.

Reconstructs DATA→INDICATORS→ELIGIBILITY→RISK→SIGNAL→ORDER→EXECUTION→EXIT
events from `bar_history` rows persisted by the live server, replays them
through the same `risk_gate()` + `TradeEngine.evaluate()` used in
production (paper mode), and records every event to a per-day SQLite DB
under `replays/`. The source `trades.db` is never written.

CLI:
    py.exe -3.12 scripts/replay_execution_timeline.py --date YYYY-MM-DD \
        [--source trades.db] [--out replays/]

Pre-Slice-A bars without persisted indicators emit `MISSING_<FIELD>` DATA
events instead of crashing the loop.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Allow `python scripts/replay_execution_timeline.py ...` from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.config import LIVE_ORDERS  # noqa: E402
from core.execution_timeline import (  # noqa: E402
    current_bottleneck,
    current_live_issue,
    init_timeline_table,
    record_event,
)
from core.risk_gate import risk_gate  # noqa: E402
from core.timeline_emit import (  # noqa: E402
    TIMELINE_RISK_REASONS,
    emit_closed_bar_timeline,
)
from core.trade_engine import TradeEngine  # noqa: E402


REQUIRED_BAR_FIELDS = (
    "win_price",
    "wdo_price",
    "di_price",
    "eg_pvalue",
    "rho",
    "rho_level",
    "beta_value",
    "beta_delta_pct",
)


@dataclass
class ReplayStats:
    bars_total: int = 0
    bars_processed: int = 0
    bars_skipped_missing: int = 0
    missing_by_field: Counter = None
    blockers_by_phase_reason: Counter = None
    trades_opened: int = 0
    trades_closed: int = 0
    pnl_paper: float = 0.0
    last_bar_ts_iso: str | None = None

    def __post_init__(self):
        if self.missing_by_field is None:
            self.missing_by_field = Counter()
        if self.blockers_by_phase_reason is None:
            self.blockers_by_phase_reason = Counter()


# ─── Bar source ─────────────────────────────────────────────────────────────

def load_bars_for_date(source_db: str, date_str: str) -> list[dict]:
    """Read raw bar_history rows for `date_str`, oldest first.

    Reads `source_db` read-only by opening with `mode=ro` URI to be doubly
    sure replay never mutates the live trades.db.
    """
    abs_path = os.path.abspath(source_db)
    uri = f"file:{abs_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    try:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM bar_history WHERE date_str = ? ORDER BY timestamp ASC",
            (date_str,),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _missing_required_fields(row: dict) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_BAR_FIELDS:
        # `field in row` is true even when value is None — sqlite returns the column.
        if field not in row or row.get(field) is None:
            missing.append(field)
    return missing


# ─── Per-bar emission ───────────────────────────────────────────────────────

def _emit_missing_data_event(
    *,
    db_path: str,
    closed_bar_ts: int | None,
    field: str,
    bar_time: str,
    row_ts_iso: str,
) -> None:
    bar_key = closed_bar_ts if closed_bar_ts is not None else row_ts_iso
    record_event(
        db_path,
        timestamp=row_ts_iso,
        closed_bar_ts=closed_bar_ts,
        correlation_id=f"replay:bar:{bar_key}",
        dedupe_key=f"replay:bar:{bar_key}:DATA:MISSING_{field.upper()}",
        phase="DATA",
        event=f"MISSING_{field.upper()}",
        status="FAILED",
        severity="error",
        message=f"bar_history row at {bar_time} missing {field}; bar skipped",
        payload_json={"field": field, "bar_time": bar_time},
    )


def _row_to_iso_ts(row: dict) -> str:
    """ISO timestamp for the bar's wall-clock moment."""
    ts = row.get("timestamp")
    return datetime.fromtimestamp(int(ts)).isoformat(timespec="seconds")


def _row_timestamp_label(row: dict) -> str:
    """Non-wall-clock fallback label for rows with corrupt timestamps."""
    date_str = row.get("date_str") or "UNKNOWN_DATE"
    bar_time = row.get("bar_time") or "UNKNOWN_TIME"
    try:
        hour, minute = str(bar_time).split(":")[:2]
        return f"{date_str}T{int(hour):02d}:{int(minute):02d}:00"
    except Exception:
        return f"{date_str} {bar_time}"


def _process_bar(
    row: dict,
    *,
    engine: TradeEngine,
    replay_db: str,
    stats: ReplayStats,
) -> None:
    bar_time = row.get("bar_time") or "00:00"
    try:
        closed_bar_ts = int(row["timestamp"])
        row_ts_iso = _row_to_iso_ts(row)
        now_dt = datetime.fromisoformat(row_ts_iso)
        stats.last_bar_ts_iso = row_ts_iso
    except Exception:
        stats.missing_by_field["timestamp"] += 1
        _emit_missing_data_event(
            db_path=replay_db,
            closed_bar_ts=None,
            field="timestamp",
            bar_time=bar_time,
            row_ts_iso=_row_timestamp_label(row),
        )
        stats.bars_skipped_missing += 1
        return

    missing = _missing_required_fields(row)
    if missing:
        for field in missing:
            stats.missing_by_field[field] += 1
            _emit_missing_data_event(
                db_path=replay_db,
                closed_bar_ts=closed_bar_ts,
                field=field,
                bar_time=bar_time,
                row_ts_iso=row_ts_iso,
            )
        stats.bars_skipped_missing += 1
        return

    try:
        hour_str, minute_str = bar_time.split(":")
        hour, minute = int(hour_str), int(minute_str)
    except Exception:
        # Malformed bar_time — treat as missing.
        stats.missing_by_field["bar_time"] += 1
        _emit_missing_data_event(
            db_path=replay_db,
            closed_bar_ts=closed_bar_ts,
            field="bar_time",
            bar_time=bar_time,
            row_ts_iso=row_ts_iso,
        )
        stats.bars_skipped_missing += 1
        return

    z_wdo = float(row["z_wdo"] or 0.0)
    z_di = float(row["z_di"] or 0.0)
    win_price = float(row["win_price"])
    wdo_price = float(row["wdo_price"])
    rho = float(row["rho"])
    rho_level = int(row["rho_level"])
    beta_value = float(row["beta_value"])
    beta_delta_pct = float(row["beta_delta_pct"])
    eg_pvalue = float(row["eg_pvalue"])
    nwe_upper = float(row.get("nwe_upper") or 0.0)
    nwe_lower = float(row.get("nwe_lower") or 0.0)
    nwe_is_up = bool(row.get("nwe_is_up") or 0)

    today_str = now_dt.strftime("%Y-%m-%d")
    trades_today_count = engine.count_trades_today(today_str)
    daily_pnl_brl = engine.pnl_today(today_str)
    minutes_since_last_loss = engine.minutes_since_last_loss(now=now_dt)

    pre_entry_gate = risk_gate(
        z_wdo=z_wdo,
        z_di=z_di,
        rho_level=rho_level,
        beta_delta_pct=beta_delta_pct,
        eg_pvalue=eg_pvalue,
        hour=hour,
        minute=minute,
        bar_close_confirmed=True,
        trades_today_count=trades_today_count,
        daily_pnl_brl=daily_pnl_brl,
        minutes_since_last_loss=minutes_since_last_loss,
        mt5_connected=True,
        joh_open=None,
        hmm_state=None,
    )

    trade_result = engine.evaluate(
        z_wdo=z_wdo,
        z_di=z_di,
        win_price=win_price,
        wdo_price=wdo_price,
        rho=rho,
        gate=pre_entry_gate,
        hmm_state=None,
        hour=hour,
        minute=minute,
        beta_value=beta_value,
        nwe_is_up=nwe_is_up,
        nwe_upper=nwe_upper,
        nwe_lower=nwe_lower,
        closed_bar_ts=closed_bar_ts,
        entry_win_price=win_price,
        entry_wdo_price=wdo_price,
        now_dt=now_dt,
    )

    emit_closed_bar_timeline(
        db_path=replay_db,
        closed_bar_ts=closed_bar_ts,
        gate=pre_entry_gate,
        trade_result=trade_result,
        z_wdo=z_wdo,
        z_di=z_di,
        rho=rho,
        rho_level=rho_level,
        beta_delta_pct=beta_delta_pct,
        eg_pvalue=eg_pvalue,
        joh_open=None,
        mt5_connected=True,
        trades_today_count=trades_today_count,
        daily_pnl_brl=daily_pnl_brl,
        minutes_since_last_loss=minutes_since_last_loss,
        now_dt=now_dt,
    )

    for reason in pre_entry_gate.get("reasons", []):
        if reason == "BAR_NOT_CLOSED":
            continue
        phase = "RISK" if reason in TIMELINE_RISK_REASONS else "ELIGIBILITY"
        stats.blockers_by_phase_reason[(phase, reason)] += 1

    strategies = trade_result.get("strategies") or {}
    for strat_result in strategies.values():
        if (
            strat_result.get("open_trade") is not None
            and strat_result.get("action") in {"BUY_WIN", "SELL_WIN"}
        ):
            stats.trades_opened += 1
        if strat_result.get("exit_reason"):
            stats.trades_closed += 1

    stats.bars_processed += 1


# ─── Summary + META ─────────────────────────────────────────────────────────

def _summarize(stats: ReplayStats, *, engine: TradeEngine, replay_date: str) -> dict:
    pnl_paper = engine.pnl_today(replay_date)
    bottleneck = current_bottleneck(engine.db_path)
    live_issue = current_live_issue(engine.db_path)
    return {
        "replay_date": replay_date,
        "bars_total": stats.bars_total,
        "bars_processed": stats.bars_processed,
        "bars_skipped_missing": stats.bars_skipped_missing,
        "missing_by_field": dict(stats.missing_by_field),
        "blockers_by_phase_reason": {
            f"{phase}:{reason}": count
            for (phase, reason), count in stats.blockers_by_phase_reason.items()
        },
        "trades_opened": stats.trades_opened,
        "trades_closed": stats.trades_closed,
        "pnl_paper_brl": round(pnl_paper, 2),
        "last_bar_timestamp": stats.last_bar_ts_iso,
        "current_bottleneck": _strip_payload(bottleneck),
        "current_live_issue": _strip_payload(live_issue),
    }


def _strip_payload(event: dict | None) -> dict | None:
    """Trim the heavy `payload_json` field out of nested summary dicts."""
    if not event:
        return None
    out = dict(event)
    out.pop("payload_json", None)
    return out


def _emit_meta_event(*, db_path: str, summary: dict) -> None:
    record_event(
        db_path,
        timestamp=summary.get("last_bar_timestamp") or f"{summary['replay_date']}T00:00:00",
        dedupe_key=f"replay:META:{summary['replay_date']}",
        phase="EXIT",
        event="REPLAY_SUMMARY",
        status="OK",
        severity="info",
        message=f"Replay completed for {summary['replay_date']}",
        payload_json=summary,
    )


def _print_summary(summary: dict) -> None:
    print()
    print("=" * 60)
    print(f"Replay summary — {summary['replay_date']}")
    print("=" * 60)
    print(f"  bars_total:           {summary['bars_total']}")
    print(f"  bars_processed:       {summary['bars_processed']}")
    print(f"  bars_skipped_missing: {summary['bars_skipped_missing']}")
    if summary["missing_by_field"]:
        print("  missing_by_field:")
        for field, count in sorted(summary["missing_by_field"].items()):
            print(f"    {field:18s} {count}")
    if summary["blockers_by_phase_reason"]:
        print("  blockers_by_phase_reason:")
        for key, count in sorted(summary["blockers_by_phase_reason"].items()):
            print(f"    {key:32s} {count}")
    print(f"  trades_opened:        {summary['trades_opened']}")
    print(f"  trades_closed:        {summary['trades_closed']}")
    print(f"  pnl_paper_brl:        {summary['pnl_paper_brl']}")
    bn = summary.get("current_bottleneck")
    li = summary.get("current_live_issue")
    if bn:
        print(f"  current_bottleneck:   {bn.get('phase')}/{bn.get('event')} ({bn.get('strategy') or '-'})")
    else:
        print("  current_bottleneck:   none")
    if li:
        print(f"  current_live_issue:   {li.get('event')}")
    else:
        print("  current_live_issue:   none")
    print("=" * 60)


# ─── Driver ─────────────────────────────────────────────────────────────────

def run_replay(
    *,
    date_str: str,
    source_db: str,
    out_dir: str,
) -> dict:
    """Run the replay. Returns the summary dict (also emitted as META event)."""
    if LIVE_ORDERS:
        raise RuntimeError(
            "LIVE_ORDERS=True; refusing to replay. Replay must run with paper-mode config."
        )
    if "MetaTrader5" in sys.modules:
        # If something already imported MT5 before us (e.g., a test fixture),
        # we let it be — the replay itself never calls into it. But we shout
        # so the human running this knows.
        print(
            "[WARN] MetaTrader5 already imported by parent process; "
            "replay will not invoke it.",
            file=sys.stderr,
        )

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    replay_db = os.path.join(out_dir, f"execution_timeline_{date_str}.db")
    _reset_replay_db(replay_db)

    init_timeline_table(replay_db)
    engine = TradeEngine(db_path=replay_db)

    rows = load_bars_for_date(source_db, date_str)
    stats = ReplayStats(bars_total=len(rows))

    for row in rows:
        _process_bar(row, engine=engine, replay_db=replay_db, stats=stats)

    summary = _summarize(stats, engine=engine, replay_date=date_str)
    _emit_meta_event(db_path=replay_db, summary=summary)
    _print_summary(summary)
    return summary


def _reset_replay_db(replay_db: str) -> None:
    """Start each replay from a clean DB so reruns are deterministic."""
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{replay_db}{suffix}")
        if path.exists():
            path.unlink()


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay Execution Timeline for a given date."
    )
    parser.add_argument(
        "--date", required=True,
        help="Date to replay, format YYYY-MM-DD (matches bar_history.date_str).",
    )
    parser.add_argument(
        "--source", default="trades.db",
        help="Source SQLite DB containing bar_history (default: trades.db).",
    )
    parser.add_argument(
        "--out", default="replays",
        help="Output directory for replay DB (default: replays/).",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"[ERRO] --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 2

    if not os.path.exists(args.source):
        print(f"[ERRO] source DB not found: {args.source}", file=sys.stderr)
        return 2

    summary = run_replay(date_str=args.date, source_db=args.source, out_dir=args.out)
    print(f"\nWrote replay DB: {os.path.join(args.out, f'execution_timeline_{args.date}.db')}")
    print(f"Summary JSON: {json.dumps(summary, default=str)[:200]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
