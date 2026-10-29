"""
Simulador e Otimizador Completo: Alinhamento da Física das 16 Estratégias do WIN
com a Matriz Vencedora do WDO + Recalibração BE/Trail (WIN 177k: 230-250 pts / lock 45 pts)
+ 3 Pilares Estruturais (BE Protegido pela Wall em 2 Estágios, Alvos/Parciais nas Walls e Stop/Limit Barra[1]).
"""

import os
import sys
import math
import time
import numpy as np
import pandas as pd

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from research.discover_gex_nwe_setups import compute_nwe_series
from research.optimizers.optimize_existing_16_setups import (
    round5,
    window_ok,
    load_win_and_wdo_aligned,
    find_structural_targets,
    simulate_single_est_slot,
    calc_slot_summary,
)


def simulate_aligned_win_wdo_slot(
    est_id: int,
    df: pd.DataFrame,
    gex_by_date: dict,
    n50_c: np.ndarray, n50_u: np.ndarray, n50_l: np.ndarray, n50_s: np.ndarray,
    n30_c: np.ndarray, n30_u: np.ndarray, n30_l: np.ndarray, n30_s: np.ndarray,
    rsi7s: np.ndarray,
    be_mode: str = "BE_WALL_2STAGE_177K",  # "BE_RECAL_ZERO", "BE_WALL_SHIELD", "BE_WALL_2STAGE_177K"
    wall_shield_buf: float = 20.0,
    tp_mode: str = "TP_CURRENT",           # "TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"
    entry_override: str = "ALIGNED",       # "ALIGNED", "STOP_B1_EXT", "LIMIT_B1_EXT", "LIMIT_B1_MID"
    replace_13_16_pa: bool = False,        # Opção A: substituir slots de baixo Ret/DD por setups PA Barra[1]
    front_run_pts: float = 20.0,
    cost_pts: float = 10.0,
):
    dates = df["session_date"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values
    wdo_ret3 = df["wdo_ret3"].values
    wdo_z = df["wdo_z"].values

    trades = []
    entry_events = []
    wall_saves = 0
    partial_hits = 0

    n = len(df)
    idx = 2
    last_trade_date = ""
    last_entry_bar_idx = -1

    while idx < n - 1:
        b1_idx = idx - 1
        b1_date = dates[b1_idx]
        today_str = dates[idx]

        if today_str < "2026-05-11" or today_str not in gex_by_date or b1_date != today_str:
            idx += 1
            continue

        new_tmin = int(t_mins[idx])
        b1_tmin = int(t_mins[b1_idx])
        if new_tmin >= 1035:
            idx += 1
            continue

        g = gex_by_date[today_str]
        m_levels_walls = g["walls"]
        m_levels_mid = g["mid_walls"]
        m_levels_all = np.sort(np.concatenate([m_levels_walls, m_levels_mid])) if len(m_levels_mid) > 0 else m_levels_walls
        m_gamma_flip = g["gamma_flip"] or 0.0
        if len(m_levels_all) == 0:
            idx += 1
            continue

        b1_o, b1_h, b1_l, b1_c = opens[b1_idx], highs[b1_idx], lows[b1_idx], closes[b1_idx]
        new_bar_open = opens[idx]

        m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1 = n50_c[b1_idx], n50_u[b1_idx], n50_l[b1_idx], n50_s[b1_idx]
        m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1 = n30_c[b1_idx], n30_u[b1_idx], n30_l[b1_idx], n30_s[b1_idx]
        m_rsi7_1 = rsi7s[b1_idx]
        m_wdo_ret3_1 = wdo_ret3[b1_idx]
        m_wdo_z_1 = wdo_z[b1_idx]

        bw50 = max(1.0, m_n50_u_1 - m_n50_l_1)
        pos50 = (b1_c - m_n50_l_1) / bw50
        bw30 = max(1.0, m_n30_u_1 - m_n30_l_1)
        pos30 = (b1_c - m_n30_l_1) / bw30

        body1 = b1_c - b1_o
        rng1 = max(1.0, b1_h - b1_l)

        dists_all_l = np.abs(m_levels_all - b1_l)
        i_all_l = int(np.argmin(dists_all_l))
        d_l, lvl_s = float(dists_all_l[i_all_l]), float(m_levels_all[i_all_l])

        dists_all_h = np.abs(m_levels_all - b1_h)
        i_all_h = int(np.argmin(dists_all_h))
        d_h, lvl_r = float(dists_all_h[i_all_h]), float(m_levels_all[i_all_h])

        if len(m_levels_walls) > 0:
            dw_l = np.abs(m_levels_walls - b1_l)
            iw_l = int(np.argmin(dw_l))
            dw_l_main, w_s_main = float(dw_l[iw_l]), float(m_levels_walls[iw_l])

            dw_h = np.abs(m_levels_walls - b1_h)
            iw_h = int(np.argmin(dw_h))
            dw_h_main, w_r_main = float(dw_h[iw_h]), float(m_levels_walls[iw_h])
        else:
            dw_l_main, w_s_main = 999999.0, 0.0
            dw_h_main, w_r_main = 999999.0, 0.0

        sig_type = None
        sig_dir = 0
        sig_px = 0.0
        # Parâmetros recalibrados p/ WINZ26 177k:
        # Stage 1 (Wall Shield): 155 pts | Stage 2 (BE Lock 45 pts): 235 pts | Trail: 340 / 125 pts
        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = (
            550.0, 240.0, 155.0, 235.0, 45.0, 340.0, 125.0, 16
        )
        def_wall = 0.0
        step2_dist, step3_dist, lot1, lot2, lot3 = 0.0, 0.0, 1, 0, 0

        # =====================================================================
        # BLOCO 1: SCALPER & ABSORÇÃO (EST-01, 02, 03, 05)
        # Absorção/Rejeição nas Walls + Ordens Limit ancoradas em pos50
        # (eliminando o deadlock do c50) + GammaFlip + Offsets descorrelacionados
        # =====================================================================
        if est_id in (1, 2):
            wm_rej = "NY_1000_1630" if est_id == 1 else "FULL_09_17"
            wm_lim = "NY_1000_1630" if est_id == 1 else "CORE_09_1615"
            # Descorrelação entre EST-01 (offset 0) e EST-02 (offset +10 pts)
            l_off = 0.0 if est_id == 1 else 10.0
            c_buy = (b1_c > b1_o and (b1_c - b1_l) >= 0.5 * rng1)
            c_sell = (b1_c < b1_o and (b1_h - b1_c) >= 0.5 * rng1)

            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, wm_rej):
                # 1A. Absorção/Rejeição na Wall no extremo do canal NWE (pos50 <= 0.35 / >= 0.65)
                if d_l <= 70.0 and -25.0 <= (b1_c - lvl_s) <= 80.0 and pos50 <= 0.32 and m_rsi7_1 <= 38.0 and c_buy and m_n50_s_1 >= -12.0:
                    sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, lvl_s
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                elif d_h <= 70.0 and -25.0 <= (lvl_r - b1_c) <= 80.0 and pos50 >= 0.68 and m_rsi7_1 >= 62.0 and c_sell and m_n50_s_1 <= 12.0:
                    sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, lvl_r
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                # 1B. Impulso de defesa na Wall (apenas EST-01, sem a trava cega de 85 pts -> até 180 pts)
                if sig_type is None and est_id == 1:
                    for lvl in m_levels_all:
                        if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 180.0 and body1 >= 55.0 and m_n50_s_1 >= 4.5 and pos50 < 0.85:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                            break
                        if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 180.0 and (-body1) >= 55.0 and m_n50_s_1 <= -4.5 and pos50 > 0.15:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                            break

            # 1C. Ordem Limit na Wall eliminando o deadlock do c50:
            # Opera tanto (a) Pullback em tendência (m_n50_s_1 >= 5.0 e pos50 <= 0.65)
            # quanto (b) Absorção estilo WDO no extremo do canal (pos50 <= 0.35 + GammaFlip e slope não derretendo)
            if sig_type is None and window_ok(new_tmin, wm_lim):
                buy_lim_ok = (d_l <= 65.0 and b1_c > (lvl_s + l_off)) and (
                    (m_n50_s_1 >= 5.5 and pos50 <= 0.68) or
                    (pos50 <= 0.35 and m_n50_s_1 >= -4.0 and (m_gamma_flip <= 0.0 or b1_c >= m_gamma_flip))
                )
                sell_lim_ok = (d_h <= 65.0 and b1_c < (lvl_r - l_off)) and (
                    (m_n50_s_1 <= -5.5 and pos50 >= 0.32) or
                    (pos50 >= 0.65 and m_n50_s_1 <= 4.0 and (m_gamma_flip <= 0.0 or b1_c <= m_gamma_flip))
                )
                if buy_lim_ok:
                    sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(lvl_s + l_off), lvl_s
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 225.0, 45.0, 320.0, 115.0, 15
                elif sell_lim_ok:
                    sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(lvl_r - l_off), lvl_r
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 225.0, 45.0, 320.0, 115.0, 15

        elif est_id == 3:
            # EST-03: Arbitragem Cambial Confluência WIN+WDO na Wall (offset +5 pts p/ descorrelacionar)
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 180.0 and body1 >= 50.0 and m_n50_s_1 >= 4.0 and pos50 < 0.85 and (m_wdo_ret3_1 <= 2.0 or m_wdo_z_1 <= 0.0):
                        sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 16
                        break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 180.0 and (-body1) >= 50.0 and m_n50_s_1 <= -4.0 and pos50 > 0.15 and (m_wdo_ret3_1 >= -2.0 or m_wdo_z_1 >= 0.0):
                        sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 16
                        break
            if sig_type is None and window_ok(new_tmin, "FULL_09_17"):
                wdo_buy_ok = (m_wdo_ret3_1 <= 2.0 or m_wdo_z_1 <= 0.2)
                wdo_sell_ok = (m_wdo_ret3_1 >= -2.0 or m_wdo_z_1 >= -0.2)
                if wdo_buy_ok and d_l <= 65.0 and b1_c > (lvl_s + 5.0) and ((m_n50_s_1 >= 6.0 and pos50 <= 0.70) or (pos50 <= 0.35 and m_n50_s_1 >= -3.0)):
                    sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(lvl_s + 5.0), lvl_s
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 16
                elif wdo_sell_ok and d_h <= 65.0 and b1_c < (lvl_r - 5.0) and ((m_n50_s_1 <= -6.0 and pos50 >= 0.30) or (pos50 >= 0.65 and m_n50_s_1 <= 3.0)):
                    sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(lvl_r - 5.0), lvl_r
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 16

        elif est_id == 5:
            # EST-05: Cluster NWE30 + NWE50 + Wall (pos30 + pos50 + offset +15 pts p/ descorrelacionar)
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 180.0 and body1 >= 45.0 and m_n30_s_1 >= 5.0 and m_n50_s_1 >= 4.0 and pos30 < 0.85:
                        sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                        break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 180.0 and (-body1) >= 45.0 and m_n30_s_1 <= -5.0 and m_n50_s_1 <= -4.0 and pos30 > 0.15:
                        sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                        break
            if sig_type is None and window_ok(new_tmin, "CORE_09_1615"):
                if d_l <= 60.0 and b1_c > (lvl_s + 15.0) and ((m_n30_s_1 >= 5.0 and m_n50_s_1 >= 5.0 and pos30 <= 0.70) or (pos30 <= 0.35 and pos50 <= 0.38 and m_n50_s_1 >= -3.0)):
                    sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(lvl_s + 15.0), lvl_s
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 225.0, 45.0, 320.0, 115.0, 16
                elif d_h <= 60.0 and b1_c < (lvl_r - 15.0) and ((m_n30_s_1 <= -5.0 and m_n50_s_1 <= -5.0 and pos30 >= 0.30) or (pos30 >= 0.65 and pos50 >= 0.62 and m_n50_s_1 <= 3.0)):
                    sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(lvl_r - 15.0), lvl_r
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 225.0, 45.0, 320.0, 115.0, 16

        # =====================================================================
        # BLOCO 2: PULLBACK & LIMIT DESCORRELACIONADOS (EST-04, 06, 09, 10)
        # =====================================================================
        elif est_id == 4:
            # EST-04: Reteste Limit de Wall Rompida c/ GammaFlip (tolerância ampliada p/ 220 pts, offset -5 pts)
            if window_ok(new_tmin, "FULL_09_17"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 220.0 and body1 >= 45.0 and m_n50_s_1 >= 5.5:
                        if (m_gamma_flip <= 0.0 or b1_c >= m_gamma_flip) and pos50 < 0.85:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(float(lvl) - 5.0), float(lvl)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 520.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                            break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 220.0 and (-body1) >= 45.0 and m_n50_s_1 <= -5.5:
                        if (m_gamma_flip <= 0.0 or b1_c <= m_gamma_flip) and pos50 > 0.15:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(float(lvl) + 5.0), float(lvl)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 520.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 16
                            break

        elif est_id == 6:
            # EST-06: Pullback Limit na Wall c/ Slope + Reteste (tolerância 220 pts, offset +20 pts p/ descorrelacionar)
            if window_ok(new_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 220.0 and body1 >= 42.0 and m_n50_s_1 >= 5.0 and pos50 < 0.85:
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(float(lvl) + 15.0), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 16
                        break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 220.0 and (-body1) >= 42.0 and m_n50_s_1 <= -5.0 and pos50 > 0.15:
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(float(lvl) - 15.0), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 16
                        break
                if sig_type is None:
                    if d_l <= 65.0 and b1_c > (lvl_s + 20.0) and ((m_n50_s_1 >= 6.5 and pos50 <= 0.70) or (pos50 <= 0.36 and b1_c > b1_o and m_n50_s_1 >= -3.0)):
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(lvl_s + 20.0), lvl_s
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 15
                    elif d_h <= 65.0 and b1_c < (lvl_r - 20.0) and ((m_n50_s_1 <= -6.5 and pos50 >= 0.30) or (pos50 >= 0.64 and b1_c < b1_o and m_n50_s_1 <= 3.0)):
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(lvl_r - 20.0), lvl_r
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 155.0, 235.0, 45.0, 330.0, 120.0, 15

        elif est_id == 9:
            # EST-09: Breakout Stop & Limit Wall (NY_1000_1630 - All Levels - Offset Limit -10 pts / b1.low)
            if window_ok(new_tmin, "NY_1000_1630"):
                if m_n30_s_1 >= 5.0 and b1_c > b1_o and body1 >= 35.0 and pos30 < 0.80:
                    for lvl in m_levels_all:
                        if lvl >= b1_c - 5.0 and (lvl - b1_c) <= 65.0:
                            sig_type, sig_dir, sig_px, def_wall = "STOP", 1, round5(max(float(lvl) + 10.0, b1_h + 5.0)), float(lvl)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16
                            break
                if sig_type is None and m_n30_s_1 <= -5.0 and b1_c < b1_o and (-body1) >= 35.0 and pos30 > 0.20:
                    for lvl in m_levels_all[::-1]:
                        if lvl <= b1_c + 5.0 and (b1_c - lvl) <= 65.0:
                            sig_type, sig_dir, sig_px, def_wall = "STOP", -1, round5(min(float(lvl) - 10.0, b1_l - 5.0)), float(lvl)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16
                            break
                if sig_type is None:
                    if d_l <= 65.0 and b1_c > (lvl_s - 10.0) and ((m_n50_s_1 >= 6.0 and pos50 <= 0.68) or (pos50 <= 0.35 and m_n50_s_1 >= -3.0)):
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(lvl_s - 10.0), lvl_s
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16
                    elif d_h <= 65.0 and b1_c < (lvl_r + 10.0) and ((m_n50_s_1 <= -6.0 and pos50 >= 0.32) or (pos50 >= 0.65 and m_n50_s_1 <= 3.0)):
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(lvl_r + 10.0), lvl_r
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16

        elif est_id == 10:
            # EST-10: Stop & Limit SÓ NAS WALLS PRINCIPAIS (CORE_09_1615 - Main Walls Only + pos50 + GammaFlip)
            if window_ok(new_tmin, "CORE_09_1615") and len(m_levels_walls) > 0:
                if m_n30_s_1 >= 4.5 and b1_c > b1_o and body1 >= 35.0 and pos30 < 0.82:
                    for w in m_levels_walls:
                        if w >= b1_c - 5.0 and (w - b1_c) <= 65.0:
                            sig_type, sig_dir, sig_px, def_wall = "STOP", 1, round5(max(float(w) + 10.0, b1_h + 5.0)), float(w)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16
                            break
                if sig_type is None and m_n30_s_1 <= -4.5 and b1_c < b1_o and (-body1) >= 35.0 and pos30 > 0.18:
                    for w in m_levels_walls[::-1]:
                        if w <= b1_c + 5.0 and (b1_c - w) <= 65.0:
                            sig_type, sig_dir, sig_px, def_wall = "STOP", -1, round5(min(float(w) - 10.0, b1_l - 5.0)), float(w)
                            tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16
                            break
                if sig_type is None:
                    if dw_l_main <= 85.0 and b1_c > w_s_main and ((m_n50_s_1 >= 5.0 and pos50 <= 0.70) or (pos50 <= 0.35 and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip) and m_n50_s_1 >= -4.0)):
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(w_s_main), w_s_main
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16
                    elif dw_h_main <= 85.0 and b1_c < w_r_main and ((m_n50_s_1 <= -5.0 and pos50 >= 0.30) or (pos50 >= 0.65 and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip) and m_n50_s_1 <= 4.0)):
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(w_r_main), w_r_main
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 160.0, 240.0, 45.0, 340.0, 125.0, 16

        # =====================================================================
        # BLOCO 3: BREAKOUT INSTITUCIONAL (EST-07, 08, 12, 15)
        # Sem a trava cega de 85 pts -> Tolerância até 260 pts (Market até 160 pts
        # e Pullback Limit na Wall recém-rompida quando estica de 160 a 260 pts!)
        # =====================================================================
        elif est_id in (7, 8):
            wm_bo = "NY_1000_1630" if est_id == 7 else "CORE_09_1615"
            min_bd = 65.0 if est_id == 7 else 50.0
            tp_b = 650.0 if est_id == 7 else 450.0
            sl_b = 260.0 if est_id == 7 else 225.0
            s1_b = 160.0 if est_id == 7 else 145.0
            be_b = 240.0 if est_id == 7 else 220.0
            tr_t = 350.0 if est_id == 7 else 260.0
            tr_d = 125.0 if est_id == 7 else 105.0
            pb_off = 5.0 if est_id == 7 else 12.0

            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, wm_bo):
                slope_ok_b = (m_n50_s_1 >= 4.0) if est_id == 7 else (m_n50_s_1 >= 4.0 and m_n30_s_1 >= 4.0)
                slope_ok_s = (m_n50_s_1 <= -4.0) if est_id == 7 else (m_n50_s_1 <= -4.0 and m_n30_s_1 <= -4.0)
                for lvl in m_levels_all:
                    if b1_o <= lvl + 15.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 260.0 and body1 >= min_bd and slope_ok_b and pos50 < 0.85:
                        if (b1_c - lvl) <= 155.0:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        else:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(float(lvl) + pb_off), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = tp_b, sl_b, s1_b, be_b, 45.0, tr_t, tr_d, 16
                        break
                    if b1_o >= lvl - 15.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 260.0 and (-body1) >= min_bd and slope_ok_s and pos50 > 0.15:
                        if (lvl - b1_c) <= 155.0:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        else:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(float(lvl) - pb_off), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = tp_b, sl_b, s1_b, be_b, 45.0, tr_t, tr_d, 16
                        break

        elif est_id == 12:
            # EST-12: Piramidação no Lucro 1+1 Lote (Tolerância até 260 pts + Pullback Limit na Wall se esticar)
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NY_1000_1630"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 15.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 260.0 and body1 >= 55.0 and m_n50_s_1 >= 4.0 and pos50 < 0.85:
                        if (b1_c - lvl) <= 155.0:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        else:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(float(lvl) + 8.0), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 320.0, 115.0, 18
                        break
                    if b1_o >= lvl - 15.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 260.0 and (-body1) >= 55.0 and m_n50_s_1 <= -4.0 and pos50 > 0.15:
                        if (lvl - b1_c) <= 155.0:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        else:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(float(lvl) - 8.0), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 320.0, 115.0, 18
                        break

        elif est_id == 15:
            # EST-15: Breakout Matinal sem trava de 85 pts -> até 260 pts (Confirmado Ret/DD = 9.25 c/ STOP_B1_EXT e TP_MIDWALL!)
            if last_trade_date != b1_date and 545 <= b1_tmin <= 780:
                for lvl in m_levels_all:
                    if b1_o <= lvl + 15.0 and b1_c > lvl + 15.0 and (b1_c - lvl) <= 260.0 and body1 >= 50.0 and m_n50_s_1 >= 4.5 and pos50 < 0.85:
                        if (b1_c - lvl) <= 150.0:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        else:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(float(lvl) + 10.0), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 900.0, 360.0, 180.0, 250.0, 50.0, 480.0, 180.0, 120
                        break
                    if b1_o >= lvl - 15.0 and b1_c < lvl - 15.0 and (lvl - b1_c) <= 260.0 and (-body1) >= 50.0 and m_n50_s_1 <= -4.5 and pos50 > 0.15:
                        if (lvl - b1_c) <= 150.0:
                            sig_type, sig_dir, sig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        else:
                            sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(float(lvl) - 10.0), float(lvl)
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 900.0, 360.0, 180.0, 250.0, 50.0, 480.0, 180.0, 120
                        break

        # =====================================================================
        # BLOCO 4: GRIDS (EST-11, 13, 14) & POSICIONAL (EST-16)
        # =====================================================================
        elif est_id == 11:
            # EST-11: Grid Pullback Tendência + Absorção pos50 <= 0.32 / >= 0.68 + d_l <= 80 pts + GammaFlip (NO_LUNCH)
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NO_LUNCH"):
                buy_grid11 = (d_l <= 80.0 and -15.0 <= (b1_c - lvl_s) <= 85.0 and b1_c > b1_o) and (
                    (m_n50_s_1 >= 3.0 and pos50 <= 0.68) or
                    (pos50 <= 0.32 and m_n50_s_1 >= -2.0 and (m_gamma_flip <= 0.0 or b1_c >= m_gamma_flip))
                )
                sell_grid11 = (d_h <= 80.0 and -15.0 <= (lvl_r - b1_c) <= 85.0 and b1_c < b1_o) and (
                    (m_n50_s_1 <= -3.0 and pos50 >= 0.32) or
                    (pos50 >= 0.68 and m_n50_s_1 <= 2.0 and (m_gamma_flip <= 0.0 or b1_c <= m_gamma_flip))
                )
                if buy_grid11:
                    sig_type, sig_dir, sig_px, def_wall = "GRID", 1, new_bar_open, lvl_s
                    step2_dist, step3_dist, lot1, lot2, lot3 = 450.0, 900.0, 1, 2, 0
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, max_hold = 280.0, 650.0, 150.0, 220.0, 45.0, 24
                elif sell_grid11:
                    sig_type, sig_dir, sig_px, def_wall = "GRID", -1, new_bar_open, lvl_r
                    step2_dist, step3_dist, lot1, lot2, lot3 = 450.0, 900.0, 1, 2, 0
                    tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, max_hold = 280.0, 650.0, 150.0, 220.0, 45.0, 24

        elif est_id == 13:
            if replace_13_16_pa:
                # Opção A Vaga 13: Rolling Stop Barra[1] na Wall c/ Tendência/Rejeição (NO_LUNCH)
                if window_ok(new_tmin, "NO_LUNCH"):
                    if d_l <= 55.0 and b1_c <= b1_o and pos50 <= 0.55 and m_n50_s_1 >= -4.0:
                        sig_type, sig_dir, sig_px, def_wall = "STOP", 1, round5(b1_h + 5.0), lvl_s
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 18
                    elif d_h <= 55.0 and b1_c >= b1_o and pos50 >= 0.45 and m_n50_s_1 <= 4.0:
                        sig_type, sig_dir, sig_px, def_wall = "STOP", -1, round5(b1_l - 5.0), lvl_r
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 230.0, 45.0, 330.0, 120.0, 18
            else:
                # EST-13 Grid 1+2 Main Walls destravado: filtro de pos50 <= 0.62 em tendência OU pos50 <= 0.32 + GammaFlip + NO_LUNCH
                if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NO_LUNCH") and len(m_levels_walls) > 0:
                    buy_g13 = (dw_l_main <= 80.0 and -15.0 <= (b1_c - w_s_main) <= 85.0 and b1_c > b1_o) and (
                        (m_n50_s_1 >= 3.5 and pos50 <= 0.62 and (m_gamma_flip <= 0.0 or b1_c >= m_gamma_flip)) or
                        (pos50 <= 0.32 and m_n50_s_1 >= 0.0)
                    )
                    sell_g13 = (dw_h_main <= 80.0 and -15.0 <= (w_r_main - b1_c) <= 85.0 and b1_c < b1_o) and (
                        (m_n50_s_1 <= -3.5 and pos50 >= 0.38 and (m_gamma_flip <= 0.0 or b1_c <= m_gamma_flip)) or
                        (pos50 >= 0.68 and m_n50_s_1 <= 0.0)
                    )
                    if buy_g13:
                        sig_type, sig_dir, sig_px, def_wall = "GRID", 1, new_bar_open, w_s_main
                        step2_dist, step3_dist, lot1, lot2, lot3 = 480.0, 960.0, 1, 2, 0
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, max_hold = 280.0, 650.0, 150.0, 220.0, 45.0, 24
                    elif sell_g13:
                        sig_type, sig_dir, sig_px, def_wall = "GRID", -1, new_bar_open, w_r_main
                        step2_dist, step3_dist, lot1, lot2, lot3 = 480.0, 960.0, 1, 2, 0
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, max_hold = 280.0, 650.0, 150.0, 220.0, 45.0, 24

        elif est_id == 14:
            if replace_13_16_pa:
                # Opção A Vaga 14: Rolling Stop Barra[1] nas Main Walls (CORE_09_1615) — Ret/DD = 3.75 na rodada anterior!
                if window_ok(new_tmin, "CORE_09_1615") and len(m_levels_walls) > 0:
                    if dw_l_main <= 85.0 and pos50 <= 0.40 and b1_c <= b1_o:
                        sig_type, sig_dir, sig_px, def_wall = "STOP", 1, round5(b1_h + 5.0), w_s_main
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 155.0, 230.0, 45.0, 350.0, 130.0, 18
                    elif dw_h_main <= 85.0 and pos50 >= 0.60 and b1_c >= b1_o:
                        sig_type, sig_dir, sig_px, def_wall = "STOP", -1, round5(b1_l - 5.0), w_r_main
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 600.0, 250.0, 155.0, 230.0, 45.0, 350.0, 130.0, 18
            else:
                if last_entry_bar_idx != b1_idx and 545 <= b1_tmin <= 930 and len(m_levels_walls) > 0:
                    buy_g14 = (dw_l_main <= 80.0 and -20.0 <= (b1_c - w_s_main) <= 85.0 and b1_c > b1_o) and (
                        (m_n50_s_1 >= 3.5 and pos50 <= 0.60 and (m_gamma_flip <= 0.0 or b1_c >= m_gamma_flip)) or
                        (pos50 <= 0.32 and m_n50_s_1 >= 0.5)
                    )
                    sell_g14 = (dw_h_main <= 80.0 and -20.0 <= (w_r_main - b1_c) <= 85.0 and b1_c < b1_o) and (
                        (m_n50_s_1 <= -3.5 and pos50 >= 0.40 and (m_gamma_flip <= 0.0 or b1_c <= m_gamma_flip)) or
                        (pos50 >= 0.68 and m_n50_s_1 <= -0.5)
                    )
                    if buy_g14:
                        sig_type, sig_dir, sig_px, def_wall = "GRID", 1, new_bar_open, w_s_main
                        step2_dist, step3_dist, lot1, lot2, lot3 = 507.0, 1014.0, 1, 1, 2
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, max_hold = 280.0, 620.0, 150.0, 220.0, 45.0, 26
                    elif sell_g14:
                        sig_type, sig_dir, sig_px, def_wall = "GRID", -1, new_bar_open, w_r_main
                        step2_dist, step3_dist, lot1, lot2, lot3 = 507.0, 1014.0, 1, 1, 2
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, max_hold = 280.0, 620.0, 150.0, 220.0, 45.0, 26

        elif est_id == 16:
            if replace_13_16_pa:
                # Opção A Vaga 16: Limit Extremo / 50% Barra[1] nas Walls (09h10-15h30)
                if 550 <= new_tmin <= 930:
                    if d_l <= 55.0 and b1_c > b1_o and pos50 <= 0.42 and m_n50_s_1 >= -2.0:
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", 1, round5(b1_l + 5.0), lvl_s
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 580.0, 240.0, 150.0, 230.0, 45.0, 340.0, 120.0, 18
                    elif d_h <= 55.0 and b1_c < b1_o and pos50 >= 0.58 and m_n50_s_1 <= 2.0:
                        sig_type, sig_dir, sig_px, def_wall = "LIMIT", -1, round5(b1_h - 5.0), lvl_r
                        tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 580.0, 240.0, 150.0, 230.0, 45.0, 340.0, 120.0, 18
            else:
                if last_trade_date != b1_date and 550 <= new_tmin <= 840:
                    if m_n30_s_1 >= 5.0 and b1_c > b1_o and body1 >= 40.0 and pos30 < 0.80:
                        for lvl in m_levels_all:
                            if lvl >= b1_c - 5.0 and (lvl - b1_c) <= 60.0:
                                sig_type, sig_dir, sig_px, def_wall = "STOP", 1, round5(max(float(lvl) + 10.0, b1_h + 5.0)), float(lvl)
                                tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 1200.0, 380.0, 180.0, 250.0, 50.0, 480.0, 180.0, 120
                                break
                    if sig_type is None and m_n30_s_1 <= -5.0 and b1_c < b1_o and (-body1) >= 40.0 and pos30 > 0.20:
                        for lvl in m_levels_all[::-1]:
                            if lvl <= b1_c + 5.0 and (b1_c - lvl) <= 60.0:
                                sig_type, sig_dir, sig_px, def_wall = "STOP", -1, round5(min(float(lvl) - 10.0, b1_l - 5.0)), float(lvl)
                                tp_pts, sl_pts, s1_trig, be_trig_177k, be_lock_177k, tr_trig, tr_dist, max_hold = 1200.0, 380.0, 180.0, 250.0, 50.0, 480.0, 180.0, 120
                                break

        if sig_type is None:
            idx += 1
            continue

        # Entry Overrides (Stop/Limit Barra Anterior b1)
        if entry_override != "ALIGNED" and sig_type != "GRID":
            if entry_override == "STOP_B1_EXT" and sig_type == "MKT":
                sig_type = "STOP"
                sig_px = round5(b1_h + 5.0) if sig_dir == 1 else round5(b1_l - 5.0)
            elif entry_override == "LIMIT_B1_EXT" and sig_type == "LIMIT":
                sig_px = round5(max(def_wall - 10.0, b1_l + 5.0)) if sig_dir == 1 else round5(min(def_wall + 10.0, b1_h - 5.0))
            elif entry_override == "LIMIT_B1_MID" and sig_type in ("LIMIT", "MKT"):
                sig_type = "LIMIT"
                sig_px = round5(0.5 * (b1_h + b1_l))

        opened_intrabar = False
        if sig_type in ("MKT", "GRID"):
            entry_px = round5(new_bar_open)
            last_entry_bar_idx = b1_idx
            if est_id in (15, 16) and not (est_id == 16 and replace_13_16_pa):
                last_trade_date = b1_date
        else:
            p5 = round5(sig_px)
            if sig_type == "LIMIT" and sig_dir == 1 and new_bar_open < p5:
                idx += 1
                continue
            if sig_type == "LIMIT" and sig_dir == -1 and new_bar_open > p5:
                idx += 1
                continue
            if sig_type == "STOP" and sig_dir == 1 and new_bar_open > p5:
                idx += 1
                continue
            if sig_type == "STOP" and sig_dir == -1 and new_bar_open < p5:
                idx += 1
                continue

            if sig_type == "LIMIT":
                filled = (lows[idx] <= p5) if sig_dir == 1 else (highs[idx] >= p5)
            else:
                filled = (highs[idx] >= p5) if sig_dir == 1 else (lows[idx] <= p5)

            if not filled:
                idx += 1
                continue

            entry_px = p5
            opened_intrabar = True
            last_entry_bar_idx = idx
            if est_id in (15, 16) and not (est_id == 16 and replace_13_16_pa):
                last_trade_date = today_str

        entry_events.append((today_str, int(t_mins[idx]), sig_dir, float(entry_px)))

        mid_tp_px, main_tp_px, raw_mid_lvl, _ = find_structural_targets(entry_px, sig_dir, m_levels_walls, m_levels_all, front_run=front_run_pts)

        if sig_type == "GRID":
            lots = lot1
            leg_stage = 1
            p1_entry = entry_px
            avg_price = entry_px
            worst_off = (lot2 * step2_dist + lot3 * step3_dist) / float(lot1 + lot2 + lot3) if lot3 > 0 else (lot2 * step2_dist) / float(lot1 + lot2)
            init_sl_dist = max(sl_pts, worst_off + sl_pts)
            curr_sl = round5(entry_px - init_sl_dist) if sig_dir == 1 else round5(entry_px + init_sl_dist)
            curr_tp = round5(entry_px + tp_pts) if sig_dir == 1 else round5(entry_px - tp_pts)
            is_partial = False
            tp1_px = curr_tp
            tp2_px = curr_tp
        else:
            lots = 1
            leg_stage = 1
            p1_entry = entry_px
            avg_price = entry_px
            curr_sl = round5(entry_px - sl_pts) if sig_dir == 1 else round5(entry_px + sl_pts)
            if tp_mode == "TP_CURRENT":
                tp1_px = round5(entry_px + tp_pts) if sig_dir == 1 else round5(entry_px - tp_pts)
                tp2_px = tp1_px
                is_partial = False
            elif tp_mode == "TP_MIDWALL":
                tp1_px = mid_tp_px
                tp2_px = mid_tp_px
                is_partial = False
            elif tp_mode == "TP_MAIN_WALL":
                tp1_px = main_tp_px
                tp2_px = main_tp_px
                is_partial = False
            else:
                tp1_px = mid_tp_px
                tp2_px = main_tp_px
                is_partial = True

        if sig_dir == 1:
            shield_sl1 = round5(def_wall - wall_shield_buf)
            if shield_sl1 <= curr_sl or shield_sl1 >= entry_px:
                shield_sl1 = round5(entry_px - 0.35 * sl_pts)
        else:
            shield_sl1 = round5(def_wall + wall_shield_buf)
            if shield_sl1 >= curr_sl or shield_sl1 <= entry_px:
                shield_sl1 = round5(entry_px + 0.35 * sl_pts)

        be_active = False
        stage2_active = False
        partial_done = False
        partial_exit_px = 0.0
        max_fav_pts = 0.0
        bars_held = 0
        touched_zero_after_shield = False
        exit_px = entry_px

        j = idx
        while j < n:
            if dates[j] != today_str or int(t_mins[j]) >= 1035:
                exit_px = closes[j - 1] if dates[j] != today_str else opens[j]
                break

            oj, hj, lj, cj = opens[j], highs[j], lows[j], closes[j]

            if sig_type == "GRID":
                if leg_stage == 1 and lot2 > 0:
                    p2_lvl = (p1_entry - step2_dist) if sig_dir == 1 else (p1_entry + step2_dist)
                    if (sig_dir == 1 and lj <= p2_lvl) or (sig_dir == -1 and hj >= p2_lvl):
                        new_lots = lot1 + lot2
                        avg_price = round5((p1_entry * lot1 + p2_lvl * lot2) / float(new_lots))
                        lots = new_lots
                        leg_stage = 2
                        be_active = False
                        max_fav_pts = 0.0
                        curr_tp = round5(avg_price + tp_pts) if sig_dir == 1 else round5(avg_price - tp_pts)
                        curr_sl = round5(avg_price - sl_pts) if sig_dir == 1 else round5(avg_price + sl_pts)
                        tp2_px = curr_tp
                if leg_stage == 2 and lot3 > 0:
                    p3_lvl = (p1_entry - step3_dist) if sig_dir == 1 else (p1_entry + step3_dist)
                    if (sig_dir == 1 and lj <= p3_lvl) or (sig_dir == -1 and hj >= p3_lvl):
                        new_lots = lots + lot3
                        avg_price = round5((avg_price * lots + p3_lvl * lot3) / float(new_lots))
                        lots = new_lots
                        leg_stage = 3
                        be_active = False
                        max_fav_pts = 0.0
                        curr_tp = round5(avg_price + tp_pts) if sig_dir == 1 else round5(avg_price - tp_pts)
                        curr_sl = round5(avg_price - sl_pts) if sig_dir == 1 else round5(avg_price + sl_pts)
                        tp2_px = curr_tp

            eff_high, eff_low = hj, lj
            if j == idx and opened_intrabar:
                is_bull = cj >= oj
                if sig_type == "LIMIT":
                    if sig_dir == 1 and not is_bull:
                        eff_high = max(entry_px, cj)
                    elif sig_dir == -1 and is_bull:
                        eff_low = min(entry_px, cj)
                elif sig_type == "STOP":
                    if sig_dir == 1 and is_bull:
                        eff_low = min(entry_px, cj)
                    elif sig_dir == -1 and not is_bull:
                        eff_high = max(entry_px, cj)

            if sig_dir == 1:
                if be_active and eff_low <= avg_price + be_lock_177k and eff_low > curr_sl:
                    touched_zero_after_shield = True
                if eff_low <= curr_sl:
                    exit_px = curr_sl
                    break
                if is_partial and not partial_done and eff_high >= tp1_px:
                    partial_done = True
                    partial_exit_px = tp1_px
                    partial_hits += 1
                    be_active = True
                    curr_sl = max(curr_sl, round5(avg_price + be_lock_177k) if be_mode == "BE_RECAL_ZERO" else shield_sl1)
                if eff_high >= tp2_px:
                    exit_px = tp2_px
                    break

                fav = (cj - avg_price) if (j == idx and opened_intrabar) else (eff_high - avg_price)
                if fav > max_fav_pts:
                    max_fav_pts = fav

                if be_mode == "BE_RECAL_ZERO":
                    if be_trig_177k > 0 and not be_active and max_fav_pts >= be_trig_177k:
                        be_active = True
                        curr_sl = max(curr_sl, round5(avg_price + be_lock_177k))
                else:
                    # Estágio 1: Ao andar s1_trig (150-160 pts), reduz SL p/ trás da Wall (shield_sl1), sem sufocar em R$ 4,00!
                    if s1_trig > 0 and not be_active and max_fav_pts >= s1_trig:
                        be_active = True
                        curr_sl = max(curr_sl, shield_sl1)
                    # Estágio 2: Ao atingir o gatilho recalibrado do WIN 177k (230-250 pts) ou cruzar a MidWall, trava +45 pts!
                    if be_mode == "BE_WALL_2STAGE_177K" and not stage2_active:
                        if max_fav_pts >= be_trig_177k or cj > raw_mid_lvl + 10.0:
                            stage2_active = True
                            curr_sl = max(curr_sl, round5(avg_price + be_lock_177k))

                if tr_trig > 0 and max_fav_pts >= tr_trig:
                    curr_sl = max(curr_sl, round5(avg_price + max_fav_pts - tr_dist))

                if est_id == 12 and leg_stage == 1 and (cj - p1_entry) >= 130.0 and j + 1 < n and dates[j + 1] == today_str:
                    nxt_open = opens[j + 1]
                    avg_price = round5(0.5 * (p1_entry + nxt_open))
                    lots = 2
                    leg_stage = 2
                    curr_sl = max(curr_sl, round5(avg_price + 40.0))
            else:
                if be_active and eff_high >= avg_price - be_lock_177k and eff_high < curr_sl:
                    touched_zero_after_shield = True
                if eff_high >= curr_sl:
                    exit_px = curr_sl
                    break
                if is_partial and not partial_done and eff_low <= tp1_px:
                    partial_done = True
                    partial_exit_px = tp1_px
                    partial_hits += 1
                    be_active = True
                    curr_sl = min(curr_sl, round5(avg_price - be_lock_177k) if be_mode == "BE_RECAL_ZERO" else shield_sl1)
                if eff_low <= tp2_px:
                    exit_px = tp2_px
                    break

                fav = (avg_price - cj) if (j == idx and opened_intrabar) else (avg_price - eff_low)
                if fav > max_fav_pts:
                    max_fav_pts = fav

                if be_mode == "BE_RECAL_ZERO":
                    if be_trig_177k > 0 and not be_active and max_fav_pts >= be_trig_177k:
                        be_active = True
                        curr_sl = min(curr_sl, round5(avg_price - be_lock_177k))
                else:
                    if s1_trig > 0 and not be_active and max_fav_pts >= s1_trig:
                        be_active = True
                        curr_sl = min(curr_sl, shield_sl1)
                    if be_mode == "BE_WALL_2STAGE_177K" and not stage2_active:
                        if max_fav_pts >= be_trig_177k or cj < raw_mid_lvl - 10.0:
                            stage2_active = True
                            curr_sl = min(curr_sl, round5(avg_price - be_lock_177k))

                if tr_trig > 0 and max_fav_pts >= tr_trig:
                    curr_sl = min(curr_sl, round5(avg_price - max_fav_pts + tr_dist))

                if est_id == 12 and leg_stage == 1 and (p1_entry - cj) >= 130.0 and j + 1 < n and dates[j + 1] == today_str:
                    nxt_open = opens[j + 1]
                    avg_price = round5(0.5 * (p1_entry + nxt_open))
                    lots = 2
                    leg_stage = 2
                    curr_sl = min(curr_sl, round5(avg_price - 40.0))

            if not (j == idx and opened_intrabar):
                bars_held += 1
                if (est_id <= 14 or (est_id == 16 and replace_13_16_pa)) and bars_held >= max_hold:
                    exit_px = opens[j + 1] if (j + 1 < n and dates[j + 1] == today_str) else cj
                    break
            j += 1
        else:
            exit_px = closes[min(j, n - 1)]

        if is_partial and partial_done:
            pts1 = (partial_exit_px - avg_price) * sig_dir - cost_pts
            pts2 = (exit_px - avg_price) * sig_dir - cost_pts
            net_pts_unit = 0.5 * pts1 + 0.5 * pts2
        else:
            net_pts_unit = (exit_px - avg_price) * sig_dir - cost_pts

        if touched_zero_after_shield and net_pts_unit > 30.0:
            wall_saves += 1

        trades.append({
            "date": today_str,
            "est_id": est_id,
            "side": int(sig_dir),
            "pnl_pts": net_pts_unit * lots,
            "contracts": lots,
            "pnl_brl": net_pts_unit * lots * 0.20,
        })
        idx = max(idx + 1, j + 1)

    return trades, {"wall_saves": wall_saves, "partial_hits": partial_hits, "entries": entry_events}


