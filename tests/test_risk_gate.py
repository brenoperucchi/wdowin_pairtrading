"""Tests for core/risk_gate.py — covers TASK-3 AC #3/#4.

Lock down each gate in isolation and a few composite scenarios so the
contract between server.py V2 endpoint and TradeEngine.evaluate() stays
explicit.
"""
import numpy as np
import pytest

from core import risk_gate as rg
from core.risk_gate import (
    EG_PVALUE_THRESHOLD,
    compute_engle_granger_pvalue,
    reset_eg_cache,
    risk_gate,
)


@pytest.fixture(autouse=True)
def _isolate_eg_cache():
    """Reset the module-level EG cache between tests."""
    reset_eg_cache()
    yield
    reset_eg_cache()


# ─── Helpers ────────────────────────────────────────────────────────────────

def _ok_kwargs(**overrides):
    """All-pass inputs — strategy tests use this and override individual fields."""
    base = dict(
        z_wdo=0.5,
        z_di=-0.3,
        rho_level=0,
        beta_delta_pct=5.0,
        eg_pvalue=0.02,
        hour=11,
        minute=0,
        bar_close_confirmed=True,
        joh_open=True,
        hmm_state="CHOP",
    )
    base.update(overrides)
    return base


# ─── Pass-through ───────────────────────────────────────────────────────────

def test_all_gates_pass_yields_allowed():
    out = risk_gate(**_ok_kwargs())
    assert out["allowed"] is True
    assert out["reasons"] == []
    assert all(out["checks"].values())


def test_informational_payload_round_trip():
    out = risk_gate(**_ok_kwargs(joh_open=False, hmm_state="BEAR", eg_pvalue=0.04))
    assert out["informational"] == {
        "joh_open": False,
        "hmm_state": "BEAR",
        "eg_pvalue": 0.04,
    }
    # Johansen=False and HMM=BEAR are informational only — must NOT block
    assert out["allowed"] is True


# ─── Hard gates, isolated ───────────────────────────────────────────────────

def test_bar_not_closed_blocks():
    out = risk_gate(**_ok_kwargs(bar_close_confirmed=False))
    assert out["allowed"] is False
    assert "BAR_NOT_CLOSED" in out["reasons"]
    assert out["checks"]["bar_close"] is False


def test_out_of_session_blocks():
    out = risk_gate(**_ok_kwargs(hour=8, minute=59))
    assert "OUT_OF_SESSION" in out["reasons"]


def test_rho_breakdown_blocks_at_level_2():
    out = risk_gate(**_ok_kwargs(rho_level=2))
    assert "RHO_BREAKDOWN" in out["reasons"]


def test_rho_level_below_2_passes():
    assert risk_gate(**_ok_kwargs(rho_level=1))["checks"]["rho"] is True


def test_beta_drift_at_25pct_blocks():
    out = risk_gate(**_ok_kwargs(beta_delta_pct=25.0))
    assert "BETA_DRIFT" in out["reasons"]


def test_beta_drift_negative_direction_also_blocks():
    """Both positive and negative drift must trip the gate."""
    out = risk_gate(**_ok_kwargs(beta_delta_pct=-30.0))
    assert "BETA_DRIFT" in out["reasons"]


def test_z_anomaly_on_either_leg_blocks():
    out_wdo = risk_gate(**_ok_kwargs(z_wdo=4.5))
    out_di = risk_gate(**_ok_kwargs(z_di=-4.2))
    assert "Z_ANOMALY" in out_wdo["reasons"]
    assert "Z_ANOMALY" in out_di["reasons"]


def test_eg_unavailable_blocks_with_explicit_reason():
    out = risk_gate(**_ok_kwargs(eg_pvalue=None))
    assert out["allowed"] is False
    assert "EG_UNAVAILABLE" in out["reasons"]
    assert "EG_NOT_COINTEGRATED" not in out["reasons"]


