"""Pytest configuration and lightweight stubs for Linux CI without MetaTrader5."""

from __future__ import annotations

import sys
import types


def _install_mt5_stub_if_missing() -> None:
    """Inject a minimal MetaTrader5 stub only when MetaTrader5 cannot be imported."""
    try:
        import MetaTrader5  # noqa: F401
        return
    except ImportError:
        pass

    mt5 = types.ModuleType("MetaTrader5")
    mt5.TIMEFRAME_M1 = 1
    mt5.TIMEFRAME_M2 = 2
    mt5.TIMEFRAME_M3 = 3
    mt5.TIMEFRAME_M4 = 4
    mt5.TIMEFRAME_M5 = 5
    mt5.TIMEFRAME_M6 = 6
    mt5.TIMEFRAME_M10 = 10
    mt5.TIMEFRAME_M12 = 12
    mt5.TIMEFRAME_M15 = 15
    mt5.TIMEFRAME_M20 = 20
    mt5.TIMEFRAME_M30 = 30
    mt5.TIMEFRAME_H1 = 16385
    mt5.TIMEFRAME_H2 = 16386
    mt5.TIMEFRAME_H3 = 16387
    mt5.TIMEFRAME_H4 = 16388
    mt5.TIMEFRAME_H6 = 16390
    mt5.TIMEFRAME_H8 = 16392
    mt5.TIMEFRAME_H12 = 16396
    mt5.TIMEFRAME_D1 = 16408
    mt5.TIMEFRAME_W1 = 32769
    mt5.TIMEFRAME_MN1 = 49153

    mt5.COPY_TICKS_ALL = -1
    mt5.COPY_TICKS_INFO = 1
    mt5.COPY_TICKS_TRADE = 2
    mt5.TICK_FLAG_BID = 2
    mt5.TICK_FLAG_ASK = 4
    mt5.TICK_FLAG_LAST = 8
    mt5.TICK_FLAG_VOLUME = 16
    mt5.TICK_FLAG_BUY = 32
    mt5.TICK_FLAG_SELL = 64

    mt5.initialize = lambda *args, **kwargs: False
    mt5.shutdown = lambda: None
    mt5.terminal_info = lambda: None
    mt5.last_error = lambda: (-1, "MetaTrader5 stub (CI)")
    mt5.symbol_select = lambda *args, **kwargs: False
    mt5.symbols_get = lambda *args, **kwargs: ()
    mt5.copy_rates_from_pos = lambda *args, **kwargs: None
    mt5.copy_rates_range = lambda *args, **kwargs: None
    mt5.copy_ticks_from = lambda *args, **kwargs: None

    sys.modules["MetaTrader5"] = mt5


_install_mt5_stub_if_missing()
