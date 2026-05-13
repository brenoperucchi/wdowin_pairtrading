"""Centralized live-trade risk gate.

All hard pre-entry checks live here. `evaluate()` consumes the result instead
of separate boolean flags. Reasons are populated when allowed=False so the
UI/log can explain WHY an entry was blocked.

Decisions baked in (see TASK-3 AC #3/#4 for context):
- Engle-Granger pvalue >= 0.10 → BLOCK (cointegration broken).
- Johansen → INFORMATIONAL ONLY (surfaced in payload, never blocks).
- HMM regime → INFORMATIONAL ONLY (stored on trade row for postmortem).
- Sizing is NOT decided here — that stays in `core/signals.get_signal()`.
"""
import threading
from typing import Optional

import numpy as np
from statsmodels.tsa.stattools import coint

from core.config import (
    Z_ANOMALY,
    ENTRY_START_H,
    ENTRY_START_M,
    ENTRY_END_H,
    ENTRY_END_M,
    MAX_TRADES_PER_DAY,
    DAILY_LOSS_LIMIT_BRL,
    LOSS_COOLDOWN_MIN,
    BLOCK_ON_MT5_DISCONNECT,
    BETA_DELTA_MAX,
)


# ─── Constants ──────────────────────────────────────────────────────────────

EG_PVALUE_THRESHOLD = 0.10  # block when pvalue >= this
EG_MIN_BARS = 60  # minimum bars for a meaningful coint test
RHO_BREAKDOWN_LEVEL = 2  # block when rho_status['level'] >= this

# Reasons emitted by risk_gate that come from the cointegration check.
# `TradeEngine.evaluate()` uses this set to filter EG out for strategies
# configured to bypass it (e.g. DI_NWE in Miqueias's design).
EG_REASONS = frozenset({"EG_NOT_COINTEGRATED", "EG_UNAVAILABLE"})


# ─── Engle-Granger pvalue cache (keyed by last_bar_ts) ──────────────────────
# FastAPI runs sync endpoints in a threadpool (not the event loop), so
# concurrent polls can race on this dict. A Lock makes the cache safe.

_eg_cache: dict = {"bar_ts": None, "pvalue": None}
_eg_lock = threading.Lock()


def compute_engle_granger_pvalue(
    win_closes, wdo_closes, bar_ts: int
) -> Optional[float]:
    """Cointegration pvalue with bar-close caching.

    Cache key is `bar_ts` (the timestamp of the most recent bar). The same M5
    bar can fire many V2 polls; we recompute only when a new bar arrives.

    Returns None if there's not enough history or statsmodels raises — the
    caller treats None as "EG unavailable" and blocks the entry.
    """
    global _eg_cache
    with _eg_lock:
        if _eg_cache["bar_ts"] == bar_ts:
            return _eg_cache["pvalue"]

    if win_closes is None or wdo_closes is None:
        with _eg_lock:
            _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
        return None
    if len(win_closes) < EG_MIN_BARS or len(wdo_closes) < EG_MIN_BARS:
        with _eg_lock:
            _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
        return None

    try:
        _, pvalue, _ = coint(np.asarray(win_closes), np.asarray(wdo_closes))
        if not np.isfinite(pvalue):
            with _eg_lock:
                _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
            return None
        result = float(pvalue)
        with _eg_lock:
            _eg_cache = {"bar_ts": bar_ts, "pvalue": result}
        return result
    except Exception:
        with _eg_lock:
            _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
        return None


def reset_eg_cache() -> None:
    """Test helper — drop the cached pvalue so the next call recomputes."""
    global _eg_cache
    with _eg_lock:
        _eg_cache = {"bar_ts": None, "pvalue": None}


# ─── Session helper ─────────────────────────────────────────────────────────

