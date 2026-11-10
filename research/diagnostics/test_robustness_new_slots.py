"""
BATERIA DE TESTES DE ROBUSTEZ: EST-03, EST-05, WDO-01 E WDO-05
==============================================================
Testes obrigatórios antes do deploy:
1. Walk-Forward / Out-of-Sample (IS: 11/05 a 31/08 | OOS: 01/09 a 04/11)
2. Estresse de Custos B3 e Slippage (1.0x, 1.5x, 2.0x)
3. Consistência Mensal (Mês a Mês: Maio a Novembro)
4. Matriz de Correlação com os Robôs Ativos
"""

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_gex_nwe_setups import compute_nwe_series
from research.mt5_loader import load_gex_csv, HIST_WIN, HIST_WDO, get_mt5_rates
import research.optimizers.optimize_existing_16_setups as o16
import research.optimizers.wdo_mt5_sim as wdo_sim

START_DATE = "2026-05-11"
SPLIT_DATE = "2026-09-01"
END_DATE = "2026-11-04"

def get_stats(trades, pt_val=0.20):
    if not trades:
        return {"tr": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "mdd": 0.0, "ret_dd": 0.0}
    n = len(trades)
    # se o trade já tem 'pnl_brl', usa ele; senão usa pts * pt_val
    pnls = [t.get("pnl_brl", t.get("pts", 0.0) * pt_val) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    wr = round(wins / n * 100.0, 1)
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = round(gw / gl, 2) if gl > 1e-6 else 99.9
    net = round(sum(pnls), 2)
    
    by_day = {}
    for t, p in zip(trades, pnls):
        d = t["date"]
        by_day[d] = by_day.get(d, 0.0) + p
    cum = np.cumsum([by_day[d] for d in sorted(by_day.keys())])
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    mdd = round(float(np.max(pk - cum)), 2) if len(cum) else 0.0
    ret_dd = round(net / mdd, 2) if mdd > 0 else 99.9
    return {"tr": n, "wr": wr, "pf": pf, "net": net, "mdd": mdd, "ret_dd": ret_dd}

def run_win_slot(est_id, cost_pts=10.0, start_d=START_DATE, end_d=END_DATE):
    # Carrega dados M5 alinhados com WDO
    from research.optimizers.test_win_aligned_wdo_matrix import load_win_and_wdo_aligned
    df, gex_by_date = load_win_and_wdo_aligned()
    df = df[(df["session_date"] >= start_d) & (df["session_date"] <= end_d)].reset_index(drop=True)
    
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    
    # Simula slot
    res = o16.simulate_single_est_slot(
        est_id, df, gex_by_date,
        n50_c, n50_u, n50_l, n50_s,
        n30_c, n30_u, n30_l, n30_s,
        rsi7s=df["rsi7"].values if "rsi7" in df else np.zeros(len(df)),
        cost_pts=cost_pts
    )
    return res[0] if isinstance(res, tuple) else res

def run_wdo_slot(slot_id, cost_pts=0.5, start_d=START_DATE, end_d=END_DATE):
    df, gex = wdo_sim.load_wdo_mt5_raw()
    df = df[(df["session_date"] >= start_d) & (df["session_date"] <= end_d)].reset_index(drop=True)
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    rsi7 = wdo_sim.compute_rsi7_series(closes)
    
    tr = wdo_sim.simulate_wdo_core_slot(
        slot_id, df, gex,
        n50_c, n50_u, n50_l, n50_s,
        n30_c, n30_u, n30_l, n30_s,
        rsi7,
        start_date=start_d, end_date=end_d, cost_pts=cost_pts
    )
    return tr

def main():
    print("=" * 110)
    print("  RELATÓRIO DE ROBUSTEZ QUANTITATIVA DOS 4 NOVOS ROBÔS: EST-03, EST-05, WDO-01, WDO-05")
    print("=" * 110)

    # 1. TESTE IN-SAMPLE VS OUT-OF-SAMPLE (WALK-FORWARD)
    print("\n--- 1. TESTE WALK-FORWARD (IN-SAMPLE: MAI-AGO | OUT-OF-SAMPLE: SET-NOV) ---")
    print(f"{'ROBÔ':<10} {'PERÍODO':<15} {'TR':>4} {'WR%':>6} {'PF':>5} {'LUCRO (R$)':>12} {'MAX DD':>10} {'RET/DD':>7}")
    print("-" * 75)
    
    # WIN
    for sid in [3, 5]:
        tr_is = run_win_slot(sid, cost_pts=10.0, start_d="2026-05-11", end_d="2026-08-31")
        tr_oos = run_win_slot(sid, cost_pts=10.0, start_d="2026-09-01", end_d="2026-11-04")
        tr_full = run_win_slot(sid, cost_pts=10.0, start_d="2026-05-11", end_d="2026-11-04")
        
        m_is = get_stats(tr_is, pt_val=0.20)
        m_oos = get_stats(tr_oos, pt_val=0.20)
        m_full = get_stats(tr_full, pt_val=0.20)
        
        print(f"EST-{sid:02d}    IS (Mai-Ago)    {m_is['tr']:>4d} {m_is['wr']:>5.1f}% {m_is['pf']:>5.2f} {m_is['net']:>12.2f} {m_is['mdd']:>10.2f} {m_is['ret_dd']:>6.2f}x")
        print(f"EST-{sid:02d}    OOS (Set-Nov)   {m_oos['tr']:>4d} {m_oos['wr']:>5.1f}% {m_oos['pf']:>5.2f} {m_oos['net']:>12.2f} {m_oos['mdd']:>10.2f} {m_oos['ret_dd']:>6.2f}x")
        print(f"EST-{sid:02d}    FULL (123d)     {m_full['tr']:>4d} {m_full['wr']:>5.1f}% {m_full['pf']:>5.2f} {m_full['net']:>12.2f} {m_full['mdd']:>10.2f} {m_full['ret_dd']:>6.2f}x")
        print("-" * 75)

    # WDO
    for sid in [1, 5]:
        tr_is = run_wdo_slot(sid, cost_pts=0.5, start_d="2026-05-11", end_d="2026-08-31")
        tr_oos = run_wdo_slot(sid, cost_pts=0.5, start_d="2026-09-01", end_d="2026-11-04")
        tr_full = run_wdo_slot(sid, cost_pts=0.5, start_d="2026-05-11", end_d="2026-11-04")
        
        m_is = get_stats(tr_is, pt_val=10.0)
        m_oos = get_stats(tr_oos, pt_val=10.0)
        m_full = get_stats(tr_full, pt_val=10.0)
        
        print(f"WDO-{sid:02d}    IS (Mai-Ago)    {m_is['tr']:>4d} {m_is['wr']:>5.1f}% {m_is['pf']:>5.2f} {m_is['net']:>12.2f} {m_is['mdd']:>10.2f} {m_is['ret_dd']:>6.2f}x")
        print(f"WDO-{sid:02d}    OOS (Set-Nov)   {m_oos['tr']:>4d} {m_oos['wr']:>5.1f}% {m_oos['pf']:>5.2f} {m_oos['net']:>12.2f} {m_oos['mdd']:>10.2f} {m_oos['ret_dd']:>6.2f}x")
        print(f"WDO-{sid:02d}    FULL (123d)     {m_full['tr']:>4d} {m_full['wr']:>5.1f}% {m_full['pf']:>5.2f} {m_full['net']:>12.2f} {m_full['mdd']:>10.2f} {m_full['ret_dd']:>6.2f}x")
        print("-" * 75)

    # 2. TESTE DE ESTRESSE DE CUSTOS E SLIPPAGE B3 (1.0x, 1.5x, 2.0x)
    print("\n--- 2. TESTE DE ESTRESSE DE CUSTOS / SLIPPAGE (1.0x, 1.5x, 2.0x TAXAS B3) ---")
    print(f"{'ROBÔ':<10} {'ESTRESSE':<15} {'CUSTO (PTS)':<12} {'PF':>5} {'LUCRO (R$)':>12} {'MAX DD':>10} {'RET/DD':>7}")
    print("-" * 75)
    for sid in [3, 5]:
        for mul, label in [(1.0, "Normal B3"), (1.5, "Estresse +50%"), (2.0, "Estresse +100%")]:
            c = 10.0 * mul
            tr = run_win_slot(sid, cost_pts=c)
            m = get_stats(tr, pt_val=0.20)
            print(f"EST-{sid:02d}    {label:<15} {c:>5.1f} pts      {m['pf']:>5.2f} {m['net']:>12.2f} {m['mdd']:>10.2f} {m['ret_dd']:>6.2f}x")
        print("-" * 75)

    for sid in [1, 5]:
        for mul, label in [(1.0, "Normal B3"), (1.5, "Estresse +50%"), (2.0, "Estresse +100%")]:
            c = 0.5 * mul
            tr = run_wdo_slot(sid, cost_pts=c)
            m = get_stats(tr, pt_val=10.0)
            print(f"WDO-{sid:02d}    {label:<15} {c:>5.2f} pts      {m['pf']:>5.2f} {m['net']:>12.2f} {m['mdd']:>10.2f} {m['ret_dd']:>6.2f}x")
        print("-" * 75)

    # 3. CONSISTÊNCIA MENSAL
    print("\n--- 3. CONSISTÊNCIA TEMPORAL MÊS A MÊS (LUCRO LÍQUIDO EM R$) ---")
    all_months = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    header = f"{'ROBÔ':<10} " + " ".join([f"{m:>10}" for m in all_months]) + f" {'TOTAL':>10}"
    print(header)
    print("-" * len(header))
    
    for sid in [3, 5]:
        tr = run_win_slot(sid, cost_pts=10.0)
        by_m = {}
        for t in tr:
            m_str = t["date"][:7]
            by_m[m_str] = by_m.get(m_str, 0.0) + t["pnl_brl"]
        tot = sum(by_m.values())
        line = f"EST-{sid:02d}    " + " ".join([f"{by_m.get(m, 0.0):>10.1f}" for m in all_months]) + f" {tot:>10.1f}"
        print(line)
        
    for sid in [1, 5]:
        tr = run_wdo_slot(sid, cost_pts=0.5)
        by_m = {}
        for t in tr:
            m_str = t["date"][:7]
            by_m[m_str] = by_m.get(m_str, 0.0) + t["pnl_brl"]
        tot = sum(by_m.values())
        line = f"WDO-{sid:02d}    " + " ".join([f"{by_m.get(m, 0.0):>10.1f}" for m in all_months]) + f" {tot:>10.1f}"
        print(line)

if __name__ == "__main__":
    main()