def count_collisions(entries_by_est: dict):
    from collections import Counter
    c_bar = Counter()
    c_px = Counter()
    for est_id, evs in entries_by_est.items():
        for (d, tm, dr, px) in set(evs):
            c_bar[(d, tm, dr)] += 1
            c_px[(d, tm, dr, px)] += 1
    col_bar = sum(v - 1 for v in c_bar.values() if v > 1)
    col_px = sum(v - 1 for v in c_px.values() if v > 1)
    max_px = max(c_px.values()) if c_px else 0
    return col_bar, col_px, max_px


def run_all():
    t0 = time.time()
    print("=" * 115)
    print("  SÍNTESE WIN$N (177K): MATRIZ ALINHADA WDO + BREAKOUT 260P + BE 2-ESTÁGIOS (WALL SHIELD -> 235/45) + 3 PILARES")
    print("=" * 115)

    df, gex_by_date = load_win_and_wdo_aligned()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    legacy_all, aligned_grids_all, aligned_opA_all = [], [], []
    entries_opA = {}
    rows = []

    for est_id in range(1, 17):
        leg_tr, leg_st = simulate_single_est_slot(
            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode="BE_ZERO", tp_mode="TP_CURRENT"
        )
        m_leg = calc_slot_summary(leg_tr, leg_st)
        legacy_all.extend(leg_tr)

        # Caminho Grids Mantidos (pos50 + GammaFlip) vs Opção A (Substituição PA 13, 14, 16; EST-15 já é 9.25 c/ Breakout 260p!)
        modes_to_run = (0, 1) if est_id in (13, 14, 16) else (0,)
        for mode_idx in modes_to_run:
            rep_pa = (mode_idx == 1 and est_id in (13, 14, 16))
            best_m = None
            best_tr = None
            best_st = None
            best_cfg = ""

            ent_cands = ["ALIGNED"] if (est_id in (9, 10, 11) or (est_id in (13, 14, 16) and not rep_pa)) else ["ALIGNED", "STOP_B1_EXT", "LIMIT_B1_EXT", "LIMIT_B1_MID"]
            be_cands = ["BE_RECAL_ZERO", "BE_WALL_SHIELD", "BE_WALL_2STAGE_177K"]
            tp_cands = ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL"] if (est_id in (11, 13, 14) and not rep_pa) else ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"]

            for e_ov in ent_cands:
                for b_m in be_cands:
                    bufs = [0.0] if b_m == "BE_RECAL_ZERO" else [15.0, 25.0]
                    for bf in bufs:
                        for t_m in tp_cands:
                            tr_c, st_c = simulate_aligned_win_wdo_slot(
                                est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                                be_mode=b_m, wall_shield_buf=bf, tp_mode=t_m, entry_override=e_ov, replace_13_16_pa=rep_pa
                            )
                            mc = calc_slot_summary(tr_c, st_c)
                            if best_m is None:
                                best_m, best_tr, best_st = mc, tr_c, st_c
                                best_cfg = f"{'PA_Sub' if rep_pa else e_ov} | {b_m}({int(bf)}) | {t_m}"
                                continue
                            if len(tr_c) < 12:
                                continue
                            sc_curr = mc["NetBRL"] + 2.0 * (mc["NetBRL"] - mc["MaxDD_BRL"])
                            sc_best = best_m["NetBRL"] + 2.0 * (best_m["NetBRL"] - best_m["MaxDD_BRL"])
                            if sc_curr > sc_best and mc["PF"] >= best_m["PF"] * 0.98:
                                best_m, best_tr, best_st = mc, tr_c, st_c
                                best_cfg = f"{'PA_Sub' if rep_pa else e_ov} | {b_m}({int(bf)}) | {t_m}"

            if mode_idx == 0:
                m_grid, tr_grid, st_grid, cfg_grid = best_m, best_tr, best_st, best_cfg
                aligned_grids_all.extend(tr_grid)
                if est_id not in (13, 14, 16):
                    m_opA, tr_opA, st_opA, cfg_opA = best_m, best_tr, best_st, best_cfg
                    aligned_opA_all.extend(tr_opA)
                    entries_opA[est_id] = st_opA["entries"]
            else:
                m_opA, tr_opA, st_opA, cfg_opA = best_m, best_tr, best_st, best_cfg
                aligned_opA_all.extend(tr_opA)
                entries_opA[est_id] = st_opA["entries"]

        rows.append({
            "ID": f"EST-{est_id:02d}",
            "Leg_Tr": m_leg["Trades"],
            "Leg_BRL": m_leg["NetBRL"],
            "Leg_DD": m_leg["MaxDD_BRL"],
            "Leg_RetDD": m_leg["Ret_DD"],
            "Alin_Grid_BRL": m_grid["NetBRL"],
            "Alin_Grid_DD": m_grid["MaxDD_BRL"],
            "Alin_Grid_RetDD": m_grid["Ret_DD"],
            "OpA_Tr": m_opA["Trades"],
            "OpA_BRL": m_opA["NetBRL"],
            "OpA_DD": m_opA["MaxDD_BRL"],
            "OpA_PF": m_opA["PF"],
            "OpA_RetDD": m_opA["Ret_DD"],
            "Saves": st_opA["wall_saves"],
            "Parciais": st_opA["partial_hits"],
            "Config_Final_OpA": cfg_opA,
        })

    df_rows = pd.DataFrame(rows)
    out_dir = os.path.join(PROJECT_ROOT, "data", "reports", "win_aligned_wdo_matrix")
    os.makedirs(out_dir, exist_ok=True)
    df_rows.to_csv(os.path.join(out_dir, "win_16_aligned_synthesis.csv"), index=False)

    print("\nCOMPARATIVO INDIVIDUAL (EST-01 A EST-16): LEGACY vs. FÍSICA ALINHADA (GRIDS) vs. FÍSICA ALINHADA + OPÇÃO A:")
    print(df_rows.to_string(index=False))

    p1 = calc_slot_summary(sorted(legacy_all, key=lambda x: x["date"]), {}, "1. LEGACY WIN (Antigo: Deadlock c50 + Trava 85p + BE 150/20)")
    p2 = calc_slot_summary(sorted(aligned_grids_all, key=lambda x: x["date"]), {}, "2. FÍSICA ALINHADA (4 Blocos + BE 177k + 3 Pilares c/ Grids)")
    p3 = calc_slot_summary(sorted(aligned_opA_all, key=lambda x: x["date"]), {}, "3. 🏆 FÍSICA ALINHADA + OPÇÃO A (Subst. 13,14,16 + EST-15 260p)")

    df_port = pd.DataFrame([p1, p2, p3])
    df_port.to_csv(os.path.join(out_dir, "portfolio_aligned_synthesis.csv"), index=False)

    col_bar, col_px, max_sim_px = count_collisions(entries_opA)

    print("\n" + "=" * 115)
    print("  RESUMO CONSOLIDADO DO PORTFÓLIO WIN$N (16 ROBÔS, 122 PREGÕES):")
    print("=" * 115)
    print(df_port[["Config", "Trades", "WinRate", "PF", "NetPts", "NetBRL", "MaxDD_BRL", "Ret_DD", "Sharpe"]].to_string(index=False))
    print("-" * 115)
    print(f"  [Auditoria de Descorrelação] Máx robôs no exato mesmo preço/segundo: {max_sim_px} (antes: 7) | Colisões exatas: {col_px}")
    print(f"  Concluído em {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    run_all()
