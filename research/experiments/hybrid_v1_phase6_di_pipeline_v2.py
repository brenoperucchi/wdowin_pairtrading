"""
DI_NWE Pipeline v2: NWE TRAVADO = WDO (BW=1 LB=100 MAE=2.0 Prox=15% is_up=False)
Otimiza apenas Z-Score, Exits, Horario+Cooldown
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
        self.delta, self.vt = delta, vt
        self.beta = np.zeros(2)
        self.P = np.zeros((2, 2))
    def step(self, x, y):
        F = np.array([x, 1.0])
        R = self.P + np.eye(2) * self.delta
        e = y - np.dot(F, self.beta)
        Q = np.dot(F, np.dot(R, F.T)) + self.vt
        K = np.dot(R, F.T) / Q
        self.beta = self.beta + K * e
        self.P = R - np.outer(K, np.dot(F, R))
        return self.beta[0], e

def main():
    t0 = time.time()
    print("=" * 70)
    print("  DI_NWE PIPELINE v2: NWE TRAVADO = WDO")
    print("  (BW=1 LB=100 MAE=2.0 Prox=15% is_up=False)")
    print("=" * 70)
    
    df = fetch_local_history()
    win, di = df['win'].values, df['di'].values
    
    # Kalman DI
    print("Calculando Kalman Z-Score DI...")
    kf = KalmanFilter(1e-4, 1e-3)
    errs = [kf.step(di[i], win[i])[1] for i in range(len(win))]
    e_arr = np.array(errs)
    s = pd.Series(e_arr)
    mu = s.rolling(40).mean().bfill().fillna(0).values
    sd = s.rolling(40).std().bfill().fillna(1).values
    sd = np.where(sd == 0, 1.0, sd)
    z_di = (e_arr - mu) / sd
    
    # NWE TRAVADO = WDO (BW=1, LB=100, MAE=2.0, Prox=15%, is_up=False)
    print("Aplicando NWE do WDO (BW=1, LB=100, MAE=2.0, Prox=15%)...")
    nwe, up_nwe, _, _ = calc_nwe_with_bands(win, bandwidth=1, lookback=100, mult_mae=1.0)
    mae_raw = up_nwe - nwe
    upper = nwe + mae_raw * 2.0
    lower = nwe - mae_raw * 2.0
    bw_width = upper - lower
    lower_adj = lower + bw_width * 0.15
    upper_adj = upper - bw_width * 0.15
    vb_nwe = (win <= lower_adj)
    vs_nwe = (win >= upper_adj)
    
    def run_bt(z_val, sl, tp, sh, eh, wb):
        sig_buy = (z_di <= -z_val)
        sig_sell = (z_di >= z_val)
        d = df.copy()
        d['signal'] = 0
        d.loc[sig_buy & vb_nwe, 'signal'] = 1
        d.loc[sig_sell & vs_nwe, 'signal'] = -1
        trades = run_backtest_cooldown(d, sl_pts=sl, tp_pts=tp, start_h=sh, end_h=eh, wait_bars=wb)
        pnl, dd, ret_dd, tc = evaluate_trades(trades)
        wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
        return {'Trades': tc, 'WinRate': round(wr, 2), 'PnL': pnl, 'MaxDD': dd, 'Ret_DD': round(ret_dd, 2)}
    
    def pick_best(df_res, min_t=400):
        f = df_res[df_res['Trades'] >= min_t].sort_values('Ret_DD', ascending=False)
        if len(f) == 0:
            f = df_res.sort_values('Ret_DD', ascending=False)
            print("  !! Nenhum >= 400 trades, usando melhor geral")
        return f.iloc[0]
    
    # FASE 2: Z-SCORE
    print("\n" + "-" * 70)
    print("  FASE 2: Z-SCORE")
    print("-" * 70)
    results_2 = []
    for z in [1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]:
        r = run_bt(z, 300, 500, 9, 16, 2)
        r['Z_DI'] = z
        results_2.append(r)
    df_2 = pd.DataFrame(results_2)
    df_2.to_csv(os.path.join(OUT_DIR, "fase2v2_zscore.csv"), index=False)
    print(df_2.sort_values('Ret_DD', ascending=False).to_string(index=False))
    best_2 = pick_best(df_2)
    z_best = float(best_2['Z_DI'])
    print(f"\n  >> VENCEDOR: Z={z_best} | Trades={best_2['Trades']} | Ret/DD={best_2['Ret_DD']}")
    
    # FASE 3: EXITS
    print("\n" + "-" * 70)
    print("  FASE 3: EXITS (SL / TP)")
    print("-" * 70)
    sl_range = list(range(300, 650, 50))
    tp_range = list(range(300, 1100, 100))
    results_3 = []
    total_3 = len(sl_range) * len(tp_range)
    cnt = 0
    for sl_v in sl_range:
        for tp_v in tp_range:
            cnt += 1
            r = run_bt(z_best, sl_v, tp_v, 9, 16, 2)
            r['SL'] = sl_v
            r['TP'] = tp_v
            results_3.append(r)
            if cnt % 10 == 0:
                print(f"  [{cnt}/{total_3}]")
    df_3 = pd.DataFrame(results_3)
    df_3.to_csv(os.path.join(OUT_DIR, "fase3v2_exits.csv"), index=False)
    df_3t = df_3[df_3['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    print("TOP 10:")
    print(df_3t.head(10).to_string(index=False))
    best_3 = pick_best(df_3)
    sl_best = int(best_3['SL'])
    tp_best = int(best_3['TP'])
    print(f"\n  >> VENCEDOR: SL={sl_best} TP={tp_best} | Trades={best_3['Trades']} | Ret/DD={best_3['Ret_DD']}")
    
    # FASE 4: HORARIO + COOLDOWN
    print("\n" + "-" * 70)
    print("  FASE 4: HORARIO + COOLDOWN")
    print("-" * 70)
    results_4 = []
    for sh in [9, 10]:
        for eh in [15, 16, 17]:
            for wb in [0, 1, 2, 3, 4, 6]:
                r = run_bt(z_best, sl_best, tp_best, sh, eh, wb)
                r['Start_H'] = sh
                r['End_H'] = eh
                r['Wait_Bars'] = wb
                results_4.append(r)
    df_4 = pd.DataFrame(results_4)
    df_4.to_csv(os.path.join(OUT_DIR, "fase4v2_horario.csv"), index=False)
    df_4t = df_4[df_4['Trades'] >= 400].sort_values('Ret_DD', ascending=False)
    print(df_4t.head(10).to_string(index=False))
    best_4 = pick_best(df_4)
    sh_b = int(best_4['Start_H'])
    eh_b = int(best_4['End_H'])
    wb_b = int(best_4['Wait_Bars'])
    print(f"\n  >> VENCEDOR: {sh_b}h-{eh_b}h CD={wb_b} | Trades={best_4['Trades']} | Ret/DD={best_4['Ret_DD']}")
    
    # RELATORIO FINAL
    elapsed = time.time() - t0
    print("\n" + "=" * 70)
    print("  SETUP DI_NWE FINAL (NWE = WDO)")
    print("=" * 70)
    print(f"  Modelo:           Kalman (1e-4, 1e-3)")
    print(f"  NWE:              BW=1 LB=100 MAE=2.0 Prox=15% is_up=False (=WDO)")
    print(f"  Z-Score:          {z_best}")
    print(f"  SL:               {sl_best}")
    print(f"  TP:               {tp_best}")
    print(f"  Horario:          {sh_b}:00 - {eh_b}:00")
    print(f"  Cooldown:         {wb_b} barras ({wb_b * 5} min)")
    print(f"  ---")
    print(f"  Trades:           {best_4['Trades']}")
    print(f"  Win Rate:         {best_4['WinRate']}%")
    print(f"  PnL:              {best_4['PnL']}")
    print(f"  Max DD:           {best_4['MaxDD']}")
    print(f"  Ret/DD:           {best_4['Ret_DD']}")
    print(f"  Pipeline em {elapsed:.0f}s")
    if tp_best > 600:
        print(f"  !! TP={tp_best}>600 - Break-Even recomendado")

if __name__ == "__main__":
    main()
