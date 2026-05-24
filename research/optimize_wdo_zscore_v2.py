import sys
import os
import itertools
import multiprocessing
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, time
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import MT5_PATH, SYMBOL_A, SYMBOL_B, TIMEFRAME
from core.kalman_filter import KalmanBetaFilter

BARS_TO_FETCH = 50000

# Parâmetros Fixos para a Fase 1
SL_PTS = 1000
TP_PTS = 1000
ALLOWED_START = time(9, 0)
ALLOWED_END = time(17, 0)
FORCE_CLOSE = time(17, 30)

def fetch_data():
    print(f"Connecting to MT5 at {MT5_PATH}...")
    if not mt5.initialize(path=MT5_PATH):
        print(f"MT5 Init Failed: {mt5.last_error()}")
        return None
        
    mt5.symbol_select(SYMBOL_A, True)
    mt5.symbol_select(SYMBOL_B, True)
    
    print(f"Fetching {BARS_TO_FETCH} bars for WDO optimization...")
    win_rates = mt5.copy_rates_from_pos(SYMBOL_A, TIMEFRAME, 0, BARS_TO_FETCH)
    wdo_rates = mt5.copy_rates_from_pos(SYMBOL_B, TIMEFRAME, 0, BARS_TO_FETCH)
    mt5.shutdown()
    
    if win_rates is None or wdo_rates is None:
        return None
        
    df_win = pd.DataFrame(win_rates)
    df_win['time'] = pd.to_datetime(df_win['time'], unit='s')
    df_win.set_index('time', inplace=True)
    
    df_wdo = pd.DataFrame(wdo_rates)
    df_wdo['time'] = pd.to_datetime(df_wdo['time'], unit='s')
    df_wdo.set_index('time', inplace=True)
    
    df = pd.DataFrame({
        'win': df_win['close'],
        'win_high': df_win['high'],
        'win_low': df_win['low'],
        'wdo': df_wdo['close']
    }).dropna()
    
    return df

def generate_wdo_zscores(df):
    print("Generating Kalman Z-Scores for WDO...")
    win = df['win'].values
    wdo = df['wdo'].values
    
    kf = KalmanBetaFilter(initial_beta=-22.5, trans_cov=1e-4, obs_cov=1e2)
    spreads = []
    for y, x in zip(win, wdo):
        beta, spread, _ = kf.update(float(y), float(x))
        spreads.append(spread)
        
    df['z_wdo'] = KalmanBetaFilter.rolling_zscore(spreads, window=40)
    return df

