"""
Simulador Python 100% alinhado ao MT5 Strategy Tester para o Dólar (WDO-01 a WDO-16).
Porta fielmente `mt5/Include/Jumba_WDO_GEX_NWE_Core.mqh` sobre os dados do terminal MT5
(`data/mt5_rates/mt5_WDO_N_M5.csv`, `mt5_WIN_N_M5.csv` e `mt5/Files/jumba_gex_wdo_history.csv`).
"""
import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_gex_nwe_setups import compute_nwe_series
from research.mt5_loader import get_mt5_rates, HIST_WDO

# As 7 estratégias ativas por padrão em `Jumba_WDO_GEX_NWE_Core.mqh` (Init lines 202-207)
ACTIVE_7_WDO = [2, 6, 7, 9, 10, 11, 15]
# As 4 estratégias com código em OnNewM5Bar mas desativadas em Init (<100 trades)
CANDIDATE_4_WDO = [3, 4, 8, 16]
# As 5 estratégias desativadas via `if(false && ...)` (clones no Walk-Forward)
CLONE_5_WDO = [1, 5, 12, 13, 14]

WDO_SLOT_NAMES = {
    1:  "WDO-01 [Clone WDO-07] Scalper Hibrido NY",
    2:  "WDO-02 [3Pil LimB1+2St+MidW] CORE",
    3:  "WDO-03 [<100tr] Arb WIN+WDO MainWall",
    4:  "WDO-04 [<100tr] MainWall GammaFlip",
    5:  "WDO-05 [Clone WDO-02] Cluster NWE30+50",
    6:  "WDO-06 [WF BrenoWick+MainW+Lim50%B1]",
    7:  "WDO-07 [3Pil BE_Wall+MidW] Absorcao NY",
    8:  "WDO-08 [<100tr] Abs MainWall+Gamma",
    9:  "WDO-09 [NOVO Cluster+LimWall] NWE30+50",
    10: "WDO-10 [WDO_S2 Reversao NWE 12-14h30]",
    11: "WDO-11 [SmartGrid GF+NextWall 1+2L]",
    12: "WDO-12 [Clone] Piramidacao 1+1L NY",
    13: "WDO-13 [Clone] SmartGrid 1+2L GF",
    14: "WDO-14 [Clone] Grid 1+2+3L Inst",
    15: "WDO-15 [MainWall Z30_Rev070+CandleShield]",
    16: "WDO-16 [<100tr] MainWall EOD",
}


def round05(val: float) -> float:
    return float(np.floor(val * 2.0 + 0.5) / 2.0) if val >= 0 else float(np.ceil(val * 2.0 - 0.5) / 2.0)


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


def find_nearest_level(levels: np.ndarray, price: float):
    if len(levels) == 0:
        return 999999.0, 0.0
    diffs = np.abs(levels - price)
    idx = int(np.argmin(diffs))
    return float(diffs[idx]), float(levels[idx])


def find_wdo_structural_targets(entry_px: float, side: int, walls: np.ndarray, all_lvls: np.ndarray, front_run: float = 0.5):
    """Port exato de FindWdoStructuralTargets (linhas 1097-1186 de Jumba_WDO_GEX_NWE_Core.mqh)."""
    n_all = len(all_lvls)
    n_walls = len(walls)
    raw_mid = 0.0
    raw_main = 0.0

    if side == 1:
        mid_idx_all = -1
        for i in range(n_all):
            if all_lvls[i] >= entry_px + 7.5:
                raw_mid = float(all_lvls[i])
                mid_idx_all = i
                break
        if raw_mid <= 0.0:
            raw_mid = entry_px + 18.0

        for i in range(n_walls):
            if walls[i] >= entry_px + 14.0:
                raw_main = float(walls[i])
                break
        if raw_main > 0.0:
            if raw_main <= raw_mid + 3.5:
                if mid_idx_all >= 0 and (mid_idx_all + 1) < n_all:
                    raw_main = float(all_lvls[mid_idx_all + 1])
                else:
                    raw_main = raw_mid + 16.0
        elif mid_idx_all >= 0 and (mid_idx_all + 1) < n_all:
            raw_main = float(all_lvls[mid_idx_all + 1])
        else:
            raw_main = raw_mid + 16.0

        tp_mid_px = round05(raw_mid - front_run)
        tp_main_px = round05(raw_main - front_run)
    else:
        mid_idx_all = -1
        for i in range(n_all - 1, -1, -1):
            if all_lvls[i] <= entry_px - 7.5:
                raw_mid = float(all_lvls[i])
                mid_idx_all = i
                break
        if raw_mid <= 0.0:
            raw_mid = entry_px - 18.0

        for i in range(n_walls - 1, -1, -1):
            if walls[i] <= entry_px - 14.0:
                raw_main = float(walls[i])
                break
        if raw_main > 0.0:
            if raw_main >= raw_mid - 3.5:
                if mid_idx_all > 0:
                    raw_main = float(all_lvls[mid_idx_all - 1])
                else:
                    raw_main = raw_mid - 16.0
        elif mid_idx_all > 0:
            raw_main = float(all_lvls[mid_idx_all - 1])
        else:
            raw_main = raw_mid - 16.0

        tp_mid_px = round05(raw_mid + front_run)
        tp_main_px = round05(raw_main + front_run)

    return tp_mid_px, tp_main_px


def calc_wdo_target_pts(entry_px: float, side: int, tp_type: int, orig_tp_pts: float, walls: np.ndarray, all_lvls: np.ndarray, front_run: float = 0.5) -> float:
    """Port exato de CalcWdoTargetPts (linhas 1188-1197 de Jumba_WDO_GEX_NWE_Core.mqh)."""
    if tp_type == 0:
        return orig_tp_pts
    tp_mid, tp_main = find_wdo_structural_targets(entry_px, side, walls, all_lvls, front_run)
    target_px = tp_mid if tp_type == 1 else tp_main
    pts = abs(target_px - entry_px)
    return max(7.0, round05(pts))


def find_wdo_next_wall_behind(entry_px: float, d: int, all_lvls: np.ndarray, min_d: float = 8.0, max_d: float = 16.0, fallback_d: float = 11.0) -> float:
    """Port exato de FindWdoNextWallBehind (linhas 1210-1232 de Jumba_WDO_GEX_NWE_Core.mqh)."""
    n = len(all_lvls)
    if d == 1:
        for i in range(n - 1, -1, -1):
            dist = entry_px - float(all_lvls[i])
            if min_d <= dist <= max_d:
                return round05(dist)
    else:
        for i in range(n):
            dist = float(all_lvls[i]) - entry_px
            if min_d <= dist <= max_d:
                return round05(dist)
    return round05(fallback_d)


