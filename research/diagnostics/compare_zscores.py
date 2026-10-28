import requests
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime

# Download backtest data logic to compare directly
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH
from core.kalman_filter import KalmanBetaFilter

def get_backtest_zscores():
    mt5.initialize(path=MT5_PATH)
    rw = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, 15000)
    rd = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, 15000)
    mt5.shutdown()
    
    n = min(len(rw), len(rd))
    rw = rw[-n:]
    rd = rd[-n:]
    
    win = np.array([r[4] for r in rw], dtype=float)
    wdo = np.array([r[4] for r in rd], dtype=float)
    times = [datetime.fromtimestamp(r[0]) for r in rw]
    
    kf_wdo = KalmanBetaFilter(initial_beta=-22.5, trans_cov=1e-4, obs_cov=1e2)
    sp_wdo = []
    betas_wdo = []
    for y, x in zip(win, wdo):
        b, s, _ = kf_wdo.update(float(y), float(x))
        sp_wdo.append(s)
        betas_wdo.append(b)
        
    z_wdo = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo, window=40))
    
    # Also simulate 2000 bars burn-in!
    kf_wdo_2000 = KalmanBetaFilter(initial_beta=-22.5, trans_cov=1e-4, obs_cov=1e2)
    sp_wdo_2000 = []
    betas_wdo_2000 = []
    for y, x in zip(win[-2000:], wdo[-2000:]):
        b, s, _ = kf_wdo_2000.update(float(y), float(x))
        sp_wdo_2000.append(s)
        betas_wdo_2000.append(b)
        
    z_wdo_2000 = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo_2000, window=40))

    # Also simulate 250 bars burn-in!
    kf_wdo_250 = KalmanBetaFilter(initial_beta=-22.5, trans_cov=1e-4, obs_cov=1e2)
    sp_wdo_250 = []
    betas_wdo_250 = []
    for y, x in zip(win[-250:], wdo[-250:]):
        b, s, _ = kf_wdo_250.update(float(y), float(x))
        sp_wdo_250.append(s)
        betas_wdo_250.append(b)
        
    z_wdo_250 = np.array(KalmanBetaFilter.rolling_zscore(sp_wdo_250, window=40))
    
    df = pd.DataFrame({
        'time': times[-250:],
        'z_15k': z_wdo[-250:],
        'b_15k': betas_wdo[-250:],
        'z_2k': z_wdo_2000[-250:],
        'b_2k': betas_wdo_2000[-250:],
        'z_250': z_wdo_250[-250:],
        'b_250': betas_wdo_250[-250:]
    })
    return df

if __name__ == "__main__":
    print("Fetching backtest Z-scores...")
    df_bt = get_backtest_zscores()
    df_target = df_bt[df_bt['time'].astype(str).str.contains("2026-04-30 14:")]
    print("\nCOMPARAÇÃO (30 de Abril, entre 14:00 e 14:55):")
    print(df_target[['time', 'z_15k', 'b_15k', 'z_2k', 'b_2k', 'z_250', 'b_250']].to_string(index=False))
