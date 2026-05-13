import sqlite3
import json
from datetime import datetime, timedelta
import pytest
import core.trade_engine as te
from core.execution_timeline import load_timeline
from core.trade_engine import TradeEngine
from core.config import (
    BUY_SL, BUY_TP, SELL_TP,
    BUY_BE_ACT, BUY_BE_LOCK,
    SELL_SL, SELL_BE_ACT, SELL_BE_LOCK,
    FORCE_CLOSE_H, FORCE_CLOSE_M,
    Z_ENTRY, Z_ATTENTION,
)


def _engine_params(
    *,
    buy_sl=BUY_SL, buy_tp=BUY_TP, buy_be_act=BUY_BE_ACT, buy_be_lock=BUY_BE_LOCK,
    sell_sl=SELL_SL, sell_tp=SELL_TP, sell_be_act=SELL_BE_ACT, sell_be_lock=SELL_BE_LOCK,
    z_entry=Z_ENTRY, z_attention=Z_ATTENTION,
) -> dict:
    return {
        "buy_sl": buy_sl, "buy_tp": buy_tp,
        "buy_be_act": buy_be_act, "buy_be_lock": buy_be_lock,
        "sell_sl": sell_sl, "sell_tp": sell_tp,
        "sell_be_act": sell_be_act, "sell_be_lock": sell_be_lock,
        "z_entry": z_entry, "z_attention": z_attention,
    }


@pytest.fixture
def engine(tmp_path):
    db_path = str(tmp_path / "test_trades.db")
    return TradeEngine(db_path=db_path)


def _gate(allowed=True, reasons=None):
    """Construct a risk_gate-shaped dict for tests focused on strategy logic.

    Real risk_gate composition is exercised in tests/test_risk_gate.py — here
    we just need a dict with the keys evaluate() reads.
    """
    return {
        "allowed": allowed,
        "reasons": list(reasons) if reasons else [],
        "checks": {},
        "informational": {"joh_open": True, "hmm_state": None, "eg_pvalue": 0.02},
    }


def _timeline_rows(engine):
    return list(reversed(load_timeline(engine.db_path, limit=100)))


# ── Entry conditions ─────────────────────────────────────────────────────────

def test_no_entry_below_threshold(engine):
    """Z-scores below all thresholds should NOT open a trade."""
    result = engine.evaluate(
        z_wdo=1.3, z_di=1.1,       # both below Z_ENTRY=1.4 and Z_ATTENTION=1.2
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "WAIT"
    assert result["holding"] is False


def test_buy_entry_consensus(engine):
    """Both z-scores confirming buy (CONS_BASE) should open BUY WIN."""
    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,     # z_wdo <= -Z_ENTRY and z_di <= -Z_ATTENTION
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "BUY_WIN"
    assert result["strategies"]["CONS_BASE"]["open_trade"] is not None
    assert result["strategies"]["CONS_BASE"]["open_trade"]["direction"] == "BUY"


def test_entry_uses_closed_bar_prices_when_provided(engine):
    """Entry fills must use closed-bar inputs while exit checks may use live prices."""
    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=999999, wdo_price=9999,
        entry_win_price=130000, entry_wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
    )

    opened = result["strategies"]["CONS_BASE"]["open_trade"]
    assert opened["price_win_in"] == 130000

    conn = sqlite3.connect(engine.db_path)
    row = conn.execute(
        "SELECT price_win_in, price_wdo_in FROM matador_ops WHERE id = ?",
        (opened["id"],),
    ).fetchone()
    conn.close()
    assert row == (130000, 5800)


def test_sell_entry_consensus(engine):
    """Both z-scores confirming sell (CONS_BASE) should open SELL WIN."""
    result = engine.evaluate(
        z_wdo=2.1, z_di=1.5,       # z_wdo >= Z_ENTRY and z_di >= Z_ATTENTION
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "SELL_WIN"
    assert result["strategies"]["CONS_BASE"]["open_trade"]["direction"] == "SELL"


def test_blocked_gate_blocks_entry(engine):
    """gate.allowed=False (any reason) should block all new entries."""
    result = engine.evaluate(
        z_wdo=-2.5, z_di=-2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["BETA_DRIFT"]),
        hmm_state="CHOP", hour=11, minute=0
    )
    assert result["action"] == "WAIT"
    # gate_reasons must propagate to the strategy result for traceability
    for strat_result in result["strategies"].values():
        assert "BETA_DRIFT" in strat_result["gate_reasons"]


def test_anomaly_reason_surfaces_as_anomaly_action(engine):
    """When Z_ANOMALY is the reason, the action label stays ANOMALY."""
    result = engine.evaluate(
        z_wdo=-4.5, z_di=4.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["Z_ANOMALY"]),
        hmm_state="CHOP", hour=11, minute=0
    )
    assert result["action"] == "ANOMALY"


