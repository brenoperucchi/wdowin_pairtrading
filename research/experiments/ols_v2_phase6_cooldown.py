import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

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

def run_phase6():
    print("--- OLS V2: FASE 6 (COOLDOWN) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    w_val = 2.6
    d_val = 2.1
    a_val = 1.0
    sl_val = 450
    tp_val = 450
    
    _, _, z_wdo_ols = rolling_ols(win_prices, wdo_prices, 40)
    _, _, z_di_ols = rolling_ols(win_prices, di_prices, 40)
    
    df_base['z_wdo'] = z_wdo_ols
    df_base['z_di'] = z_di_ols
    
    print("Skipping NWE Filter (As requested)...")
    valid_buy = np.ones_like(win_prices, dtype=bool)
    valid_sell = np.ones_like(win_prices, dtype=bool)
    
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
    
    results = []
    
    wait_bars_range = range(0, 13) # Test up to 1h of cooldown (12 bars of M5)
    
    for wb in wait_bars_range:
        trades = run_backtest_cooldown(df_sig, sl_pts=sl_val, tp_pts=tp_val, start_h=9, end_h=16, wait_bars=wb, be_activation=0)
        pnl, dd, ret_dd, t_count = evaluate_trades(trades)
        wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
        
        results.append({
            'Wait_Bars': wb,
            'Trades': t_count,
            'WinRate': round(wr, 2),
            'PnL': pnl,
            'MaxDD': dd,
            'Ret_DD': round(ret_dd, 2)
        })
        
    df_res = pd.DataFrame(results).sort_values(by='Ret_DD', ascending=False)
    print("\n--- RESULTADOS OLS-V2 FASE 6 (COOLDOWN) ---")
    print(df_res.to_string(index=False))
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "ols_v2", "phase_6_cooldown")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "ols_cooldown_grid.csv")
    df_res.to_csv(csv_path, index=False)
    
    # Plotting Barchart
    plt.figure(figsize=(10, 6))
    sns.barplot(data=df_res, x='Wait_Bars', y='Ret_DD', palette='viridis')
    plt.title("Phase 6 OLS-V2: Cooldown Period vs Ret/DD")
    plt.xlabel('Wait Bars (M5)')
    plt.ylabel('Retorno / Max Drawdown')
    for i, row in df_res.iterrows():
        plt.text(row['Wait_Bars'], row['Ret_DD'], f"{row['Ret_DD']:.2f}\n(DD: {row['MaxDD']})", ha='center', va='bottom', fontsize=8)
        
    plt.savefig(os.path.join(out_dir, "barchart_cooldown.png"))
    print(f"\nReport and Chart saved to {out_dir}")

if __name__ == "__main__":
    run_phase6()
