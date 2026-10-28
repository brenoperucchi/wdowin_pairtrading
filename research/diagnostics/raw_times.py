import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

from core.config import SYMBOL_A, SYMBOL_B, TIMEFRAME, MT5_PATH

mt5.initialize(path=MT5_PATH)
rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 100)
mt5.shutdown()

times = [datetime.fromtimestamp(r[0]) for r in rw]
win = [r[4] for r in rw]

df = pd.DataFrame({'time': times, 'win': win})
print(df[df['time'].astype(str).str.contains("2026-04-30")].to_string())
