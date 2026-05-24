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

def run_phase4():
    print("--- OLS V2: FASE 4 (BREAK-EVEN) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    di_prices = df_base['di'].values
    
    # Best params from Phase 1 & 3
    w_val = 2.6
    d_val = 2.1
    a_val = 1.0
    sl_val = 450
    tp_val = 450
    
    print(f"Applying OLS 40 | Z_WDO: {w_val} | Z_DI: {d_val} | Z_ATT: {a_val}")
    print(f"Exits | SL: {sl_val} | TP: {tp_val}")
    
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
    
    # Break-Even Grid
    # be_activation: 100, 150, 200, 250
    # be_trail: 20, 50, 100
    be_activations = [0, 100, 150, 200, 250, 300]
    be_trails = [20, 50, 100]
    
    results = []
    
    for be_act in be_activations:
        if be_act == 0:
            trails_to_test = [0]
        else:
            trails_to_test = be_trails
            
        for be_tr in trails_to_test:
            trades = run_backtest_cooldown(df_sig, sl_pts=sl_val, tp_pts=tp_val, start_h=9, end_h=16, wait_bars=1, 
                                           be_activation=be_act, be_trail=be_tr)
            pnl, dd, ret_dd, t_count = evaluate_trades(trades)
            wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
            
            results.append({
                'BE_Act': be_act,
                'BE_Trail': be_tr,
                'Trades': t_count,
                'WinRate': round(wr, 2),
                'PnL': pnl,
                'MaxDD': dd,
                'Ret_DD': round(ret_dd, 2)
            })
            
    df_res = pd.DataFrame(results).sort_values(by='Ret_DD', ascending=False)
    print("\n--- RESULTADOS OLS-V2 FASE 4 (BREAK-EVEN) ---")
    print(df_res.to_string(index=False))
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "ols_v2", "phase_4_breakeven")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "ols_be_grid.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"\nReport saved to {csv_path}")

if __name__ == "__main__":
    run_phase4()