def _in_session(
    hour: int,
    minute: int,
    *,
    entry_start_h: int | None = None,
    entry_start_m: int | None = None,
    entry_end_h: int | None = None,
    entry_end_m: int | None = None,
) -> bool:
    """Window inclusive on both ends. ``None`` kwargs fall back to
    ``core.config`` constants (backward compat for callers that haven't
    migrated to the runtime profile yet).
    """
    sh = ENTRY_START_H if entry_start_h is None else entry_start_h
    sm = ENTRY_START_M if entry_start_m is None else entry_start_m
    eh = ENTRY_END_H if entry_end_h is None else entry_end_h
    em = ENTRY_END_M if entry_end_m is None else entry_end_m
    t = hour * 60 + minute
    start = sh * 60 + sm
    end = eh * 60 + em
    return start <= t <= end


# ─── Operational checks (TASK-3 AC #11) ─────────────────────────────────────
# Extracted as its own helper so both `risk_gate()` (called once per poll
# from server.py with poll-start stats) AND `TradeEngine.evaluate()` (called
# per-strategy entry attempt with this-poll-fresh stats) share one impl.
# Avoids drift if defaults or thresholds move.

# Reasons that the engine MUST recompute mid-poll because exits in slot A can
# change them before slot B's entry attempt. MT5 connection doesn't change
# within a poll, so it stays in the market-side gate built by server.py.
WITHIN_POLL_OP_REASONS = frozenset(
    {"MAX_TRADES_REACHED", "DAILY_LOSS_LIMIT", "LOSS_COOLDOWN"}
)


def operational_checks(
    *,
    trades_today_count: int,
    daily_pnl_brl: float,
    minutes_since_last_loss: Optional[float],
    mt5_connected: bool,
) -> tuple[list[str], dict[str, bool]]:
    """Return (reasons, checks) for the four operational gates.

    Returned reasons subset:
      MAX_TRADES_REACHED, DAILY_LOSS_LIMIT, LOSS_COOLDOWN, MT5_DISCONNECTED.
    """
    reasons: list[str] = []
    checks: dict[str, bool] = {}

    checks["max_trades"] = trades_today_count < MAX_TRADES_PER_DAY
    if not checks["max_trades"]:
        reasons.append("MAX_TRADES_REACHED")

    # daily_pnl_brl is signed: negative = loss. Block when cumulative loss
    # crosses the limit (i.e., pnl <= -LIMIT). A profitable day is unbounded.
    checks["daily_loss"] = daily_pnl_brl > -DAILY_LOSS_LIMIT_BRL
    if not checks["daily_loss"]:
        reasons.append("DAILY_LOSS_LIMIT")

    checks["loss_cooldown"] = (
        minutes_since_last_loss is None
        or minutes_since_last_loss >= LOSS_COOLDOWN_MIN
    )
    if not checks["loss_cooldown"]:
        reasons.append("LOSS_COOLDOWN")

    if BLOCK_ON_MT5_DISCONNECT:
        checks["mt5_connection"] = bool(mt5_connected)
        if not checks["mt5_connection"]:
            reasons.append("MT5_DISCONNECTED")
    else:
        checks["mt5_connection"] = True

    return reasons, checks


# ─── Main gate ──────────────────────────────────────────────────────────────

