import requests
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime

from core.config import SYMBOL_A, SYMBOL_B, TIMEFRAME, MT5_PATH

def get_backtest_data():
    mt5.initialize(path=MT5_PATH)
    rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 250)
    rd = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 250)
    mt5.shutdown()
    
    times = [datetime.fromtimestamp(r[0]) for r in rw]
    win = [r[4] for r in rw]
    wdo = [r[4] for r in rd]
    
    df = pd.DataFrame({
        'time': times,
        'win_bt': win,
        'wdo_bt': wdo
    })
    return df

def get_live_data():
    r = requests.get('http://localhost:8080/api/history?days=2')
    data = r.json().get("history", [])
    df = pd.DataFrame(data)
    if not df.empty:
        df['time'] = pd.to_datetime(df['datetime'])
    return df

if __name__ == "__main__":
    df_bt = get_backtest_data()
    df_live = get_live_data()
    
    if not df_live.empty:
        df_merge = pd.merge(df_live, df_bt, on='time', how='inner')
        df_target = df_merge[df_merge['datetime'].str.contains("2026-04-30 14:")]
        print("\nCOMPARAÇÃO PRICES (30 de Abril, 14:00 - 14:55):")
        print(df_target[['datetime', 'win_price', 'win_bt', 'wdo_bt', 'z']].to_string(index=False))
