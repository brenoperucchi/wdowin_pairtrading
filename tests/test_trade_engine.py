import sqlite3
import os
import pytest
from datetime import datetime
from core.trade_engine import TradeEngine
from core.config import (
    BUY_BE_ACT, BUY_BE_LOCK, BUY_SL, BUY_TP,
    CONS_WDO_ENTRY, CONS_Z_ATTENTION,
    SELL_SL, SELL_TP, WALL_MIN_PTS, Z_ENTRY, Z_ANOMALY,
)


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
    """z_wdo <= -CONS_WDO_ENTRY (-1.8) and z_di <= -CONS_Z_ATTENTION (-1.2) inside NWE lower band opens CONS_BASE BUY WIN."""
    # Below CONS_WDO_ENTRY (1.8) must remain WAIT even inside CONS_BASE 15% NWE band
    below_res = engine.evaluate(
        z_wdo=-1.5, z_di=-1.3,
        win_price=129620, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert below_res["strategies"]["CONS_BASE"]["action"] == "WAIT"
    assert below_res["strategies"]["WDO_NWE"]["action"] == "WAIT"

    # Meeting CONS_WDO_ENTRY (-1.9 <= -1.8) + attention (-1.3 <= -1.2) inside 15% NWE tolerance (<= 129650) opens CONS_BASE
    result = engine.evaluate(
        z_wdo=-1.9, z_di=-1.3,
        win_price=129620, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert result["action"] == "BUY_WIN"
    assert result["holding"]

    # Verify consensus slot has open trade while WDO_NWE (> 10% NWE tolerance 129600) stayed WAIT
    cons_strat = result["strategies"]["CONS_BASE"]
    assert cons_strat["action"] == "BUY_WIN"
    assert cons_strat["open_trade"]["direction"] == "BUY"
    assert cons_strat["open_trade"]["z_source"] == "CONSENSO"
    assert result["strategies"]["WDO_NWE"]["action"] == "WAIT"


def test_nwe_band_filter_and_broker_flow_and_time_align(engine, tmp_path):
    """Test CONS_BASE (15% NWE) & WDO_NWE (10% NWE) band filters, broker flow preservation, and bar time alignment."""
    import numpy as np
    from core.mt5_client import align_series_by_time
    from core.profit_mt5_flow_engine import ProfitMt5FlowEngine

    # 1a. At center of NWE band (130000), CONS_USE_NWE=True blocks CONS_BASE and WDO_NWE
    res_center = engine.evaluate(
        z_wdo=-1.9, z_di=-1.3,
        win_price=130000, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert res_center["strategies"]["CONS_BASE"]["action"] == "WAIT"
    assert res_center["strategies"]["WDO_NWE"]["action"] == "WAIT"

    # 1b. Between 10% (129600) and 15% (129650) of lower NWE band, CONS_BASE opens while WDO_NWE stays WAIT
    res_mid = engine.evaluate(
        z_wdo=-1.9, z_di=-1.3,
        win_price=129620, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert res_mid["strategies"]["CONS_BASE"]["action"] == "BUY_WIN"
    assert res_mid["strategies"]["WDO_NWE"]["action"] == "WAIT"

    # 1c. When price touches lower NWE band (129520 <= 129500 + 100), WDO_NWE opens BUY_WIN
    res_band = engine.evaluate(
        z_wdo=-1.5, z_di=0.0,
        win_price=129520, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=10,
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
        z_wdo=-1.9, z_di=-1.5,
        win_price=129550, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=8, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert result["action"] == "WAIT"


def test_stop_loss_buy(engine):
    """BUY trade without GEX walls uses fallback SL (WALL_MIN_PTS=200) and closes on STOP_LOSS."""
    entry_px = 129550
    open_res = engine.evaluate(
        z_wdo=-1.9, z_di=-1.3,
        win_price=entry_px, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert open_res["action"] == "BUY_WIN"
    sl_pts = open_res["strategies"]["CONS_BASE"]["open_trade"]["sl_pts"]
    assert sl_pts == WALL_MIN_PTS

    # Just above SL -> still HOLDING
    hold_res = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=entry_px - (sl_pts - 5), wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=2,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert hold_res["action"] == "HOLDING"

    # Price drops to SL (200 pts) -> STOP_LOSS
    result = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=entry_px - sl_pts, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "STOP_LOSS"
    assert result["pnl"] == -80.0


def test_take_profit_sell(engine):
    """SELL trade with GEX walls sets wall-based TP (800 pts) and closes on TARGET."""
    entry_px = 130450
    walls = [129640, 130720]  # SL behind 130720 + 30 = 300 pts; TP before 129640 + 10 = 800 pts
    open_res = engine.evaluate(
        z_wdo=1.9, z_di=1.3,
        win_price=entry_px, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=True, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True,
        walls=walls,
    )
    assert open_res["action"] == "SELL_WIN"
    assert open_res["strategies"]["CONS_BASE"]["open_trade"]["tp_pts"] == SELL_TP
    assert open_res["strategies"]["CONS_BASE"]["open_trade"]["sl_pts"] == SELL_SL

    # Halfway to TP -> still HOLDING (z stays >= 0.5 so mean-reversion exit does not trigger)
    hold_res = engine.evaluate(
        z_wdo=0.5, z_di=0.5,
        win_price=entry_px - 400, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=2,
        beta_value=-22.5,
        nwe_is_up=True, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False,
        walls=walls,
    )
    assert hold_res["action"] == "HOLDING"

    # Price drops to 129650 (800 pts in favor) -> TARGET
    result = engine.evaluate(
        z_wdo=0.5, z_di=0.5,
        win_price=entry_px - SELL_TP, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=True, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False,
        walls=walls,
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "TARGET"
    assert result["pnl"] == 320.0


def test_breakeven_activation_buy(engine):
    """BUY trade activates BE after BUY_BE_ACT (150 pts), holds above BUY_BE_LOCK (15 pts), and closes at +15 pts."""
    entry_px = 129550
    open_res = engine.evaluate(
        z_wdo=-1.9, z_di=-1.3,
        win_price=entry_px, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=0,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=True
    )
    assert open_res["action"] == "BUY_WIN"

    # Price rises by BUY_BE_ACT (150 pts) -> BE activates, stays HOLDING
    result = engine.evaluate(
        z_wdo=-0.5, z_di=-0.5,
        win_price=entry_px + BUY_BE_ACT, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=5,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "HOLDING"

    # Price retraces to +20 pts (above BUY_BE_LOCK=15) -> still HOLDING
    hold_res = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=entry_px + BUY_BE_LOCK + 5, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=8,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert hold_res["action"] == "HOLDING"

    # Price retraces to BUY_BE_LOCK (+15 pts) -> BE_STOP
    result = engine.evaluate(
        z_wdo=0.0, z_di=0.0,
        win_price=entry_px + BUY_BE_LOCK, wdo_price=5800,
        rho=-0.75, beta_safe=True, hmm_state="CHOP",
        hour=11, minute=10,
        beta_value=-22.5,
        nwe_is_up=False, nwe_upper=130500, nwe_lower=129500,
        bar_close_confirmed=False
    )
    assert result["action"] == "CLOSE"
    assert result["exit_reason"] == "BE_STOP"
    assert result["pnl"] == 6.0
