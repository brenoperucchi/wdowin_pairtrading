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

from core import bar_history_db as bhdb  # noqa: E402
from core.config import LIVE_ORDERS  # noqa: E402
from core import runtime_config  # noqa: E402
from core.execution_timeline import (  # noqa: E402
    current_bottleneck,
    current_live_issue,
    init_timeline_table,
    record_event,
)
from core.risk_gate import (  # noqa: E402
    compute_engle_granger_pvalue,
    reset_eg_cache,
    risk_gate,
)
from core.timeline_emit import (  # noqa: E402
    TIMELINE_RISK_REASONS,
    emit_closed_bar_timeline,
)
from core.trade_engine import TradeEngine  # noqa: E402


REQUIRED_BAR_FIELDS = (
    "win_price",
    "wdo_price",
    "di_price",
    "rho",
    "rho_level",
    "beta_value",
    "beta_delta_pct",
)


@dataclass(frozen=True)
class ReplayRuntimeProfile:
    eg_threshold: float
    eg_bars: int
    eg_recalc: str
    rho_breakdown_level: int
    beta_delta_max: float
    eg_strategies: tuple[str, ...]
    z_anomaly: float
    simulation: dict
    entry_start_h: int
    entry_start_m: int
    entry_end_h: int
    entry_end_m: int
    force_close_h: int
    force_close_m: int
    buy_sl: int
    buy_tp: int
    buy_be_act: int
    buy_be_lock: int
    sell_sl: int
    sell_tp: int
    sell_be_act: int
    sell_be_lock: int

    @classmethod
    def from_mapping(cls, payload: dict) -> "ReplayRuntimeProfile":
        return cls(
            eg_threshold=float(payload["eg_threshold"]),
            eg_bars=int(payload["eg_bars"]),
            eg_recalc=str(payload["eg_recalc"]),
            rho_breakdown_level=int(payload["rho_breakdown_level"]),
            beta_delta_max=float(payload["beta_delta_max"]),
            eg_strategies=tuple(payload["eg_strategies"]),
            z_anomaly=float(payload["z_anomaly"]),
            simulation=dict(payload["simulation"]),
            entry_start_h=int(payload["entry_start_h"]),
            entry_start_m=int(payload["entry_start_m"]),
            entry_end_h=int(payload["entry_end_h"]),
            entry_end_m=int(payload["entry_end_m"]),
            force_close_h=int(payload["force_close_h"]),
            force_close_m=int(payload["force_close_m"]),
            buy_sl=int(payload["buy_sl"]),
            buy_tp=int(payload["buy_tp"]),
            buy_be_act=int(payload["buy_be_act"]),
            buy_be_lock=int(payload["buy_be_lock"]),
            sell_sl=int(payload["sell_sl"]),
            sell_tp=int(payload["sell_tp"]),
            sell_be_act=int(payload["sell_be_act"]),
            sell_be_lock=int(payload["sell_be_lock"]),
        )

    def as_engine_params(self) -> dict:
        """Plain dict matching the keys TradeEngine.evaluate(engine_params=)."""
        return {
            "buy_sl": self.buy_sl,
            "buy_tp": self.buy_tp,
            "buy_be_act": self.buy_be_act,
            "buy_be_lock": self.buy_be_lock,
            "sell_sl": self.sell_sl,
            "sell_tp": self.sell_tp,
            "sell_be_act": self.sell_be_act,
            "sell_be_lock": self.sell_be_lock,
        }


@dataclass
class ReplayStats:
    bars_total: int = 0
    bars_processed: int = 0
    bars_skipped_missing: int = 0
    missing_by_field: Counter = None
    warnings_by_reason: Counter = None
    blockers_by_phase_reason: Counter = None
    trades_opened: int = 0
    trades_closed: int = 0
    pnl_paper: float = 0.0
    last_bar_ts_iso: str | None = None
    runtime_profile: ReplayRuntimeProfile | None = None

    def __post_init__(self):
        if self.missing_by_field is None:
            self.missing_by_field = Counter()
        if self.warnings_by_reason is None:
            self.warnings_by_reason = Counter()
        if self.blockers_by_phase_reason is None:
            self.blockers_by_phase_reason = Counter()


