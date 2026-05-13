import importlib

import pytest

import core.config as cfg
from core.config import (
    Z_ENTRY, BUY_SL, BUY_TP, SELL_SL, SELL_TP,
    BUY_BE_ACT, BUY_BE_LOCK, SELL_BE_ACT, SELL_BE_LOCK,
    WIN_CONTRACTS, WIN_PV, SYMBOL_A, SYMBOL_B, _env_bool, _env_str,
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


def test_live_orders_env_flag(monkeypatch):
    monkeypatch.delenv("LIVE_ORDERS", raising=False)
    assert _env_bool("LIVE_ORDERS", False) is False
    monkeypatch.setenv("LIVE_ORDERS", "1")
    assert _env_bool("LIVE_ORDERS", False) is True
    monkeypatch.setenv("LIVE_ORDERS", "false")
    assert _env_bool("LIVE_ORDERS", True) is False


def test_env_str_uses_default_for_blank_values(monkeypatch):
    monkeypatch.delenv("MT5_PATH", raising=False)
    assert _env_str("MT5_PATH", "fallback") == "fallback"
    monkeypatch.setenv("MT5_PATH", "  ")
    assert _env_str("MT5_PATH", "fallback") == "fallback"
    monkeypatch.setenv("MT5_PATH", "E:\\MetaTraders\\XP\\terminal64.exe")
    assert _env_str("MT5_PATH", "fallback") == "E:\\MetaTraders\\XP\\terminal64.exe"


def test_live_symbol_env_override(monkeypatch):
    try:
        monkeypatch.setenv("LIVE_ORDERS", "0")
        monkeypatch.setenv("LIVE_SYMBOL_WIN", "WINM26")
        reloaded = importlib.reload(cfg)
        assert reloaded.LIVE_SYMBOL_WIN == "WINM26"
    finally:
        monkeypatch.delenv("LIVE_ORDERS", raising=False)
        monkeypatch.delenv("LIVE_SYMBOL_WIN", raising=False)
        importlib.reload(cfg)


def test_live_symbol_defaults_to_auto(monkeypatch):
    try:
        monkeypatch.delenv("LIVE_SYMBOL_WIN", raising=False)
        reloaded = importlib.reload(cfg)
        assert reloaded.LIVE_SYMBOL_WIN == "AUTO"
    finally:
        importlib.reload(cfg)


def test_live_orders_refuses_continuous_symbol_without_explicit_override(monkeypatch):
    try:
        monkeypatch.setenv("LIVE_ORDERS", "1")
        monkeypatch.setenv("LIVE_SYMBOL_WIN", "WIN$N")
        monkeypatch.delenv("ALLOW_CONTINUOUS_LIVE_SYMBOL", raising=False)
        with pytest.raises(ValueError, match="continuous LIVE_SYMBOL_WIN"):
            importlib.reload(cfg)
    finally:
        monkeypatch.setenv("LIVE_ORDERS", "0")
        monkeypatch.delenv("LIVE_SYMBOL_WIN", raising=False)
        monkeypatch.delenv("ALLOW_CONTINUOUS_LIVE_SYMBOL", raising=False)
        importlib.reload(cfg)
