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


def test_nwe_band_filter_and_broker_flow_and_time_align(engine, tmp_path):
    """Test WDO_NWE band filter, broker flow institutional preservation, and bar timestamp alignment."""
    import numpy as np
    from core.mt5_client import align_series_by_time
    from core.profit_mt5_flow_engine import ProfitMt5FlowEngine

    # 1. WDO_NWE requires price inside 10% NWE band tolerance
    # When price is at the center (130000), WDO_NWE should WAIT while CONS_BASE opens
    res_mid = engine.evaluate(
        z_wdo=-1.5, z_di=-1.3,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert res_mid["strategies"]["CONS_BASE"]["action"] == "BUY_WIN"
    assert res_mid["strategies"]["WDO_NWE"]["action"] == "WAIT"

    # When price touches lower NWE band (129520 <= 129500 + 100), WDO_NWE opens BUY_WIN
    res_band = engine.evaluate(
        z_wdo=-1.5, z_di=0.0,
        win_price=129520, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert res_band["strategies"]["WDO_NWE"]["action"] == "BUY_WIN"

    # 2. Verify align_series_by_time aligns timestamps with gaps accurately
    closes_a = np.array([100.0, 101.0, 102.0, 103.0])
    times_a = np.array([1000, 1300, 1600, 1900])
    closes_b = np.array([50.0, 52.0, 53.0])
    times_b = np.array([1000, 1600, 1900])  # missing 1300 bar
    ca, cb, ct = align_series_by_time(closes_a, times_a, closes_b, times_b)
    assert list(ct) == [1000, 1600, 1900]
    assert list(ca) == [100.0, 102.0, 103.0]
    assert list(cb) == [50.0, 52.0, 53.0]

    # 3. Verify _parse_profit_broker_balance_file preserves aggr_buy and is_institutional
    flow_eng = ProfitMt5FlowEngine()
    state = flow_eng.win_state
    state.brokers["UBS"].update({
        "aggr_buy": 450,
        "aggr_sell": 120,
        "passive_buy": 50,
        "passive_sell": 30,
        "net": 350,
        "avg": 129800.0,
        "is_institutional": True,
    })
    csv_file = tmp_path / "WIN_saldo.csv"
    csv_file.write_text("Corretora;Saldo;Preco Medio\nUBS;500;129900,0\n", encoding="latin1")
    flow_eng._parse_profit_broker_balance_file(str(csv_file), state)
    assert state.brokers["UBS"]["net"] == 500
    assert state.brokers["UBS"]["aggr_buy"] == 450
    assert state.brokers["UBS"]["is_institutional"] is True


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
