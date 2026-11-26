"""
Gera CSVs históricos com GEX assinado (+ Call Wall / - Put Wall), gex_share e rank_abs_gex
para WIN e WDO (2026-01-02 a 2026-11-11), usando exatamente os algoritmos validados de produção:
  - WIN: V2_B3_STRIKES (Catalogo B3 ISIN + parse_b3_oi + curva expandida)
  - WDO: ONLY_EXPANDED_FLIP (strike_base_10 + parse_b3_oi + curva expandida, sem DOLF27)

Não altera nenhum arquivo de produção.
Uso: python -m research.gex_audit_bt.build_signed_gex
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

from gex.engine.b3_history_calculator import (  # noqa: E402
    _wdo_symbol_for_expiry,
    get_selic_for_date,
    load_mt5_synced_m5_prices,
)
from gex.engine.black76 import black76_gamma  # noqa: E402
from gex.engine.mt5_exporter import _norm_wall_type  # noqa: E402
from gex.engine.mt5_prices import get_b3_expected_wdo_contract, get_b3_expected_win_contract  # noqa: E402
from research.gex_audit_bt.build_variants import (  # noqa: E402
    DATA_DIR,
    END_DATE,
    OUT_DIR,
    START_DATE,
    _find_nearest_zero_cross,
    load_b3_catalog,
    parse_csv_all_modes,
)


def calc_win_walls_signed(
    df_opts: pd.DataFrame,
    current_win: float,
    current_ibov: float,
    expiry_days: int,
    r: float,
    ref_date: datetime.date,
) -> tuple[list[dict], dict]:
    if df_opts.empty:
        return [], {}
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
    rank_map = {s: rank + 1 for rank, (s, _) in enumerate(sorted_by_gex)}
    total_abs_16 = sum(gex_per_strike[s]["abs_gex"] for s in selected_strikes)
    total_net_16 = sum(gex_per_strike[s]["gex_net"] for s in selected_strikes)

    walls = []
    call_cnt = 0
    put_cnt = 0
    for s in selected_strikes:
        g_info = gex_per_strike[s]
        g_net = float(g_info["gex_net"])
        if g_net > 0:
            call_cnt += 1
        elif g_net < 0:
            put_cnt += 1
        share = float(g_info["abs_gex"] / total_abs_16) if total_abs_16 > 0 else 0.0
        walls.append({
            "price": round(g_info["strike_win"], 3),
            "type": "Wall",
            "width": width_map[s],
            "gex": g_net,
            "gex_share": share,
            "rank_abs_gex": rank_map[s],
        })

    n_w = len(walls)
    for i in range(n_w - 1):
        walls.append({
            "price": round((walls[i]["price"] + walls[i + 1]["price"]) / 2, 3),
            "type": "MidWall",
            "width": 1,
            "gex": 0.0,
            "gex_share": 0.0,
            "rank_abs_gex": 0,
        })

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

    walls.append({"price": round(max_gamma_price, 3), "type": "MaxGamma", "width": 3, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})
    walls.append({"price": round(min_gamma_price, 3), "type": "MinGamma", "width": 3, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})
    walls.append({"price": round(flip_price, 3), "type": "GammaFlip", "width": 2, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})

    shares_sorted = sorted((w["gex_share"] for w in walls if w["type"] == "Wall"), reverse=True)
    meta = {
        "spot_ref": round(float(current_win), 2),
        "gamma_flip": round(float(flip_price), 2),
        "max_gamma": round(float(max_gamma_price), 2),
        "min_gamma": round(float(min_gamma_price), 2),
        "total_abs_gex_16": float(total_abs_16),
        "total_net_gex_16": float(total_net_16),
        "call_walls_cnt": call_cnt,
        "put_walls_cnt": put_cnt,
        "top1_share": round(shares_sorted[0], 6) if shares_sorted else 0.0,
        "top3_share": round(sum(shares_sorted[:3]), 6) if shares_sorted else 0.0,
    }
    return walls, meta


def calc_dol_walls_signed(
    df_dol: pd.DataFrame,
    current_wdo: float,
    ref_date: datetime.date,
) -> tuple[list[dict], dict]:
    """Algoritmo oficial WDO: strike_base_10 + parse_b3_oi + curva expandida (sem DOLF27)."""
    if df_dol.empty or current_wdo <= 0:
        return [], {}

    ref_date_str = ref_date.isoformat()
    df_future = df_dol[df_dol["expiry"].str[:10] > ref_date_str].copy()
    df_valid = df_future if not df_future.empty else df_dol[df_dol["expiry"].str[:10] >= ref_date_str].copy()
    if df_valid.empty:
        return [], {}

    r = get_selic_for_date(ref_date_str)
    iv = 0.12
    multiplier = 50
    active_contract, _ = get_b3_expected_wdo_contract(ref_date)

    all_expiries = sorted(df_valid["expiry"].unique())
    front_month = all_expiries[0]
    front_wdo_sym = _wdo_symbol_for_expiry(front_month)

    selected_expiries = [front_month]
    if front_wdo_sym != active_contract and len(all_expiries) > 1:
        for exp_cand in all_expiries[1:]:
            if _wdo_symbol_for_expiry(exp_cand) == active_contract:
                selected_expiries.append(exp_cand)
                break

    df_front = df_valid[df_valid["expiry"].isin(selected_expiries)].copy()
    expiry_meta = {}
    for exp_val in selected_expiries:
        opt_wdo_sym = _wdo_symbol_for_expiry(exp_val)
        exp_dt = datetime.date.fromisoformat(exp_val[:10])
        b_days = max(1, int(np.busday_count(ref_date_str, exp_dt.isoformat())))
        t_val = max(1 / 252, b_days / 252)
        carry_ratio = 1.0 if opt_wdo_sym == active_contract else ((1 + r) ** (21 / 252))
        expiry_meta[exp_val] = {"T": t_val, "carry_ratio": carry_ratio}

    df_front["carry_ratio"] = df_front["expiry"].map(lambda e: expiry_meta[e]["carry_ratio"])
    df_front["T_opt"] = df_front["expiry"].map(lambda e: expiry_meta[e]["T"])
    df_front["strike_wdo"] = df_front["strike"] * df_front["carry_ratio"]
    df_front["strike_base"] = (df_front["strike"] / 10.0).round() * 10.0
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
        return [], {}

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_wdo))
    atm_idx = all_strikes.index(atm_strike)
    si = max(0, atm_idx - 8)
    ei = min(len(all_strikes), si + 16)
    si = max(0, ei - 16)
    selected_strikes = all_strikes[si:ei]

    sorted_by_gex = sorted(((s, gex_per_strike[s]) for s in selected_strikes), key=lambda x: x[1]["abs_gex"], reverse=True)
    width_map = {s: (3 if rank == 0 else (2 if rank <= 2 else 1)) for rank, (s, _) in enumerate(sorted_by_gex)}
    rank_map = {s: rank + 1 for rank, (s, _) in enumerate(sorted_by_gex)}
    total_abs_16 = sum(gex_per_strike[s]["abs_gex"] for s in selected_strikes)
    total_net_16 = sum(gex_per_strike[s]["gex_net"] for s in selected_strikes)

    walls_basic = []
    call_cnt = 0
    put_cnt = 0
    for s in sorted(selected_strikes):
        g_info = gex_per_strike[s]
        g_net = float(g_info["gex_net"])
        if g_net > 0:
            call_cnt += 1
        elif g_net < 0:
            put_cnt += 1
        share = float(g_info["abs_gex"] / total_abs_16) if total_abs_16 > 0 else 0.0
        walls_basic.append({
            "price": round(float(s), 2),
            "type": "Wall",
            "width": width_map[s],
            "gex": g_net,
            "gex_share": share,
            "rank_abs_gex": rank_map[s],
        })

    walls = []
    for i, wb in enumerate(walls_basic):
        walls.append(wb)
        if i < len(walls_basic) - 1:
            mid = (wb["price"] + walls_basic[i + 1]["price"]) / 2.0
            walls.append({"price": round(mid, 2), "type": "MidWall", "width": 1, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})

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

    walls.append({"price": max_gamma_dol, "type": "MaxGamma", "width": 3, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})
    walls.append({"price": min_gamma_dol, "type": "MinGamma", "width": 3, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})
    walls.append({"price": round(float(flip_dol), 2), "type": "GammaFlip", "width": 2, "gex": 0.0, "gex_share": 0.0, "rank_abs_gex": 0})

    shares_sorted = sorted((w["gex_share"] for w in walls_basic), reverse=True)
    meta = {
        "spot_ref": round(float(current_wdo), 2),
        "gamma_flip": round(float(flip_dol), 2),
        "max_gamma": round(float(max_gamma_dol), 2),
        "min_gamma": round(float(min_gamma_dol), 2),
        "total_abs_gex_16": float(total_abs_16),
        "total_net_gex_16": float(total_net_16),
        "call_walls_cnt": call_cnt,
        "put_walls_cnt": put_cnt,
        "top1_share": round(shares_sorted[0], 6) if shares_sorted else 0.0,
        "top3_share": round(sum(shares_sorted[:3]), 6) if shares_sorted else 0.0,
    }
    return walls, meta


def write_signed_csv(path: str, hist_map: dict[str, list[dict]]):
    lines = ["session_date;type;price;width;gex;gex_share;rank_abs_gex"]
    for d in sorted(hist_map):
        for w in hist_map[d]:
            lines.append(
                f"{d};{_norm_wall_type(w['type'])};{float(w['price']):.2f};"
                f"{int(w['width'])};{float(w['gex']):.2f};{float(w['gex_share']):.6f};{int(w['rank_abs_gex'])}"
            )
    with open(path, "w", encoding="ascii", errors="ignore") as f:
        f.write("\n".join(lines) + "\n")


def write_plain_csv(path: str, hist_map: dict[str, list[dict]]):
    lines = ["session_date;type;price;width"]
    for d in sorted(hist_map):
        for w in hist_map[d]:
            lines.append(f"{d};{_norm_wall_type(w['type'])};{float(w['price']):.2f};{int(w['width'])}")
    with open(path, "w", encoding="ascii", errors="ignore") as f:
        f.write("\n".join(lines) + "\n")


def assert_parity(signed_path: str, ref_path: str, label: str, wall_mid_only: bool = False):
    df_s = pd.read_csv(signed_path, sep=";")
    df_r = pd.read_csv(ref_path, sep=";")
    s_dates = sorted(df_s["session_date"].unique())
    r_dates = sorted(df_r["session_date"].unique())
    assert len(s_dates) == 215, f"{label}: esperado 215 sessoes, obtido {len(s_dates)}"
    assert s_dates == r_dates, f"{label}: datas divergentes"
    assert len(df_s) == len(df_r), f"{label}: linhas divergentes {len(df_s)} vs {len(df_r)}"

    max_diff = 0.0
    max_wm_diff = 0.0
    pos_gex_cnt = 0
    neg_gex_cnt = 0
    for d in s_dates:
        gs = df_s[df_s["session_date"] == d].sort_values(["type", "price", "width"]).reset_index(drop=True)
        gr = df_r[df_r["session_date"] == d].sort_values(["type", "price", "width"]).reset_index(drop=True)
        assert list(gs["type"]) == list(gr["type"]), f"{label} {d}: tipos divergentes"
        assert list(gs["width"]) == list(gr["width"]), f"{label} {d}: widths divergentes"
        wm_mask = gs["type"].isin(["Wall", "MidWall"])
        wm_diff = float(np.max(np.abs(gs.loc[wm_mask, "price"].to_numpy() - gr.loc[wm_mask, "price"].to_numpy())))
        if wm_diff > max_wm_diff:
            max_wm_diff = wm_diff
        assert wm_diff < 0.015, f"{label} {d}: diff Wall/MidWall {wm_diff:.4f} >= 0.015"
        diff = float(np.max(np.abs(gs["price"].to_numpy() - gr["price"].to_numpy())))
        if diff > max_diff:
            max_diff = diff
        if not wall_mid_only:
            assert diff < 0.015, f"{label} {d}: diff preco {diff:.4f} >= 0.015"

        ws = gs[gs["type"] == "Wall"]
        sh_sum = float(ws["gex_share"].sum())
        assert abs(sh_sum - 1.0) < 1e-4, f"{label} {d}: sum(gex_share)={sh_sum:.6f}"
        pos_gex_cnt += int((ws["gex"] > 0).sum())
        neg_gex_cnt += int((ws["gex"] < 0).sum())

        gf = gs[gs["type"] == "GammaFlip"]["price"].iloc[0]
        assert gf > 0.0, f"{label} {d}: GammaFlip invalido ({gf})"

    assert pos_gex_cnt > 0 and neg_gex_cnt > 0, f"{label}: gex sem sinais +/- ({pos_gex_cnt}, {neg_gex_cnt})"
    print(
        f"[PARITY OK] {label}: 215 sessoes, {len(df_s)} linhas, "
        f"max_wm_diff={max_wm_diff:.5f}, max_all_diff={max_diff:.5f}, +GEX={pos_gex_cnt}, -GEX={neg_gex_cnt}"
    )


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

    print(f"Construindo GEX assinado (WIN + WDO) para {len(dated_files)} pregoes ({START_DATE}..{END_DATE})...")

    win_hist, wdo_hist = {}, {}
    meta_rows = []
    win_prev_meta, wdo_prev_meta = None, None

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

        _, _, df_ib_v2, _, df_dol_fix = parse_csv_all_modes(ref_path, ref_obj, catalog)

        walls_w, meta_w = [], {}
        if not df_ib_v2.empty:
            df_fut = df_ib_v2[df_ib_v2["expiry"].str[:10] > session_str]
            df_use = df_fut if not df_fut.empty else df_ib_v2[df_ib_v2["expiry"].str[:10] >= ref_str]
            if not df_use.empty:
                front_exp = sorted(df_use["expiry"].unique())[0]
                exp_dt = datetime.date.fromisoformat(front_exp[:10])
                exp_days = max(1, int(np.busday_count(ref_str, exp_dt.isoformat())))
                walls_w, meta_w = calc_win_walls_signed(df_use, f_win, s_ibov, exp_days, r_selic, ref_obj)
        if not walls_w and win_hist:
            prev_d = max(win_hist.keys())
            walls_w = win_hist[prev_d]
            meta_w = dict(win_prev_meta)
        if walls_w:
            win_hist[session_str] = walls_w
            win_prev_meta = meta_w
            meta_rows.append({"asset": "WIN", "session_date": session_str, **meta_w})

        walls_d, meta_d = calc_dol_walls_signed(df_dol_fix, wdo_price, ref_obj)
        if not walls_d and wdo_hist:
            prev_d = max(wdo_hist.keys())
            walls_d = wdo_hist[prev_d]
            meta_d = dict(wdo_prev_meta)
        if walls_d:
            wdo_hist[session_str] = walls_d
            wdo_prev_meta = meta_d
            meta_rows.append({"asset": "WDO", "session_date": session_str, **meta_d})

        if (idx + 1) % 30 == 0 or (idx + 1) == len(dated_files):
            print(f"  [{idx + 1:3d}/{len(dated_files)}] {session_str} processado", flush=True)

    win_out = os.path.join(OUT_DIR, "win_prod_signed.csv")
    wdo_out = os.path.join(OUT_DIR, "wdo_prod_signed.csv")
    win_plain = os.path.join(OUT_DIR, "win_prod_plain.csv")
    wdo_plain = os.path.join(OUT_DIR, "wdo_prod_plain.csv")
    meta_out = os.path.join(OUT_DIR, "gex_daily_meta.csv")

    write_signed_csv(win_out, win_hist)
    write_signed_csv(wdo_out, wdo_hist)
    write_plain_csv(win_plain, win_hist)
    write_plain_csv(wdo_plain, wdo_hist)
    pd.DataFrame(meta_rows).to_csv(meta_out, index=False)

    assert_parity(win_out, os.path.join(OUT_DIR, "win_v2_b3_strikes.csv"), "WIN win_prod_signed vs win_v2_b3_strikes")
    assert_parity(win_out, win_plain, "WIN win_prod_signed vs win_prod_plain")
    assert_parity(wdo_out, os.path.join(OUT_DIR, "wdo_ablate_flip_only.csv"), "WDO wdo_prod_signed vs wdo_ablate_flip_only (Wall/MidWall exact)", wall_mid_only=True)
    assert_parity(wdo_out, wdo_plain, "WDO wdo_prod_signed vs wdo_prod_plain")
    print(f"Arquivos gerados: {win_out}, {wdo_out}, {win_plain}, {wdo_plain}, {meta_out}")


if __name__ == "__main__":
    main()
