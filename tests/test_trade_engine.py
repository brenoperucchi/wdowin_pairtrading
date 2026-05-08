import sqlite3
import json
from datetime import datetime, timedelta
import pytest
import core.trade_engine as te
from core.execution_timeline import load_timeline
from core.trade_engine import TradeEngine
from core.config import (
    BUY_SL, BUY_TP, SELL_TP,
    FORCE_CLOSE_H, FORCE_CLOSE_M,
)


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


def test_timeline_does_not_emit_skipped_signal_on_blocked_poll(engine):
    for _ in range(3):
        engine.evaluate(
            z_wdo=-2.5, z_di=-2.5,
            win_price=130000, wdo_price=5800,
            rho=-0.75, gate=_gate(allowed=False, reasons=["EG_NOT_COINTEGRATED"]),
            hmm_state="CHOP", hour=11, minute=0,
        )

    assert _timeline_rows(engine) == []
