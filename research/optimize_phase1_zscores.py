import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, time
import matplotlib.pyplot as plt
import seaborn as sns
from itertools import product

from core.config import MT5_PATH, SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME
from research.backtest_matador import fetch_data, generate_signals

def generate_signals_grid(df_base, z_wdo_val, z_di_val, z_att_val):
    df = df_base.copy()
    
    # Attention zones
    df['sig_wdo'] = np.where(df['z_wdo'] <= -z_att_val, 1, np.where(df['z_wdo'] >= z_att_val, -1, 0))
    df['sig_di'] = np.where(df['z_di'] <= -z_att_val, 1, np.where(df['z_di'] >= z_att_val, -1, 0))
    
    # Entry thresholds
    df['sig_wdo_strong'] = np.where(df['z_wdo'] <= -z_wdo_val, 1, np.where(df['z_wdo'] >= z_wdo_val, -1, 0))
    df['sig_di_strong'] = np.where(df['z_di'] <= -z_di_val, 1, np.where(df['z_di'] >= z_di_val, -1, 0))
    
    df['signal'] = 0
    # Buy
    buy_mask = ((df['sig_wdo_strong'] == 1) & (df['sig_di'] == 1)) | ((df['sig_wdo'] == 1) & (df['sig_di_strong'] == 1))
    df.loc[buy_mask, 'signal'] = 1
    # Sell
    sell_mask = ((df['sig_wdo_strong'] == -1) & (df['sig_di'] == -1)) | ((df['sig_wdo'] == -1) & (df['sig_di_strong'] == -1))
    df.loc[sell_mask, 'signal'] = -1
    return df

def run_backtest_fast(df, sl_pts=1000, tp_pts=1000):
    trades = []
    open_trade = None
    
    # Extract arrays for speed
    win_high = df['win_high'].values
    win_low = df['win_low'].values
    win_close = df['win'].values
    signals = df['signal'].values
    times = df.index
    
    for i in range(len(df)):
        dt = times[i]
        
        # Check Exits
        if open_trade is not None:
            entry_price = open_trade['entry_price']
            direction = open_trade['direction']
            
            hit_sl = False
            hit_tp = False
            exit_price = None
            
            # Simplified High/Low exit check
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
                    
            if hit_sl or hit_tp:
                open_trade['exit_price'] = exit_price
                open_trade['pnl'] = (exit_price - entry_price) * direction
                trades.append(open_trade)
                open_trade = None
                continue # Wait for next bar for a new signal
                
        # Check Entries
        if open_trade is None and signals[i] != 0:
            # Entry Window 09:00 to 17:00
            t = dt.time()
            if t >= time(9, 0) and t < time(17, 0):
                open_trade = {
                    'direction': signals[i],
                    'entry_price': win_close[i]
                }
            
    return trades

def evaluate_trades(trades):
    if not trades:
        return 0, 0, 0, 0
    df_trades = pd.DataFrame(trades)
    net_pnl = df_trades['pnl'].sum()
    
    # Drawdown
    df_trades['cum_pnl'] = df_trades['pnl'].cumsum()
    df_trades['peak'] = df_trades['cum_pnl'].cummax()
    df_trades['drawdown'] = df_trades['peak'] - df_trades['cum_pnl']
    max_dd = df_trades['drawdown'].max()
    
    ret_dd = net_pnl / max_dd if max_dd > 0 else (net_pnl if net_pnl > 0 else 0)
    win_rate = len(df_trades[df_trades['pnl'] > 0]) / len(df_trades)
    
    return net_pnl, max_dd, ret_dd, len(trades)

def run_phase_1():
    print("Loading data and pre-calculating base Kalman filters...")
    df_base = fetch_data()
    if df_base is None:
        print("Failed to fetch data.")
        return
        
    df_base = generate_signals(df_base)
    
    # Define grid
    z_wdo_range = np.arange(1.4, 2.6, 0.1) # 1.4 to 2.5
    z_di_range = np.arange(2.2, 4.2, 0.2)  # 2.2 to 4.0
    z_att_range = np.arange(1.2, 1.7, 0.1) # 1.2 to 1.6
    
    results = []
    
    total_iters = len(z_wdo_range) * len(z_di_range) * len(z_att_range)
    
    count = 0
    for z_wdo, z_di, z_att in product(z_wdo_range, z_di_range, z_att_range):
        z_wdo = round(z_wdo, 1)
        z_di = round(z_di, 1)
        z_att = round(z_att, 1)
        
        # Skip illogical scenarios where attention is stricter than entry
        if z_att >= z_wdo or z_att >= z_di:
            total_iters -= 1
            continue
            
        count += 1
        if count % 20 == 0:
            print(f"Progress: {count} combinations tested...")
            
        df_sig = generate_signals_grid(df_base, z_wdo, z_di, z_att)
        trades = run_backtest_fast(df_sig, sl_pts=1000, tp_pts=1000)
        
        pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
        
        results.append({
            'z_wdo': z_wdo,
            'z_di': z_di,
            'z_att': z_att,
            'trades': total_trades,
            'pnl': pnl,
            'max_dd': max_dd,
            'ret_dd': ret_dd
        })
        
    print(f"Finished {count} logical combinations.")
    
    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(by='ret_dd', ascending=False)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_1_zscores")
    os.makedirs(out_dir, exist_ok=True)
    
    csv_path = os.path.join(out_dir, "zscore_grid.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"Grid results saved to {csv_path}")
    
    # Heatmap: We will fix the best z_att and plot z_wdo vs z_di
    if len(df_res) > 0:
        best_z_att = df_res.iloc[0]['z_att']
        df_heat = df_res[df_res['z_att'] == best_z_att]
        
        if not df_heat.empty:
            pivot = df_heat.pivot(index='z_wdo', columns='z_di', values='ret_dd')
            
            plt.figure(figsize=(10, 8))
            sns.heatmap(pivot, annot=True, cmap="viridis", fmt=".2f")
            plt.title(f"Phase 1 Heatmap (Ret/DD) - Fixed Z_ATT = {best_z_att}")
            plt.xlabel("Z_ENTRY_DI")
            plt.ylabel("Z_ENTRY_WDO")
            
            png_path = os.path.join(out_dir, "heatmap_zscore.png")
            plt.savefig(png_path)
            print(f"Heatmap saved to {png_path}")
        
if __name__ == "__main__":
    run_phase_1()
