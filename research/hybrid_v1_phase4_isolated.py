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

def run_isolated():
    print("--- HYBRID V1: FASE 4 (ISOLATED SETUPS) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    print("Calculating OLS 40 for WDO...")
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    print("Calculating Kalman for DI...")
    kf_di = KalmanFilter(delta=1e-4, vt=1e-3)
    e_di_history = []
    for i in range(len(win_prices)):
        _, e_di = kf_di.step(di_prices[i], win_prices[i])
        e_di_history.append(e_di)
        
    e_di_arr = np.array(e_di_history)
    std_di = pd.Series(e_di_arr).rolling(window=40).std().bfill().fillna(1).values
    std_di = np.where(std_di == 0, 1.0, std_di)
    mean_di = pd.Series(e_di_arr).rolling(window=40).mean().bfill().fillna(0).values
    z_di = (e_di_arr - mean_di) / std_di
    
    # NWE Filters on WIN
    nwe_masks = {}
    for bw in [0, 5, 8]:
        if bw == 0:
            nwe_masks[bw] = (np.ones_like(win_prices, dtype=bool), np.ones_like(win_prices, dtype=bool))
        else:
            nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=150, mult_mae=1.0)
            mae = upper_nwe - nwe
            upper = nwe + mae * 5.0
            lower = nwe - mae * 5.0
            band_w = upper - lower
            valid_buy = (~is_up) & (win_prices <= lower + band_w * 0.0)
            valid_sell = (is_up) & (win_prices >= upper - band_w * 0.0)
            nwe_masks[bw] = (valid_buy, valid_sell)
            
    # Test WDO Isolated (Z_WDO from 2.0 to 3.0)
    wdo_results = []
    for z in np.arange(2.0, 3.1, 0.2):
        z = round(z, 1)
        for bw in [0, 5, 8]:
            df_sig = df_base.copy()
            df_sig['signal'] = 0
            
            sig_buy = (z_wdo <= -z)
            sig_sell = (z_wdo >= z)
            
            v_buy, v_sell = nwe_masks[bw]
            
            df_sig.loc[sig_buy & v_buy, 'signal'] = 1
            df_sig.loc[sig_sell & v_sell, 'signal'] = -1
            
            trades = run_backtest_cooldown(df_sig, sl_pts=300, tp_pts=500, start_h=9, end_h=16, wait_bars=2)
            pnl, dd, ret_dd, t_count = evaluate_trades(trades)
            wdo_results.append({'Asset': 'WDO(OLS)', 'Z_Score': z, 'NWE_BW': bw, 'Trades': t_count, 'PnL': pnl, 'MaxDD': dd, 'Ret_DD': ret_dd})
            
    print("\n--- TOP WDO ISOLATED ---")
    print(pd.DataFrame(wdo_results).sort_values('Ret_DD', ascending=False).head(10).to_string(index=False))
    
    # Test DI Isolated (Z_DI from 2.0 to 4.0)
    di_results = []
    for z in np.arange(2.0, 4.1, 0.2):
        z = round(z, 1)
        for bw in [0, 5, 8]:
            df_sig = df_base.copy()
            df_sig['signal'] = 0
            
            sig_buy = (z_di <= -z)
            sig_sell = (z_di >= z)
            
            v_buy, v_sell = nwe_masks[bw]
            
            df_sig.loc[sig_buy & v_buy, 'signal'] = 1
            df_sig.loc[sig_sell & v_sell, 'signal'] = -1
            
            trades = run_backtest_cooldown(df_sig, sl_pts=300, tp_pts=500, start_h=9, end_h=16, wait_bars=2)
            pnl, dd, ret_dd, t_count = evaluate_trades(trades)
            di_results.append({'Asset': 'DI(Kalman)', 'Z_Score': z, 'NWE_BW': bw, 'Trades': t_count, 'PnL': pnl, 'MaxDD': dd, 'Ret_DD': ret_dd})
            
    print("\n--- TOP DI ISOLATED ---")
    print(pd.DataFrame(di_results).sort_values('Ret_DD', ascending=False).head(10).to_string(index=False))
    
if __name__ == "__main__":
    run_isolated()
