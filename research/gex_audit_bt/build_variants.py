"""
Gera CSVs históricos paralelos das variantes WIN e WDO (2026-01-02 a 2026-11-11)
para backtest comparativo sem alterar nenhum arquivo de produção.

Uso: python -m research.gex_audit_bt.build_variants
"""
from __future__ import annotations

import datetime
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gex.engine.b3_dol_parser import _get_dol_expiration, parse_b3_oi
from gex.engine.b3_history_calculator import (
    _wdo_symbol_for_expiry,
    get_selic_for_date,
    load_mt5_synced_m5_prices,
)
from gex.engine.b3_parser import _get_ibov_expiration
from gex.engine.black76 import black76_gamma
from gex.engine.mt5_exporter import _norm_wall_type
from gex.engine.mt5_prices import get_b3_expected_wdo_contract, get_b3_expected_win_contract

DATA_DIR = os.path.join(ROOT, "gex", "data")
OUT_DIR = os.path.join(ROOT, "research", "gex_audit_bt", "gex_csvs")
CATALOG_CSV = os.path.join(ROOT, "research", "gex_audit_bt", "b3_ibov_catalog_2026.csv")

START_DATE = "2026-01-02"
END_DATE = "2026-11-11"

IBOV_MONTH_CODES = {
    "A": (1, "CALL"), "B": (2, "CALL"), "C": (3, "CALL"), "D": (4, "CALL"),
    "E": (5, "CALL"), "F": (6, "CALL"), "G": (7, "CALL"), "H": (8, "CALL"),
    "I": (9, "CALL"), "J": (10, "CALL"), "K": (11, "CALL"), "L": (12, "CALL"),
    "M": (1, "PUT"), "N": (2, "PUT"), "O": (3, "PUT"), "P": (4, "PUT"),
    "Q": (5, "PUT"), "R": (6, "PUT"), "S": (7, "PUT"), "T": (8, "PUT"),
    "U": (9, "PUT"), "V": (10, "PUT"), "W": (11, "PUT"), "X": (12, "PUT"),
}
DOL_MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}


def _legacy_int_oi(raw_val) -> int:
    s = str(raw_val).replace(".", "").replace("-", "0").strip()
    try:
        return int(s)
    except Exception:
        return 0


def load_b3_catalog() -> dict[str, dict]:
    df = pd.read_csv(CATALOG_CSV, dtype=str)
    cat = {}
    for _, r in df.iterrows():
        cat[r["isin"]] = {
            "ticker": r["ticker"],
            "type": r["type"],
            "strike": float(r["strike"]),
            "expiry": r["expiry"][:10],
        }
    return cat


