import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from research.test_supreme_longterm import fetch_local_history
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades

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

def run_wdo_isolated():
    print("--- HYBRID V1: WDO ISOLATED (NO NWE) ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    print("Calculating OLS 40 for WDO...")
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    # Exits otimizados pelo consenso híbrido
    sl = 300
    tp = 500
    
    wdo_results = []
    
    # Grid de Z-Score isolado
    for z in np.arange(2.0, 4.1, 0.2):
        z = round(z, 1)
        
        df_sig = df_base.copy()
        df_sig['signal'] = 0
        
        sig_buy = (z_wdo <= -z)
        sig_sell = (z_wdo >= z)
        
        df_sig.loc[sig_buy, 'signal'] = 1
        df_sig.loc[sig_sell, 'signal'] = -1
        
        trades = run_backtest_cooldown(df_sig, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
        pnl, dd, ret_dd, t_count = evaluate_trades(trades)
        wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
        
        wdo_results.append({
            'Z_WDO': z,
            'Trades': t_count,
            'WinRate': round(wr, 2),
            'PnL': pnl,
            'MaxDD': dd,
            'Ret_DD': round(ret_dd, 2)
        })
        
    df_res = pd.DataFrame(wdo_results).sort_values('Ret_DD', ascending=False)
    print("\n--- RESULTADOS: WDO ISOLADO OLS (SEM NWE) ---")
    print(df_res.to_string(index=False))

if __name__ == "__main__":
    run_wdo_isolated()