def test_blocked_gate_with_session_reason_returns_wait(engine):
    result = engine.evaluate(
        z_wdo=-2.5, z_di=-2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["OUT_OF_SESSION"]),
        hmm_state="CHOP", hour=8, minute=59
    )
    assert result["action"] == "WAIT"


# ── Per-strategy EG bypass (Slice C) ─────────────────────────────────────────

def test_eg_strategies_none_blocks_all_strategies(engine):
    """Default behaviour (eg_strategies=None): EG_NOT_COINTEGRATED blocks every slot."""
    result = engine.evaluate(
        z_wdo=2.5, z_di=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["EG_NOT_COINTEGRATED"]),
        hmm_state="CHOP", hour=11, minute=0,
        eg_strategies=None,
    )
    for strat in ("CONS_BASE", "WDO_NWE", "DI_NWE"):
        assert "EG_NOT_COINTEGRATED" in result["strategies"][strat]["gate_reasons"]
        assert result["strategies"][strat]["open_trade"] is None


def test_eg_strategies_subset_strips_eg_for_excluded_slots(engine):
    """Strategies absent from eg_strategies should not see EG reasons."""
    result = engine.evaluate(
        z_wdo=2.5, z_di=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["EG_NOT_COINTEGRATED"]),
        hmm_state="CHOP", hour=11, minute=0,
        nwe_is_up=True, nwe_upper=130100.0, nwe_lower=129900.0,
        eg_strategies=["CONS_BASE", "WDO_NWE"],
    )
    # Listed strategies still blocked by EG
    assert "EG_NOT_COINTEGRATED" in result["strategies"]["CONS_BASE"]["gate_reasons"]
    assert "EG_NOT_COINTEGRATED" in result["strategies"]["WDO_NWE"]["gate_reasons"]
    # DI_NWE bypasses EG: gate_reasons (if present) must not include it.
    di_reasons = result["strategies"]["DI_NWE"].get("gate_reasons", [])
    assert "EG_NOT_COINTEGRATED" not in di_reasons


def test_eg_strategies_empty_bypasses_eg_for_all_slots(engine):
    """eg_strategies=[] means EG never blocks — strategies pass the gate (CONS_BASE opens)."""
    result = engine.evaluate(
        z_wdo=2.5, z_di=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["EG_NOT_COINTEGRATED"]),
        hmm_state="CHOP", hour=11, minute=0,
        nwe_is_up=True, nwe_upper=130100.0, nwe_lower=129900.0,
        eg_strategies=[],
    )
    # CONS_BASE bypasses EG and reaches its strategy logic → SELL_WIN opens
    assert result["strategies"]["CONS_BASE"]["open_trade"] is not None
    # No slot may report EG as a blocking reason when EG is bypassed for all.
    for strat in ("CONS_BASE", "WDO_NWE", "DI_NWE"):
        reasons = result["strategies"][strat].get("gate_reasons", [])
        assert "EG_NOT_COINTEGRATED" not in reasons


def test_eg_strategies_bypass_does_not_strip_other_reasons(engine):
    """EG bypass must only strip EG_* reasons, not BETA_DRIFT or RHO_BREAKDOWN."""
    result = engine.evaluate(
        z_wdo=2.5, z_di=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75,
        gate=_gate(
            allowed=False,
            reasons=["EG_NOT_COINTEGRATED", "BETA_DRIFT"],
        ),
        hmm_state="CHOP", hour=11, minute=0,
        eg_strategies=["CONS_BASE"],  # WDO_NWE and DI_NWE bypass EG
    )
    # CONS_BASE sees both
    assert "EG_NOT_COINTEGRATED" in result["strategies"]["CONS_BASE"]["gate_reasons"]
    assert "BETA_DRIFT" in result["strategies"]["CONS_BASE"]["gate_reasons"]
    # The bypassed slots still see BETA_DRIFT (only EG is stripped)
    for strat in ("WDO_NWE", "DI_NWE"):
        assert "EG_NOT_COINTEGRATED" not in result["strategies"][strat]["gate_reasons"]
        assert "BETA_DRIFT" in result["strategies"][strat]["gate_reasons"]


def test_eg_unavailable_also_filtered_for_excluded_strategies(engine):
    """Both EG_REASONS members (EG_UNAVAILABLE + EG_NOT_COINTEGRATED) are stripped."""
    result = engine.evaluate(
        z_wdo=2.5, z_di=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(allowed=False, reasons=["EG_UNAVAILABLE"]),
        hmm_state="CHOP", hour=11, minute=0,
        nwe_is_up=True, nwe_upper=130100.0, nwe_lower=129900.0,
        eg_strategies=["CONS_BASE", "WDO_NWE"],
    )
    assert "EG_UNAVAILABLE" in result["strategies"]["CONS_BASE"]["gate_reasons"]
    assert "EG_UNAVAILABLE" in result["strategies"]["WDO_NWE"]["gate_reasons"]
    di_reasons = result["strategies"]["DI_NWE"].get("gate_reasons", [])
    assert "EG_UNAVAILABLE" not in di_reasons


