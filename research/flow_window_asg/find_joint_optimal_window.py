# -*- coding: utf-8 -*-
import os
import sys
import glob
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT_DIR = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

SCRATCH_DIR = r"C:\Users\ryzen\.gemini\antigravity\brain\c2b74f00-91a2-46d9-a669-fdd6bd3e1379\scratch"
if SCRATCH_DIR not in sys.path:
    sys.path.insert(0, SCRATCH_DIR)

from test_best_windows_on_6strats import (
    raw_win_series,
    raw_wdo_series,
    df_win,
    gex_win,
    pb_win,
    n50_c, n50_u, n50_l, n50_s,
    n30_c, n30_u, n30_l, n30_s,
    rsi7s_w,
    df_wdo,
    gex_wdo,
    pb_wdo,
    d_n50_c, d_n50_u, d_n50_l, d_n50_s,
    d_n30_c, d_n30_u, d_n30_l, d_n30_s,
    d_rsi7s,
    all_dates,
    compute_dashboard_series_custom,
    align_dashboard_arrays,
    build_filter_masks,
    run_win_strategy,
    run_wdo_strategy,
    calc_metrics,
)
from optimize_flow_window_and_6strats import simulate_flow_window_for_params

print("=== BUSCA CONJUNTA: MELHOR JANELA PURA + MELHORIA NAS 6 ESTRATEGIAS ===")

# Precompute unchanging strategies (EST_07 c/ 3_FLUXO_INST, EST_13 c/ 4_FLUXO_ABSORCAO, WDO_11 c/ 4_FLUXO_ABSORCAO)
d_map_w0 = {s_d: compute_dashboard_series_custom(raw_win_series[s_d], True, 4, 11, 0.68, 0.45, 6.5) for s_d in all_dates}
d_feat_w0 = align_dashboard_arrays(df_win, d_map_w0, is_win=True)
f_w0 = build_filter_masks(d_feat_w0, is_win=True)
tr_07_base = run_win_strategy(7, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, *f_w0["3_FLUXO_INST"])
tr_13_base = run_win_strategy(13, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, *f_w0["4_FLUXO_ABSORCAO"])

d_map_d0 = {s_d: compute_dashboard_series_custom(raw_wdo_series[s_d], False, 4, 11, 0.68, 0.45, 6.5) for s_d in all_dates}
d_feat_d0 = align_dashboard_arrays(df_wdo, d_map_d0, is_win=False)
f_d0 = build_filter_masks(d_feat_d0, is_win=False)
tr_11_base = run_wdo_strategy(11, df_wdo, gex_wdo, pb_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, *f_d0["4_FLUXO_ABSORCAO"])

# Test grid on WIN (where EST_01 uses 6_COMBO_SMART)
win_joint = []
for fp in [2, 3, 4, 5, 6]:
    for sp in [8, 10, 11, 14, 18]:
        if fp >= sp - 2:
            continue
        for wc in [0.68, 0.85, 1.00]:
            for sm in [0.45]:
                for fl in [5.0, 6.5, 8.5, 11.0, 14.0, 18.0, 22.0]:
                    pure = simulate_flow_window_for_params("WIN", fp, sp, wc, sm, fl)
                    if pure["net_brl"] <= 869:
                        continue
                    d_map = {s_d: compute_dashboard_series_custom(raw_win_series[s_d], True, fp, sp, wc, sm, fl) for s_d in all_dates}
                    d_feat = align_dashboard_arrays(df_win, d_map, is_win=True)
                    f_m = build_filter_masks(d_feat, is_win=True)
                    tr_01 = run_win_strategy(1, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, *f_m["6_COMBO_SMART"])
                    m01 = calc_metrics(tr_01, all_dates, "pnl_brl")
                    mmix = calc_metrics(tr_01 + tr_07_base + tr_13_base, all_dates, "pnl_brl")
                    win_joint.append((fp, sp, wc, sm, fl, pure, m01, mmix))

win_joint.sort(key=lambda x: (x[6]["pos_months"], x[6]["net"], x[5]["ret_dd"]), reverse=True)
print("\n--- WIN: MELHORES COMBINACOES (JANELA PURA + WIN REJEICAO EST_01 + COMBO WIN) ---")
for fp, sp, wc, sm, fl, pure, m01, mmix in win_joint[:10]:
    print(
        f"  Fast={fp:2d} Slow={sp:2d} wCVD={wc:.2f} Flip={fl:4.1f} | "
        f"JanPura: Net=R${pure['net_brl']:5.0f} (PF={pure['pf']:.2f}, Ret/DD={pure['ret_dd']:.2f}x, {pure['flips_per_day']}/d) || "
        f"EST_01: Net=R${m01['net']:5.0f} (WR={m01['wr']:.1f}%, PF={m01['pf']:.2f}, Ret/DD={m01['ret_dd']:.2f}x, M={m01['pos_months']}/6) || "
        f"3xWIN: Net=R${mmix['net']:6.0f} (Ret/DD={mmix['ret_dd']:.2f}x)"
    )

# Test grid on WDO (where WDO_09 uses 1_JANELA_ASG)
wdo_joint = []
for fp in [2, 3, 4, 5, 6, 8]:
    for sp in [8, 10, 11, 14, 18, 22]:
        if fp >= sp - 2:
            continue
        for wc in [0.50, 0.68, 0.85, 1.00]:
            for sm in [0.35, 0.45, 0.60]:
                for fl in [4.5, 6.5, 8.5, 11.0, 14.0]:
                    pure = simulate_flow_window_for_params("WDO", fp, sp, wc, sm, fl)
                    d_map = {s_d: compute_dashboard_series_custom(raw_wdo_series[s_d], False, fp, sp, wc, sm, fl) for s_d in all_dates}
                    d_feat = align_dashboard_arrays(df_wdo, d_map, is_win=False)
                    f_m = build_filter_masks(d_feat, is_win=False)
                    tr_09 = run_wdo_strategy(9, df_wdo, gex_wdo, pb_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, *f_m["1_JANELA_ASG"])
                    m09 = calc_metrics(tr_09, all_dates, "pnl_brl")
                    if m09["net"] >= 2500:
                        mmix = calc_metrics(tr_09 + tr_11_base, all_dates, "pnl_brl")
                        wdo_joint.append((fp, sp, wc, sm, fl, pure, m09, mmix))

wdo_joint.sort(key=lambda x: (x[6]["pos_months"], x[6]["ret_dd"], x[6]["net"], x[5]["net_brl"]), reverse=True)
print("\n--- WDO: MELHORES COMBINACOES (JANELA PURA + WDO PULLBACK WDO_09 + COMBO WDO) ---")
for fp, sp, wc, sm, fl, pure, m09, mmix in wdo_joint[:12]:
    print(
        f"  Fast={fp:2d} Slow={sp:2d} wCVD={wc:.2f} Sm={sm:.2f} Flip={fl:4.1f} | "
        f"JanPura: Net=R${pure['net_brl']:6.0f} (PF={pure['pf']:.2f}, {pure['flips_per_day']}/d) || "
        f"WDO_09: Tr={m09['trades']:3d} Net=R${m09['net']:5.0f} (WR={m09['wr']:.1f}%, PF={m09['pf']:.2f}, MDD=R${m09['mdd']:3.0f}, Ret/DD={m09['ret_dd']:.2f}x, M={m09['pos_months']}/6) || "
        f"WDO_09+11: Net=R${mmix['net']:5.0f} (Ret/DD={mmix['ret_dd']:.2f}x)"
    )
