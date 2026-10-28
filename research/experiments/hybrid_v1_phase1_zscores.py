import sys
import os
import time
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

def run_hybrid_phase1():
    print("--- HYBRID V1: WDO(OLS) + DI(KALMAN) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    # 1. WDO using OLS (Window 40)
    print("Calculating OLS 40 for WDO...")
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    df_base['z_wdo'] = z_wdo
    
    # 2. DI using Kalman Filter
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
    df_base['z_di'] = z_di
    
    # Setup constraints
    sl_val = 450
    tp_val = 450
    start_h = 9
    end_h = 16
    wait_bars = 2
    
    print(f"Base Setup: SL {sl_val} | TP {tp_val} | {start_h}h-{end_h}h | Cooldown {wait_bars}")
    
    # Grid Ranges
    wdo_range = np.arange(1.0, 3.0, 0.2)
    di_range = np.arange(1.5, 3.5, 0.2)
    att_range = np.arange(0.8, 2.0, 0.2)
    
    results = []
    
    total_iters = len(wdo_range) * len(di_range) * len(att_range)
    print(f"Total Combinations to test: {total_iters}")
    
    start_time = time.time()
    counter = 0
    
    for w in wdo_range:
        w_val = round(w, 1)
        for d in di_range:
            d_val = round(d, 1)
            for a in att_range:
                a_val = round(a, 1)
                counter += 1
                
                if a_val >= w_val or a_val >= d_val:
                    continue
                
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
                
                trades = run_backtest_cooldown(df_sig, sl_pts=sl_val, tp_pts=tp_val, start_h=start_h, end_h=end_h, wait_bars=wait_bars)
                pnl, dd, ret_dd, t_count = evaluate_trades(trades)
                wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
                
                results.append({
                    'Z_WDO': w_val,
                    'Z_DI': d_val,
                    'Z_ATT': a_val,
                    'Trades': t_count,
                    'WinRate': round(wr, 2),
                    'PnL': pnl,
                    'MaxDD': dd,
                    'Ret_DD': round(ret_dd, 2)
                })
                
                if counter % 50 == 0:
                    elapsed = time.time() - start_time
                    print(f"Progresso: {counter}/{total_iters} | Tempo: {elapsed:.1f}s")
                    
    df_res = pd.DataFrame(results).sort_values(by='Ret_DD', ascending=False)
    print("\n--- TOP 10 RESULTADOS HYBRID-V1 FASE 1 ---")
    print(df_res.head(10).to_string(index=False))
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "phase_1_zscores")
    os.makedirs(out_dir, exist_ok=True)
    
    csv_path = os.path.join(out_dir, "hybrid_zscores_grid.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"\nReport saved to {csv_path}")

if __name__ == "__main__":
    run_hybrid_phase1()
