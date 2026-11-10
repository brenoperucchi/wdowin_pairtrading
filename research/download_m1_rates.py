import os
import datetime as dt
import MetaTrader5 as mt5
import pandas as pd

term_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
if mt5.initialize(term_path, timeout=15000):
    d_from = dt.datetime(2026, 4, 1, 0, 0, 0)
    d_to = dt.datetime(2026, 11, 6, 23, 59, 59)
    for sym_name, fname in [("WIN$N", "mt5_WIN_N_M1.csv"), ("WDO$N", "mt5_WDO_N_M1.csv")]:
        target = os.path.join("data", "mt5_rates", fname)
        print("Checking", sym_name, "...")
        mt5.symbol_select(sym_name, True)
        rates = mt5.copy_rates_range(sym_name, mt5.TIMEFRAME_M1, d_from, d_to)
        if rates is not None and len(rates):
            df = pd.DataFrame(rates)
            df["t"] = pd.to_datetime(df["time"], unit="s")
            df = df[["t", "open", "high", "low", "close", "tick_volume", "real_volume"]]
            df.to_csv(target, index=False)
            t_start = df["t"].iloc[0]
            t_end = df["t"].iloc[-1]
            print(f"  Saved {target}: {len(df)} bars ({t_start} to {t_end})")
        else:
            print(f"  Failed to fetch {sym_name}: {mt5.last_error()}")
    mt5.shutdown()
else:
    print("Failed to initialize MT5:", mt5.last_error())