def parse_csv_all_modes(file_path: str, ref_date: datetime.date, catalog: dict[str, dict]):
    """
    Lê `Posições em aberto` uma única vez (sem dtype=str para replicar legado, e via strings para o corrigido)
    e retorna os DataFrames para cada variante.
    """
    header_idx = 0
    with open(file_path, "r", encoding="latin1") as f:
        for i, line in enumerate(f):
            if "Instrumento financeiro" in line:
                header_idx = i
                break

    pos_legacy = pd.read_csv(file_path, sep=";", encoding="latin1", skiprows=header_idx, low_memory=False)
    pos_str = pd.read_csv(file_path, sep=";", encoding="latin1", skiprows=header_idx, dtype=str, low_memory=False)

    ref_year, ref_month = ref_date.year, ref_date.month

    # --- IBOV ---
    tk_s = pos_str.iloc[:, 0].astype(str).str.strip()
    seg_s = pos_str.iloc[:, 4].astype(str).str.strip()
    ib_mask = tk_s.str.startswith("IBOV") & (seg_s.str.contains("EQUITY CALL", na=False) | seg_s.str.contains("EQUITY PUT", na=False))

    ib_leg, ib_v1, ib_v2 = [], [], []
    for idx_row in pos_str.index[ib_mask]:
        row_s = pos_str.loc[idx_row]
        row_l = pos_legacy.loc[idx_row]
        tk = str(row_s.iloc[0]).strip()
        m = re.match(r"^IBOV([A-X])(\d+)$", tk)
        if not m:
            continue
        m_code, s_code = m.groups()
        strike_leg = int(s_code) * 1000
        if len(s_code) == 2 and strike_leg < 30000:
            strike_leg *= 10
        m_num, o_type = IBOV_MONTH_CODES[m_code]
        yr = ref_year + (1 if m_num < ref_month else 0)
        exp_leg = _get_ibov_expiration(yr, m_num).isoformat()

        oi_leg = _legacy_int_oi(row_l.iloc[11]) if len(row_l) > 11 else 0
        oi_fix = parse_b3_oi(row_s.iloc[11]) if len(row_s) > 11 else 0

        if strike_leg >= 100000 and oi_leg > 0:
            ib_leg.append({"ticker": tk, "type": o_type, "strike": float(strike_leg), "expiry": exp_leg, "oi": oi_leg})
        if strike_leg >= 100000 and oi_fix > 0:
            ib_v1.append({"ticker": tk, "type": o_type, "strike": float(strike_leg), "expiry": exp_leg, "oi": oi_fix})

        if oi_fix > 0:
            isin = str(row_s.iloc[1]).strip()
            cat_hit = catalog.get(isin)
            if cat_hit is not None:
                ib_v2.append({
                    "ticker": tk,
                    "type": cat_hit["type"],
                    "strike": float(cat_hit["strike"]),
                    "expiry": cat_hit["expiry"] + "T00:00:00",
                    "oi": oi_fix,
                })
            elif strike_leg >= 100000:
                ib_v2.append({
                    "ticker": tk,
                    "type": o_type,
                    "strike": float(strike_leg),
                    "expiry": exp_leg,
                    "oi": oi_fix,
                })

    # --- DOL ---
    dol_mask = tk_s.str.startswith("DOL")
    dol_leg, dol_fix = [], []
    for idx_row in pos_str.index[dol_mask]:
        row_s = pos_str.loc[idx_row]
        row_l = pos_legacy.loc[idx_row]
        tk = str(row_s.iloc[0]).strip()
        m = re.match(r"^DOL([A-Z])(\d{2})([CP])(\d{6})$", tk)
        if not m:
            continue
        m_code, y_code, t_char, s_code = m.groups()
        try:
            strike = float(s_code)
            if strike > 20000:
                strike /= 100.0
        except Exception:
            continue
        o_type = "CALL" if t_char == "C" else "PUT"
        m_num = DOL_MONTH_CODES.get(m_code, 1)
        yr = int("20" + y_code)
        exp_dt = _get_dol_expiration(yr, m_num).isoformat()

        oi_l = 0
        oi_f = 0
        for c_idx in (11, 5):
            if len(row_l) > c_idx:
                v_l = _legacy_int_oi(row_l.iloc[c_idx])
                if v_l > oi_l:
                    oi_l = v_l
                v_f = parse_b3_oi(row_s.iloc[c_idx])
                if v_f > oi_f:
                    oi_f = v_f
        if oi_l > 0:
            dol_leg.append({"ticker": tk, "type": o_type, "strike": float(strike), "expiry": exp_dt, "oi": oi_l})
        if oi_f > 0:
            dol_fix.append({"ticker": tk, "type": o_type, "strike": float(strike), "expiry": exp_dt, "oi": oi_f})

    return (
        pd.DataFrame(ib_leg),
        pd.DataFrame(ib_v1),
        pd.DataFrame(ib_v2),
        pd.DataFrame(dol_leg),
        pd.DataFrame(dol_fix),
    )


