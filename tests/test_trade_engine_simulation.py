"""TradeEngine ⨯ simulation_profile (Slice A.6).

Validates that ``simulation_profile`` is wired into ``TradeEngine.evaluate``
as an *input parameter* — never a parallel code path. When the profile is
``None`` or ``enabled=False`` the engine must behave bit-exactly to the
baseline so live (which always passes ``simulation_profile=None``) is
untouched.

Covers:
  - Entry slippage (paper mode only; live MT5 fill price wins).
  - Intra-bar SL/TP detection via ``win_high``/``win_low``.
  - Conflict rule resolution when TP and SL trigger inside the same bar.
  - ``exit_at_sl_tp_level`` snapping the realized exit to the SL/TP level.
  - Exit slippage and round-trip cost deduction.
  - Graceful degradation when ``intra_bar_sl_tp=True`` but H/L absent.
"""
import json
import sqlite3

import pytest

import core.trade_engine as te
from core.execution_timeline import load_timeline
from core.trade_engine import TradeEngine
from core.config import (
    BUY_SL, BUY_TP, BUY_BE_ACT, BUY_BE_LOCK,
    SELL_SL, SELL_TP,
    WIN_CONTRACTS, WIN_PV,
)


@pytest.fixture
def engine(tmp_path):
    return TradeEngine(db_path=str(tmp_path / "test_trades.db"))


def _gate(allowed=True, reasons=None):
    return {
        "allowed": allowed,
        "reasons": list(reasons) if reasons else [],
        "checks": {},
        "informational": {"joh_open": True, "hmm_state": None, "eg_pvalue": 0.02},
    }


def _sim(**overrides):
    """Build a simulation_profile dict; defaults to ``enabled=True`` so tests
    explicitly opt-out via ``enabled=False`` when they want baseline."""
    base = {
        "enabled": True,
        "entry_slippage_pts": 5.0,
        "exit_slippage_pts": 5.0,
        "cost_per_contract_rt_brl": 1.0,
        "intra_bar_sl_tp": True,
        "exit_at_sl_tp_level": True,
        "conflict_rule": "sl_first",
    }
    base.update(overrides)
    return base


def _open_buy(engine, win_price=130000, sim=None):
    return engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=win_price, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        simulation_profile=sim,
    )


def _open_sell(engine, win_price=130000, sim=None):
    return engine.evaluate(
        z_wdo=2.1, z_di=1.5,
        win_price=win_price, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        simulation_profile=sim,
    )


def _matador_row(engine, trade_id):
    conn = sqlite3.connect(engine.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM matador_ops WHERE id = ?", (trade_id,)
    ).fetchone()
    conn.close()
    return dict(row)


# ── Bit-exact regression when sim disabled / None ───────────────────────────

def test_simulation_none_matches_baseline_target(engine):
    _open_buy(engine)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"
    # Baseline pnl: pts_favor=BUY_TP, cost=0, no slippage
    expected = BUY_TP * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_simulation_enabled_false_matches_baseline(engine):
    """Profile with ``enabled=False`` must be a no-op (bit-exact baseline)."""
    sim_off = _sim(enabled=False, entry_slippage_pts=10, exit_slippage_pts=10,
                   cost_per_contract_rt_brl=5.0)
    _open_buy(engine, sim=sim_off)
    row_in = _matador_row(engine, 1)
    assert row_in["price_win_in"] == 130000  # NO entry slip

    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim_off,
        win_high=130000 + BUY_TP + 100, win_low=130000 - 50,
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"
    expected = BUY_TP * WIN_CONTRACTS * WIN_PV  # no cost, no slippage
    assert result["pnl"] == pytest.approx(expected)


# ── Entry slippage ───────────────────────────────────────────────────────────

def test_entry_slippage_buy_paper(engine, monkeypatch):
    monkeypatch.setattr(te, "LIVE_ORDERS", False)
    sim = _sim(entry_slippage_pts=7.0)
    _open_buy(engine, win_price=130000, sim=sim)

    row = _matador_row(engine, 1)
    assert row["price_win_in"] == 130007  # BUY pays the ask: +slip


def test_entry_slippage_sell_paper(engine, monkeypatch):
    monkeypatch.setattr(te, "LIVE_ORDERS", False)
    sim = _sim(entry_slippage_pts=7.0)
    _open_sell(engine, win_price=130000, sim=sim)

    row = _matador_row(engine, 1)
    assert row["price_win_in"] == 129993  # SELL hits the bid: -slip


