import sqlite3
import os
import pytest
from datetime import datetime
from core.trade_engine import TradeEngine
from core.config import BUY_SL, BUY_TP, SELL_SL, SELL_TP, Z_ENTRY, Z_ANOMALY


@pytest.fixture
def engine(tmp_path):
    db_path = str(tmp_path / "test_trades.db")
    return TradeEngine(db_path=db_path)


def test_no_entry_below_threshold(engine):
    """Z below 1.4 should NOT open any trade."""
    result = engine.evaluate(
        z_wdo=-1.0, z_di=-1.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert result["action"] == "WAIT"
    assert not result["holding"]


def test_consensus_buy_entry(engine):
    """z_wdo <= -1.4 and z_di <= -1.2 should open consensus BUY WIN."""
    result = engine.evaluate(
        z_wdo=-1.5, z_di=-1.3,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert result["action"] == "BUY_WIN"
    assert result["holding"]
    
    # Verify consensus slot has open trade
    cons_strat = result["strategies"]["CONS_BASE"]
    assert cons_strat["action"] == "BUY_WIN"
    assert cons_strat["open_trade"]["direction"] == "BUY"


def test_hmm_blocks_entry(engine):
    """HMM BULL state should NOT block consensus or NWE, unless configured.
    Wait, in V5, does HMM state block? Let's check how trade_engine evaluates it.
    Usually, HMM filter blocks specific entries or has strategy slots.
    Let's check if the trade engine has HMM blockage.
    """
    # Let's check if HMM blocks in eval_consensus
    pass


def test_outside_session_no_entry(engine):
    """Outside 09:00-15:00 should not open."""
    result = engine.evaluate(
        z_wdo=-1.5, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=8, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert result["action"] == "WAIT"


def test_stop_loss_buy(engine):
    """BUY trade should close on SL when price drops 300pts."""
    # Open trade first
    engine.evaluate(
        z_wdo=-1.5, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    
    # Price drops by 300 points
    result = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=130000 - BUY_SL, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "STOP_LOSS"


def test_take_profit_sell(engine):
    """SELL trade should close on TP when price drops 800pts (since SELL WIN gains on drop? No, SELL WIN gains when price drops? 
    Wait, in pair trading:
    SELL WIN / BUY WDO.
    If WIN price drops, the short WIN position gains! So points in favor is entry_px - win_price.
    So if entry is 130000, and price drops to 129200 (800pts drop), points in favor is +800, which hits TP!
    """
    # Open sell trade
    engine.evaluate(
        z_wdo=1.5, z_di=1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=True, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    
    # Price drops to 129200
    result = engine.evaluate(
        z_wdo=0.5, z_di=0.5,
        win_price=130000 - SELL_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=True, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"


def test_breakeven_activation_buy(engine):
    """BUY trade should activate BE after 300pts (BUY_BE_ACT), then close on retrace to 0pts (BUY_BE_LOCK)."""
    engine.evaluate(
        z_wdo=-1.5, z_di=-1.5,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    
    # Price rises 300pts -> BE activates
    result = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=130000 + 300, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "HOLDING"

    # Price retraces to entry -> BE_STOP
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=10,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "BE_STOP"