def _find_nearest_zero_cross(p_arr: np.ndarray, g_arr: np.ndarray, ref_spot: float):
    cross_price = None
    best_dist = float("inf")
    for i in range(len(g_arr) - 1):
        if g_arr[i] * g_arr[i + 1] < 0:
            x0, x1 = p_arr[i], p_arr[i + 1]
            y0, y1 = g_arr[i], g_arr[i + 1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            dist = abs(cross - ref_spot)
            if dist < best_dist:
                best_dist = dist
                cross_price = float(cross)
    return cross_price


def calc_win_walls(df_opts: pd.DataFrame, current_win: float, current_ibov: float,
                   expiry_days: int, r: float, ref_date: datetime.date, expanded_curve: bool) -> list[dict]:
    if df_opts.empty:
        return []
    iv = 0.20
    all_expiries = sorted(df_opts["expiry"].unique())
    front_month = None
    for exp in all_expiries:
        ed = df_opts[df_opts["expiry"] == exp]
        if len(ed) >= 5 and ed["strike"].nunique() >= 3:
            front_month = exp
            break
    if front_month is None:
        front_month = df_opts.groupby("expiry").size().idxmax()

    df_fm = df_opts[df_opts["expiry"] == front_month].copy()
    _, _, win_exp_dt = get_b3_expected_win_contract(ref_date)
    win_exp_days = max(1, int(np.busday_count(ref_date.isoformat(), win_exp_dt.isoformat())))
    T = max(1 / 252, expiry_days / 252)
    T_win = max(1 / 252, win_exp_days / 252)

    mt5_factor = (current_win / current_ibov) if (current_win and current_ibov > 0) else None
    theo_factor = (1 + r) ** T_win
    factor = mt5_factor if (mt5_factor is not None and 0.995 <= mt5_factor <= 1.045) else theo_factor

    df_fm["strike_round"] = (df_fm["strike"] / 1000).round() * 1000
    gex_per_strike = {}
    for strike_ibov, grp in df_fm.groupby("strike_round"):
        strike_win = strike_ibov * factor
        gex_net = 0.0
        for _, row in grp.iterrows():
            gamma = black76_gamma(F=current_win, K=strike_win, T=T, sigma=iv)
            c = row["oi"] * gamma * (current_win ** 2) * 0.01
            if row["type"].upper() == "PUT":
                c = -c
            gex_net += c
        gex_per_strike[strike_ibov] = {"strike_win": strike_win, "gex_net": gex_net, "abs_gex": abs(gex_net)}

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_ibov))
    atm_idx = all_strikes.index(atm_strike)
    si = max(0, atm_idx - 8)
    ei = min(len(all_strikes), si + 16)
    si = max(0, ei - 16)
    selected_strikes = all_strikes[si:ei]

    sorted_by_gex = sorted(((s, gex_per_strike[s]) for s in selected_strikes), key=lambda x: x[1]["abs_gex"], reverse=True)
    width_map = {s: (3 if rank == 0 else (2 if rank <= 2 else 1)) for rank, (s, _) in enumerate(sorted_by_gex)}

    walls = []
    for s in selected_strikes:
        walls.append({"price": round(gex_per_strike[s]["strike_win"], 3), "type": "Wall", "width": width_map[s]})
    n_w = len(walls)
    for i in range(n_w - 1):
        walls.append({"price": round((walls[i]["price"] + walls[i + 1]["price"]) / 2, 3), "type": "MidWall", "width": 1})

    df_loc = df_fm[df_fm["strike_round"].isin(selected_strikes)].copy()
    if df_loc.empty:
        df_loc = df_fm

    def _curve_win(df_src: pd.DataFrame, p_arr: np.ndarray) -> np.ndarray:
        F_sw = p_arr[:, None]
        k_arr = (df_src["strike"].to_numpy(dtype=float) * factor)[None, :]
        oi_arr = df_src["oi"].to_numpy(dtype=float)
        sgn = np.where(df_src["type"].str.upper().to_numpy() == "PUT", -1.0, 1.0)[None, :]
        d1 = (np.log(F_sw / k_arr) + 0.5 * (iv ** 2) * T) / (iv * np.sqrt(T))
        gamma_mat = np.exp(-0.5 * d1 ** 2) / (np.sqrt(2 * np.pi) * F_sw * iv * np.sqrt(T))
        return np.sum(sgn * oi_arr[None, :] * gamma_mat * (F_sw ** 2) * 0.01, axis=1)

    min_wall_win = min(gex_per_strike[s]["strike_win"] for s in selected_strikes)
    max_wall_win = max(gex_per_strike[s]["strike_win"] for s in selected_strikes)
    f_low = max(current_win * 0.955, min_wall_win)
    f_high = min(current_win * 1.045, max_wall_win)
    if f_low >= f_high:
        f_low, f_high = current_win * 0.96, current_win * 1.04

    prices = np.linspace(f_low, f_high, 200)
    gex_values = _curve_win(df_loc, prices)

    if not expanded_curve:
        max_gamma_price = float(prices[int(np.argmax(gex_values))])
        min_gamma_price = float(prices[int(np.argmin(gex_values))])
        flip_price = _find_nearest_zero_cross(prices, gex_values, current_win)
        if flip_price is None:
            near_mask = (prices >= current_win * 0.975) & (prices <= current_win * 1.025)
            if np.any(near_mask):
                np_arr = prices[near_mask]
                flip_price = float(np_arr[int(np.argmin(np.abs(gex_values[near_mask])))])
            else:
                flip_price = float(current_win)
    else:
        flip_price = _find_nearest_zero_cross(prices, gex_values, current_win)
        need_wide = (
            flip_price is None
            or float(np.min(gex_values)) >= 0.0
            or float(np.max(gex_values)) <= 0.0
        )
        prices_wide, gex_wide = None, None
        if need_wide:
            w_low = min(float(df_fm["strike"].min() * factor), current_win * 0.85)
            w_high = max(float(df_fm["strike"].max() * factor), current_win * 1.15)
            if w_low < w_high:
                prices_wide = np.linspace(w_low, w_high, 600)
                gex_wide = _curve_win(df_fm, prices_wide)

        if flip_price is None and gex_wide is not None:
            flip_price = _find_nearest_zero_cross(prices_wide, gex_wide, current_win)
        if flip_price is None:
            g_spot = float(_curve_win(df_fm, np.array([current_win], dtype=float))[0])
            flip_price = min_wall_win if g_spot >= 0.0 else max_wall_win

        if float(np.max(gex_values)) > 0.0:
            max_gamma_price = float(prices[int(np.argmax(gex_values))])
        elif gex_wide is not None and float(np.max(gex_wide)) > 0.0:
            max_gamma_price = float(prices_wide[int(np.argmax(gex_wide))])
        else:
            above_mask = prices >= flip_price
            sub_p = prices[above_mask] if np.any(above_mask) else prices
            sub_g = gex_values[above_mask] if np.any(above_mask) else gex_values
            max_gamma_price = float(sub_p[int(np.argmax(sub_g))])

        if float(np.min(gex_values)) < 0.0:
            min_gamma_price = float(prices[int(np.argmin(gex_values))])
        elif gex_wide is not None and float(np.min(gex_wide)) < 0.0:
            min_gamma_price = float(prices_wide[int(np.argmin(gex_wide))])
        else:
            below_mask = prices <= max_gamma_price
            sub_p = prices[below_mask] if np.any(below_mask) else prices
            sub_g = gex_values[below_mask] if np.any(below_mask) else gex_values
            min_gamma_price = float(sub_p[int(np.argmin(sub_g))])

    walls.append({"price": round(max_gamma_price, 3), "type": "MaxGamma", "width": 3})
    walls.append({"price": round(min_gamma_price, 3), "type": "MinGamma", "width": 3})
    walls.append({"price": round(flip_price, 3), "type": "GammaFlip", "width": 2})
    return walls


