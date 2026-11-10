import os
import sys
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import inspect
import pandas as pd
import numpy as np
import research.optimizers.wdo_mt5_sim as wsim

df_wdo, gex = wsim.load_wdo_mt5_raw()
closes = df_wdo['close'].values
n50_c, n50_u, n50_l, _, n50_s = wsim.compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
n30_c, n30_u, n30_l, _, n30_s = wsim.compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
rsi7 = wsim.compute_rsi7_series(closes)

src_orig = inspect.getsource(wsim.simulate_wdo_core_slot)

print("=" * 90)
print("TESTES DE TP, SL E BE PARA WDO-02, WDO-07, WDO-09")
print("=" * 90)

# 1. WDO-02
cases_02 = [
    ("WDO-02 BASELINE (MidWall, BE2Stage, SL11/13.5)", 1, "ORIG_SL", 2),
    ("WDO-02 TP_MAINWALL (BE2Stage, SL11/13.5)", 2, "ORIG_SL", 2),
    ("WDO-02 TP_MIDWALL + SL_WALL_SHIELD", 1, "WALL_SL", 2),
    ("WDO-02 TP_MAINWALL + SL_WALL_SHIELD", 2, "WALL_SL", 2),
    ("WDO-02 TP_MIDWALL + BE_WALL_SHIELD_1STAGE", 1, "ORIG_SL", 1),
]

t_block_02 = """                    if sig2 != 0:
                        p2_lim = round05(b1_l + 0.5) if sig2 == 1 else round05(b1_h - 0.5)
                        tp_calc = calc_wdo_target_pts(p2_lim, sig2, 1, 25.0, m_levels_walls, m_levels_all)
                        arm_pending_order(sig2, 1, p2_lim, new_bar_time, new_bar_open, tp_calc, sl2, be2, 1.5, trt2, trd2, mh2, wall2, 2, 1.0, 1, today_str)"""

for label, tpt, slt, bem in cases_02:
    sl_expr = "sl2" if slt == "ORIG_SL" else "max(7.0, min(16.0, round05(abs(p2_lim - wall2) + 1.5)))"
    repl = f"""                    if sig2 != 0:
                        p2_lim = round05(b1_l + 0.5) if sig2 == 1 else round05(b1_h - 0.5)
                        tp_calc = calc_wdo_target_pts(p2_lim, sig2, {tpt}, 25.0, m_levels_walls, m_levels_all)
                        sl_custom = {sl_expr}
                        arm_pending_order(sig2, 1, p2_lim, new_bar_time, new_bar_open, tp_calc, sl_custom, be2, 1.5, trt2, trd2, mh2, wall2, {bem}, 1.0, 1, today_str)"""
    ns = dict(wsim.__dict__)
    exec(src_orig.replace(t_block_02, repl, 1), ns)
    sim_func = ns['simulate_wdo_core_slot']
    tr = sim_func(2, df_wdo, gex, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7, cost_pts=0.5)
    s = wsim.summarize_wdo_trades(tr, label)
    print(f"{label:48s} | Tr={s['Trades']:3d} | WR={s['WR%']:4.1f}% | PF={s['PF_com_custo']:4.2f} | Net=R$ {s['R$_com_custo']:6.0f} | DD=R$ {s['DD_com_custo']:4.0f} | RetDD={s['RetDD_com_custo']:4.2f}")


# 2. WDO-07
cases_07 = [
    ("WDO-07 BASELINE (MidWall, BE_Shield_1stg, SL11)", 1, "ORIG_SL", 1),
    ("WDO-07 TP_MAINWALL (BE_Shield_1stg, SL11)", 2, "ORIG_SL", 1),
    ("WDO-07 TP_MIDWALL + BE_WALL_2STAGE", 1, "ORIG_SL", 2),
    ("WDO-07 TP_MAINWALL + BE_WALL_2STAGE", 2, "ORIG_SL", 2),
    ("WDO-07 TP_MIDWALL + SL_WALL_SHIELD", 1, "WALL_SL", 1),
]

