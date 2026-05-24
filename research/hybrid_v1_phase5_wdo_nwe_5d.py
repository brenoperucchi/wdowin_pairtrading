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
    beta = (cov / var).bfill().fillna(1.0).values
    spread = y - (beta * x)
    s = pd.Series(spread)
    mu = s.rolling(window=window).mean().bfill().fillna(0).values.copy()
    sd = s.rolling(window=window).std().bfill().fillna(1).values.copy()
    sd = np.where(sd == 0, 1.0, sd)
    return beta, spread, (spread - mu) / sd

def run_full_nwe_grid():
    print("=" * 70)
    print("  WDO ISOLADO: GRID 5D COMPLETO DO NWE")
    print("=" * 70)
    
    df_base = fetch_local_history()
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    print("Calculating OLS 40...")
    _, _, z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    z_val = 2.2
    sl, tp = 300, 500
    
    sig_buy_z = (z_wdo <= -z_val)
    sig_sell_z = (z_wdo >= z_val)
    
    # Grid ranges (ajustados pelo usuario)
    bw_range = [1, 2, 3, 4, 5]
    lb_range = [50, 100, 150, 200]
    mae_range = [1.5, 2.0, 2.5, 3.0]
    prox_range = [0.0, 0.10, 0.15, 0.20]
    isup_range = [True, False]
    
    total = len(bw_range) * len(lb_range) * len(mae_range) * len(prox_range) * len(isup_range)
    print(f"Total combinations: {total}")
    
    # Pre-compute NWE for each (bw, lb) pair to avoid redundant recalculation
    print("Pre-computing NWE for all (BW, LB) pairs...")
    nwe_cache = {}
    for bw in bw_range:
        for lb in lb_range:
            nwe, upper_nwe, lower_nwe, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
            mae_raw = upper_nwe - nwe  # MAE with mult=1.0, so this is the raw MAE
            nwe_cache[(bw, lb)] = (nwe, mae_raw, is_up)
    print(f"NWE cache built: {len(nwe_cache)} pairs")
    
    results = []
    counter = 0
    start_time = time.time()
    
    for bw in bw_range:
        for lb in lb_range:
            nwe, mae_raw, is_up = nwe_cache[(bw, lb)]
            
            for mae_mult in mae_range:
                upper = nwe + mae_raw * mae_mult
                lower = nwe - mae_raw * mae_mult
                bw_width = upper - lower  # largura total da banda
                
                for prox_pct in prox_range:
                    # Ajustar bandas com proximity
                    lower_adj = lower + bw_width * prox_pct
                    upper_adj = upper - bw_width * prox_pct
                    
                    for use_isup in isup_range:
                        counter += 1
                        
                        if use_isup:
                            valid_buy = (~is_up) & (win_prices <= lower_adj)
                            valid_sell = (is_up) & (win_prices >= upper_adj)
                        else:
                            valid_buy = (win_prices <= lower_adj)
                            valid_sell = (win_prices >= upper_adj)
                        
                        df_sig = df_base.copy()
                        df_sig['signal'] = 0
                        df_sig.loc[sig_buy_z & valid_buy, 'signal'] = 1
                        df_sig.loc[sig_sell_z & valid_sell, 'signal'] = -1
                        
                        trades = run_backtest_cooldown(df_sig, sl_pts=sl, tp_pts=tp, start_h=9, end_h=16, wait_bars=2)
                        pnl, dd, ret_dd, t_count = evaluate_trades(trades)
                        wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
                        
                        results.append({
                            'BW': bw,
                            'Lookback': lb,
                            'MAE_Mult': mae_mult,
                            'Prox_Pct': prox_pct,
                            'Use_IsUp': use_isup,
                            'Trades': t_count,
                            'WinRate': round(wr, 2),
                            'PnL': pnl,
                            'MaxDD': dd,
                            'Ret_DD': round(ret_dd, 2)
                        })
                        
                        if counter % 50 == 0:
                            elapsed = time.time() - start_time
                            eta = (elapsed / counter) * (total - counter)
                            print(f"  [{counter}/{total}] {elapsed:.0f}s elapsed | ETA: {eta:.0f}s")
    
    elapsed = time.time() - start_time
    print(f"\nGrid completo em {elapsed:.0f}s")
    
    df_res = pd.DataFrame(results)
    
    # Salvar CSV completo
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                           "data", "reports", "hybrid_v1", "phase5_wdo_nwe_grid")
    os.makedirs(out_dir, exist_ok=True)
    csv_all = os.path.join(out_dir, "wdo_nwe_5d_full.csv")
    df_res.sort_values('Ret_DD', ascending=False).to_csv(csv_all, index=False)
    
    # Filtrar >= 400 trades
    df_400 = df_res[df_res['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    csv_400 = os.path.join(out_dir, "wdo_nwe_5d_400plus.csv")
    df_400.to_csv(csv_400, index=False)
    
    print(f"\n{'=' * 70}")
    print(f"  RESULTADOS: SETUPS COM >= 400 TRADES")
    print(f"{'=' * 70}")
    
    if len(df_400) == 0:
        print("NENHUM setup atingiu 400 trades! Mostrando top 20 geral:")
        print(df_res.sort_values('Ret_DD', ascending=False).head(20).to_string(index=False))
    else:
        print(f"Total setups com >= 400 trades: {len(df_400)}")
        print(f"\nTOP 20:")
        print(df_400.head(20).to_string(index=False))
    
    print(f"\nCSV completo: {csv_all}")
    print(f"CSV 400+: {csv_400}")

if __name__ == "__main__":
    run_full_nwe_grid()