def load_wdo_mt5_raw():
    """Carrega as barras M5 brutas do MT5 para WDO$N e WIN$N (exatamente como CopyRates no MT5)."""
    df_wdo = get_mt5_rates("WDO$N", "M5").copy().reset_index(drop=True)
    df_wdo["session_date"] = df_wdo["t"].dt.strftime("%Y-%m-%d")
    df_wdo["t_min"] = df_wdo["t"].dt.hour * 60 + df_wdo["t"].dt.minute
    df_wdo["unix_ts"] = (df_wdo["t"] - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")

    df_win = get_mt5_rates("WIN$N", "M5")[["t", "close"]].rename(columns={"close": "win_close"}).reset_index(drop=True)
    wc = df_win["win_close"].values
    win_ret3 = np.zeros(len(wc), dtype=float)
    win_z = np.zeros(len(wc), dtype=float)
    rets = np.zeros(len(wc), dtype=float)
    for i in range(1, len(wc)):
        if wc[i - 1] > 0:
            rets[i] = wc[i] / wc[i - 1] - 1.0
    for i in range(24, len(wc)):
        if wc[i - 3] > 0:
            win_ret3[i] = (wc[i] / wc[i - 3] - 1.0) * 10000.0
        window_r = rets[i - 19 : i + 1]
        mean = np.mean(window_r)
        std = np.sqrt(np.mean((window_r - mean) ** 2))
        if std > 1e-9:
            win_z[i] = (rets[i] - mean) / std
    df_win["win_ret3"] = win_ret3
    df_win["win_z"] = win_z

    df_wdo = df_wdo.merge(df_win[["t", "win_ret3", "win_z"]], on="t", how="left")
    df_wdo[["win_ret3", "win_z"]] = df_wdo[["win_ret3", "win_z"]].ffill().fillna(0.0)

    df_csv = pd.read_csv(HIST_WDO, sep=";")
    gex_by_date = {}
    for s_date, grp in df_csv.groupby("session_date"):
        grp_valid = grp[grp["price"].astype(float) > 0.0]
        walls = sorted(grp_valid[grp_valid["type"].isin(["Wall", "wall"])]["price"].astype(float).tolist())
        mid_walls = sorted(grp_valid[grp_valid["type"].isin(["MidWall", "mid_wall"])]["price"].astype(float).tolist())
        gf_rows = grp_valid[grp_valid["type"].isin(["GammaFlip", "gamma_flip"])]["price"].astype(float).tolist()
        maxg_rows = grp_valid[grp_valid["type"].isin(["MaxGamma", "max_gamma"])]["price"].astype(float).tolist()
        ming_rows = grp_valid[grp_valid["type"].isin(["MinGamma", "min_gamma"])]["price"].astype(float).tolist()
        all_lvls = sorted(grp_valid["price"].astype(float).tolist())
        gex_by_date[str(s_date)] = {
            "walls": np.array(walls, dtype=float),
            "mid_walls": np.array(mid_walls, dtype=float),
            "all_levels": np.array(all_lvls, dtype=float),
            "gamma_flip": gf_rows[-1] if gf_rows else 0.0,
            "max_gamma": maxg_rows[-1] if maxg_rows else 0.0,
            "min_gamma": ming_rows[-1] if ming_rows else 0.0,
        }
    return df_wdo.reset_index(drop=True), gex_by_date


def compute_rsi7_series(closes: np.ndarray) -> np.ndarray:
    """Port exato de ComputeRsi7 (linhas 1023-1046 de Jumba_WDO_GEX_NWE_Core.mqh)."""
    n = len(closes)
    r = np.full(n, 50.0, dtype=float)
    for i in range(8, n):
        gains = 0.0
        losses = 0.0
        for k in range(7):
            d = closes[i - k] - closes[i - k - 1]
            if d > 0.0:
                gains += d
            else:
                losses -= d
        r[i] = (100.0 * gains / (gains + losses)) if (gains + losses > 1e-9) else 50.0
    return r


# Ligado só pelo runner ao vivo (core/setups_runner.py) quando há corte de dados; o BT não muda.
EMIT_OPEN_AT_END = False


def simulate_wdo_core_slot(
    slot_id: int,
    df: pd.DataFrame,
    gex_by_date: dict,
    n50_c: np.ndarray, n50_u: np.ndarray, n50_l: np.ndarray, n50_s: np.ndarray,
    n30_c: np.ndarray, n30_u: np.ndarray, n30_l: np.ndarray, n30_s: np.ndarray,
    rsi7: np.ndarray,
    start_date: str = "2026-05-11",
    end_date: str = "2026-11-04",
    cost_pts: float = 0.0,
    sig_filter=None,
):
    """
    Simula fielmente o slot `slot_id` (1..16) de `Jumba_WDO_GEX_NWE_Core.mqh`.
    Retorna lista de trades fechados com timestamps, preços, lotes, razão e PnL (com e sem custo).

    `sig_filter(date, b1_tmin, dir) -> bool` (opcional): filtro de fluxo/janela do dashboard
    aplicado na barra de sinal b1. Só bloqueia entradas novas (não afeta gestão de posição).
    """
    # [ativo, data_b1, tmin_b1] durante a avaliação de sinais da barra
    _gate = [False, "", 0]
    dates = df["session_date"].values
    ts_arr = df["t"].values
    unix_ts = df["unix_ts"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values
    win_ret3 = df["win_ret3"].values
    win_z = df["win_z"].values

    # Estado do slot (idêntico a SWdoVirtualSlot)
    d_pos = 0
    lots = 0
    leg_stage = 0
    p1_entry = 0.0
    avg_price = 0.0
    curr_sl = 0.0
    curr_tp = 0.0
    max_fav_pts = 0.0
    be_active = False
    be_stage2_active = False
    opened_intrabar = False
    bars_held = 0
    entry_bar_time = 0
    last_entry_bar_time = 0
    last_trade_date = ""

    pend_dir = 0
    pend_type = 0
    pend_price = 0.0
    pend_tp_pts = 0.0
    pend_sl_pts = 0.0
    pend_bar_time = 0
    pend_bars_left = 0
    pend_def_wall = 0.0
    pend_be_mode = 0
    pend_wall_buf = 0.0
    broker_order_active = False

    def_wall = 0.0
    be_mode = 0
    wall_shield_buf = 0.0
    be_trig = 0.0
    be_lock = 0.0
    tr_trig = 0.0
    tr_dist = 0.0
    step2_dist = 0.0
    step3_dist = 0.0
    lot1 = 0
    lot2 = 0
    lot3 = 0
    tp_avg_pts = 0.0
    max_sl_pts = 0.0
    max_hold_bars = 16
    pyr_trig = 0.0
    pyr_lock = 0.0

    loaded_date = ""
    trades_today = 0
    closed_pnl_today_brl = 0.0
    m_levels_all = np.array([], dtype=float)
    m_levels_walls = np.array([], dtype=float)
    m_gamma_flip = 0.0

    trades = []

    def reset_slot():
        nonlocal d_pos, lots, leg_stage, p1_entry, avg_price, curr_sl, curr_tp, max_fav_pts
        nonlocal be_active, be_stage2_active, opened_intrabar, bars_held, entry_bar_time
        nonlocal pend_dir, pend_type, pend_price, pend_tp_pts, pend_sl_pts, pend_bar_time
        nonlocal pend_bars_left, pend_def_wall, pend_be_mode, pend_wall_buf, broker_order_active
        nonlocal def_wall, be_mode, wall_shield_buf, pyr_trig, pyr_lock
        d_pos = 0
        lots = 0
        leg_stage = 0
        p1_entry = 0.0
        avg_price = 0.0
        curr_sl = 0.0
        curr_tp = 0.0
        max_fav_pts = 0.0
        be_active = False
        be_stage2_active = False
        opened_intrabar = False
        bars_held = 0
        entry_bar_time = 0
        pend_dir = 0
        pend_type = 0
        pend_price = 0.0
        pend_tp_pts = 0.0
        pend_sl_pts = 0.0
        pend_bar_time = 0
        pend_bars_left = 0
        pend_def_wall = 0.0
        pend_be_mode = 0
        pend_wall_buf = 0.0
        broker_order_active = False
        def_wall = 0.0
        be_mode = 0
        wall_shield_buf = 0.0
        pyr_trig = 0.0
        pyr_lock = 0.0

    def calc_stage1_stop() -> float:
        if (be_mode == 1 or be_mode == 2) and def_wall > 0.0:
            buf = wall_shield_buf if wall_shield_buf > 0.0 else 1.5
            return round05(def_wall - buf) if d_pos == 1 else round05(def_wall + buf)
        return round05(avg_price + be_lock) if d_pos == 1 else round05(avg_price - be_lock)

    def open_virtual_single(
        _dir: int, _entry_p: float, _bar_t: int, _tp_pts: float, _sl_pts: float,
        _be_trig: float, _be_lock: float, _tr_trig: float, _tr_dist: float,
        _max_hold: int = 16, _is_intrabar: bool = False,
        _pyr_trig: float = 0.0, _pyr_lock: float = 1.0,
        _def_wall: float = 0.0, _be_mode: int = 0, _wall_buf: float = 0.0
    ):
        nonlocal d_pos, lots, leg_stage, p1_entry, avg_price, curr_sl, curr_tp, max_fav_pts
        nonlocal be_active, be_stage2_active, opened_intrabar, bars_held, entry_bar_time
        nonlocal be_trig, be_lock, tr_trig, tr_dist, max_hold_bars, pyr_trig, pyr_lock
        nonlocal def_wall, be_mode, wall_shield_buf, step2_dist, step3_dist, lot1, lot2, lot3
        nonlocal tp_avg_pts, max_sl_pts, pend_dir, pend_bars_left, broker_order_active
        if _gate[0] and sig_filter is not None and not sig_filter(_gate[1], _gate[2], _dir):
            return
        p05 = round05(_entry_p)
        d_pos = _dir
        lots = 1
        leg_stage = 1
        p1_entry = p05
        avg_price = p05
        curr_sl = round05(p05 - _sl_pts) if _dir == 1 else round05(p05 + _sl_pts)
        curr_tp = round05(p05 + _tp_pts) if _dir == 1 else round05(p05 - _tp_pts)
        max_fav_pts = 0.0
        be_active = False
        be_stage2_active = False
        opened_intrabar = _is_intrabar
        bars_held = 0
        entry_bar_time = _bar_t
        be_trig = _be_trig
        be_lock = _be_lock
        tr_trig = _tr_trig
        tr_dist = _tr_dist
        max_hold_bars = _max_hold
        pyr_trig = _pyr_trig
        pyr_lock = _pyr_lock
        def_wall = _def_wall
        be_mode = _be_mode
        wall_shield_buf = _wall_buf
        if slot_id == 11:
            s2 = find_wdo_next_wall_behind(p05, _dir, m_levels_all, 8.0, 16.0, 11.0)
            sl2_pts = 7.0
            step2_dist = s2
            step3_dist = 0.0
            lot1 = 1
            lot2 = 2
            lot3 = 0
            tp_avg_pts = 4.5
            max_sl_pts = sl2_pts
            curr_sl = round05(p05 - (s2 + sl2_pts)) if _dir == 1 else round05(p05 + (s2 + sl2_pts))
        pend_dir = 0
        pend_bars_left = 0
        broker_order_active = False

    def open_virtual_grid(
        _dir: int, _entry_p: float, _bar_t: int,
        _step2: float, _step3: float, _l1: int, _l2: int, _l3: int,
        _tp_avg: float, _max_sl: float, _be_trig: float, _be_lock: float = 1.5, _max_hold: int = 26
    ):
        nonlocal d_pos, lots, leg_stage, p1_entry, avg_price, curr_sl, curr_tp, max_fav_pts
        nonlocal be_active, be_stage2_active, opened_intrabar, bars_held, entry_bar_time
        nonlocal step2_dist, step3_dist, lot1, lot2, lot3, tp_avg_pts, max_sl_pts
        nonlocal be_trig, be_lock, tr_trig, tr_dist, max_hold_bars, pyr_trig
        nonlocal def_wall, be_mode, wall_shield_buf, pend_dir, pend_bars_left, broker_order_active
        if _gate[0] and sig_filter is not None and not sig_filter(_gate[1], _gate[2], _dir):
            return
        p05 = round05(_entry_p)
        d_pos = _dir
        lots = _l1
        leg_stage = 1
        p1_entry = p05
        avg_price = p05
        if _l3 > 0:
            worst_off = (_l2 * _step2 + _l3 * _step3) / float(_l1 + _l2 + _l3)
        elif _l2 > 0:
            worst_off = (_l2 * _step2) / float(_l1 + _l2)
        else:
            worst_off = 0.0
        init_sl_dist = max(_max_sl, worst_off + _max_sl)
        curr_sl = round05(p05 - init_sl_dist) if _dir == 1 else round05(p05 + init_sl_dist)
        p1_tp_pts = calc_wdo_target_pts(p05, _dir, 1, _tp_avg, m_levels_walls, m_levels_all, 0.5)
        curr_tp = round05(p05 + p1_tp_pts) if _dir == 1 else round05(p05 - p1_tp_pts)
        max_fav_pts = 0.0
        be_active = False
        be_stage2_active = False
        opened_intrabar = False
        bars_held = 0
        entry_bar_time = _bar_t
        step2_dist = _step2
        step3_dist = _step3
        lot1 = _l1
        lot2 = _l2
        lot3 = _l3
        tp_avg_pts = _tp_avg
        max_sl_pts = _max_sl
        be_trig = _be_trig
        be_lock = _be_lock
        tr_trig = 0.0
        tr_dist = 0.0
        max_hold_bars = _max_hold
        pyr_trig = 0.0
        def_wall = 0.0
        be_mode = 0
        wall_shield_buf = 0.0
        pend_dir = 0
        pend_bars_left = 0
        broker_order_active = False

    def arm_pending_order(
        _dir: int, _ptype: int, _price: float, _bar_t: int, _new_bar_open: float,
        _tp_pts: float, _sl_pts: float, _be_trig: float, _be_lock: float,
        _tr_trig: float, _tr_dist: float, _max_hold: int = 16,
        _def_wall: float = 0.0, _be_mode: int = 0, _wall_buf: float = 0.0, _valid_bars: int = 1,
        _today_str: str = ""
    ):
        nonlocal pend_dir, pend_type, pend_price, pend_bar_time, pend_tp_pts, pend_sl_pts
        nonlocal be_trig, be_lock, tr_trig, tr_dist, max_hold_bars
        nonlocal pend_def_wall, pend_be_mode, pend_wall_buf, pend_bars_left, broker_order_active
        nonlocal last_entry_bar_time, last_trade_date
        if _gate[0] and sig_filter is not None and not sig_filter(_gate[1], _gate[2], _dir):
            return
        p05 = round05(_price)
        if _ptype == 1 and _dir == 1 and _new_bar_open < p05:
            return
        if _ptype == 1 and _dir == -1 and _new_bar_open > p05:
            return
        if _ptype == 2 and _dir == 1 and _new_bar_open > p05:
            return
        if _ptype == 2 and _dir == -1 and _new_bar_open < p05:
            return

        pend_dir = _dir
        pend_type = _ptype
        pend_price = p05
        pend_bar_time = _bar_t
        pend_tp_pts = _tp_pts
        pend_sl_pts = _sl_pts
        be_trig = _be_trig
        be_lock = _be_lock
        tr_trig = _tr_trig
        tr_dist = _tr_dist
        max_hold_bars = _max_hold
        pend_def_wall = _def_wall
        pend_be_mode = _be_mode
        pend_wall_buf = _wall_buf
        pend_bars_left = _valid_bars

        # Linhas 2568-2582 de Jumba_WDO_GEX_NWE_Core.mqh: preenchimento imediato na abertura se new_bar_open == p05
        if (_ptype == 1 and _dir == 1 and _new_bar_open <= p05) or \
           (_ptype == 1 and _dir == -1 and _new_bar_open >= p05) or \
           (_ptype == 2 and _dir == 1 and _new_bar_open >= p05) or \
           (_ptype == 2 and _dir == -1 and _new_bar_open <= p05):
            pt_save = pyr_trig
            pl_save = pyr_lock
            open_virtual_single(_dir, p05, _bar_t, _tp_pts, _sl_pts, _be_trig, _be_lock, _tr_trig, _tr_dist, _max_hold, True, pt_save, pl_save, _def_wall, _be_mode, _wall_buf)
            last_entry_bar_time = _bar_t
            if slot_id == 16:
                last_trade_date = _today_str
            return

        broker_order_active = True

    def close_virtual_slot(exit_px: float, reason: str, exit_time, today_s: str):
        nonlocal trades_today, closed_pnl_today_brl
        if d_pos == 0:
            return
        raw_pts = (exit_px - avg_price) * d_pos
        net_pts_lot = raw_pts - cost_pts
        pnl_raw_brl = raw_pts * lots * 10.0
        pnl_net_brl = net_pts_lot * lots * 10.0
        closed_pnl_today_brl += pnl_raw_brl
        trades_today += 1
        trades.append({
            "date": today_s,
            "entry_time": pd.Timestamp(entry_bar_time, unit="s"),
            "exit_time": pd.Timestamp(exit_time),
            "slot_id": slot_id,
            "side": int(d_pos),
            "contracts": int(lots),
            "leg_stage": int(leg_stage),
            "avg_px": float(avg_price),
            "exit_px": float(exit_px),
            "sl_last": float(curr_sl),
            "tp_px": float(curr_tp),
            "raw_pts": float(raw_pts * lots),
            "pnl_pts": float(net_pts_lot * lots),
            "pnl_brl_nocost": float(pnl_raw_brl),
            "pnl_brl": float(pnl_net_brl),
            "reason": reason,
        })
        reset_slot()

    n = len(df)
    for idx in range(110, n):
        today_str = str(dates[idx])
        if today_str < start_date or today_str > end_date:
            continue

        new_bar_time = int(unix_ts[idx])
        new_tmin = int(t_mins[idx])
        o0, h0, l0, c0 = float(opens[idx]), float(highs[idx]), float(lows[idx]), float(closes[idx])

        # LoadDailyGexWalls(today_str) no início do dia
        if today_str != loaded_date:
            trades_today = 0
            closed_pnl_today_brl = 0.0
            if today_str in gex_by_date:
                g = gex_by_date[today_str]
                m_levels_all = g["all_levels"]
                m_levels_walls = g["walls"]
                m_gamma_flip = float(g["gamma_flip"] or 0.0)
                loaded_date = today_str
            else:
                m_levels_all = np.array([], dtype=float)
                m_levels_walls = np.array([], dtype=float)
                m_gamma_flip = 0.0

        # EOD 17:15 (t_min >= 1035) em OnTickProcess ANTES de OnNewM5Bar
        if new_tmin >= 1035:
            if pend_dir != 0:
                pend_dir = 0
                pend_bars_left = 0
                broker_order_active = False
            if d_pos != 0:
                close_virtual_slot(o0, "EOD_1715", ts_arr[idx], today_str)
            continue

        # =====================================================================
        # OnNewM5Bar(new_bar_time, today_str)
        # =====================================================================
        if len(m_levels_all) > 0:
            b1_idx = idx - 1
            b1_date = str(dates[b1_idx])
            b1_time = int(unix_ts[b1_idx])
            b1_tmin = int(t_mins[b1_idx])
            b1_o, b1_h, b1_l, b1_c = float(opens[b1_idx]), float(highs[b1_idx]), float(lows[b1_idx]), float(closes[b1_idx])
            new_bar_open = o0

            # 1. Gerencia ordens pendentes multi-barra
            if pend_dir != 0:
                pend_bars_left -= 1
                if pend_bars_left <= 0 or b1_date != today_str or new_tmin >= 1005:
                    broker_order_active = False
                    pend_dir = 0
                    pend_bars_left = 0
                else:
                    broker_order_active = False
                    arm_pending_order(
                        pend_dir, pend_type, pend_price, new_bar_time, new_bar_open,
                        pend_tp_pts, pend_sl_pts, be_trig, be_lock,
                        tr_trig, tr_dist, max_hold_bars,
                        pend_def_wall, pend_be_mode, pend_wall_buf,
                        pend_bars_left, today_str
                    )

            # 2. Atualiza BE, Trailing Stop, Piramidação e Time Stop
            if d_pos != 0:
                if opened_intrabar:
                    fav_c = (b1_c - avg_price) if d_pos == 1 else (avg_price - b1_c)
                    if fav_c > max_fav_pts:
                        max_fav_pts = fav_c
                    if be_trig > 0.0 and not be_active and max_fav_pts >= be_trig:
                        cand_sl = calc_stage1_stop()
                        if (d_pos == 1 and new_bar_open > cand_sl + 0.5) or (d_pos == -1 and new_bar_open < cand_sl - 0.5):
                            curr_sl = max(curr_sl, cand_sl) if d_pos == 1 else min(curr_sl, cand_sl)
                            be_active = True
                    if be_mode == 2 and not be_stage2_active and max_fav_pts >= max(11.5, be_trig + 4.5):
                        cand_sl2 = round05(avg_price + 2.5) if d_pos == 1 else round05(avg_price - 2.5)
                        if (d_pos == 1 and new_bar_open > cand_sl2 + 0.5) or (d_pos == -1 and new_bar_open < cand_sl2 - 0.5):
                            curr_sl = max(curr_sl, cand_sl2) if d_pos == 1 else min(curr_sl, cand_sl2)
                            be_stage2_active = True
                            be_active = True
                    opened_intrabar = False
                else:
                    bars_held += 1
                    fav = (b1_h - avg_price) if d_pos == 1 else (avg_price - b1_l)
                    if fav > max_fav_pts:
                        max_fav_pts = fav
                    if be_trig > 0.0 and not be_active and max_fav_pts >= be_trig:
                        cand_sl = calc_stage1_stop()
                        if (d_pos == 1 and new_bar_open > cand_sl + 0.5) or (d_pos == -1 and new_bar_open < cand_sl - 0.5):
                            curr_sl = max(curr_sl, cand_sl) if d_pos == 1 else min(curr_sl, cand_sl)
                            be_active = True
                    if be_mode == 2 and not be_stage2_active and max_fav_pts >= max(11.5, be_trig + 4.5):
                        cand_sl2 = round05(avg_price + 2.5) if d_pos == 1 else round05(avg_price - 2.5)
                        if (d_pos == 1 and new_bar_open > cand_sl2 + 0.5) or (d_pos == -1 and new_bar_open < cand_sl2 - 0.5):
                            curr_sl = max(curr_sl, cand_sl2) if d_pos == 1 else min(curr_sl, cand_sl2)
                            be_stage2_active = True
                            be_active = True
                    if tr_trig > 0.0 and max_fav_pts >= tr_trig:
                        cand_sl = round05(avg_price + max_fav_pts - tr_dist) if d_pos == 1 else round05(avg_price - max_fav_pts + tr_dist)
                        if (d_pos == 1 and new_bar_open > cand_sl + 0.5) or (d_pos == -1 and new_bar_open < cand_sl - 0.5):
                            curr_sl = max(curr_sl, cand_sl) if d_pos == 1 else min(curr_sl, cand_sl)
                    if slot_id == 12 and leg_stage == 1 and pyr_trig > 0.0:
                        fav_close = (b1_c - p1_entry) if d_pos == 1 else (p1_entry - b1_c)
                        if fav_close >= pyr_trig:
                            avg_price = round05(0.5 * (p1_entry + new_bar_open))
                            lots = 2
                            leg_stage = 2
                            cand_sl = round05(avg_price + pyr_lock) if d_pos == 1 else round05(avg_price - pyr_lock)
                            if (d_pos == 1 and new_bar_open > cand_sl + 0.5) or (d_pos == -1 and new_bar_open < cand_sl - 0.5):
                                curr_sl = max(curr_sl, cand_sl) if d_pos == 1 else min(curr_sl, cand_sl)
                    if slot_id <= 15 and bars_held >= max_hold_bars:
                        close_virtual_slot(new_bar_open, "TIME_STOP", ts_arr[idx], today_str)

            # 3. Avaliação de sinais de entrada (apenas se b1_date == today_str)
            _gate[0], _gate[1], _gate[2] = True, str(b1_date), int(b1_tmin)
            if b1_date == today_str and d_pos == 0 and pend_dir == 0:
                d_l, lvl_s = find_nearest_level(m_levels_all, b1_l)
                d_h, lvl_r = find_nearest_level(m_levels_all, b1_h)
                dw_l_main, w_s_main = find_nearest_level(m_levels_walls, b1_l)
                dw_h_main, w_r_main = find_nearest_level(m_levels_walls, b1_h)

                m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1 = float(n50_c[b1_idx]), float(n50_u[b1_idx]), float(n50_l[b1_idx]), float(n50_s[b1_idx])
                m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1 = float(n30_c[b1_idx]), float(n30_u[b1_idx]), float(n30_l[b1_idx]), float(n30_s[b1_idx])
                m_rsi7_1 = float(rsi7[b1_idx])
                m_win_ret3_1 = float(win_ret3[b1_idx])
                m_win_z_1 = float(win_z[b1_idx])

                bw50 = max(1.0, m_n50_u_1 - m_n50_l_1)
                pos50 = (b1_c - m_n50_l_1) / bw50
                bw30 = max(1.0, m_n30_u_1 - m_n30_l_1)
                pos30 = (b1_c - m_n30_l_1) / bw30
                body1 = b1_c - b1_o
                mid_b1 = round05(0.5 * (b1_h + b1_l))

                if slot_id == 1:
                    ent1 = False
                    if last_entry_bar_time != b1_time and window_ok(b1_tmin, "NY_1000_1630"):
                        for lvl in m_levels_all:
                            if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                                tp_calc = min(8.0, max(6.0, calc_wdo_target_pts(new_bar_open, -1, 1, 18.0, m_levels_walls, m_levels_all)))
                                open_virtual_single(-1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), 1, 1.0)
                                last_entry_bar_time = b1_time
                                ent1 = True
                                break
                            if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                                tp_calc = min(8.0, max(6.0, calc_wdo_target_pts(new_bar_open, 1, 1, 18.0, m_levels_walls, m_levels_all)))
                                open_virtual_single(1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), 1, 1.0)
                                last_entry_bar_time = b1_time
                                ent1 = True
                                break
                    if not ent1 and window_ok(new_tmin, "NY_1000_1630"):
                        if pos50 >= 0.65 and d_h <= 3.5 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                            tp_calc = min(8.0, max(6.0, calc_wdo_target_pts(lvl_r, -1, 1, 24.0, m_levels_walls, m_levels_all)))
                            arm_pending_order(-1, 1, lvl_r, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_r, 1, 1.0, 1, today_str)
                        elif pos50 <= 0.35 and d_l <= 3.5 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                            tp_calc = min(8.0, max(6.0, calc_wdo_target_pts(lvl_s, 1, 1, 24.0, m_levels_walls, m_levels_all)))
                            arm_pending_order(1, 1, lvl_s, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.0, 5.5, 16, lvl_s, 1, 1.0, 1, today_str)

                elif slot_id == 2:
                    if bw50 >= 7.15:
                        sig2 = 0
                        wall2, sl2, be2, trt2, trd2, mh2 = 0.0, 13.5, 7.5, 14.5, 5.5, 16
                        if last_entry_bar_time != b1_time and window_ok(b1_tmin, "CORE_09_1615"):
                            for lvl in m_levels_all:
                                if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 2.0):
                                    sig2, wall2, sl2, be2, trt2, trd2, mh2 = -1, float(lvl), 11.0, 6.5, 11.0, 4.5, 15
                                    break
                                if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 2.0):
                                    sig2, wall2, sl2, be2, trt2, trd2, mh2 = 1, float(lvl), 11.0, 6.5, 11.0, 4.5, 15
                                    break
                        if sig2 == 0 and window_ok(new_tmin, "CORE_09_1615"):
                            if pos50 >= 0.64 and d_h <= 3.5 and b1_c < (lvl_r - 0.5) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                                sig2, wall2 = -1, lvl_r
                            elif pos50 <= 0.36 and d_l <= 3.5 and b1_c > (lvl_s + 0.5) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                                sig2, wall2 = 1, lvl_s
                        if sig2 != 0:
                            p2_lim = round05(b1_l + 0.5) if sig2 == 1 else round05(b1_h - 0.5)
                            tp_calc = calc_wdo_target_pts(p2_lim, sig2, 1, 25.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig2, 1, p2_lim, new_bar_time, new_bar_open, tp_calc, sl2, be2, 1.5, trt2, trd2, mh2, wall2, 1, 1.0, 1, today_str)

                elif slot_id == 3:
                    if window_ok(b1_tmin, "CORE_09_1615") and len(m_levels_walls) > 0:
                        sig3, wall3 = 0, 0.0
                        if dw_l_main <= 4.0 and pos50 <= 0.36 and (m_win_ret3_1 <= -5.0 or m_win_z_1 <= -0.8) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 8.0):
                            sig3, wall3 = 1, w_s_main
                        elif dw_h_main <= 4.0 and pos50 >= 0.64 and (m_win_ret3_1 >= 5.0 or m_win_z_1 >= 0.8) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 8.0):
                            sig3, wall3 = -1, w_r_main
                        if sig3 != 0:
                            tp_calc = calc_wdo_target_pts(mid_b1, sig3, 1, 22.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig3, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 13.5, 5.0, 16, wall3, 2, 1.5, 2, today_str)

                elif slot_id == 4:
                    if trades_today < 1 and window_ok(new_tmin, "FULL_09_17") and m_gamma_flip > 0.0 and len(m_levels_walls) > 0:
                        if b1_c > m_gamma_flip + 4.0 and pos50 >= 0.65 and dw_h_main <= 4.0 and b1_c < w_r_main:
                            tp_calc = calc_wdo_target_pts(mid_b1, -1, 2, 25.0, m_levels_walls, m_levels_all)
                            arm_pending_order(-1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 14.0, 7.5, 1.5, 15.0, 5.5, 18, w_r_main, 2, 1.5, 1, today_str)
                        elif b1_c < m_gamma_flip - 4.0 and pos50 <= 0.35 and dw_l_main <= 4.0 and b1_c > w_s_main:
                            tp_calc = calc_wdo_target_pts(mid_b1, 1, 2, 25.0, m_levels_walls, m_levels_all)
                            arm_pending_order(1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 14.0, 7.5, 1.5, 15.0, 5.5, 18, w_s_main, 2, 1.5, 1, today_str)

                elif slot_id == 5:
                    sig5 = 0
                    wall5, sl5, be5, trt5, trd5 = 0.0, 13.5, 7.5, 14.0, 5.5
                    if last_entry_bar_time != b1_time and window_ok(b1_tmin, "CORE_09_1615"):
                        for lvl in m_levels_all:
                            if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n30_s_1 >= 0.15 and m_n50_s_1 >= 0.10 and b1_c < (m_n30_u_1 - bw30 * 0.10):
                                sig5, wall5, sl5, be5, trt5, trd5 = -1, float(lvl), 11.0, 6.5, 11.0, 4.5
                                break
                            if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n30_s_1 <= -0.15 and m_n50_s_1 <= -0.10 and b1_c > (m_n30_l_1 + bw30 * 0.10):
                                sig5, wall5, sl5, be5, trt5, trd5 = 1, float(lvl), 11.0, 6.5, 11.0, 4.5
                                break
                    if sig5 == 0 and window_ok(new_tmin, "CORE_09_1615"):
                        if pos30 >= 0.65 and pos50 >= 0.62 and d_h <= 3.5 and b1_c < lvl_r and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                            sig5, wall5 = -1, lvl_r
                        elif pos30 <= 0.35 and pos50 <= 0.38 and d_l <= 3.5 and b1_c > lvl_s and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                            sig5, wall5 = 1, lvl_s
                    if sig5 != 0:
                        p5_lim = round05(b1_l + 0.5) if sig5 == 1 else round05(b1_h - 0.5)
                        tp_calc = min(9.5, max(7.0, calc_wdo_target_pts(p5_lim, sig5, 1, 24.0, m_levels_walls, m_levels_all)))
                        arm_pending_order(sig5, 1, p5_lim, new_bar_time, new_bar_open, tp_calc, sl5, be5, 1.5, trt5, trd5, 16, wall5, 0, 0.0, 1, today_str)

                elif slot_id == 6:
                    if trades_today < 2 and window_ok(b1_tmin, "CORE_09_1615") and len(m_levels_walls) > 0:
                        sig6, wall6 = 0, 0.0
                        w_bot6 = min(b1_o, b1_c) - b1_l
                        w_top6 = b1_h - max(b1_o, b1_c)
                        if dw_l_main <= 3.0 and w_bot6 >= 2.0 and m_rsi7_1 <= 35.0 and b1_c > b1_o:
                            sig6, wall6 = 1, w_s_main
                        elif dw_h_main <= 3.0 and w_top6 >= 2.0 and m_rsi7_1 >= 65.0 and b1_c < b1_o:
                            sig6, wall6 = -1, w_r_main
                        if sig6 != 0:
                            tp_calc = calc_wdo_target_pts(mid_b1, sig6, 1, 22.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig6, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 12.5, 6.5, 1.5, 14.5, 5.5, 20, wall6, 1, 1.5, 2, today_str)

                elif slot_id == 7:
                    if last_entry_bar_time != b1_time and window_ok(b1_tmin, "NY_1000_1630"):
                        for lvl in m_levels_all:
                            if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                                tp_calc = calc_wdo_target_pts(new_bar_open, -1, 1, 19.0, m_levels_walls, m_levels_all)
                                open_virtual_single(-1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), 1, 1.0)
                                last_entry_bar_time = b1_time
                                break
                            if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                                tp_calc = calc_wdo_target_pts(new_bar_open, 1, 1, 19.0, m_levels_walls, m_levels_all)
                                open_virtual_single(1, new_bar_open, new_bar_time, tp_calc, 11.0, 6.5, 1.5, 11.0, 4.5, 15, False, 0.0, 1.0, float(lvl), 1, 1.0)
                                last_entry_bar_time = b1_time
                                break

                elif slot_id == 8:
                    if window_ok(b1_tmin, "NO_LUNCH") and len(m_levels_walls) > 0:
                        sig8, wall8 = 0, 0.0
                        if dw_l_main <= 3.5 and pos50 <= 0.30 and b1_c > b1_o and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                            sig8, wall8 = 1, w_s_main
                        elif dw_h_main <= 3.5 and pos50 >= 0.70 and b1_c < b1_o and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                            sig8, wall8 = -1, w_r_main
                        if sig8 != 0:
                            tp_calc = calc_wdo_target_pts(mid_b1, sig8, 2, 25.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig8, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 13.5, 5.0, 16, wall8, 2, 1.5, 2, today_str)

                elif slot_id == 9:
                    if trades_today < 2 and window_ok(b1_tmin, "NO_LUNCH") and bw50 >= 7.15:
                        sig9, wall9 = 0, 0.0
                        if d_l <= 5.0 and pos30 <= 0.32 and pos50 <= 0.35 and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 5.0):
                            sig9, wall9 = 1, lvl_s
                        elif d_h <= 5.0 and pos30 >= 0.68 and pos50 >= 0.65 and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 5.0):
                            sig9, wall9 = -1, lvl_r
                        if sig9 != 0:
                            p9_lim = round05(wall9 + 0.5) if sig9 == 1 else round05(wall9 - 0.5)
                            sl9 = max(7.0, min(15.0, round05(abs(p9_lim - wall9) + 2.0)))
                            tp_calc = calc_wdo_target_pts(p9_lim, sig9, 1, 22.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig9, 1, p9_lim, new_bar_time, new_bar_open, tp_calc, sl9, 6.5, 1.5, 13.5, 5.0, 16, wall9, 2, 1.5, 2, today_str)

                elif slot_id == 10:
                    if trades_today < 3 and 720 <= b1_tmin <= 870 and bw50 >= 7.15:
                        if last_entry_bar_time == 0 or (b1_time - last_entry_bar_time) >= 900:
                            mae30_10 = max(1.2, (m_n30_u_1 - m_n30_c_1) / 1.6)
                            pos_nwe30_10 = (b1_c - m_n30_c_1) / mae30_10
                            rng10 = max(0.5, b1_h - b1_l)
                            lw10 = min(b1_o, b1_c) - b1_l
                            uw10 = b1_h - max(b1_o, b1_c)
                            if pos_nwe30_10 <= -0.75 and b1_c >= (b1_l + 0.50 * rng10) and (lw10 >= 0.25 * rng10 or b1_c > b1_o):
                                tp_calc = calc_wdo_target_pts(new_bar_open, 1, 1, 16.0, m_levels_walls, m_levels_all)
                                open_virtual_single(1, new_bar_open, new_bar_time, tp_calc, 10.0, 5.5, 1.0, 0.0, 0.0, 24, False, 0.0, 1.0, b1_l, 1, 1.5)
                                last_entry_bar_time = b1_time
                            elif pos_nwe30_10 >= 0.75 and b1_c <= (b1_h - 0.50 * rng10) and (uw10 >= 0.25 * rng10 or b1_c < b1_o):
                                tp_calc = calc_wdo_target_pts(new_bar_open, -1, 1, 16.0, m_levels_walls, m_levels_all)
                                open_virtual_single(-1, new_bar_open, new_bar_time, tp_calc, 10.0, 5.5, 1.0, 0.0, 0.0, 24, False, 0.0, 1.0, b1_h, 1, 1.5)
                                last_entry_bar_time = b1_time

                elif slot_id == 11:
                    if trades_today < 2 and 545 <= b1_tmin <= 975 and m_gamma_flip > 0.0:
                        sig11, wall11 = 0, 0.0
                        if d_l <= 6.0 and b1_c < (m_gamma_flip - 3.0) and pos50 <= 0.42 and b1_c > b1_o:
                            sig11, wall11 = 1, lvl_s
                        elif d_h <= 6.0 and b1_c > (m_gamma_flip + 3.0) and pos50 >= 0.58 and b1_c < b1_o:
                            sig11, wall11 = -1, lvl_r
                        if sig11 != 0:
                            s2_11 = find_wdo_next_wall_behind(mid_b1, sig11, m_levels_all, 8.0, 16.0, 11.0)
                            tp_calc = calc_wdo_target_pts(mid_b1, sig11, 1, 22.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig11, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, s2_11 + 7.0, 6.0, 1.0, 0.0, 0.0, 20, wall11, 1, 1.0, 2, today_str)

                elif slot_id == 12:
                    ent12 = False
                    if last_entry_bar_time != b1_time and window_ok(b1_tmin, "NY_1000_1630"):
                        for lvl in m_levels_all:
                            if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                                tp_calc = calc_wdo_target_pts(new_bar_open, -1, 2, 24.0, m_levels_walls, m_levels_all)
                                open_virtual_single(-1, new_bar_open, new_bar_time, tp_calc, 12.0, 7.0, 1.5, 13.5, 5.0, 16, False, 8.5, 2.5, float(lvl), 1, 1.5)
                                last_entry_bar_time = b1_time
                                ent12 = True
                                break
                            if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                                tp_calc = calc_wdo_target_pts(new_bar_open, 1, 2, 24.0, m_levels_walls, m_levels_all)
                                open_virtual_single(1, new_bar_open, new_bar_time, tp_calc, 12.0, 7.0, 1.5, 13.5, 5.0, 16, False, 8.5, 2.5, float(lvl), 1, 1.5)
                                last_entry_bar_time = b1_time
                                ent12 = True
                                break
                    if not ent12 and window_ok(new_tmin, "NY_1000_1630") and m_gamma_flip > 0.0:
                        if b1_c > m_gamma_flip + 4.0 and pos50 >= 0.65 and d_h <= 3.5 and b1_c < lvl_r:
                            pyr_trig, pyr_lock = 8.5, 2.5
                            tp_calc = calc_wdo_target_pts(lvl_r, -1, 2, 25.0, m_levels_walls, m_levels_all)
                            arm_pending_order(-1, 1, lvl_r, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_r, 1, 1.5, 1, today_str)
                        elif b1_c < m_gamma_flip - 4.0 and pos50 <= 0.35 and d_l <= 3.5 and b1_c > lvl_s:
                            pyr_trig, pyr_lock = 8.5, 2.5
                            tp_calc = calc_wdo_target_pts(lvl_s, 1, 2, 25.0, m_levels_walls, m_levels_all)
                            arm_pending_order(1, 1, lvl_s, new_bar_time, new_bar_open, tp_calc, 13.5, 7.5, 1.5, 14.5, 5.5, 16, lvl_s, 1, 1.5, 1, today_str)

                elif slot_id == 13:
                    if last_entry_bar_time != b1_time and window_ok(b1_tmin, "FULL_09_17") and m_gamma_flip > 0.0:
                        if b1_c < m_gamma_flip - 5.0 and pos50 <= 0.35 and d_l <= 4.5 and b1_c > b1_o:
                            open_virtual_grid(1, new_bar_open, new_bar_time, 16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 26)
                            last_entry_bar_time = b1_time
                        elif b1_c > m_gamma_flip + 5.0 and pos50 >= 0.65 and d_h <= 4.5 and b1_c < b1_o:
                            open_virtual_grid(-1, new_bar_open, new_bar_time, 16.0, 32.0, 1, 2, 0, 11.0, 22.0, 6.5, 1.5, 26)
                            last_entry_bar_time = b1_time

                elif slot_id == 14:
                    if last_entry_bar_time != b1_time and 545 <= b1_tmin <= 930 and m_gamma_flip > 0.0:
                        if b1_c < m_gamma_flip - 5.0 and pos50 <= 0.35 and d_l <= 4.5 and b1_c > b1_o:
                            open_virtual_grid(1, new_bar_open, new_bar_time, 18.0, 40.0, 1, 2, 3, 11.0, 22.0, 6.5, 1.5, 26)
                            last_entry_bar_time = b1_time
                        elif b1_c > m_gamma_flip + 5.0 and pos50 >= 0.65 and d_h <= 4.5 and b1_c < b1_o:
                            open_virtual_grid(-1, new_bar_open, new_bar_time, 18.0, 40.0, 1, 2, 3, 11.0, 22.0, 6.5, 1.5, 26)
                            last_entry_bar_time = b1_time

                elif slot_id == 15:
                    if trades_today < 3 and window_ok(b1_tmin, "NO_LUNCH") and len(m_levels_walls) > 0:
                        hb30_15 = max(1.0, 0.5 * bw30)
                        z30_c_15 = (b1_c - m_n30_c_1) / hb30_15
                        z30_l_15 = (b1_l - m_n30_c_1) / hb30_15
                        z30_h_15 = (b1_h - m_n30_c_1) / hb30_15
                        gf_b15 = (m_gamma_flip <= 0.0) or (b1_c < m_gamma_flip + 6.0)
                        gf_s15 = (m_gamma_flip <= 0.0) or (b1_c > m_gamma_flip - 6.0)
                        sig15 = 0
                        if dw_l_main <= 4.5 and b1_c >= (w_s_main - 0.5) and (z30_c_15 <= -0.70 or z30_l_15 <= -0.90) and b1_c > b1_o and gf_b15:
                            sig15 = 1
                        elif dw_h_main <= 4.5 and b1_c <= (w_r_main + 0.5) and (z30_c_15 >= 0.70 or z30_h_15 >= 0.90) and b1_c < b1_o and gf_s15:
                            sig15 = -1
                        if sig15 != 0:
                            p15_lim = round05(b1_l + 0.5) if sig15 == 1 else round05(b1_h - 0.5)
                            c_shld_15 = b1_l if sig15 == 1 else b1_h
                            tp_calc = calc_wdo_target_pts(p15_lim, sig15, 1, 14.0, m_levels_walls, m_levels_all)
                            arm_pending_order(sig15, 1, p15_lim, new_bar_time, new_bar_open, tp_calc, 11.5, 6.5, 1.5, 0.0, 0.0, 16, c_shld_15, 1, 1.5, 2, today_str)

                elif slot_id == 16:
                    if last_trade_date != today_str and 550 <= new_tmin <= 840 and len(m_levels_walls) > 0:
                        if pos50 >= 0.65 and dw_h_main <= 4.0 and b1_c < w_r_main and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                            tp_calc = calc_wdo_target_pts(mid_b1, -1, 1, 65.0, m_levels_walls, m_levels_all)
                            arm_pending_order(-1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 20.0, 11.5, 2.0, 26.0, 10.5, 120, w_r_main, 1, 1.5, 1, today_str)
                        elif pos50 <= 0.35 and dw_l_main <= 4.0 and b1_c > w_s_main and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                            tp_calc = calc_wdo_target_pts(mid_b1, 1, 1, 65.0, m_levels_walls, m_levels_all)
                            arm_pending_order(1, 1, mid_b1, new_bar_time, new_bar_open, tp_calc, 20.0, 11.5, 2.0, 26.0, 10.5, 120, w_s_main, 1, 1.5, 1, today_str)

        # =====================================================================
        # OnTickProcess durante a barra M5 `idx` (OHLC da barra `idx`)
        # =====================================================================
        _gate[0] = False
        # 1. Ordem pendente ativa na corretora para esta barra
        if d_pos == 0 and pend_dir != 0 and broker_order_active and pend_bar_time == new_bar_time:
            triggered = False
            if pend_type == 1:
                if pend_dir == 1 and l0 <= pend_price:
                    triggered = True
                elif pend_dir == -1 and h0 >= pend_price:
                    triggered = True
            elif pend_type == 2:
                if pend_dir == 1 and h0 >= pend_price:
                    triggered = True
                elif pend_dir == -1 and l0 <= pend_price:
                    triggered = True

            if triggered:
                pt_save = pyr_trig
                pl_save = pyr_lock
                open_virtual_single(
                    pend_dir, pend_price, new_bar_time,
                    pend_tp_pts, pend_sl_pts,
                    be_trig, be_lock, tr_trig, tr_dist,
                    max_hold_bars, True, pt_save, pl_save,
                    pend_def_wall, pend_be_mode, pend_wall_buf
                )
                last_entry_bar_time = new_bar_time
                if slot_id == 16:
                    last_trade_date = today_str

        # 2. Gerenciamento intrabar da posição aberta (Grid Perna 2/3 e SL/TP)
        if d_pos != 0:
            is_bull = c0 >= o0
            if opened_intrabar and entry_bar_time == new_bar_time and o0 != p1_entry:
                # Se preencheu intrabar via Limit/Stop, filtra extremo anterior ao preenchimento
                if d_pos == 1:
                    eff_low = l0
                    eff_high = h0 if is_bull else max(p1_entry, c0)
                else:
                    eff_high = h0
                    eff_low = l0 if not is_bull else min(p1_entry, c0)
            else:
                eff_high, eff_low = h0, l0

            if slot_id in (11, 13, 14):
                if leg_stage == 1 and not be_active and lot2 > 0 and step2_dist > 0.0:
                    p2_lvl = round05(p1_entry - step2_dist) if d_pos == 1 else round05(p1_entry + step2_dist)
                    if (d_pos == 1 and eff_low <= p2_lvl) or (d_pos == -1 and eff_high >= p2_lvl):
                        new_lots = lot1 + lot2
                        avg_price = round05((p1_entry * lot1 + p2_lvl * lot2) / float(new_lots))
                        lots = new_lots
                        leg_stage = 2
                        be_active = False
                        max_fav_pts = 0.0
                        be_trig = 2.5
                        be_lock = 0.5
                        be_mode = 0
                        curr_tp = round05(avg_price + tp_avg_pts) if d_pos == 1 else round05(avg_price - tp_avg_pts)
                        curr_sl = round05(p2_lvl - max_sl_pts) if d_pos == 1 else round05(p2_lvl + max_sl_pts)
                        # Após executar Perna 2 na mínima/máxima, na mesma barra o preço a favor só vai até o fechamento se já fez a mínima/máxima depois
                        if d_pos == 1 and not is_bull:
                            eff_high = max(p2_lvl, c0)
                        elif d_pos == -1 and is_bull:
                            eff_low = min(p2_lvl, c0)

                if leg_stage == 2 and lot3 > 0 and step3_dist > 0.0:
                    p3_lvl = round05(p1_entry - step3_dist) if d_pos == 1 else round05(p1_entry + step3_dist)
                    if (d_pos == 1 and eff_low <= p3_lvl) or (d_pos == -1 and eff_high >= p3_lvl):
                        new_lots = lots + lot3
                        avg_price = round05((avg_price * lots + p3_lvl * lot3) / float(new_lots))
                        lots = new_lots
                        leg_stage = 3
                        be_active = False
                        max_fav_pts = 0.0
                        curr_tp = round05(avg_price + tp_avg_pts) if d_pos == 1 else round05(avg_price - tp_avg_pts)
                        curr_sl = round05(avg_price - max_sl_pts) if d_pos == 1 else round05(avg_price + max_sl_pts)

            if d_pos == 1:
                if eff_low <= curr_sl:
                    exit_p = min(curr_sl, o0) if not (opened_intrabar and entry_bar_time == new_bar_time) else curr_sl
                    close_virtual_slot(exit_p, "SL", ts_arr[idx], today_str)
                elif eff_high >= curr_tp:
                    exit_p = max(curr_tp, o0) if not (opened_intrabar and entry_bar_time == new_bar_time) else curr_tp
                    close_virtual_slot(exit_p, "TP", ts_arr[idx], today_str)
            else:
                sl_srv = round05(curr_sl + 0.5)
                tp_srv = round05(curr_tp + 0.5)
                if eff_high >= sl_srv:
                    exit_p = max(curr_sl, round05(o0 - 0.5)) if not (opened_intrabar and entry_bar_time == new_bar_time) else curr_sl
                    close_virtual_slot(exit_p, "SL", ts_arr[idx], today_str)
                elif eff_low <= tp_srv:
                    exit_p = min(curr_tp, round05(o0 - 0.5)) if not (opened_intrabar and entry_bar_time == new_bar_time) else curr_tp
                    close_virtual_slot(exit_p, "TP", ts_arr[idx], today_str)

    # Ao vivo (dados cortados no meio do pregão): emite a posição ainda aberta na última barra disponível.
    if EMIT_OPEN_AT_END and d_pos != 0 and n > 0 and start_date <= str(dates[n - 1]) <= end_date:
        close_virtual_slot(float(closes[n - 1]), "ABERTA", ts_arr[n - 1], str(dates[n - 1]))

    return trades


