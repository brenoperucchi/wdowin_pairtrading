"""Auditoria de estresse, placebo (sem Wall / nível deslocado / sem fluxo) e busca seletiva (maior PF) em WIN Rompimento de Wall & Seguidora de Fluxo."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.flow_breakout.explore import build_cache
from research.div_master.flow_breakout.refine_win import extract_win_rich, run_grid
from research.div_master.win_especialista.audit_e22_win import XW, sim_win_exact, get_e22_signals, eval_e22


def eval_win_df(df_sub, DS, sl, tp, tmax, be_t=0.0, be_l=0.0, mgmt="UM", cost=10.0, stop_slip=5.0, entry_slip=0.0, adv_m1=False, inv=False):
    if df_sub.empty:
        return dict(ops=0, rdd=0.0), df_sub
    df = df_sub.sort_values(["date", "tm", "i", "dir"]).reset_index(drop=True).copy()
    pnls, xts = [], []
    for r in df.itertuples():
        D = DS[r.date]
        dr = -r.dir if inv else r.dir
        p, xt = sim_win_exact(D, r.e, r.ep, dr, sl, tp, be_t, be_l, tmax, XW["tick"], cost, stop_slip, entry_slip, adv_m1)
        pnls.append(p)
        xts.append(xt)
    df["pnl"] = pnls
    df["xt"] = xts
    if mgmt == "UM":
        df = bt.mgmt(df, "pnl", "xt", "UM")
    return bt.stats(df, "pnl", "xt"), df


def audit_rule(title, df_sub, DS, sl, tp, tmax, df_e22, all_dates, placebo_df=None, placebo_lbl="Placebo"):
    print(f"\n{'='*90}\n{title}\n{'='*90}")
    st, df_v = eval_win_df(df_sub, DS, sl, tp, tmax)
    print("Base (10/5):         ", st)
    print("LIVRE:               ", eval_win_df(df_sub, DS, sl, tp, tmax, mgmt="LIVRE")[0])
    print("Pior M1:             ", eval_win_df(df_sub, DS, sl, tp, tmax, adv_m1=True)[0])
    print("Stop 2 ticks (10/10):", eval_win_df(df_sub, DS, sl, tp, tmax, stop_slip=10.0)[0])
    print("Custo 2x (20/5):     ", eval_win_df(df_sub, DS, sl, tp, tmax, cost=20.0)[0])
    print("Pesado (20/10/+5e):  ", eval_win_df(df_sub, DS, sl, tp, tmax, cost=20.0, stop_slip=10.0, entry_slip=5.0)[0])
    print("Invertida (-dir):    ", eval_win_df(df_sub, DS, sl, tp, tmax, inv=True)[0])
    if placebo_df is not None:
        print(f"{placebo_lbl:20s}:", eval_win_df(placebo_df, DS, sl, tp, tmax)[0])
    port = bt.portfolio(df_e22, df_v, "pnl", "pnl", "xt", "xt")
    s1 = df_e22.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)
    s2 = df_v.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)
    print(f"Corr vs E22: {s1.corr(s2):.3f} | Portfólio E22(2ct)+Cand(1ct): {port}")


if __name__ == "__main__":
    DS, cache = build_cache("WIN")
    df = extract_win_rich(cache)
    _, df_e22_1 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=1.0)
    _, df_e22_2 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=2.0)
    all_dates = pd.Index(sorted(cache.keys()))
    s_e22 = df_e22_1.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)

    # 1. Busca de variantes mais seletivas (maior PF por trade!) em B1 (Rompimento de Wall) e A1 (Seguidora de Fluxo)
    cw = df["cross_w"].values
    ce65 = (df["close_ext"] >= 0.65).values
    sel_masks = {
        # Rompimento de Wall mais seletivo
        "B_nwa200_ag10": cw & ce65 & (df["ag_n"] >= 1.0).values & (df["nwa_d"] >= 200.0).values,
        "B_nwa200_ag15": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["nwa_d"] >= 200.0).values,
        "B_nwa200_ag15_ex12": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["nwa_d"] >= 200.0).values & (df["ex50"] < 1.2).values,
        "B_nwa200_ag15_ps0": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["ps_n"] > 0).values & (df["nwa_d"] >= 200.0).values,
        "B_nwa200_ag10_vol12": cw & ce65 & (df["ag_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["nwa_d"] >= 200.0).values,
        "B_nwa200_ag10_dw": cw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values,
        "B_nwa200_ag10_lot": cw & ce65 & (df["ag_n"] >= 1.0).values & df["lot_adv"].values & (df["nwa_d"] >= 200.0).values,
        "B_nwa250_ag10_ex12": cw & ce65 & (df["ag_n"] >= 1.0).values & (df["nwa_d"] >= 250.0).values & (df["ex50"] < 1.2).values,
        "B_ex12_ag15_ps0": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["ps_n"] > 0).values & (df["ex50"] < 1.2).values,
        # Seguidora de Fluxo mais refinada (além da A_ag15_ps10_vol12_sl0)
        "A_ag15_ps10_vol12_sl0": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values,
        "A_ag15_ps10_vol12_sl0_ex12": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values & (df["ex50"] < 1.2).values,
        "A_ag15_ps08_vol12_sl0": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 0.8).values & (df["vol_r"] >= 1.2).values & (df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values,
        "A_ag12_ps10_vol12_sl0": (df["ag_n"] >= 1.2).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values,
        "A_ag15_ps10_sl0_ce65": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 1.0).values & (df["sl50"] > 0.0).values & ce65,
        "A_ag15_ps10_vol12_dw": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["dw_f"] > 0).values & (df["bar_str"] >= 0.4).values,
        "A_ag20_ps10_vol12": (df["ag_n"] >= 2.0).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["bar_str"] >= 0.4).values,
    }
    time_masks = {
        "ALL": np.ones(len(df), dtype=bool),
        "09_15": (df["tm"] <= 900).values,
        "10_16": ((df["tm"] >= 600) & (df["tm"] < 960)).values,
    }
    exits = [
        ("SL250_TP250_t18", 250.0, 250.0, 0.0, 0.0, 18),
        ("SL280_TP280_t24", 280.0, 280.0, 0.0, 0.0, 24),
        ("SL300_TP250_t18", 300.0, 250.0, 0.0, 0.0, 18),
        ("SL250_TP300_t24", 250.0, 300.0, 0.0, 0.0, 24),
        ("SL300_TP300_t24", 300.0, 300.0, 0.0, 0.0, 24),
        ("SL200_TP250_t12", 200.0, 250.0, 0.0, 0.0, 12),
    ]
    res = run_grid(df, DS, s_e22, all_dates, sel_masks, time_masks, exits, "SEL")
    print("=== TOP SELETIVAS (ops>=100, rdd>=3.5, H1/H2/OOS>0) ===")
    if not res.empty:
        print(res.head(30).to_string(index=False))

    # 2. Auditoria detalhada do B_nwa200_ag10 (09_15, SL250 TP250 t18) e placebo SEM cruzamento de Wall
    sub_b = df[cw & ce65 & (df["ag_n"] >= 1.0).values & (df["nwa_d"] >= 200.0).values & (df["tm"] <= 900).values]
    plac_b_nowall = df[(~cw) & ce65 & (df["ag_n"] >= 1.0).values & (df["nwa_d"] >= 200.0).values & (df["tm"] <= 900).values]
    audit_rule(
        "ROMPIMENTO B1: cross_w & close_ext>=0.65 & ag_n>=1.0 & nwa_d>=200 & 09h-15h | SL250 TP250 t18",
        sub_b, DS, 250.0, 250.0, 18, df_e22_2, all_dates, plac_b_nowall, "Placebo SEM Wall",
    )

    # Auditoria B_nwa200_ag15_ex12 ou B_nwa200_ag10_dw se bom
    sub_b2 = df[cw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values & (df["tm"] <= 900).values]
    plac_b2 = df[(~cw) & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values & (df["tm"] <= 900).values]
    audit_rule(
        "ROMPIMENTO B2: cross_w & close_ext>=0.65 & ag_n>=1.0 & dw_f>0 & nwa_d>=200 & 09h-15h | SL250 TP250 t18",
        sub_b2, DS, 250.0, 250.0, 18, df_e22_2, all_dates, plac_b2, "Placebo SEM Wall",
    )

    # Auditoria A1 Seguidora de Fluxo: ag_n>=1.5 & ps_n>=1.0 & vol_r>=1.2 & sl50>0 & bar_str>=0.4 & 10_16
    sub_a = df[(df["ag_n"] >= 1.5).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values & ((df["tm"] >= 600) & (df["tm"] < 960)).values]
    plac_a = df[(df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values & ((df["tm"] >= 600) & (df["tm"] < 960)).values]
    audit_rule(
        "SEGUIDORA FLUXO A1: ag>=1.5 & ps>=1.0 & vol>=1.2 & sl50>0 & bar>=0.4 & 10h-16h | SL300 TP250 t18",
        sub_a, DS, 300.0, 250.0, 18, df_e22_2, all_dates, plac_a, "Placebo SEM fluxo",
    )
