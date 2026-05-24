"""
WDO_NWE: Pipeline completo de otimização — Fases 2 a 5
Cada fase trava o vencedor da anterior e otimiza o próximo parâmetro.
"""
import sys, os, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from research.test_supreme_longterm import fetch_local_history
from research.optimize_phase6_cooldown import run_backtest_cooldown
from research.optimize_phase1_zscores import evaluate_trades
from core.signals import calc_nwe_with_bands

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "reports", "hybrid_v1", "phase5_wdo_pipeline")
os.makedirs(OUT_DIR, exist_ok=True)

def rolling_ols(y, x, window):
    s_y, s_x = pd.Series(y), pd.Series(x)
    cov = s_y.rolling(window=window).cov(s_x)
    var = s_x.rolling(window=window).var()
    beta = (cov / var).bfill().fillna(1.0).values
    spread = y - (beta * x)
    s = pd.Series(spread)
    mu = s.rolling(window=window).mean().bfill().fillna(0).values.copy()
    sd = s.rolling(window=window).std().bfill().fillna(1).values.copy()
    sd = np.where(sd == 0, 1.0, sd)
    return (spread - mu) / sd

def build_nwe_mask(win_prices, bw, lb, mae_mult, prox_pct):
    nwe, upper_nwe, _, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
    mae_raw = upper_nwe - nwe
    upper = nwe + mae_raw * mae_mult
    lower = nwe - mae_raw * mae_mult
    bw_width = upper - lower
    lower_adj = lower + bw_width * prox_pct
    upper_adj = upper - bw_width * prox_pct
    # is_up=False (desligado)
    valid_buy = (win_prices <= lower_adj)
    valid_sell = (win_prices >= upper_adj)
    return valid_buy, valid_sell

def run_bt(df_base, z_arr, z_val, valid_buy_nwe, valid_sell_nwe, sl, tp, sh, eh, wb):
    sig_buy = (z_arr <= -z_val)
    sig_sell = (z_arr >= z_val)
    df = df_base.copy()
    df['signal'] = 0
    df.loc[sig_buy & valid_buy_nwe, 'signal'] = 1
    df.loc[sig_sell & valid_sell_nwe, 'signal'] = -1
    trades = run_backtest_cooldown(df, sl_pts=sl, tp_pts=tp, start_h=sh, end_h=eh, wait_bars=wb)
    pnl, dd, ret_dd, tc = evaluate_trades(trades)
    wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
    return {'Trades': tc, 'WinRate': round(wr, 2), 'PnL': pnl, 'MaxDD': dd, 'Ret_DD': round(ret_dd, 2)}

def pick_best(df_res, min_trades=400):
    df_f = df_res[df_res['Trades'] >= min_trades].sort_values('Ret_DD', ascending=False)
    if len(df_f) == 0:
        df_f = df_res.sort_values('Ret_DD', ascending=False)
        print("  !! Nenhum setup >= 400 trades, usando melhor geral.")
    return df_f.iloc[0]

