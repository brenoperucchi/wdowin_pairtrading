"""Busca de alta seletividade (PF maior, menos custo) no WIN: Rompimento de Wall + Fluxo Institucional."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.flow_breakout.explore import build_cache
from research.div_master.flow_breakout.refine_win import extract_win_rich, run_grid
from research.div_master.flow_breakout.audit_win_fb import audit_rule, eval_win_df
from research.div_master.win_especialista.audit_e22_win import get_e22_signals, eval_e22
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN


if __name__ == "__main__":
    DS, cache = build_cache("WIN")
    df = extract_win_rich(cache)
    _, df_e22_1 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=1.0)
    _, df_e22_2 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=2.0)
    all_dates = pd.Index(sorted(cache.keys()))
    s_e22 = df_e22_1.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)

    cw = df["cross_w"].values
    fw = df["first_w"].values
    ce65 = (df["close_ext"] >= 0.65).values
    base = cw & ce65 & (df["ag_n"] >= 1.0).values & (df["nwa_d"] >= 200.0).values

    masks = {
        "B_base": base,
        "B_dw": base & (df["dw_f"] > 0).values,
        "B_dw_sl0": base & (df["dw_f"] > 0).values & (df["sl50"] > 0).values,
        "B_dw_ex10": base & (df["dw_f"] > 0).values & (df["ex50"] < 1.0).values,
        "B_dw_ps0": base & (df["dw_f"] > 0).values & (df["ps_n"] > 0).values,
        "B_dw_ps05": base & (df["dw_f"] > 0).values & (df["ps_n"] >= 0.5).values,
        "B_dw_vol11": base & (df["dw_f"] > 0).values & (df["vol_r"] >= 1.1).values,
        "B_dw_vol12": base & (df["dw_f"] > 0).values & (df["vol_r"] >= 1.2).values,
        "B_dw_lot": base & (df["dw_f"] > 0).values & df["lot_adv"].values,
        "B_ag15_dw": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values,
        "B_ag15_dw_ex10": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["dw_f"] > 0).values & (df["ex50"] < 1.0).values & (df["nwa_d"] >= 200.0).values,
        "B_ag15_ps0_sl0": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["ps_n"] > 0).values & (df["sl50"] > 0).values & (df["nwa_d"] >= 200.0).values,
        "B_ag15_ps0_dw": cw & ce65 & (df["ag_n"] >= 1.5).values & (df["ps_n"] > 0).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values,
        "B_1st_dw": fw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values,
        "B_1st_dw_ex12": fw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["ex50"] < 1.2).values & (df["nwa_d"] >= 200.0).values,
        "B_dw_atr10": base & (df["dw_f"] > 0).values & (df["rng_atr"] >= 1.0).values,
        "B_dw_nw300": cw & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["nw_d"] >= 300.0).values,
    }
    time_masks = {
        "09_15": (df["tm"] <= 900).values,
        "09_12": (df["tm"] <= 720).values,
        "10_15": ((df["tm"] >= 600) & (df["tm"] <= 900)).values,
    }
    exits = [
        ("SL250_TP250_t18", 250.0, 250.0, 0.0, 0.0, 18),
        ("SL250_TP350_t24", 250.0, 350.0, 0.0, 0.0, 24),
        ("SL250_TP350_BE200_t24", 250.0, 350.0, 200.0, 20.0, 24),
        ("SL280_TP280_t24", 280.0, 280.0, 0.0, 0.0, 24),
        ("SL280_TP350_t24", 280.0, 350.0, 0.0, 0.0, 24),
        ("SL300_TP300_t24", 300.0, 300.0, 0.0, 0.0, 24),
    ]

    res = run_grid(df, DS, s_e22, all_dates, masks, time_masks, exits, "SEL2")
    print("=== TOP POR RET/DD ===")
    print(res.head(20).to_string(index=False))

    print("\n=== TOP COM PF >= 1.35 (<= 450 ops) ===")
    hi_pf = res[(res["pf"] >= 1.35) & (res["ops"] <= 450)]
    print(hi_pf.head(20).to_string(index=False) if not hi_pf.empty else "Nenhum com PF>=1.35 e ops<=450.")

    # Audita os 2 melhores com PF mais alto e melhor Ret/DD
    if not res.empty:
        # Melhor Ret/DD geral: B_dw | 09_15 | SL280_TP280_t24
        sub1 = df[masks["B_dw"] & time_masks["09_15"]]
        plac1 = df[(~cw) & ce65 & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values & (df["nwa_d"] >= 200.0).values & time_masks["09_15"]]
        audit_rule("MELHOR RET/DD: B_dw 09_15 SL280 TP280 t24", sub1, DS, 280.0, 280.0, 24, df_e22_2, all_dates, plac1, "Placebo SEM Wall")

        if not hi_pf.empty:
            r0 = hi_pf.iloc[0]
            sub2 = df[masks[r0["rule"]] & time_masks[r0["time"]]]
            ex = [e for e in exits if e[0] == r0["exit"]][0]
            audit_rule(f"MAIOR PF: {r0['rule']} {r0['time']} {r0['exit']}", sub2, DS, ex[1], ex[2], ex[5], df_e22_2, all_dates)

            # Carteira 3 pontas com V1a WDO
            P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
            r_wdo = run_v32_wdo(P_wdo, "wall", "common", OPT_OPEN, "CONF", lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
            _, df_wdo = eval_wdo(r_wdo, 14.0, "nw", 0.0, 24, "UM")
            _, df_sub2 = eval_win_df(sub2, DS, ex[1], ex[2], ex[5])
            df_wtot = pd.concat([df_e22_2, df_sub2], ignore_index=True).sort_values(["date", "xt"])
            print("\nPortfólio E22(2ct) + MAIOR_PF_BREAK(1ct) + V1a_WDO(1ct):", bt.portfolio(df_wtot, df_wdo, "pnl", "pnl", "xt", "xt"))
