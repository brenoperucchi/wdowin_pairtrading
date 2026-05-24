import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from research.test_supreme_longterm import fetch_local_history
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades

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

def run_single_test():
    print("--- HYBRID V1: SINGLE TEST ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    w_val = 2.2
    d_val = 2.2
    a_val = 1.6
    sl = 300
    tp = 500
    
    print(f"Applying Hybrid | Z_WDO: {w_val} | Z_DI: {d_val} | Z_ATT: {a_val}")
    print(f"Exits: SL {sl} / TP {tp}")
    
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
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
    
    sig_wdo_strong = np.where(z_wdo <= -w_val, 1, np.where(z_wdo >= w_val, -1, 0))
    sig_di_strong = np.where(z_di <= -d_val, 1, np.where(z_di >= d_val, -1, 0))
    sig_wdo_att = np.where(z_wdo <= -a_val, 1, np.where(z_wdo >= a_val, -1, 0))
    sig_di_att = np.where(z_di <= -a_val, 1, np.where(z_di >= a_val, -1, 0))
    
    buy_mask = ((sig_wdo_strong == 1) & (sig_di_att == 1)) | ((sig_wdo_att == 1) & (sig_di_strong == 1))
    sell_mask = ((sig_wdo_strong == -1) & (sig_di_att == -1)) | ((sig_wdo_att == -1) & (sig_di_strong == -1))
    
    df_sig = df_base.copy()
    df_sig['signal'] = 0
    df_sig.loc[buy_mask, 'signal'] = 1
    df_sig.loc[sell_mask, 'signal'] = -1
    
    trades = run_backtest_cooldown(df_sig, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
    pnl, dd, ret_dd, t_count = evaluate_trades(trades)
    wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
    
    print("\n--- RESULTS ---")
    print(f"Trades: {t_count}")
    print(f"Win Rate: {wr:.2f}%")
    print(f"PnL Líquido: {pnl}")
    print(f"Max Drawdown: {dd}")
    print(f"Ret/DD: {ret_dd:.2f}")

if __name__ == "__main__":
    run_single_test()