# ── Exit conditions (gate is allowed; entries open then exits trigger) ───────

def test_stop_loss_buy(engine):
    """BUY trade should close on SL when price drops BUY_SL points."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    result = engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "STOP_LOSS"


def test_take_profit_sell(engine):
    """SELL trade should close on TP when price drops SELL_TP points."""
    engine.evaluate(
        z_wdo=2.1, z_di=1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    result = engine.evaluate(
        z_wdo=0.5, z_di=0.5,
        win_price=130000 - SELL_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"


def test_breakeven_activation_buy(engine):
    """BUY trade should activate BE after BUY_BE_ACT pts, then close at BUY_BE_LOCK."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    # Price rises enough to activate BE
    result = engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 + 400, wdo_price=5800,   # 400 >= BUY_BE_ACT=300
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "HOLDING"

    # Price retraces to BUY_BE_LOCK (0 pts = entry price)
    result = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=130000, wdo_price=5800,          # pts_favor=0 <= BUY_BE_LOCK=0
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=10
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "BE_STOP"


def test_exits_run_even_when_gate_blocks_new_entries(engine):
    """Exits must be evaluated every tick regardless of gate.allowed.
    If the gate blocks while a position is open, SL/TP/BE still fire."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    # Now the gate goes hostile (e.g., rho breakdown mid-trade) AND price hits SL
    result = engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.30, gate=_gate(allowed=False, reasons=["RHO_BREAKDOWN"]),
        hmm_state="CHOP", hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "STOP_LOSS"


def test_performance_report(engine):
    """Performance report should reflect closed trades."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5
    )
    perf = engine.get_performance()
    assert perf["total_closed_trades"] == 1
    assert perf["wins"] == 1
    assert perf["accumulated_pnl"] > 0


# ── get_trades_for_date() ────────────────────────────────────────────────────

def test_get_trades_for_date_banco_vazio(engine):
    """Empty DB should return empty list."""
    result = engine.get_trades_for_date("2026-05-06")
    assert result == []


def test_get_trades_for_date_retorna_open_e_closed(engine):
    """Should return OPEN and CLOSED trades together for the requested date."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Open and immediately close a BUY trade (CONS_BASE)
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5
    )

    # Open a second BUY trade (WDO_NWE) — leave it OPEN
    # Use nwe_is_up=False + win_price near lower band to pass NWE filter
    engine.evaluate(
        z_wdo=-2.1, z_di=0.0,
        win_price=100000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=12, minute=0,
        nwe_is_up=False, nwe_upper=120000, nwe_lower=99000,
    )

    trades = engine.get_trades_for_date(today)
    statuses = {t["status"] for t in trades}
    assert "CLOSED" in statuses
    assert "OPEN" in statuses
    assert len(trades) >= 2


def test_get_trades_for_date_filtra_outra_data(engine):
    """Should NOT return trades from a different date."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = engine.get_trades_for_date(yesterday)
    assert result == []


def test_get_trades_for_date_preserva_campos(engine):
    """Should preserve ISO timestamps, prices, and status fields."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0
    )
    today = datetime.now().strftime("%Y-%m-%d")
    trades = engine.get_trades_for_date(today)
    assert len(trades) == 1
    t = trades[0]

    # Required fields present
    assert "id" in t
    assert "strategy" in t
    assert "direction" in t
    assert t["direction"] == "BUY"
    assert t["price_win_in"] == 130000
    assert t["status"] == "OPEN"

    # timestamp_in is full ISO (contains 'T' separator)
    assert "T" in t["timestamp_in"]

    # time_in is HH:MM:SS format
    assert t["time_in"] is not None
    parts = t["time_in"].split(":")
    assert len(parts) == 3

    # OPEN trade has no exit fields
    assert t["price_win_out"] is None
    assert t["pnl_brl"] is None
    assert t["time_out"] is None


# ── Operational risk stat helpers (TASK-3 AC #11) ───────────────────────────

def test_count_trades_today_empty(engine):
    assert engine.count_trades_today("2026-05-07") == 0


def test_count_trades_today_includes_open_and_closed(engine):
    today = datetime.now().strftime("%Y-%m-%d")
    # Open + close one trade
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0, win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=5,
    )
    # Open another, leave it open (different strategy slot)
    engine.evaluate(
        z_wdo=-2.1, z_di=0.0, win_price=100000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=12, minute=0,
        nwe_is_up=False, nwe_upper=120000, nwe_lower=99000,
    )
    assert engine.count_trades_today(today) == 2


def test_pnl_today_zero_when_no_closed_trades(engine):
    today = datetime.now().strftime("%Y-%m-%d")
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )
    # Trade is OPEN, no realized P&L yet
    assert engine.pnl_today(today) == 0.0


def test_pnl_today_sums_closed_trades(engine):
    today = datetime.now().strftime("%Y-%m-%d")
    # BUY → TARGET (positive PnL)
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0, win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=5,
    )
    pnl = engine.pnl_today(today)
    assert pnl > 0


def test_minutes_since_last_loss_none_when_no_history(engine):
    assert engine.minutes_since_last_loss() is None


def test_minutes_since_last_loss_after_stop_loss(engine):
    # Open BUY then trigger SL
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )
    engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=5,
    )
    # Cooldown should be ~0 minutes from now
    mins = engine.minutes_since_last_loss()
    assert mins is not None
    assert mins < 1.0


def test_minutes_since_last_loss_uses_explicit_now(engine):
    """`now` arg lets callers compute deterministic deltas — important so
    the V2 endpoint gets a consistent reference instead of clock drift."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )
    engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=5,
    )
    future = datetime.now() + timedelta(minutes=45)
    mins = engine.minutes_since_last_loss(now=future)
    assert mins is not None
    assert 44.0 < mins < 46.0


