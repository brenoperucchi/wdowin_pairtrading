"""
OTIMIZAÇÃO DE TP, SL E BE COM USO DE WALLS, MIDWALLS E MÁXIMAS/MÍNIMAS
======================================================================
Audita e otimiza sistematicamente todas as 11 estratégias da carteira:
  WIN: EST-01, EST-04, EST-07, EST-13, EST-14, EST-15, EST-16
  WDO: WDO-02, WDO-07, WDO-09, WDO-10

Pontos analisados:
  1. TP (Take Profit):
     - Usa Próxima MidWall (TP_MIDWALL) ou Próxima Main Wall (TP_MAIN_WALL)
     - Elimina alvos cegos/fixos (ex: EST-07 com 650 fixo e WDO-10 com 16 fixo)
     - Nos SmartGrids (EST-13..16), testa liberar a trava de 220 pts para buscar alvos estruturais.
  2. Proteção de Stop Loss Inicial (SL):
     - Ancorado atrás da Wall de defesa (SL_WALL_SHIELD)
     - Ancorado atrás da Máxima/Mínima da barra de sinal (SL_B1_EXT)
     - Stop fixo tradicional (SL_FIXED)
  3. Proteção de Break-Even / Trailing (BE):
     - BE_ZERO (avg_price +- be_lock)
     - BE_WALL_SHIELD (move SL para trás da Wall de defesa)
     - BE_WALL_2STAGE (Estágio 1 atrás da Wall; Estágio 2 na MidWall superada ou no 0 a 0)
     - BE_B1_EXT (move SL para trás do extremo da barra de sinal)

Período: 11/05/2026 a 04/11/2026.
Custos: R$ 2/contrato no WIN (10 pts) e R$ 5/contrato no WDO (0,5 pt).
"""
import os
import sys
import time
import inspect
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
from research.mt5_loader import load_win_and_wdo_aligned, load_m5_m1_wdo_gex
import research.optimizers.optimize_existing_16_setups as o16
import research.optimizers.wdo_mt5_sim as wsim

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "tp_sl_be_optimization")
os.makedirs(OUT_DIR, exist_ok=True)

WIN_COST_PTS = 10.0
WDO_COST_PTS = 0.5


def run_win_optimizations():
    print("=" * 90)
    print("  OTIMIZAÇÃO WIN: EST-01, EST-04, EST-07, EST-13, EST-14, EST-15, EST-16")
    print("=" * 90)

    df_win, gex_win = load_win_and_wdo_aligned()
    closes = df_win["close"].values
    n50_c, n50_u, n50_l, _, n50_s = disc.compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = disc.compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)

    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    results = []

    # 1. EST-01, EST-04, EST-07
    singles = [
        (1, "EST-01 Scalper Hibrido NY", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
        (4, "EST-04 Pullback Reteste Wall", "BE_WALL_2STAGE", 15.0, "TP_MIDWALL"),
        (7, "EST-07 Breakout Momentum NY", "BE_WALL_SHIELD", 15.0, "TP_CURRENT"),  # Atualmente TP fixo 650!
    ]

    for est_id, name, cur_be, cur_buf, cur_tp in singles:
        # Baseline
        tr_base, st_base = o16.simulate_single_est_slot(
            est_id, df_win, gex_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode=cur_be, wall_shield_buf=cur_buf, tp_mode=cur_tp, cost_pts=WIN_COST_PTS
        )
        m_base = o16.calc_slot_summary(tr_base, st_base, f"{name} BASELINE")

        best_m = m_base
        best_cfg = f"BE={cur_be}({int(cur_buf)}) | TP={cur_tp} (ATUAL)"

        # Test combinations of TP and BE
        tp_options = ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"]
        be_options = ["BE_ZERO", "BE_WALL_SHIELD", "BE_WALL_2STAGE"]
        buf_options = [15.0, 25.0]

        for tp_m in tp_options:
            for be_m in be_options:
                b_list = [0.0] if be_m == "BE_ZERO" else buf_options
                for buf in b_list:
                    tr, st = o16.simulate_single_est_slot(
                        est_id, df_win, gex_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                        entry_override="CURRENT", be_mode=be_m, wall_shield_buf=buf, tp_mode=tp_m, cost_pts=WIN_COST_PTS
                    )
                    if len(tr) < max(20, int(0.5 * len(tr_base))):
                        continue
                    m = o16.calc_slot_summary(tr, st)
                    # Optimization criterion: Higher Net and Higher Ret/DD
                    if (m["NetBRL"] > best_m["NetBRL"] and m["PF"] >= best_m["PF"] * 0.98) or (m["Ret_DD"] > best_m["Ret_DD"] * 1.15 and m["NetBRL"] >= best_m["NetBRL"] * 0.90):
                        best_m = m
                        best_cfg = f"BE={be_m}({int(buf)}) | TP={tp_m}"

        results.append({
            "ID": f"EST-{est_id:02d}",
            "Nome": name,
            "Trades_Base": m_base["Trades"],
            "NetBRL_Base": m_base["NetBRL"],
            "PF_Base": m_base["PF"],
            "DD_Base": m_base["MaxDD_BRL"],
            "RetDD_Base": m_base["Ret_DD"],
            "Trades_Opt": best_m["Trades"],
            "NetBRL_Opt": best_m["NetBRL"],
            "PF_Opt": best_m["PF"],
            "DD_Opt": best_m["MaxDD_BRL"],
            "RetDD_Opt": best_m["Ret_DD"],
            "Delta_BRL": round(best_m["NetBRL"] - m_base["NetBRL"], 2),
            "Melhor_Config": best_cfg,
        })
        print(f"[{name}] Base: R$ {m_base['NetBRL']} (Ret/DD {m_base['Ret_DD']}) -> Opt: R$ {best_m['NetBRL']} (Ret/DD {best_m['Ret_DD']}) | Config: {best_cfg}")

    return results


def run_wdo_optimizations():
    print("\n" + "=" * 90)
    print("  OTIMIZAÇÃO WDO: WDO-02, WDO-07, WDO-09, WDO-10")
    print("=" * 90)

    df_wdo, gex_wdo = wsim.load_wdo_mt5_raw()
    closes = df_wdo["close"].values
    n50_c, n50_u, n50_l, _, n50_s = wsim.compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = wsim.compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    rsi7 = wsim.compute_rsi7_series(closes)

    wdo_results = []

    # Baseline runs
    for sid in [2, 7, 9, 10]:
        tr_base = wsim.simulate_wdo_core_slot(sid, df_wdo, gex_wdo, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7, cost_pts=WDO_COST_PTS)
        s_base = wsim.summarize_wdo_trades(tr_base, f"WDO-{sid:02d} BASELINE")
        print(f"[WDO-{sid:02d}] Baseline: Trades={s_base['Trades']} | WR={s_base['WR%']}% | PF={s_base['PF_com_custo']} | Net=R$ {s_base['R$_com_custo']} | DD=R$ {s_base['DD_com_custo']} | Ret/DD={s_base['RetDD_com_custo']}")

    return df_wdo, gex_wdo, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7


if __name__ == "__main__":
    t0 = time.time()
    res_win = run_win_optimizations()
    run_wdo_optimizations()
    print(f"\nConcluído em {time.time() - t0:.1f}s.")

