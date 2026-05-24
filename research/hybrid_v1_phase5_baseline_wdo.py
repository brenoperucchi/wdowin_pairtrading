import sys
import os
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

def run_wdo_baseline():
    print("--- BASELINE WDO ISOLADO (Z=2.2) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    print("Calculating OLS 40 for WDO...")
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    # Calc NWE Bandwidth 5
    nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=5, lookback=150, mult_mae=1.0)
    mae = upper_nwe - nwe
    upper = nwe + mae * 5.0
    lower = nwe - mae * 5.0
    valid_buy_nwe = (~is_up) & (win_prices <= lower)
    valid_sell_nwe = (is_up) & (win_prices >= upper)
    
    sl = 300
    tp = 500
    z_val = 2.2
    
    sig_buy = (z_wdo <= -z_val)
    sig_sell = (z_wdo >= z_val)
    
    # TEST 1: WDO 2.2 SEM NWE
    df_sig1 = df_base.copy()
    df_sig1['signal'] = 0
    df_sig1.loc[sig_buy, 'signal'] = 1
    df_sig1.loc[sig_sell, 'signal'] = -1
    
    trades1 = run_backtest_cooldown(df_sig1, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
    pnl1, dd1, ret_dd1, t_count1 = evaluate_trades(trades1)
    wr1 = (len([t for t in trades1 if t['pnl'] > 0]) / len(trades1)) * 100 if trades1 else 0
    
    # TEST 2: WDO 2.2 COM NWE BW=5
    df_sig2 = df_base.copy()
    df_sig2['signal'] = 0
    df_sig2.loc[sig_buy & valid_buy_nwe, 'signal'] = 1
    df_sig2.loc[sig_sell & valid_sell_nwe, 'signal'] = -1
    
    trades2 = run_backtest_cooldown(df_sig2, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
    pnl2, dd2, ret_dd2, t_count2 = evaluate_trades(trades2)
    wr2 = (len([t for t in trades2 if t['pnl'] > 0]) / len(trades2)) * 100 if trades2 else 0
    
    print("\n[RESULTADO 1: WDO 2.2 ISOLADO - SEM NWE]")
    print(f"Trades: {t_count1}")
    print(f"Win Rate: {wr1:.2f}%")
    print(f"PnL: {pnl1}")
    print(f"MaxDD: {dd1}")
    print(f"Ret/DD: {ret_dd1:.2f}")
    
    print("\n[RESULTADO 2: WDO 2.2 ISOLADO - COM NWE (Bandwidth=5)]")
    print(f"Trades: {t_count2}")
    print(f"Win Rate: {wr2:.2f}%")
    print(f"PnL: {pnl2}")
    print(f"MaxDD: {dd2}")
    print(f"Ret/DD: {ret_dd2:.2f}")

if __name__ == "__main__":
    run_wdo_baseline()
