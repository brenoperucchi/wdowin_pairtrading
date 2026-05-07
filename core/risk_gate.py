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
)


# ─── Constants ──────────────────────────────────────────────────────────────

EG_PVALUE_THRESHOLD = 0.10  # block when pvalue >= this
EG_MIN_BARS = 60  # minimum bars for a meaningful coint test
BETA_DRIFT_PCT_LIMIT = 25.0  # block when |beta_delta_pct| >= this
RHO_BREAKDOWN_LEVEL = 2  # block when rho_status['level'] >= this


# ─── Engle-Granger pvalue cache (keyed by last_bar_ts) ──────────────────────

_eg_cache: dict = {"bar_ts": None, "pvalue": None}


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
    if _eg_cache["bar_ts"] == bar_ts:
        return _eg_cache["pvalue"]

    if win_closes is None or wdo_closes is None:
        _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
        return None
    if len(win_closes) < EG_MIN_BARS or len(wdo_closes) < EG_MIN_BARS:
        _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
        return None

    try:
        _, pvalue, _ = coint(np.asarray(win_closes), np.asarray(wdo_closes))
        if not np.isfinite(pvalue):
            _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
            return None
        _eg_cache = {"bar_ts": bar_ts, "pvalue": float(pvalue)}
        return float(pvalue)
    except Exception:
        _eg_cache = {"bar_ts": bar_ts, "pvalue": None}
        return None


def reset_eg_cache() -> None:
    """Test helper — drop the cached pvalue so the next call recomputes."""
    global _eg_cache
    _eg_cache = {"bar_ts": None, "pvalue": None}


# ─── Session helper ─────────────────────────────────────────────────────────

def _in_session(hour: int, minute: int) -> bool:
    t = hour * 60 + minute
    start = ENTRY_START_H * 60 + ENTRY_START_M
    end = ENTRY_END_H * 60 + ENTRY_END_M
    return start <= t <= end


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
      - rho:       rho_status level < 2 (correlation healthy)
      - beta:      |beta_delta_pct| < 25%
      - z_anomaly: max(|z_wdo|, |z_di|) < Z_ANOMALY
      - engle_granger: eg_pvalue is finite AND < 0.10
      - max_trades: trades_today_count < MAX_TRADES_PER_DAY
      - daily_loss: daily_pnl_brl > -DAILY_LOSS_LIMIT_BRL
      - loss_cooldown: minutes_since_last_loss is None OR >= LOSS_COOLDOWN_MIN
      - mt5_connection: mt5_connected (skipped if BLOCK_ON_MT5_DISCONNECT=False)

    Reasons emitted:
      BAR_NOT_CLOSED, OUT_OF_SESSION, RHO_BREAKDOWN, BETA_DRIFT,
      Z_ANOMALY, EG_UNAVAILABLE, EG_NOT_COINTEGRATED,
      MAX_TRADES_REACHED, DAILY_LOSS_LIMIT, LOSS_COOLDOWN, MT5_DISCONNECTED.
    """
    reasons: list[str] = []
    checks: dict[str, bool] = {}

    checks["bar_close"] = bool(bar_close_confirmed)
    if not checks["bar_close"]:
        reasons.append("BAR_NOT_CLOSED")

    checks["session"] = _in_session(hour, minute)
    if not checks["session"]:
        reasons.append("OUT_OF_SESSION")

    checks["rho"] = rho_level < RHO_BREAKDOWN_LEVEL
    if not checks["rho"]:
        reasons.append("RHO_BREAKDOWN")

    checks["beta"] = abs(beta_delta_pct) < BETA_DRIFT_PCT_LIMIT
    if not checks["beta"]:
        reasons.append("BETA_DRIFT")

    checks["z_anomaly"] = abs(z_wdo) < Z_ANOMALY and abs(z_di) < Z_ANOMALY
    if not checks["z_anomaly"]:
        reasons.append("Z_ANOMALY")

    if eg_pvalue is None:
        checks["engle_granger"] = False
        reasons.append("EG_UNAVAILABLE")
    elif eg_pvalue >= EG_PVALUE_THRESHOLD:
        checks["engle_granger"] = False
        reasons.append("EG_NOT_COINTEGRATED")
    else:
        checks["engle_granger"] = True

    # ── Operational gates (TASK-3 AC #11) ──
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
