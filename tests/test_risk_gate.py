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


def test_beta_drift_blocks_at_runtime_config_15_default():
    """With the upstream-aligned 15.0 default from runtime_config, 20% drift blocks.

    Pre-TASK-13.1 this case (beta_delta_pct=20, beta_delta_max=15) was being passed
    25.0 from DEFAULTS.live and silently allowed.
    """
    out = risk_gate(**_ok_kwargs(beta_delta_pct=20.0, beta_delta_max=15.0))
    assert "BETA_DRIFT" in out["reasons"]

    # Sanity: same drift at the old 25.0 threshold did not block.
    out_old = risk_gate(**_ok_kwargs(beta_delta_pct=20.0, beta_delta_max=25.0))
    assert "BETA_DRIFT" not in out_old["reasons"]


def test_beta_drift_negative_direction_also_blocks():
    """Both positive and negative drift must trip the gate."""
    out = risk_gate(**_ok_kwargs(beta_delta_pct=-30.0))
    assert "BETA_DRIFT" in out["reasons"]


def test_beta_drift_threshold_follows_config_BETA_DELTA_MAX(monkeypatch):
    """Gate must use core.config.BETA_DELTA_MAX, not a local copy.

    Monkeypatching the module attribute proves the live check reads from
    config rather than a hardcoded constant that would drift silently.
    """
    import core.risk_gate as rg
    monkeypatch.setattr(rg, "BETA_DELTA_MAX", 30.0)
    # 25% drift: below the patched threshold → must NOT block
    no_block = risk_gate(**_ok_kwargs(beta_delta_pct=25.0))
    assert "BETA_DRIFT" not in no_block["reasons"]
    # 31% drift: above the patched threshold → must block
    blocked = risk_gate(**_ok_kwargs(beta_delta_pct=31.0))
    assert "BETA_DRIFT" in blocked["reasons"]


def test_z_anomaly_on_either_leg_blocks():
    out_wdo = risk_gate(**_ok_kwargs(z_wdo=4.5))
    out_di = risk_gate(**_ok_kwargs(z_di=-4.2))
    assert "Z_ANOMALY" in out_wdo["reasons"]
    assert "Z_ANOMALY" in out_di["reasons"]


def test_z_anomaly_kwarg_overrides_default():
    """live_profile.z_anomaly=3.5 must trip at |z|=3.7 even though core.config.Z_ANOMALY=4.0."""
    out = risk_gate(**_ok_kwargs(z_wdo=3.7, z_anomaly=3.5))
    assert "Z_ANOMALY" in out["reasons"]

    # Sanity: same |z|=3.7 at the unchanged 4.0 threshold does not block.
    out_default = risk_gate(**_ok_kwargs(z_wdo=3.7))
    assert "Z_ANOMALY" not in out_default["reasons"]


def test_z_anomaly_kwarg_can_loosen_threshold():
    """live_profile.z_anomaly=5.0 lets |z|=4.5 pass when the static default would block."""
    out = risk_gate(**_ok_kwargs(z_wdo=4.5, z_anomaly=5.0))
    assert "Z_ANOMALY" not in out["reasons"]


def test_beta_unstable_true_blocks_with_reason():
    """`beta_unstable=True` mirrors upstream `not beta_unstable` → BETA_UNSTABLE."""
    out = risk_gate(**_ok_kwargs(beta_unstable=True))
    assert out["allowed"] is False
    assert "BETA_UNSTABLE" in out["reasons"]
    assert out["checks"]["beta_state"] is False


def test_beta_unstable_false_does_not_block():
    out = risk_gate(**_ok_kwargs(beta_unstable=False))
    assert "BETA_UNSTABLE" not in out["reasons"]
    assert out["checks"]["beta_state"] is True


def test_beta_unstable_default_does_not_block():
    """Omitting the kwarg keeps prior callers unaffected (default False)."""
    out = risk_gate(**_ok_kwargs())
    assert "BETA_UNSTABLE" not in out["reasons"]


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


def test_threshold_overrides_are_applied_without_changing_defaults():
    relaxed = risk_gate(
        **_ok_kwargs(
            eg_pvalue=0.20,
            rho_level=2,
            beta_delta_pct=30.0,
            eg_threshold=0.30,
            rho_breakdown_level=3,
            beta_delta_max=40.0,
        )
    )
    assert "EG_NOT_COINTEGRATED" not in relaxed["reasons"]
    assert "RHO_BREAKDOWN" not in relaxed["reasons"]
    assert "BETA_DRIFT" not in relaxed["reasons"]

    default = risk_gate(**_ok_kwargs(eg_pvalue=0.20, rho_level=2, beta_delta_pct=30.0))
    assert "EG_NOT_COINTEGRATED" in default["reasons"]
    assert "RHO_BREAKDOWN" in default["reasons"]
    assert "BETA_DRIFT" in default["reasons"]


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


# ─── TASK-16.3: session window via profile kwargs ───────────────────────────


def test_session_window_kwargs_widen_entry_window():
    """A profile that opens entries earlier than core.config must let an
    08:00 poll through (default ENTRY_START_H=09:00 would block it)."""
    blocked = risk_gate(**_ok_kwargs(hour=8, minute=0))
    assert "OUT_OF_SESSION" in blocked["reasons"]
    allowed = risk_gate(**_ok_kwargs(
        hour=8, minute=0,
        entry_start_h=7, entry_start_m=0,
        entry_end_h=17, entry_end_m=25,
    ))
    assert allowed["checks"]["session"] is True
    assert "OUT_OF_SESSION" not in allowed["reasons"]


def test_session_window_kwargs_shrink_entry_window():
    """A profile that closes the entry window earlier than core.config must
    reject a poll inside the legacy window."""
    allowed_default = risk_gate(**_ok_kwargs(hour=14, minute=0))
    assert allowed_default["checks"]["session"] is True
    blocked = risk_gate(**_ok_kwargs(
        hour=14, minute=0,
        entry_start_h=9, entry_start_m=0,
        entry_end_h=10, entry_end_m=0,
    ))
    assert blocked["checks"]["session"] is False
    assert "OUT_OF_SESSION" in blocked["reasons"]


def test_in_session_boundary_inclusive_for_both_ends():
    """Window is inclusive on both ends (preserves legacy behaviour)."""
    out_start = risk_gate(**_ok_kwargs(
        hour=9, minute=0,
        entry_start_h=9, entry_start_m=0,
        entry_end_h=17, entry_end_m=25,
    ))
    assert out_start["checks"]["session"] is True

    out_end = risk_gate(**_ok_kwargs(
        hour=17, minute=25,
        entry_start_h=9, entry_start_m=0,
        entry_end_h=17, entry_end_m=25,
    ))
    assert out_end["checks"]["session"] is True


def test_session_kwargs_none_falls_back_to_core_config():
    """Backward-compat: kwargs absent ⇒ ``core.config`` constants apply."""
    out = risk_gate(**_ok_kwargs(hour=10, minute=0))  # inside legacy 09:00-17:25
    assert out["checks"]["session"] is True
