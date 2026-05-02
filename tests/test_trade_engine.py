import sqlite3
import os
import pytest
from core.trade_engine import TradeEngine
from core.config import BUY_SL, BUY_TP, SELL_SL, SELL_TP, Z_ENTRY, Z_ANOMALY


@pytest.fixture
def engine(tmp_path):
    db_path = str(tmp_path / "test_trades.db")
    return TradeEngine(db_path=db_path)


def test_no_entry_below_threshold(engine):
    """Z below 1.8 should NOT open a trade."""
    result = engine.evaluate(
        z_buy=1.5, z_sell=1.2,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "WAIT"
    assert result["open_trade"] is None


def test_buy_entry_on_kalman(engine):
    """z_buy (Kalman) <= -1.8 should open BUY WIN."""
    result = engine.evaluate(
        z_buy=-2.1, z_sell=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "BUY_WIN"
    assert result["open_trade"] is not None
    assert result["open_trade"]["direction"] == "BUY"


def test_sell_entry_on_ols(engine):
    """z_sell (OLS) >= 1.8 should open SELL WIN."""
    result = engine.evaluate(
        z_buy=1.5, z_sell=2.1,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "SELL_WIN"
    assert result["open_trade"]["direction"] == "SELL"


def test_hmm_bull_blocks_entry(engine):
    """HMM BULL state should block all entries."""
    result = engine.evaluate(
        z_buy=-2.5, z_sell=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="BULL",
        hour=11, minute=0
    )
    assert result["action"] == "HMM_BLOCKED"


def test_anomaly_blocks_entry(engine):
    """Z >= 4.0 should be anomaly — no trade."""
    result = engine.evaluate(
        z_buy=-4.5, z_sell=4.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    assert result["action"] == "ANOMALY"


def test_outside_session_no_entry(engine):
    """Outside 10:00-16:00 should not open."""
    result = engine.evaluate(
        z_buy=-2.5, z_sell=2.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=9, minute=0
    )
    assert result["action"] == "WAIT"


def test_stop_loss_buy(engine):
    """BUY trade should close on SL when price drops 350pts."""
    engine.evaluate(
        z_buy=-2.1, z_sell=0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    result = engine.evaluate(
        z_buy=-1.0, z_sell=0,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "STOP_LOSS"


def test_take_profit_sell(engine):
    """SELL trade should close on TP when price drops 1400pts."""
    engine.evaluate(
        z_buy=0, z_sell=2.1,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    result = engine.evaluate(
        z_buy=0, z_sell=0.5,
        win_price=130000 - SELL_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"


def test_breakeven_activation_buy(engine):
    """BUY trade should activate BE after 400pts, then close on retrace to 50pts."""
    engine.evaluate(
        z_buy=-2.1, z_sell=0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    # Price rises 400pts → BE activates
    result = engine.evaluate(
        z_buy=-1.0, z_sell=0,
        win_price=130000 + 400, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    assert result["action"] == "HOLDING"

    # Price retraces to entry + 50pts → BE_STOP
    result = engine.evaluate(
        z_buy=-0.5, z_sell=0,
        win_price=130000 + 50, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=10
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "BE_STOP"


def test_performance_report(engine):
    """Performance report should reflect closed trades."""
    # Open and close a winning trade
    engine.evaluate(
        z_buy=-2.1, z_sell=0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0
    )
    engine.evaluate(
        z_buy=0, z_sell=0,
        win_price=130000 + BUY_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5
    )
    perf = engine.get_performance()
    assert perf["total_closed_trades"] == 1
    assert perf["wins"] == 1
    assert perf["accumulated_pnl"] > 0