def test_stop_loss_in_one_slot_blocks_open_in_other_slot(engine):
    """Codex round-4 regression: a STOP_LOSS firing in phase 1 must trip
    LOSS_COOLDOWN for any other slot's entry attempt in the SAME evaluate()
    call. Before the two-pass refactor, the gate computed once at
    server.py:732 was reused stale across slots — letting WDO_NWE bypass
    the cooldown that was just earned by CONS_BASE losing."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Open a CONS_BASE BUY at win_price=130000
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )

    # Same poll: price drop triggers CONS_BASE STOP_LOSS in phase 1.
    # WDO_NWE has no open trade and z_wdo well past entry, so phase 2 would
    # otherwise open it. NWE bands set so the filter allows the BUY.
    win_now = 130000 - BUY_SL
    result = engine.evaluate(
        z_wdo=-2.1, z_di=0.0,
        win_price=win_now, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=5,
        nwe_is_up=False, nwe_lower=win_now, nwe_upper=win_now + 500,
    )

    # Phase 1: CONS_BASE closed on stop
    cb = result["strategies"]["CONS_BASE"]
    assert cb["action"] == "CLOSE"
    assert cb["exit_reason"] == "STOP_LOSS"

    # Phase 2: WDO_NWE must be blocked by LOSS_COOLDOWN, NOT opened
    wdo = result["strategies"]["WDO_NWE"]
    assert wdo["open_trade"] is None, "WDO_NWE bypassed LOSS_COOLDOWN"
    assert "LOSS_COOLDOWN" in wdo["gate_reasons"]
    assert wdo["action"] == "WAIT"

    # And no second trade was actually inserted
    assert engine.count_trades_today(today) == 1


def test_minutes_since_last_loss_ignores_target_exits(engine):
    """Only STOP_LOSS exits count for cooldown — TARGET wins shouldn't
    keep a fresh trade off the table."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5, win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=0,
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0, win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP", hour=11, minute=5,
    )
    assert engine.minutes_since_last_loss() is None


# ── gate_block logging ────────────────────────────────────────────────────────

def test_gate_block_logged_for_substantive_reason(engine, caplog):
    """A hard gate failure (e.g. RHO_BREAKDOWN) must produce an INFO record
    with strategy, action, and reasons so operators can diagnose blocks."""
    import logging
    with caplog.at_level(logging.INFO, logger="core.trade_engine"):
        engine.evaluate(
            z_wdo=0.5, z_di=-0.3,
            win_price=130000, wdo_price=5800,
            rho=-0.75,
            gate=_gate(allowed=False, reasons=["RHO_BREAKDOWN"]),
            hmm_state="CHOP",
            hour=11, minute=0,
        )
    gate_records = [r for r in caplog.records if "gate_block" in r.message]
    assert len(gate_records) >= 1
    assert "RHO_BREAKDOWN" in gate_records[0].message


def test_gate_block_not_logged_for_bar_not_closed(engine, caplog):
    """BAR_NOT_CLOSED fires on every poll tick — must NOT produce log spam."""
    import logging
    with caplog.at_level(logging.INFO, logger="core.trade_engine"):
        engine.evaluate(
            z_wdo=0.5, z_di=-0.3,
            win_price=130000, wdo_price=5800,
            rho=-0.75,
            gate=_gate(allowed=False, reasons=["BAR_NOT_CLOSED"]),
            hmm_state="CHOP",
            hour=11, minute=0,
        )
    gate_records = [r for r in caplog.records if "gate_block" in r.message]
    assert gate_records == []


