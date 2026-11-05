import os
import sys
import glob
import json
import inspect
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT_DIR = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

SCRATCH_DIR = r"C:\Users\ryzen\.gemini\antigravity\brain\c2b74f00-91a2-46d9-a669-fdd6bd3e1379\scratch"
if SCRATCH_DIR not in sys.path:
    sys.path.insert(0, SCRATCH_DIR)

import research.optimizers.optimize_existing_16_setups as mod_est16
import research.optimizers.test_win_aligned_wdo_matrix as mod_aligned
import research.optimizers.optimize_structural_walls_pa as mod_pa
import research.optimizers.evaluate_and_optimize_wdo_16 as mod_wdo16
import research.optimizers.build_wdo_best_mix_portfolio as mod_wdo_mix
from research.discover_gex_nwe_setups import compute_nwe_series

# ==============================================================================
# PATCH IN-MEMORY DOS SIMULADORES PARA SUPORTAR FILTRO CAUSAL NA BARRA DE SINAL
# ==============================================================================
_ACTIVE_FILTER_BUY = None
_ACTIVE_FILTER_SELL = None

def _patch_function(mod, func_name, target_str, repl_str):
    src = inspect.getsource(getattr(mod, func_name))
    assert target_str in src, f"Target not found in {func_name}"
    new_src = src.replace(target_str, repl_str, 1)
    ns = dict(mod.__dict__)
    ns["_check_dash_filter"] = lambda b_idx, s_dir: (
        True if (_ACTIVE_FILTER_BUY is None or s_dir == 0)
        else (bool(_ACTIVE_FILTER_BUY[b_idx]) if s_dir == 1 else bool(_ACTIVE_FILTER_SELL[b_idx]))
    )
    exec(new_src, ns)
    setattr(mod, func_name, ns[func_name])

# 1. simulate_single_est_slot (usa b1_idx e sig_dir)
_patch_function(
    mod_est16,
    "simulate_single_est_slot",
    "        if sig_dir == 0:\n            idx += 1\n            continue",
    "        if not _check_dash_filter(b1_idx, sig_dir):\n            sig_dir = 0\n        if sig_dir == 0:\n            idx += 1\n            continue",
)

# 2. simulate_aligned_win_wdo_slot (usa b1_idx e sig_type/sig_dir)
_patch_function(
    mod_aligned,
    "simulate_aligned_win_wdo_slot",
    "        if sig_type is None:\n            idx += 1\n            continue",
    "        if not _check_dash_filter(b1_idx, sig_dir):\n            sig_type = None\n            sig_dir = 0\n        if sig_type is None:\n            idx += 1\n            continue",
)

# 3. simulate_structural_setup (usa i e sig_dir)
_patch_function(
    mod_pa,
    "simulate_structural_setup",
    "        if sig_dir == 0:\n            i += 1\n            continue",
    "        if not _check_dash_filter(i, sig_dir):\n            sig_dir = 0\n        if sig_dir == 0:\n            i += 1\n            continue",
)

# 4. simulate_single_wdo_slot (usa b1_idx e action/sig_dir)
_patch_function(
    mod_wdo16,
    "simulate_single_wdo_slot",
    "        if action is None:\n            idx += 1\n            continue",
    "        if not _check_dash_filter(b1_idx, sig_dir):\n            action = None\n            sig_dir = 0\n        if action is None:\n            idx += 1\n            continue",
)

# 5. simulate_decorrelated_wdo_family (usa b1 e sig)
_patch_function(
    mod_wdo_mix,
    "simulate_decorrelated_wdo_family",
    "        if sig == 0:\n            idx += 1\n            continue",
    "        if not _check_dash_filter(b1, sig):\n            sig = 0\n        if sig == 0:\n            idx += 1\n            continue",
)


