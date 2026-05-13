import sys
import types

# MetaTrader5 only works on Windows. Stub it so tests run on Linux/CI.
if "MetaTrader5" not in sys.modules:
    _mt5 = types.ModuleType("MetaTrader5")

    # Timeframe constants
    _mt5.TIMEFRAME_M1 = 1
    _mt5.TIMEFRAME_M5 = 5
    _mt5.TIMEFRAME_M15 = 15
    _mt5.TIMEFRAME_M30 = 30
    _mt5.TIMEFRAME_H1 = 60
    _mt5.TIMEFRAME_H4 = 240

    # Order / trade action constants (TASK-2 slice 1)
    _mt5.TRADE_ACTION_DEAL = 1
    _mt5.ORDER_TYPE_BUY = 0
    _mt5.ORDER_TYPE_SELL = 1
    _mt5.ORDER_FILLING_RETURN = 2
    _mt5.ORDER_TIME_GTC = 1
    _mt5.POSITION_TYPE_BUY = 0
    _mt5.POSITION_TYPE_SELL = 1
    _mt5.TRADE_RETCODE_DONE = 10009

    # Stub functions — tests monkeypatch these; the attribute must pre-exist.
    _mt5.order_send = lambda req: None
    _mt5.positions_get = lambda **kw: []
    _mt5.last_error = lambda: (0, "")
    _mt5.copy_rates_from_pos = lambda symbol, timeframe, pos, count: None
    _mt5.copy_rates_range = lambda symbol, timeframe, dt_start, dt_end: None

    sys.modules["MetaTrader5"] = _mt5