def test_gate_block_not_logged_for_out_of_session(engine, caplog):
    """OUT_OF_SESSION fires on every out-of-hours poll — must NOT spam."""
    import logging
    with caplog.at_level(logging.INFO, logger="core.trade_engine"):
        engine.evaluate(
            z_wdo=0.5, z_di=-0.3,
            win_price=130000, wdo_price=5800,
            rho=-0.75,
            gate=_gate(allowed=False, reasons=["OUT_OF_SESSION"]),
            hmm_state="CHOP",
            hour=8, minute=0,
        )
    gate_records = [r for r in caplog.records if "gate_block" in r.message]
    assert gate_records == []


def test_gate_block_logged_when_bar_closed_plus_other_reason(engine, caplog):
    """BAR_NOT_CLOSED combined with a substantive reason must still log."""
    import logging
    with caplog.at_level(logging.INFO, logger="core.trade_engine"):
        engine.evaluate(
            z_wdo=0.5, z_di=-0.3,
            win_price=130000, wdo_price=5800,
            rho=-0.75,
            gate=_gate(allowed=False, reasons=["BAR_NOT_CLOSED", "EG_UNAVAILABLE"]),
            hmm_state="CHOP",
            hour=11, minute=0,
        )
    gate_records = [r for r in caplog.records if "gate_block" in r.message]
    assert len(gate_records) >= 1
    assert "EG_UNAVAILABLE" in gate_records[0].message


# ── Execution timeline emission (TASK-4.3 / Slice C) ─────────────────────────

def test_timeline_paper_open_records_real_signal_without_order(engine, monkeypatch):
    monkeypatch.setattr(te, "LIVE_ORDERS", False)

    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0, closed_bar_ts=1778243100,
    )

    assert result["action"] == "BUY_WIN"
    rows = _timeline_rows(engine)
    assert [r["event"] for r in rows] == ["BUY_WIN"]
    signal = rows[0]
    assert signal["phase"] == "SIGNAL"
    assert signal["status"] == "OK"
    assert signal["closed_bar_ts"] == 1778243100
    assert signal["correlation_id"].startswith("attempt:")
    assert signal["attempt_id"]
    assert signal["trade_id"] is None
    payload = json.loads(signal["payload_json"])
    assert payload["direction"] == "BUY"
    assert payload["z_source"] == "CONSENSO"


def test_timeline_live_open_records_signal_order_and_execution(engine, monkeypatch):
    captured = {}

    def fake_send(symbol, side, volume, magic, deviation, comment):
        captured.update(
            symbol=symbol, side=side, volume=volume,
            magic=magic, deviation=deviation, comment=comment,
        )
        return {
            "ok": True,
            "ticket": 111222,
            "retcode": 10009,
            "message": "done",
            "price": 130025.0,
        }

    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(te, "send_market_order", fake_send)

    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0, closed_bar_ts=1778243100,
    )

    assert result["action"] == "BUY_WIN"
    rows = _timeline_rows(engine)
    assert [r["event"] for r in rows] == [
        "BUY_WIN",
        "ORDER_REQUEST",
        "EXECUTION_FILLED",
    ]
    attempt_ids = {r["attempt_id"] for r in rows}
    corr_ids = {r["correlation_id"] for r in rows}
    assert len(attempt_ids) == 1
    assert len(corr_ids) == 1
    assert next(iter(corr_ids)).startswith("attempt:")
    assert all(r["closed_bar_ts"] == 1778243100 for r in rows)

    order_request = json.loads(rows[1]["payload_json"])
    assert order_request == captured
    execution = json.loads(rows[2]["payload_json"])
    assert execution["ticket"] == 111222
    assert execution["price"] == 130025.0
    assert execution["retcode"] == 10009


def test_timeline_live_reject_records_execution_rejected_without_trade(engine, monkeypatch):
    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te,
        "send_market_order",
        lambda *args, **kwargs: {
            "ok": False,
            "ticket": None,
            "retcode": 10004,
            "message": "requote",
            "price": None,
        },
    )

    result = engine.evaluate(
        z_wdo=2.1, z_di=1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0, closed_bar_ts=1778243100,
        nwe_is_up=False,
    )

    assert result["action"] == "ORDER_FAILED"
    rows = _timeline_rows(engine)
    assert [r["event"] for r in rows] == [
        "SELL_WIN",
        "ORDER_REQUEST",
        "EXECUTION_REJECTED",
    ]
    assert rows[-1]["phase"] == "EXECUTION"
    assert rows[-1]["status"] == "FAILED"
    assert rows[-1]["severity"] == "operational_block"
    assert "EXIT" not in {r["phase"] for r in rows}
    conn = sqlite3.connect(engine.db_path)
    count = conn.execute("SELECT COUNT(*) FROM matador_ops").fetchone()[0]
    conn.close()
    assert count == 0


