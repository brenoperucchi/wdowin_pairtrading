"""Auditoria final de B_dw_ex10, B_dw_vol11, platôs e portfólios 3 pontas."""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.flow_breakout.explore import build_cache
from research.div_master.flow_breakout.refine_win import extract_win_rich
from research.div_master.flow_breakout.audit_win_fb import audit_rule, eval_win_df
from research.div_master.win_especialista.audit_e22_win import get_e22_signals, eval_e22
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN


if __name__ == "__main__":
    DS, cache = build_cache("WIN")
    df = extract_win_rich(cache)
    _, df_e22_2 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=2.0)
    all_dates = pd.Index(sorted(cache.keys()))

    cw = df["cross_w"].values
    ce65 = (df["close_ext"] >= 0.65).values
    t0915 = (df["tm"] <= 900).values

    sub1 = df[cw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["ex50"] < 1.0).values & (df["nwa_d"] >= 200.0).values & t0915]
    plac1 = df[(~cw) & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["ex50"] < 1.0).values & (df["nwa_d"] >= 200.0).values & t0915]
    audit_rule("B_dw_ex10 (09_15, SL280 TP280 t24)", sub1, DS, 280.0, 280.0, 24, df_e22_2, all_dates, plac1, "Placebo SEM Wall")

    sub2 = df[cw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["vol_r"] >= 1.1).values & (df["nwa_d"] >= 200.0).values & t0915]
    plac2 = df[(~cw) & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["vol_r"] >= 1.1).values & (df["nwa_d"] >= 200.0).values & t0915]
    audit_rule("B_dw_vol11 (09_15, SL250 TP250 t18)", sub2, DS, 250.0, 250.0, 18, df_e22_2, all_dates, plac2, "Placebo SEM Wall")

    print("\n=== Platô SL x TP de B_dw_ex10 (09_15, t=24) ===")
    for sl in (220.0, 250.0, 280.0, 300.0):
        row = []
        for tp in (220.0, 250.0, 280.0, 300.0):
            s, _ = eval_win_df(sub1, DS, sl, tp, 24)
            row.append(f"TP{tp:.0f}:{s['rdd']:.2f}({s['meses']})")
        print(f"  SL={sl:.0f}: " + " | ".join(row))

    print("\n=== Platô ag_n em B_dw_ex10 (09_15, 280/280 t24) ===")
    for ag in (0.0, 0.5, 1.0, 1.2, 1.5):
        ss = df[cw & ce65 & (df["ag_n"] >= ag).values & (df["dw_f"] > 0).values & (df["ex50"] < 1.0).values & (df["nwa_d"] >= 200.0).values & t0915]
        print(f"  ag>={ag:.1f}:", eval_win_df(ss, DS, 280.0, 280.0, 24)[0])

    print("\n=== Carteiras 3 pontas ===")
    P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
    r_wdo = run_v32_wdo(P_wdo, "wall", "common", OPT_OPEN, "CONF", lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
    _, df_wdo = eval_wdo(r_wdo, 14.0, "nw", 0.0, 24, "UM")
    for name, sub_x, sl, tp, tm in [
        ("E22+B_dw_ex10+WDO", sub1, 280.0, 280.0, 24),
        ("E22+B_dw_vol11+WDO", sub2, 250.0, 250.0, 18),
    ]:
        _, df_x = eval_win_df(sub_x, DS, sl, tp, tm)
        df_wtot = pd.concat([df_e22_2, df_x], ignore_index=True).sort_values(["date", "xt"])
        print(f"  {name:22s}:", bt.portfolio(df_wtot, df_wdo, "pnl", "pnl", "xt", "xt"))