def test_entry_slippage_skipped_in_live_mode(engine, monkeypatch):
    """When LIVE_ORDERS=1, MT5 fill price wins; sim entry slip is ignored."""
    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te, "send_market_order",
        lambda *a, **kw: {"ok": True, "ticket": 999, "retcode": 10009,
                          "message": "ok", "price": 130123.0},
    )
    sim = _sim(entry_slippage_pts=50.0)
    _open_buy(engine, win_price=130000, sim=sim)
    row = _matador_row(engine, 1)
    assert row["price_win_in"] == 130123.0  # MT5 fill, not sim


# ── Exit slippage ────────────────────────────────────────────────────────────

def test_exit_slippage_target_buy(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=5.0,
               cost_per_contract_rt_brl=0)
    _open_buy(engine, sim=sim)
    # win_low must stay above entry so BE_STOP (be_lock=0) does not race TP.
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP, win_low=130000 + 50,
    )
    assert result["exit_reason"] == "TARGET"
    # exit at TP level (800), then -5 slip = 795 final pts_favor
    expected = (BUY_TP - 5.0) * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_exit_slippage_target_sell(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=5.0,
               cost_per_contract_rt_brl=0)
    _open_sell(engine, sim=sim)
    # win_high < entry so SELL favor_low > 0 (no BE_STOP race).
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - SELL_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 - 50, win_low=130000 - SELL_TP,
    )
    assert result["exit_reason"] == "TARGET"
    expected = (SELL_TP - 5.0) * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


# ── Intra-bar SL/TP detection ────────────────────────────────────────────────

def test_intra_bar_tp_from_wick_buy(engine):
    """bar.high crosses TP but close did not — exit at TP level."""
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0)
    _open_buy(engine, sim=sim)
    # win_low above entry so BE_STOP doesn't race TP intra-bar.
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP - 50, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP + 10, win_low=130000 + 100,
    )
    assert result["exit_reason"] == "TARGET"
    expected = BUY_TP * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_intra_bar_sl_from_wick_buy(engine):
    """bar.low crosses SL but close did not — exit at SL level."""
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0)
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - 50, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + 20, win_low=130000 - BUY_SL - 10,
    )
    assert result["exit_reason"] == "STOP_LOSS"
    expected = -BUY_SL * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_intra_bar_no_trigger_when_neither_level_hit(engine):
    """High/Low both inside the band → HOLDING, no exit."""
    sim = _sim()
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + 100, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + 200, win_low=130000 - 100,
    )
    assert result["action"] == "HOLDING"


# ── Conflict resolution ──────────────────────────────────────────────────────

def test_conflict_rule_sl_first_picks_be_stop_when_original_sl_not_hit(engine):
    """TP + BE_STOP same bar (BE auto-activates when high >= BE_ACT < TP).
    ``sl_first`` picks the conservative stop-side resolution → BE_STOP."""
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0, conflict_rule="sl_first")
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP + 5, win_low=130000 - 5,
    )
    assert result["exit_reason"] == "BE_STOP"
    # exit at BE_LOCK level (0)
    expected = float(BUY_BE_LOCK) * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_conflict_rule_sl_first_picks_stop_loss_when_original_sl_hit(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0, conflict_rule="sl_first")
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP + 5, win_low=130000 - BUY_SL - 5,
    )
    assert result["exit_reason"] == "STOP_LOSS"
    expected = -BUY_SL * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_conflict_rule_tp_first_picks_target(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0, conflict_rule="tp_first")
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP + 5, win_low=130000 - 5,
    )
    assert result["exit_reason"] == "TARGET"
    expected = BUY_TP * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_conflict_rule_worst_matches_sl_first(engine):
    """``worst`` is equivalent to ``sl_first`` for original SL conflicts."""
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0, conflict_rule="worst")
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP + 5, win_low=130000 - BUY_SL - 5,
    )
    assert result["exit_reason"] == "STOP_LOSS"


def test_conflict_rule_tp_first_picks_target_when_original_sl_hit(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0, conflict_rule="tp_first")
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP + 5, win_low=130000 - BUY_SL - 5,
    )
    assert result["exit_reason"] == "TARGET"


# ── Cost deduction ───────────────────────────────────────────────────────────