def summarize_wdo_trades(trades: list, label: str = "") -> dict:
    if not trades:
        return {
            "EA": label, "Trades": 0, "Contracts": 0, "WR%": 0.0,
            "PF_sem_custo": 0.0, "PF_com_custo": 0.0,
            "R$_sem_custo": 0.0, "R$_com_custo": 0.0,
            "DD_sem_custo": 0.0, "DD_com_custo": 0.0,
            "RetDD_sem_custo": 0.0, "RetDD_com_custo": 0.0,
            "PiorDia_com_custo": 0.0,
        }
    df_t = pd.DataFrame(trades)
    n_tr = len(df_t)
    tot_lots = int(df_t["contracts"].sum())

    # Sem custo
    gw_nc = df_t.loc[df_t["pnl_brl_nocost"] > 0, "pnl_brl_nocost"].sum()
    gl_nc = abs(df_t.loc[df_t["pnl_brl_nocost"] < 0, "pnl_brl_nocost"].sum())
    pf_nc = gw_nc / gl_nc if gl_nc > 1e-6 else 99.9
    net_nc = df_t["pnl_brl_nocost"].sum()
    daily_nc = df_t.groupby("date")["pnl_brl_nocost"].sum()
    cum_nc = daily_nc.cumsum()
    dd_nc = float((cum_nc.cummax().clip(lower=0.0) - cum_nc).max())
    retdd_nc = net_nc / dd_nc if dd_nc > 0 else 0.0

    # Com custo
    wins_c = (df_t["pnl_brl"] > 0).sum()
    wr_c = 100.0 * wins_c / n_tr
    gw_c = df_t.loc[df_t["pnl_brl"] > 0, "pnl_brl"].sum()
    gl_c = abs(df_t.loc[df_t["pnl_brl"] < 0, "pnl_brl"].sum())
    pf_c = gw_c / gl_c if gl_c > 1e-6 else 99.9
    net_c = df_t["pnl_brl"].sum()
    daily_c = df_t.groupby("date")["pnl_brl"].sum()
    cum_c = daily_c.cumsum()
    dd_c = float((cum_c.cummax().clip(lower=0.0) - cum_c).max())
    retdd_c = net_c / dd_c if dd_c > 0 else 0.0
    worst_day_c = float(daily_c.min())

    return {
        "EA": label,
        "Trades": int(n_tr),
        "Contracts": tot_lots,
        "WR%": round(wr_c, 1),
        "PF_sem_custo": round(pf_nc, 2),
        "PF_com_custo": round(pf_c, 2),
        "R$_sem_custo": round(net_nc, 0),
        "R$_com_custo": round(net_c, 0),
        "DD_sem_custo": round(dd_nc, 0),
        "DD_com_custo": round(dd_c, 0),
        "RetDD_sem_custo": round(retdd_nc, 2),
        "RetDD_com_custo": round(retdd_c, 2),
        "PiorDia_com_custo": round(worst_day_c, 0),
    }


def run_all_wdo_slots(cost_pts: float = 0.5, start_date: str = "2026-05-11", end_date: str = "2026-11-04"):
    df, gex = load_wdo_mt5_raw()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    rsi7 = compute_rsi7_series(closes)

    trades_by_slot = {}
    summary_rows = []
    for sid in range(1, 17):
        tr = simulate_wdo_core_slot(
            sid, df, gex,
            n50_c, n50_u, n50_l, n50_s,
            n30_c, n30_u, n30_l, n30_s,
            rsi7,
            start_date=start_date, end_date=end_date, cost_pts=cost_pts,
        )
        trades_by_slot[sid] = tr
        summary_rows.append(summarize_wdo_trades(tr, f"WDO-{sid:02d}"))
    return pd.DataFrame(summary_rows), trades_by_slot


if __name__ == "__main__":
    df_sum, tr_map = run_all_wdo_slots(cost_pts=0.5)
    print(df_sum.to_string(index=False))
