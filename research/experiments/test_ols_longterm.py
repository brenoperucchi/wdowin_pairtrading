import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from research.test_supreme_longterm import fetch_local_history
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades
from core.signals import calc_nwe_with_bands

def rolling_ols(y, x, window):
    """
    Computes rolling OLS beta, spread and z-score for arrays y (WIN) and x (WDO).
    Uses pandas rolling for efficient computation.
    """
    # Create pandas Series
    s_y = pd.Series(y)
    s_x = pd.Series(x)
    
    # Calculate rolling covariance and variance
    cov = s_y.rolling(window=window).cov(s_x)
    var = s_x.rolling(window=window).var()
    
    beta = cov / var
    # Fill NA for the first 'window' bars with 1.0 or the first valid beta
    beta = beta.bfill().fillna(1.0).values
    
    spread = y - (beta * x)
    s_spread = pd.Series(spread)
    
    # Z-Score = (Spread - Mean(Spread)) / Std(Spread)
    mean_spread = s_spread.rolling(window=window).mean()
    std_spread = s_spread.rolling(window=window).std()
    
    # Backfill first 'window' bars to avoid NaNs
    mean_spread = mean_spread.bfill().fillna(0).values.copy()
    std_spread = std_spread.bfill().fillna(1).values.copy()
    
    std_spread = np.where(std_spread == 0, 1.0, std_spread) # Prevent division by zero
    
    z_score = (spread - mean_spread) / std_spread
    return beta, spread, z_score

def run_ols_longterm():
    print("--- OLS VS KALMAN 5 YEAR BACKTEST ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    # Constants for Supreme Setup
    z_wdo_val = 2.0
    z_di_val = 3.0
    z_att_val = 1.6
    sl_val = 200
    tp_val = 500
    sh = 9
    eh = 16
    wb = 1
    
    # Pre-calculate NWE (it's the same regardless of Z-Score method)
    print("Calculating NWE (might take a minute)...")
    nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=5, lookback=150, mult_mae=1.0)
    mae = upper_nwe - nwe
    upper = nwe + mae * 5.0
    lower = nwe - mae * 5.0
    bw = upper - lower
    
    valid_buy = (~is_up) & (win_prices <= lower + bw * 0.0)
    valid_sell = (is_up) & (win_prices >= upper - bw * 0.0)
    
    windows = [40, 80, 160, 320]
    results = []
    
    plt.figure(figsize=(14, 7))
    
    print("Starting OLS Grid Evaluation...")
    for w in windows:
        print(f"  -> Testing OLS Window: {w} bars")
        
        # Calculate OLS Z-Scores
        _, _, z_wdo_ols = rolling_ols(win_prices, wdo_prices, w)
        _, _, z_di_ols = rolling_ols(win_prices, di_prices, w)
        
        # Build signals
        df_base['z_wdo'] = z_wdo_ols
        df_base['z_di'] = z_di_ols
        
        sig_wdo_strong = np.where(z_wdo_ols <= -z_wdo_val, 1, np.where(z_wdo_ols >= z_wdo_val, -1, 0))
        sig_di_strong = np.where(z_di_ols <= -z_di_val, 1, np.where(z_di_ols >= z_di_val, -1, 0))
        sig_wdo = np.where(z_wdo_ols <= -z_att_val, 1, np.where(z_wdo_ols >= z_att_val, -1, 0))
        sig_di = np.where(z_di_ols <= -z_att_val, 1, np.where(z_di_ols >= z_att_val, -1, 0))
        
        buy_mask = ((sig_wdo_strong == 1) & (sig_di == 1)) | ((sig_wdo == 1) & (sig_di_strong == 1))
        sell_mask = ((sig_wdo_strong == -1) & (sig_di == -1)) | ((sig_wdo == -1) & (sig_di_strong == -1))
        
        df_sig = df_base.copy()
        df_sig['signal'] = 0
        df_sig.loc[buy_mask & valid_buy, 'signal'] = 1
        df_sig.loc[sell_mask & valid_sell, 'signal'] = -1
        
        # Backtest
        trades = run_backtest_cooldown(df_sig, sl_pts=sl_val, tp_pts=tp_val, start_h=sh, end_h=eh, wait_bars=wb)
        pnl, dd, ret_dd, t_count = evaluate_trades(trades)
        wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
        
        results.append({
            'Model': f'OLS_{w}',
            'Trades': t_count,
            'WinRate': round(wr, 2),
            'PnL': pnl,
            'MaxDD': dd,
            'Ret_DD': round(ret_dd, 2)
        })
        
        # Plot
        df_tb = pd.DataFrame(trades)
        if not df_tb.empty:
            df_tb['cum'] = df_tb['pnl'].cumsum()
            plt.plot(df_tb['cum'].tolist(), label=f'OLS Window {w} (PnL: {pnl} | DD: {dd})', linewidth=2)
            
    # Draw Kalman result for comparison (from previous phase)
    # Kalman with NWE resulted in PnL: 8310, DD: 6800. We just draw a baseline for reference, 
    # or we can plot it properly if we recalculate it, but text reference is fine.
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "ols_v_kalman")
    os.makedirs(out_dir, exist_ok=True)
    
    df_res = pd.DataFrame(results).sort_values(by='Ret_DD', ascending=False)
    print("\n--- RELATÓRIO OLS FINAL ---")
    print(df_res.to_string(index=False))
    
    csv_path = os.path.join(out_dir, "ols_grid_report.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"\nReport saved to {csv_path}")
    
    plt.title('Backtest Mestre (5 Anos): Impacto das Janelas OLS no Setup Supremo')
    plt.xlabel('Número de Trades')
    plt.ylabel('PnL (Pontos)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    plot_path = os.path.join(out_dir, "master_5_years_ols.png")
    plt.savefig(plot_path)
    print(f"Plot saved to {plot_path}")

if __name__ == "__main__":
    run_ols_longterm()
