# -*- coding: utf-8 -*-
import os
import pandas as pd
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
df = pd.read_csv(os.path.join(ROOT_DIR, "data", "reports", "bt_dashboard_flow_2026", "trades_16_strategies_all_filters_2026.csv"))
df["date"] = df["date"].astype(str)
all_days = sorted(df["date"].unique())
oos_days = [d for d in all_days if d <= "2026-05-06"]
is_days = [d for d in all_days if d >= "2026-05-07"]


def eval_combo(name, items):
    parts = [df[(df["strat"] == s) & (df["filter"] == f)] for s, f in items]
    cat = pd.concat(parts, ignore_index=True)
    res = {}
    for p, days in [("OOS", oos_days), ("IS", is_days), ("TOT", all_days)]:
        sub = cat[cat["date"].isin(days)]
        d_s = sub.groupby("date")["pnl"].sum().reindex(days, fill_value=0.0)
        net = float(d_s.sum())
        cum = d_s.cumsum().values
        pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
        dd = float(np.max(pk - cum))
        rdd = net / dd if dd > 0 else 99.9
        gw = float(sub[sub["pnl"] > 0]["pnl"].sum())
        gl = float(-sub[sub["pnl"] < 0]["pnl"].sum())
        pf = gw / gl if gl > 0 else 99.9
        wr = 100.0 * (sub["pnl"] > 0).mean() if len(sub) else 0.0
        sh = float(d_s.mean() / d_s.std(ddof=1) * np.sqrt(252)) if d_s.std(ddof=1) > 0 else 0.0
        res[p] = (len(sub), round(wr, 1), round(pf, 2), round(net), round(dd), round(rdd, 2), round(sh, 2))
    cat["m"] = cat["date"].str.slice(0, 7)
    m_s = cat.groupby("m")["pnl"].sum()
    pos_m = int((m_s > 0).sum())
    o = res["OOS"]
    i = res["IS"]
    t = res["TOT"]
    print(
        f"{name:<38} | OOS: {o[0]:>4}tr PF {o[2]:>4.2f} R${o[3]:>+7d} DD {o[4]:>4d} ({o[5]:>5.2f}x Sh {o[6]:>4.2f}) "
        f"| IS: PF {i[2]:>4.2f} R${i[3]:>+7d} DD {i[4]:>4d} ({i[5]:>5.2f}x) "
        f"| 2026: {t[0]:>4}tr PF {t[2]:>4.2f} R${t[3]:>+7d} DD {t[4]:>4d} ({t[5]:>5.2f}x Sh {t[6]:>4.2f}) | M+: {pos_m}/11"
    )


all_15 = ["EST-01", "EST-03", "EST-04", "EST-05", "EST-07", "EST-13", "EST-14", "EST-15", "EST-16", "WDO-01", "WDO-02", "WDO-05", "WDO-07", "WDO-09", "WDO-10"]
mt5_14_no16 = [s for s in all_15 if s != "EST-16"]
mt5_11_oos_pos = ["EST-01", "EST-03", "EST-04", "EST-05", "EST-07", "EST-13", "EST-14", "EST-15", "WDO-01", "WDO-05", "WDO-07"]
mt5_9_elite = ["EST-03", "EST-04", "EST-05", "EST-13", "EST-14", "EST-15", "WDO-01", "WDO-05", "WDO-07"]

print("=== 1. PROPOSTAS MT5 (100% AUTOMATIZADO SEM DEPENDER DE FLUXO EXTERNO) ===")
eval_combo("MT5_ATUAL_15_ROBOS", [(s, "0_BASE_MT5") for s in all_15])
eval_combo("MT5_PROPOSTA_A_14_SEM_EST16", [(s, "0_BASE_MT5") for s in mt5_14_no16])
eval_combo("MT5_PROPOSTA_B_11_OOS_POSITIVOS", [(s, "0_BASE_MT5") for s in mt5_11_oos_pos])
eval_combo("MT5_PROPOSTA_C_9_ELITE_BAIXO_DD", [(s, "0_BASE_MT5") for s in mt5_9_elite])