def _open_buy_consensus(engine):
    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
    )
    return result["strategies"]["CONS_BASE"]["open_trade"]["id"]


def test_timeline_paper_exit_records_target_with_trade_correlation(engine):
    trade_id = _open_buy_consensus(engine)

    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5, closed_bar_ts=1778243400,
    )

    assert result["action"] == "CLOSE"
    target = [r for r in _timeline_rows(engine) if r["event"] == "TARGET"][0]
    assert target["phase"] == "EXIT"
    assert target["status"] == "OK"
    assert target["correlation_id"] == f"trade:{trade_id}"
    assert target["trade_id"] == trade_id
    assert target["closed_bar_ts"] == 1778243400


def test_timeline_paper_exit_records_stop_loss(engine):
    _open_buy_consensus(engine)

    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )

    assert "STOP_LOSS" in [r["event"] for r in _timeline_rows(engine)]


def test_timeline_paper_exit_records_be_stop(engine):
    _open_buy_consensus(engine)

    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130400, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=10,
    )

    assert "BE_STOP" in [r["event"] for r in _timeline_rows(engine)]


def test_timeline_paper_exit_records_force_close(engine):
    _open_buy_consensus(engine)

    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=FORCE_CLOSE_H, minute=FORCE_CLOSE_M,
    )

    assert "FORCE_CLOSE" in [r["event"] for r in _timeline_rows(engine)]


def test_timeline_live_close_failure_records_exit_and_close_failed(engine, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 5, 8, 11, 5, 10)

    monkeypatch.setattr(te, "datetime", FixedDatetime)
    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te,
        "send_market_order",
        lambda *args, **kwargs: {
            "ok": True,
            "ticket": 111222,
            "retcode": 10009,
            "message": "done",
            "price": 130000.0,
        },
    )
    trade_id = _open_buy_consensus(engine)

    monkeypatch.setattr(
        te,
        "close_position_by_ticket",
        lambda ticket, magic, comment="": {
            "ok": False,
            "ticket": ticket,
            "retcode": 10006,
            "message": "timeout",
            "price": None,
        },
    )
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )

    assert result["action"] == "CLOSE_FAILED"
    rows = _timeline_rows(engine)
    exit_rows = [r for r in rows if r["phase"] == "EXIT"]
    assert [r["event"] for r in exit_rows] == ["STOP_LOSS", "CLOSE_FAILED"]
    assert all(r["correlation_id"] == f"trade:{trade_id}" for r in exit_rows)
    assert exit_rows[0]["status"] == "FAILED"
    assert exit_rows[0]["severity"] == "operational_block"
    assert exit_rows[-1]["status"] == "FAILED"
    payload = json.loads(exit_rows[-1]["payload_json"])
    assert payload["retcode"] == 10006
    assert payload["message"] == "timeout"

    # Same failing close in the same minute must not spam CLOSE_FAILED rows.
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )
    exit_rows = [r for r in _timeline_rows(engine) if r["phase"] == "EXIT"]
    assert [r["event"] for r in exit_rows] == ["STOP_LOSS", "CLOSE_FAILED"]

    monkeypatch.setattr(
        te,
        "close_position_by_ticket",
        lambda ticket, magic, comment="": {
            "ok": True,
            "ticket": ticket,
            "retcode": 10009,
            "message": "done",
            "price": 129890.0,
        },
    )
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )

    assert result["action"] == "CLOSE"
    exit_rows = [r for r in _timeline_rows(engine) if r["phase"] == "EXIT"]
    assert [(r["event"], r["status"]) for r in exit_rows] == [
        ("STOP_LOSS", "FAILED"),
        ("CLOSE_FAILED", "FAILED"),
        ("STOP_LOSS", "OK"),
    ]


def test_timeline_does_not_emit_skipped_signal_on_blocked_poll(engine):
    for _ in range(3):
        engine.evaluate(
            z_wdo=-2.5, z_di=-2.5,
            win_price=130000, wdo_price=5800,
            rho=-0.75, gate=_gate(allowed=False, reasons=["EG_NOT_COINTEGRATED"]),
            hmm_state="CHOP", hour=11, minute=0,
        )

    assert _timeline_rows(engine) == []


# ─── TASK-16.3: force_close via profile kwargs ──────────────────────────────


def test_force_close_kwargs_override_advances_force_close(engine):
    """Profile that force-closes earlier than core.config must trip at the
    configured time even though core.config FORCE_CLOSE is still in the future."""
    _open_buy_consensus(engine)
    # Use an hour < FORCE_CLOSE_H so the legacy default would NOT trip
    early_hour = max(0, FORCE_CLOSE_H - 2)
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=early_hour, minute=0,
        force_close_h=early_hour, force_close_m=0,
    )
    events = [r["event"] for r in _timeline_rows(engine)]
    assert "FORCE_CLOSE" in events


