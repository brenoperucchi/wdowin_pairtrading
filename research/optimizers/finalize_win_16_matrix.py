"""
Script rápido de consolidação final das 16 estratégias do WIN (Física Alinhada WDO +
Recalibração BE 177k + 3 Pilares Estruturais + Descorrelação).
Roda apenas as configurações campeãs de cada slot (execução em ~5 segundos).
"""

import os
import sys
import numpy as np
import pandas as pd

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from research.discover_gex_nwe_setups import compute_nwe_series
from research.optimizers.optimize_existing_16_setups import (
    load_win_and_wdo_aligned,
    simulate_single_est_slot,
    calc_slot_summary,
)
from research.optimizers.test_win_aligned_wdo_matrix import (
    simulate_aligned_win_wdo_slot,
    count_collisions,
)


def main():
    df, gex_by_date = load_win_and_wdo_aligned()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    # Winning configs from our grid search for each slot
    # Format: (use_aligned_engine, entry_override, be_mode, buf, tp_mode, replace_pa, desc)
    configs_grid_kept = {
        1:  (True,  "STOP_B1_EXT", "BE_WALL_SHIELD",      25.0, "TP_MAIN_WALL",     False, "Bloco1 pos50 + Stop_B1 + BE_Wall(25) + TP_MainWall"),
        2:  (True,  "ALIGNED",     "BE_WALL_SHIELD",      25.0, "TP_MAIN_WALL",     False, "Bloco1 pos50(off+10) + BE_Wall(25) + TP_MainWall"),
        3:  (True,  "STOP_B1_EXT", "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL",     False, "Bloco1 WDO(off+5) + Stop_B1 + BE_Wall(15) + TP_MainWall"),
        4:  (True,  "ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL",       False, "Bloco2 Reteste 220p(off-5) + BE_2Stage_177k(15) + TP_MidWall"),
        5:  (True,  "STOP_B1_EXT", "BE_RECAL_ZERO",        0.0, "TP_MAIN_WALL",     False, "Bloco1 Cluster(off+15) + Stop_B1 + BE_177k(230/45) + TP_MainWall"),
        6:  (True,  "ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL",     False, "Bloco2 Reteste/Slope(off+15/+20) + BE_Wall(15) + TP_MainWall"),
        7:  (True,  "ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_CURRENT",       False, "Bloco3 Breakout 260p + PB_Limit + BE_Wall(15)"),
        8:  (True,  "STOP_B1_EXT", "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL",     False, "Bloco3 Breakout 260p + Stop_B1 + BE_Wall(15) + TP_MainWall"),
        9:  (True,  "ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_PARTIAL_WALLS", False, "Bloco2 Stop/Lim NY(off-10) + BE_Wall(15) + Parcial_Mid_Main"),
        10: (True,  "ALIGNED",     "BE_RECAL_ZERO",        0.0, "TP_CURRENT",       False, "Bloco2 MainWalls pos50+GammaFlip + BE_177k(240/45)"),
        11: (False, "CURRENT",     "BE_WALL_2STAGE",      15.0, "TP_CURRENT",       False, "Bloco4 Grid 1+2 NWE + BE_2Stage(15)"),
        12: (True,  "ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL",     False, "Bloco3 Piram 1+1 Breakout 260p + PB_Limit + BE_Wall(15) + TP_MainWall"),
        13: (True,  "ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_CURRENT",       False, "Bloco4 SmartGrid MainWall pos50<=0.32+GammaFlip + BE_177k"),
        14: (True,  "ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_CURRENT",       False, "Bloco4 Grid Inst MainWall pos50<=0.30+GammaFlip(1+1+2L)"),
        15: (True,  "STOP_B1_EXT", "BE_RECAL_ZERO",        0.0, "TP_MIDWALL",       False, "Bloco3 Breakout 260p + Stop_B1 + BE_177k(250/50) + TP_MidWall"),
        16: (False, "CURRENT",     "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL",     False, "Bloco4 Posicional StopWall + BE_Wall(15) + TP_MainWall"),
    }

    # Opção A: Substitui EST-13 e EST-14 pelos setups PA de alta eficiência (Rolling Stop Barra[1] nas Walls/MainWalls)
    configs_op_a = dict(configs_grid_kept)
    configs_op_a[13] = (True, "ALIGNED", "BE_WALL_SHIELD", 15.0, "TP_PARTIAL_WALLS", True, "OPÇÃO A: Rolling Stop Barra[1] Wall + BE_Wall(15) + Parcial")
    configs_op_a[14] = (True, "ALIGNED", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL",     True, "OPÇÃO A: Rolling Stop Barra[1] MainWall + BE_Wall(25) + TP_MainWall")

    leg_all, grid_all, opa_all = [], [], []
    entries_opa = {}
    rows = []

    for est_id in range(1, 17):
        tr_l, st_l = simulate_single_est_slot(
            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode="BE_ZERO", tp_mode="TP_CURRENT"
        )
        m_l = calc_slot_summary(tr_l, st_l)
        leg_all.extend(tr_l)

        # Grid Kept
        u_al, e_ov, b_m, bf, t_m, rep_pa, desc_g = configs_grid_kept[est_id]
        if u_al:
            tr_g, st_g = simulate_aligned_win_wdo_slot(
                est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                be_mode=b_m, wall_shield_buf=bf, tp_mode=t_m, entry_override=e_ov, replace_13_16_pa=rep_pa
            )
        else:
            tr_g, st_g = simulate_single_est_slot(
                est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                entry_override=e_ov, be_mode=b_m, wall_shield_buf=bf, tp_mode=t_m
            )
        m_g = calc_slot_summary(tr_g, st_g)
        grid_all.extend(tr_g)

        # Opção A
        u_al2, e_ov2, b_m2, bf2, t_m2, rep_pa2, desc_a = configs_op_a[est_id]
        if est_id == 13 and rep_pa2:
            # Usa Rolling Stop Barra[1] All Levels no horário NO_LUNCH (igual ao setup 14 mas em All Levels)
            tr_a, st_a = simulate_aligned_win_wdo_slot(
                14, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                be_mode="BE_WALL_SHIELD", wall_shield_buf=15.0, tp_mode="TP_PARTIAL_WALLS", entry_override="ALIGNED", replace_13_16_pa=True
            )
        elif u_al2:
            tr_a, st_a = simulate_aligned_win_wdo_slot(
                est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                be_mode=b_m2, wall_shield_buf=bf2, tp_mode=t_m2, entry_override=e_ov2, replace_13_16_pa=rep_pa2
            )
        else:
            tr_a, st_a = simulate_single_est_slot(
                est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                entry_override=e_ov2, be_mode=b_m2, wall_shield_buf=bf2, tp_mode=t_m2
            )
        m_a = calc_slot_summary(tr_a, st_a)
        opa_all.extend(tr_a)
        if "entries" in st_a:
            entries_opa[est_id] = st_a["entries"]

        rows.append({
            "ID": f"EST-{est_id:02d}",
            "Leg_Tr": m_l["Trades"],
            "Leg_BRL": m_l["NetBRL"],
            "Leg_DD": m_l["MaxDD_BRL"],
            "Leg_RetDD": m_l["Ret_DD"],
            "GridAlin_BRL": m_g["NetBRL"],
            "GridAlin_DD": m_g["MaxDD_BRL"],
            "GridAlin_RetDD": m_g["Ret_DD"],
            "OpA_Tr": m_a["Trades"],
            "OpA_BRL": m_a["NetBRL"],
            "OpA_DD": m_a["MaxDD_BRL"],
            "OpA_PF": m_a["PF"],
            "OpA_RetDD": m_a["Ret_DD"],
            "Saves": st_a.get("wall_saves", 0),
            "Parciais": st_a.get("partial_hits", 0),
            "Arquitetura_Final": desc_a,
        })

    df_r = pd.DataFrame(rows)
    out_dir = os.path.join(PROJECT_ROOT, "data", "reports", "win_aligned_wdo_matrix")
    df_r.to_csv(os.path.join(out_dir, "win_16_final_architecture.csv"), index=False)

    p_leg = calc_slot_summary(sorted(leg_all, key=lambda x: x["date"]), {}, "1. LEGACY ATUAL (Deadlock c50 + Trava 85p + BE 150/20)")
    p_grd = calc_slot_summary(sorted(grid_all, key=lambda x: x["date"]), {}, "2. NOVO ALINHADO (4 Blocos WDO + BE 177k + 3 Pilares c/ Grids 13-14)")
    p_opa = calc_slot_summary(sorted(opa_all, key=lambda x: x["date"]), {}, "3. NOVO ALINHADO + OPCAO A (4 Blocos + BE 177k + 3 Pilares + PA 13-14)")
    df_p = pd.DataFrame([p_leg, p_grd, p_opa])
    df_p.to_csv(os.path.join(out_dir, "portfolio_final_comparison.csv"), index=False)

    print(df_r.to_string(index=False))
    print("\n" + "=" * 115)
    print(df_p[["Config", "Trades", "WinRate", "PF", "NetPts", "NetBRL", "MaxDD_BRL", "Ret_DD", "Sharpe"]].to_string(index=False))
    print("=" * 115)


if __name__ == "__main__":
    main()
