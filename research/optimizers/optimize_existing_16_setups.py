"""
AUDITORIA E OTIMIZAÇÃO INDIVIDUAL DOS 16 SETUPS EXISTENTES DO MT5 (EST-01 A EST-16)
===================================================================================
Replica fielmente a lógica exata de cada uma das 16 estratégias (`EST-01` a `EST-16`)
de `mt5/Include/Jumba_GEX_NWE_Core.mqh` sobre os pregões de WIN$N + WDO$N (via `mt5_loader`)
e compara, ESTRATÉGIA POR ESTRATÉGIA (Antes vs. Depois):

  - BASELINE ATUAL (como está hoje no MT5: BE no Zero + Alvo Fixo + Entrada Atual)
  - OTIMIZADO (testando em cada um dos 16 setups):
      1. BE_Mode:
         * "BE_ZERO" (atual: avg_price ± be_lock)
         * "BE_WALL_SHIELD" (reduz SL para trás da Wall de entrada: def_wall ∓ buf)
         * "BE_WALL_2STAGE" (Estágio 1 atrás da Wall: def_wall ∓ buf; Estágio 2 no lucro/MidWall após avançar)
      2. TP_Mode:
         * "TP_CURRENT" (alvo fixo atual de cada EST)
         * "TP_MIDWALL" (100% na próxima MidWall real - front_run)
         * "TP_MAIN_WALL" (100% na próxima Main Wall real - front_run)
         * "TP_PARTIAL_WALLS" (50% na MidWall + 50% na Main Wall com stop protegido atrás da Wall)
      3. Entry_Override (usando Máxima/Mínima da Barra Anterior b1):
         * "CURRENT" (mantém o gatilho original da EST)
         * "STOP_B1_EXT" (converte entradas Mkt para Buy Stop em b1.high+5 / Sell Stop em b1.low-5)
         * "LIMIT_B1_EXT" (usa b1.low+5 / b1.high-5 como referência de Limit)
         * "LIMIT_B1_MID" (usa 50% da barra b1 como Limit de desconto)
"""
import os
import sys
import time
import sqlite3
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_gex_nwe_setups import load_aligned_data, compute_nwe_series, DB_PATH
from research.mt5_loader import load_win_and_wdo_aligned as _mt5_load_win_and_wdo_aligned

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "existing_16_setups_opt")
os.makedirs(OUT_DIR, exist_ok=True)

EST_NAMES = {
    1: "EST-01 Scalper Hibrido NY",
    2: "EST-02 Scalper Hibrido DiaTodo",
    3: "EST-03 Arbitragem Cambial WDO",
    4: "EST-04 Pullback Reteste Wall",
    5: "EST-05 Pullback Cluster NWE30+50",
    6: "EST-06 Pullback Limit Slope",
    7: "EST-07 Breakout Momentum NY",
    8: "EST-08 Breakout Rapido Core",
    9: "EST-09 Breakout Stop/Lim Wall NY",
    10: "EST-10 Breakout Stop/Lim MainWall",
    11: "EST-11 Grid Pullback 1+2L",
    12: "EST-12 Piramidacao Lucro 1+1L",
    13: "EST-13 SmartGrid MainWall 1+2L",
    14: "EST-14 Grid Institucional 1+2+3L",
    15: "EST-15 Posicional EOD Breakout",
    16: "EST-16 Posicional EOD StopWall",
}


def round5(val: float) -> float:
    return np.round(val / 5.0) * 5.0


def window_ok(t_min: int, wm: str) -> bool:
    if wm == "FULL_09_17":
        return 540 <= t_min < 1020
    if wm == "CORE_09_1615":
        return 540 <= t_min <= 975
    if wm == "NY_1000_1630":
        return 600 <= t_min <= 990
    if wm == "NO_LUNCH":
        return (545 <= t_min <= 720) or (810 <= t_min <= 980)
    return True


def load_win_and_wdo_aligned(use_sqlite: bool = False):
    """Por padrão carrega as barras M5 do terminal MT5 e o jumba_gex_win_history.csv."""
    if not use_sqlite:
        return _mt5_load_win_and_wdo_aligned()

    df_bars, gex_by_date = load_aligned_data(use_sqlite=True)
    conn = sqlite3.connect(DB_PATH)
    df_wdo = pd.read_sql_query(
        """
        SELECT timestamp_utc, close AS wdo_close
        FROM market_bars
        WHERE symbol = 'WDO$N' AND timeframe = 'M5' AND timestamp_utc >= '2026-04-15'
        ORDER BY timestamp_utc ASC
        """,
        conn,
    )
    conn.close()

    df_wdo["wdo_ret3"] = df_wdo["wdo_close"].diff(3).fillna(0.0)
    rm = df_wdo["wdo_close"].rolling(20).mean()
    rs = df_wdo["wdo_close"].rolling(20).std().replace(0, 1.0)
    df_wdo["wdo_z"] = ((df_wdo["wdo_close"] - rm) / rs).fillna(0.0)

    df_merged = pd.merge(df_bars, df_wdo[["timestamp_utc", "wdo_ret3", "wdo_z"]], on="timestamp_utc", how="left")
    df_merged["wdo_ret3"] = df_merged["wdo_ret3"].ffill().fillna(0.0)
    df_merged["wdo_z"] = df_merged["wdo_z"].ffill().fillna(0.0)
    return df_merged, gex_by_date


def find_structural_targets(entry_px: float, side: int, walls: np.ndarray, all_lvls: np.ndarray, front_run: float = 20.0):
    """[ALINHADO MT5] Cópia exata de FindStructuralTargets() do Jumba_GEX_NWE_Core.mqh:
    mid = 1º nível (Wall ou MidWall) a >=135 pts; main = 1ª WALL a >=300 pts E além de mid+80 (pula para a próxima Wall)."""
    walls = np.sort(np.asarray(walls, float))
    all_lvls = np.sort(np.asarray(all_lvls, float))
    if side == 1:
        ia = np.where(all_lvls >= entry_px + 135.0)[0]
        mid_i = int(ia[0]) if len(ia) else -1
        raw_mid = float(all_lvls[mid_i]) if mid_i >= 0 else entry_px + 460.0
        cw = walls[(walls >= entry_px + 300.0) & (walls > raw_mid + 80.0)]
        if len(cw):
            raw_main = float(cw[0])
        elif mid_i >= 0 and mid_i + 1 < len(all_lvls) and all_lvls[mid_i + 1] > raw_mid + 80.0:
            raw_main = float(all_lvls[mid_i + 1])
        else:
            raw_main = raw_mid + 480.0
        return round5(raw_mid - front_run), round5(raw_main - front_run), raw_mid, raw_main
    ia = np.where(all_lvls <= entry_px - 135.0)[0]
    mid_i = int(ia[-1]) if len(ia) else -1
    raw_mid = float(all_lvls[mid_i]) if mid_i >= 0 else entry_px - 460.0
    cw = walls[(walls <= entry_px - 300.0) & (walls < raw_mid - 80.0)]
    if len(cw):
        raw_main = float(cw[-1])
    elif mid_i > 0 and all_lvls[mid_i - 1] < raw_mid - 80.0:
        raw_main = float(all_lvls[mid_i - 1])
    else:
        raw_main = raw_mid - 480.0
    return round5(raw_mid + front_run), round5(raw_main + front_run), raw_mid, raw_main


