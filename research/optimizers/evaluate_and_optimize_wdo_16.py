"""
AUDITORIA E OTIMIZAÇÃO COMPLETA DOS 16 ROBÔS DO DÓLAR (WDO-01 A WDO-16)
=======================================================================
Replica fielmente a lógica exata de cada uma das 16 estratégias (`WDO-01` a `WDO-16`)
de `mt5/Include/Jumba_WDO_GEX_NWE_Core.mqh` sobre os 122 pregões reais de WDO$N + WIN$N
e avalia:

  1. Diagnóstico Individual do Portfólio Atual (`WDO-01` a `WDO-16` Baseline MT5)
  2. Otimização Individual nos 3 Pilares Estruturais (Caminho 1):
     - Pilar 1 (Break-Even):
         * `BE_ZERO` (atual: avg_price ± be_lock)
         * `BE_WALL_SHIELD` (reduz SL para trás da Wall defendida: def_wall ∓ buf_pts, buf = 1.0, 1.5, 2.0 pts)
         * `BE_WALL_2STAGE` (Estágio 1 atrás da Wall; Estágio 2 trava +2.5 pts após esticar 12.0 pts ou cruzar MidWall)
     - Pilar 2 (Alvos Estruturais e Saídas Parciais):
         * `TP_CURRENT` (alvo fixo original em pontos)
         * `TP_MIDWALL` (100% na próxima MidWall real - front_run)
         * `TP_MAIN_WALL` (100% na próxima Main Wall real - front_run)
         * `TP_PARTIAL_WALLS` (50% na MidWall + 50% na Main Wall com stop protegido atrás da Wall)
     - Pilar 3 (Gatilhos de Entrada na Barra Anterior `b1`):
         * `CURRENT` (gatilho original da WDO-k)
         * `STOP_B1_EXT` (entrada Stop na confirmação de b1.high+0.5 / b1.low-0.5)
         * `LIMIT_B1_EXT` (entrada Limit na mínima/máxima de b1: b1.low+0.5 / b1.high-0.5)
         * `LIMIT_B1_MID` (entrada Limit em 50% da barra b1)
  3. Descoberta dos 4 Novos Achados Estruturais do WDO (Price Action Barra[1] + Wall2Stop + Alvo/Parcial nas Walls, 2 Contratos)
  4. Comparativo dos 4 Estágios do Portfólio WDO:
     - Estágio 1: ATUAL LEGACY (`WDO-01..16` Sem Alteração)
     - Estágio 2: TROCA PURA ANTES DA OTIMIZAÇÃO (Mantém originais intactos e substitui apenas as vagas de pior Ret/DD pelos Novos Achados)
     - Estágio 3: OTIMIZADO 3-PILARES (`WDO-01..16` Caminho 1: Alvo Cheio vs Saída Parcial)
     - Estágio 4: PORTFÓLIO MIX CAMPEÃO DO DÓLAR (Regra Estrita: Maior Ret/DD em cada vaga 01..16!)
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

from research.discover_gex_nwe_setups import compute_nwe_series, DB_PATH

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "wdo_16_setups_opt")
os.makedirs(OUT_DIR, exist_ok=True)

WDO_NAMES = {
    1:  "WDO-01 Scalper Hibrido NY",
    2:  "WDO-02 Scalper Hibrido CORE",
    3:  "WDO-03 Arbitragem WIN+WDO Wall",
    4:  "WDO-04 Limit Wall c/ GammaFlip",
    5:  "WDO-05 Cluster NWE30+NWE50+Wall",
    6:  "WDO-06 Limit Wall Rejeicao NWE50",
    7:  "WDO-07 Absorcao Mkt Wall NY",
    8:  "WDO-08 Absorcao Mkt Wall CORE",
    9:  "WDO-09 Stop & Limit Wall NY",
    10: "WDO-10 Stop & Limit Main Walls",
    11: "WDO-11 Grid 1+2 Absorcao NWE",
    12: "WDO-12 Piramidacao 1+1 Lucro NY",
    13: "WDO-13 Smart Grid 1+2 GammaFlip",
    14: "WDO-14 Grid 1+2+3 Institucional",
    15: "WDO-15 Posicional EOD Matinal",
    16: "WDO-16 Posicional EOD Limit Wall",
}


def round05(val: float) -> float:
    return np.round(val * 2.0) / 2.0


def window_ok(t_min: int, wmode: str) -> bool:
    if wmode == "MORNING_09_12":
        return 545 <= t_min <= 720
    if wmode == "NO_LUNCH":
        return (545 <= t_min <= 735) or (810 <= t_min <= 1005)
    if wmode == "NY_1000_1630":
        return 600 <= t_min <= 990
    if wmode == "CORE_09_1615":
        return 550 <= t_min <= 975
    if wmode == "FULL_09_17":
        return 545 <= t_min <= 1020
    return False


def load_wdo_and_win_aligned(use_sqlite: bool = False):
    if not use_sqlite:
        from research.mt5_loader import load_wdo_and_win_aligned as _mt5_load_wdo_and_win_aligned
        return _mt5_load_wdo_and_win_aligned()
    conn = sqlite3.connect(DB_PATH)
    df_bars = pd.read_sql_query(
        """
        SELECT timestamp_utc, open, high, low, close, volume, delta
        FROM market_bars
        WHERE symbol = 'WDO$N' AND timeframe = 'M5' AND timestamp_utc >= '2026-04-15'
        ORDER BY timestamp_utc ASC
        """,
        conn,
    )
    df_win = pd.read_sql_query(
        """
        SELECT timestamp_utc, close AS win_close
        FROM market_bars
        WHERE symbol = 'WIN$N' AND timeframe = 'M5' AND timestamp_utc >= '2026-04-15'
        ORDER BY timestamp_utc ASC
        """,
        conn,
    )
    conn.close()

    # Compute WIN metrics exactly as ComputeWinMetrics in Jumba_WDO_GEX_NWE_Core.mqh
    wc = df_win["win_close"].values
    win_ret3 = np.zeros(len(wc), dtype=float)
    win_z = np.zeros(len(wc), dtype=float)
    rets = np.zeros(len(wc), dtype=float)
    for i in range(1, len(wc)):
        if wc[i - 1] > 0:
            rets[i] = wc[i] / wc[i - 1] - 1.0
    for i in range(25, len(wc)):
        if wc[i - 3] > 0:
            win_ret3[i] = (wc[i] / wc[i - 3] - 1.0) * 10000.0
        window_r = rets[i - 19 : i + 1]
        std = np.std(window_r)
        if std > 1e-9:
            win_z[i] = (rets[i] - np.mean(window_r)) / std

    df_win["win_ret3"] = win_ret3
    df_win["win_z"] = win_z

    df_bars = pd.merge(df_bars, df_win[["timestamp_utc", "win_ret3", "win_z"]], on="timestamp_utc", how="left")
    df_bars["win_ret3"] = df_bars["win_ret3"].ffill().fillna(0.0)
    df_bars["win_z"] = df_bars["win_z"].ffill().fillna(0.0)

    # Normalize timestamp_utc to BRT (09:00 - 17:55)
    ts_dt = pd.to_datetime(df_bars["timestamp_utc"])
    is_shifted = ts_dt >= pd.Timestamp("2026-06-24T14:00:00Z")
    ts_brt = ts_dt.copy()
    ts_brt.loc[is_shifted] = ts_dt.loc[is_shifted] - pd.Timedelta(hours=6)

    df_bars["dt_brt"] = ts_brt
    df_bars["session_date"] = df_bars["dt_brt"].dt.strftime("%Y-%m-%d")
    df_bars["hour"] = df_bars["dt_brt"].dt.hour
    df_bars["minute"] = df_bars["dt_brt"].dt.minute
    df_bars["t_min"] = df_bars["hour"] * 60 + df_bars["minute"]

    df_bars = df_bars[(df_bars["t_min"] >= 9 * 60) & (df_bars["t_min"] <= 17 * 60 + 55)].copy()
    df_bars.reset_index(drop=True, inplace=True)

    # Load WDO GEX history from mt5/Files/jumba_gex_wdo_history.csv
    csv_path = os.path.join(ROOT_DIR, "mt5", "Files", "jumba_gex_wdo_history.csv")
    df_csv = pd.read_csv(csv_path, sep=";")
    gex_by_date = {}
    for s_date, grp in df_csv.groupby("session_date"):
        walls = sorted(grp[grp["type"].isin(["Wall", "wall"])]["price"].astype(float).tolist())
        mid_walls = sorted(grp[grp["type"].isin(["MidWall", "mid_wall"])]["price"].astype(float).tolist())
        gf_rows = grp[grp["type"].isin(["GammaFlip", "gamma_flip"])]["price"].astype(float).tolist()
        maxg_rows = grp[grp["type"].isin(["MaxGamma", "max_gamma"])]["price"].astype(float).tolist()
        ming_rows = grp[grp["type"].isin(["MinGamma", "min_gamma"])]["price"].astype(float).tolist()
        all_lvls = sorted(grp["price"].astype(float).tolist())
        gex_by_date[str(s_date)] = {
            "walls": np.array(walls, dtype=float),
            "mid_walls": np.array(mid_walls, dtype=float),
            "all_levels": np.array(all_lvls, dtype=float),
            "gamma_flip": gf_rows[0] if gf_rows else 0.0,
            "max_gamma": maxg_rows[0] if maxg_rows else 0.0,
            "min_gamma": ming_rows[0] if ming_rows else 0.0,
        }

    return df_bars, gex_by_date


def find_nearest_level(levels: np.ndarray, price: float):
    if len(levels) == 0:
        return 999999.0, 0.0
    diffs = np.abs(levels - price)
    idx = int(np.argmin(diffs))
    return float(diffs[idx]), float(levels[idx])


def find_wdo_structural_targets(entry_px: float, side: int, walls: np.ndarray, all_lvls: np.ndarray, front_run: float = 0.5):
    """
    Localiza a próxima MidWall (`raw_mid`) e a próxima Main Wall (`raw_main`) na direção do trade no WDO.
    Garante distância mínima realista de pelo menos 7.5 pts para MidWall e 14.0 pts para Main Wall.
    """
    if side == 1:
        cand_all = all_lvls[all_lvls >= entry_px + 7.5]
        cand_walls = walls[walls >= entry_px + 14.0]
        raw_mid = float(cand_all[0]) if len(cand_all) > 0 else entry_px + 18.0
        if len(cand_walls) > 0:
            raw_main = float(cand_walls[0])
            if raw_main <= raw_mid + 3.5 and len(cand_all) > 1:
                raw_main = float(cand_all[1])
            elif raw_main <= raw_mid + 3.5:
                raw_main = raw_mid + 16.0
        elif len(cand_all) > 1:
            raw_main = float(cand_all[1])
        else:
            raw_main = raw_mid + 16.0
        return round05(raw_mid - front_run), round05(raw_main - front_run), raw_mid, raw_main
    else:
        cand_all = all_lvls[all_lvls <= entry_px - 7.5]
        cand_walls = walls[walls <= entry_px - 14.0]
        raw_mid = float(cand_all[-1]) if len(cand_all) > 0 else entry_px - 18.0
        if len(cand_walls) > 0:
            raw_main = float(cand_walls[-1])
            if raw_main >= raw_mid - 3.5 and len(cand_all) > 1:
                raw_main = float(cand_all[-2])
            elif raw_main >= raw_mid - 3.5:
                raw_main = raw_mid - 16.0
        elif len(cand_all) > 1:
            raw_main = float(cand_all[-2])
        else:
            raw_main = raw_mid - 16.0
        return round05(raw_mid + front_run), round05(raw_main + front_run), raw_mid, raw_main


def simulate_single_wdo_slot(
    slot_id: int,
    df: pd.DataFrame,
    gex_by_date: dict,
    n50_c: np.ndarray, n50_u: np.ndarray, n50_l: np.ndarray, n50_s: np.ndarray,
    n30_c: np.ndarray, n30_u: np.ndarray, n30_l: np.ndarray, n30_s: np.ndarray,
    rsi7s: np.ndarray,
    entry_override: str = "CURRENT",   # "CURRENT", "STOP_B1_EXT", "LIMIT_B1_EXT", "LIMIT_B1_MID"
    be_mode: str = "BE_ZERO",          # "BE_ZERO", "BE_WALL_SHIELD", "BE_WALL_2STAGE"
    wall_shield_buf: float = 1.5,      # Distância atrás da Wall em pts do WDO (ex: 1.0, 1.5, 2.0)
    tp_mode: str = "TP_CURRENT",       # "TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"
    front_run_pts: float = 0.5,
    cost_pts: float = 0.5,             # R$ 5,00 por contrato de custo/slippage
):
    """
    Executa a simulação fiel da estratégia `WDO-slot_id` (1..16) de `Jumba_WDO_GEX_NWE_Core.mqh`.
    1 ponto de WDO = R$ 10,00 por mini-contrato.
    """
    dates = df["session_date"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values
    win_ret3 = df["win_ret3"].values
    win_z = df["win_z"].values

    trades = []
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

        if today_str < "2026-05-07" or today_str not in gex_by_date or b1_date != today_str:
            idx += 1
            continue

        new_tmin = int(t_mins[idx])
        b1_tmin = int(t_mins[b1_idx])
        if new_tmin >= 1035:
            idx += 1
            continue

        g = gex_by_date[today_str]
        m_levels_walls = g["walls"]
        m_levels_all = g["all_levels"]
        m_gamma_flip = g["gamma_flip"] or 0.0
        if len(m_levels_all) == 0:
            idx += 1
            continue

        b1_o, b1_h, b1_l, b1_c = opens[b1_idx], highs[b1_idx], lows[b1_idx], closes[b1_idx]
        new_bar_open = opens[idx]

        d_l, lvl_s = find_nearest_level(m_levels_all, b1_l)
        d_h, lvl_r = find_nearest_level(m_levels_all, b1_h)
        dw_l_main, w_s_main = find_nearest_level(m_levels_walls, b1_l)
        dw_h_main, w_r_main = find_nearest_level(m_levels_walls, b1_h)

        bw50 = max(1.0, n50_u[b1_idx] - n50_l[b1_idx])
        pos50 = (b1_c - n50_l[b1_idx]) / bw50
        bw30 = max(1.0, n30_u[b1_idx] - n30_l[b1_idx])
        pos30 = (b1_c - n30_l[b1_idx]) / bw30
        body1 = b1_c - b1_o

        m_n50_s_1, m_n50_u_1, m_n50_l_1 = n50_s[b1_idx], n50_u[b1_idx], n50_l[b1_idx]
        m_n30_s_1, m_n30_u_1, m_n30_l_1 = n30_s[b1_idx], n30_u[b1_idx], n30_l[b1_idx]
        m_win_ret3_1, m_win_z_1 = win_ret3[b1_idx], win_z[b1_idx]

        # Detect signal exactly as in Jumba_WDO_GEX_NWE_Core.mqh
        action = None  # "MKT", "PEND", "GRID"
        sig_dir = 0
        pend_type = 0  # 1=Limit, 2=Stop
        pend_px = 0.0
        tp_pts = 0.0
        sl_pts = 0.0
        be_trig = 0.0
        be_lock = 0.0
        tr_trig = 0.0
        tr_dist = 0.0
        max_hold = 16
        pyr_trig = 0.0
        pyr_lock = 1.0
        grid_params = None
        def_wall = 0.0

        # --- WDO-01 ---
        if slot_id == 1:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NY_1000_1630"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", -1, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, lvl
                        break
                    if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", 1, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, lvl
                        break
            if action is None and window_ok(new_tmin, "NY_1000_1630"):
                if pos50 >= 0.65 and d_h <= 3.5 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_r
                elif pos50 <= 0.35 and d_l <= 3.5 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_s

        # --- WDO-02 ---
        elif slot_id == 2:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 2.0):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", -1, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, lvl
                        break
                    if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 2.0):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", 1, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 15, lvl
                        break
            if action is None and window_ok(new_tmin, "CORE_09_1615"):
                if pos50 >= 0.64 and d_h <= 3.5 and b1_c < (lvl_r - 0.5) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r - 0.5, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_r
                elif pos50 <= 0.36 and d_l <= 3.5 and b1_c > (lvl_s + 0.5) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s + 0.5, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_s

        # --- WDO-03 ---
        elif slot_id == 3:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 1.5 and (m_win_ret3_1 >= -8.0 or m_win_z_1 >= -1.2):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", -1, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16, lvl
                        break
                    if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 1.5 and (m_win_ret3_1 <= 8.0 or m_win_z_1 <= 1.2):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", 1, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16, lvl
                        break
            if action is None and window_ok(new_tmin, "FULL_09_17"):
                if pos50 >= 0.65 and (m_win_ret3_1 >= 8.0 or m_win_z_1 >= 1.2) and d_h <= 3.5 and b1_c < lvl_r:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16, lvl_r
                elif pos50 <= 0.35 and (m_win_ret3_1 <= -8.0 or m_win_z_1 <= -1.2) and d_l <= 3.5 and b1_c > lvl_s:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 22.0, 12.0, 7.0, 1.5, 13.0, 5.0, 16, lvl_s

        # --- WDO-04 ---
        elif slot_id == 4:
            if window_ok(new_tmin, "FULL_09_17") and m_gamma_flip > 0.0:
                if b1_c > m_gamma_flip + 4.0 and pos50 >= 0.65 and d_h <= 3.5 and b1_c < lvl_r:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 25.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18, lvl_r
                elif b1_c < m_gamma_flip - 4.0 and pos50 <= 0.35 and d_l <= 3.5 and b1_c > lvl_s:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 25.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18, lvl_s

        # --- WDO-05 ---
        elif slot_id == 5:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "CORE_09_1615"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n30_s_1 >= 0.15 and m_n50_s_1 >= 0.10 and b1_c < (m_n30_u_1 - bw30 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", -1, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 16, lvl
                        break
                    if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n30_s_1 <= -0.15 and m_n50_s_1 <= -0.10 and b1_c > (m_n30_l_1 + bw30 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", 1, 18.0, 11.0, 6.5, 1.5, 11.0, 4.5, 16, lvl
                        break
            if action is None and window_ok(new_tmin, "CORE_09_1615"):
                if pos30 >= 0.65 and pos50 >= 0.62 and d_h <= 3.5 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_r
                elif pos30 <= 0.35 and pos50 <= 0.38 and d_l <= 3.5 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 24.0, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_s

        # --- WDO-06 ---
        elif slot_id == 6:
            if window_ok(new_tmin, "FULL_09_17"):
                if pos50 >= 0.62 and d_h <= 3.5 and b1_c < lvl_r and (b1_c < b1_o or (m_gamma_flip > 0.0 and b1_c > m_gamma_flip)):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_r
                elif pos50 <= 0.38 and d_l <= 3.5 and b1_c > lvl_s and (b1_c > b1_o or (m_gamma_flip > 0.0 and b1_c < m_gamma_flip)):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_s

        # --- WDO-07 & WDO-08 ---
        elif slot_id in (7, 8):
            wm_bo = "NY_1000_1630" if slot_id == 7 else "CORE_09_1615"
            tp_b = 19.0 if slot_id == 7 else 18.0
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, wm_bo):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", -1, tp_b, 11.0, 6.5, 1.5, 11.0, 4.5, 15, lvl
                        break
                    if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", 1, tp_b, 11.0, 6.5, 1.5, 11.0, 4.5, 15, lvl
                        break

        # --- WDO-09 ---
        elif slot_id == 9:
            if window_ok(new_tmin, "NY_1000_1630"):
                if pos30 <= 0.28 and d_l <= 4.0 and b1_c > b1_o and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 10.0):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 2, b1_h + 0.5, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16, lvl_s
                elif pos30 >= 0.72 and d_h <= 4.0 and b1_c < b1_o and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 10.0):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 2, b1_l - 0.5, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16, lvl_r
                elif pos50 <= 0.35 and d_l <= 4.0 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16, lvl_s
                elif pos50 >= 0.65 and d_h <= 4.0 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 24.0, 13.0, 7.5, 1.5, 14.0, 5.0, 16, lvl_r

        # --- WDO-10 ---
        elif slot_id == 10:
            if window_ok(new_tmin, "CORE_09_1615") and len(m_levels_walls) > 0:
                if dw_h_main <= 6.0 and pos50 >= 0.65 and b1_c < w_r_main and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, w_r_main, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18, w_r_main
                elif dw_l_main <= 6.0 and pos50 <= 0.35 and b1_c > w_s_main and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, w_s_main, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18, w_s_main
                elif m_gamma_flip > 0.0 and b1_c > m_gamma_flip + 5.0 and pos50 >= 0.70 and d_h <= 3.5 and b1_c < lvl_r:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18, lvl_r
                elif m_gamma_flip > 0.0 and b1_c < m_gamma_flip - 5.0 and pos50 <= 0.30 and d_l <= 3.5 and b1_c > lvl_s:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 26.0, 14.0, 8.0, 1.5, 15.0, 5.5, 18, lvl_s

        # --- WDO-11 ---
        elif slot_id == 11:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NO_LUNCH"):
                if pos50 <= 0.25 and d_l <= 4.0 and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 15.0):
                    action, sig_dir, grid_params, def_wall = "GRID", 1, (16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 24), lvl_s
                elif pos50 >= 0.75 and d_h <= 4.0 and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 15.0):
                    action, sig_dir, grid_params, def_wall = "GRID", -1, (16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 24), lvl_r

        # --- WDO-12 ---
        elif slot_id == 12:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "NY_1000_1630"):
                for lvl in m_levels_all:
                    if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, pyr_trig, pyr_lock, def_wall = "MKT", -1, 24.0, 12.0, 7.0, 1.5, 13.5, 5.0, 16, 8.5, 2.5, lvl
                        break
                    if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                        action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, pyr_trig, pyr_lock, def_wall = "MKT", 1, 24.0, 12.0, 7.0, 1.5, 13.5, 5.0, 16, 8.5, 2.5, lvl
                        break
            if action is None and window_ok(new_tmin, "NY_1000_1630") and m_gamma_flip > 0.0:
                if b1_c > m_gamma_flip + 4.0 and pos50 >= 0.65 and d_h <= 3.5 and b1_c < lvl_r:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, pyr_trig, pyr_lock, def_wall = "PEND", -1, 1, lvl_r, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16, 8.5, 2.5, lvl_r
                elif b1_c < m_gamma_flip - 4.0 and pos50 <= 0.35 and d_l <= 3.5 and b1_c > lvl_s:
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, pyr_trig, pyr_lock, def_wall = "PEND", 1, 1, lvl_s, 25.0, 13.5, 7.5, 1.5, 14.5, 5.5, 16, 8.5, 2.5, lvl_s

        # --- WDO-13 ---
        elif slot_id == 13:
            if last_entry_bar_idx != b1_idx and window_ok(b1_tmin, "FULL_09_17") and m_gamma_flip > 0.0:
                if b1_c < m_gamma_flip - 5.0 and pos50 <= 0.35 and d_l <= 4.5 and b1_c > b1_o:
                    action, sig_dir, grid_params, def_wall = "GRID", 1, (16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 26), lvl_s
                elif b1_c > m_gamma_flip + 5.0 and pos50 >= 0.65 and d_h <= 4.5 and b1_c < b1_o:
                    action, sig_dir, grid_params, def_wall = "GRID", -1, (16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 26), lvl_r

        # --- WDO-14 ---
        elif slot_id == 14:
            if last_entry_bar_idx != b1_idx and 545 <= b1_tmin <= 930 and m_gamma_flip > 0.0:
                if b1_c < m_gamma_flip - 5.0 and pos50 <= 0.35 and d_l <= 4.5 and b1_c > b1_o:
                    action, sig_dir, grid_params, def_wall = "GRID", 1, (18.0, 40.0, 1, 2, 3, 11.0, 22.0, 6.5, 1.5, 26), lvl_s
                elif b1_c > m_gamma_flip + 5.0 and pos50 >= 0.65 and d_h <= 4.5 and b1_c < b1_o:
                    action, sig_dir, grid_params, def_wall = "GRID", -1, (18.0, 40.0, 1, 2, 3, 11.0, 22.0, 6.5, 1.5, 26), lvl_r

        # --- WDO-15 ---
        elif slot_id == 15:
            if last_trade_date != today_str:
                if 545 <= b1_tmin <= 780:
                    for lvl in m_levels_all:
                        if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                            action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", -1, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, lvl
                            break
                        if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                            action, sig_dir, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "MKT", 1, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, lvl
                            break
                if action is None and 550 <= new_tmin <= 810:
                    if pos50 >= 0.65 and d_h <= 3.5 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                        action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, lvl_r
                    elif pos50 <= 0.35 and d_l <= 3.5 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                        action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, lvl_s

        # --- WDO-16 ---
        elif slot_id == 16:
            if last_trade_date != today_str and 550 <= new_tmin <= 840:
                if pos50 >= 0.68 and d_h <= 3.5 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", -1, 1, lvl_r, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, lvl_r
                elif pos50 <= 0.32 and d_l <= 3.5 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                    action, sig_dir, pend_type, pend_px, tp_pts, sl_pts, be_trig, be_lock, tr_trig, tr_dist, max_hold, def_wall = "PEND", 1, 1, lvl_s, 65.0, 20.0, 12.5, 2.0, 26.0, 10.5, 120, lvl_s

        if action is None:
            idx += 1
            continue

        # Apply Entry Override (Pilar 3) for non-grid strategies
        if action in ("MKT", "PEND") and entry_override != "CURRENT":
            if entry_override == "STOP_B1_EXT":
                action = "PEND"
                pend_type = 2
                pend_px = round05(b1_h + 0.5) if sig_dir == 1 else round05(b1_l - 0.5)
            elif entry_override == "LIMIT_B1_EXT":
                action = "PEND"
                pend_type = 1
                pend_px = round05(b1_l + 0.5) if sig_dir == 1 else round05(b1_h - 0.5)
            elif entry_override == "LIMIT_B1_MID":
                action = "PEND"
                pend_type = 1
                pend_px = round05(0.5 * (b1_h + b1_l))

        # Check Pending Order execution on bar `idx`
        opened_intrabar = False
        if action == "PEND":
            p05 = round05(pend_px)
            if pend_type == 1 and sig_dir == 1 and new_bar_open < p05:
                idx += 1
                continue
            if pend_type == 1 and sig_dir == -1 and new_bar_open > p05:
                idx += 1
                continue
            if pend_type == 2 and sig_dir == 1 and new_bar_open > p05:
                idx += 1
                continue
            if pend_type == 2 and sig_dir == -1 and new_bar_open < p05:
                idx += 1
                continue

            triggered = False
            if pend_type == 1:
                if sig_dir == 1 and lows[idx] <= p05:
                    triggered = True
                elif sig_dir == -1 and highs[idx] >= p05:
                    triggered = True
            elif pend_type == 2:
                if sig_dir == 1 and highs[idx] >= p05:
                    triggered = True
                elif sig_dir == -1 and lows[idx] <= p05:
                    triggered = True

            if not triggered:
                idx += 1
                continue

            entry_px = p05
            opened_intrabar = True
            last_entry_bar_idx = idx
            if slot_id in (15, 16):
                last_trade_date = today_str
        else:
            entry_px = round05(new_bar_open)
            last_entry_bar_idx = b1_idx
            if slot_id in (15, 16):
                last_trade_date = today_str

        # --- Simulate Position Lifecycle ---
        if action == "GRID":
            step2, step3, l1, l2, l3, tp_avg, max_sl, be_t, be_l, m_hold = grid_params
            lots = l1
            leg_stage = 1
            p1_entry = entry_px
            avg_price = entry_px
            worst_off = (l2 * step2 + l3 * step3) / (l1 + l2 + l3) if l3 > 0 else (l2 * step2) / (l1 + l2)
            init_sl_dist = max(max_sl, worst_off + max_sl)
            curr_sl = round05(entry_px - init_sl_dist) if sig_dir == 1 else round05(entry_px + init_sl_dist)

            tp_mid_px, tp_main_px, _, _ = find_wdo_structural_targets(avg_price, sig_dir, m_levels_walls, m_levels_all, front_run_pts)
            if tp_mode == "TP_MIDWALL":
                curr_tp = tp_mid_px
            elif tp_mode in ("TP_MAIN_WALL", "TP_PARTIAL_WALLS"):
                curr_tp = tp_main_px
            else:
                curr_tp = round05(avg_price + tp_avg) if sig_dir == 1 else round05(avg_price - tp_avg)

            max_fav = 0.0
            be_active = False
            bars_held = 0
            k = idx
            exit_px = closes[idx]

            while k < n:
                if dates[k] != today_str or int(t_mins[k]) >= 1035:
                    exit_px = opens[k] if dates[k] == today_str else closes[k - 1]
                    break
                bh, bl, bc = highs[k], lows[k], closes[k]

                # Scaling-in legs
                if leg_stage == 1 and l2 > 0:
                    p2_lvl = round05(p1_entry - step2) if sig_dir == 1 else round05(p1_entry + step2)
                    if (sig_dir == 1 and bl <= p2_lvl) or (sig_dir == -1 and bh >= p2_lvl):
                        new_lots = l1 + l2
                        avg_price = round05((p1_entry * l1 + p2_lvl * l2) / new_lots)
                        lots = new_lots
                        leg_stage = 2
                        be_active = False
                        max_fav = 0.0
                        curr_tp = round05(avg_price + tp_avg) if sig_dir == 1 else round05(avg_price - tp_avg)
                        curr_sl = round05(avg_price - max_sl) if sig_dir == 1 else round05(avg_price + max_sl)

                if leg_stage == 2 and l3 > 0:
                    p3_lvl = round05(p1_entry - step3) if sig_dir == 1 else round05(p1_entry + step3)
                    if (sig_dir == 1 and bl <= p3_lvl) or (sig_dir == -1 and bh >= p3_lvl):
                        new_lots = lots + l3
                        avg_price = round05((avg_price * lots + p3_lvl * l3) / new_lots)
                        lots = new_lots
                        leg_stage = 3
                        be_active = False
                        max_fav = 0.0
                        curr_tp = round05(avg_price + tp_avg) if sig_dir == 1 else round05(avg_price - tp_avg)
                        curr_sl = round05(avg_price - max_sl) if sig_dir == 1 else round05(avg_price + max_sl)

                if sig_dir == 1:
                    if bl <= curr_sl:
                        exit_px = curr_sl
                        break
                    if bh >= curr_tp:
                        exit_px = curr_tp
                        break
                else:
                    if bh >= curr_sl:
                        exit_px = curr_sl
                        break
                    if bl <= curr_tp:
                        exit_px = curr_tp
                        break

                bars_held += 1
                fav = (bh - avg_price) if sig_dir == 1 else (avg_price - bl)
                if fav > max_fav:
                    max_fav = fav

                if k + 1 < n and dates[k + 1] == today_str:
                    nxt_open = opens[k + 1]
                    if be_t > 0.0 and not be_active and max_fav >= be_t:
                        if be_mode in ("BE_WALL_SHIELD", "BE_WALL_2STAGE") and leg_stage == 1 and def_wall > 0:
                            cand_sl = round05(def_wall - wall_shield_buf) if sig_dir == 1 else round05(def_wall + wall_shield_buf)
                        else:
                            cand_sl = round05(avg_price + be_l) if sig_dir == 1 else round05(avg_price - be_l)
                        if (sig_dir == 1 and nxt_open > cand_sl + 0.5) or (sig_dir == -1 and nxt_open < cand_sl - 0.5):
                            curr_sl = max(curr_sl, cand_sl) if sig_dir == 1 else min(curr_sl, cand_sl)
                            be_active = True
                    if be_mode == "BE_WALL_2STAGE" and max_fav >= be_t + 4.5:
                        cand_sl2 = round05(avg_price + be_l) if sig_dir == 1 else round05(avg_price - be_l)
                        if (sig_dir == 1 and nxt_open > cand_sl2 + 0.5) or (sig_dir == -1 and nxt_open < cand_sl2 - 0.5):
                            curr_sl = max(curr_sl, cand_sl2) if sig_dir == 1 else min(curr_sl, cand_sl2)

                    if bars_held >= m_hold:
                        exit_px = nxt_open
                        k += 1
                        break
                k += 1

            pnl_pts = ((exit_px - avg_price) * sig_dir - cost_pts) * lots
            trades.append({
                "date": today_str,
                "slot_id": slot_id,
                "side": sig_dir,
                "contracts": float(lots),
                "pnl_pts": float(pnl_pts),
                "pnl_brl": float(pnl_pts * 10.0),
            })
            idx = max(idx + 1, k + 1)

        else:
            # Single / Pyramiding / Partial Trade Lifecycle
            p1_entry = entry_px
            avg_price = entry_px
            lots = 1
            leg_stage = 1
            curr_sl = round05(entry_px - sl_pts) if sig_dir == 1 else round05(entry_px + sl_pts)

            tp_mid_px, tp_main_px, raw_mid, _ = find_wdo_structural_targets(entry_px, sig_dir, m_levels_walls, m_levels_all, front_run_pts)
            if tp_mode == "TP_MIDWALL":
                curr_tp = tp_mid_px
            elif tp_mode in ("TP_MAIN_WALL", "TP_PARTIAL_WALLS"):
                curr_tp = tp_main_px
            else:
                curr_tp = round05(entry_px + tp_pts) if sig_dir == 1 else round05(entry_px - tp_pts)

            max_fav = 0.0
            be_active = False
            partial_done = False
            partial_pnl_pts = 0.0
            rem_weight = 1.0
            touched_zero_after_be = False
            bars_held = 0
            k = idx
            exit_px = closes[idx]

            while k < n:
                if dates[k] != today_str or int(t_mins[k]) >= 1035:
                    exit_px = opens[k] if dates[k] == today_str else closes[k - 1]
                    break
                bh, bl, bc = highs[k], lows[k], closes[k]

                if be_active and be_mode in ("BE_WALL_SHIELD", "BE_WALL_2STAGE"):
                    if (sig_dir == 1 and bl <= avg_price + be_lock) or (sig_dir == -1 and bh >= avg_price - be_lock):
                        touched_zero_after_be = True

                if sig_dir == 1:
                    if bl <= curr_sl:
                        exit_px = curr_sl
                        break
                    if tp_mode == "TP_PARTIAL_WALLS" and not partial_done and bh >= tp_mid_px:
                        partial_done = True
                        partial_hits += 1
                        partial_pnl_pts = 0.5 * ((tp_mid_px - avg_price) - cost_pts)
                        rem_weight = 0.5
                        if def_wall > 0:
                            sh_sl = round05(def_wall - wall_shield_buf)
                            curr_sl = max(curr_sl, sh_sl)
                        else:
                            curr_sl = max(curr_sl, round05(avg_price + be_lock))
                        be_active = True
                    if bh >= curr_tp:
                        exit_px = curr_tp
                        break
                else:
                    if bh >= curr_sl:
                        exit_px = curr_sl
                        break
                    if tp_mode == "TP_PARTIAL_WALLS" and not partial_done and bl <= tp_mid_px:
                        partial_done = True
                        partial_hits += 1
                        partial_pnl_pts = 0.5 * ((avg_price - tp_mid_px) - cost_pts)
                        rem_weight = 0.5
                        if def_wall > 0:
                            sh_sl = round05(def_wall + wall_shield_buf)
                            curr_sl = min(curr_sl, sh_sl)
                        else:
                            curr_sl = min(curr_sl, round05(avg_price - be_lock))
                        be_active = True
                    if bl <= curr_tp:
                        exit_px = curr_tp
                        break

                if k + 1 < n and dates[k + 1] == today_str:
                    nxt_open = opens[k + 1]
                    if opened_intrabar:
                        fav_c = (bc - avg_price) if sig_dir == 1 else (avg_price - bc)
                        if fav_c > max_fav:
                            max_fav = fav_c
                        if be_trig > 0.0 and not be_active and max_fav >= be_trig:
                            if be_mode in ("BE_WALL_SHIELD", "BE_WALL_2STAGE") and def_wall > 0:
                                cand_sl = round05(def_wall - wall_shield_buf) if sig_dir == 1 else round05(def_wall + wall_shield_buf)
                            else:
                                cand_sl = round05(avg_price + be_lock) if sig_dir == 1 else round05(avg_price - be_lock)
                            if (sig_dir == 1 and nxt_open > cand_sl + 0.5) or (sig_dir == -1 and nxt_open < cand_sl - 0.5):
                                curr_sl = max(curr_sl, cand_sl) if sig_dir == 1 else min(curr_sl, cand_sl)
                                be_active = True
                        opened_intrabar = False
                    else:
                        bars_held += 1
                        fav = (bh - avg_price) if sig_dir == 1 else (avg_price - bl)
                        if fav > max_fav:
                            max_fav = fav

                        if be_trig > 0.0 and not be_active and max_fav >= be_trig:
                            if be_mode in ("BE_WALL_SHIELD", "BE_WALL_2STAGE") and def_wall > 0:
                                cand_sl = round05(def_wall - wall_shield_buf) if sig_dir == 1 else round05(def_wall + wall_shield_buf)
                            else:
                                cand_sl = round05(avg_price + be_lock) if sig_dir == 1 else round05(avg_price - be_lock)
                            if (sig_dir == 1 and nxt_open > cand_sl + 0.5) or (sig_dir == -1 and nxt_open < cand_sl - 0.5):
                                curr_sl = max(curr_sl, cand_sl) if sig_dir == 1 else min(curr_sl, cand_sl)
                                be_active = True

                        if be_mode == "BE_WALL_2STAGE" and max_fav >= max(11.5, be_trig + 4.5):
                            cand_sl2 = round05(avg_price + 2.5) if sig_dir == 1 else round05(avg_price - 2.5)
                            if (sig_dir == 1 and nxt_open > cand_sl2 + 0.5) or (sig_dir == -1 and nxt_open < cand_sl2 - 0.5):
                                curr_sl = max(curr_sl, cand_sl2) if sig_dir == 1 else min(curr_sl, cand_sl2)

                        if tr_trig > 0.0 and max_fav >= tr_trig:
                            cand_sl = round05(avg_price + max_fav - tr_dist) if sig_dir == 1 else round05(avg_price - max_fav + tr_dist)
                            if (sig_dir == 1 and nxt_open > cand_sl + 0.5) or (sig_dir == -1 and nxt_open < cand_sl - 0.5):
                                curr_sl = max(curr_sl, cand_sl) if sig_dir == 1 else min(curr_sl, cand_sl)

                        if slot_id == 12 and leg_stage == 1 and pyr_trig > 0.0:
                            fav_close = (bc - p1_entry) if sig_dir == 1 else (p1_entry - bc)
                            if fav_close >= pyr_trig:
                                avg_price = round05(0.5 * (p1_entry + nxt_open))
                                lots = 2
                                leg_stage = 2
                                cand_sl = round05(avg_price + pyr_lock) if sig_dir == 1 else round05(avg_price - pyr_lock)
                                if (sig_dir == 1 and nxt_open > cand_sl + 0.5) or (sig_dir == -1 and nxt_open < cand_sl - 0.5):
                                    curr_sl = max(curr_sl, cand_sl) if sig_dir == 1 else min(curr_sl, cand_sl)

                        if slot_id <= 14 and bars_held >= max_hold:
                            exit_px = nxt_open
                            k += 1
                            break
                k += 1

            rem_pnl_pts = rem_weight * (((exit_px - avg_price) * sig_dir) - cost_pts) * lots
            tot_pnl_pts = partial_pnl_pts * lots + rem_pnl_pts
            if touched_zero_after_be and tot_pnl_pts > 2.5:
                wall_saves += 1

            trades.append({
                "date": today_str,
                "slot_id": slot_id,
                "side": sig_dir,
                "contracts": float(lots),
                "pnl_pts": float(tot_pnl_pts),
                "pnl_brl": float(tot_pnl_pts * 10.0),
            })
            idx = max(idx + 1, k + 1)

    stats = {"wall_saves": wall_saves, "partial_hits": partial_hits}
    return trades, stats


def simulate_wdo_structural_pa_setup(
    df: pd.DataFrame,
    gex_by_date: dict,
    n50_c: np.ndarray, n50_u: np.ndarray, n50_l: np.ndarray, n50_s: np.ndarray,
    rsi7s: np.ndarray,
    signal_mode: str = "HYBRID_WALL_NWE",   # "HYBRID_WALL_NWE", "PULLBACK_SLOPE", "GAMMA_WALL_REJ"
    entry_type: str = "STOP_PREV_BAR",      # "STOP_PREV_BAR", "ROLLING_STOP_PREV_BAR", "LIMIT_PREV_BAR"
    entry_off: float = 0.5,
    valid_bars: int = 2,
    sl_init_pts: float = 11.5,
    be_mode: str = "BE_WALL_2STAGE",
    be_trigger_pts: float = 6.5,
    wall_shield_buf: float = 1.5,
    tp_mode: str = "TP_MIDWALL",            # "TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"
    front_run_pts: float = 0.5,
    contracts: float = 2.0,
    cost_pts: float = 0.5,
):
    """
    Simula os Novos Achados Estruturais para o WDO (Price Action Barra[1] + Wall2Stop + Alvo/Parcial nas Walls).
    """
    dates = df["session_date"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values

    trades = []
    wall_saves = 0
    partial_hits = 0

    n = len(df)
    idx = 2

    while idx < n - 1:
        b1_idx = idx - 1
        today_str = dates[idx]
        if today_str < "2026-05-07" or today_str not in gex_by_date or dates[b1_idx] != today_str:
            idx += 1
            continue

        t_m = int(t_mins[b1_idx])
        if t_m < 550 or t_m > 975:
            idx += 1
            continue

        g = gex_by_date[today_str]
        walls = g["walls"]
        all_lvls = g["all_levels"]
        gf = g["gamma_flip"] or 0.0
        if len(all_lvls) == 0:
            idx += 1
            continue

        b1_o, b1_h, b1_l, b1_c = opens[b1_idx], highs[b1_idx], lows[b1_idx], closes[b1_idx]
        d_l, lvl_s = find_nearest_level(all_lvls, b1_l)
        d_h, lvl_r = find_nearest_level(all_lvls, b1_h)

        bw50 = max(1.0, n50_u[b1_idx] - n50_l[b1_idx])
        pos50 = (b1_c - n50_l[b1_idx]) / bw50
        s50 = n50_s[b1_idx]

        sig_dir = 0
        def_wall = 0.0

        if signal_mode == "HYBRID_WALL_NWE":
            if d_l <= 3.5 and pos50 <= 0.32 and b1_c >= lvl_s - 1.0 and (gf <= 0.0 or b1_c < gf + 8.0):
                sig_dir, def_wall = 1, lvl_s
            elif d_h <= 3.5 and pos50 >= 0.68 and b1_c <= lvl_r + 1.0 and (gf <= 0.0 or b1_c > gf - 8.0):
                sig_dir, def_wall = -1, lvl_r
        elif signal_mode == "PULLBACK_SLOPE":
            if d_l <= 3.5 and s50 > 0.08 and pos50 <= 0.55 and b1_c >= lvl_s - 0.5:
                sig_dir, def_wall = 1, lvl_s
            elif d_h <= 3.5 and s50 < -0.08 and pos50 >= 0.45 and b1_c <= lvl_r + 0.5:
                sig_dir, def_wall = -1, lvl_r
        elif signal_mode == "GAMMA_WALL_REJ":
            if d_l <= 3.0 and pos50 <= 0.36 and b1_c > b1_o and (gf <= 0.0 or b1_c < gf):
                sig_dir, def_wall = 1, lvl_s
            elif d_h <= 3.0 and pos50 >= 0.64 and b1_c < b1_o and (gf <= 0.0 or b1_c > gf):
                sig_dir, def_wall = -1, lvl_r

        if sig_dir == 0:
            idx += 1
            continue

        # Try entry across valid_bars
        filled = False
        fill_bar = idx
        entry_px = 0.0
        for vb in range(valid_bars):
            eb = idx + vb
            if eb >= n or dates[eb] != today_str or int(t_mins[eb]) >= 1005:
                break
            ref_idx = eb - 1 if (entry_type == "ROLLING_STOP_PREV_BAR" and vb > 0) else b1_idx
            rh, rl = highs[ref_idx], lows[ref_idx]

            if entry_type in ("STOP_PREV_BAR", "ROLLING_STOP_PREV_BAR"):
                ord_p = round05(rh + entry_off) if sig_dir == 1 else round05(rl - entry_off)
                if sig_dir == 1 and opens[eb] <= ord_p and highs[eb] >= ord_p:
                    filled, fill_bar, entry_px = True, eb, ord_p
                    break
                elif sig_dir == -1 and opens[eb] >= ord_p and lows[eb] <= ord_p:
                    filled, fill_bar, entry_px = True, eb, ord_p
                    break
            elif entry_type == "LIMIT_PREV_BAR":
                ord_p = round05(rl + entry_off) if sig_dir == 1 else round05(rh - entry_off)
                if sig_dir == 1 and opens[eb] >= ord_p and lows[eb] <= ord_p:
                    filled, fill_bar, entry_px = True, eb, ord_p
                    break
                elif sig_dir == -1 and opens[eb] <= ord_p and highs[eb] >= ord_p:
                    filled, fill_bar, entry_px = True, eb, ord_p
                    break

        if not filled:
            idx += 1
            continue

        curr_sl = round05(entry_px - sl_init_pts) if sig_dir == 1 else round05(entry_px + sl_init_pts)
        tp_mid_px, tp_main_px, _, _ = find_wdo_structural_targets(entry_px, sig_dir, walls, all_lvls, front_run_pts)
        curr_tp = tp_mid_px if tp_mode == "TP_MIDWALL" else tp_main_px

        max_fav = 0.0
        be_active = False
        partial_done = False
        partial_pnl = 0.0
        rem_w = 1.0
        k = fill_bar
        exit_px = closes[fill_bar]
        bars_held = 0

        while k < n:
            if dates[k] != today_str or int(t_mins[k]) >= 1035:
                exit_px = opens[k] if dates[k] == today_str else closes[k - 1]
                break
            bh, bl, bc = highs[k], lows[k], closes[k]

            if sig_dir == 1:
                if bl <= curr_sl:
                    exit_px = curr_sl
                    break
                if tp_mode == "TP_PARTIAL_WALLS" and not partial_done and bh >= tp_mid_px:
                    partial_done = True
                    partial_hits += 1
                    partial_pnl = 0.5 * ((tp_mid_px - entry_px) - cost_pts)
                    rem_w = 0.5
                    curr_sl = max(curr_sl, round05(def_wall - wall_shield_buf))
                    be_active = True
                if bh >= curr_tp:
                    exit_px = curr_tp
                    break
            else:
                if bh >= curr_sl:
                    exit_px = curr_sl
                    break
                if tp_mode == "TP_PARTIAL_WALLS" and not partial_done and bl <= tp_mid_px:
                    partial_done = True
                    partial_hits += 1
                    partial_pnl = 0.5 * ((entry_px - tp_mid_px) - cost_pts)
                    rem_w = 0.5
                    curr_sl = min(curr_sl, round05(def_wall + wall_shield_buf))
                    be_active = True
                if bl <= curr_tp:
                    exit_px = curr_tp
                    break

            bars_held += 1
            fav = (bh - entry_px) if sig_dir == 1 else (entry_px - bl)
            if fav > max_fav:
                max_fav = fav

            if k + 1 < n and dates[k + 1] == today_str:
                nxt_open = opens[k + 1]
                if not be_active and max_fav >= be_trigger_pts:
                    cand_sl = round05(def_wall - wall_shield_buf) if sig_dir == 1 else round05(def_wall + wall_shield_buf)
                    if (sig_dir == 1 and nxt_open > cand_sl + 0.5) or (sig_dir == -1 and nxt_open < cand_sl - 0.5):
                        curr_sl = max(curr_sl, cand_sl) if sig_dir == 1 else min(curr_sl, cand_sl)
                        be_active = True
                if be_mode == "BE_WALL_2STAGE" and max_fav >= be_trigger_pts + 5.0:
                    cand_sl2 = round05(entry_px + 2.5) if sig_dir == 1 else round05(entry_px - 2.5)
                    if (sig_dir == 1 and nxt_open > cand_sl2 + 0.5) or (sig_dir == -1 and nxt_open < cand_sl2 - 0.5):
                        curr_sl = max(curr_sl, cand_sl2) if sig_dir == 1 else min(curr_sl, cand_sl2)
                if max_fav >= 13.5:
                    cand_tr = round05(entry_px + max_fav - 5.0) if sig_dir == 1 else round05(entry_px - max_fav + 5.0)
                    if (sig_dir == 1 and nxt_open > cand_tr + 0.5) or (sig_dir == -1 and nxt_open < cand_tr - 0.5):
                        curr_sl = max(curr_sl, cand_tr) if sig_dir == 1 else min(curr_sl, cand_tr)
                if bars_held >= 16:
                    exit_px = nxt_open
                    k += 1
                    break
            k += 1

        tot_pts = (partial_pnl + rem_w * (((exit_px - entry_px) * sig_dir) - cost_pts)) * contracts
        trades.append({
            "date": today_str,
            "slot_id": 99,
            "side": sig_dir,
            "contracts": float(contracts),
            "pnl_pts": float(tot_pts),
            "pnl_brl": float(tot_pts * 10.0),
        })
        idx = max(idx + 1, k + 1)

    return trades, {"wall_saves": wall_saves, "partial_hits": partial_hits}


def calc_wdo_summary(trades_list: list, stats: dict, label: str = "") -> dict:
    if not trades_list:
        return {
            "Config": label, "Trades": 0, "WinRate": 0.0, "PF": 0.0,
            "NetPts": 0.0, "NetBRL": 0.0, "MaxDD_BRL": 0.0, "Ret_DD": 0.0, "Sharpe": 0.0,
            "WallSaves": 0, "PartialHits": 0,
        }
    df_t = pd.DataFrame(trades_list)
    n_tr = len(df_t)
    wins = (df_t["pnl_brl"] > 0).sum()
    wr = 100.0 * wins / n_tr
    gross_win = df_t.loc[df_t["pnl_brl"] > 0, "pnl_brl"].sum()
    gross_loss = abs(df_t.loc[df_t["pnl_brl"] < 0, "pnl_brl"].sum())
    pf = gross_win / gross_loss if gross_loss > 1e-6 else 99.9
    net_pts = df_t["pnl_pts"].sum()
    net_brl = df_t["pnl_brl"].sum()

    # Daily equity curve for realistic MaxDD and Sharpe
    daily = df_t.groupby("date")["pnl_brl"].sum()
    cum = daily.cumsum()
    peak = cum.cummax().clip(lower=0.0)
    dd_daily = (peak - cum).max()

    # Trade-by-trade DD as well (take max of daily DD and trade DD for strictness)
    cum_tr = df_t["pnl_brl"].cumsum()
    peak_tr = cum_tr.cummax().clip(lower=0.0)
    dd_tr = (peak_tr - cum_tr).max()
    max_dd = max(float(dd_daily), float(dd_tr), 1.0)

    ret_dd = net_brl / max_dd if max_dd > 0 else 0.0
    std_d = daily.std()
    sharpe = (daily.mean() / std_d) * np.sqrt(252) if std_d and std_d > 1e-6 else 0.0

    return {
        "Config": label,
        "Trades": int(n_tr),
        "WinRate": round(wr, 1),
        "PF": round(pf, 2),
        "NetPts": round(net_pts, 1),
        "NetBRL": round(net_brl, 2),
        "MaxDD_BRL": round(max_dd, 2),
        "Ret_DD": round(ret_dd, 2),
        "Sharpe": round(sharpe, 2),
        "WallSaves": stats.get("wall_saves", 0),
        "PartialHits": stats.get("partial_hits", 0),
    }


def main():
    t0 = time.time()
    print("[1/4] Carregando 122 pregoes sincronizados de WDO$N + WIN$N + jumba_gex_wdo_history.csv...")
    df, gex_by_date = load_wdo_and_win_aligned()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    print(f"      Barras M5 WDO$N: {len(df)} | Sessoes GEX WDO: {len(gex_by_date)}")

    # 1. Avalia Baseline e Otimizacao 3 Pilares para cada WDO-01..16
    print("[2/4] Auditando Baseline e Otimizando os 3 Pilares Estruturais em cada WDO-01..16...")
    baseline_trades_by_slot = {}
    baseline_metrics_by_slot = {}
    best_3p_full_by_slot = {}
    best_3p_part_by_slot = {}

    entry_modes = ["CURRENT", "STOP_B1_EXT", "LIMIT_B1_EXT", "LIMIT_B1_MID"]
    be_modes = [
        ("BE_ZERO", 0.0),
        ("BE_WALL_SHIELD", 1.0),
        ("BE_WALL_SHIELD", 1.5),
        ("BE_WALL_SHIELD", 2.0),
        ("BE_WALL_2STAGE", 1.0),
        ("BE_WALL_2STAGE", 1.5),
    ]
    tp_modes_full = ["TP_CURRENT", "TP_MIDWALL", "TP_MAIN_WALL"]

    comparison_rows = []

    for sid in range(1, 17):
        tr_base, st_base = simulate_single_wdo_slot(
            sid, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode="BE_ZERO", wall_shield_buf=0.0, tp_mode="TP_CURRENT"
        )
        m_base = calc_wdo_summary(tr_base, st_base, f"{WDO_NAMES[sid]} [BASELINE]")
        baseline_trades_by_slot[sid] = tr_base
        baseline_metrics_by_slot[sid] = m_base

        best_full_m = m_base
        best_full_tr = tr_base
        best_full_st = st_base
        best_full_cfg = ("CURRENT", "BE_ZERO", 0.0, "TP_CURRENT")

        # Grid search for best 3-Pillar config on slot `sid`
        e_list = ["CURRENT"] if sid in (11, 13, 14) else entry_modes
        for em in e_list:
            for bm, buf in be_modes:
                for tm in tp_modes_full:
                    if em == "CURRENT" and bm == "BE_ZERO" and tm == "TP_CURRENT":
                        continue
                    tr_c, st_c = simulate_single_wdo_slot(
                        sid, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
                        entry_override=em, be_mode=bm, wall_shield_buf=buf, tp_mode=tm
                    )
                    m_c = calc_wdo_summary(tr_c, st_c, f"{em}|{bm}({buf})|{tm}")
                    if m_c["Trades"] >= max(15, int(0.45 * m_base["Trades"])):
                        # Score prioritizes Ret/DD while ensuring NetBRL >= 92% of baseline (or > baseline if baseline < 0)
                        if m_c["Ret_DD"] > best_full_m["Ret_DD"] and m_c["NetBRL"] >= min(m_base["NetBRL"] * 0.92, m_base["NetBRL"] + 500.0):
                            best_full_m = m_c
                            best_full_tr = tr_c
                            best_full_st = st_c
                            best_full_cfg = (em, bm, buf, tm)

        best_3p_full_by_slot[sid] = (best_full_cfg, best_full_m, best_full_tr, best_full_st)

        # Also test Partial Exit (50% MidWall + 50% MainWall) on the champion config
        em_b, bm_b, buf_b, _ = best_full_cfg
        tr_part, st_part = simulate_single_wdo_slot(
            sid, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override=em_b, be_mode=bm_b if bm_b != "BE_ZERO" else "BE_WALL_SHIELD",
            wall_shield_buf=buf_b if buf_b > 0 else 1.5, tp_mode="TP_PARTIAL_WALLS"
        )
        m_part = calc_wdo_summary(tr_part, st_part, f"{em_b}|PARTIAL_MID_MAIN")
        best_3p_part_by_slot[sid] = (m_part, tr_part, st_part)

        comparison_rows.append({
            "Slot": f"WDO-{sid:02d}",
            "Nome": WDO_NAMES[sid],
            "Base_Tr": m_base["Trades"],
            "Base_BRL": m_base["NetBRL"],
            "Base_DD": m_base["MaxDD_BRL"],
            "Base_PF": m_base["PF"],
            "Base_RetDD": m_base["Ret_DD"],
            "Opt3P_Tr": best_full_m["Trades"],
            "Opt3P_BRL": best_full_m["NetBRL"],
            "Opt3P_DD": best_full_m["MaxDD_BRL"],
            "Opt3P_PF": best_full_m["PF"],
            "Opt3P_RetDD": best_full_m["Ret_DD"],
            "Opt3P_Cfg": f"{best_full_cfg[0]} | {best_full_cfg[1]}({best_full_cfg[2]}) | {best_full_cfg[3]}",
            "Part_BRL": m_part["NetBRL"],
            "Part_DD": m_part["MaxDD_BRL"],
            "Part_RetDD": m_part["Ret_DD"],
        })

    df_comp = pd.DataFrame(comparison_rows)
    df_comp.to_csv(os.path.join(OUT_DIR, "wdo_16_individual_comparison.csv"), index=False)

    # 2. Descobre e avalia os 4 Novos Achados Estruturais do WDO (2 Contratos = 1+1 p/ Parcial)
    print("[3/4] Avaliando os Novos Achados Estruturais do WDO (Price Action Barra[1] + Wall2Stop + Walls)...")
    pa_candidates = []
    for sm in ["HYBRID_WALL_NWE", "PULLBACK_SLOPE", "GAMMA_WALL_REJ"]:
        for et in ["STOP_PREV_BAR", "ROLLING_STOP_PREV_BAR", "LIMIT_PREV_BAR"]:
            for vb in [1, 2]:
                for bm, buf in [("BE_WALL_SHIELD", 1.5), ("BE_WALL_2STAGE", 1.5)]:
                    for tm in ["TP_MIDWALL", "TP_MAIN_WALL", "TP_PARTIAL_WALLS"]:
                        tr_pa, st_pa = simulate_wdo_structural_pa_setup(
                            df, gex_by_date, n50_c, n50_u, n50_l, n50_s, rsi7s,
                            signal_mode=sm, entry_type=et, entry_off=0.5, valid_bars=vb,
                            sl_init_pts=11.5, be_mode=bm, be_trigger_pts=6.5, wall_shield_buf=buf,
                            tp_mode=tm, front_run_pts=0.5, contracts=2.0
                        )
                        desc_pa = f"NOVO_WDO({sm}|{et}_vb{vb}|{bm}({buf})|{tm})"
                        m_pa = calc_wdo_summary(tr_pa, st_pa, desc_pa)
                        if m_pa["Trades"] >= 35 and m_pa["NetBRL"] > 2000:
                            pa_candidates.append((desc_pa, m_pa, tr_pa, st_pa, (sm, et, vb, bm, buf, tm)))

    # Sort PA candidates by Ret_DD descending, pick Top 4 diverse setups
    pa_candidates.sort(key=lambda x: (x[1]["Ret_DD"], x[1]["NetBRL"]), reverse=True)
    top_4_pa = []
    used_keys = set()
    for item in pa_candidates:
        sm, et, vb, bm, buf, tm = item[4]
        key = (sm, et, tm)
        if key not in used_keys:
            used_keys.add(key)
            top_4_pa.append(item)
        if len(top_4_pa) == 4:
            break

    print("\nTOP 4 NOVOS ACHADOS ESTRUTURAIS DO WDO (2 CONTRATOS):")
    for idx_pa, (d_pa, m_pa, _, _, _) in enumerate(top_4_pa, 1):
        print(f"  #{idx_pa}: {d_pa} -> Trades={m_pa['Trades']} | Net=R$ {m_pa['NetBRL']:.2f} | DD=R$ {m_pa['MaxDD_BRL']:.2f} | PF={m_pa['PF']:.2f} | Ret/DD={m_pa['Ret_DD']:.2f}")

    # 3. Constrói os 4 Estágios do Portfólio WDO e a Seleção Estrita do MIX CAMPEÃO
    print("\n[4/4] Construindo Comparativo dos 4 Estagios do Portfolio WDO e Selecao Estrita Vaga a Vaga...")
    # Identify the 4 weakest slots by Baseline Ret/DD
    sorted_slots_by_retdd = sorted(range(1, 17), key=lambda s: baseline_metrics_by_slot[s]["Ret_DD"])
    weakest_4_slots = sorted_slots_by_retdd[:4]
    weakest_str = [f"WDO-{s:02d} (Ret/DD={baseline_metrics_by_slot[s]['Ret_DD']})" for s in weakest_4_slots]
    print(f"      4 vagas de menor Ret/DD no WDO Atual: {weakest_str}")

    port_1_legacy = []
    port_2_pure_swap = []
    port_3_opt3p_full = []
    port_3b_opt3p_part = []
    port_4_best_mix = []

    mix_selection_rows = []

    for sid in range(1, 17):
        tr_base = baseline_trades_by_slot[sid]
        m_base = baseline_metrics_by_slot[sid]
        cfg_3p, m_3p, tr_3p, _ = best_3p_full_by_slot[sid]
        m_part, tr_part, _ = best_3p_part_by_slot[sid]

        port_1_legacy.extend(tr_base)
        port_3_opt3p_full.extend(tr_3p)
        port_3b_opt3p_part.extend(tr_part if m_part["Ret_DD"] >= m_3p["Ret_DD"] else tr_3p)

        if sid in weakest_4_slots:
            w_idx = weakest_4_slots.index(sid)
            pa_desc, pa_m, pa_tr, _, _ = top_4_pa[w_idx]
            port_2_pure_swap.extend(pa_tr)
        else:
            port_2_pure_swap.extend(tr_base)

        # Strict Mix Selection for slot `sid`: highest Ret/DD among Original, 3P Full, 3P Partial, and (if in weakest_4_slots) New PA Finding
        cands = [
            ("MANTIDO ORIGINAL", m_base, tr_base),
            (f"3-Pilares ({cfg_3p[0]}|{cfg_3p[1]}({cfg_3p[2]})|{cfg_3p[3]})", m_3p, tr_3p),
            (f"3-Pilares c/ Parcial ({cfg_3p[0]}|PARTIAL_MID_MAIN)", m_part, tr_part),
        ]
        if sid in weakest_4_slots:
            w_idx = weakest_4_slots.index(sid)
            pa_desc, pa_m, pa_tr, _, _ = top_4_pa[w_idx]
            cands.append((pa_desc, pa_m, pa_tr))

        best_lbl, best_m, best_tr = max(cands, key=lambda c: c[1]["Ret_DD"])
        port_4_best_mix.extend(best_tr)

        mix_selection_rows.append({
            "Slot": f"WDO-{sid:02d}",
            "Nome": WDO_NAMES[sid],
            "Orig_Tr": m_base["Trades"],
            "Orig_BRL": m_base["NetBRL"],
            "Orig_DD": m_base["MaxDD_BRL"],
            "Orig_PF": m_base["PF"],
            "Orig_RetDD": m_base["Ret_DD"],
            "Opt3P_RetDD": m_3p["Ret_DD"],
            "Part_RetDD": m_part["Ret_DD"],
            "MIX_Tr": best_m["Trades"],
            "MIX_BRL": best_m["NetBRL"],
            "MIX_DD": best_m["MaxDD_BRL"],
            "MIX_PF": best_m["PF"],
            "MIX_RetDD": best_m["Ret_DD"],
            "Decisao_Estrita": best_lbl,
        })

    df_mix_sel = pd.DataFrame(mix_selection_rows)
    df_mix_sel.to_csv(os.path.join(OUT_DIR, "wdo_16_best_mix_selection.csv"), index=False)

    p1 = calc_wdo_summary(sorted(port_1_legacy, key=lambda x: x["date"]), {}, "1. ATUAL LEGACY (WDO-01..16 Sem Alteracao)")
    p2 = calc_wdo_summary(sorted(port_2_pure_swap, key=lambda x: x["date"]), {}, "2. TROCA PURA ANTES DA OTIMIZACAO (Troca das 4 piores vagas pelos Novos Achados)")
    p3 = calc_wdo_summary(sorted(port_3_opt3p_full, key=lambda x: x["date"]), {}, "3A. OTIMIZADO 3-PILARES (WDO-01..16 Alvo Cheio nas Walls)")
    p3b = calc_wdo_summary(sorted(port_3b_opt3p_part, key=lambda x: x["date"]), {}, "3B. OTIMIZADO 3-PILARES + SAIDA PARCIAL 50% MID / 50% MAIN")
    p4 = calc_wdo_summary(sorted(port_4_best_mix, key=lambda x: x["date"]), {}, "4. MIX CAMPEAO WDO (Maior Ret/DD estrito em cada vaga)")

    df_ports = pd.DataFrame([p1, p2, p3, p3b, p4])
    df_ports.to_csv(os.path.join(OUT_DIR, "wdo_portfolio_stages_comparison.csv"), index=False)

    print("\n" + "=" * 130)
    print("DIAGNOSTICO E SELECAO VAGA A VAGA DO DOLAR (WDO-01 A WDO-16):")
    print("=" * 130)
    print(df_mix_sel.to_string(index=False))

    print("\n" + "=" * 130)
    print("COMPARATIVO CONSOLIDADO DOS ESTAGIOS DO PORTFOLIO DO DOLAR (122 PREGOES):")
    print("=" * 130)
    print(df_ports[["Config", "Trades", "WinRate", "PF", "NetPts", "NetBRL", "MaxDD_BRL", "Ret_DD", "Sharpe"]].to_string(index=False))
    print("=" * 130)
    print(f"Concluido em {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