# ══════════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    print("=" * 70)
    print("  WDO_NWE PIPELINE: FASES 2-5")
    print("=" * 70)
    
    df_base = fetch_local_history()
    win_prices = df_base['win'].values
    wdo_prices = df_base['wdo'].values
    
    z_wdo = rolling_ols(win_prices, wdo_prices, 40)
    
    # NWE travado (Fase 1)
    valid_buy_nwe, valid_sell_nwe = build_nwe_mask(win_prices, bw=1, lb=100, mae_mult=2.0, prox_pct=0.15)
    
    # -- FASE 2: Z-SCORE ----------------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 2: Z-SCORE DE ENTRADA")
    print("-" * 70)
    
    z_range = [1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]
    results_2 = []
    for z in z_range:
        r = run_bt(df_base, z_wdo, z, valid_buy_nwe, valid_sell_nwe, 300, 500, 9, 16, 2)
        r['Z_WDO'] = z
        results_2.append(r)
    
    df_2 = pd.DataFrame(results_2)
    df_2.to_csv(os.path.join(OUT_DIR, "fase2_zscore.csv"), index=False)
    print(df_2.sort_values('Ret_DD', ascending=False).to_string(index=False))
    
    best_2 = pick_best(df_2)
    z_best = best_2['Z_WDO']
    print(f"\n  >> VENCEDOR FASE 2: Z={z_best} | Trades={best_2['Trades']} | Ret/DD={best_2['Ret_DD']}")
    
    # -- FASE 3: EXITS (SL / TP) --------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 3: EXITS (SL / TP)")
    print("-" * 70)
    
    sl_range = [150, 200, 250, 300, 350, 400, 500]
    tp_range = [200, 300, 400, 500, 600, 800, 1000]
    results_3 = []
    total_3 = len(sl_range) * len(tp_range)
    cnt = 0
    for sl_v in sl_range:
        for tp_v in tp_range:
            cnt += 1
            r = run_bt(df_base, z_wdo, z_best, valid_buy_nwe, valid_sell_nwe, sl_v, tp_v, 9, 16, 2)
            r['SL'] = sl_v
            r['TP'] = tp_v
            results_3.append(r)
            if cnt % 10 == 0:
                print(f"  [{cnt}/{total_3}]")
    
    df_3 = pd.DataFrame(results_3)
    df_3.to_csv(os.path.join(OUT_DIR, "fase3_exits.csv"), index=False)
    df_3_top = df_3[df_3['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    print("\nTOP 10 (>=400 trades):")
    print(df_3_top.head(10).to_string(index=False))
    
    best_3 = pick_best(df_3)
    sl_best = int(best_3['SL'])
    tp_best = int(best_3['TP'])
    print(f"\n  >> VENCEDOR FASE 3: SL={sl_best} TP={tp_best} | Trades={best_3['Trades']} | Ret/DD={best_3['Ret_DD']}")
    
    # -- FASE 4: HORÁRIO ----------------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 4: HORÁRIO DE OPERAÇÃO")
    print("-" * 70)
    
    start_range = [9, 10]  # 09:00, 10:00 (9:30 requer lógica extra em M5)
    end_range = [15, 16, 17]
    results_4 = []
    for sh in start_range:
        for eh in end_range:
            r = run_bt(df_base, z_wdo, z_best, valid_buy_nwe, valid_sell_nwe, sl_best, tp_best, sh, eh, 2)
            r['Start_H'] = sh
            r['End_H'] = eh
            results_4.append(r)
    
    df_4 = pd.DataFrame(results_4)
    df_4.to_csv(os.path.join(OUT_DIR, "fase4_horario.csv"), index=False)
    print(df_4.sort_values('Ret_DD', ascending=False).to_string(index=False))
    
    best_4 = pick_best(df_4)
    sh_best = int(best_4['Start_H'])
    eh_best = int(best_4['End_H'])
    print(f"\n  >> VENCEDOR FASE 4: {sh_best}h-{eh_best}h | Trades={best_4['Trades']} | Ret/DD={best_4['Ret_DD']}")
    
    # -- FASE 5: COOLDOWN ---------------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 5: COOLDOWN")
    print("-" * 70)
    
    wb_range = [0, 1, 2, 3, 4, 6]
    results_5 = []
    for wb in wb_range:
        r = run_bt(df_base, z_wdo, z_best, valid_buy_nwe, valid_sell_nwe, sl_best, tp_best, sh_best, eh_best, wb)
        r['Wait_Bars'] = wb
        results_5.append(r)
    
    df_5 = pd.DataFrame(results_5)
    df_5.to_csv(os.path.join(OUT_DIR, "fase5_cooldown.csv"), index=False)
    print(df_5.sort_values('Ret_DD', ascending=False).to_string(index=False))
    
    best_5 = pick_best(df_5)
    wb_best = int(best_5['Wait_Bars'])
    print(f"\n  >> VENCEDOR FASE 5: Cooldown={wb_best} bars | Trades={best_5['Trades']} | Ret/DD={best_5['Ret_DD']}")
    
    # -- RELATÓRIO FINAL ----------------------------------------------
    elapsed = time.time() - t0
    print("\n" + "=" * 70)
    print("  SETUP WDO_NWE FINAL OTIMIZADO")
    print("=" * 70)
    print(f"  OLS Window:       40")
    print(f"  NWE BW:           1")
    print(f"  NWE Lookback:     100")
    print(f"  NWE MAE Mult:     2.0")
    print(f"  NWE Proximity:    15%")
    print(f"  NWE is_up:        False")
    print(f"  Z-Score Entrada:  {z_best}")
    print(f"  Stop Loss:        {sl_best}")
    print(f"  Take Profit:      {tp_best}")
    print(f"  Horário:          {sh_best}:00 - {eh_best}:00")
    print(f"  Cooldown:         {wb_best} barras ({wb_best*5} min)")
    print(f"  -----------------------------")
    print(f"  Trades:           {best_5['Trades']}")
    print(f"  Win Rate:         {best_5['WinRate']}%")
    print(f"  PnL:              {best_5['PnL']}")
    print(f"  Max Drawdown:     {best_5['MaxDD']}")
    print(f"  Ret/DD:           {best_5['Ret_DD']}")
    print(f"  -----------------------------")
    print(f"  Pipeline completo em {elapsed:.0f}s")
    
    # Check se precisa de Break-Even
    if tp_best > 600:
        print(f"\n  !! TP={tp_best} > 600. Recomendável adicionar fase de Break-Even.")
    else:
        print(f"\n  OK TP={tp_best} ≤ 600. Break-Even dispensado.")

if __name__ == "__main__":
    main()
