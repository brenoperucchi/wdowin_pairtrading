"""Closed-bar Execution Timeline emission helpers.

Lives outside `server.py` so the live FastAPI loop AND the offline replay
script (`scripts/replay_execution_timeline.py`) can share one emission
implementation. Phase routing (RISK vs ELIGIBILITY), severity tagging,
and per-reason metric/threshold/operator metadata are decisions the UI
relies on — duplicating them between live and replay would drift.

This module is deliberately MT5-free so it imports cleanly on Linux/CI.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.config import (
    BETA_DELTA_MAX,
    DAILY_LOSS_LIMIT_BRL,
    LIVE_ORDERS,
    LOSS_COOLDOWN_MIN,
    MAX_TRADES_PER_DAY,
    Z_ANOMALY,
)
from core.execution_timeline import bulk_record_events
from core.risk_gate import EG_PVALUE_THRESHOLD, WITHIN_POLL_OP_REASONS
from core.trade_engine import STRATEGIES


TIMELINE_RISK_REASONS = set(WITHIN_POLL_OP_REASONS) | {"MT5_DISCONNECTED"}
TIMELINE_TRANSIENT_REASONS = {"OUT_OF_SESSION"}


def timeline_ts(now_dt: datetime | None = None) -> str:
    return (now_dt or datetime.now()).isoformat(timespec="seconds")


def timeline_minute_key(now_dt: datetime | None = None) -> str:
    return (now_dt or datetime.now()).strftime("%Y%m%d%H%M")


def severity_for_reason(reason: str) -> str:
    if reason in TIMELINE_RISK_REASONS:
        return "operational_block"
    if reason in TIMELINE_TRANSIENT_REASONS:
        return "transient_block"
    return "structural_block"


def reason_fields(
    reason: str,
    *,
    z_wdo: float,
    z_di: float,
    rho_level: int,
    beta_delta_pct: float,
    eg_pvalue: float | None,
    trades_today_count: int,
    daily_pnl_brl: float,
    minutes_since_last_loss: float | None,
) -> dict:
    """Attach metric/threshold/operator context for known gate reasons."""
    if reason in {"EG_NOT_COINTEGRATED", "EG_UNAVAILABLE"}:
        return {
            "metric": "eg_pvalue",
            "value": eg_pvalue,
            "threshold": EG_PVALUE_THRESHOLD,
            "operator": "<",
        }
    if reason == "RHO_BREAKDOWN":
        return {"metric": "rho_level", "value": rho_level, "threshold": 2, "operator": "<"}
    if reason == "BETA_DRIFT":
        return {
            "metric": "abs_beta_delta_pct",
            "value": abs(beta_delta_pct),
            "threshold": BETA_DELTA_MAX,
            "operator": "<",
        }
    if reason == "Z_ANOMALY":
        return {
            "metric": "max_abs_z",
            "value": max(abs(z_wdo), abs(z_di)),
            "threshold": Z_ANOMALY,
            "operator": "<",
        }
    if reason == "MAX_TRADES_REACHED":
        return {
            "metric": "trades_today_count",
            "value": trades_today_count,
            "threshold": MAX_TRADES_PER_DAY,
            "operator": "<",
        }
    if reason == "DAILY_LOSS_LIMIT":
        return {
            "metric": "daily_pnl_brl",
            "value": daily_pnl_brl,
            "threshold": -DAILY_LOSS_LIMIT_BRL,
            "operator": ">",
        }
    if reason == "LOSS_COOLDOWN":
        return {
            "metric": "minutes_since_last_loss",
            "value": minutes_since_last_loss,
            "threshold": LOSS_COOLDOWN_MIN,
            "operator": ">=",
        }
    return {}


def emit_closed_bar_timeline(
    *,
    db_path: str,
    closed_bar_ts: int | None,
    gate: dict,
    trade_result: dict,
    z_wdo: float,
    z_di: float,
    rho: float,
    rho_level: int,
    beta_delta_pct: float,
    eg_pvalue: float | None,
    joh_open: bool | None,
    mt5_connected: bool,
    trades_today_count: int,
    daily_pnl_brl: float,
    minutes_since_last_loss: float | None,
    now_dt: datetime,
) -> int:
    """Emit the full closed-bar funnel for INDICATORS / ELIGIBILITY / RISK / SIGNAL.

    Returns the number of rows actually inserted (dedupe collisions count as 0).
    SIGNAL events for entries / ORDER / EXECUTION / EXIT are emitted by
    `TradeEngine` itself when `evaluate(...)` runs — this function only owns
    the bar-level summary frame.
    """
    if closed_bar_ts is None:
        return 0

    ts = timeline_ts(now_dt)
    base_global = f"bar:{closed_bar_ts}:GLOBAL"
    events: list[dict] = [
        {
            "timestamp": ts,
            "closed_bar_ts": closed_bar_ts,
            "correlation_id": base_global,
            "dedupe_key": f"{base_global}:INDICATORS:INDICATORS_OK",
            "phase": "INDICATORS",
            "event": "INDICATORS_OK",
            "status": "OK",
            "severity": "info",
            "payload_json": {
                "closed_bar_ts": closed_bar_ts,
                "z_wdo": z_wdo,
                "z_di": z_di,
                "rho": rho,
                "rho_level": rho_level,
                "beta_delta_pct": beta_delta_pct,
                "eg_pvalue": eg_pvalue,
                "joh_open": joh_open,
                "live_orders_enabled": bool(LIVE_ORDERS),
                "mt5_connected": mt5_connected,
            },
        }
    ]

    gate_reasons = [r for r in gate.get("reasons", []) if r != "BAR_NOT_CLOSED"]
    for reason in gate_reasons:
        phase = "RISK" if reason in TIMELINE_RISK_REASONS else "ELIGIBILITY"
        event: dict[str, Any] = {
            "timestamp": ts,
            "closed_bar_ts": closed_bar_ts,
            "correlation_id": base_global,
            "dedupe_key": f"{base_global}:{phase}:{reason}",
            "phase": phase,
            "event": reason,
            "status": "BLOCKED",
            "severity": severity_for_reason(reason),
            "message": f"{phase} blocked by {reason}",
        }
        event.update(
            reason_fields(
                reason,
                z_wdo=z_wdo,
                z_di=z_di,
                rho_level=rho_level,
                beta_delta_pct=beta_delta_pct,
                eg_pvalue=eg_pvalue,
                trades_today_count=trades_today_count,
                daily_pnl_brl=daily_pnl_brl,
                minutes_since_last_loss=minutes_since_last_loss,
            )
        )
        events.append(event)

    strategies = trade_result.get("strategies") or {}
    for strategy in STRATEGIES:
        strat_result = strategies.get(strategy) or {}
        action = strat_result.get("action", "WAIT")
        if gate_reasons:
            signal_event = "SKIPPED"
            status = "SKIPPED"
            message = "Gate blocked before strategy evaluation"
        elif action == "WAIT":
            signal_event = "WAIT"
            status = "INFO"
            message = "No entry signal on closed bar"
        else:
            continue

        correlation_id = f"bar:{closed_bar_ts}:{strategy}"
        events.append({
            "timestamp": ts,
            "closed_bar_ts": closed_bar_ts,
            "correlation_id": correlation_id,
            "dedupe_key": f"{correlation_id}:SIGNAL:{signal_event}",
            "phase": "SIGNAL",
            "event": signal_event,
            "status": status,
            "severity": "info",
            "strategy": strategy,
            "message": message,
            "payload_json": {
                "action": action,
                "gate_reasons": gate_reasons,
            },
        })

    rowids = bulk_record_events(db_path, events)
    return sum(1 for rowid in rowids if rowid is not None)