def risk_gate(
    *,
    z_wdo: float,
    z_di: float,
    rho_level: int,
    beta_delta_pct: float,
    eg_pvalue: Optional[float],
    hour: int,
    minute: int,
    bar_close_confirmed: bool,
    trades_today_count: int = 0,
    daily_pnl_brl: float = 0.0,
    minutes_since_last_loss: Optional[float] = None,
    mt5_connected: bool = True,
    joh_open: Optional[bool] = None,
    hmm_state: Optional[str] = None,
    eg_threshold: Optional[float] = None,
    rho_breakdown_level: Optional[int] = None,
    beta_delta_max: Optional[float] = None,
    z_anomaly: Optional[float] = None,
    beta_unstable: bool = False,
    entry_start_h: Optional[int] = None,
    entry_start_m: Optional[int] = None,
    entry_end_h: Optional[int] = None,
    entry_end_m: Optional[int] = None,
) -> dict:
    """Run all hard gates and return a structured decision.

    Returns:
        {
          "allowed": bool,
          "reasons": list[str],   # empty when allowed=True
          "checks": dict[str, bool],
          "informational": {"joh_open": ..., "hmm_state": ..., "eg_pvalue": ...},
        }

    Blocking gates (any False → not allowed):
      - bar_close: entries fire only on confirmed bar close
      - session:   inside ENTRY_START..ENTRY_END
      - rho:       rho_status level < rho_breakdown_level (correlation healthy)
      - beta:      |beta_delta_pct| < beta_delta_max
      - beta_state: not beta_unstable (bar-over-bar Kalman drift state machine)
      - z_anomaly: max(|z_wdo|, |z_di|) < Z_ANOMALY
      - engle_granger: eg_pvalue is finite AND < eg_threshold
      - max_trades: trades_today_count < MAX_TRADES_PER_DAY
      - daily_loss: daily_pnl_brl > -DAILY_LOSS_LIMIT_BRL
      - loss_cooldown: minutes_since_last_loss is None OR >= LOSS_COOLDOWN_MIN
      - mt5_connection: mt5_connected (skipped if BLOCK_ON_MT5_DISCONNECT=False)

    Reasons emitted:
      BAR_NOT_CLOSED, OUT_OF_SESSION, RHO_BREAKDOWN, BETA_DRIFT, BETA_UNSTABLE,
      Z_ANOMALY, EG_UNAVAILABLE, EG_NOT_COINTEGRATED,
      MAX_TRADES_REACHED, DAILY_LOSS_LIMIT, LOSS_COOLDOWN, MT5_DISCONNECTED.
    """
    eg_threshold = EG_PVALUE_THRESHOLD if eg_threshold is None else eg_threshold
    rho_breakdown_level = (
        RHO_BREAKDOWN_LEVEL if rho_breakdown_level is None else rho_breakdown_level
    )
    beta_delta_max = BETA_DELTA_MAX if beta_delta_max is None else beta_delta_max
    z_anomaly_threshold = Z_ANOMALY if z_anomaly is None else z_anomaly

    reasons: list[str] = []
    checks: dict[str, bool] = {}

    checks["bar_close"] = bool(bar_close_confirmed)
    if not checks["bar_close"]:
        reasons.append("BAR_NOT_CLOSED")

    checks["session"] = _in_session(
        hour,
        minute,
        entry_start_h=entry_start_h,
        entry_start_m=entry_start_m,
        entry_end_h=entry_end_h,
        entry_end_m=entry_end_m,
    )
    if not checks["session"]:
        reasons.append("OUT_OF_SESSION")

    checks["rho"] = rho_level < rho_breakdown_level
    if not checks["rho"]:
        reasons.append("RHO_BREAKDOWN")

    checks["beta"] = abs(beta_delta_pct) < beta_delta_max
    if not checks["beta"]:
        reasons.append("BETA_DRIFT")

    checks["beta_state"] = not bool(beta_unstable)
    if not checks["beta_state"]:
        reasons.append("BETA_UNSTABLE")

    checks["z_anomaly"] = abs(z_wdo) < z_anomaly_threshold and abs(z_di) < z_anomaly_threshold
    if not checks["z_anomaly"]:
        reasons.append("Z_ANOMALY")

    if eg_pvalue is None:
        checks["engle_granger"] = False
        reasons.append("EG_UNAVAILABLE")
    elif eg_pvalue >= eg_threshold:
        checks["engle_granger"] = False
        reasons.append("EG_NOT_COINTEGRATED")
    else:
        checks["engle_granger"] = True

    # ── Operational gates (TASK-3 AC #11) ──
    ops_reasons, ops_checks = operational_checks(
        trades_today_count=trades_today_count,
        daily_pnl_brl=daily_pnl_brl,
        minutes_since_last_loss=minutes_since_last_loss,
        mt5_connected=mt5_connected,
    )
    reasons.extend(ops_reasons)
    checks.update(ops_checks)

    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
        "checks": checks,
        "informational": {
            "joh_open": joh_open,
            "hmm_state": hmm_state,
            "eg_pvalue": eg_pvalue,
        },
    }