def test_cost_per_contract_rt_deducted_from_pnl(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=1.0)
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP, win_low=130000 + 100,
    )
    assert result["exit_reason"] == "TARGET"
    expected = BUY_TP * WIN_CONTRACTS * WIN_PV - 1.0 * WIN_CONTRACTS
    assert result["pnl"] == pytest.approx(expected)


# ── exit_at_sl_tp_level toggle ───────────────────────────────────────────────

def test_exit_at_sl_tp_level_false_uses_close(engine):
    """When ``exit_at_sl_tp_level=False`` the exit prices at the close."""
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0, exit_at_sl_tp_level=False)
    _open_buy(engine, sim=sim)
    # Close overshoots TP — without snap-to-level, exit at the overshoot.
    overshoot = BUY_TP + 200
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + overshoot, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + overshoot, win_low=130000 + overshoot - 50,
    )
    assert result["exit_reason"] == "TARGET"
    expected = overshoot * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


# ── Graceful degradation when H/L missing ────────────────────────────────────

def test_intra_bar_missing_hl_falls_back_to_close_only(engine):
    """``intra_bar_sl_tp=True`` but ``win_high``/``win_low`` absent: the engine
    must still apply the sim profile (slippage + cost + snap-to-level) but
    detection falls back to close-only.
    """
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0)
    _open_buy(engine, sim=sim)
    # close exactly crosses TP — close-only path still triggers TARGET.
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=None, win_low=None,
    )
    assert result["exit_reason"] == "TARGET"
    expected = BUY_TP * WIN_CONTRACTS * WIN_PV
    assert result["pnl"] == pytest.approx(expected)


def test_intra_bar_missing_hl_doesnt_trigger_from_wick(engine):
    """Without H/L, the wick scenario from
    ``test_intra_bar_tp_from_wick_buy`` (close < TP) must NOT trigger.
    """
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0)
    _open_buy(engine, sim=sim)
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP - 50, wdo_price=5800,  # close below TP
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=None, win_low=None,
    )
    assert result["action"] == "HOLDING"


# ── Timeline payload audit trail ─────────────────────────────────────────────

def test_timeline_signal_records_entry_slippage(engine, monkeypatch):
    monkeypatch.setattr(te, "LIVE_ORDERS", False)
    sim = _sim(entry_slippage_pts=7.0)
    _open_buy(engine, sim=sim)

    rows = list(reversed(load_timeline(engine.db_path, limit=20)))
    signal = [r for r in rows if r["event"] == "BUY_WIN"][0]
    payload = json.loads(signal["payload_json"])
    assert payload["entry_slippage_pts"] == 7.0
    assert payload["entry_price"] == 130007


def test_timeline_exit_records_simulation_audit_fields(engine):
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=5.0,
               cost_per_contract_rt_brl=1.0)
    _open_buy(engine, sim=sim)
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_TP, win_low=130000 + 100,
    )

    rows = list(reversed(load_timeline(engine.db_path, limit=20)))
    exit_evt = [r for r in rows if r["event"] == "TARGET"][0]
    payload = json.loads(exit_evt["payload_json"])
    assert payload["simulation_enabled"] is True
    assert payload["intra_bar_used"] is True
    assert payload["exit_pts_favor"] == float(BUY_TP)
    assert payload["final_pts_favor"] == pytest.approx(BUY_TP - 5.0)
    assert payload["exit_slippage_pts"] == 5.0
    assert payload["cost_brl"] == pytest.approx(1.0 * WIN_CONTRACTS)


# ── BE activation by intra-bar peak ──────────────────────────────────────────

def test_be_activation_uses_intra_bar_high(engine):
    """BE must activate when bar.high reaches BE_ACT — not only when close
    does. Otherwise replay would miss BE locks that actually fired live."""
    sim = _sim(entry_slippage_pts=0, exit_slippage_pts=0,
               cost_per_contract_rt_brl=0)
    _open_buy(engine, sim=sim)
    # Bar where close is back to entry but high reached BE_ACT
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        simulation_profile=sim,
        win_high=130000 + BUY_BE_ACT + 10, win_low=130000 - 5,
    )
    # BUY_BE_LOCK = 0; close at entry (pts_favor=0) means be_lock crossed.
    # Conflict: no SL hit (low=-5 > -BUY_SL), tp not hit, BE activated and
    # be_stop_hit when favor_low <= 0 → reason = "BE_STOP".
    assert result["exit_reason"] == "BE_STOP"