# ─── Bar source ─────────────────────────────────────────────────────────────

def load_bars_for_date(date_str: str) -> list[dict]:
    """Read raw bar_history rows for `date_str`, oldest first.

    Backend (sqlite/dual/postgres) is dispatched via `core.bar_history_db`.
    SQLite path comes from BAR_HISTORY_SQLITE_PATH (the `--source` CLI flag
    exports it before calling here).
    """
    return bhdb.select_by_date(date_str)


def load_eg_source_rows(date_str: str) -> list[dict]:
    """Read all bar_history rows up to `date_str` for EG recomputation.

    Replay processes only the requested date, but EG windows can be larger
    than one session. Prior rows are therefore warmup data, not emitted bars.
    """
    return bhdb.select_eg_warmup(date_str)


def _missing_required_fields(row: dict) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_BAR_FIELDS:
        # `field in row` is true even when value is None — sqlite returns the column.
        if field not in row or row.get(field) is None:
            missing.append(field)
    return missing


def resolve_replay_profile(
    *,
    config_path: str | None = None,
    overrides: dict | None = None,
    runtime_profile: dict | ReplayRuntimeProfile | None = None,
    simulation_overrides: dict | None = None,
) -> ReplayRuntimeProfile:
    """Load runtime_config['replay'] and apply CLI/test overrides.

    `simulation_overrides` patches the nested ``simulation`` sub-block; only
    keys with non-None values are applied so partial CLI flags don't clobber
    the on-disk profile.
    """
    if isinstance(runtime_profile, ReplayRuntimeProfile):
        return runtime_profile

    if runtime_profile is None:
        full_config = runtime_config.load_runtime_config(config_path)
    else:
        full_config = {
            name: dict(values)
            for name, values in runtime_config.DEFAULTS.items()
        }
        full_config["replay"] = dict(runtime_profile)

    replay = dict(full_config["replay"])
    for key, value in (overrides or {}).items():
        if value is not None:
            replay[key] = value

    if simulation_overrides:
        sim_block = dict(replay.get("simulation") or {})
        for key, value in simulation_overrides.items():
            if value is not None:
                sim_block[key] = value
        replay["simulation"] = sim_block

    full_config["replay"] = replay
    normalised = runtime_config.validate_runtime_config(full_config)
    return ReplayRuntimeProfile.from_mapping(normalised["replay"])


class ReplayEgComputer:
    """Recompute Engle-Granger pvalues from bar_history prices."""

    def __init__(self, rows: list[dict], profile: ReplayRuntimeProfile):
        self.profile = profile
        self._daily_cache: dict[str, float | None] = {}
        self._valid_rows: list[dict] = []
        for row in rows:
            try:
                self._valid_rows.append(
                    {
                        "timestamp": int(row["timestamp"]),
                        "date_str": row["date_str"],
                        "win_price": float(row["win_price"]),
                        "wdo_price": float(row["wdo_price"]),
                    }
                )
            except (TypeError, ValueError, KeyError):
                continue

    def pvalue_for(self, row: dict) -> float | None:
        ts = int(row["timestamp"])
        date_str = str(row.get("date_str") or "")
        if self.profile.eg_recalc == "daily" and date_str in self._daily_cache:
            return self._daily_cache[date_str]

        window = [
            item for item in self._valid_rows
            if item["timestamp"] <= ts
        ][-self.profile.eg_bars:]
        if len(window) < 60:
            pvalue = None
        else:
            win = [item["win_price"] for item in window]
            wdo = [item["wdo_price"] for item in window]
            pvalue = compute_engle_granger_pvalue(win, wdo, ts)

        if self.profile.eg_recalc == "daily" and pvalue is not None:
            self._daily_cache[date_str] = pvalue
        return pvalue


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