def test_force_close_kwargs_override_delays_force_close(engine):
    """Profile that pushes force-close later must NOT trip at the legacy time."""
    _open_buy_consensus(engine)
    # Run exactly at the legacy FORCE_CLOSE; with override pushing it +1h,
    # the engine must NOT fire FORCE_CLOSE.
    late_h = min(23, FORCE_CLOSE_H + 1)
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=FORCE_CLOSE_H, minute=FORCE_CLOSE_M,
        force_close_h=late_h, force_close_m=FORCE_CLOSE_M,
    )
    events = [r["event"] for r in _timeline_rows(engine)]
    assert "FORCE_CLOSE" not in events


def test_force_close_kwargs_none_falls_back_to_core_config(engine):
    """Backward-compat: omitting kwargs preserves the legacy behaviour."""
    _open_buy_consensus(engine)
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=FORCE_CLOSE_H, minute=FORCE_CLOSE_M,
    )
    assert "FORCE_CLOSE" in [r["event"] for r in _timeline_rows(engine)]


# ─── TASK-16.4: SL/TP/BE snapshot at _open_trade ────────────────────────────


def test_engine_params_burned_into_matador_ops_on_open(engine):
    """SL/TP/BE from engine_params get persisted on the matador_ops row."""
    custom = _engine_params(buy_sl=77, buy_tp=199, buy_be_act=88, buy_be_lock=11)
    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=custom,
    )
    trade_id = result["strategies"]["CONS_BASE"]["open_trade"]["id"]
    conn = sqlite3.connect(engine.db_path)
    row = conn.execute(
        "SELECT sl_pts, tp_pts, be_act_pts, be_lock_pts FROM matador_ops WHERE id=?",
        (trade_id,),
    ).fetchone()
    conn.close()
    assert row == (77, 199, 88, 11)


def test_engine_params_sell_direction_picks_sell_keys(engine):
    """SELL direction uses sell_* keys, not buy_*."""
    custom = _engine_params(buy_sl=77, sell_sl=222, sell_tp=333, sell_be_act=44, sell_be_lock=22)
    result = engine.evaluate(
        z_wdo=2.1, z_di=1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=custom,
    )
    trade_id = result["strategies"]["CONS_BASE"]["open_trade"]["id"]
    conn = sqlite3.connect(engine.db_path)
    row = conn.execute(
        "SELECT direction, sl_pts, tp_pts, be_act_pts, be_lock_pts FROM matador_ops WHERE id=?",
        (trade_id,),
    ).fetchone()
    conn.close()
    assert row == ("SELL", 222, 333, 44, 22)


def test_engine_params_none_falls_back_to_core_config(engine):
    """No engine_params: legacy core.config defaults get burned in."""
    _open_buy_consensus(engine)
    conn = sqlite3.connect(engine.db_path)
    row = conn.execute(
        "SELECT sl_pts, tp_pts, be_act_pts, be_lock_pts FROM matador_ops "
        "WHERE status='OPEN'"
    ).fetchone()
    conn.close()
    assert row == (BUY_SL, BUY_TP, BUY_BE_ACT, BUY_BE_LOCK)


def test_snapshot_is_immutable_to_mid_position_param_changes(engine):
    """CAR4: hot-reload of engine_params after _open_trade must NOT move SL
    of the already-open trade. Open with SL=100, then poll with SL=400 and
    confirm the open trade still STOP_LOSSes at the original 100 level."""
    # Open with a tight SL=100 so a small adverse move triggers the stop.
    open_params = _engine_params(buy_sl=100, buy_tp=9000)
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=open_params,
    )
    # Mid-position hot reload widens SL to 400. The price moves -150 — past
    # the snapshot (100) but still within the new param (400). The trade
    # MUST close: snapshot wins.
    relaxed = _engine_params(buy_sl=400, buy_tp=9000)
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - 150, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        engine_params=relaxed,
    )
    events = [r["event"] for r in _timeline_rows(engine)]
    assert "STOP_LOSS" in events


