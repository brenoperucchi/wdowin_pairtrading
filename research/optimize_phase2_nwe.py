import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from itertools import product

from research.backtest_matador import fetch_data, generate_signals
from research.optimize_phase1_zscores import run_backtest_fast, evaluate_trades
from core.signals import calc_nwe_with_bands

def run_phase_2():
    print("Loading data and pre-calculating base Kalman filters...")
    df_base = fetch_data()
    if df_base is None:
        print("Failed to fetch data.")
        return
        
    df_base = generate_signals(df_base)
    
    # Fixed Phase 1 parameters
    z_wdo_val = 1.5
    z_di_val = 1.7
    z_att_val = 1.3
    
    print(f"Applying Fixed Z-Scores: WDO={z_wdo_val}, DI={z_di_val}, ATT={z_att_val}")
    
    # Base Z-Score signals
    df_base['sig_wdo_strong'] = np.where(df_base['z_wdo'] <= -z_wdo_val, 1, np.where(df_base['z_wdo'] >= z_wdo_val, -1, 0))
    df_base['sig_di_strong'] = np.where(df_base['z_di'] <= -z_di_val, 1, np.where(df_base['z_di'] >= z_di_val, -1, 0))
    df_base['sig_wdo'] = np.where(df_base['z_wdo'] <= -z_att_val, 1, np.where(df_base['z_wdo'] >= z_att_val, -1, 0))
    df_base['sig_di'] = np.where(df_base['z_di'] <= -z_att_val, 1, np.where(df_base['z_di'] >= z_att_val, -1, 0))
    
    buy_mask = ((df_base['sig_wdo_strong'] == 1) & (df_base['sig_di'] == 1)) | ((df_base['sig_wdo'] == 1) & (df_base['sig_di_strong'] == 1))
    sell_mask = ((df_base['sig_wdo_strong'] == -1) & (df_base['sig_di'] == -1)) | ((df_base['sig_wdo'] == -1) & (df_base['sig_di_strong'] == -1))
    
    # Define NWE grid
    lb_range = np.arange(50, 350, 50)  # 50 to 300
    bw_range = np.arange(3, 16, 1)     # 3 to 15
    mult_range = np.arange(1.0, 5.5, 0.5) # 1.0 to 5.0
    pct_range = [0.0, 0.1, 0.2]        # % of band hit
    
    results = []
    total_iters = len(lb_range) * len(bw_range) * len(mult_range) * len(pct_range)
    print(f"Starting Grid Search Phase 2: {total_iters} combinations...")
    
    count = 0
    win_prices = df_base['win'].values
    
    for lb, bw in product(lb_range, bw_range):
        # Calculate base NWE (mult_mae=1.0) for this LB and BW
        nwe, upper_1, lower_1, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
        mae = upper_1 - nwe
        
        for mult, pct in product(mult_range, pct_range):
            count += 1
            if count % 100 == 0:
                print(f"Progress: {count}/{total_iters}")
            
            # Scale bands
            upper = nwe + mae * mult
            lower = nwe - mae * mult
            band_width = upper - lower
            
            # Apply NWE rules
            # valid_buy: NOT trending up AND price is close to or below lower band
            valid_buy_nwe = (~is_up) & (win_prices <= lower + band_width * pct)
            
            # valid_sell: NOT trending down AND price is close to or above upper band
            valid_sell_nwe = (is_up) & (win_prices >= upper - band_width * pct)
            
            df_sig = df_base.copy()
            df_sig['signal'] = 0
            df_sig.loc[buy_mask & valid_buy_nwe, 'signal'] = 1
            df_sig.loc[sell_mask & valid_sell_nwe, 'signal'] = -1
            
            # Run fast backtest
            trades = run_backtest_fast(df_sig, sl_pts=1000, tp_pts=1000)
            
            pnl, max_dd, ret_dd, total_trades = evaluate_trades(trades)
            
            results.append({
                'nwe_lb': lb,
                'nwe_bw': bw,
                'nwe_mult': mult,
                'nwe_pct': pct,
                'trades': total_trades,
                'pnl': pnl,
                'max_dd': max_dd,
                'ret_dd': ret_dd
            })
            
    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(by='ret_dd', ascending=False)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "kalman_v2", "phase_2_nwe")
    os.makedirs(out_dir, exist_ok=True)
    
    csv_path = os.path.join(out_dir, "nwe_grid.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"Grid results saved to {csv_path}")
    
    # Heatmap: Fix the best NWE_LB and NWE_PCT, plot BW vs MULT
    if len(df_res) > 0:
        best_lb = df_res.iloc[0]['nwe_lb']
        best_pct = df_res.iloc[0]['nwe_pct']
        
        df_heat = df_res[(df_res['nwe_lb'] == best_lb) & (df_res['nwe_pct'] == best_pct)]
        if not df_heat.empty:
            pivot = df_heat.pivot(index='nwe_mult', columns='nwe_bw', values='ret_dd')
            
            plt.figure(figsize=(12, 8))
            sns.heatmap(pivot, annot=True, cmap="viridis", fmt=".2f")
            plt.title(f"Phase 2 Heatmap (Ret/DD) - Fixed LB={best_lb}, PCT={best_pct}")
            plt.xlabel("NWE_BW")
            plt.ylabel("NWE_MULT")
            
            png_path = os.path.join(out_dir, "heatmap_nwe.png")
            plt.savefig(png_path)
            print(f"Heatmap saved to {png_path}")
            
if __name__ == "__main__":
    run_phase_2()
