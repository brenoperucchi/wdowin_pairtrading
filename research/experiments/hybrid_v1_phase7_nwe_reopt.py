import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from research.test_supreme_longterm import fetch_local_history
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades
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

def rolling_ols(y, x, window):
    s_y = pd.Series(y)
    s_x = pd.Series(x)
    cov = s_y.rolling(window=window).cov(s_x)
    var = s_x.rolling(window=window).var()
    beta = cov / var
    beta = beta.bfill().fillna(1.0).values
    spread = y - (beta * x)
    s_spread = pd.Series(spread)
    mean_spread = s_spread.rolling(window=window).mean().bfill().fillna(0).values.copy()
    std_spread = s_spread.rolling(window=window).std().bfill().fillna(1).values.copy()
    std_spread = np.where(std_spread == 0, 1.0, std_spread)
    z_score = (spread - mean_spread) / std_spread
    return beta, spread, z_score

from numba import njit

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

def run_nwe_reopt():
    print("--- HYBRID V1: FASE 7 (NWE RE-OPTIMIZATION) ---")
    df_base = fetch_local_history()
    
    win_high = df_base['win_high'].values
    win_low = df_base['win_low'].values
    win_close = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    hour_arr = df_base.index.hour.values
    minute_arr = df_base.index.minute.values
    
    print("Calculating OLS 40 for WDO...")
    _, _, z_wdo = rolling_ols(win_close, wdo_prices, 40)
    
    print("Calculating Kalman for DI...")
    kf_di = KalmanFilter(delta=1e-4, vt=1e-3)
    e_di_history = []
    for i in range(len(win_close)):
        _, e_di = kf_di.step(di_prices[i], win_close[i])
        e_di_history.append(e_di)
        
    e_di_arr = np.array(e_di_history)
    std_di = pd.Series(e_di_arr).rolling(window=40).std().bfill().fillna(1).values
    std_di = np.where(std_di == 0, 1.0, std_di)
    mean_di = pd.Series(e_di_arr).rolling(window=40).mean().bfill().fillna(0).values
    z_di = (e_di_arr - mean_di) / std_di
    
    print("Applying Fixed NWE Filter (BW=8, Lookback=100, MAE=3.0, Prox=10%)...")
    nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_close, bandwidth=8, lookback=100, mult_mae=3.0)
    
    band_w = upper_nwe - lower_nwe
    buy_zone = lower_nwe + band_w * 0.10
    sell_zone = upper_nwe - band_w * 0.10
    
    valid_buy_price = (win_close <= buy_zone)
    valid_sell_price = (win_close >= sell_zone)
    
    z_range = np.arange(1.8, 2.7, 0.2)
    sl_range = np.arange(300, 850, 50)
    tp_range = np.arange(300, 850, 50)
    cooldowns = [2, 3]
    is_up_modes = [True, False]
    
    results_wdo = []
    results_di = []
    
    total_iters = len(z_range) * len(sl_range) * len(tp_range) * len(cooldowns) * len(is_up_modes)
    print(f"Grid search will evaluate {total_iters} combinations per setup.")
    
    # Pre-compile numba func
    _ = fast_backtest(win_high[:100], win_low[:100], win_close[:100], np.zeros(100), hour_arr[:100], minute_arr[:100], 300, 500, 2)
    
    start_time = time.time()
    iter_count = 0
    
    for z in z_range:
        z = round(z, 2)
        sig_buy_ols = (z_wdo <= -z)
        sig_sell_ols = (z_wdo >= z)
        sig_buy_kal = (z_di <= -z)
        sig_sell_kal = (z_di >= z)
        
        for use_is_up in is_up_modes:
            if use_is_up:
                buy_mask = valid_buy_price & (~is_up)
                sell_mask = valid_sell_price & (is_up)
            else:
                buy_mask = valid_buy_price
                sell_mask = valid_sell_price
                
            sig_wdo = np.zeros(len(win_close), dtype=np.int32)
            sig_wdo[sig_buy_ols & buy_mask] = 1
            sig_wdo[sig_sell_ols & sell_mask] = -1
            
            sig_di = np.zeros(len(win_close), dtype=np.int32)
            sig_di[sig_buy_kal & buy_mask] = 1
            sig_di[sig_sell_kal & sell_mask] = -1
            
            for cd in cooldowns:
                for sl in sl_range:
                    for tp in tp_range:
                        if sl >= tp * 2: 
                            continue
                        
                        iter_count += 1
                        
                        pnl, dd, ret_dd, t_count = fast_backtest(win_high, win_low, win_close, sig_wdo, hour_arr, minute_arr, sl, tp, cd)
                        if t_count >= 50 and pnl > 0:
                            results_wdo.append({'Z_Entry': z, 'is_up': use_is_up, 'Cooldown': cd, 'SL': sl, 'TP': tp, 'Trades': t_count, 'PnL': pnl, 'MaxDD': dd, 'Ret_DD': ret_dd})
                        
                        pnl_di, dd_di, ret_dd_di, t_count_di = fast_backtest(win_high, win_low, win_close, sig_di, hour_arr, minute_arr, sl, tp, cd)
                        if t_count_di >= 50 and pnl_di > 0:
                            results_di.append({'Z_Entry': z, 'is_up': use_is_up, 'Cooldown': cd, 'SL': sl, 'TP': tp, 'Trades': t_count_di, 'PnL': pnl_di, 'MaxDD': dd_di, 'Ret_DD': ret_dd_di})
                            
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "phase7_nwe_reopt")
    os.makedirs(out_dir, exist_ok=True)
    
    df_wdo_res = pd.DataFrame(results_wdo).sort_values('Ret_DD', ascending=False)
    df_di_res = pd.DataFrame(results_di).sort_values('Ret_DD', ascending=False)
    
    df_wdo_res.to_csv(os.path.join(out_dir, "wdo_nwe_reopt.csv"), index=False)
    df_di_res.to_csv(os.path.join(out_dir, "di_nwe_reopt.csv"), index=False)
    
    print("\n--- TOP 10 WDO_NWE (OLS) ---")
    print(df_wdo_res.head(10).to_string(index=False))
    
    print("\n--- TOP 10 DI_NWE (KALMAN) ---")
    print(df_di_res.head(10).to_string(index=False))
    
    print(f"\nExecution finished in {(time.time() - start_time):.1f}s")

if __name__ == "__main__":
    run_nwe_reopt()
