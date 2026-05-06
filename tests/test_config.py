from core.config import (
    Z_ENTRY, BUY_SL, BUY_TP, SELL_SL, SELL_TP,
    BUY_BE_ACT, BUY_BE_LOCK, SELL_BE_ACT, SELL_BE_LOCK,
    WIN_CONTRACTS, WIN_PV, SYMBOL_A, SYMBOL_B,
)


def test_setup_matador_params():
    """Verify the validated backtest params are correctly configured (Setup Matador v4)."""
    assert Z_ENTRY == 1.4
    assert BUY_SL == 300
    assert BUY_TP == 800
    assert SELL_SL == 300
    assert SELL_TP == 800


def test_be_params():
    assert BUY_BE_ACT == 300
    assert BUY_BE_LOCK == 0
    assert SELL_BE_ACT == 300
    assert SELL_BE_LOCK == 0


def test_sizing():
    assert WIN_CONTRACTS == 2
    assert WIN_PV == 0.20
