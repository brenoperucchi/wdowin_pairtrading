"""
IMPACTO NO PORTFÓLIO E TESTES DE ROBUSTEZ DOS 4 NOVOS ROBÔS:
- WIN: EST-03 (M15 Fakeout Trap) e EST-05 (M15 MidWall Pullback)
- WDO: WDO-01 (Scalper NY) e WDO-05 (Cluster NWE)
==============================================================
"""

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_gex_nwe_setups import compute_nwe_series
from research.mt5_loader import load_gex_csv, HIST_WIN, HIST_WDO
import research.optimizers.optimize_existing_16_setups as o16
import research.optimizers.wdo_mt5_sim as wdo_sim
from research.discover_m15_deep_dive import run_experiment, load_tf_bars, compute_metrics
from research.optimizers.test_win_aligned_wdo_matrix import load_win_and_wdo_aligned

START_DATE = "2026-05-11"
END_DATE = "2026-11-04"

# 1. Carrega dados de M15 para WIN
df_win_m15 = load_tf_bars("WIN", "M15")
gex_win = load_gex_csv(HIST_WIN)
c_m15 = df_win_m15["close"].values
c15, u15, l15, _, s15 = compute_nwe_series(c_m15, lookback=30, bw=4.0, mult=1.8)
nwe_win_m15 = {"center": c15, "upper": u15, "lower": l15, "slope": s15}

# 2. Carrega dados de M5 para WIN (ativos atuais)
df_win_m5, gex_by_date_m5 = load_win_and_wdo_aligned()
c_m5 = df_win_m5["close"].values
n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(c_m5, lookback=50, bw=5.0, mult=2.0)
n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(c_m5, lookback=30, bw=3.0, mult=1.6)

# 3. Carrega dados de M5 para WDO
df_wdo_m5, gex_wdo = wdo_sim.load_wdo_mt5_raw()
cw_m5 = df_wdo_m5["close"].values
wn50_c, wn50_u, wn50_l, _, wn50_s = compute_nwe_series(cw_m5, lookback=50, bw=5.0, mult=2.0)
wn30_c, wn30_u, wn30_l, _, wn30_s = compute_nwe_series(cw_m5, lookback=30, bw=3.0, mult=1.6)
rsi7_wdo = wdo_sim.compute_rsi7_series(cw_m5)

# --- EXECUÇÃO DOS 4 NOVOS ROBÔS ---

# NOVO EST-03 (WIN M15 Trap)
tr_est03 = run_experiment(
    df_win_m15, gex_win, "WIN", "M15", "M15_FAKEOUT_TRAP", "MARKET", nwe_win_m15,
    wall_buf=30.0, min_tp_dist=220.0, front_run=20.0, be_ratio=0.50, be_lock_pts=25.0
)

# NOVO EST-05 (WIN M15 Pullback)
tr_est05 = run_experiment(
    df_win_m15, gex_win, "WIN", "M15", "M15_MIDWALL_PULLBACK", "MARKET", nwe_win_m15,
    wall_buf=35.0, min_tp_dist=250.0, front_run=20.0, be_ratio=0.50, be_lock_pts=25.0,
    use_nwe_slope=True, nwe_slope_thresh=4.0, min_nwe_bw=300.0
)

# WDO-01 (WDO Scalper NY)
tr_wdo01 = wdo_sim.simulate_wdo_core_slot(
    1, df_wdo_m5, gex_wdo, wn50_c, wn50_u, wn50_l, wn50_s, wn30_c, wn30_u, wn30_l, wn30_s, rsi7_wdo,
    cost_pts=0.5
)

# WDO-05 (WDO Cluster NWE)
tr_wdo05 = wdo_sim.simulate_wdo_core_slot(
    5, df_wdo_m5, gex_wdo, wn50_c, wn50_u, wn50_l, wn50_s, wn30_c, wn30_u, wn30_l, wn30_s, rsi7_wdo,
    cost_pts=0.5
)

# --- EXECUÇÃO DOS ROBÔS ATUAIS DA CONTA (18 ROBÔS) ---
# WIN atuais: 1, 2, 4, 6, 7, 8, 12 (PA M5) + 13, 14, 15, 16 (SG M1)
win_active_slots = [1, 2, 4, 6, 7, 8, 12]
trades_win_curr = {}
for sid in win_active_slots:
    res = o16.simulate_single_est_slot(
        sid, df_win_m5, gex_by_date_m5,
        n50_c, n50_u, n50_l, n50_s,
        n30_c, n30_u, n30_l, n30_s,
        rsi7s=df_win_m5["rsi7"].values if "rsi7" in df_win_m5 else np.zeros(len(df_win_m5)),
        cost_pts=10.0
    )
    trades_win_curr[sid] = res[0] if isinstance(res, tuple) else res

# WDO atuais: 2, 6, 7, 9, 10, 11, 15
wdo_active_slots = [2, 6, 7, 9, 10, 11, 15]
trades_wdo_curr = {}
for sid in wdo_active_slots:
    trades_wdo_curr[sid] = wdo_sim.simulate_wdo_core_slot(
        sid, df_wdo_m5, gex_wdo, wn50_c, wn50_u, wn50_l, wn50_s, wn30_c, wn30_u, wn30_l, wn30_s, rsi7_wdo,
        cost_pts=0.5
    )

# Transforma em séries diárias
def to_daily_series(trades, pt_val=1.0, is_brl=False):
    d = {}
    for t in trades:
        date = t["date"]
        pnl = t["brl"] if "brl" in t else (t["pnl_brl"] if "pnl_brl" in t else t.get("pts", 0.0) * pt_val)
        d[date] = d.get(date, 0.0) + pnl
    return pd.Series(d)