def calc_dol_walls(df_dol: pd.DataFrame, current_wdo: float, ref_date: datetime.date,
                   mode: str) -> list[dict]:
    """
    mode:
      - 'base_recalc': legado (strike_base_10, curva ±4% / ±2% fallback)
      - 'v1_fixes123': strike_base 5 em 5 + curva expandida (front-month + rolagem padrão)
      - 'v2a_multiexp_always': Fixes 1-3 + sempre front + next com carry diferencial Brasil-EUA
      - 'v2b_multiexp_roll5d': Fixes 1-3 + front + next quando <= 5 DU ou OI(next) > OI(front)
    """
    if df_dol.empty or current_wdo <= 0:
        return []

    ref_date_str = ref_date.isoformat()
    df_future = df_dol[df_dol["expiry"].str[:10] > ref_date_str].copy()
    df_valid = df_future if not df_future.empty else df_dol[df_dol["expiry"].str[:10] >= ref_date_str].copy()
    if df_valid.empty:
        return []

    r = get_selic_for_date(ref_date_str)
    iv = 0.12
    multiplier = 50
    active_contract, _ = get_b3_expected_wdo_contract(ref_date)

    all_expiries = sorted(df_valid["expiry"].unique())
    front_month = all_expiries[0]
    front_wdo_sym = _wdo_symbol_for_expiry(front_month)
    front_dt = datetime.date.fromisoformat(front_month[:10])
    front_bdays = max(1, int(np.busday_count(ref_date_str, front_dt.isoformat())))

    selected_expiries = [front_month]
    if mode in ("base_recalc", "v1_fixes123"):
        if front_wdo_sym != active_contract and len(all_expiries) > 1:
            for exp_cand in all_expiries[1:]:
                if _wdo_symbol_for_expiry(exp_cand) == active_contract:
                    selected_expiries.append(exp_cand)
                    break
    elif mode == "v2a_multiexp_always":
        if len(all_expiries) > 1:
            selected_expiries.append(all_expiries[1])
    elif mode == "v2b_multiexp_roll5d":
        if front_wdo_sym != active_contract and len(all_expiries) > 1:
            for exp_cand in all_expiries[1:]:
                if _wdo_symbol_for_expiry(exp_cand) == active_contract:
                    selected_expiries.append(exp_cand)
                    break
        elif len(all_expiries) > 1:
            next_month = all_expiries[1]
            oi_front = float(df_valid[df_valid["expiry"] == front_month]["oi"].sum())
            oi_next = float(df_valid[df_valid["expiry"] == next_month]["oi"].sum())
            if front_bdays <= 5 or oi_next > oi_front:
                selected_expiries.append(next_month)

    df_front = df_valid[df_valid["expiry"].isin(selected_expiries)].copy()

    # Descobre b_days do contrato ativo para carry diferencial
    act_bdays = None
    for exp_cand in all_expiries:
        if _wdo_symbol_for_expiry(exp_cand) == active_contract:
            exp_dt = datetime.date.fromisoformat(exp_cand[:10])
            act_bdays = max(1, int(np.busday_count(ref_date_str, exp_dt.isoformat())))
            break
    if act_bdays is None:
        act_bdays = front_bdays if front_wdo_sym == active_contract else (front_bdays + 21)

    diff_rate = max(r - 0.05, 0.04)
    expiry_meta = {}
    for exp_val in selected_expiries:
        opt_wdo_sym = _wdo_symbol_for_expiry(exp_val)
        exp_dt = datetime.date.fromisoformat(exp_val[:10])
        b_days = max(1, int(np.busday_count(ref_date_str, exp_dt.isoformat())))
        t_val = max(1 / 252, b_days / 252)
        if opt_wdo_sym == active_contract:
            carry_ratio = 1.0
        elif mode == "base_recalc" or mode == "v1_fixes123":
            carry_ratio = (1 + r) ** (21 / 252)
        else:
            delta_bdays = b_days - act_bdays
            carry_ratio = (1.0 + diff_rate) ** (-delta_bdays / 252.0)
        expiry_meta[exp_val] = {"T": t_val, "carry_ratio": carry_ratio}

    df_front["carry_ratio"] = df_front["expiry"].map(lambda e: expiry_meta[e]["carry_ratio"])
    df_front["T_opt"] = df_front["expiry"].map(lambda e: expiry_meta[e]["T"])
    df_front["strike_wdo"] = df_front["strike"] * df_front["carry_ratio"]

    if mode == "base_recalc":
        df_front["strike_base"] = (df_front["strike"] / 10.0).round() * 10.0
    else:
        df_front["strike_base"] = (df_front["strike"] / 5.0).round() * 5.0

    # No multi-vencimento projetado para a escala do ativo, agrupa pelo tick de 0.5 ou 5 pts na escala do ativo?
    # Preserva exatamente `strike_round = ((strike_base * carry_ratio) * 2).round() / 2` quando carry == 1.0,
    # e quando multiexp projeta `next` (ex: 6000 * 0.9928 = 5956.8) aproxima ao cluster de 5 pts do ativo para não poluir a grade!
    if mode in ("v2a_multiexp_always", "v2b_multiexp_roll5d"):
        raw_scaled = df_front["strike_base"] * df_front["carry_ratio"]
        # Para o contrato ativo (carry_ratio == 1.0), mantém exato; para outro vencimento, casa com múltiplos de 5 pts
        is_act = np.isclose(df_front["carry_ratio"], 1.0)
        df_front["strike_round"] = np.where(
            is_act,
            (raw_scaled * 2.0).round() / 2.0,
            (raw_scaled / 5.0).round() * 5.0,
        )
    else:
        df_front["strike_round"] = ((df_front["strike_base"] * df_front["carry_ratio"]) * 2).round() / 2

    gex_per_strike = {}
    for strike_round, grp in df_front.groupby("strike_round"):
        gex_net = 0.0
        for _, row in grp.iterrows():
            gamma = black76_gamma(F=current_wdo, K=float(row["strike_wdo"]), T=float(row["T_opt"]), sigma=iv)
            c = row["oi"] * gamma * (current_wdo ** 2) * 0.01 * multiplier
            if row["type"] == "PUT":
                c = -c
            gex_net += c
        gex_per_strike[float(strike_round)] = {"gex_net": gex_net, "abs_gex": abs(gex_net)}

    if not gex_per_strike:
        return []

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_wdo))
    atm_idx = all_strikes.index(atm_strike)
    si = max(0, atm_idx - 8)
    ei = min(len(all_strikes), si + 16)
    si = max(0, ei - 16)
    selected_strikes = all_strikes[si:ei]

    sorted_by_gex = sorted(((s, gex_per_strike[s]) for s in selected_strikes), key=lambda x: x[1]["abs_gex"], reverse=True)
    width_map = {s: (3 if rank == 0 else (2 if rank <= 2 else 1)) for rank, (s, _) in enumerate(sorted_by_gex)}

    walls_basic = sorted(
        [{"price": round(float(s), 2), "type": "Wall", "width": width_map[s]} for s in selected_strikes],
        key=lambda x: x["price"],
    )
    walls = []
    for i, wb in enumerate(walls_basic):
        walls.append(wb)
        if i < len(walls_basic) - 1:
            mid = (wb["price"] + walls_basic[i + 1]["price"]) / 2.0
            walls.append({"price": round(mid, 2), "type": "MidWall", "width": 1})

    df_loc = df_front[df_front["strike_round"].isin(selected_strikes)].copy()
    if df_loc.empty:
        df_loc = df_front

    def _curve_dol(df_src: pd.DataFrame, prices_arr: np.ndarray) -> np.ndarray:
        F_sw = prices_arr[:, None]
        k_arr = df_src["strike_wdo"].to_numpy(dtype=float)[None, :]
        t_arr = df_src["T_opt"].to_numpy(dtype=float)[None, :]
        oi_arr = df_src["oi"].to_numpy(dtype=float)
        sgn = np.where(df_src["type"].to_numpy() == "PUT", -1.0, 1.0)[None, :]
        d1 = (np.log(F_sw / k_arr) + 0.5 * (iv ** 2) * t_arr) / (iv * np.sqrt(t_arr))
        n_p = (1.0 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * (d1 ** 2))
        g_mat = np.exp(-0.1425 * t_arr) * n_p / (F_sw * iv * np.sqrt(t_arr))
        return np.sum(sgn * oi_arr[None, :] * g_mat * (F_sw ** 2) * 0.01 * multiplier, axis=1)

    min_wall_wdo = float(min(selected_strikes))
    max_wall_wdo = float(max(selected_strikes))
    f_low = max(current_wdo * 0.96, min_wall_wdo)
    f_high = min(current_wdo * 1.04, max_wall_wdo)
    if f_low >= f_high:
        f_low, f_high = current_wdo * 0.97, current_wdo * 1.03

    sweep_prices = np.linspace(f_low, f_high, 200)
    gex_values = _curve_dol(df_loc, sweep_prices)

    max_gamma_dol = round(float(sweep_prices[int(np.argmax(gex_values))]), 2)
    if mode == "base_recalc":
        min_gamma_dol = round(float(sweep_prices[int(np.argmin(gex_values))]), 2)
        flip_dol = _find_nearest_zero_cross(sweep_prices, gex_values, current_wdo)
        if flip_dol is None:
            near_mask = (sweep_prices >= current_wdo * 0.98) & (sweep_prices <= current_wdo * 1.02)
            if np.any(near_mask):
                np_arr = sweep_prices[near_mask]
                flip_dol = float(np_arr[int(np.argmin(np.abs(gex_values[near_mask])))])
            else:
                flip_dol = float(current_wdo)
    else:
        flip_dol = _find_nearest_zero_cross(sweep_prices, gex_values, current_wdo)
        need_wide = (
            flip_dol is None
            or float(np.min(gex_values)) >= 0.0
            or float(np.max(gex_values)) <= 0.0
        )
        prices_wide, gex_wide = None, None
        if need_wide:
            w_low = float(df_front["strike_wdo"].min())
            w_high = float(df_front["strike_wdo"].max())
            if w_low < w_high:
                prices_wide = np.linspace(w_low, w_high, 600)
                gex_wide = _curve_dol(df_front, prices_wide)

        if flip_dol is None and gex_wide is not None:
            flip_dol = _find_nearest_zero_cross(prices_wide, gex_wide, current_wdo)
        if flip_dol is None:
            g_spot = float(_curve_dol(df_front, np.array([current_wdo], dtype=float))[0])
            flip_dol = min_wall_wdo if g_spot >= 0.0 else max_wall_wdo

        if float(np.min(gex_values)) < 0.0:
            min_gamma_dol = round(float(sweep_prices[int(np.argmin(gex_values))]), 2)
        elif gex_wide is not None and float(np.min(gex_wide)) < 0.0:
            min_gamma_dol = round(float(prices_wide[int(np.argmin(gex_wide))]), 2)
        else:
            below_mask = sweep_prices <= max_gamma_dol
            sub_p = sweep_prices[below_mask] if np.any(below_mask) else sweep_prices
            sub_g = gex_values[below_mask] if np.any(below_mask) else gex_values
            min_gamma_dol = round(float(sub_p[int(np.argmin(sub_g))]), 2)

    walls.append({"price": max_gamma_dol, "type": "MaxGamma", "width": 3})
    walls.append({"price": min_gamma_dol, "type": "MinGamma", "width": 3})
    walls.append({"price": round(float(flip_dol), 2), "type": "GammaFlip", "width": 2})
    return walls


