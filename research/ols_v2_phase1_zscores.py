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

def run_phase1():
    print("--- OLS V2: FASE 1 (Z-SCORES CONSENSO) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    # Calculate OLS 40 globally since it doesn't change during Z-Score optimization
    print("Calculating OLS 40 for WDO and DI...")
    _, _, z_wdo_ols = rolling_ols(win_prices, wdo_prices, 40)
    _, _, z_di_ols = rolling_ols(win_prices, di_prices, 40)
    
    df_base['z_wdo'] = z_wdo_ols
    df_base['z_di'] = z_di_ols
    
    print("Desabilitando NWE Filter para aumentar amostragem...")
    valid_buy = np.ones_like(win_prices, dtype=bool)
    valid_sell = np.ones_like(win_prices, dtype=bool)
    
    wdo_range = np.arange(1.0, 2.7, 0.2)
    di_range = np.arange(1.5, 2.7, 0.2)
    att_range = np.arange(0.8, 1.7, 0.2)
    
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
                
                # Logic guard: attention must be strictly less than the triggers
                if a_val >= w_val or a_val >= d_val:
                    continue
                
                # Pre-calculate masks
                sig_wdo_strong = np.where(z_wdo_ols <= -w_val, 1, np.where(z_wdo_ols >= w_val, -1, 0))
                sig_di_strong = np.where(z_di_ols <= -d_val, 1, np.where(z_di_ols >= d_val, -1, 0))
                sig_wdo_att = np.where(z_wdo_ols <= -a_val, 1, np.where(z_wdo_ols >= a_val, -1, 0))
                sig_di_att = np.where(z_di_ols <= -a_val, 1, np.where(z_di_ols >= a_val, -1, 0))
                
                buy_mask = ((sig_wdo_strong == 1) & (sig_di_att == 1)) | ((sig_wdo_att == 1) & (sig_di_strong == 1))
                sell_mask = ((sig_wdo_strong == -1) & (sig_di_att == -1)) | ((sig_wdo_att == -1) & (sig_di_strong == -1))
                
                df_sig = df_base.copy()
                df_sig['signal'] = 0
                df_sig.loc[buy_mask & valid_buy, 'signal'] = 1
                df_sig.loc[sell_mask & valid_sell, 'signal'] = -1
                
                # Backtest (SL 300 / TP 500 / Wait 1 / Hours 9-16)
                trades = run_backtest_cooldown(df_sig, sl_pts=300, tp_pts=500, start_h=9, end_h=16, wait_bars=1)
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
    print("\n--- TOP 10 RESULTADOS OLS-V2 FASE 1 ---")
    print(df_res.head(10).to_string(index=False))
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "ols_v2", "phase_1_zscores")
    os.makedirs(out_dir, exist_ok=True)
    
    csv_path = os.path.join(out_dir, "ols_zscores_grid.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"\nReport saved to {csv_path}")

if __name__ == "__main__":
    run_phase1()
