import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from numba import njit

from research.test_supreme_longterm import fetch_local_history
from core.signals import calc_nwe_with_bands

class KalmanFilter:
    def __init__(self, delta=1e-4, vt=1e-3):
        self.delta = delta
        self.vt = vt
        self.beta = np.zeros(2)
        self.P = np.zeros((2, 2))
        
    def step(self, x, y):
        F = np.array([x, 1.0])
        R = self.P + np.eye(2) * self.delta
        y_hat = np.dot(F, self.beta)
        e = y - y_hat
        Q = np.dot(F, np.dot(R, F.T)) + self.vt
        K = np.dot(R, F.T) / Q
        self.beta = self.beta + K * e
        self.P = R - np.outer(K, np.dot(F, R))
        return self.beta[0], e

@njit
def fast_backtest(win_high, win_low, win_close, signals, hour_arr, minute_arr, sl_pts, tp_pts, wait_bars):
    t_start_h = 9
    t_end_h = 16
    eod_h = 17
    eod_m = 40
    
    pnl_total = 0.0
    max_dd = 0.0
    peak = 0.0
    trade_count = 0
    
    open_entry = 0.0
    open_dir = 0
    cooldown = 0
    
    for i in range(len(win_close)):
        h = hour_arr[i]
        m = minute_arr[i]
        
        if cooldown > 0:
            cooldown -= 1
            
        if open_dir != 0:
            is_eod = False
            if h > eod_h or (h == eod_h and m >= eod_m):
                is_eod = True
                
            exit_price = 0.0
            if open_dir == 1:
                if win_low[i] <= open_entry - sl_pts:
                    exit_price = open_entry - sl_pts
                elif win_high[i] >= open_entry + tp_pts:
                    exit_price = open_entry + tp_pts
                elif is_eod:
                    exit_price = win_close[i]
            else:
                if win_high[i] >= open_entry + sl_pts:
                    exit_price = open_entry + sl_pts
                elif win_low[i] <= open_entry - tp_pts:
                    exit_price = open_entry - tp_pts
                elif is_eod:
                    exit_price = win_close[i]
                    
            if exit_price > 0:
                trade_pnl = (exit_price - open_entry) * open_dir
                pnl_total += trade_pnl
                trade_count += 1
                
                if pnl_total > peak:
                    peak = pnl_total
                dd = peak - pnl_total
                if dd > max_dd:
                    max_dd = dd
                    
                open_dir = 0
                cooldown = wait_bars
                
        if open_dir == 0 and cooldown == 0:
            if t_start_h <= h <= t_end_h:
                if signals[i] == 1:
                    open_dir = 1
                    open_entry = win_close[i]
                elif signals[i] == -1:
                    open_dir = -1
                    open_entry = win_close[i]
                    
    ret_dd = pnl_total / max_dd if max_dd > 0 else 0
    return pnl_total, max_dd, ret_dd, trade_count