def _emit_replay_warning_event(
    *,
    db_path: str,
    closed_bar_ts: int,
    event: str,
    bar_time: str,
    row_ts_iso: str,
    message: str,
    payload_json: dict,
) -> None:
    record_event(
        db_path,
        timestamp=row_ts_iso,
        closed_bar_ts=closed_bar_ts,
        correlation_id=f"replay:bar:{closed_bar_ts}",
        dedupe_key=f"replay:bar:{closed_bar_ts}:DATA:{event}",
        phase="DATA",
        event=event,
        status="WARN",
        severity="warning",
        message=message,
        payload_json={"bar_time": bar_time, **payload_json},
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


WIN_BETA_UNSTABLE_PCT = 15.0  # mirrors server.py `_win_beta_state` threshold


def _process_bar(
    row: dict,
    *,
    engine: TradeEngine,
    replay_db: str,
    stats: ReplayStats,
    runtime_profile: ReplayRuntimeProfile | None = None,
    eg_computer: ReplayEgComputer | None = None,
    beta_state: dict | None = None,
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
    if eg_computer is not None:
        eg_pvalue = eg_computer.pvalue_for(row)
    elif row.get("eg_pvalue") is None:
        eg_pvalue = None
    else:
        eg_pvalue = float(row["eg_pvalue"])
    nwe_upper = float(row.get("nwe_upper") or 0.0)
    nwe_lower = float(row.get("nwe_lower") or 0.0)
    nwe_is_up = bool(row.get("nwe_is_up") or 0)

    raw_win_high = row.get("win_high")
    raw_win_low = row.get("win_low")
    win_high = float(raw_win_high) if raw_win_high is not None else None
    win_low = float(raw_win_low) if raw_win_low is not None else None

    if runtime_profile is None:
        runtime_profile = ReplayRuntimeProfile.from_mapping(
            runtime_config.DEFAULTS["replay"]
        )
    sim = runtime_profile.simulation
    if (
        sim.get("enabled")
        and sim.get("intra_bar_sl_tp", True)
        and (win_high is None or win_low is None)
    ):
        missing_ohlc = [
            name for name, value in (("win_high", win_high), ("win_low", win_low))
            if value is None
        ]
        stats.warnings_by_reason[("DATA", "INTRA_BAR_DEGRADED")] += 1
        _emit_replay_warning_event(
            db_path=replay_db,
            closed_bar_ts=closed_bar_ts,
            event="INTRA_BAR_DEGRADED",
            bar_time=bar_time,
            row_ts_iso=row_ts_iso,
            message=(
                "Simulation intra-bar requested but WIN high/low is incomplete; "
                "bar processed with close-only exit checks"
            ),
            payload_json={
                "missing_fields": missing_ohlc,
                "fallback": "close_only",
                "simulation_enabled": True,
                "intra_bar_sl_tp": True,
            },
        )

    today_str = now_dt.strftime("%Y-%m-%d")
    trades_today_count = engine.count_trades_today(today_str)
    daily_pnl_brl = engine.pnl_today(today_str)
    minutes_since_last_loss = engine.minutes_since_last_loss(now=now_dt)

    # Bar-over-bar Kalman beta state machine — parity with live server.py
    # `_win_beta_state`. First bar has no predecessor → unstable=False.
    if beta_state is None:
        beta_state = {"previous_beta": None, "unstable": False}
    prev_beta = beta_state.get("previous_beta")
    if prev_beta is not None and prev_beta != 0:
        beta_change_pct = (beta_value - prev_beta) / abs(prev_beta) * 100
        beta_state["unstable"] = abs(beta_change_pct) > WIN_BETA_UNSTABLE_PCT
    else:
        beta_state["unstable"] = False
    beta_state["previous_beta"] = beta_value

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
        eg_threshold=runtime_profile.eg_threshold,
        rho_breakdown_level=runtime_profile.rho_breakdown_level,
        beta_delta_max=runtime_profile.beta_delta_max,
        z_anomaly=runtime_profile.z_anomaly,
        beta_unstable=bool(beta_state["unstable"]),
        entry_start_h=runtime_profile.entry_start_h,
        entry_start_m=runtime_profile.entry_start_m,
        entry_end_h=runtime_profile.entry_end_h,
        entry_end_m=runtime_profile.entry_end_m,
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
        eg_strategies=list(runtime_profile.eg_strategies),
        simulation_profile=runtime_profile.simulation,
        win_high=win_high,
        win_low=win_low,
        force_close_h=runtime_profile.force_close_h,
        force_close_m=runtime_profile.force_close_m,
        engine_params=runtime_profile.as_engine_params(),
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
        eg_threshold=runtime_profile.eg_threshold,
        rho_breakdown_level=runtime_profile.rho_breakdown_level,
        beta_delta_max=runtime_profile.beta_delta_max,
        z_anomaly=runtime_profile.z_anomaly,
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
        "warnings_by_reason": {
            f"{phase}:{reason}": count
            for (phase, reason), count in stats.warnings_by_reason.items()
        },
        "blockers_by_phase_reason": {
            f"{phase}:{reason}": count
            for (phase, reason), count in stats.blockers_by_phase_reason.items()
        },
        "trades_opened": stats.trades_opened,
        "trades_closed": stats.trades_closed,
        "pnl_paper_brl": round(pnl_paper, 2),
        "last_bar_timestamp": stats.last_bar_ts_iso,
        "runtime_profile": (
            stats.runtime_profile.__dict__ if stats.runtime_profile else None
        ),
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
    if summary["warnings_by_reason"]:
        print("  warnings_by_reason:")
        for key, count in sorted(summary["warnings_by_reason"].items()):
            print(f"    {key:32s} {count}")
    if summary["blockers_by_phase_reason"]:
        print("  blockers_by_phase_reason:")
        for key, count in sorted(summary["blockers_by_phase_reason"].items()):
            print(f"    {key:32s} {count}")
    print(f"  trades_opened:        {summary['trades_opened']}")
    print(f"  trades_closed:        {summary['trades_closed']}")
    print(f"  pnl_paper_brl:        {summary['pnl_paper_brl']}")
    if summary.get("runtime_profile"):
        prof = summary["runtime_profile"]
        eg_strats = prof.get("eg_strategies") or []
        print(
            "  replay_profile:       "
            f"EG<{prof['eg_threshold']} bars={prof['eg_bars']} "
            f"recalc={prof['eg_recalc']} rho<L{prof['rho_breakdown_level']} "
            f"beta<{prof['beta_delta_max']}% "
            f"eg_for=[{','.join(eg_strats) or 'none'}]"
        )
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
    out_dir: str,
    source_db: str | None = None,
    config_path: str | None = None,
    runtime_profile: dict | ReplayRuntimeProfile | None = None,
    overrides: dict | None = None,
    simulation_overrides: dict | None = None,
) -> dict:
    """Run the replay. Returns the summary dict (also emitted as META event).

    Bar source is dispatched via `core.bar_history_db` and BAR_HISTORY_BACKEND.
    `source_db` is preserved as a legacy parameter: when provided it exports
    BAR_HISTORY_SQLITE_PATH so the SQLite backend reads from the requested file
    instead of the default `trades.db`. Ignored under postgres/dual.
    """
    if source_db:
        os.environ["BAR_HISTORY_SQLITE_PATH"] = source_db
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

    profile = resolve_replay_profile(
        config_path=config_path,
        runtime_profile=runtime_profile,
        overrides=overrides,
        simulation_overrides=simulation_overrides,
    )
    reset_eg_cache()

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    replay_db = os.path.join(out_dir, f"execution_timeline_{date_str}.db")
    _reset_replay_db(replay_db)

    init_timeline_table(replay_db)
    engine = TradeEngine(db_path=replay_db)

    rows = load_bars_for_date(date_str)
    eg_rows = load_eg_source_rows(date_str)
    eg_computer = ReplayEgComputer(eg_rows, profile)
    stats = ReplayStats(bars_total=len(rows), runtime_profile=profile)

    beta_state = {"previous_beta": None, "unstable": False}
    for row in rows:
        _process_bar(
            row,
            engine=engine,
            replay_db=replay_db,
            stats=stats,
            runtime_profile=profile,
            eg_computer=eg_computer,
            beta_state=beta_state,
        )

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
    parser.add_argument(
        "--config",
        default=None,
        help="Runtime config JSON path (default: config/runtime.json).",
    )
    parser.add_argument(
        "--eg-threshold",
        type=float,
        default=None,
        help="Override replay eg_threshold.",
    )
    parser.add_argument(
        "--eg-bars",
        type=int,
        default=None,
        help="Override replay eg_bars.",
    )
    parser.add_argument(
        "--eg-recalc",
        choices=runtime_config.EG_RECALC_VALUES,
        default=None,
        help="Override replay eg_recalc.",
    )
    parser.add_argument(
        "--rho-breakdown-level",
        type=int,
        default=None,
        help="Override replay rho_breakdown_level.",
    )
    parser.add_argument(
        "--beta-delta-max",
        type=float,
        default=None,
        help="Override replay beta_delta_max.",
    )
    parser.add_argument(
        "--eg-strategies",
        default=None,
        help=(
            "Comma-separated list of strategies that check EG (subset of "
            f"{list(runtime_config.VALID_STRATEGIES)}). Use 'none' to bypass "
            "EG for all strategies."
        ),
    )
    parser.add_argument(
        "--sim-enabled",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override replay simulation.enabled (toggle MT5 fidelity sim).",
    )
    parser.add_argument(
        "--sim-entry-slip",
        type=float,
        default=None,
        help="Override replay simulation.entry_slippage_pts.",
    )
    parser.add_argument(
        "--sim-exit-slip",
        type=float,
        default=None,
        help="Override replay simulation.exit_slippage_pts.",
    )
    parser.add_argument(
        "--sim-cost-rt",
        type=float,
        default=None,
        help="Override replay simulation.cost_per_contract_rt_brl.",
    )
    parser.add_argument(
        "--sim-intra-bar",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override replay simulation.intra_bar_sl_tp.",
    )
    parser.add_argument(
        "--sim-exit-at-level",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override replay simulation.exit_at_sl_tp_level.",
    )
    parser.add_argument(
        "--sim-conflict-rule",
        choices=runtime_config.CONFLICT_RULES,
        default=None,
        help="Override replay simulation.conflict_rule.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"[ERRO] --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 2

    # `--source` is the SQLite file. Validate (and forward to the wrapper) only
    # when the effective backend actually reads SQLite. In postgres mode the
    # path is unused — guarding it would block PG-only environments / runs
    # outside the repo root where trades.db doesn't exist.
    backend = bhdb.get_backend()
    source_db = args.source if backend in ("sqlite", "dual") else None
    if source_db is not None and not os.path.exists(source_db):
        print(f"[ERRO] source DB not found: {source_db}", file=sys.stderr)
        return 2

    eg_strategies_override: list[str] | None = None
    if args.eg_strategies is not None:
        raw = args.eg_strategies.strip()
        if raw.lower() == "none" or raw == "":
            eg_strategies_override = []
        else:
            eg_strategies_override = [s.strip() for s in raw.split(",") if s.strip()]

    overrides = {
        "eg_threshold": args.eg_threshold,
        "eg_bars": args.eg_bars,
        "eg_recalc": args.eg_recalc,
        "rho_breakdown_level": args.rho_breakdown_level,
        "beta_delta_max": args.beta_delta_max,
        "eg_strategies": eg_strategies_override,
    }
    simulation_overrides = {
        "enabled": args.sim_enabled,
        "entry_slippage_pts": args.sim_entry_slip,
        "exit_slippage_pts": args.sim_exit_slip,
        "cost_per_contract_rt_brl": args.sim_cost_rt,
        "intra_bar_sl_tp": args.sim_intra_bar,
        "exit_at_sl_tp_level": args.sim_exit_at_level,
        "conflict_rule": args.sim_conflict_rule,
    }
    try:
        summary = run_replay(
            date_str=args.date,
            source_db=source_db,
            out_dir=args.out,
            config_path=args.config,
            overrides=overrides,
            simulation_overrides=simulation_overrides,
        )
    except ValueError as exc:
        print(f"[ERRO] invalid runtime config: {exc}", file=sys.stderr)
        return 2
    print(f"\nWrote replay DB: {os.path.join(args.out, f'execution_timeline_{args.date}.db')}")
    print(f"Summary JSON: {json.dumps(summary, default=str)[:200]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
