"""
DI_NWE: Pipeline completo de otimizacao - Fases 1 a 4
Modelo base: Kalman (delta=1e-4, vt=1e-3) - TRAVADO
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
                       "data", "reports", "hybrid_v1", "phase6_di_pipeline")
os.makedirs(OUT_DIR, exist_ok=True)

class KalmanFilter:
    def __init__(self, delta=1e-4, vt=1e-3):
        self.delta = delta
        self.vt = vt
        self.beta = np.zeros(2)
        self.P = np.zeros((2, 2))
        
    def step(self, x, y):
        F = np.array([x, 1.0])
        R = self.P + np.eye(2) * self.delta
        y_hat = np.dot(F, self.beta)
        e = y - y_hat
        Q = np.dot(F, np.dot(R, F.T)) + self.vt
        K = np.dot(R, F.T) / Q
        self.beta = self.beta + K * e
        self.P = R - np.outer(K, np.dot(F, R))
        return self.beta[0], e

def calc_kalman_zscore(win_prices, di_prices, window=40):
    kf = KalmanFilter(delta=1e-4, vt=1e-3)
    errors = []
    for i in range(len(win_prices)):
        _, e = kf.step(di_prices[i], win_prices[i])
        errors.append(e)
    e_arr = np.array(errors)
    s = pd.Series(e_arr)
    mu = s.rolling(window=window).mean().bfill().fillna(0).values
    sd = s.rolling(window=window).std().bfill().fillna(1).values
    sd = np.where(sd == 0, 1.0, sd)
    return (e_arr - mu) / sd

def build_nwe_mask(win_prices, bw, lb, mae_mult, prox_pct, use_isup):
    nwe, upper_nwe, _, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
    mae_raw = upper_nwe - nwe
    upper = nwe + mae_raw * mae_mult
    lower = nwe - mae_raw * mae_mult
    bw_width = upper - lower
    lower_adj = lower + bw_width * prox_pct
    upper_adj = upper - bw_width * prox_pct
    if use_isup:
        valid_buy = (~is_up) & (win_prices <= lower_adj)
        valid_sell = (is_up) & (win_prices >= upper_adj)
    else:
        valid_buy = (win_prices <= lower_adj)
        valid_sell = (win_prices >= upper_adj)
    return valid_buy, valid_sell

def run_bt(df_base, z_arr, z_val, valid_buy, valid_sell, sl, tp, sh, eh, wb):
    sig_buy = (z_arr <= -z_val)
    sig_sell = (z_arr >= z_val)
    df = df_base.copy()
    df['signal'] = 0
    df.loc[sig_buy & valid_buy, 'signal'] = 1
    df.loc[sig_sell & valid_sell, 'signal'] = -1
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

def main():
    t0 = time.time()
    print("=" * 70)
    print("  DI_NWE PIPELINE: FASES 1-4 (Kalman)")
    print("=" * 70)
    
    df_base = fetch_local_history()
    win_prices = df_base['win'].values
    di_prices = df_base['di'].values
    
    print("Calculating Kalman Z-Score for DI...")
    z_di = calc_kalman_zscore(win_prices, di_prices, window=40)
    
    # -- FASE 1: NWE 5D GRID -----------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 1: NWE 5D GRID")
    print("-" * 70)
    
    bw_range = [1, 2, 3, 4, 5]
    lb_range = [50, 100, 150, 200]
    mae_range = [1.5, 2.0, 2.5, 3.0]
    prox_range = [0.0, 0.10, 0.15, 0.20]
    isup_range = [True, False]
    
    total_1 = len(bw_range) * len(lb_range) * len(mae_range) * len(prox_range) * len(isup_range)
    print(f"Total: {total_1} combinacoes")
    
    # Pre-compute NWE cache
    nwe_cache = {}
    for bw in bw_range:
        for lb in lb_range:
            nwe, upper_nwe, _, is_up = calc_nwe_with_bands(win_prices, bandwidth=bw, lookback=lb, mult_mae=1.0)
            mae_raw = upper_nwe - nwe
            nwe_cache[(bw, lb)] = (nwe, mae_raw, is_up)
    
    results_1 = []
    cnt = 0
    for bw in bw_range:
        for lb in lb_range:
            nwe_v, mae_raw, is_up = nwe_cache[(bw, lb)]
            for mae_m in mae_range:
                upper = nwe_v + mae_raw * mae_m
                lower = nwe_v - mae_raw * mae_m
                bw_width = upper - lower
                for prox in prox_range:
                    lower_adj = lower + bw_width * prox
                    upper_adj = upper - bw_width * prox
                    for use_isup in isup_range:
                        cnt += 1
                        if use_isup:
                            vb = (~is_up) & (win_prices <= lower_adj)
                            vs = (is_up) & (win_prices >= upper_adj)
                        else:
                            vb = (win_prices <= lower_adj)
                            vs = (win_prices >= upper_adj)
                        
                        r = run_bt(df_base, z_di, 2.2, vb, vs, 300, 500, 9, 16, 2)
                        r.update({'BW': bw, 'LB': lb, 'MAE': mae_m, 'Prox': prox, 'IsUp': use_isup})
                        results_1.append(r)
                        
                        if cnt % 80 == 0:
                            elapsed = time.time() - t0
                            print(f"  [{cnt}/{total_1}] {elapsed:.0f}s")
    
    df_1 = pd.DataFrame(results_1)
    df_1.to_csv(os.path.join(OUT_DIR, "fase1_nwe_5d.csv"), index=False)
    df_1_400 = df_1[df_1['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    print(f"\nSetups >= 400 trades: {len(df_1_400)}")
    print(df_1_400.head(10).to_string(index=False))
    
    best_1 = pick_best(df_1)
    bw_best = int(best_1['BW'])
    lb_best = int(best_1['LB'])
    mae_best = float(best_1['MAE'])
    prox_best = float(best_1['Prox'])
    isup_best = bool(best_1['IsUp'])
    print(f"\n  >> VENCEDOR FASE 1: BW={bw_best} LB={lb_best} MAE={mae_best} Prox={prox_best} IsUp={isup_best}")
    print(f"     Trades={best_1['Trades']} | Ret/DD={best_1['Ret_DD']}")
    
    vb_best, vs_best = build_nwe_mask(win_prices, bw_best, lb_best, mae_best, prox_best, isup_best)
    
    # -- FASE 2: Z-SCORE ---------------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 2: Z-SCORE DE ENTRADA")
    print("-" * 70)
    
    z_range = [1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]
    results_2 = []
    for z in z_range:
        r = run_bt(df_base, z_di, z, vb_best, vs_best, 300, 500, 9, 16, 2)
        r['Z_DI'] = z
        results_2.append(r)
    
    df_2 = pd.DataFrame(results_2)
    df_2.to_csv(os.path.join(OUT_DIR, "fase2_zscore.csv"), index=False)
    print(df_2.sort_values('Ret_DD', ascending=False).to_string(index=False))
    
    best_2 = pick_best(df_2)
    z_best = float(best_2['Z_DI'])
    print(f"\n  >> VENCEDOR FASE 2: Z={z_best} | Trades={best_2['Trades']} | Ret/DD={best_2['Ret_DD']}")
    
    # -- FASE 3: EXITS ------------------------------------------------
    print("\n" + "-" * 70)
    print("  FASE 3: EXITS (SL / TP)")
    print("-" * 70)
    
    sl_range = list(range(300, 650, 50))   # 300,350,400,450,500,550,600
    tp_range = list(range(300, 1100, 100)) # 300,400,500,600,700,800,900,1000
    results_3 = []
    total_3 = len(sl_range) * len(tp_range)
    cnt = 0
    for sl_v in sl_range:
        for tp_v in tp_range:
            cnt += 1
            r = run_bt(df_base, z_di, z_best, vb_best, vs_best, sl_v, tp_v, 9, 16, 2)
            r['SL'] = sl_v
            r['TP'] = tp_v
            results_3.append(r)
            if cnt % 10 == 0:
                print(f"  [{cnt}/{total_3}]")
    
    df_3 = pd.DataFrame(results_3)
    df_3.to_csv(os.path.join(OUT_DIR, "fase3_exits.csv"), index=False)
    df_3_top = df_3[df_3['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    print(f"\nTOP 10 (>=400 trades):")
    print(df_3_top.head(10).to_string(index=False))
    
    best_3 = pick_best(df_3)
    sl_best = int(best_3['SL'])
    tp_best = int(best_3['TP'])
    print(f"\n  >> VENCEDOR FASE 3: SL={sl_best} TP={tp_best} | Trades={best_3['Trades']} | Ret/DD={best_3['Ret_DD']}")
    
    # -- FASE 4: HORARIO + COOLDOWN ----------------------------------
    print("\n" + "-" * 70)
    print("  FASE 4: HORARIO + COOLDOWN")
    print("-" * 70)
    
    start_range = [9, 10]
    end_range = [15, 16, 17]
    wb_range = [0, 1, 2, 3, 4, 6]
    results_4 = []
    for sh in start_range:
        for eh in end_range:
            for wb in wb_range:
                r = run_bt(df_base, z_di, z_best, vb_best, vs_best, sl_best, tp_best, sh, eh, wb)
                r['Start_H'] = sh
                r['End_H'] = eh
                r['Wait_Bars'] = wb
                results_4.append(r)
    
    df_4 = pd.DataFrame(results_4)
    df_4.to_csv(os.path.join(OUT_DIR, "fase4_horario_cooldown.csv"), index=False)
    df_4_top = df_4[df_4['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    print(df_4_top.head(10).to_string(index=False))
    
    best_4 = pick_best(df_4)
    sh_best = int(best_4['Start_H'])
    eh_best = int(best_4['End_H'])
    wb_best = int(best_4['Wait_Bars'])
    print(f"\n  >> VENCEDOR FASE 4: {sh_best}h-{eh_best}h CD={wb_best} | Trades={best_4['Trades']} | Ret/DD={best_4['Ret_DD']}")
    
    # -- RELATORIO FINAL ----------------------------------------------
    elapsed = time.time() - t0
    print("\n" + "=" * 70)
    print("  SETUP DI_NWE FINAL OTIMIZADO")
    print("=" * 70)
    print(f"  Modelo:           Kalman (delta=1e-4, vt=1e-3)")
    print(f"  Z-Score Window:   40")
    print(f"  NWE BW:           {bw_best}")
    print(f"  NWE Lookback:     {lb_best}")
    print(f"  NWE MAE Mult:     {mae_best}")
    print(f"  NWE Proximity:    {prox_best*100:.0f}%")
    print(f"  NWE is_up:        {isup_best}")
    print(f"  Z-Score Entrada:  {z_best}")
    print(f"  Stop Loss:        {sl_best}")
    print(f"  Take Profit:      {tp_best}")
    print(f"  Horario:          {sh_best}:00 - {eh_best}:00")
    print(f"  Cooldown:         {wb_best} barras ({wb_best*5} min)")
    print(f"  -----------------------------")
    print(f"  Trades:           {best_4['Trades']}")
    print(f"  Win Rate:         {best_4['WinRate']}%")
    print(f"  PnL:              {best_4['PnL']}")
    print(f"  Max Drawdown:     {best_4['MaxDD']}")
    print(f"  Ret/DD:           {best_4['Ret_DD']}")
    print(f"  -----------------------------")
    print(f"  Pipeline completo em {elapsed:.0f}s")
    
    if tp_best > 600:
        print(f"\n  !! TP={tp_best} > 600. Recomendavel adicionar fase de Break-Even.")
    else:
        print(f"\n  OK TP={tp_best} <= 600. Break-Even dispensado.")

if __name__ == "__main__":
    main()
