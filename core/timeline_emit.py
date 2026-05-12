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
    eg_threshold: float = EG_PVALUE_THRESHOLD,
    rho_breakdown_level: int = 2,
    beta_delta_max: float = BETA_DELTA_MAX,
    z_anomaly: float = Z_ANOMALY,
) -> dict:
    """Attach metric/threshold/operator context for known gate reasons."""
    if reason in {"EG_NOT_COINTEGRATED", "EG_UNAVAILABLE"}:
        return {
            "metric": "eg_pvalue",
            "value": eg_pvalue,
            "threshold": eg_threshold,
            "operator": "<",
        }
    if reason == "RHO_BREAKDOWN":
        return {
            "metric": "rho_level",
            "value": rho_level,
            "threshold": rho_breakdown_level,
            "operator": "<",
        }
    if reason == "BETA_DRIFT":
        return {
            "metric": "abs_beta_delta_pct",
            "value": abs(beta_delta_pct),
            "threshold": beta_delta_max,
            "operator": "<",
        }
    if reason == "Z_ANOMALY":
        return {
            "metric": "max_abs_z",
            "value": max(abs(z_wdo), abs(z_di)),
            "threshold": z_anomaly,
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


def _fmt_num(value: float | int | None, digits: int = 4) -> str:
    if value is None:
        return "indisponivel"
    return f"{float(value):.{digits}g}"


def reason_message(reason: str, phase: str, fields: dict) -> str:
    """Human explanation for operator-facing timeline rows."""
    if reason == "EG_NOT_COINTEGRATED":
        return (
            "Bloqueado por Engle-Granger: o p-value "
            f"{_fmt_num(fields.get('value'))} ficou acima do limite "
            f"{_fmt_num(fields.get('threshold'))}. Isso indica que o spread "
            "WINxWDO nao esta com reversao a media estatisticamente confiavel "
            "nesta janela."
        )
    if reason == "EG_UNAVAILABLE":
        return (
            "Bloqueado porque o Engle-Granger nao conseguiu calcular um "
            "p-value valido para a barra fechada. Sem esse teste, o motor nao "
            "confirma a premissa de co-integracao."
        )
    if reason == "RHO_BREAKDOWN":
        return (
            "Bloqueado por correlacao fraca: rho_level "
            f"{_fmt_num(fields.get('value'), 0)} precisa ficar abaixo de "
            f"{_fmt_num(fields.get('threshold'), 0)} para permitir entrada."
        )
    if reason == "BETA_DRIFT":
        return (
            "Bloqueado por drift de beta: variacao absoluta "
            f"{_fmt_num(fields.get('value'))}% excede o maximo "
            f"{_fmt_num(fields.get('threshold'))}% configurado."
        )
    if reason == "BETA_UNSTABLE":
        return "Bloqueado porque o beta esta instavel no state machine operacional."
    if reason == "Z_ANOMALY":
        return (
            "Bloqueado por anomalia de Z-score: |z| maximo "
            f"{_fmt_num(fields.get('value'))} excede o limite "
            f"{_fmt_num(fields.get('threshold'))}. O motor evita entrar em "
            "outlier extremo."
        )
    if reason == "OUT_OF_SESSION":
        return "Bloqueado porque a barra esta fora da janela operacional de entrada."
    if reason == "MAX_TRADES_REACHED":
        return (
            "Bloqueado pelo limite diario de trades: "
            f"{_fmt_num(fields.get('value'), 0)} trade(s) hoje contra limite "
            f"{_fmt_num(fields.get('threshold'), 0)}."
        )
    if reason == "DAILY_LOSS_LIMIT":
        return (
            "Bloqueado pelo limite de perda diaria: PnL "
            f"R$ {_fmt_num(fields.get('value'))} esta abaixo do limite "
            f"R$ {_fmt_num(fields.get('threshold'))}."
        )
    if reason == "LOSS_COOLDOWN":
        return (
            "Bloqueado por cooldown apos perda: passaram "
            f"{_fmt_num(fields.get('value'))} min, precisa de pelo menos "
            f"{_fmt_num(fields.get('threshold'))} min."
        )
    if reason == "MT5_DISCONNECTED":
        return "Bloqueado porque o MT5 nao esta conectado no momento da avaliacao."
    return f"{phase} bloqueado por {reason}."


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
    eg_threshold: float = EG_PVALUE_THRESHOLD,
    rho_breakdown_level: int = 2,
    beta_delta_max: float = BETA_DELTA_MAX,
    z_anomaly: float = Z_ANOMALY,
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
        fields = reason_fields(
            reason,
            z_wdo=z_wdo,
            z_di=z_di,
            rho_level=rho_level,
            beta_delta_pct=beta_delta_pct,
            eg_pvalue=eg_pvalue,
            trades_today_count=trades_today_count,
            daily_pnl_brl=daily_pnl_brl,
            minutes_since_last_loss=minutes_since_last_loss,
            eg_threshold=eg_threshold,
            rho_breakdown_level=rho_breakdown_level,
            beta_delta_max=beta_delta_max,
            z_anomaly=z_anomaly,
        )
        event: dict[str, Any] = {
            "timestamp": ts,
            "closed_bar_ts": closed_bar_ts,
            "correlation_id": base_global,
            "dedupe_key": f"{base_global}:{phase}:{reason}",
            "phase": phase,
            "event": reason,
            "status": "BLOCKED",
            "severity": severity_for_reason(reason),
            "message": reason_message(reason, phase, fields),
        }
        event.update(fields)
        events.append(event)

    strategies = trade_result.get("strategies") or {}
    for strategy in STRATEGIES:
        strat_result = strategies.get(strategy) or {}
        action = strat_result.get("action", "WAIT")
        # Use the per-strategy gate_reasons so EG bypass (eg_strategies in
        # runtime_config) is reflected: a slot that bypassed EG won't show
        # EG_NOT_COINTEGRATED here, even when the global gate did block it.
        strat_gate_reasons = list(strat_result.get("gate_reasons", []))
        if strat_gate_reasons:
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
                "gate_reasons": strat_gate_reasons,
            },
        })

    rowids = bulk_record_events(db_path, events)
    return sum(1 for rowid in rowids if rowid is not None)
