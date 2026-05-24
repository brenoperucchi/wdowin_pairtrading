import sys
import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from numba import njit

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
def fast_equity_curve(win_high, win_low, win_close, signals, hour_arr, minute_arr, sl_pts, tp_pts, wait_bars):
    t_start_h = 9
    t_end_h = 16
    eod_h = 17
    eod_m = 40
    
    n = len(win_close)
    equity = np.zeros(n)
    
    pnl_total = 0.0
    open_entry = 0.0
    open_dir = 0
    cooldown = 0
    
    for i in range(n):
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
                    
        equity[i] = pnl_total
        
    return equity

def plot_portfolio():
    print("Fetching data...")
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
    
    # ----------------------- WDO -----------------------
    # WDO Base: delta=1e-5, vt=1e-3, w=40, z=1.8, cd=2, sl=300, tp=400
    print("Calculating WDO Kalman...")
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
    
    print("Running WDO Backtest...")
    eq_wdo = fast_equity_curve(win_high, win_low, win_close, sig_wdo_final, hour_arr, minute_arr, sl_pts=300, tp_pts=400, wait_bars=2)
    
    # ----------------------- DI -----------------------
    # DI Base: delta=1e-5, vt=1.0, w=40, z=2.6, cd=2, sl=250, tp=600
    print("Calculating DI Kalman...")
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

    print("Running DI Backtest...")
    eq_di = fast_equity_curve(win_high, win_low, win_close, sig_di_final, hour_arr, minute_arr, sl_pts=250, tp_pts=600, wait_bars=2)
    
    # ----------------------- PORTFOLIO -----------------------
    eq_portfolio = eq_wdo + eq_di
    
    # Plotting
    plt.figure(figsize=(14, 8))
    plt.plot(df_base.index, eq_wdo, label='WDO_Kalman (SL:300, TP:400)', color='blue', alpha=0.7)
    plt.plot(df_base.index, eq_di, label='DI_Kalman (SL:250, TP:600)', color='orange', alpha=0.7)
    plt.plot(df_base.index, eq_portfolio, label='Portfolio (WDO + DI)', color='green', linewidth=2.5)
    
    plt.title('Equity Curve: Matador V6 (WDO + DI Portfolio)', fontsize=16)
    plt.xlabel('Date')
    plt.ylabel('Cumulative PnL (points)')
    plt.grid(True, alpha=0.3)
    plt.legend(loc='upper left', fontsize=12)
    plt.tight_layout()
    
    out_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "portfolio_equity.png")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    plt.savefig(out_file, dpi=150)
    print(f"Chart saved to: {out_file}")

if __name__ == "__main__":
    plot_portfolio()
