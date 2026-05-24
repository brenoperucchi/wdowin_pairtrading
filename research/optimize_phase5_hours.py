import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from itertools import product
from datetime import time

from research.backtest_matador import fetch_data, generate_signals
from research.optimize_phase1_zscores import evaluate_trades

def run_backtest_hours(df, sl_pts, tp_pts, start_h, end_h):
    trades = []
    open_trade = None
    
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_close = df['win'].values
    signals = df['signal'].values
    times = df.index
    
    eod_time = time(17, 30)
    
    t_start = time(start_h, 0)
    t_end = time(end_h, 0)
    
    for i in range(len(df)):
        dt = times[i]
        t = dt.time()
        
        # Check Exits
        if open_trade is not None:
            open_trade['bars_held'] += 1
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
                
            hit_exit = False
            exit_price = None
            
            if direction == 1: # BUY
                if win_high[i] >= entry_price + tp_pts:
                    hit_exit, exit_price = True, entry_price + tp_pts
                elif win_low[i] <= entry_price - sl_pts:
                    hit_exit, exit_price = True, entry_price - sl_pts
            else: # SELL
                if win_low[i] <= entry_price - tp_pts:
                    hit_exit, exit_price = True, entry_price - tp_pts
                elif win_high[i] >= entry_price + sl_pts:
                    hit_exit, exit_price = True, entry_price + sl_pts
            
            if not hit_exit and t >= eod_time:
                hit_exit, exit_price = True, win_close[i]
                
            if hit_exit:
                open_trade['exit_price'] = exit_price
                open_trade['pnl'] = (exit_price - entry_price) * direction
                trades.append(open_trade)
                open_trade = None
                continue
                
        # Check Entries
        if open_trade is None and signals[i] != 0:
            if t >= t_start and t < t_end:
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i],
                    'bars_held': 0,
                }
            
    return trades

def run_phase_5():
    print("Loading data and pre-calculating base Kalman filters...")
    df_base = fetch_data()
    if df_base is None:
        print("Failed to fetch data.")
        return
        
    df_base = generate_signals(df_base)
    
    # Winners
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    sl_val = 200
    tp_val = 500
    
    df_base['sig_wdo_strong'] = np.where(df_base['z_wdo'] <= -z_wdo_val, 1, np.where(df_base['z_wdo'] >= z_wdo_val, -1, 0))
    df_base['sig_di_strong'] = np.where(df_base['z_di'] <= -z_di_val, 1, np.where(df_base['z_di'] >= z_di_val, -1, 0))
    df_base['sig_wdo'] = np.where(df_base['z_wdo'] <= -z_att_val, 1, np.where(df_base['z_wdo'] >= z_att_val, -1, 0))
    df_base['sig_di'] = np.where(df_base['z_di'] <= -z_att_val, 1, np.where(df_base['z_di'] >= z_att_val, -1, 0))
    
    buy_mask = ((df_base['sig_wdo_strong'] == 1) & (df_base['sig_di'] == 1)) | ((df_base['sig_wdo'] == 1) & (df_base['sig_di_strong'] == 1))
    sell_mask = ((df_base['sig_wdo_strong'] == -1) & (df_base['sig_di'] == -1)) | ((df_base['sig_wdo'] == -1) & (df_base['sig_di_strong'] == -1))
    
    df_sig = df_base.copy()
    df_sig['signal'] = 0
    df_sig.loc[buy_mask, 'signal'] = 1
    df_sig.loc[sell_mask, 'signal'] = -1
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_5_hours")
    os.makedirs(out_dir, exist_ok=True)
    
    print("--- Starting Phase 5: Trading Hours Grid ---")
    start_hours = [9, 10, 11, 12, 13]
    end_hours = [14, 15, 16, 17]
    
    scenarios = [(s, e) for s in start_hours for e in end_hours if s < e]
    
    results = []
    
    for sh, eh in scenarios:
        trades = run_backtest_hours(df_sig, sl_pts=sl_val, tp_pts=tp_val, start_h=sh, end_h=eh)
        pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
        
        results.append({
            'START_H': sh,
            'END_H': eh,
            'trades': total_trades,
            'pnl': pnl,
            'max_dd': max_dd,
            'ret_dd': ret_dd
        })
        
    df_res = pd.DataFrame(results).sort_values(by='ret_dd', ascending=False)
    df_res.to_csv(os.path.join(out_dir, "hours_grid.csv"), index=False)
    
    if len(df_res) > 0:
        pivot = df_res.pivot(index='START_H', columns='END_H', values='ret_dd')
        plt.figure(figsize=(10, 8))
        sns.heatmap(pivot, annot=True, cmap="viridis", fmt=".2f")
        plt.title("Phase 5: Start vs End Hours (Ret/DD)")
        plt.savefig(os.path.join(out_dir, "heatmap_hours.png"))
        
    print("Phase 5 finished.")

if __name__ == "__main__":
    run_phase_5()