def test_eg_above_threshold_blocks():
    out = risk_gate(**_ok_kwargs(eg_pvalue=EG_PVALUE_THRESHOLD))
    assert "EG_NOT_COINTEGRATED" in out["reasons"]


def test_eg_just_below_threshold_passes():
    out = risk_gate(**_ok_kwargs(eg_pvalue=EG_PVALUE_THRESHOLD - 1e-9))
    assert out["checks"]["engle_granger"] is True


# ─── Composite ──────────────────────────────────────────────────────────────

def test_multiple_failures_listed_in_reasons():
    out = risk_gate(**_ok_kwargs(
        bar_close_confirmed=False,
        rho_level=2,
        eg_pvalue=None,
    ))
    assert out["allowed"] is False
    assert set(out["reasons"]) >= {"BAR_NOT_CLOSED", "RHO_BREAKDOWN", "EG_UNAVAILABLE"}


def test_johansen_closed_does_not_block():
    """Slice 2 decision: Johansen is informational only."""
    out = risk_gate(**_ok_kwargs(joh_open=False))
    assert out["allowed"] is True


def test_hmm_bear_does_not_block():
    """Slice 2 decision: HMM is informational only."""
    out = risk_gate(**_ok_kwargs(hmm_state="BEAR"))
    assert out["allowed"] is True


# ─── Engle-Granger pvalue cache ─────────────────────────────────────────────

def test_eg_cache_returns_same_value_for_same_bar_ts(monkeypatch):
    calls = {"n": 0}

    def fake_coint(a, b):
        calls["n"] += 1
        return (None, 0.03, None)

    monkeypatch.setattr(rg, "coint", fake_coint)

    win = np.linspace(130000, 130500, 100)
    wdo = np.linspace(5800, 5850, 100)

    p1 = compute_engle_granger_pvalue(win, wdo, bar_ts=1000)
    p2 = compute_engle_granger_pvalue(win, wdo, bar_ts=1000)
    assert p1 == p2 == 0.03
    assert calls["n"] == 1  # cache hit on second call


def test_eg_cache_recomputes_on_new_bar_ts(monkeypatch):
    calls = {"n": 0}

    def fake_coint(a, b):
        calls["n"] += 1
        return (None, 0.04, None)

    monkeypatch.setattr(rg, "coint", fake_coint)

    win = np.linspace(130000, 130500, 100)
    wdo = np.linspace(5800, 5850, 100)

    compute_engle_granger_pvalue(win, wdo, bar_ts=1000)
    compute_engle_granger_pvalue(win, wdo, bar_ts=2000)
    assert calls["n"] == 2


def test_eg_returns_none_below_min_bars():
    win = np.linspace(130000, 130100, 30)
    wdo = np.linspace(5800, 5810, 30)
    assert compute_engle_granger_pvalue(win, wdo, bar_ts=42) is None


def test_eg_returns_none_when_coint_raises(monkeypatch):
    def boom(a, b):
        raise ValueError("singular matrix")

    monkeypatch.setattr(rg, "coint", boom)
    win = np.linspace(130000, 130500, 100)
    wdo = np.linspace(5800, 5850, 100)
    assert compute_engle_granger_pvalue(win, wdo, bar_ts=99) is None


def test_eg_returns_none_when_coint_yields_nan(monkeypatch):
    monkeypatch.setattr(rg, "coint", lambda a, b: (None, float("nan"), None))
    win = np.linspace(130000, 130500, 100)
    wdo = np.linspace(5800, 5850, 100)
    assert compute_engle_granger_pvalue(win, wdo, bar_ts=99) is None


# ─── Operational risk gates (TASK-3 AC #11) ─────────────────────────────────

from core.config import (
    MAX_TRADES_PER_DAY,
    DAILY_LOSS_LIMIT_BRL,
    LOSS_COOLDOWN_MIN,
)


def test_max_trades_below_limit_passes():
    out = risk_gate(**_ok_kwargs(trades_today_count=MAX_TRADES_PER_DAY - 1))
    assert out["allowed"] is True
    assert out["checks"]["max_trades"] is True