def simulate_isolated_wdo(args):
    df_records, z_entry, z_att = args
    
    # Sig logic for WDO isolated
    # Buy WIN when z_wdo <= -z_entry (after passing -z_att)
    # Sell WIN when z_wdo >= z_entry (after passing z_att)
    # A simplified logic without state tracking for attention:
    # Since we want to just test basic thresholds, we can just trigger on z_entry
    # However, to be true to the system, Z_ATTENTION acts as a pre-requisite.
    # We will simulate exactly: state 0 (neutral), state 1 (attention buy), state 2 (attention sell)
    
    pnl_total = 0
    max_dd = 0
    trades_count = 0
    wins_count = 0
    
    trades = []
    open_trade = None
    
    # Pre-extract arrays for speed
    z_wdo = df_records['z_wdo'].values
    win_c = df_records['win'].values
    win_h = df_records['win_high'].values
    win_l = df_records['win_low'].values
    times = df_records.index.values
    
    for i in range(len(win_c)):
        dt = pd.to_datetime(times[i])
        cur_time = dt.time()
        
        # Check Exits
        if open_trade is not None:
            hit_sl, hit_tp, hit_time = False, False, False
            exit_price = None
            
            if open_trade['dir'] == 1: # BUY
                if win_l[i] <= open_trade['ep'] - SL_PTS:
                    hit_sl, exit_price = True, open_trade['ep'] - SL_PTS
                elif win_h[i] >= open_trade['ep'] + TP_PTS:
                    hit_tp, exit_price = True, open_trade['ep'] + TP_PTS
            else: # SELL
                if win_h[i] >= open_trade['ep'] + SL_PTS:
                    hit_sl, exit_price = True, open_trade['ep'] + SL_PTS
                elif win_l[i] <= open_trade['ep'] - TP_PTS:
                    hit_tp, exit_price = True, open_trade['ep'] - TP_PTS
                    
            if cur_time >= FORCE_CLOSE:
                hit_time, exit_price = True, win_c[i]
                
            if hit_sl or hit_tp or hit_time:
                pnl = (exit_price - open_trade['ep']) if open_trade['dir'] == 1 else (open_trade['ep'] - exit_price)
                trades.append(pnl)
                open_trade = None
                continue
                
        # Check Entries
        if open_trade is None:
            if cur_time < ALLOWED_START or cur_time >= ALLOWED_END:
                continue
                
            # Simulate Attention & Entry (Simplified: if z crosses entry, we assume attention was crossed)
            # In real system, Z must hit Attention first, then Entry. 
            # In backtest, if Z is >= Z_ENTRY, it mathematically had to cross Z_ATTENTION at some point.
            # So for isolated WDO, hitting Z_ENTRY is enough, but varying Z_ATTENTION in reality 
            # affects the consensus state machine. For isolated WDO, Z_ATTENTION is mostly cosmetic unless it's a gap condition.
            # We'll just trigger on Z_ENTRY.
            if z_wdo[i] <= -z_entry:
                open_trade = {'dir': 1, 'ep': win_c[i]}
            elif z_wdo[i] >= z_entry:
                open_trade = {'dir': -1, 'ep': win_c[i]}
                
    # Calculate stats
    if len(trades) > 0:
        trades_arr = np.array(trades)
        pnl_total = np.sum(trades_arr)
        wins_count = np.sum(trades_arr > 0)
        trades_count = len(trades_arr)
        cum_pnl = np.cumsum(trades_arr)
        peak = np.maximum.accumulate(cum_pnl)
        drawdown = peak - cum_pnl
        max_dd = np.max(drawdown)
        
    ret_dd = pnl_total / max_dd if max_dd > 0 else (pnl_total if pnl_total > 0 else 0)
    
    return {
        'Z_ENTRY_WDO': z_entry,
        'Z_ATTENTION': z_att,
        'Trades': trades_count,
        'WinRate': (wins_count / trades_count * 100) if trades_count > 0 else 0,
        'PnL': pnl_total,
        'MaxDD': max_dd,
        'RetDD': ret_dd
    }

def main():
    df = fetch_data()
    if df is None: return
    df = generate_wdo_zscores(df)
    
    z_entries = np.arange(1.4, 2.6, 0.1)
    z_atts = np.arange(1.2, 1.7, 0.1)
    
    # Filter combinations where Z_ATTENTION < Z_ENTRY
    combos = [(round(e,1), round(a,1)) for e in z_entries for a in z_atts if a < e]
    print(f"Testing {len(combos)} combinations for WDO Isolated...")
    
    args_list = [(df, e, a) for e, a in combos]
    
    results = []
    # Usando multiprocessing para acelerar
    with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
        for i, res in enumerate(pool.imap_unordered(simulate_isolated_wdo, args_list)):
            results.append(res)
            print(f"Progress: {i+1}/{len(combos)}", end='\r')
            
    print("\nProcessing results...")
    res_df = pd.DataFrame(results)
    res_df.sort_values('RetDD', ascending=False, inplace=True)
    
    # Save CSV
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_1_zscores")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "wdo_zscore_grid.csv")
    res_df.to_csv(csv_path, index=False)
    
    # Plot Heatmap
    heatmap_data = res_df.pivot_table(index='Z_ATTENTION', columns='Z_ENTRY_WDO', values='RetDD', aggfunc='mean')
    plt.figure(figsize=(10, 6))
    sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap="RdYlGn", cbar_kws={'label': 'Ret/DD'})
    plt.title("WDO Isolated Optimization - Ret/DD")
    plt.tight_layout()
    png_path = os.path.join(out_dir, "heatmap_wdo_zscore.png")
    plt.savefig(png_path)
    
    print("\n--- TOP 5 WDO CONFIGURATIONS ---")
    print(res_df.head(5).to_string(index=False))
    print(f"\nSaved full results to: {csv_path}")
    print(f"Saved heatmap to: {png_path}")

if __name__ == "__main__":
    main()