def simulate_single_est_slot(
    est_id: int,
    df: pd.DataFrame,
    gex_by_date: dict,
    n50_c: np.ndarray, n50_u: np.ndarray, n50_l: np.ndarray, n50_s: np.ndarray,
    n30_c: np.ndarray, n30_u: np.ndarray, n30_l: np.ndarray, n30_s: np.ndarray,
    rsi7s: np.ndarray,
    # Modos de Otimização
    entry_override: str = "CURRENT",   # "CURRENT", "STOP_B1_EXT", "LIMIT_B1_EXT", "LIMIT_B1_MID"
    be_mode: str = "BE_ZERO",          # "BE_ZERO", "BE_WALL_SHIELD", "BE_WALL_2STAGE"
    wall_shield_buf: float = 20.0,     # Distância atrás da Wall (ex: 15..30 pts)
    tp_mode: str = "TP_CURRENT",       # "TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"
    front_run_pts: float = 20.0,
    cost_pts: float = 10.0,
):
    """
    Executa a simulação fiel do slot `est_id` (1..16) de `Jumba_GEX_NWE_Core.mqh`.
    """
    dates = df["session_date"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values
    wdo_ret3 = df["wdo_ret3"].values
    wdo_z = df["wdo_z"].values

    trades = []
    wall_saves = 0
    partial_hits = 0

    n = len(df)
    idx = 2
    last_trade_date = ""
    last_entry_bar_idx = -1

    while idx < n - 1:
        # No MT5, `OnNewM5Bar` roda na abertura da barra `idx`, olhando a barra fechada `b1 = idx - 1`
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

        bw50 = m_n50_u_1 - m_n50_l_1
        bw30 = m_n30_u_1 - m_n30_l_1
        body1 = b1_c - b1_o
        rng1 = max(1.0, b1_h - b1_l)

        # FindNearestLevel
        dists_all_l = np.abs(m_levels_all - b1_l)
        i_all_l = int(np.argmin(dists_all_l))
        d_l, lvl_s = float(dists_all_l[i_all_l]), float(m_levels_all[i_all_l])

        dists_all_h = np.abs(m_levels_all - b1_h)
        i_all_h = int(np.argmin(dists_all_h))
        d_h, lvl_r = float(dists_all_h[i_all_h]), float(m_levels_all[i_all_h])

        if len(m_levels_walls) > 0:
            dw_l_arr = np.abs(m_levels_walls - b1_l)
            iw_l = int(np.argmin(dw_l_arr))
            dw_l_main, w_s_main = float(dw_l_arr[iw_l]), float(m_levels_walls[iw_l])

            dw_h_arr = np.abs(m_levels_walls - b1_h)
            iw_h = int(np.argmin(dw_h_arr))
            dw_h_main, w_r_main = float(dw_h_arr[iw_h]), float(m_levels_walls[iw_h])
        else:
            dw_l_main, w_s_main = 999999.0, 0.0
            dw_h_main, w_r_main = 999999.0, 0.0

        # ======================================================================
        # AVALIAÇÃO EXATA DO SINAL DA ESTRATÉGIA `est_id` (1..16)
        # ======================================================================
        action_kind = None  # "MKT", "PEND_LIMIT", "PEND_STOP", "GRID"
        sig_dir = 0
        trig_px = 0.0
        def_wall = 0.0
        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
        step2_d, step3_d, lot1, lot2, lot3, tp_avg_p, max_sl_p = 0.0, 0.0, 1, 0, 0, 0.0, 0.0

        # --- EST-01 & EST-02 ---
        if est_id in (1, 2):
            wm_rej = "NY_1000_1630" if est_id == 1 else "FULL_09_17"
            wm_lim = "NY_1000_1630" if est_id == 1 else "CORE_09_1615"
            l_off = 0.0 if est_id == 1 else 10.0
            c_buy = (b1_c > b1_o) and ((b1_c - b1_l) >= 0.5 * rng1)
            c_sell = (b1_c < b1_o) and ((b1_h - b1_c) >= 0.5 * rng1)

            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, wm_rej):
                if d_l <= 60.0 and -25.0 <= (b1_c - lvl_s) <= 75.0 and b1_c <= (m_n50_l_1 + bw50 * 0.22) and m_rsi7_1 <= 35.0 and c_buy and m_n50_s_1 >= -12.0:
                    action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, lvl_s
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                elif d_h <= 60.0 and -25.0 <= (lvl_r - b1_c) <= 75.0 and b1_c >= (m_n50_u_1 - bw50 * 0.22) and m_rsi7_1 >= 65.0 and c_sell and m_n50_s_1 <= 12.0:
                    action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, lvl_r
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                elif est_id == 1:
                    for lvl in m_levels_all:
                        if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 85.0 and body1 >= 55.0 and m_n50_s_1 >= 4.5 and b1_c < (m_n50_u_1 - bw50 * 0.15):
                            action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                            tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                            break
                        if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 85.0 and (-body1) >= 55.0 and m_n50_s_1 <= -4.5 and b1_c > (m_n50_l_1 + bw50 * 0.15):
                            action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                            tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                            break

            if sig_dir == 0 and window_ok(new_tmin, wm_lim):
                if m_n50_s_1 >= 6.0 and b1_c <= (m_n50_c_1 + bw50 * 0.18) and d_l <= 55.0 and b1_c > (lvl_s + l_off):
                    action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, lvl_s + l_off, lvl_s
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15
                elif m_n50_s_1 <= -6.0 and b1_c >= (m_n50_c_1 - bw50 * 0.18) and d_h <= 55.0 and b1_c < (lvl_r - l_off):
                    action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, lvl_r - l_off, lvl_r
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15

        # --- EST-03 ---
        elif est_id == 3:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 85.0 and body1 >= 50.0 and m_n50_s_1 >= 4.0 and b1_c < (m_n50_u_1 - bw50 * 0.15) and (m_wdo_ret3_1 <= 2.0 or m_wdo_z_1 <= 0.0):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                        break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 85.0 and (-body1) >= 50.0 and m_n50_s_1 <= -4.0 and b1_c > (m_n50_l_1 + bw50 * 0.15) and (m_wdo_ret3_1 >= -2.0 or m_wdo_z_1 >= 0.0):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                        break
            if sig_dir == 0 and window_ok(new_tmin, "FULL_09_17"):
                if m_n50_s_1 >= 8.0 and (m_wdo_ret3_1 <= 2.0 or m_wdo_z_1 <= 0.2) and d_l <= 55.0 and b1_c > lvl_s and b1_c <= (m_n50_c_1 + bw50 * 0.20):
                    action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, lvl_s, lvl_s
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                elif m_n50_s_1 <= -8.0 and (m_wdo_ret3_1 >= -2.0 or m_wdo_z_1 >= -0.2) and d_h <= 55.0 and b1_c < lvl_r and b1_c >= (m_n50_c_1 - bw50 * 0.20):
                    action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, lvl_r, lvl_r
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16

        # --- EST-04 ---
        elif est_id == 4:
            if window_ok(new_tmin, "FULL_09_17"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 10.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 95.0 and body1 >= 45.0 and m_n50_s_1 >= 6.0:
                        if (m_gamma_flip <= 0.0 or b1_c >= m_gamma_flip) and b1_c < (m_n50_u_1 - bw50 * 0.15):
                            action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, float(lvl), float(lvl)
                            tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                            break
                    if b1_o >= lvl - 10.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 95.0 and (-body1) >= 45.0 and m_n50_s_1 <= -6.0:
                        if (m_gamma_flip <= 0.0 or b1_c <= m_gamma_flip) and b1_c > (m_n50_l_1 + bw50 * 0.15):
                            action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, float(lvl), float(lvl)
                            tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                            break

        # --- EST-05 ---
        elif est_id == 5:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 90.0 and body1 >= 45.0 and m_n30_s_1 >= 5.0 and m_n50_s_1 >= 4.0 and b1_c < (m_n30_u_1 - bw30 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                        break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 90.0 and (-body1) >= 45.0 and m_n30_s_1 <= -5.0 and m_n50_s_1 <= -4.0 and b1_c > (m_n30_l_1 + bw30 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                        break
            if sig_dir == 0 and window_ok(new_tmin, "CORE_09_1615"):
                if m_n30_s_1 >= 6.0 and m_n50_s_1 >= 6.0 and b1_c <= (m_n30_c_1 + bw30 * 0.20) and d_l <= 50.0 and b1_c > lvl_s:
                    action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, lvl_s, lvl_s
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                elif m_n30_s_1 <= -6.0 and m_n50_s_1 <= -6.0 and b1_c >= (m_n30_c_1 - bw30 * 0.20) and d_h <= 50.0 and b1_c < lvl_r:
                    action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, lvl_r, lvl_r
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 500.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16

        # --- EST-06 ---
        elif est_id == 6:
            if window_ok(new_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 10.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 95.0 and body1 >= 42.0 and m_n50_s_1 >= 5.5 and b1_c < (m_n50_u_1 - bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, float(lvl), float(lvl)
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                        break
                    if b1_o >= lvl - 10.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 95.0 and (-body1) >= 42.0 and m_n50_s_1 <= -5.5 and b1_c > (m_n50_l_1 + bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, float(lvl), float(lvl)
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 16
                        break
                if sig_dir == 0:
                    if m_n50_s_1 >= 8.0 and b1_c <= (m_n50_c_1 + bw50 * 0.20) and d_l <= 55.0 and b1_c > lvl_s:
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, lvl_s, lvl_s
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15
                    elif m_n50_s_1 <= -8.0 and b1_c >= (m_n50_c_1 - bw50 * 0.20) and d_h <= 55.0 and b1_c < lvl_r:
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, lvl_r, lvl_r
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 15

        # --- EST-07 & EST-08 ---
        elif est_id in (7, 8):
            wm_bo = "NY_1000_1630" if est_id == 7 else "CORE_09_1615"
            min_bd = 65.0 if est_id == 7 else 50.0
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, wm_bo):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 15.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 90.0 and body1 >= min_bd and m_n50_s_1 >= 4.0 and b1_c < (m_n50_u_1 - bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        break
                    if b1_o >= lvl - 15.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 90.0 and (-body1) >= min_bd and m_n50_s_1 <= -4.0 and b1_c > (m_n50_l_1 + bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        break
                if sig_dir != 0:
                    if est_id == 7:
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 650.0, 260.0, 160.0, 20.0, 350.0, 120.0, 16
                    else:
                        tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 400.0, 220.0, 140.0, 20.0, 250.0, 100.0, 16

        # --- EST-09 ---
        elif est_id == 9:
            if window_ok(new_tmin, "NY_1000_1630"):
                if m_n30_s_1 >= 5.0 and b1_c > b1_o and body1 >= 35.0 and b1_c < (m_n30_u_1 - bw30 * 0.20):
                    for lvl in m_levels_all:
                        if lvl >= b1_c - 5.0 and (lvl - b1_c) <= 55.0:
                            action_kind, sig_dir, trig_px, def_wall = "PEND_STOP", 1, max(float(lvl) + 10.0, b1_h + 5.0), float(lvl)
                            break
                if sig_dir == 0 and m_n30_s_1 <= -5.0 and b1_c < b1_o and (-body1) >= 35.0 and b1_c > (m_n30_l_1 + bw30 * 0.20):
                    for lvl in reversed(m_levels_all):
                        if lvl <= b1_c + 5.0 and (b1_c - lvl) <= 55.0:
                            action_kind, sig_dir, trig_px, def_wall = "PEND_STOP", -1, min(float(lvl) - 10.0, b1_l - 5.0), float(lvl)
                            break
                if sig_dir == 0:
                    if m_n50_s_1 >= 6.5 and d_l <= 55.0 and b1_c > lvl_s and b1_c <= (m_n50_c_1 + bw50 * 0.20):
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, lvl_s, lvl_s
                    elif m_n50_s_1 <= -6.5 and d_h <= 55.0 and b1_c < lvl_r and b1_c >= (m_n50_c_1 - bw50 * 0.20):
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, lvl_r, lvl_r
                if sig_dir != 0:
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16

        # --- EST-10 ---
        elif est_id == 10:
            if window_ok(new_tmin, "CORE_09_1615") and len(m_levels_walls) > 0:
                if m_n30_s_1 >= 4.5 and b1_c > b1_o and body1 >= 35.0 and b1_c < (m_n30_u_1 - bw30 * 0.18):
                    for w in m_levels_walls:
                        if w >= b1_c - 5.0 and (w - b1_c) <= 55.0:
                            action_kind, sig_dir, trig_px, def_wall = "PEND_STOP", 1, max(float(w) + 10.0, b1_h + 5.0), float(w)
                            break
                if sig_dir == 0 and m_n30_s_1 <= -4.5 and b1_c < b1_o and (-body1) >= 35.0 and b1_c > (m_n30_l_1 + bw30 * 0.18):
                    for w in reversed(m_levels_walls):
                        if w <= b1_c + 5.0 and (b1_c - w) <= 55.0:
                            action_kind, sig_dir, trig_px, def_wall = "PEND_STOP", -1, min(float(w) - 10.0, b1_l - 5.0), float(w)
                            break
                if sig_dir == 0:
                    if m_n50_s_1 >= 5.5 and dw_l_main <= 60.0 and b1_c > w_s_main and b1_c <= (m_n50_c_1 + bw50 * 0.22):
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", 1, w_s_main, w_s_main
                    elif m_n50_s_1 <= -5.5 and dw_h_main <= 60.0 and b1_c < w_r_main and b1_c >= (m_n50_c_1 - bw50 * 0.22):
                        action_kind, sig_dir, trig_px, def_wall = "PEND_LIMIT", -1, w_r_main, w_r_main
                if sig_dir != 0:
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 600.0, 250.0, 155.0, 20.0, 320.0, 115.0, 16

        # --- EST-11 (Grid 1+2L) ---
        elif est_id == 11:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NO_LUNCH"):
                if m_n50_s_1 >= 3.0 and b1_c < (m_n50_u_1 - bw50 * 0.15) and d_l <= 55.0 and -10.0 <= (b1_c - lvl_s) <= 85.0 and b1_c > b1_o:
                    action_kind, sig_dir, trig_px, def_wall = "GRID", 1, new_bar_open, lvl_s
                elif m_n50_s_1 <= -3.0 and b1_c > (m_n50_l_1 + bw50 * 0.15) and d_h <= 55.0 and -10.0 <= (lvl_r - b1_c) <= 85.0 and b1_c < b1_o:
                    action_kind, sig_dir, trig_px, def_wall = "GRID", -1, new_bar_open, lvl_r
                if sig_dir != 0:
                    step2_d, step3_d, lot1, lot2, lot3, tp_avg_p, max_sl_p, be_trig, be_lock, max_hold = 450.0, 900.0, 1, 2, 0, 280.0, 650.0, 150.0, 25.0, 24

        # --- EST-12 (Piramidação 1+1L) ---
        elif est_id == 12:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NY_1000_1630"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 15.0 and b1_c > lvl + 12.0 and (b1_c - lvl) <= 90.0 and body1 >= 55.0 and m_n50_s_1 >= 4.0 and b1_c < (m_n50_u_1 - bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        break
                    if b1_o >= lvl - 15.0 and b1_c < lvl - 12.0 and (lvl - b1_c) <= 90.0 and (-body1) >= 55.0 and m_n50_s_1 <= -4.0 and b1_c > (m_n50_l_1 + bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        break
                if sig_dir != 0:
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 550.0, 240.0, 150.0, 20.0, 300.0, 110.0, 18

        # --- EST-13 (Smart Grid 1+2L Main Walls) ---
        elif est_id == 13:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "FULL_09_17") and len(m_levels_walls) > 0:
                if m_n50_s_1 >= 2.0 and b1_c < (m_n50_u_1 - bw50 * 0.12) and dw_l_main <= 65.0 and -15.0 <= (b1_c - w_s_main) <= 90.0 and b1_c > b1_o:
                    action_kind, sig_dir, trig_px, def_wall = "GRID", 1, new_bar_open, w_s_main
                elif m_n50_s_1 <= -2.0 and b1_c > (m_n50_l_1 + bw50 * 0.12) and dw_h_main <= 65.0 and -15.0 <= (w_r_main - b1_c) <= 90.0 and b1_c < b1_o:
                    action_kind, sig_dir, trig_px, def_wall = "GRID", -1, new_bar_open, w_r_main
                if sig_dir != 0:
                    step2_d, step3_d, lot1, lot2, lot3, tp_avg_p, max_sl_p, be_trig, be_lock, max_hold = 507.0, 1014.0, 1, 2, 0, 280.0, 700.0, 150.0, 25.0, 26

        # --- EST-14 (Grid Institucional 1+2+3L Main Walls) ---
        elif est_id == 14:
            if last_entry_bar_idx != b1_idx and 545 <= b1_tmin <= 930 and len(m_levels_walls) > 0:
                if m_n50_s_1 >= 1.5 and b1_c < (m_n50_u_1 - bw50 * 0.15) and dw_l_main <= 65.0 and -20.0 <= (b1_c - w_s_main) <= 85.0 and b1_c > b1_o:
                    action_kind, sig_dir, trig_px, def_wall = "GRID", 1, new_bar_open, w_s_main
                elif m_n50_s_1 <= -1.5 and b1_c > (m_n50_l_1 + bw50 * 0.15) and dw_h_main <= 65.0 and -20.0 <= (w_r_main - b1_c) <= 85.0 and b1_c < b1_o:
                    action_kind, sig_dir, trig_px, def_wall = "GRID", -1, new_bar_open, w_r_main
                if sig_dir != 0:
                    step2_d, step3_d, lot1, lot2, lot3, tp_avg_p, max_sl_p, be_trig, be_lock, max_hold = 507.0, 1014.0, 1, 2, 3, 280.0, 650.0, 150.0, 25.0, 28

        # --- EST-15 (Posicional EOD Breakout) ---
        elif est_id == 15:
            if last_trade_date != b1_date and 545 <= b1_tmin <= 780:
                for lvl in m_levels_all:
                    if b1_o <= lvl + 12.0 and b1_c > lvl + 15.0 and (b1_c - lvl) <= 95.0 and body1 >= 50.0 and m_n50_s_1 >= 5.0 and b1_c < (m_n50_u_1 - bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", 1, new_bar_open, float(lvl)
                        break
                    if b1_o >= lvl - 12.0 and b1_c < lvl - 15.0 and (lvl - b1_c) <= 95.0 and (-body1) >= 50.0 and m_n50_s_1 <= -5.0 and b1_c > (m_n50_l_1 + bw50 * 0.15):
                        action_kind, sig_dir, trig_px, def_wall = "MKT", -1, new_bar_open, float(lvl)
                        break
                if sig_dir != 0:
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 1500.0, 450.0, 300.0, 25.0, 600.0, 250.0, 120

        # --- EST-16 (Posicional EOD Stop Wall) ---
        elif est_id == 16:
            if last_trade_date != b1_date and 550 <= new_tmin <= 840:
                if m_n30_s_1 >= 5.0 and b1_c > b1_o and body1 >= 40.0 and b1_c < (m_n30_u_1 - bw30 * 0.20):
                    for lvl in m_levels_all:
                        if lvl >= b1_c - 5.0 and (lvl - b1_c) <= 55.0:
                            action_kind, sig_dir, trig_px, def_wall = "PEND_STOP", 1, max(float(lvl) + 10.0, b1_h + 5.0), float(lvl)
                            break
                if sig_dir == 0 and m_n30_s_1 <= -5.0 and b1_c < b1_o and (-body1) >= 40.0 and b1_c > (m_n30_l_1 + bw30 * 0.20):
                    for lvl in reversed(m_levels_all):
                        if lvl <= b1_c + 5.0 and (b1_c - lvl) <= 55.0:
                            action_kind, sig_dir, trig_px, def_wall = "PEND_STOP", -1, min(float(lvl) - 10.0, b1_l - 5.0), float(lvl)
                            break
                if sig_dir != 0:
                    tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold = 1500.0, 400.0, 260.0, 25.0, 500.0, 200.0, 120

        if sig_dir == 0:
            idx += 1
            continue

        # ======================================================================
        # PILAR 3: OVERRIDE DE ENTRADA PELA BARRA ANTERIOR (SE ATIVADO)
        # ======================================================================
        if entry_override != "CURRENT" and action_kind in ("MKT", "PEND_LIMIT"):
            if entry_override == "STOP_B1_EXT":
                action_kind = "PEND_STOP"
                trig_px = round5(b1_h + 5.0) if sig_dir == 1 else round5(b1_l - 5.0)
            elif entry_override == "LIMIT_B1_EXT":
                action_kind = "PEND_LIMIT"
                trig_px = round5(b1_l + 5.0) if sig_dir == 1 else round5(b1_h - 5.0)
            elif entry_override == "LIMIT_B1_MID":
                action_kind = "PEND_LIMIT"
                trig_px = round5(0.5 * (b1_h + b1_l))

        # Verifica preenchimento na barra `idx` (fiel ao ArmPendingOrder do MT5)
        o0, h0, l0, c0 = opens[idx], highs[idx], lows[idx], closes[idx]
        entered = False
        entry_px = 0.0
        opened_intrabar = False

        if action_kind in ("MKT", "GRID"):
            entered = True
            entry_px = round5(new_bar_open)
            opened_intrabar = False
            last_entry_bar_idx = b1_idx
            if est_id == 15:
                last_trade_date = b1_date
        elif action_kind == "PEND_LIMIT":
            p5 = round5(trig_px)
            # Regra exata do ArmPendingOrder no MT5 (linhas 2000-2004):
            if sig_dir == 1 and new_bar_open >= p5 and l0 <= p5:
                entered = True
                entry_px = p5
                opened_intrabar = True
                last_entry_bar_idx = idx
            elif sig_dir == -1 and new_bar_open <= p5 and h0 >= p5:
                entered = True
                entry_px = p5
                opened_intrabar = True
                last_entry_bar_idx = idx
        elif action_kind == "PEND_STOP":
            p5 = round5(trig_px)
            if sig_dir == 1 and new_bar_open <= p5 and h0 >= p5:
                entered = True
                entry_px = p5
                opened_intrabar = True
                last_entry_bar_idx = idx
                if est_id == 16:
                    last_trade_date = today_str
            elif sig_dir == -1 and new_bar_open >= p5 and l0 <= p5:
                entered = True
                entry_px = p5
                opened_intrabar = True
                last_entry_bar_idx = idx
                if est_id == 16:
                    last_trade_date = today_str

        if not entered:
            idx += 1
            continue

        # ======================================================================
        # SIMULAÇÃO DA POSIÇÃO ABERTA (SINGLE, PIRAMIDAÇÃO OU GRID)
        # ======================================================================
        tp_mid_px, tp_main_px, raw_mid_lvl, raw_main_lvl = find_structural_targets(
            entry_px, sig_dir, m_levels_walls, m_levels_all, front_run=front_run_pts
        )

        if action_kind == "GRID":
            # Estratégias de Grid (EST-11, EST-13, EST-14)
            p1_entry = entry_px
            avg_price = entry_px
            lots = lot1
            leg_stage = 1
            be_active = False
            stage2_active = False
            max_fav_pts = 0.0
            bars_held = 0
            partial_done = False
            partial_pts_locked = 0.0

            base_tp_dist = tp_avg_p
            if tp_mode == "TP_MIDWALL":
                base_tp_dist = max(180.0, abs(tp_mid_px - avg_price))
            elif tp_mode == "TP_MAIN_WALL":
                base_tp_dist = max(280.0, abs(tp_main_px - avg_price))

            curr_tp = round5(avg_price + base_tp_dist) if sig_dir == 1 else round5(avg_price - base_tp_dist)
            curr_sl = round5(avg_price - max_sl_p) if sig_dir == 1 else round5(avg_price + max_sl_p)
            sl0 = curr_sl
            tp2_px = curr_tp

            j = idx
            exit_px = avg_price
            while j < n and dates[j] == today_str:
                hj, lj, cj = highs[j], lows[j], closes[j]
                if t_mins[j] >= 1035:
                    exit_px = opens[j]
                    break

                # Adição de Lotes de Grid (Perna 2 e Perna 3) ANTES do Hard SL
                if leg_stage == 1 and lot2 > 0:
                    p2_lvl = (p1_entry - step2_d) if sig_dir == 1 else (p1_entry + step2_d)
                    if (sig_dir == 1 and lj <= p2_lvl) or (sig_dir == -1 and hj >= p2_lvl):
                        new_lots = lot1 + lot2
                        avg_price = round5((p1_entry * lot1 + p2_lvl * lot2) / float(new_lots))
                        lots = new_lots
                        leg_stage = 2
                        be_active = False
                        max_fav_pts = 0.0
                        curr_tp = round5(avg_price + tp_avg_p) if sig_dir == 1 else round5(avg_price - tp_avg_p)
                        curr_sl = round5(avg_price - max_sl_p) if sig_dir == 1 else round5(avg_price + max_sl_p)
                        tp2_px = curr_tp

                if leg_stage == 2 and lot3 > 0:
                    p3_lvl = (p1_entry - step3_d) if sig_dir == 1 else (p1_entry + step3_d)
                    if (sig_dir == 1 and lj <= p3_lvl) or (sig_dir == -1 and hj >= p3_lvl):
                        new_lots = lots + lot3
                        avg_price = round5((avg_price * lots + p3_lvl * lot3) / float(new_lots))
                        lots = new_lots
                        leg_stage = 3
                        be_active = False
                        max_fav_pts = 0.0
                        curr_tp = round5(avg_price + tp_avg_p) if sig_dir == 1 else round5(avg_price - tp_avg_p)
                        curr_sl = round5(avg_price - max_sl_p) if sig_dir == 1 else round5(avg_price + max_sl_p)
                        tp2_px = curr_tp

                # Verifica SL / TP na barra j
                if sig_dir == 1:
                    if lj <= curr_sl:
                        exit_px = min(curr_sl, opens[j]) if j > idx else curr_sl
                        break
                    if hj >= curr_tp:
                        exit_px = curr_tp
                        break
                    fav = hj - avg_price
                    if fav > max_fav_pts:
                        max_fav_pts = fav
                    if be_trig > 0 and not be_active and max_fav_pts >= be_trig:
                        be_active = True
                        if be_mode == "BE_ZERO" or leg_stage > 1:
                            cand_sl = round5(avg_price + be_lock)
                        else:
                            cand_sl = round5(min(def_wall - wall_shield_buf, avg_price - 15.0))
                        curr_sl = max(curr_sl, cand_sl)
                    if be_mode == "BE_WALL_2STAGE" and leg_stage == 1 and max_fav_pts >= 220.0:
                        curr_sl = max(curr_sl, round5(avg_price + be_lock))
                else:
                    if hj >= curr_sl:
                        exit_px = max(curr_sl, opens[j]) if j > idx else curr_sl
                        break
                    if lj <= curr_tp:
                        exit_px = curr_tp
                        break
                    fav = avg_price - lj
                    if fav > max_fav_pts:
                        max_fav_pts = fav
                    if be_trig > 0 and not be_active and max_fav_pts >= be_trig:
                        be_active = True
                        if be_mode == "BE_ZERO" or leg_stage > 1:
                            cand_sl = round5(avg_price - be_lock)
                        else:
                            cand_sl = round5(max(def_wall + wall_shield_buf, avg_price + 15.0))
                        curr_sl = min(curr_sl, cand_sl)
                    if be_mode == "BE_WALL_2STAGE" and leg_stage == 1 and max_fav_pts >= 220.0:
                        curr_sl = min(curr_sl, round5(avg_price - be_lock))

                bars_held += 1
                if bars_held >= max_hold:
                    exit_px = cj
                    break
                j += 1
            else:
                exit_px = closes[min(j, n - 1)]

            net_pts_per_lot = (exit_px - avg_price) * sig_dir - cost_pts
            trades.append({
                "date": today_str, "i_sig": int(idx), "j_exit": int(min(j, n - 1)), "exit_px": float(exit_px), "avg_px": float(avg_price), "tp_px": float(tp2_px), "sl_last": float(curr_sl), "sl0": float(sl0),
                "est_id": est_id,
                "side": int(sig_dir),
                "pnl_pts": net_pts_per_lot * lots,
                "contracts": lots,
                "pnl_brl": net_pts_per_lot * lots * 0.20,
            })
            idx = max(idx + 1, j + 1)

        else:
            # Estratégias Single / Piramidação / EOD (EST-01..10, 12, 15, 16)
            p1_entry = entry_px
            avg_price = entry_px
            lots = 1
            leg_stage = 1
            be_active = False
            stage2_active = False
            max_fav_pts = 0.0
            bars_held = 0
            partial_done = False
            partial_exit_px = 0.0
            touched_zero_after_shield = False

            if tp_mode == "TP_CURRENT":
                tp1_px = round5(avg_price + tp_pts) if sig_dir == 1 else round5(avg_price - tp_pts)
                tp2_px = tp1_px
                is_partial = False
            elif tp_mode == "TP_MIDWALL":
                tp1_px = tp_mid_px
                tp2_px = tp_mid_px
                is_partial = False
            elif tp_mode == "TP_MAIN_WALL":
                tp1_px = tp_main_px
                tp2_px = tp_main_px
                is_partial = False
            elif tp_mode == "TP_PARTIAL_WALLS":
                tp1_px = tp_mid_px
                tp2_px = tp_main_px
                is_partial = True
            else:
                tp1_px = round5(avg_price + tp_pts) if sig_dir == 1 else round5(avg_price - tp_pts)
                tp2_px = tp1_px
                is_partial = False

            curr_sl = round5(avg_price - sl_pts) if sig_dir == 1 else round5(avg_price + sl_pts)
            sl0 = curr_sl

            if sig_dir == 1:
                shield_sl1 = max(curr_sl + 35.0, round5(min(def_wall - wall_shield_buf, avg_price - 15.0)))
            else:
                shield_sl1 = min(curr_sl - 35.0, round5(max(def_wall + wall_shield_buf, avg_price + 15.0)))

            j = idx
            exit_px = avg_price
            while j < n and dates[j] == today_str:
                ob_j, hj, lj, cj = opens[j], highs[j], lows[j], closes[j]
                if t_mins[j] >= 1035:
                    exit_px = ob_j
                    break

                # Na barra de entrada intrabar (Limit/Stop), usa sequência OHLC realista
                if j == idx and opened_intrabar:
                    is_bull = cj >= ob_j
                    if sig_dir == 1:
                        eff_low = lj if (action_kind == "PEND_LIMIT" or not is_bull) else min(avg_price, cj)
                        eff_high = hj if (action_kind == "PEND_STOP" or is_bull) else max(avg_price, cj)
                    else:
                        eff_high = hj if (action_kind == "PEND_LIMIT" or is_bull) else max(avg_price, cj)
                        eff_low = lj if (action_kind == "PEND_STOP" or not is_bull) else min(avg_price, cj)
                else:
                    eff_high, eff_low = hj, lj

                if sig_dir == 1:
                    if be_active and eff_low <= avg_price + be_lock and eff_low > curr_sl:
                        touched_zero_after_shield = True

                    if eff_low <= curr_sl:
                        exit_px = min(curr_sl, ob_j) if not (j == idx and opened_intrabar) else curr_sl
                        break

                    if is_partial and not partial_done and eff_high >= tp1_px:
                        partial_done = True
                        partial_exit_px = tp1_px
                        partial_hits += 1
                        be_active = True
                        curr_sl = max(curr_sl, round5(avg_price + be_lock) if be_mode == "BE_ZERO" else shield_sl1)

                    if eff_high >= tp2_px:
                        exit_px = tp2_px
                        break

                    # Fechamento da barra j: atualiza BE e Trailing igual ao OnNewM5Bar do MT5
                    fav = (cj - avg_price) if (j == idx and opened_intrabar) else (eff_high - avg_price)
                    if fav > max_fav_pts:
                        max_fav_pts = fav

                    # [ALINHADO MT5] OnNewM5Bar: stop só sobe se a abertura da próxima barra já estiver além do novo stop + 5
                    nb_open = opens[j + 1] if (j + 1 < n and dates[j + 1] == today_str) else cj
                    if be_trig > 0 and not be_active and max_fav_pts >= be_trig:
                        if be_mode == "BE_ZERO" or def_wall <= 0:
                            cand = round5(avg_price + be_lock)
                        else:
                            cand = max(curr_sl, min(round5(def_wall - wall_shield_buf), avg_price + 10.0))
                            cand = max(cand, round5(avg_price - 90.0))
                        if nb_open > cand + 5.0:
                            curr_sl = max(curr_sl, cand); be_active = True

                    if be_mode == "BE_WALL_2STAGE" and not stage2_active:
                        if max_fav_pts >= 240.0 or (raw_mid_lvl > 0 and cj > raw_mid_lvl + 10.0):
                            cand2 = max(round5(avg_price + be_lock), round5(raw_mid_lvl - wall_shield_buf)) if (raw_mid_lvl > 0 and cj > raw_mid_lvl + 10.0) else round5(avg_price + be_lock)
                            if nb_open > cand2 + 5.0:
                                curr_sl = max(curr_sl, cand2); stage2_active = True; be_active = True

                    if tr_trig > 0 and max_fav_pts >= tr_trig and not (j == idx and opened_intrabar):  # [ALINHADO MT5] sem trailing na barra de entrada intrabar
                        cand_tr = round5(avg_price + max_fav_pts - tr_dist)
                        if nb_open > cand_tr + 5.0:
                            curr_sl = max(curr_sl, cand_tr)

                    # EST-12 Piramidação no Fechamento
                    if est_id == 12 and leg_stage == 1 and (cj - p1_entry) >= 110.0 and j + 1 < n and dates[j + 1] == today_str:
                        nxt_open = opens[j + 1]
                        avg_price = round5(0.5 * (p1_entry + nxt_open))
                        lots = 2
                        leg_stage = 2
                        curr_sl = max(curr_sl, round5(avg_price + 25.0))

                else:  # VENDA
                    if be_active and eff_high >= avg_price - be_lock and eff_high < curr_sl:
                        touched_zero_after_shield = True

                    if eff_high >= curr_sl:
                        exit_px = max(curr_sl, ob_j) if not (j == idx and opened_intrabar) else curr_sl
                        break

                    if is_partial and not partial_done and eff_low <= tp1_px:
                        partial_done = True
                        partial_exit_px = tp1_px
                        partial_hits += 1
                        be_active = True
                        curr_sl = min(curr_sl, round5(avg_price - be_lock) if be_mode == "BE_ZERO" else shield_sl1)

                    if eff_low <= tp2_px:
                        exit_px = tp2_px
                        break

                    fav = (avg_price - cj) if (j == idx and opened_intrabar) else (avg_price - eff_low)
                    if fav > max_fav_pts:
                        max_fav_pts = fav

                    # [ALINHADO MT5] OnNewM5Bar: stop só sobe se a abertura da próxima barra já estiver além do novo stop + 5
                    nb_open = opens[j + 1] if (j + 1 < n and dates[j + 1] == today_str) else cj
                    if be_trig > 0 and not be_active and max_fav_pts >= be_trig:
                        if be_mode == "BE_ZERO" or def_wall <= 0:
                            cand = round5(avg_price - be_lock)
                        else:
                            cand = min(curr_sl, max(round5(def_wall + wall_shield_buf), avg_price - 10.0))
                            cand = min(cand, round5(avg_price + 90.0))
                        if nb_open < cand - 5.0:
                            curr_sl = min(curr_sl, cand); be_active = True

                    if be_mode == "BE_WALL_2STAGE" and not stage2_active:
                        if max_fav_pts >= 240.0 or (raw_mid_lvl > 0 and cj < raw_mid_lvl - 10.0):
                            cand2 = min(round5(avg_price - be_lock), round5(raw_mid_lvl + wall_shield_buf)) if (raw_mid_lvl > 0 and cj < raw_mid_lvl - 10.0) else round5(avg_price - be_lock)
                            if nb_open < cand2 - 5.0:
                                curr_sl = min(curr_sl, cand2); stage2_active = True; be_active = True

                    if tr_trig > 0 and max_fav_pts >= tr_trig and not (j == idx and opened_intrabar):  # [ALINHADO MT5] sem trailing na barra de entrada intrabar
                        cand_tr = round5(avg_price - max_fav_pts + tr_dist)
                        if nb_open < cand_tr - 5.0:
                            curr_sl = min(curr_sl, cand_tr)

                    if est_id == 12 and leg_stage == 1 and (p1_entry - cj) >= 110.0 and j + 1 < n and dates[j + 1] == today_str:
                        nxt_open = opens[j + 1]
                        avg_price = round5(0.5 * (p1_entry + nxt_open))
                        lots = 2
                        leg_stage = 2
                        curr_sl = min(curr_sl, round5(avg_price - 25.0))

                if not (j == idx and opened_intrabar):
                    bars_held += 1
                    if est_id <= 14 and bars_held >= max_hold:
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
                "date": today_str, "i_sig": int(idx), "j_exit": int(min(j, n - 1)), "exit_px": float(exit_px), "avg_px": float(avg_price), "tp_px": float(tp2_px), "sl_last": float(curr_sl), "sl0": float(sl0),
                "est_id": est_id,
                "side": int(sig_dir),
                "pnl_pts": net_pts_unit * lots,
                "contracts": lots,
                "pnl_brl": net_pts_unit * lots * 0.20,
            })
            idx = max(idx + 1, j + 1)

    return trades, {"wall_saves": wall_saves, "partial_hits": partial_hits}


def calc_slot_summary(trades, extra, label=""):
    if not trades:
        return {
            "Config": label, "Trades": 0, "WinRate": 0.0, "PF": 0.0,
            "NetPts": 0.0, "NetBRL": 0.0, "MaxDD_BRL": 0.0, "Ret_DD": 0.0,
            "Sharpe": 0.0, "WallSaves": 0, "PartialHits": 0
        }
    df_t = pd.DataFrame(trades)
    n_t = len(df_t)
    w = df_t[df_t["pnl_brl"] > 0]
    l = df_t[df_t["pnl_brl"] <= 0]
    wr = (len(w) / n_t) * 100.0
    gw = w["pnl_brl"].sum() if len(w) > 0 else 0.0
    gl = abs(l["pnl_brl"].sum()) if len(l) > 0 else 1e-6
    pf = gw / gl if gl > 0 else 99.9

    cum = df_t["pnl_brl"].cumsum().values
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    max_dd = float(np.max(pk - cum)) if len(cum) > 0 else 0.0
    tot_brl = float(cum[-1])
    ret_dd = tot_brl / max_dd if max_dd > 0 else 99.9

    daily = df_t.groupby("date")["pnl_brl"].sum()
    sharpe = float((daily.mean() / daily.std()) * np.sqrt(252)) if len(daily) > 2 and daily.std() > 0 else 0.0

    return {
        "Config": label,
        "Trades": n_t,
        "WinRate": round(wr, 1),
        "PF": round(pf, 2),
        "NetPts": round(float(df_t["pnl_pts"].sum()), 0),
        "NetBRL": round(tot_brl, 2),
        "MaxDD_BRL": round(max_dd, 2),
        "Ret_DD": round(ret_dd, 2),
        "Sharpe": round(sharpe, 2),
        "WallSaves": extra.get("wall_saves", 0),
        "PartialHits": extra.get("partial_hits", 0),
    }


def run_16_setups_optimization():
    t0 = time.time()
    print("=" * 110)
    print("  OTIMIZAÇÃO INDIVIDUAL DOS 16 SETUPS EXISTENTES DO MT5 (EST-01 A EST-16): ANTES vs. DEPOIS")
    print("=" * 110)

    df, gex_by_date = load_win_and_wdo_aligned()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)

    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    comparison_rows = []
    baseline_all_trades = []
    optimized_all_trades = []
    baseline_saves_tot, opt_saves_tot = 0, 0
    baseline_part_tot, opt_part_tot = 0, 0

    for est_id in range(1, 17):
        # 1. Roda o BASELINE exato atual do MT5
        base_tr, base_st = simulate_single_est_slot(
            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode="BE_ZERO", tp_mode="TP_CURRENT"
        )
        base_m = calc_slot_summary(base_tr, base_st, label="BASELINE")
        baseline_all_trades.extend(base_tr)

        # 2. Testa a grade de melhorias (BE Wall Shield/2Stage + Alvos/Parciais nas Walls + Entradas Barra Anterior)
        best_m = base_m
        best_tr = base_tr
        best_st = base_st
        best_desc = "MANTIDO ORIGINAL"

        entry_candidates = ["CURRENT"] if est_id in (9, 10, 11, 13, 14, 16) else ["CURRENT", "STOP_B1_EXT", "LIMIT_B1_EXT", "LIMIT_B1_MID"]
        be_candidates = ["BE_ZERO", "BE_WALL_SHIELD", "BE_WALL_2STAGE"]
        tp_candidates = ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL"] if est_id in (11, 13, 14) else ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"]

        for ent_ov in entry_candidates:
            for be_m in be_candidates:
                buf_list = [0.0] if be_m == "BE_ZERO" else [15.0, 25.0]
                for buf in buf_list:
                    for tp_m in tp_candidates:
                        tr_c, st_c = simulate_single_est_slot(
                            est_id, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                            entry_override=ent_ov, be_mode=be_m, wall_shield_buf=buf, tp_mode=tp_m
                        )
                        if len(tr_c) < max(15, int(0.45 * len(base_tr))):
                            continue
                        m_c = calc_slot_summary(tr_c, st_c)
                        # Critério de seleção: melhora simultânea de Lucro/DD e Lucro Líquido (ou redução de DD mantendo lucro)
                        score_curr = m_c["NetBRL"] + 1.5 * (m_c["NetBRL"] - m_c["MaxDD_BRL"])
                        score_best = best_m["NetBRL"] + 1.5 * (best_m["NetBRL"] - best_m["MaxDD_BRL"])
                        if score_curr > score_best and m_c["PF"] >= best_m["PF"]:
                            best_m = m_c
                            best_tr = tr_c
                            best_st = st_c
                            best_desc = f"Ent={ent_ov} | {be_m}({int(buf)}) | {tp_m}"

        optimized_all_trades.extend(best_tr)
        opt_saves_tot += best_st.get("wall_saves", 0)
        opt_part_tot += best_st.get("partial_hits", 0)

        comparison_rows.append({
            "ID": f"EST-{est_id:02d}",
            "Nome": EST_NAMES[est_id],
            "Trades_Base": base_m["Trades"],
            "BRL_Base": base_m["NetBRL"],
            "DD_Base": base_m["MaxDD_BRL"],
            "PF_Base": base_m["PF"],
            "RetDD_Base": base_m["Ret_DD"],
            "Trades_Opt": best_m["Trades"],
            "BRL_Opt": best_m["NetBRL"],
            "DD_Opt": best_m["MaxDD_BRL"],
            "PF_Opt": best_m["PF"],
            "RetDD_Opt": best_m["Ret_DD"],
            "Delta_BRL": round(best_m["NetBRL"] - base_m["NetBRL"], 2),
            "WallSaves": best_st.get("wall_saves", 0),
            "Parciais": best_st.get("partial_hits", 0),
            "Melhor_Config": best_desc,
        })

    df_comp = pd.DataFrame(comparison_rows)
    df_comp.to_csv(os.path.join(OUT_DIR, "est01_to_16_before_after.csv"), index=False)

    print("\nCOMPARATIVO INDIVIDUAL DOS 16 ROBÔS EXISTENTES (ANTES vs. DEPOIS):")
    print(df_comp[["ID", "Trades_Base", "BRL_Base", "DD_Base", "RetDD_Base", "Trades_Opt", "BRL_Opt", "DD_Opt", "RetDD_Opt", "Delta_BRL", "Melhor_Config"]].to_string(index=False))

    # Portfólio Combinado TODAS AS 16 ESTRATÉGIAS (Antes vs Depois)
    base_all_sorted = sorted(baseline_all_trades, key=lambda x: x["date"])
    opt_all_sorted = sorted(optimized_all_trades, key=lambda x: x["date"])
    m_port_base = calc_slot_summary(base_all_sorted, {"wall_saves": 0, "partial_hits": 0}, "PORTFÓLIO 16 ROBÔS ATUAL (BASELINE)")
    m_port_opt = calc_slot_summary(opt_all_sorted, {"wall_saves": opt_saves_tot, "partial_hits": opt_part_tot}, "PORTFÓLIO 16 ROBÔS OTIMIZADO (NOVO)")

    df_port = pd.DataFrame([m_port_base, m_port_opt])
    df_port.to_csv(os.path.join(OUT_DIR, "portfolio_16_before_after.csv"), index=False)
    print("\n" + "=" * 110)
    print("  IMPACTO NO PORTFÓLIO COMPLETO DAS 16 ESTRATÉGIAS (EST-01 A EST-16 JUNTAS):")
    print("=" * 110)
    print(df_port[["Config", "Trades", "WinRate", "PF", "NetPts", "NetBRL", "MaxDD_BRL", "Ret_DD", "Sharpe", "WallSaves", "PartialHits"]].to_string(index=False))
    print(f"\nConcluído em {time.time() - t0:.1f}s. Relatórios salvos em: {OUT_DIR}")


if __name__ == "__main__":
    run_16_setups_optimization()
