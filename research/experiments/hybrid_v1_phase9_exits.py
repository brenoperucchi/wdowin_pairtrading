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
def fast_backtest_exits(win_high, win_low, win_close, signals, hour_arr, minute_arr, sl_pts, tp_pts, wait_bars, be_act, be_lock):
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
    
    dynamic_sl = 0.0
    be_triggered = False
    
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
                # Se atingiu a ativacao do BE e ele estava ativo
                if be_act > 0 and not be_triggered:
                    if win_high[i] >= open_entry + be_act:
                        be_triggered = True
                        dynamic_sl = open_entry + be_lock
                        
                if win_low[i] <= dynamic_sl:
                    exit_price = dynamic_sl
                elif win_high[i] >= open_entry + tp_pts:
                    exit_price = open_entry + tp_pts
                elif is_eod:
                    exit_price = win_close[i]
                    
            else:
                if be_act > 0 and not be_triggered:
                    if win_low[i] <= open_entry - be_act:
                        be_triggered = True
                        dynamic_sl = open_entry - be_lock
                        
                if win_high[i] >= dynamic_sl:
                    exit_price = dynamic_sl
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
                be_triggered = False
                
        if open_dir == 0 and cooldown == 0:
            if t_start_h <= h <= t_end_h:
                if signals[i] == 1:
                    open_dir = 1
                    open_entry = win_close[i]
                    dynamic_sl = open_entry - sl_pts
                    be_triggered = False
                elif signals[i] == -1:
                    open_dir = -1
                    open_entry = win_close[i]
                    dynamic_sl = open_entry + sl_pts
                    be_triggered = False
                    
    ret_dd = pnl_total / max_dd if max_dd > 0 else 0
    return pnl_total, max_dd, ret_dd, trade_count

def optimize_exits():
    print("--- HYBRID V1: FASE 9 (EXITS & BREAKEVEN) ---")
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
    valid_buy_price = (win_close <= (lower_nwe + band_w * 0.10))
    valid_sell_price = (win_close >= (upper_nwe - band_w * 0.10))
    
    # WDO Base: delta=1e-5, vt=1e-3, w=40, z=1.8, cd=2
    print("Pre-calculating WDO signals...")
    kf_wdo = KalmanFilter(delta=1e-5, vt=1e-3)
    e_wdo = []
    for i in range(len(win_close)):
        _, e = kf_wdo.step(wdo_prices[i], win_close[i])
        e_wdo.append(e)
    e_wdo = np.array(e_wdo)
    std_wdo = pd.Series(e_wdo).rolling(window=40).std().bfill().fillna(1).values
    std_wdo = np.where(std_wdo == 0, 1.0, std_wdo)
    mean_wdo = pd.Series(e_wdo).rolling(window=40).mean().bfill().fillna(0).values
    z_wdo = (e_wdo - mean_wdo) / std_wdo
    
    sig_wdo_final = np.zeros(len(win_close), dtype=np.int32)
    sig_wdo_final[(z_wdo <= -1.8) & valid_buy_price] = 1
    sig_wdo_final[(z_wdo >= 1.8) & valid_sell_price] = -1
    
    # DI Base: delta=1e-5, vt=1.0, w=40, z=2.6, cd=2
    print("Pre-calculating DI signals...")
    kf_di = KalmanFilter(delta=1e-5, vt=1.0)
    e_di = []
    for i in range(len(win_close)):
        _, e = kf_di.step(di_prices[i], win_close[i])
        e_di.append(e)
    e_di = np.array(e_di)
    std_di = pd.Series(e_di).rolling(window=40).std().bfill().fillna(1).values
    std_di = np.where(std_di == 0, 1.0, std_di)
    mean_di = pd.Series(e_di).rolling(window=40).mean().bfill().fillna(0).values
    z_di = (e_di - mean_di) / std_di
    
    sig_di_final = np.zeros(len(win_close), dtype=np.int32)
    sig_di_final[(z_di <= -2.6) & valid_buy_price] = 1
    sig_di_final[(z_di >= 2.6) & valid_sell_price] = -1

    # Grid de Otimizacao
    sl_arr = np.arange(200, 500, 50)
    tp_arr = np.arange(400, 1050, 100)
    be_configs = [
        (0, 0),         # Off
        (200, 0),       # BE 200 pts, Lock 0
        (300, 0),       # BE 300 pts, Lock 0
        (400, 100)      # BE 400 pts, Lock 100
    ]
    
    print("Compiling Numba backtester...")
    _ = fast_backtest_exits(win_high[:100], win_low[:100], win_close[:100], np.zeros(100, dtype=np.int32), hour_arr[:100], minute_arr[:100], 300, 600, 2, 0, 0)
    
    def run_grid(asset_name, sig_arr):
        print(f"Running Exit Grid for {asset_name}...")
        results = []
        for sl in sl_arr:
            for tp in tp_arr:
                if sl >= tp * 2: continue # Irrational R:R
                
                for be_act, be_lock in be_configs:
                    if be_act > 0 and be_act >= tp: continue # BE > TP is impossible
                    
                    pnl, dd, ret_dd, t_count = fast_backtest_exits(win_high, win_low, win_close, sig_arr, hour_arr, minute_arr, sl, tp, 2, be_act, be_lock)
                    
                    if t_count >= 50 and pnl > 0:
                        results.append({
                            'Asset': asset_name,
                            'SL': sl,
                            'TP': tp,
                            'BE_Act': be_act,
                            'BE_Lock': be_lock,
                            'Trades': t_count,
                            'PnL': pnl,
                            'MaxDD': dd,
                            'Ret_DD': ret_dd
                        })
        return pd.DataFrame(results).sort_values('Ret_DD', ascending=False)
        
    start_time = time.time()
    
    df_wdo = run_grid("WDO", sig_wdo_final)
    df_di = run_grid("DI", sig_di_final)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "phase9_exits")
    os.makedirs(out_dir, exist_ok=True)
    
    if not df_wdo.empty:
        df_wdo.to_csv(os.path.join(out_dir, "wdo_exits.csv"), index=False)
        print("\n--- TOP 10 WDO (EXITS) ---")
        print(df_wdo.head(10).to_string(index=False))
        
    if not df_di.empty:
        df_di.to_csv(os.path.join(out_dir, "di_exits.csv"), index=False)
        print("\n--- TOP 10 DI (EXITS) ---")
        print(df_di.head(10).to_string(index=False))

    print(f"\nExecution finished in {(time.time() - start_time):.1f}s")

if __name__ == "__main__":
    optimize_exits()
