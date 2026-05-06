import sys
import types

# MetaTrader5 only works on Windows. Stub it so tests run on Linux/CI.
if "MetaTrader5" not in sys.modules:
    _mt5 = types.ModuleType("MetaTrader5")
    _mt5.TIMEFRAME_M1 = 1
    _mt5.TIMEFRAME_M5 = 5
    _mt5.TIMEFRAME_M15 = 15
    _mt5.TIMEFRAME_M30 = 30
    _mt5.TIMEFRAME_H1 = 60
    _mt5.TIMEFRAME_H4 = 240
    sys.modules["MetaTrader5"] = _mt5
