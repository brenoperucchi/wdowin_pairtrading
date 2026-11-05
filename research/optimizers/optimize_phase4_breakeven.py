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

def run_backtest_be(df, sl_pts, tp_pts, be_act, be_lock):
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
            be_active = open_trade['be_active']
            max_favor = open_trade['max_favor']
            
            # calculate pts favor for high/low
            if direction == 1:
                curr_max_favor = win_high[i] - entry_price
                curr_min_favor = win_low[i] - entry_price
            else:
                curr_max_favor = entry_price - win_low[i]
                curr_min_favor = entry_price - win_high[i]
                
            if curr_max_favor > max_favor:
                max_favor = curr_max_favor
                open_trade['max_favor'] = max_favor
                
            if not be_active and max_favor >= be_act:
                be_active = True
                open_trade['be_active'] = True
                
            hit_exit = False
            exit_price = None
            
            if direction == 1: # BUY
                if win_high[i] >= entry_price + tp_pts:
                    hit_exit, exit_price = True, entry_price + tp_pts
                elif be_active and win_low[i] <= entry_price + be_lock:
                    hit_exit, exit_price = True, entry_price + be_lock
                elif not be_active and win_low[i] <= entry_price - sl_pts:
                    hit_exit, exit_price = True, entry_price - sl_pts
            else: # SELL
                if win_low[i] <= entry_price - tp_pts:
                    hit_exit, exit_price = True, entry_price - tp_pts
                elif be_active and win_high[i] >= entry_price - be_lock:
                    hit_exit, exit_price = True, entry_price - be_lock
                elif not be_active and win_high[i] >= entry_price + sl_pts:
                    hit_exit, exit_price = True, entry_price + sl_pts
            
            if not hit_exit and dt.time() >= eod_time:
                hit_exit, exit_price = True, win_close[i]
                
            if hit_exit:
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
                    'bars_held': 0,
                    'max_favor': 0,
                    'be_active': False
                }
            
    return trades

def run_phase_4():
    print("Loading data and pre-calculating base Kalman filters...")
    df_base = fetch_data()
    if df_base is None:
        print("Failed to fetch data.")
        return
        
    df_base = generate_signals(df_base)
    
    # User's chosen Fixed Consensus Z-Scores (NO NWE)
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    
    # User's chosen fixed Phase 3 Exits
    sl_val = 200
    tp_val = 500
    
    print(f"Applying Fixed Consensus Z-Scores: WDO={z_wdo_val}, DI={z_di_val}, ATT={z_att_val}")
    print(f"Applying Fixed Exits: SL={sl_val}, TP={tp_val}")
    
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
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_4_breakeven")
    os.makedirs(out_dir, exist_ok=True)
    
    print("--- Starting Phase 4: Break-Even Grid ---")
    be_act_range = range(100, 450, 50)
    be_lock_range = [0, 50, 100]
    
    # We also include a control scenario (No BE)
    # BE_ACT = 9999 means it will never trigger
    scenarios = [(act, lock) for act in be_act_range for lock in be_lock_range if lock < act]
    scenarios.append((9999, 0)) # Sem Break-Even
    
    results_4 = []
    total = len(scenarios)
    count = 0
    
    for act, lock in scenarios:
        count += 1
        trades = run_backtest_be(df_sig, sl_pts=sl_val, tp_pts=tp_val, be_act=act, be_lock=lock)
        pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
        
        # Calculate Win Rate locally
        if len(trades) > 0:
            df_t = pd.DataFrame(trades)
            wins = len(df_t[df_t['pnl'] > 0])
            wr = (wins / len(trades)) * 100
        else:
            wr = 0
            
        is_control = (act == 9999)
            
        results_4.append({
            'BE_ACT': 'Sem BE' if is_control else act,
            'BE_LOCK': '-' if is_control else lock,
            'trades': total_trades,
            'win_rate': wr,
            'pnl': pnl,
            'max_dd': max_dd,
            'ret_dd': ret_dd
        })
        
    df_4 = pd.DataFrame(results_4).sort_values(by='ret_dd', ascending=False)
    df_4.to_csv(os.path.join(out_dir, "be_grid.csv"), index=False)
    
    # Heatmap filtering out the control
    df_hm = df_4[df_4['BE_ACT'] != 'Sem BE'].copy()
    if len(df_hm) > 0:
        pivot_4 = df_hm.pivot(index='BE_ACT', columns='BE_LOCK', values='ret_dd')
        plt.figure(figsize=(10, 8))
        sns.heatmap(pivot_4, annot=True, cmap="viridis", fmt=".2f")
        plt.title("Phase 4: BE_ACT vs BE_LOCK (Ret/DD)")
        plt.savefig(os.path.join(out_dir, "heatmap_be.png"))
        
    print("Phase 4 finished. Data saved in data/reports/kalman_v2/phase_4_breakeven/")

if __name__ == "__main__":
    run_phase_4()
