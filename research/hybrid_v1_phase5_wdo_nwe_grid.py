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

def run_wdo_nwe_3d_grid():
    print("--- OTIMIZACAO WDO ISOLADO FASE 1: NWE BW x LOOKBACK x MAE MULTIPLIER ---")
    df_base = fetch_local_history()
    
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    print("Calculating OLS 40 for WDO...")
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    # Travados:
    z_val = 2.2
    sl = 300
    tp = 500
    
    sig_buy = (z_wdo <= -z_val)
    sig_sell = (z_wdo >= z_val)
    
    # 3D Grid de otimizacao (incluso o MAE Multiplier pedido pelo usuario)
    bw_range = [3, 5, 8, 10]
    lookback_range = [50, 95, 150, 200]
    mae_range = [1.0, 2.0, 3.0, 4.0, 5.0]
    
    results = []
    total_iters = len(bw_range) * len(lookback_range) * len(mae_range)
    print(f"Total combinations: {total_iters}")
    
    counter = 0
    start_time = time.time()
    
    for bw in bw_range:
        for lb in lookback_range:
            for mae_mult in mae_range:
                counter += 1
                
                nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
                mae = upper_nwe - nwe
                # Aqui entra o MAE multiplier customizado!
                upper = nwe + mae * mae_mult
                lower = nwe - mae * mae_mult
                
                valid_buy_nwe = (~is_up) & (win_prices <= lower)
                valid_sell_nwe = (is_up) & (win_prices >= upper)
                
                df_sig = df_base.copy()
                df_sig['signal'] = 0
                df_sig.loc[sig_buy & valid_buy_nwe, 'signal'] = 1
                df_sig.loc[sig_sell & valid_sell_nwe, 'signal'] = -1
                
                trades = run_backtest_cooldown(df_sig, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
                pnl, dd, ret_dd, t_count = evaluate_trades(trades)
                wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
                
                results.append({
                    'BW': bw,
                    'Lookback': lb,
                    'MAE_Mult': mae_mult,
                    'Trades': t_count,
                    'WinRate': round(wr, 2),
                    'PnL': pnl,
                    'MaxDD': dd,
                    'Ret_DD': round(ret_dd, 2)
                })
                
                if counter % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"Progresso: {counter}/{total_iters} | Tempo: {elapsed:.1f}s")
                
    df_res = pd.DataFrame(results).sort_values('Ret_DD', ascending=False)
    print("\n--- RESULTADOS: NWE BW VS LOOKBACK VS MAE (WDO 2.2) ---")
    print(df_res.head(20).to_string(index=False)) # Mostrar top 20
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports", "hybrid_v1", "phase5_wdo_nwe_grid")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "wdo_nwe_3d_grid.csv")
    df_res.to_csv(csv_path, index=False)
    print(f"\nReport saved to {csv_path}")

if __name__ == "__main__":
    run_wdo_nwe_3d_grid()