def test_max_trades_at_limit_blocks():
    out = risk_gate(**_ok_kwargs(trades_today_count=MAX_TRADES_PER_DAY))
    assert out["allowed"] is False
    assert "MAX_TRADES_REACHED" in out["reasons"]


def test_max_trades_above_limit_blocks():
    out = risk_gate(**_ok_kwargs(trades_today_count=MAX_TRADES_PER_DAY + 5))
    assert "MAX_TRADES_REACHED" in out["reasons"]


def test_daily_pnl_above_limit_passes():
    out = risk_gate(**_ok_kwargs(daily_pnl_brl=-DAILY_LOSS_LIMIT_BRL + 1.0))
    assert out["allowed"] is True
    assert out["checks"]["daily_loss"] is True


def test_daily_pnl_at_limit_blocks():
    """Loss exactly equal to the limit must trip the gate (>= triggers)."""
    out = risk_gate(**_ok_kwargs(daily_pnl_brl=-DAILY_LOSS_LIMIT_BRL))
    assert "DAILY_LOSS_LIMIT" in out["reasons"]


def test_daily_pnl_above_limit_blocks():
    out = risk_gate(**_ok_kwargs(daily_pnl_brl=-(DAILY_LOSS_LIMIT_BRL + 50)))
    assert "DAILY_LOSS_LIMIT" in out["reasons"]


def test_profitable_day_never_blocks_on_loss_gate():
    """No upper bound on profit — only the loss side can block."""
    out = risk_gate(**_ok_kwargs(daily_pnl_brl=10_000.0))
    assert out["checks"]["daily_loss"] is True


def test_no_prior_loss_means_no_cooldown():
    """minutes_since_last_loss=None → no cooldown applies."""
    out = risk_gate(**_ok_kwargs(minutes_since_last_loss=None))
    assert out["checks"]["loss_cooldown"] is True


def test_loss_cooldown_active_blocks():
    out = risk_gate(**_ok_kwargs(minutes_since_last_loss=LOSS_COOLDOWN_MIN - 1))
    assert out["allowed"] is False
    assert "LOSS_COOLDOWN" in out["reasons"]


def test_loss_cooldown_at_threshold_passes():
    """Exactly at threshold, cooldown has expired."""
    out = risk_gate(**_ok_kwargs(minutes_since_last_loss=LOSS_COOLDOWN_MIN))
    assert out["checks"]["loss_cooldown"] is True


def test_loss_cooldown_long_past_passes():
    out = risk_gate(**_ok_kwargs(minutes_since_last_loss=240.0))
    assert out["checks"]["loss_cooldown"] is True


def test_mt5_disconnected_blocks_when_default_block_true():
    out = risk_gate(**_ok_kwargs(mt5_connected=False))
    assert out["allowed"] is False
    assert "MT5_DISCONNECTED" in out["reasons"]


def test_mt5_disconnected_allowed_when_block_disabled(monkeypatch):
    """If BLOCK_ON_MT5_DISCONNECT is False (offline backtest mode), the gate
    must NOT block on disconnection — the check is skipped entirely."""
    monkeypatch.setattr(rg, "BLOCK_ON_MT5_DISCONNECT", False)
    out = risk_gate(**_ok_kwargs(mt5_connected=False))
    assert "MT5_DISCONNECTED" not in out["reasons"]
    assert out["checks"]["mt5_connection"] is True


def test_operational_failures_compose_with_market_failures():
    out = risk_gate(**_ok_kwargs(
        rho_level=2,
        trades_today_count=MAX_TRADES_PER_DAY,
        daily_pnl_brl=-(DAILY_LOSS_LIMIT_BRL + 1),
        minutes_since_last_loss=5.0,
    ))
    assert out["allowed"] is False
    assert set(out["reasons"]) >= {
        "RHO_BREAKDOWN",
        "MAX_TRADES_REACHED",
        "DAILY_LOSS_LIMIT",
        "LOSS_COOLDOWN",
    }
