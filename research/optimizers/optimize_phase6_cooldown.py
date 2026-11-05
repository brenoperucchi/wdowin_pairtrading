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

def run_backtest_cooldown(df, sl_pts, tp_pts, start_h, end_h, wait_bars, be_activation=0, be_trail=0, max_hold_h=17, max_hold_m=30):
    trades = []
    open_trade = None
    cooldown_until = None
    
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_close = df['win'].values
    signals = df['signal'].values
    times = df.index
    
    eod_time = time(max_hold_h, max_hold_m)
    
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
            
            # Dynamic Stop Loss for Break-Even
            current_sl = sl_pts
            if be_activation > 0:
                max_fav = (win_high[i] - entry_price) if direction == 1 else (entry_price - win_low[i])
                if open_trade.get('max_fav_excursion', 0) < max_fav:
                    open_trade['max_fav_excursion'] = max_fav
                
                if open_trade.get('max_fav_excursion', 0) >= be_activation:
                    # Move SL to entry + trail, but expressed in points distance
                    current_sl = -be_trail # so that entry - current_sl = entry + trail
                
            hit_exit = False
            exit_price = None
            
            if direction == 1: # BUY
                if win_high[i] >= entry_price + tp_pts:
                    hit_exit, exit_price = True, entry_price + tp_pts
                elif win_low[i] <= entry_price - current_sl:
                    hit_exit, exit_price = True, entry_price - current_sl
            else: # SELL
                if win_low[i] <= entry_price - tp_pts:
                    hit_exit, exit_price = True, entry_price - tp_pts
                elif win_high[i] >= entry_price + current_sl:
                    hit_exit, exit_price = True, entry_price + current_sl
            
            if not hit_exit and t >= eod_time:
                hit_exit, exit_price = True, win_close[i]
                
            if hit_exit:
                open_trade['exit_price'] = exit_price
                open_trade['pnl'] = (exit_price - entry_price) * direction
                trades.append(open_trade)
                open_trade = None
                cooldown_until = i + wait_bars
                continue
                
        # Check Entries
        if open_trade is None and signals[i] != 0:
            if cooldown_until is not None and i <= cooldown_until:
                continue
                
            if t >= t_start and t < t_end:
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i],
                    'bars_held': 0,
                }
            
    return trades

def run_phase_6():
    print("Loading data and pre-calculating base Kalman filters...")
    df_base = fetch_data()
    if df_base is None:
        print("Failed to fetch data.")
        return
        
    df_base = generate_signals(df_base)
    
    # Winners so far
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    sl_val = 200
    tp_val = 500
    
    # Let's assume Phase 5 will lock standard hours if not provided differently.
    # Default is 9 to 17.
    start_h = 9
    end_h = 17
    
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
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_6_cooldown")
    os.makedirs(out_dir, exist_ok=True)
    
    print("--- Starting Phase 6: Cooldown Grid ---")
    wait_bars_range = range(0, 7)
    
    results = []
    
    for wb in wait_bars_range:
        trades = run_backtest_cooldown(df_sig, sl_pts=sl_val, tp_pts=tp_val, start_h=start_h, end_h=end_h, wait_bars=wb)
        pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
        
        results.append({
            'WAIT_BARS': wb,
            'trades': total_trades,
            'pnl': pnl,
            'max_dd': max_dd,
            'ret_dd': ret_dd
        })
        
    df_res = pd.DataFrame(results)
    df_res.to_csv(os.path.join(out_dir, "cooldown_grid.csv"), index=False)
    
    plt.figure(figsize=(10, 6))
    sns.barplot(data=df_res, x='WAIT_BARS', y='ret_dd', palette='viridis')
    plt.title("Phase 6: Cooldown Period vs Ret/DD")
    plt.xlabel('Wait Bars (M5)')
    plt.ylabel('Retorno / Max Drawdown')
    for i, row in df_res.iterrows():
        plt.text(i, row['ret_dd'], f"{row['ret_dd']:.2f}\n(DD: {row['max_dd']})", ha='center', va='bottom')
        
    plt.savefig(os.path.join(out_dir, "barchart_cooldown.png"))
    
    print("Phase 6 finished.")

if __name__ == "__main__":
    run_phase_6()