s_e03 = to_daily_series(tr_est03, is_brl=True).rename("EST-03 (M15)")
s_e05 = to_daily_series(tr_est05, is_brl=True).rename("EST-05 (M15)")
s_w01 = to_daily_series(tr_wdo01, is_brl=True).rename("WDO-01")
s_w05 = to_daily_series(tr_wdo05, is_brl=True).rename("WDO-05")

# Séries dos robôs atuais
curr_series_dict = {}
for sid in win_active_slots:
    curr_series_dict[f"WIN-{sid:02d}"] = to_daily_series(trades_win_curr[sid], pt_val=0.20)
for sid in wdo_active_slots:
    curr_series_dict[f"WDO-{sid:02d}"] = to_daily_series(trades_wdo_curr[sid], is_brl=True)

df_all = pd.DataFrame(curr_series_dict).fillna(0.0)
df_all["EST-03 (M15)"] = s_e03
df_all["EST-05 (M15)"] = s_e05
df_all["WDO-01"] = s_w01
df_all["WDO-05"] = s_w05
df_all = df_all.fillna(0.0)

# 1. ANÁLISE DE CORRELAÇÃO DOS 4 NOVOS CONTRA TODOS OS ATUAIS
print("=" * 105)
print("  MATRIZ DE CORRELAÇÃO: 4 NOVOS ROBÔS vs ROBÔS ATUAIS DA CONTA")
print("=" * 105)

cols_curr = [c for c in df_all.columns if c not in ["EST-03 (M15)", "EST-05 (M15)", "WDO-01", "WDO-05"]]
corr_df = pd.DataFrame(index=cols_curr)
for n in ["EST-03 (M15)", "EST-05 (M15)", "WDO-01", "WDO-05"]:
    corr_df[n] = [df_all[n].corr(df_all[c]) for c in cols_curr]

print(corr_df.round(2).to_string())

# 2. COMPARAÇÃO DO PORTFÓLIO ANTES vs DEPOIS
pnl_before = df_all[cols_curr].sum(axis=1)
pnl_after = df_all.sum(axis=1)

def calc_portfolio_metrics(pnl_s, label):
    net = pnl_s.sum()
    cum = pnl_s.cumsum()
    pk = np.maximum.accumulate(np.insert(cum.values, 0, 0.0))[1:]
    dd = float(np.max(pk - cum.values))
    ret_dd = net / dd if dd > 0 else 99.9
    sharpe = (pnl_s.mean() / pnl_s.std() * np.sqrt(252)) if pnl_s.std() > 0 else 0.0
    win_days = (pnl_s > 0).sum()
    tot_days = len(pnl_s)
    pct_win_days = win_days / tot_days * 100.0
    worst_day = pnl_s.min()
    return {
        "Carteira": label,
        "Lucro Total (R$)": round(net, 2),
        "Max Drawdown (R$)": round(dd, 2),
        "Ret/DD": round(ret_dd, 2),
        "Sharpe Anual": round(sharpe, 2),
        "% Dias Positivos": f"{pct_win_days:.1f}%",
        "Pior Dia (R$)": round(worst_day, 2)
    }

m_before = calc_portfolio_metrics(pnl_before, "PORTFÓLIO ATUAL (Sem os 4 novos)")
m_after = calc_portfolio_metrics(pnl_after, "PORTFÓLIO EXPANDIDO (+ 4 novos robôs)")

print("\n" + "=" * 105)
print("  IMPACTO NO PORTFÓLIO: ANTES vs DEPOIS DA ADIÇÃO DOS 4 ROBÔS")
print("=" * 105)
res_comp = pd.DataFrame([m_before, m_after])
print(res_comp.to_string(index=False))

# Contribuição individual de cada um dos 4 novos
print("\n" + "=" * 105)
print("  MÉTRICAS INDIVIDUAIS DOS 4 NOVOS ROBÔS")
print("=" * 105)
def calc_stats_safe(trades, pt_val=1.0):
    pnls = [t.get("pnl_brl", t.get("brl", t.get("pts", 0.0) * pt_val)) for t in trades]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    wr = round(wins / n * 100.0, 1)
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = round(gw / gl, 2) if gl > 1e-6 else 99.9
    net = round(sum(pnls), 2)
    by_day = {}
    for t, p in zip(trades, pnls):
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + p
    cum = np.cumsum([by_day[d] for d in sorted(by_day.keys())])
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    mdd = round(float(np.max(pk - cum)), 2) if len(cum) else 0.0
    ret_dd = round(net / mdd, 2) if mdd > 0 else 99.9
    return {"tr": n, "wr": wr, "pf": pf, "net": net, "mdd": mdd, "ret_dd": ret_dd}

for name, s, tr, pv in [
    ("EST-03 (WIN M15 Trap)", s_e03, tr_est03, 0.20),
    ("EST-05 (WIN M15 Pullback)", s_e05, tr_est05, 0.20),
    ("WDO-01 (WDO Scalper NY)", s_w01, tr_wdo01, 10.0),
    ("WDO-05 (WDO Cluster NWE)", s_w05, tr_wdo05, 10.0),
]:
    met = calc_stats_safe(tr, pv)
    print(f"  {name:<28}: {met['tr']:>4d} trades | WR {met['wr']:>4.1f}% | PF {met['pf']:>4.2f} | Lucro: R$ {met['net']:>8.2f} | Max DD: R$ {met['mdd']:>6.2f} | Ret/DD: {met['ret_dd']:>5.2f}x")
