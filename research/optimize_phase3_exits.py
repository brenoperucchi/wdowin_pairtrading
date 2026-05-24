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

def run_backtest_exits(df, sl_pts=None, tp_pts=None, max_bars=None, end_of_day=False):
    trades = []
    open_trade = None
    
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_close = df['win'].values
    signals = df['signal'].values
    times = df.index
    
    eod_time = time(17, 30)
    
    for i in range(len(df)):
        dt = times[i]
        
        # Check Exits
        if open_trade is not None:
            open_trade['bars_held'] += 1
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            hit_sl = False
            hit_tp = False
            hit_time = False
            exit_price = None
            
            # 1. SL/TP check
            if sl_pts is not None and tp_pts is not None:
                if direction == 1: # BUY
                    if win_low[i] <= entry_price - sl_pts:
                        hit_sl, exit_price = True, entry_price - sl_pts
                    elif win_high[i] >= entry_price + tp_pts:
                        hit_tp, exit_price = True, entry_price + tp_pts
                else: # SELL
                    if win_high[i] >= entry_price + sl_pts:
                        hit_sl, exit_price = True, entry_price + sl_pts
                    elif win_low[i] <= entry_price - tp_pts:
                        hit_tp, exit_price = True, entry_price - tp_pts
                        
            # 2. Time checks
            if not (hit_sl or hit_tp):
                if max_bars is not None and open_trade['bars_held'] >= max_bars:
                    hit_time, exit_price = True, win_close[i]
                elif end_of_day and dt.time() >= eod_time:
                    hit_time, exit_price = True, win_close[i]
                    
            if hit_sl or hit_tp or hit_time:
                open_trade['exit_price'] = exit_price
                open_trade['pnl'] = (exit_price - entry_price) * direction
                trades.append(open_trade)
                open_trade = None
                continue
                
        # Check Entries
        if open_trade is None and signals[i] != 0:
            t = dt.time()
            if t >= time(9, 0) and t < time(17, 0):
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i],
                    'bars_held': 0
                }
            
    return trades

def run_phase_3():
    print("Loading data and pre-calculating base Kalman filters...")
    df_base = fetch_data()
    if df_base is None:
        print("Failed to fetch data.")
        return
        
    df_base = generate_signals(df_base)
    
    # User's chosen fixed Z-Scores for Consensus
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    
    print(f"Applying Fixed Consensus Z-Scores: WDO={z_wdo_val}, DI={z_di_val}, ATT={z_att_val} (No NWE)")
    
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
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_3_exits")
    os.makedirs(out_dir, exist_ok=True)
    
    # ==========================================
    # Subphase 3A: Traditional SL/TP
    # ==========================================
    print("--- Starting Subphase 3A: SL/TP Grid ---")
    sl_range = np.arange(200, 650, 50)
    tp_range = np.arange(200, 1100, 100)
    
    results_3a = []
    total_3a = len(sl_range) * len(tp_range)
    count = 0
    
    for sl, tp in product(sl_range, tp_range):
        count += 1
        if count % 20 == 0:
            print(f"Subphase 3A Progress: {count}/{total_3a}")
            
        trades = run_backtest_exits(df_sig, sl_pts=sl, tp_pts=tp, max_bars=None, end_of_day=True)
        pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
        
        results_3a.append({
            'SL': sl,
            'TP': tp,
            'trades': total_trades,
            'pnl': pnl,
            'max_dd': max_dd,
            'ret_dd': ret_dd
        })
        
    df_3a = pd.DataFrame(results_3a).sort_values(by='ret_dd', ascending=False)
    df_3a.to_csv(os.path.join(out_dir, "sltp_grid.csv"), index=False)
    
    if len(df_3a) > 0:
        pivot_3a = df_3a.pivot(index='SL', columns='TP', values='ret_dd')
        plt.figure(figsize=(10, 8))
        sns.heatmap(pivot_3a, annot=True, cmap="viridis", fmt=".2f")
        plt.title("Phase 3A: SL vs TP (Ret/DD)")
        plt.savefig(os.path.join(out_dir, "heatmap_exits_3a.png"))
        
    # ==========================================
    # Subphase 3B: Time-based Exits (No SL/TP)
    # ==========================================
    print("--- Starting Subphase 3B: Time Exits Grid ---")
    # For safety against extreme events, we put a huge SL just in case, but rely on time
    # Actually plan says "Ignora SL e TP", so we pass None
    max_bars_range = [5, 10, 15, 20, 25, 30]
    eod_options = [True, False]
    
    results_3b = []
    for mb, eod in product(max_bars_range, eod_options):
        trades = run_backtest_exits(df_sig, sl_pts=None, tp_pts=None, max_bars=mb, end_of_day=eod)
        pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
        
        results_3b.append({
            'max_bars': mb,
            'end_of_day': eod,
            'trades': total_trades,
            'pnl': pnl,
            'max_dd': max_dd,
            'ret_dd': ret_dd
        })
        
    df_3b = pd.DataFrame(results_3b).sort_values(by='ret_dd', ascending=False)
    df_3b.to_csv(os.path.join(out_dir, "time_exit_grid.csv"), index=False)
    
    # Small bar chart for 3B since it's just a few combinations
    plt.figure(figsize=(10, 6))
    sns.barplot(data=df_3b, x='max_bars', y='ret_dd', hue='end_of_day')
    plt.title("Phase 3B: Time-based Exits (Ret/DD)")
    plt.savefig(os.path.join(out_dir, "barchart_exits_3b.png"))
    
    print("Phase 3 finished. Data saved in data/reports/kalman_v2/phase_3_exits/")

if __name__ == "__main__":
    run_phase_3()
