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

test_cases_10 = [
    ('WDO-10_BASELINE_16p', '16.0', '16.0', '10.0', '10.0', 1, 1.5),
    ('WDO-10_TP_MIDWALL', 'calc_wdo_target_pts(new_bar_open, 1, 1, 16.0, m_levels_walls, m_levels_all)', 'calc_wdo_target_pts(new_bar_open, -1, 1, 16.0, m_levels_walls, m_levels_all)', '10.0', '10.0', 1, 1.5),
    ('WDO-10_TP_MAINWALL', 'calc_wdo_target_pts(new_bar_open, 1, 2, 16.0, m_levels_walls, m_levels_all)', 'calc_wdo_target_pts(new_bar_open, -1, 2, 16.0, m_levels_walls, m_levels_all)', '10.0', '10.0', 1, 1.5),
    ('WDO-10_TP_MIDWALL_BE_STG2', 'calc_wdo_target_pts(new_bar_open, 1, 1, 16.0, m_levels_walls, m_levels_all)', 'calc_wdo_target_pts(new_bar_open, -1, 1, 16.0, m_levels_walls, m_levels_all)', '10.0', '10.0', 2, 1.5),
    ('WDO-10_TP_16p_BE_STG2', '16.0', '16.0', '10.0', '10.0', 2, 1.5),
    ('WDO-10_TP_MIDWALL_SL_B1', 'calc_wdo_target_pts(new_bar_open, 1, 1, 16.0, m_levels_walls, m_levels_all)', 'calc_wdo_target_pts(new_bar_open, -1, 1, 16.0, m_levels_walls, m_levels_all)', 'max(7.0, min(14.0, round05(new_bar_open - b1_l + 1.0)))', 'max(7.0, min(14.0, round05(b1_h - new_bar_open + 1.0)))', 2, 1.5),
]

target_10 = '''                            if pos_nwe30_10 <= -0.75 and b1_c >= (b1_l + 0.50 * rng10) and (lw10 >= 0.25 * rng10 or b1_c > b1_o):
                                open_virtual_single(1, new_bar_open, new_bar_time, 16.0, 10.0, 5.5, 1.0, 0.0, 0.0, 24, False, 0.0, 1.0, b1_l, 1, 1.5)
                                last_entry_bar_time = b1_time
                            elif pos_nwe30_10 >= 0.75 and b1_c <= (b1_h - 0.50 * rng10) and (uw10 >= 0.25 * rng10 or b1_c < b1_o):
                                open_virtual_single(-1, new_bar_open, new_bar_time, 16.0, 10.0, 5.5, 1.0, 0.0, 0.0, 24, False, 0.0, 1.0, b1_h, 1, 1.5)
                                last_entry_bar_time = b1_time'''

for label, tp_b, tp_s, sl_b, sl_s, be_m, be_buf in test_cases_10:
    repl_10 = f'''                            if pos_nwe30_10 <= -0.75 and b1_c >= (b1_l + 0.50 * rng10) and (lw10 >= 0.25 * rng10 or b1_c > b1_o):
                                open_virtual_single(1, new_bar_open, new_bar_time, {tp_b}, {sl_b}, 5.5, 1.0, 0.0, 0.0, 24, False, 0.0, 1.0, b1_l, {be_m}, {be_buf})
                                last_entry_bar_time = b1_time
                            elif pos_nwe30_10 >= 0.75 and b1_c <= (b1_h - 0.50 * rng10) and (uw10 >= 0.25 * rng10 or b1_c < b1_o):
                                open_virtual_single(-1, new_bar_open, new_bar_time, {tp_s}, {sl_s}, 5.5, 1.0, 0.0, 0.0, 24, False, 0.0, 1.0, b1_h, {be_m}, {be_buf})
                                last_entry_bar_time = b1_time'''
    ns = dict(wsim.__dict__)
    exec(src_orig.replace(target_10, repl_10, 1), ns)
    sim_func = ns['simulate_wdo_core_slot']
    tr = sim_func(10, df_wdo, gex, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7, cost_pts=0.5)
    s = wsim.summarize_wdo_trades(tr, label)
    net_val = s['R$_com_custo']
    print(f"{label:30s} | Trades={s['Trades']:3d} | WR={s['WR%']:4.1f}% | PF={s['PF_com_custo']:4.2f} | Net=R$ {net_val:6.0f} | DD=R$ {s['DD_com_custo']:4.0f} | RetDD={s['RetDD_com_custo']:4.2f}")