def write_history_csv(path: str, hist_map: dict[str, list[dict]]):
    lines = ["session_date;type;price;width"]
    for d in sorted(hist_map):
        for w in hist_map[d]:
            lines.append(f"{d};{_norm_wall_type(w['type'])};{float(w['price']):.2f};{int(w['width'])}")
    with open(path, "w", encoding="ascii", errors="ignore") as f:
        f.write("\n".join(lines) + "\n")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    catalog = load_b3_catalog()
    prices_ibov, prices_win, prices_wdo = load_mt5_synced_m5_prices()

    files = glob.glob(os.path.join(DATA_DIR, "Posições em aberto-*.csv"))
    dated_files = []
    for f in files:
        m = re.search(r"Posições em aberto-(\d{2})-(\d{2})-(\d{4})\.csv", f)
        if not m:
            continue
        d, mo, y = m.groups()
        iso = f"{y}-{mo}-{d}"
        if START_DATE <= iso <= END_DATE:
            dated_files.append((iso, datetime.date(int(y), int(mo), int(d)), f))
    dated_files.sort(key=lambda x: x[0])

    print(f"Construindo variantes para {len(dated_files)} pregoes ({START_DATE}..{END_DATE})...")

    win_vars = {k: {} for k in ("win_base_recalc", "win_v1_oi_flip", "win_v2_b3_strikes")}
    wdo_vars = {k: {} for k in ("wdo_base_recalc", "wdo_v1_fixes123", "wdo_v2a_multiexp_always", "wdo_v2b_multiexp_roll5d")}

    for idx, (session_str, session_obj, f_path_today) in enumerate(dated_files):
        ref_str, ref_obj, ref_path = dated_files[idx - 1] if idx > 0 else (session_str, session_obj, f_path_today)

        s_ibov = prices_ibov.get(ref_str) or prices_ibov.get(session_str) or 160000.0
        r_selic = get_selic_for_date(session_str)
        _, _, win_exp_dt = get_b3_expected_win_contract(ref_obj)
        win_exp_days = max(1, int(np.busday_count(ref_obj.isoformat(), win_exp_dt.isoformat())))
        theo_win_factor = (1 + r_selic) ** (win_exp_days / 252)

        f_win = prices_win.get(ref_str) or prices_win.get(session_str)
        if f_win is None or not (0.995 <= (f_win / s_ibov) <= 1.045):
            f_win = round(s_ibov * theo_win_factor, 0)
        wdo_price = prices_wdo.get(ref_str) or prices_wdo.get(session_str) or 5400.0

        df_ib_leg, df_ib_v1, df_ib_v2, df_dol_leg, df_dol_fix = parse_csv_all_modes(ref_path, ref_obj, catalog)

        # WIN variants
        for vname, df_src, exp_curve in (
            ("win_base_recalc", df_ib_leg, False),
            ("win_v1_oi_flip", df_ib_v1, True),
            ("win_v2_b3_strikes", df_ib_v2, True),
        ):
            walls_w = []
            if not df_src.empty:
                df_fut = df_src[df_src["expiry"].str[:10] > session_str]
                df_use = df_fut if not df_fut.empty else df_src[df_src["expiry"].str[:10] >= ref_str]
                if not df_use.empty:
                    front_exp = sorted(df_use["expiry"].unique())[0]
                    exp_dt = datetime.date.fromisoformat(front_exp[:10])
                    exp_days = max(1, int(np.busday_count(ref_str, exp_dt.isoformat())))
                    walls_w = calc_win_walls(df_use, f_win, s_ibov, exp_days, r_selic, ref_obj, expanded_curve=exp_curve)
            if not walls_w and win_vars[vname]:
                prev_d = max(win_vars[vname].keys())
                walls_w = win_vars[vname][prev_d]
            if walls_w:
                win_vars[vname][session_str] = walls_w

        # WDO variants
        for vname, df_src, mode in (
            ("wdo_base_recalc", df_dol_leg, "base_recalc"),
            ("wdo_v1_fixes123", df_dol_fix, "v1_fixes123"),
            ("wdo_v2a_multiexp_always", df_dol_fix, "v2a_multiexp_always"),
            ("wdo_v2b_multiexp_roll5d", df_dol_fix, "v2b_multiexp_roll5d"),
        ):
            walls_d = calc_dol_walls(df_src, wdo_price, ref_obj, mode=mode)
            if not walls_d and wdo_vars[vname]:
                prev_d = max(wdo_vars[vname].keys())
                walls_d = wdo_vars[vname][prev_d]
            if walls_d:
                wdo_vars[vname][session_str] = walls_d

        if (idx + 1) % 30 == 0 or (idx + 1) == len(dated_files):
            print(f"  [{idx + 1:3d}/{len(dated_files)}] {session_str} processado", flush=True)

    for vname, hmap in {**win_vars, **wdo_vars}.items():
        out_p = os.path.join(OUT_DIR, f"{vname}.csv")
        write_history_csv(out_p, hmap)
        print(f"Salvo {vname}.csv ({len(hmap)} sessoes)")


if __name__ == "__main__":
    main()