def test_next_open_after_hot_reload_uses_new_params(engine):
    """AC2: after the open trade closes, the NEXT _open_trade picks up the
    new engine_params — proves hot-reload still works for fresh entries."""
    t0 = datetime(2026, 5, 13, 11, 0, 0)
    # First trade: SL=100, gets stopped immediately.
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=_engine_params(buy_sl=100, buy_tp=9000),
        now_dt=t0,
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - 150, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
        engine_params=_engine_params(buy_sl=100, buy_tp=9000),
        now_dt=t0 + timedelta(minutes=5),
    )
    # Second trade: opens 60 min after the loss (past LOSS_COOLDOWN_MIN=30).
    # New SL=250 — persisted snapshot must reflect the NEW value, not 100.
    new_params = _engine_params(buy_sl=250, buy_tp=8888, buy_be_act=99, buy_be_lock=11)
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=12, minute=5,
        engine_params=new_params,
        now_dt=t0 + timedelta(minutes=65),
    )
    conn = sqlite3.connect(engine.db_path)
    row = conn.execute(
        "SELECT sl_pts, tp_pts, be_act_pts, be_lock_pts FROM matador_ops "
        "WHERE status='OPEN' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == (250, 8888, 99, 11)


def test_legacy_open_trade_without_snapshot_falls_back_to_globals(engine):
    """Pre-migration open trades have NULL sl_pts columns. _check_exits must
    fall back to core.config globals so they still close correctly."""
    # Simulate a legacy OPEN row inserted before the migration.
    conn = sqlite3.connect(engine.db_path)
    conn.execute(
        "INSERT INTO matador_ops "
        "(timestamp_in, status, direction, z_in, z_source, strategy, "
        " rho_in, beta_in, qty_win, price_win_in, price_wdo_in, hmm_state, live, "
        " max_pts_favor, be_active) "
        "VALUES (?, 'OPEN', 'BUY', -2.1, 'CONSENSO', 'CONS_BASE', "
        " -0.75, 1.0, 2, 130000, 5800, 'CHOP', 0, 0.0, 0)",
        (datetime.now().isoformat(),),
    )
    conn.commit()
    conn.close()
    # Push price to -BUY_SL — must STOP_LOSS via fallback.
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=5,
    )
    events = [r["event"] for r in _timeline_rows(engine)]
    assert "STOP_LOSS" in events


# ── TASK-16.5: z_entry / z_attention sourced from engine_params ─────────────


def test_engine_params_z_entry_gates_consensus_buy(engine):
    """High z_entry blocks a consensus BUY that core.config defaults would open."""
    # z_wdo=-1.6, z_di=-1.6 would trigger BUY under Z_ENTRY=1.4 default but not
    # under z_entry=2.5.
    result = engine.evaluate(
        z_wdo=-1.6, z_di=-1.6,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=_engine_params(z_entry=2.5, z_attention=2.0),
    )
    assert result["strategies"]["CONS_BASE"]["open_trade"] is None

    # Now relax — z_entry=1.5, z_attention=1.4 → triggers.
    result2 = engine.evaluate(
        z_wdo=-1.6, z_di=-1.6,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=_engine_params(z_entry=1.5, z_attention=1.4),
    )
    assert result2["strategies"]["CONS_BASE"]["open_trade"] is not None
    assert result2["strategies"]["CONS_BASE"]["open_trade"]["direction"] == "BUY"


def test_engine_params_z_entry_gates_wdo_nwe(engine):
    """WDO_NWE uses z_entry from engine_params (no consensus needed)."""
    # |z_wdo|=1.6 < 2.5: should not fire.
    result = engine.evaluate(
        z_wdo=-1.6, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        nwe_is_up=False, nwe_upper=130100, nwe_lower=129000,
        engine_params=_engine_params(z_entry=2.5),
    )
    assert result["strategies"]["WDO_NWE"]["open_trade"] is None


def test_engine_params_z_entry_recorded_on_timeline_threshold(engine):
    """Timeline SIGNAL event uses z_entry from engine_params, not Z_ENTRY global."""
    custom_threshold = 1.85
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.9,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
        engine_params=_engine_params(z_entry=custom_threshold, z_attention=1.8),
    )
    signal_events = [
        r for r in _timeline_rows(engine)
        if r["phase"] == "SIGNAL" and r["strategy"] == "CONS_BASE"
    ]
    assert signal_events, "expected a SIGNAL event"
    assert signal_events[0]["threshold"] == custom_threshold


def test_engine_params_z_entry_none_falls_back_to_global(engine):
    """No engine_params: _eval_* and _open_trade use core.config Z_ENTRY/Z_ATTENTION."""
    # |z|=1.6 > Z_ENTRY=1.4 default → triggers under fallback.
    result = engine.evaluate(
        z_wdo=-1.6, z_di=-1.6,
        win_price=130000, wdo_price=5800,
        rho=-0.75, gate=_gate(), hmm_state="CHOP",
        hour=11, minute=0,
    )
    assert result["strategies"]["CONS_BASE"]["open_trade"] is not None
    signal_events = [
        r for r in _timeline_rows(engine)
        if r["phase"] == "SIGNAL" and r["strategy"] == "CONS_BASE"
    ]
    assert signal_events[0]["threshold"] == Z_ENTRY
