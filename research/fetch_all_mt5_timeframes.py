import os
import datetime as dt
import MetaTrader5 as mt5
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RATES_DIR = os.path.join(ROOT_DIR, "data", "mt5_rates")
os.makedirs(RATES_DIR, exist_ok=True)

term_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
if mt5.initialize(term_path, timeout=15000):
    d_from = dt.datetime(2025, 12, 15, 0, 0, 0)
    d_to = dt.datetime(2026, 11, 7, 23, 59, 59)
    
    symbols = ["WIN" + chr(36) + "N", "WDO" + chr(36) + "N"]
    tfs = [
        ("M1", mt5.TIMEFRAME_M1),
        ("M2", mt5.TIMEFRAME_M2),
        ("M5", mt5.TIMEFRAME_M5),
        ("M15", mt5.TIMEFRAME_M15),
    ]
    
    for sym in symbols:
        clean_sym = sym.replace("$", "_")
        mt5.symbol_select(sym, True)
        for tf_name, tf_code in tfs:
            out_file = os.path.join(RATES_DIR, f"mt5_{clean_sym}_{tf_name}.csv")
            print(f"Fetching {sym} {tf_name} ...")
            chunks = []
            cur = d_from
            while cur < d_to:
                nxt = min(cur + dt.timedelta(days=60), d_to)
                r = mt5.copy_rates_range(sym, tf_code, cur, nxt)
                if r is not None and len(r) > 0:
                    chunks.append(pd.DataFrame(r))
                cur = nxt
            if chunks:
                df = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
                df["t"] = pd.to_datetime(df["time"], unit="s")
                df = df[df["t"] >= "2025-12-15"].copy()
                df = df[["t", "open", "high", "low", "close", "tick_volume", "real_volume"]]
                df.to_csv(out_file, index=False)
                print(f"  OK {out_file}: {len(df)} bars ({df['t'].iloc[0]} -> {df['t'].iloc[-1]})")
            else:
                print(f"  FAIL {sym} {tf_name}: {mt5.last_error()}")
    mt5.shutdown()
    print("ALL DONE!")
else:
    print("MT5 Init Failed:", mt5.last_error())