def optimize_asset_kalman(asset_name, asset_prices, win_high, win_low, win_close, hour_arr, minute_arr, buy_mask, sell_mask):
    deltas = [1e-5, 1e-4, 1e-3]
    vts = [1e-3, 1e-2, 1e-1, 1.0, 10.0]
    windows = [20, 40, 60, 80]
    z_entries = np.arange(1.6, 2.7, 0.2)
    cooldowns = [2, 3]
    sl_fixed = 300
    tp_fixed = 600
    
    results = []
    
    for delta in deltas:
        for vt in vts:
            print(f"[{asset_name}] Running Kalman Filtering (delta={delta}, vt={vt})...")
            kf = KalmanFilter(delta=delta, vt=vt)
            e_history = []
            for i in range(len(win_close)):
                _, e = kf.step(asset_prices[i], win_close[i])
                e_history.append(e)
            e_arr = np.array(e_history)
            
            for w in windows:
                std_arr = pd.Series(e_arr).rolling(window=w).std().bfill().fillna(1).values
                std_arr = np.where(std_arr == 0, 1.0, std_arr)
                mean_arr = pd.Series(e_arr).rolling(window=w).mean().bfill().fillna(0).values
                z_arr = (e_arr - mean_arr) / std_arr
                
                for z in z_entries:
                    z = round(z, 2)
                    sig_buy_kal = (z_arr <= -z)
                    sig_sell_kal = (z_arr >= z)
                    
                    sig_final = np.zeros(len(win_close), dtype=np.int32)
                    sig_final[sig_buy_kal & buy_mask] = 1
                    sig_final[sig_sell_kal & sell_mask] = -1
                    
                    for cd in cooldowns:
                        pnl, dd, ret_dd, t_count = fast_backtest(win_high, win_low, win_close, sig_final, hour_arr, minute_arr, sl_fixed, tp_fixed, cd)
                        if t_count >= 30 and pnl > 0:
                            results.append({
                                'Asset': asset_name,
                                'Delta': delta,
                                'VT': vt,
                                'Window': w,
                                'Z_Entry': z,
                                'Cooldown': cd,
                                'Trades': t_count,
                                'PnL': pnl,
                                'MaxDD': dd,
                                'Ret_DD': ret_dd
                            })
                            
    return pd.DataFrame(results)

def run_kalman_opt():
    print("--- HYBRID V1: FASE 8 (KALMAN RE-OPTIMIZATION) ---")
    df_base = fetch_local_history()
    
    win_high = df_base['win_high'].values
    win_low = df_base['win_low'].values
    win_close = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    hour_arr = df_base.index.hour.values
    minute_arr = df_base.index.minute.values
    
    print("Applying Fixed NWE Filter (BW=8, Lookback=100, MAE=3.0, Prox=10%)...")
    _, upper_nwe, lower_nwe, _ = calc_nwe_with_bands(win_close, bandwidth=8, lookback=100, mult_mae=3.0)
    
    band_w = upper_nwe - lower_nwe
    buy_zone = lower_nwe + band_w * 0.10
    sell_zone = upper_nwe - band_w * 0.10
    
    valid_buy_price = (win_close <= buy_zone)
    valid_sell_price = (win_close >= sell_zone)
    
    # Pre-compile Numba
    print("Compiling Numba engine...")
    _ = fast_backtest(win_high[:100], win_low[:100], win_close[:100], np.zeros(100, dtype=np.int32), hour_arr[:100], minute_arr[:100], 300, 600, 2)
    
    start_time = time.time()
    
    # Otimizar WDO
    df_wdo_res = optimize_asset_kalman('WDO', wdo_prices, win_high, win_low, win_close, hour_arr, minute_arr, valid_buy_price, valid_sell_price)
    if not df_wdo_res.empty:
        df_wdo_res = df_wdo_res.sort_values('Ret_DD', ascending=False)
        
    # Otimizar DI
    df_di_res = optimize_asset_kalman('DI', di_prices, win_high, win_low, win_close, hour_arr, minute_arr, valid_buy_price, valid_sell_price)
    if not df_di_res.empty:
        df_di_res = df_di_res.sort_values('Ret_DD', ascending=False)
        
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "phase8_kalman")
    os.makedirs(out_dir, exist_ok=True)
    
    if not df_wdo_res.empty:
        df_wdo_res.to_csv(os.path.join(out_dir, "wdo_kalman.csv"), index=False)
        print("\n--- TOP 10 WDO (KALMAN) ---")
        print(df_wdo_res.head(10).to_string(index=False))
        
    if not df_di_res.empty:
        df_di_res.to_csv(os.path.join(out_dir, "di_kalman.csv"), index=False)
        print("\n--- TOP 10 DI (KALMAN) ---")
        print(df_di_res.head(10).to_string(index=False))

    print(f"\nExecution finished in {(time.time() - start_time):.1f}s")

if __name__ == "__main__":
    run_kalman_opt()