print("\n=== 2. PROPOSTAS DASHBOARD 5174 (CARTEIRA SISTEMATICA ALINHADA) ===")
eval_combo("5174_ATUAL_TOP6_BASE", [(s, "0_BASE_MT5") for s in ["EST-04", "EST-07", "EST-14", "WDO-02", "WDO-07", "WDO-10"]])
eval_combo("5174_ATUAL_11_FLOW", [
    ("EST-01", "6_COMBO_SMART"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
    ("EST-13", "4_FLUXO_ABSORCAO"), ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "0_BASE_MT5"),
    ("EST-16", "2_JANELA_S_EXPLOSAO"), ("WDO-02", "0_BASE_MT5"), ("WDO-07", "0_BASE_MT5"),
    ("WDO-09", "1_JANELA_ASG"), ("WDO-10", "3_FLUXO_INST")
])
eval_combo("5174_PROPOSTA_A_10_SEM_EST16_FLOW", [
    ("EST-01", "6_COMBO_SMART"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
    ("EST-13", "4_FLUXO_ABSORCAO"), ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "4_FLUXO_ABSORCAO"),
    ("WDO-02", "0_BASE_MT5"), ("WDO-07", "3_FLUXO_INST"), ("WDO-09", "0_BASE_MT5"), ("WDO-10", "4_FLUXO_ABSORCAO")
])
eval_combo("5174_PROPOSTA_B_TOP8_ELITE_M5", [
    ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"), ("EST-13", "4_FLUXO_ABSORCAO"),
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "4_FLUXO_ABSORCAO"),
    ("WDO-01", "3_FLUXO_INST"), ("WDO-05", "0_BASE_MT5"), ("WDO-07", "3_FLUXO_INST")
])
eval_combo("5174_PROPOSTA_C_14_COMPLETA_HIBRIDA", [
    ("EST-01", "6_COMBO_SMART"), ("EST-03", "0_BASE_MT5"), ("EST-04", "4_FLUXO_ABSORCAO"),
    ("EST-05", "0_BASE_MT5"), ("EST-07", "4_FLUXO_ABSORCAO"), ("EST-13", "4_FLUXO_ABSORCAO"),
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "4_FLUXO_ABSORCAO"),
    ("WDO-01", "3_FLUXO_INST"), ("WDO-02", "0_BASE_MT5"), ("WDO-05", "0_BASE_MT5"),
    ("WDO-07", "3_FLUXO_INST"), ("WDO-09", "0_BASE_MT5"), ("WDO-10", "4_FLUXO_ABSORCAO")
])

print("\n=== 3. PROPOSTAS DASHBOARD 5176 (ESPECIALISTA EM FLUXO NAS WALLS) ===")
eval_combo("5176_ATUAL_WALLS6_FLOW", [
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
    ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "0_BASE_MT5"), ("WDO-10", "3_FLUXO_INST")
])
eval_combo("5176_PROPOSTA_A_WALLS6_STRICT", [
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
    ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "3_FLUXO_INST"), ("WDO-10", "3_FLUXO_INST")
])
eval_combo("5176_PROPOSTA_B_WALLS6_WDO01_LUGAR_10", [
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
    ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "3_FLUXO_INST"), ("WDO-01", "3_FLUXO_INST")
])
eval_combo("5176_PROPOSTA_C_WALLS7 (4WIN + 3WDO)", [
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
    ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "3_FLUXO_INST"), ("WDO-01", "3_FLUXO_INST"), ("WDO-10", "4_FLUXO_ABSORCAO")
])
eval_combo("5176_PROPOSTA_D_WALLS8 (6WIN + 2WDO)", [
    ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-13", "4_FLUXO_ABSORCAO"), ("EST-15", "4_FLUXO_ABSORCAO"),
    ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"), ("WIN-E2", "6_COMBO_SMART"),
    ("WDO-07", "3_FLUXO_INST"), ("WDO-01", "3_FLUXO_INST")
])

