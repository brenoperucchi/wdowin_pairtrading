from core.config import (
    Z_ENTRY, BUY_SL, BUY_TP, SELL_SL, SELL_TP,
    BUY_BE_ACT, BUY_BE_LOCK, SELL_BE_ACT, SELL_BE_LOCK,
    WIN_CONTRACTS, WIN_PV, SYMBOL_A, SYMBOL_B,
)


def test_setup_matador_params():
    """Verify the validated backtest params are correctly configured."""
    assert Z_ENTRY == 1.8
    assert BUY_SL == 350
    assert BUY_TP == 500
    assert SELL_SL == 300
    assert SELL_TP == 1400


def test_be_params():
    assert BUY_BE_ACT == 400
    assert BUY_BE_LOCK == 50
    assert SELL_BE_ACT == 800
    assert SELL_BE_LOCK == 200


def test_sizing():
    assert WIN_CONTRACTS == 2
    assert WIN_PV == 0.20