t_block_07 = """                                tp_calc = calc_wdo_target_pts(new_bar_open, -1, 1, 19.0, m_levels_walls, m_levels_all)
                                open_virtual_single(-1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), 1, 1.0)
                                last_entry_bar_time = b1_time
                                break
                            if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                                tp_calc = calc_wdo_target_pts(new_bar_open, 1, 1, 19.0, m_levels_walls, m_levels_all)
                                open_virtual_single(1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), 1, 1.0)"""

for label, tpt, slt, bem in cases_07:
    sl_expr = "11.0" if slt == "ORIG_SL" else "max(7.0, min(15.0, round05(abs(new_bar_open - float(lvl)) + 1.5)))"
    repl_07 = f"""                                tp_calc = calc_wdo_target_pts(new_bar_open, -1, {tpt}, 19.0, m_levels_walls, m_levels_all)
                                sl_custom = {sl_expr}
                                open_virtual_single(-1, new_bar_open, new_bar_time, tp_calc, sl_custom, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), {bem}, 1.0)
                                last_entry_bar_time = b1_time
                                break
                            if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                                tp_calc = calc_wdo_target_pts(new_bar_open, 1, {tpt}, 19.0, m_levels_walls, m_levels_all)
                                sl_custom = {sl_expr}
                                open_virtual_single(1, new_bar_open, new_bar_time, tp_calc, sl_custom, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), {bem}, 1.0)"""
    ns = dict(wsim.__dict__)
    exec(src_orig.replace(t_block_07, repl_07, 1), ns)
    sim_func = ns['simulate_wdo_core_slot']
    tr = sim_func(7, df_wdo, gex, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7, cost_pts=0.5)
    s = wsim.summarize_wdo_trades(tr, label)
    print(f"{label:48s} | Tr={s['Trades']:3d} | WR={s['WR%']:4.1f}% | PF={s['PF_com_custo']:4.2f} | Net=R$ {s['R$_com_custo']:6.0f} | DD=R$ {s['DD_com_custo']:4.0f} | RetDD={s['RetDD_com_custo']:4.2f}")


# 3. WDO-09
cases_09 = [
    ("WDO-09 BASELINE (MidWall, BE2Stage, SL11.5)", 1, "ORIG_SL", 2),
    ("WDO-09 TP_MAINWALL (BE2Stage, SL11.5)", 2, "ORIG_SL", 2),
    ("WDO-09 TP_MIDWALL + SL_WALL_SHIELD", 1, "WALL_SL", 2),
    ("WDO-09 TP_MAINWALL + SL_WALL_SHIELD", 2, "WALL_SL", 2),
]

t_block_09 = """                        if sig9 != 0:
                            p9_lim = round05(wall9 + 0.5) if sig9 == 1 else round05(wall9 - 0.5)
                            tp_calc = calc_wdo_target_pts(p9_lim, sig9, 1, 22.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig9, 1, p9_lim, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 13.5, 5.0, 16, wall9, 2, 1.5, 2, today_str)"""

for label, tpt, slt, bem in cases_09:
    sl_expr = "11.5" if slt == "ORIG_SL" else "max(7.0, min(15.0, round05(abs(p9_lim - wall9) + 2.0)))"
    repl_09 = f"""                        if sig9 != 0:
                            p9_lim = round05(wall9 + 0.5) if sig9 == 1 else round05(wall9 - 0.5)
                            tp_calc = calc_wdo_target_pts(p9_lim, sig9, {tpt}, 22.0, m_levels_walls, m_levels_all)
                            sl_custom = {sl_expr}
                            arm_pending_order(sig9, 1, p9_lim, new_bar_time, new_bar_open, tp_calc, sl_custom, 6.5, 1.5, 13.5, 5.0, 16, wall9, {bem}, 1.5, 2, today_str)"""
    ns = dict(wsim.__dict__)
    exec(src_orig.replace(t_block_09, repl_09, 1), ns)
    sim_func = ns['simulate_wdo_core_slot']
    tr = sim_func(9, df_wdo, gex, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7, cost_pts=0.5)
    s = wsim.summarize_wdo_trades(tr, label)
    print(f"{label:48s} | Tr={s['Trades']:3d} | WR={s['WR%']:4.1f}% | PF={s['PF_com_custo']:4.2f} | Net=R$ {s['R$_com_custo']:6.0f} | DD=R$ {s['DD_com_custo']:4.0f} | RetDD={s['RetDD_com_custo']:4.2f}")

