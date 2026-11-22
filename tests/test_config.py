from core.config import (
    Z_ENTRY, BUY_SL, BUY_TP, SELL_SL, SELL_TP,
    BUY_BE_ACT, BUY_BE_LOCK, SELL_BE_ACT, SELL_BE_LOCK,
    CONS_WDO_ENTRY, CONS_DI_ENTRY, CONS_Z_ATTENTION, CONS_USE_NWE,
    WALL_MIN_PTS, WALL_SL_BUFFER, WALL_TP_BUFFER, WALL_MAX_SL, WALL_MIN_RR,
    COOLDOWN_BARS,
    WIN_CONTRACTS, WIN_PV, SYMBOL_A, SYMBOL_B,
)


def test_setup_matador_params():
    """Verify the validated backtest params are correctly configured."""
    assert Z_ENTRY == 1.4
    assert BUY_SL == 300
    assert BUY_TP == 800
    assert SELL_SL == 300
    assert SELL_TP == 800


def test_be_params():
    assert BUY_BE_ACT == 150
    assert BUY_BE_LOCK == 15
    assert SELL_BE_ACT == 150
    assert SELL_BE_LOCK == 15


def test_consensus_and_wall_params():
    assert CONS_WDO_ENTRY == 1.8
    assert CONS_DI_ENTRY == 2.2
    assert CONS_Z_ATTENTION == 1.2
    assert CONS_USE_NWE is True
    assert WALL_MIN_PTS == 200.0
    assert WALL_SL_BUFFER == 30.0
    assert WALL_TP_BUFFER == 10.0
    assert WALL_MAX_SL == 300.0
    assert WALL_MIN_RR == 1.4
    assert COOLDOWN_BARS == 4


def test_sizing():
    assert SYMBOL_A == "WIN$N"
    assert SYMBOL_B == "WDO$N"
    assert WIN_CONTRACTS == 2
    assert WIN_PV == 0.20
