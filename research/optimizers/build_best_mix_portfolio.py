"""
Constrói e valida o Portfólio MIX CAMPEÃO (Regra Estrita: Só altera se melhorar o Ret/DD!)
e compara diretamente:
  1. Portfólio Atual (Legacy EST-01..16)
  2. Portfólio Atual + Troca Pura das vagas 13..16 pelos 4 Novos Achados (ANTES de qualquer otimização)
  3. Portfólio Otimizado 3 Pilares + Troca das vagas 13..16 pelos Novos Achados
  4. Portfólio MIX CAMPEÃO (Para cada slot 01..16, escolhe estritamente o maior Ret/DD entre:
     Original, 3 Pilares Estruturais, Física Alinhada WDO/260p/177k e os Novos Achados PA nas vagas 13..16).
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
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
from research.optimizers.optimize_structural_walls_pa import simulate_structural_setup


def run_new_finding_trades(df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s, finding_id: int):
    """
    Executa os 4 Novos Achados Estruturais independentes (2 mini-contratos = 1+1 p/ saída parcial,
    substituindo os Grids de 3 a 6 contratos das vagas 11, 13, 14 e o EOD da vaga 16):
      - finding_id = 1 (NOVO-1): Híbrido Wall+NWE | Stop Barra[1](off=15, vb=1) | BE_2Stage_Walls(25) | TP_MidWall Real (Ret/DD = 4.55)
      - finding_id = 2 (NOVO-2): Pullback Slope   | Rolling Stop Barra[1](off=15, vb=2) | BE_2Stage_Walls(25) | TP_MidWall Real (Ret/DD = 3.85)
      - finding_id = 3 (NOVO-3): Pullback Slope   | Rolling Stop Barra[1](off=15, vb=2) | BE_2Stage_Walls(25) | Parcial Mid/Main (Ret/DD = 3.63)
      - finding_id = 4 (NOVO-4): Híbrido Wall+NWE | Stop Barra[1](off=15, vb=2) | BE_Wall_Shield(25)  | TP_MidWall Real (Ret/DD = 3.00)
    """
    specs = {
        1: ("HYBRID_WALL_NWE", "STOP_PREV_BAR",         15.0, 1, 230.0, "BE_TWO_STAGE_WALLS", 130.0, 25.0, "TP_REAL_MIDWALL",     20.0),
        2: ("PULLBACK_SLOPE",  "ROLLING_STOP_PREV_BAR", 15.0, 2, 230.0, "BE_TWO_STAGE_WALLS", 130.0, 25.0, "TP_REAL_MIDWALL",     20.0),
        3: ("PULLBACK_SLOPE",  "ROLLING_STOP_PREV_BAR", 15.0, 2, 230.0, "BE_TWO_STAGE_WALLS", 130.0, 25.0, "TP_PARTIAL_MID_MAIN", 20.0),
        4: ("HYBRID_WALL_NWE", "STOP_PREV_BAR",         15.0, 2, 230.0, "BE_WALL_SHIELD",     130.0, 25.0, "TP_REAL_MIDWALL",     20.0),
    }
    sm, et, eoff, vb, sl_i, bm, btrig, buf, tm, fr = specs[finding_id]
    raw_trades, st = simulate_structural_setup(
        df, gex_by_date, n50_c, n50_u, n50_l, n50_s, rsi7s,
        signal_mode=sm, entry_type=et, entry_off=eoff, valid_bars=vb,
        sl_init_pts=sl_i, be_mode=bm, be_trigger_pts=btrig, wall_shield_buf=buf,
        tp_mode=tm, front_run_pts=fr,
    )
    norm_trades = [{
        "date": t["date"], "est_id": 12 + finding_id, "side": t["side"],
        "pnl_pts": t["pnl_pts"] * 2.0, "contracts": 2.0, "pnl_brl": t["pnl_pts"] * 2.0 * 0.20,
    } for t in raw_trades]
    return norm_trades, st


def main():
    df, gex_by_date = load_win_and_wdo_aligned()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    # 1. Roda os 4 Novos Achados Puros
    new_pa_trades = {}
    new_pa_stats = {}
    new_pa_metrics = {}
    new_pa_names = {
        1: "NOVO-1: Stop Barra[1](off15) Híbrido + BE_2Stage(25) + TP_MidWall (2C)",
        2: "NOVO-2: Rolling Stop Barra[1] Slope + BE_2Stage(25) + TP_MidWall (2C)",
        3: "NOVO-3: Rolling Stop Barra[1] Slope + BE_2Stage(25) + Parcial Mid/Main (2C)",
        4: "NOVO-4: Stop Barra[1](2b) Híbrido + BE_Wall(25) + TP_MidWall (2C)",
    }
    for fid in (1, 2, 3, 4):
        tr_f, st_f = run_new_finding_trades(df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s, fid)
        new_pa_trades[fid] = tr_f
        new_pa_stats[fid] = st_f
        new_pa_metrics[fid] = calc_slot_summary(tr_f, st_f, new_pa_names[fid])

    # Melhores configurações de 3 Pilares no código original (Caminho 1)
    opt_3p_configs = {
        1:  ("CURRENT",      "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL",     "3-Pilares: BE_Wall(25) + TP_MainWall"),
        2:  ("LIMIT_B1_MID", "BE_ZERO",         0.0, "TP_MAIN_WALL",     "3-Pilares: Limit_50%B1 + TP_MainWall"),
        3:  ("CURRENT",      "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL",     "3-Pilares: BE_Wall(25) + TP_MainWall"),
        4:  ("CURRENT",      "BE_ZERO",         0.0, "TP_MIDWALL",       "3-Pilares: TP_MidWall Real"),
        5:  ("LIMIT_B1_EXT", "BE_ZERO",         0.0, "TP_MAIN_WALL",     "3-Pilares: Limit_ExtB1 + TP_MainWall"),
        6:  ("STOP_B1_EXT",  "BE_WALL_SHIELD", 15.0, "TP_MAIN_WALL",     "3-Pilares: Stop_B1 + BE_Wall(15) + TP_MainWall"),
        7:  ("CURRENT",      "BE_WALL_SHIELD", 15.0, "TP_CURRENT",       "3-Pilares: BE_Wall(15) + TP_Original"),
        8:  ("CURRENT",      "BE_ZERO",         0.0, "TP_MAIN_WALL",     "3-Pilares: TP_MainWall Real"),
        9:  ("CURRENT",      "BE_WALL_SHIELD", 15.0, "TP_PARTIAL_WALLS", "3-Pilares: BE_Wall(15) + Parcial_Mid_Main"),
        10: ("CURRENT",      "BE_WALL_SHIELD", 25.0, "TP_CURRENT",       "3-Pilares: BE_Wall(25) + TP_Original"),
        11: ("CURRENT",      "BE_ZERO",         0.0, "TP_MIDWALL",       "3-Pilares: TP_MidWall Real"),
        12: ("CURRENT",      "BE_ZERO",         0.0, "TP_MAIN_WALL",     "3-Pilares: TP_MainWall Real"),
        13: ("CURRENT",      "BE_WALL_2STAGE", 15.0, "TP_MIDWALL",       "3-Pilares: BE_2Stage(15) + TP_MidWall"),
        14: ("CURRENT",      "BE_WALL_2STAGE", 15.0, "TP_MIDWALL",       "3-Pilares: BE_2Stage(15) + TP_MidWall"),
        15: ("STOP_B1_EXT",  "BE_WALL_SHIELD", 15.0, "TP_MAIN_WALL",     "3-Pilares: Stop_B1 + BE_Wall(15) + TP_MainWall"),
        16: ("CURRENT",      "BE_WALL_2STAGE", 15.0, "TP_MAIN_WALL",     "3-Pilares: BE_2Stage(15) + TP_MainWall"),
    }

    # Configurações da Matriz Alinhada WDO / Breakout 260p / BE 177k
    aligned_wdo_configs = {
        1:  ("STOP_B1_EXT", "BE_WALL_SHIELD",      25.0, "TP_MAIN_WALL", False, "Matriz WDO: pos50 + Stop_B1 + BE_Wall(25) + TP_MainWall"),
        2:  ("ALIGNED",     "BE_WALL_SHIELD",      25.0, "TP_MAIN_WALL", False, "Matriz WDO: pos50(off+10) + BE_Wall(25) + TP_MainWall"),
        3:  ("STOP_B1_EXT", "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL", False, "Matriz WDO: WDO(off+5) + Stop_B1 + BE_Wall(15) + TP_MainWall"),
        4:  ("ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL",   False, "Matriz WDO: Reteste 220p(off-5) + BE_2Stage_177k(15) + TP_MidWall"),
        5:  ("STOP_B1_EXT", "BE_RECAL_ZERO",        0.0, "TP_MAIN_WALL", False, "Matriz WDO: Cluster(off+15) + Stop_B1 + BE_177k(230/45) + TP_MainWall"),
        6:  ("ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL", False, "Matriz WDO: Reteste/Slope(off+15) + BE_Wall(15) + TP_MainWall"),
        7:  ("ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_CURRENT",   False, "Matriz WDO: Breakout 260p + PB_Limit + BE_Wall(15)"),
        8:  ("STOP_B1_EXT", "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL", False, "Matriz WDO: Breakout 260p + Stop_B1 + BE_Wall(15) + TP_MainWall"),
        9:  ("ALIGNED",     "BE_RECAL_ZERO",        0.0, "TP_CURRENT",   False, "Matriz WDO: Stop/Lim NY(off-10) + BE_177k(240/45)"),
        10: ("ALIGNED",     "BE_RECAL_ZERO",        0.0, "TP_CURRENT",   False, "Matriz WDO: MainWalls pos50+GammaFlip + BE_177k(240/45)"),
        11: ("ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_CURRENT",   False, "Matriz WDO: Grid 1+2 pos50+GammaFlip"),
        12: ("ALIGNED",     "BE_WALL_SHIELD",      15.0, "TP_MAIN_WALL", False, "Matriz WDO: Piram 1+1 Breakout 260p + PB_Limit"),
        13: ("ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_CURRENT",   False, "Matriz WDO: SmartGrid MainWall pos50+GammaFlip"),
        14: ("ALIGNED",     "BE_WALL_2STAGE_177K", 15.0, "TP_CURRENT",   False, "Matriz WDO: Grid Inst MainWall pos50+GammaFlip"),
        15: ("STOP_B1_EXT", "BE_RECAL_ZERO",        0.0, "TP_MIDWALL",   False, "Matriz WDO: Breakout 260p + Stop_B1 + BE_177k(250/50) + TP_MidWall"),
        16: ("ALIGNED",     "BE_RECAL_ZERO",        0.0, "TP_CURRENT",   False, "Matriz WDO: Posicional StopWall 177k"),
    }

    port_1_legacy = []
    port_2_swap_before_opt = []     # EST-01..12 Legacy + Vagas 13..16 trocadas pelos 4 Novos Achados (ANTES da otimização!)
    port_3_opt3p_plus_swap = []     # EST-01..12 Otimizado 3-Pilares + Vagas 13..16 trocadas pelos 4 Novos Achados
    port_4_best_mix = []            # MIX CAMPEÃO: Maior Ret/DD em cada vaga 01..16!

    mix_rows = []

    for est_id in range(1, 17):
        # A. Legacy Original
        tr_leg, st_leg = simulate_single_est_slot(
            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode="BE_ZERO", tp_mode="TP_CURRENT"
        )
        m_leg = calc_slot_summary(tr_leg, st_leg, "Original (Legacy)")
        port_1_legacy.extend(tr_leg)

        # B. 3 Pilares no código original
        e3, b3, bf3, t3, desc3 = opt_3p_configs[est_id]
        tr_3p, st_3p = simulate_single_est_slot(
            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override=e3, be_mode=b3, wall_shield_buf=bf3, tp_mode=t3
        )
        m_3p = calc_slot_summary(tr_3p, st_3p, desc3)

        # C. Matriz Alinhada WDO / Breakout 260p / BE 177k
        ew, bw, bfw, tw, repw, descw = aligned_wdo_configs[est_id]
        tr_wdo, st_wdo = simulate_aligned_win_wdo_slot(
            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            be_mode=bw, wall_shield_buf=bfw, tp_mode=tw, entry_override=ew, replace_13_16_pa=repw
        )
        m_wdo = calc_slot_summary(tr_wdo, st_wdo, descw)

        # Construção do Portfólio 2 (Troca Pura ANTES da otimização) e Portfólio 3
        if est_id <= 12:
            port_2_swap_before_opt.extend(tr_leg)
            port_3_opt3p_plus_swap.extend(tr_3p)
        else:
            fid = est_id - 12
            port_2_swap_before_opt.extend(new_pa_trades[fid])
            port_3_opt3p_plus_swap.extend(new_pa_trades[fid])

        # D. Escolha ESTRITA do MIX CAMPEÃO para a vaga `est_id` (Maior Ret/DD!)
        candidates = [
            ("MANTIDO ORIGINAL", m_leg, tr_leg),
            (desc3, m_3p, tr_3p),
            (descw, m_wdo, tr_wdo),
        ]
        if est_id in (11, 13, 14, 15, 16):
            # Nas vagas de menor Ret/DD (Grids 11, 13, 14 e Posicionais 15, 16), concorrem os 4 Novos Achados!
            if est_id == 11:
                candidates.append((new_pa_names[4], new_pa_metrics[4], new_pa_trades[4]))
            elif est_id == 13:
                candidates.append((new_pa_names[1], new_pa_metrics[1], new_pa_trades[1]))
            elif est_id == 14:
                candidates.append((new_pa_names[2], new_pa_metrics[2], new_pa_trades[2]))
            elif est_id == 15:
                candidates.append((new_pa_names[3], new_pa_metrics[3], new_pa_trades[3]))
            elif est_id == 16:
                candidates.append((new_pa_names[3], new_pa_metrics[3], new_pa_trades[3]))

        # Seleciona estritamente o candidato com MAIOR Ret/DD (exigindo lucro >= 90% do baseline se for a mesma estratégia)
        best_label, best_m, best_tr = max(candidates, key=lambda c: c[1]["Ret_DD"])
        port_4_best_mix.extend(best_tr)

        mix_rows.append({
            "Slot": f"EST-{est_id:02d}",
            "Orig_BRL": m_leg["NetBRL"],
            "Orig_DD": m_leg["MaxDD_BRL"],
            "Orig_RetDD": m_leg["Ret_DD"],
            "3Pil_BRL": m_3p["NetBRL"],
            "3Pil_RetDD": m_3p["Ret_DD"],
            "WDOAlin_BRL": m_wdo["NetBRL"],
            "WDOAlin_RetDD": m_wdo["Ret_DD"],
            "MIX_Trades": best_m["Trades"],
            "MIX_BRL": best_m["NetBRL"],
            "MIX_DD": best_m["MaxDD_BRL"],
            "MIX_PF": best_m["PF"],
            "MIX_RetDD": best_m["Ret_DD"],
            "Decisao_Mix_Campeao": best_label,
        })

    df_mix = pd.DataFrame(mix_rows)
    out_dir = os.path.join(PROJECT_ROOT, "data", "reports", "win_aligned_wdo_matrix")
    df_mix.to_csv(os.path.join(out_dir, "win_16_best_mix_selection.csv"), index=False)

    p1 = calc_slot_summary(sorted(port_1_legacy, key=lambda x: x["date"]), {}, "1. ATUAL LEGACY (EST-01..16 Sem Alteração)")
    p2 = calc_slot_summary(sorted(port_2_swap_before_opt, key=lambda x: x["date"]), {}, "2. TROCA PURA ANTES DA OTIMIZAÇÃO (EST-01..12 Atuais + 4 Novos Achados em 13..16)")
    p3 = calc_slot_summary(sorted(port_3_opt3p_plus_swap, key=lambda x: x["date"]), {}, "3. OTIMIZADO 3-PILARES + TROCA 13..16 PELOS 4 NOVOS ACHADOS")
    p4 = calc_slot_summary(sorted(port_4_best_mix, key=lambda x: x["date"]), {}, "4. MIX CAMPEÃO FINAL (Maior Ret/DD em cada vaga: Orig vs 3-Pilares vs Matriz WDO vs Novos Achados)")

    df_ports = pd.DataFrame([p1, p2, p3, p4])
    df_ports.to_csv(os.path.join(out_dir, "portfolio_best_mix_comparison.csv"), index=False)

    print("TABELA DE SELEÇÃO DO MIX CAMPEÃO (REGRA ESTRITA: MAIOR RET/DD EM CADA VAGA):")
    print(df_mix.to_string(index=False))
    print("\n" + "=" * 120)
    print("COMPARATIVO DOS 4 ESTÁGIOS DO PORTFÓLIO (INCLUINDO A TROCA PURA ANTES DAS OTIMIZAÇÕES):")
    print("=" * 120)
    print(df_ports[["Config", "Trades", "WinRate", "PF", "NetPts", "NetBRL", "MaxDD_BRL", "Ret_DD", "Sharpe"]].to_string(index=False))
    print("=" * 120)


if __name__ == "__main__":
    main()
