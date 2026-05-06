import sqlite3
import os
from datetime import datetime, timedelta
import pytest
from core.trade_engine import TradeEngine
from core.config import BUY_SL, BUY_TP, SELL_SL, SELL_TP, Z_ENTRY, Z_ANOMALY, Z_ATTENTION


@pytest.fixture
def engine(tmp_path):
    db_path = str(tmp_path / "test_trades.db")
    return TradeEngine(db_path=db_path)


# ── Entry conditions ─────────────────────────────────────────────────────────

def test_no_entry_below_threshold(engine):
    """Z-scores below all thresholds should NOT open a trade."""
    result = engine.evaluate(
        z_wdo=1.3, z_di=1.1,       # both below Z_ENTRY=1.4 and Z_ATTENTION=1.2
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "WAIT"
    assert result["holding"] is False


def test_buy_entry_consensus(engine):
    """Both z-scores confirming buy (CONS_BASE) should open BUY WIN."""
    result = engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,     # z_wdo <= -Z_ENTRY and z_di <= -Z_ATTENTION
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
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
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "SELL_WIN"
    assert result["strategies"]["CONS_BASE"]["open_trade"]["direction"] == "SELL"


def test_beta_unsafe_blocks_entry(engine):
    """beta_safe=False should block all new entries."""
    result = engine.evaluate(
        z_wdo=-2.5, z_di=-2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=False, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "WAIT"


def test_anomaly_blocks_entry(engine):
    """|z| >= Z_ANOMALY should return ANOMALY — no trade."""
    result = engine.evaluate(
        z_wdo=-4.5, z_di=4.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "ANOMALY"


def test_outside_session_no_entry(engine):
    """Before ENTRY_START_H:ENTRY_START_M (9:00) should not open."""
    result = engine.evaluate(
        z_wdo=-2.5, z_di=-2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=8, minute=59        # 1 minute before session opens at 9:00
    )
    assert result["action"] == "WAIT"


# ── Exit conditions ──────────────────────────────────────────────────────────

def test_stop_loss_buy(engine):
    """BUY trade should close on SL when price drops BUY_SL points."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    result = engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "STOP_LOSS"


def test_take_profit_sell(engine):
    """SELL trade should close on TP when price drops SELL_TP points."""
    engine.evaluate(
        z_wdo=2.1, z_di=1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    result = engine.evaluate(
        z_wdo=0.5, z_di=0.5,
        win_price=130000 - SELL_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"


def test_breakeven_activation_buy(engine):
    """BUY trade should activate BE after BUY_BE_ACT pts, then close at BUY_BE_LOCK."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    # Price rises enough to activate BE
    result = engine.evaluate(
        z_wdo=-1.0, z_di=-0.5,
        win_price=130000 + 400, wdo_price=5800,   # 400 >= BUY_BE_ACT=300
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "HOLDING"

    # Price retraces to BUY_BE_LOCK (0 pts = entry price)
    result = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=130000, wdo_price=5800,          # pts_favor=0 <= BUY_BE_LOCK=0
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=10
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "BE_STOP"


def test_performance_report(engine):
    """Performance report should reflect closed trades."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
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
    """Should return both OPEN and CLOSED trades for the requested date."""
    # Open a trade (OPEN)
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    today = datetime.now().strftime("%Y-%m-%d")
    trades = engine.get_trades_for_date(today)
    assert len(trades) == 1
    assert trades[0]["status"] == "OPEN"

    # Close the trade (TARGET)
    engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    trades = engine.get_trades_for_date(today)
    assert len(trades) == 1
    assert trades[0]["status"] == "CLOSED"


def test_get_trades_for_date_filtra_outra_data(engine):
    """Should NOT return trades from a different date."""
    engine.evaluate(
        z_wdo=-2.1, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
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
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
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
