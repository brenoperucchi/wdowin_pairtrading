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

def run_di_isolated():
    print("--- HYBRID V1: DI ISOLATED (NO NWE) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    di_prices = df_base['di'].values
    
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
    
    sl = 300
    tp = 500
    
    di_results = []
    
    # Grid de Z-Score isolado
    for z in np.arange(2.0, 4.1, 0.2):
        z = round(z, 1)
        
        df_sig = df_base.copy()
        df_sig['signal'] = 0
        
        sig_buy = (z_di <= -z)
        sig_sell = (z_di >= z)
        
        df_sig.loc[sig_buy, 'signal'] = 1
        df_sig.loc[sig_sell, 'signal'] = -1
        
        trades = run_backtest_cooldown(df_sig, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
        pnl, dd, ret_dd, t_count = evaluate_trades(trades)
        wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
        
        di_results.append({
            'Z_DI': z,
            'Trades': t_count,
            'WinRate': round(wr, 2),
            'PnL': pnl,
            'MaxDD': dd,
            'Ret_DD': round(ret_dd, 2)
        })
        
    df_res = pd.DataFrame(di_results).sort_values('Ret_DD', ascending=False)
    print("\n--- RESULTADOS: DI ISOLADO KALMAN (SEM NWE) ---")
    print(df_res.to_string(index=False))

if __name__ == "__main__":
    run_di_isolated()