# ==============================================================================
# CARREGA AS 124 SESSOES DO DASHBOARD E CALCULA EXATAMENTE AS METRICAS A.S.G / FLUXO
# ==============================================================================
def compute_dashboard_series_for_asset(m5_series, is_win: bool):
    fast_p = 5.0 if is_win else 4.0
    slow_p = 18.0 if is_win else 22.0
    w_cvd = 0.85
    w_price = 0.15
    smooth_a = 0.45 if is_win else 0.60
    flip_thr = 11.0

    alpha_fast = 2.0 / (fast_p + 1.0)
    alpha_slow = 2.0 / (slow_p + 1.0)
    alpha_band = 2.0 / (7.0 + 1.0)

    if not m5_series:
        return {}

    first_b = m5_series[0]
    first_c = float(first_b.get("close", 0.0))
    first_h = float(first_b.get("high", first_c))
    first_l = float(first_b.get("low", first_c))
    first_cvd = round(float(first_b.get("cvd_inst", 0.0)), 0)

    ema_p_high = first_h
    ema_p_low = first_l
    ema_atr = max(first_h - first_l, 40.0 if is_win else 1.5)
    ema_cvd_f = first_cvd
    ema_cvd_s = first_cvd
    ema_cvd_step = max(abs(float(first_b.get("inst_delta_bar", 0.0))), 2500.0 if is_win else 500.0)
    ema_hist = 0.0
    active_win_dir = 0

    out_by_tmin = {}
    prev_cvd = first_cvd
    prev_hist = 0.0

    for idx, b in enumerate(m5_series):
        ts_raw = int(b.get("time", 0))
        dt = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
        t_min = dt.hour * 60 + dt.minute

        o = float(b.get("open", b.get("close", 0.0)))
        h = float(b.get("high", o))
        l = float(b.get("low", o))
        c = float(b.get("close", o))
        inst_5m = float(b.get("inst_delta_bar", 0.0))
        delta_5m = float(b.get("delta_bar", 0.0))
        ret_5m = float(b.get("ret_delta_bar", 0.0))
        buy_v = float(b.get("buy_vol", 0.0))
        sell_v = float(b.get("sell_vol", 0.0))
        tot_v = buy_v + sell_v
        imb_5m = ((delta_5m / tot_v) * 100.0) if tot_v > 0 else 0.0
        cvd = round(float(b.get("cvd_inst", 0.0)), 0)

        inst_15m = sum(float(m5_series[k].get("inst_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))

        if idx == 0:
            prev_cvd = cvd - round(inst_5m, 0)

        rng_bar = max(round(h, 2) - round(l, 2), 15.0 if is_win else 0.5)
        ema_atr = alpha_band * rng_bar + (1.0 - alpha_band) * ema_atr
        ema_p_high = alpha_band * round(h, 2) + (1.0 - alpha_band) * ema_p_high
        ema_p_low = alpha_band * round(l, 2) + (1.0 - alpha_band) * ema_p_low

        p_upper_trava = round(ema_p_high + 0.35 * ema_atr, 2)
        p_lower_trava = round(ema_p_low - 0.35 * ema_atr, 2)
        p_mid_trava = round(0.5 * (p_upper_trava + p_lower_trava), 2)

        ema_cvd_f = alpha_fast * cvd + (1.0 - alpha_fast) * ema_cvd_f
        ema_cvd_s = alpha_slow * cvd + (1.0 - alpha_slow) * ema_cvd_s
        ema_cvd_step = alpha_band * max(abs(cvd - prev_cvd), 500.0 if is_win else 100.0) + (1.0 - alpha_band) * ema_cvd_step

        raw_cvd_osc = (ema_cvd_f - ema_cvd_s) / max(1.0, ema_cvd_step * 1.4)
        raw_price_osc = (round(c, 2) - p_mid_trava) / max(1.0, ema_atr * 0.9)
        raw_score = float(np.clip((w_cvd * raw_cvd_osc + w_price * raw_price_osc) * 55.0, -100.0, 100.0))
        ema_hist = smooth_a * raw_score + ((1.0 - smooth_a) * ema_hist)
        hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

        if active_win_dir == 0:
            if hist_val >= 4.0 or (cvd >= prev_cvd and round(c, 2) >= round(o, 2)):
                active_win_dir = 1
            else:
                active_win_dir = -1
        else:
            if active_win_dir == 1 and hist_val <= -flip_thr:
                active_win_dir = -1
            elif active_win_dir == -1 and hist_val >= flip_thr:
                active_win_dir = 1

        if active_win_dir == 1:
            candle_state = 1 if (round(c, 2) >= round(o, 2) or round(c, 2) >= p_mid_trava or cvd >= prev_cvd) else 0
        else:
            candle_state = -1 if (round(c, 2) <= round(o, 2) or round(c, 2) <= p_mid_trava or cvd <= prev_cvd) else 0

        out_by_tmin[t_min] = {
            "window_dir": active_win_dir,
            "flow_hist": hist_val,
            "hist_slope": hist_val - prev_hist,
            "candle_state": candle_state,
            "inst_5m": inst_5m,
            "inst_15m": inst_15m,
            "delta_5m": delta_5m,
            "ret_5m": ret_5m,
            "imb_5m": imb_5m,
            "cvd_inst": cvd,
            "prev_cvd": prev_cvd,
        }
        prev_cvd = cvd
        prev_hist = hist_val

    return out_by_tmin


def load_all_dashboard_features():
    files = sorted(glob.glob(os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1", "*.json")))
    dash_win = {}
    dash_wdo = {}
    for f in files:
        s_date = os.path.basename(f).replace(".json", "")
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        win_s = data.get("WIN", {}).get("m5_cvd_series", [])
        wdo_s = data.get("WDO", {}).get("m5_cvd_series", [])
        dash_win[s_date] = compute_dashboard_series_for_asset(win_s, is_win=True)
        dash_wdo[s_date] = compute_dashboard_series_for_asset(wdo_s, is_win=False)
    return dash_win, dash_wdo


def align_dashboard_arrays(df: pd.DataFrame, dash_map: dict, is_win: bool):
    n = len(df)
    dates = df["session_date"].values
    t_mins = df["t_min"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    window_dir = np.zeros(n, dtype=int)
    flow_hist = np.zeros(n, dtype=float)
    hist_slope = np.zeros(n, dtype=float)
    candle_state = np.zeros(n, dtype=int)
    inst_5m = np.zeros(n, dtype=float)
    inst_15m = np.zeros(n, dtype=float)
    delta_5m = np.zeros(n, dtype=float)
    ret_5m = np.zeros(n, dtype=float)
    imb_5m = np.zeros(n, dtype=float)
    has_dash = np.zeros(n, dtype=bool)

    for i in range(n):
        d = str(dates[i])
        tm = int(t_mins[i])
        if d in dash_map and tm in dash_map[d]:
            info = dash_map[d][tm]
            window_dir[i] = info["window_dir"]
            flow_hist[i] = info["flow_hist"]
            hist_slope[i] = info["hist_slope"]
            candle_state[i] = info["candle_state"]
            inst_5m[i] = info["inst_5m"]
            inst_15m[i] = info["inst_15m"]
            delta_5m[i] = info["delta_5m"]
            ret_5m[i] = info["ret_5m"]
            imb_5m[i] = info["imb_5m"]
            has_dash[i] = True

    rng = np.maximum(highs - lows, 5.0 if is_win else 0.5)
    lower_wick = np.minimum(opens, closes) - lows
    upper_wick = highs - np.maximum(opens, closes)

    return {
        "has_dash": has_dash,
        "window_dir": window_dir,
        "flow_hist": flow_hist,
        "hist_slope": hist_slope,
        "candle_state": candle_state,
        "inst_5m": inst_5m,
        "inst_15m": inst_15m,
        "delta_5m": delta_5m,
        "ret_5m": ret_5m,
        "imb_5m": imb_5m,
        "rng": rng,
        "lower_wick": lower_wick,
        "upper_wick": upper_wick,
        "opens": opens,
        "closes": closes,
    }


def build_filter_masks(feat: dict, is_win: bool):
    hd = feat["has_dash"]
    wdir = feat["window_dir"]
    fhist = feat["flow_hist"]
    hslope = feat["hist_slope"]
    i5 = feat["inst_5m"]
    i15 = feat["inst_15m"]
    d5 = feat["delta_5m"]
    rng = feat["rng"]
    lwick = feat["lower_wick"]
    uwick = feat["upper_wick"]
    opens = feat["opens"]
    closes = feat["closes"]

    n = len(hd)
    all_true = np.ones(n, dtype=bool)

    # 1. JANELA_ASG: Estritamente a favor da Janela A.S.G (Compra na Janela Verde, Venda na Janela Vermelha)
    b_win_strict = (~hd) | (wdir == 1)
    s_win_strict = (~hd) | (wdir == -1)

    # 2. JANELA_SEM_EXPLOSAO_CONTRA: Janela a favor OU desacelerando/sem explosao contra (flow_hist >= -15 ou subindo)
    b_win_noconf = (~hd) | (wdir == 1) | (fhist >= -14.0) | (hslope >= 0.0)
    s_win_noconf = (~hd) | (wdir == -1) | (fhist <= 14.0) | (hslope <= 0.0)

    # 3. FLUXO_INST_PURO: Fluxo institucional 5m ou 15m a favor
    b_inst_pure = (~hd) | (i5 >= 0.0) | (i15 >= 0.0)
    s_inst_pure = (~hd) | (i5 <= 0.0) | (i15 <= 0.0)

    # 4. FLUXO_OU_ABSORCAO: Fluxo Institucional a favor OU Absorcao no Pavio (bateram contra mas absorveram no pavio/fechamento)
    abs_buy = (lwick >= 0.22 * rng) | (closes >= opens)
    abs_sell = (uwick >= 0.22 * rng) | (closes <= opens)
    crash_thr = -12000.0 if is_win else -800.0
    surge_thr = 12000.0 if is_win else 800.0

    b_flow_abs = (~hd) | (((i5 >= 0.0) | (d5 >= 0.0) | abs_buy) & (i5 >= crash_thr))
    s_flow_abs = (~hd) | (((i5 <= 0.0) | (d5 <= 0.0) | abs_sell) & (i5 <= surge_thr))

    # 5. COMBO_JANELA_E_FLUXO (Estrito: Janela A.S.G == Dir + Fluxo/Absorcao)
    b_combo_strict = b_win_strict & b_flow_abs
    s_combo_strict = s_win_strict & s_flow_abs

    # 6. COMBO_DASHBOARD_INTELIGENTE (Janela s/ Explosao Contra + Fluxo/Absorcao Institucional)
    b_combo_smart = b_win_noconf & b_flow_abs
    s_combo_smart = s_win_noconf & s_flow_abs

    return {
        "0_BASE_MT5":         (None, None),
        "1_JANELA_ASG":       (b_win_strict, s_win_strict),
        "2_JANELA_S_EXPLOSAO":(b_win_noconf, s_win_noconf),
        "3_FLUXO_INST":       (b_inst_pure, s_inst_pure),
        "4_FLUXO_ABSORCAO":   (b_flow_abs, s_flow_abs),
        "5_COMBO_ESTRITO":    (b_combo_strict, s_combo_strict),
        "6_COMBO_SMART":      (b_combo_smart, s_combo_smart),
    }


# ==============================================================================
# SIMULADORES DAS 12 ESTRATEGIAS WIN E 10 ESTRATEGIAS WDO ATIVAS NO MT5
# ==============================================================================
def find_next_wall_behind(entry_px: float, side: int, lvls: np.ndarray, min_step: float, max_step: float, default_step: float):
    if side == 1:
        cands = lvls[(lvls <= entry_px - min_step) & (lvls >= entry_px - max_step)]
        return float(cands[-1]) if len(cands) > 0 else (entry_px - default_step)
    else:
        cands = lvls[(lvls >= entry_px + min_step) & (lvls <= entry_px + max_step)]
        return float(cands[0]) if len(cands) > 0 else (entry_px + default_step)

def precompute_grid_bars(df, gex_map, n50_u, n50_l, n50_s, n30_u, n30_l, rsi7, min_date):
    dates = df["session_date"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values
    n = len(df)
    dl_arr = np.full(n, 999999.0)
    dh_arr = np.full(n, 999999.0)
    ls_arr = np.zeros(n)
    lr_arr = np.zeros(n)
    gf_arr = np.zeros(n)
    valid_arr = np.zeros(n, dtype=bool)
    for i in range(1, n):
        d = dates[i]
        if d < min_date or d not in gex_map or dates[i-1] != d:
            continue
        g = gex_map[d]
        lvls = g["all_levels"]
        if len(lvls) == 0:
            continue
        valid_arr[i] = True
        dl_arr[i-1], ls_arr[i-1] = mod_wdo16.find_nearest_level(lvls, lows[i-1])
        dh_arr[i-1], lr_arr[i-1] = mod_wdo16.find_nearest_level(lvls, highs[i-1])
        gf_arr[i-1] = g["gamma_flip"] or 0.0
    bw50 = np.maximum(1e-3, n50_u - n50_l)
    pos50 = (closes - n50_l) / bw50
    bw30 = np.maximum(1e-3, n30_u - n30_l)
    pos30 = (closes - n30_l) / bw30
    w_bot = np.minimum(opens, closes) - lows
    w_top = highs - np.maximum(opens, closes)
    return dict(
        dates=dates, opens=opens, highs=highs, lows=lows, closes=closes, t_mins=t_mins,
        dl=dl_arr, dh=dh_arr, ls=ls_arr, lr=lr_arr, gf=gf_arr, valid=valid_arr,
        pos50=pos50, pos30=pos30, slp50=n50_s, rsi7=rsi7, w_bot=w_bot, w_top=w_top
    )

def sim_smart_grid(pb, gex_map, sig_arr, def_w_arr, cfg, is_wdo: bool, f_buy=None, f_sell=None):
    dates = pb["dates"]
    opens = pb["opens"]
    highs = pb["highs"]
    lows = pb["lows"]
    closes = pb["closes"]
    t_mins = pb["t_mins"]
    valid = pb["valid"]

    t_start, t_end = cfg["t_range"]
    ent_mode = cfg["ent_mode"]
    leg2_mode = cfg["leg2_mode"]
    min_step, max_step, def_step = cfg["step_cfg"]
    lot2 = cfg["lot2"]
    tp1_cap = cfg.get("tp1_cap", 999999.0)
    tp2_pts = cfg["tp2_pts"]
    sl2_pts = cfg["sl2_pts"]
    be1_trig = cfg["be1_trig"]
    be2_trig = cfg["be2_trig"]
    max_per_day = cfg["max_per_day"]
    max_hold = cfg.get("max_hold", 20)
    rnd = mod_wdo16.round05 if is_wdo else mod_est16.round5
    slip = 0.5 if is_wdo else 15.0
    mult_brl = 10.0 if is_wdo else 0.20
    be_buf = 1.0 if is_wdo else 20.0
    be2_lock = 0.5 if is_wdo else 15.0
    pad = 0.5 if is_wdo else 20.0

    trades = []
    n = len(dates)
    idx = 2
    day_cnt = {}

    while idx < n - 1:
        if not valid[idx]:
            idx += 1
            continue
        b1 = idx - 1
        sig = int(sig_arr[b1])
        if f_buy is not None and ((sig == 1 and not f_buy[b1]) or (sig == -1 and not f_sell[b1])):
            sig = 0
        if sig == 0:
            idx += 1
            continue
        d_str = dates[idx]
        if day_cnt.get(d_str, 0) >= max_per_day:
            idx += 1
            continue
        tm = int(t_mins[b1])
        if not (t_start <= tm <= t_end):
            idx += 1
            continue

        def_w = def_w_arr[b1]
        bh, bl = highs[b1], lows[b1]
        filled, fbar, p1 = False, idx, 0.0
        if ent_mode == "MKT":
            filled, fbar, p1 = True, idx, rnd(opens[idx])
        else:
            for v in range(2):
                eb = idx + v
                if eb >= n or dates[eb] != d_str or int(t_mins[eb]) >= 1005:
                    break
                op = rnd(0.5 * (bh + bl)) if ent_mode == "LIM_MID" else (rnd(bl + (0.5 if is_wdo else 10.0)) if sig == 1 else rnd(bh - (0.5 if is_wdo else 10.0)))
                if (sig == 1 and opens[eb] >= op and lows[eb] <= op) or (sig == -1 and opens[eb] <= op and highs[eb] >= op):
                    filled, fbar, p1 = True, eb, op
                    break
        if not filled:
            idx += 1
            continue

        g = gex_map[d_str]
        p2 = rnd(find_next_wall_behind(p1, sig, g["all_levels"], min_step, max_step, def_step)) if leg2_mode == "NEXT_WALL" else (rnd(p1 - def_step) if sig == 1 else rnd(p1 + def_step))
        c_sl = rnd(p2 - sl2_pts) if sig == 1 else rnd(p2 + sl2_pts)
        if is_wdo:
            tm_px, _, _, _ = mod_wdo16.find_wdo_structural_targets(p1, sig, g["walls"], g["all_levels"], 0.5)
        else:
            tm_px, _, _, _ = mod_est16.find_structural_targets(p1, sig, g["walls"], g["all_levels"], 20.0)
        c_tp = min(tm_px, rnd(p1 + tp1_cap)) if sig == 1 else max(tm_px, rnd(p1 - tp1_cap))

        lots, leg = 1, 1
        avg_p = p1
        mfav, bea = 0.0, False
        k, bh_cnt = fbar, 0
        ex_px = closes[fbar]

        while k < n:
            if dates[k] != d_str or int(t_mins[k]) >= 1035:
                ex_px = opens[k] if dates[k] == d_str else closes[k - 1]
                break
            if leg == 1 and not bea:
                if (sig == 1 and lows[k] <= p2) or (sig == -1 and highs[k] >= p2):
                    tot_l = 1 + lot2
                    avg_p = rnd((p1 * 1.0 + p2 * lot2) / tot_l)
                    lots, leg, mfav, bea = tot_l, 2, 0.0, False
                    c_tp = rnd(avg_p + tp2_pts) if sig == 1 else rnd(avg_p - tp2_pts)
                    c_sl = rnd(p2 - sl2_pts) if sig == 1 else rnd(p2 + sl2_pts)

            if (sig == 1 and lows[k] <= c_sl) or (sig == -1 and highs[k] >= c_sl):
                ex_px = c_sl
                break
            if (sig == 1 and highs[k] >= c_tp) or (sig == -1 and lows[k] <= c_tp):
                ex_px = c_tp
                break

            bh_cnt += 1
            fav = (highs[k] - avg_p) if sig == 1 else (avg_p - lows[k])
            if fav > mfav:
                mfav = fav

            if k + 1 < n and dates[k + 1] == d_str:
                no = opens[k + 1]
                trig = be1_trig if leg == 1 else be2_trig
                if not bea and mfav >= trig:
                    if leg == 1:
                        w_sl = rnd(def_w - be_buf) if sig == 1 else rnd(def_w + be_buf)
                        lock_sl = rnd(avg_p + be_buf) if sig == 1 else rnd(avg_p - be_buf)
                        cand_sl = max(w_sl, lock_sl) if sig == 1 else min(w_sl, lock_sl)
                    else:
                        cand_sl = rnd(avg_p + be2_lock) if sig == 1 else rnd(avg_p - be2_lock)
                    if (sig == 1 and cand_sl > c_sl and no > cand_sl + pad) or (sig == -1 and cand_sl < c_sl and no < cand_sl - pad):
                        c_sl = cand_sl
                        bea = True
                if bh_cnt >= max_hold:
                    ex_px = no
                    k += 1
                    break
            k += 1

        pts_unit = (ex_px - avg_p) * sig - slip
        pts_tot = pts_unit * lots
        trades.append({
            "date": d_str, "side": sig, "contracts": float(lots), "leg_reached": leg,
            "pnl_pts": float(pts_tot), "pnl_brl": float(pts_tot * mult_brl),
            "pnl_1c_brl": float(pts_unit * mult_brl),
        })
        day_cnt[d_str] = day_cnt.get(d_str, 0) + 1
        idx = max(idx + 1, k + 1)

    return trades


def run_win_strategy(est_id, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s, f_buy=None, f_sell=None):
    global _ACTIVE_FILTER_BUY, _ACTIVE_FILTER_SELL
    _ACTIVE_FILTER_BUY = f_buy
    _ACTIVE_FILTER_SELL = f_sell

    # Smart Grids >=100 trades ativados no MT5 (EST-13 e EST-14)
    if est_id == 13:
        dlw, dhw, lsw, lrw = pb_win["dl"], pb_win["dh"], pb_win["ls"], pb_win["lr"]
        bow, bcw, pos50w, wzw = pb_win["opens"], pb_win["closes"], pb_win["pos50"], pb_win["wdo_z"]
        b_est13 = (dlw <= 80.0) & (pos50w <= 0.45) & (wzw <= 0.35) & (bcw > lsw) & (bcw > bow)
        s_est13 = (dhw <= 80.0) & (pos50w >= 0.55) & (wzw >= -0.35) & (bcw < lrw) & (bcw < bow)
        cfg_est13 = dict(fam="WIN_G5_CROSS_WDO", t_range=(545, 975), ent_mode="LIM_MID", leg2_mode="NEXT_WALL", step_cfg=(140.0, 280.0, 190.0), lot2=2, tp1_cap=220.0, tp2_pts=170.0, sl2_pts=175.0, be1_trig=130.0, be2_trig=90.0, max_per_day=5, max_hold=18)
        tr = sim_smart_grid(pb_win, gex_win, np.where(b_est13, 1, np.where(s_est13, -1, 0)), np.where(b_est13, lsw, lrw), cfg_est13, is_wdo=False, f_buy=f_buy, f_sell=f_sell)
    elif est_id == 14:
        dlw, dhw, lsw, lrw = pb_win["dl"], pb_win["dh"], pb_win["ls"], pb_win["lr"]
        bow, bcw, pos50w, w_botw, w_topw = pb_win["opens"], pb_win["closes"], pb_win["pos50"], pb_win["w_bot"], pb_win["w_top"]
        b_est14 = (dlw <= 75.0) & (w_botw >= 25.0) & (pos50w <= 0.48) & (bcw >= bow) & (bcw > lsw - 15.0)
        s_est14 = (dhw <= 75.0) & (w_topw >= 25.0) & (pos50w >= 0.52) & (bcw <= bow) & (bcw < lrw + 15.0)
        cfg_est14 = dict(fam="WIN_G3_WICK_DEFENSE", t_range=(545, 1005), ent_mode="LIM_MID", leg2_mode="NEXT_WALL", step_cfg=(140.0, 280.0, 190.0), lot2=2, tp1_cap=220.0, tp2_pts=170.0, sl2_pts=175.0, be1_trig=130.0, be2_trig=90.0, max_per_day=3, max_hold=18)
        tr = sim_smart_grid(pb_win, gex_win, np.where(b_est14, 1, np.where(s_est14, -1, 0)), np.where(b_est14, lsw, lrw), cfg_est14, is_wdo=False, f_buy=f_buy, f_sell=f_sell)
    elif est_id == 4:
        tr, _ = mod_aligned.simulate_aligned_win_wdo_slot(
            4, df_win, gex_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            be_mode="BE_WALL_2STAGE_177K", wall_shield_buf=15.0, tp_mode="TP_MIDWALL", entry_override="ALIGNED", replace_13_16_pa=False
        )
    elif est_id in (11, 16):
        fid = 4 if est_id == 11 else 3
        specs = {
            3: ("PULLBACK_SLOPE",  "ROLLING_STOP_PREV_BAR", 15.0, 2, 230.0, "BE_TWO_STAGE_WALLS", 130.0, 25.0, "TP_PARTIAL_MID_MAIN", 20.0),
            4: ("HYBRID_WALL_NWE", "STOP_PREV_BAR",         15.0, 2, 230.0, "BE_WALL_SHIELD",     130.0, 25.0, "TP_REAL_MIDWALL",     20.0),
        }
        sm, et, eoff, vb, sl_i, bm, btrig, buf, tm, fr = specs[fid]
        raw_tr, _ = mod_pa.simulate_structural_setup(
            df_win, gex_win, n50_c, n50_u, n50_l, n50_s, rsi7s,
            signal_mode=sm, entry_type=et, entry_off=eoff, valid_bars=vb,
            sl_init_pts=sl_i, be_mode=bm, be_trigger_pts=btrig, wall_shield_buf=buf,
            tp_mode=tm, front_run_pts=fr,
        )
        tr = [{
            "date": t["date"], "side": t["side"], "contracts": 2.0,
            "pnl_pts": t["pnl_pts"] * 2.0, "pnl_brl": t["pnl_pts"] * 2.0 * 0.20,
            "pnl_1c_brl": t["pnl_pts"] * 0.20,
        } for t in raw_tr]
    else:
        opt_3p_win = {
            1:  ("CURRENT",      "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
            2:  ("LIMIT_B1_MID", "BE_ZERO",         0.0, "TP_MAIN_WALL"),
            6:  ("STOP_B1_EXT",  "BE_WALL_SHIELD", 15.0, "TP_MAIN_WALL"),
            7:  ("CURRENT",      "BE_WALL_SHIELD", 15.0, "TP_CURRENT"),
            8:  ("CURRENT",      "BE_ZERO",         0.0, "TP_MAIN_WALL"),
            12: ("CURRENT",      "BE_ZERO",         0.0, "TP_MAIN_WALL"),
            15: ("STOP_B1_EXT",  "BE_WALL_SHIELD", 15.0, "TP_MAIN_WALL"),
        }
        e3, b3, bf3, t3 = opt_3p_win[est_id]
        tr, _ = mod_est16.simulate_single_est_slot(
            est_id, df_win, gex_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override=e3, be_mode=b3, wall_shield_buf=bf3, tp_mode=t3
        )

    for x in tr:
        x["slot"] = f"EST-{est_id:02d}"
        if "pnl_1c_brl" not in x:
            c_l = max(1.0, float(x.get("contracts", 1.0)))
            x["pnl_1c_brl"] = float(x["pnl_brl"]) / c_l
    _ACTIVE_FILTER_BUY = None
    _ACTIVE_FILTER_SELL = None
    return tr


def run_wdo_strategy(sid, df_wdo, gex_wdo, pb_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, f_buy=None, f_sell=None):
    global _ACTIVE_FILTER_BUY, _ACTIVE_FILTER_SELL
    _ACTIVE_FILTER_BUY = f_buy
    _ACTIVE_FILTER_SELL = f_sell

    if sid == 11:
        dl, dh, ls, lr = pb_wdo["dl"], pb_wdo["dh"], pb_wdo["ls"], pb_wdo["lr"]
        bo, bc, pos50, gf = pb_wdo["opens"], pb_wdo["closes"], pb_wdo["pos50"], pb_wdo["gf"]
        b_wdo11 = (dl <= 6.0) & (gf > 0) & (bc < gf - 3.0) & (pos50 <= 0.42) & (bc > bo)
        s_wdo11 = (dh <= 6.0) & (gf > 0) & (bc > gf + 3.0) & (pos50 >= 0.58) & (bc < bo)
        sig_wdo11 = np.where(b_wdo11, 1, np.where(s_wdo11, -1, 0))
        def_wdo11 = np.where(b_wdo11, ls, lr)
        cfg_wdo11 = dict(fam="WDO_G6_GF_WALL", t_range=(545, 975), ent_mode="LIM_MID", leg2_mode="NEXT_WALL", step_cfg=(8.0, 16.0, 11.0), lot2=2, tp1_cap=999.0, tp2_pts=4.5, sl2_pts=7.0, be1_trig=6.0, be2_trig=2.5, max_per_day=2, max_hold=20)
        tr = sim_smart_grid(pb_wdo, gex_wdo, sig_wdo11, def_wdo11, cfg_wdo11, is_wdo=True, f_buy=f_buy, f_sell=f_sell)
    elif sid in (3, 4, 6, 8, 9, 16):
        pa_specs_wdo = {
            3: dict(fam="WIN_ARB_WALL", wmode="CORE_09_1615", use_main_walls=True, ent_mode="LIM_MID", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MID"),
            4: dict(fam="WDO04_MAIN", wmode="FULL_09_17", use_main_walls=True, ent_mode="LIM_MID", vb_max=1, sl_pts=14.0, be_trig=7.5, buf=1.5, tp_mode="MAIN"),
            6: dict(fam="RSI_WALL", wmode="NO_LUNCH", use_main_walls=False, ent_mode="LIM_EXT", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MID"),
            8: dict(fam="WALL_ABS_LIMIT", wmode="NO_LUNCH", use_main_walls=True, ent_mode="LIM_MID", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MAIN"),
            9: dict(fam="MAIN_WALL_CLUSTER", wmode="NO_LUNCH", use_main_walls=False, ent_mode="LIM_WALL", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MID"),
            16: dict(fam="WDO16_EOD_MAIN", wmode="FULL_09_17", use_main_walls=True, ent_mode="LIM_MID", vb_max=1, sl_pts=20.0, be_trig=11.5, buf=1.5, tp_mode="MID"),
        }
        tr, _ = mod_wdo_mix.simulate_decorrelated_wdo_family(
            sid, df_wdo, gex_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, **pa_specs_wdo[sid]
        )
    else:
        opt_3p_wdo = {
            2:  ("LIMIT_B1_EXT", "BE_WALL_2STAGE", 1.0, "TP_MIDWALL"),
            7:  ("CURRENT",      "BE_WALL_SHIELD", 1.0, "TP_MIDWALL"),
            15: ("LIMIT_B1_EXT", "BE_WALL_SHIELD", 1.0, "TP_CURRENT"),
        }
        em, bm, buf, tm = opt_3p_wdo[sid]
        tr, _ = mod_wdo16.simulate_single_wdo_slot(
            sid, df_wdo, gex_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s,
            entry_override=em, be_mode=bm, wall_shield_buf=buf, tp_mode=tm
        )

    for x in tr:
        x["slot"] = f"WDO-{sid:02d}"
        if "pnl_1c_brl" not in x:
            c_l = max(1.0, float(x.get("contracts", 1.0)))
            x["pnl_1c_brl"] = float(x["pnl_brl"]) / c_l
    _ACTIVE_FILTER_BUY = None
    _ACTIVE_FILTER_SELL = None
    return tr


def calc_metrics(trades_list, all_dates, col_pnl="pnl_brl"):
    if not trades_list:
        return dict(trades=0, wr=0.0, pf=0.0, net=0.0, mdd=999999.0, ret_dd=0.0, pos_months=0)
    df_t = pd.DataFrame(trades_list)
    daily_pnl = df_t.groupby("date")[col_pnl].sum().reindex(all_dates, fill_value=0.0)
    eq_daily = daily_pnl.cumsum().values
    pk_daily = np.maximum.accumulate(np.maximum(0.0, eq_daily))
    mdd = float(np.max(pk_daily - eq_daily))
    p = df_t[col_pnl].values
    w = p[p > 0]
    l = p[p < 0]
    wr = len(w) / len(p) * 100.0 if len(p) > 0 else 0.0
    pf = float(w.sum() / abs(l.sum())) if len(l) > 0 and abs(l.sum()) > 0 else 99.9
    net = float(p.sum())
    ret_dd = net / mdd if mdd > 0 else (99.9 if net > 0 else 0.0)
    df_t["ym"] = df_t["date"].str.slice(0, 7)
    m_pnl = df_t.groupby("ym")[col_pnl].sum()
    pos_m = int((m_pnl > 0).sum())
    return dict(
        trades=len(df_t),
        wr=round(wr, 1),
        pf=round(pf, 2),
        net=round(net, 0),
        mdd=round(mdd, 0),
        ret_dd=round(ret_dd, 2),
        pos_months=pos_m,
    )


if __name__ == "__main__":
    dash_win_map, dash_wdo_map = load_all_dashboard_features()

    df_win, gex_win = mod_est16.load_win_and_wdo_aligned()
    for d, g in gex_win.items():
        g["all_levels"] = np.sort(np.concatenate([g["walls"], g["mid_walls"]])) if len(g["mid_walls"]) > 0 else g["walls"]
    closes_w = df_win["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes_w, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes_w, lookback=30, bw=3.0, mult=1.6)
    dp_w = pd.Series(closes_w).diff()
    rsi7s_w = (100.0 - (100.0 / (1.0 + (dp_w.clip(lower=0).rolling(7).mean() / (-dp_w.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    df_wdo, gex_wdo = mod_wdo16.load_wdo_and_win_aligned()
    closes_d = df_wdo["close"].values
    d_n50_c, d_n50_u, d_n50_l, _, d_n50_s = compute_nwe_series(closes_d, lookback=50, bw=5.0, mult=2.0)
    d_n30_c, d_n30_u, d_n30_l, _, d_n30_s = compute_nwe_series(closes_d, lookback=30, bw=3.0, mult=1.6)
    dp_d = pd.Series(closes_d).diff()
    d_rsi7s = (100.0 - (100.0 / (1.0 + (dp_d.clip(lower=0).rolling(7).mean() / (-dp_d.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    pb_win = precompute_grid_bars(df_win, gex_win, n50_u, n50_l, n50_s, n30_u, n30_l, rsi7s_w, "2026-05-11")
    pb_win["wdo_z"] = df_win["wdo_z"].values
    pb_wdo = precompute_grid_bars(df_wdo, gex_wdo, d_n50_u, d_n50_l, d_n50_s, d_n30_u, d_n30_l, d_rsi7s, "2026-05-07")
    pb_wdo["win_z"] = df_wdo["win_z"].values

    d_feat_win = align_dashboard_arrays(df_win, dash_win_map, is_win=True)
    d_feat_wdo = align_dashboard_arrays(df_wdo, dash_wdo_map, is_win=False)

    win_filters = build_filter_masks(d_feat_win, is_win=True)
    wdo_filters = build_filter_masks(d_feat_wdo, is_win=False)

    all_dates = sorted(gex_wdo.keys())
    win_active_ids = [1, 2, 4, 6, 7, 8, 11, 12, 13, 14, 15, 16]
    wdo_active_ids = [2, 3, 4, 6, 7, 8, 9, 11, 15, 16]

    win_trades_by_f = {fname: {} for fname in win_filters}
    wdo_trades_by_f = {fname: {} for fname in wdo_filters}

    for fname, (fb, fs) in win_filters.items():
        for eid in win_active_ids:
            win_trades_by_f[fname][eid] = run_win_strategy(
                eid, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, f_buy=fb, f_sell=fs
            )

    for fname, (fb, fs) in wdo_filters.items():
        for sid in wdo_active_ids:
            wdo_trades_by_f[fname][sid] = run_wdo_strategy(
                sid, df_wdo, gex_wdo, pb_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, f_buy=fb, f_sell=fs
            )

    print("\n================ RESUMO PORTFOLIO WIN (12 ROBOS ATIVOS) POR FILTRO DO DASHBOARD ================")
    for fname in win_filters:
        all_tr = [x for eid in win_active_ids for x in win_trades_by_f[fname][eid]]
        m_orig = calc_metrics(all_tr, all_dates, "pnl_brl")
        m_1c = calc_metrics(all_tr, all_dates, "pnl_1c_brl")
        print(f"{fname:22s} | Tr={m_orig['trades']:4d} | WR={m_orig['wr']:4.1f}% | PF={m_orig['pf']:4.2f} | Net(MT5)=R${m_orig['net']:6.0f} (MDD=R${m_orig['mdd']:4.0f}, Ret/DD={m_orig['ret_dd']:5.2f}) | Net(1C)=R${m_1c['net']:6.0f} (Ret/DD={m_1c['ret_dd']:5.2f})")

    print("\n================ RESUMO PORTFOLIO WDO (9 ROBOS WF CAMPEAO: s/ WDO-06) POR FILTRO DO DASHBOARD ================")
    wdo_9_ids = [2, 3, 4, 7, 8, 9, 11, 15, 16]
    for fname in wdo_filters:
        all_tr = [x for sid in wdo_9_ids for x in wdo_trades_by_f[fname][sid]]
        m_orig = calc_metrics(all_tr, all_dates, "pnl_brl")
        m_1c = calc_metrics(all_tr, all_dates, "pnl_1c_brl")
        print(f"{fname:22s} | Tr={m_orig['trades']:4d} | WR={m_orig['wr']:4.1f}% | PF={m_orig['pf']:4.2f} | Net(MT5)=R${m_orig['net']:6.0f} (MDD=R${m_orig['mdd']:4.0f}, Ret/DD={m_orig['ret_dd']:5.2f}) | Net(1C)=R${m_1c['net']:6.0f} (Ret/DD={m_1c['ret_dd']:5.2f})")

    print("\n================ DETALHE INDIVIDUAL WIN (12 ROBOS): BASE_MT5 vs JANELA_ASG vs FLUXO_ABSORCAO vs COMBO_SMART ================")
    for eid in win_active_ids:
        b0 = calc_metrics(win_trades_by_f["0_BASE_MT5"][eid], all_dates, "pnl_brl")
        b1 = calc_metrics(win_trades_by_f["1_JANELA_ASG"][eid], all_dates, "pnl_brl")
        b3 = calc_metrics(win_trades_by_f["3_FLUXO_INST"][eid], all_dates, "pnl_brl")
        b4 = calc_metrics(win_trades_by_f["4_FLUXO_ABSORCAO"][eid], all_dates, "pnl_brl")
        b6 = calc_metrics(win_trades_by_f["6_COMBO_SMART"][eid], all_dates, "pnl_brl")
        print(
            f"EST-{eid:02d} | BASE: {b0['trades']:3d}tr R${b0['net']:5.0f} PF={b0['pf']:4.2f} R/DD={b0['ret_dd']:5.2f} | "
            f"JANELA: {b1['trades']:3d}tr R${b1['net']:5.0f} PF={b1['pf']:4.2f} R/DD={b1['ret_dd']:5.2f} | "
            f"INST: {b3['trades']:3d}tr R${b3['net']:5.0f} PF={b3['pf']:4.2f} R/DD={b3['ret_dd']:5.2f} | "
            f"ABS: {b4['trades']:3d}tr R${b4['net']:5.0f} PF={b4['pf']:4.2f} R/DD={b4['ret_dd']:5.2f} | "
            f"SMART: {b6['trades']:3d}tr R${b6['net']:5.0f} PF={b6['pf']:4.2f} R/DD={b6['ret_dd']:5.2f}"
        )

    print("\n================ DETALHE INDIVIDUAL WDO (10 ROBOS): BASE_MT5 vs JANELA_ASG vs FLUXO_ABSORCAO vs COMBO_SMART ================")
    for sid in wdo_active_ids:
        b0 = calc_metrics(wdo_trades_by_f["0_BASE_MT5"][sid], all_dates, "pnl_brl")
        b1 = calc_metrics(wdo_trades_by_f["1_JANELA_ASG"][sid], all_dates, "pnl_brl")
        b3 = calc_metrics(wdo_trades_by_f["3_FLUXO_INST"][sid], all_dates, "pnl_brl")
        b4 = calc_metrics(wdo_trades_by_f["4_FLUXO_ABSORCAO"][sid], all_dates, "pnl_brl")
        b6 = calc_metrics(wdo_trades_by_f["6_COMBO_SMART"][sid], all_dates, "pnl_brl")
        print(
            f"WDO-{sid:02d} | BASE: {b0['trades']:3d}tr R${b0['net']:5.0f} PF={b0['pf']:4.2f} R/DD={b0['ret_dd']:5.2f} | "
            f"JANELA: {b1['trades']:3d}tr R${b1['net']:5.0f} PF={b1['pf']:4.2f} R/DD={b1['ret_dd']:5.2f} | "
            f"INST: {b3['trades']:3d}tr R${b3['net']:5.0f} PF={b3['pf']:4.2f} R/DD={b3['ret_dd']:5.2f} | "
            f"ABS: {b4['trades']:3d}tr R${b4['net']:5.0f} PF={b4['pf']:4.2f} R/DD={b4['ret_dd']:5.2f} | "
            f"SMART: {b6['trades']:3d}tr R${b6['net']:5.0f} PF={b6['pf']:4.2f} R/DD={b6['ret_dd']:5.2f}"
        )
