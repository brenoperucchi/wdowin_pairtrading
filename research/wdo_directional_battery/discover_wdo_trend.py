"""
Bateria Anti-Overfitting de Descoberta: Robo Direcional / Seguidor de Tendencia no WDO (M5 + M1 Verify)
========================================================================================================
Objetivo:
  Encontrar 1 estrategia genuinamente direcional / trend-following no WDO (com trailing stop longo)
  que lucre especificamente nos "dias de furia" direcionais (30-70+ pts) onde WDO-01/05/07 (reversao)
  sofrem, passando nos 5 gates anti-overfitting (IS Jan-Jul, Blind OOS Ago-Nov, M1 exact verification,
  stress de custo 1.0 pt, estabilidade de vizinhanca e sinergia real com top_10 B3).
"""
import os
import sys
import json
import time
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.optimizers.wdo_mt5_sim import load_wdo_mt5_raw, round05
from research.discover_gex_nwe_setups import compute_nwe_series
from research.stop_diario.data_loader import load_portfolio_trades, load_m1_bars, PORTFOLIO_PRESETS


def _summarize_daily_pnls(pnls: list[float]) -> dict:
    arr = np.array(pnls, dtype=float)
    total = float(arr.sum()) if len(arr) else 0.0
    eq = np.cumsum(arr)
    peak = np.maximum.accumulate(np.insert(eq, 0, 0.0))[1:]
    dd = float(np.max(peak - eq)) if len(eq) else 0.0
    ret_dd = total / dd if dd > 0 else (99.0 if total > 0 else 0.0)
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    sharpe = (float(np.mean(arr)) / std) * np.sqrt(252.0) if std > 1e-9 else 0.0
    worst = float(np.min(arr)) if len(arr) else 0.0
    return {"total_pnl": total, "max_dd": dd, "ret_dd": ret_dd, "sharpe": sharpe, "worst_day": worst}

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "wdo_directional_battery")
os.makedirs(OUT_DIR, exist_ok=True)


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    tr = np.zeros(n, dtype=float)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = pd.Series(tr).rolling(period, min_periods=1).mean().values
    return atr


def prepare_wdo_features():
    """Carrega WDO M5 + GEX Walls + NWE50/NWE30 + contexto causal intraday (day_open, day_eff, ORB, ATR)."""
    df, gex_by_date = load_wdo_mt5_raw()
    df = df[(df["session_date"] >= "2026-01-02") & (df["session_date"] <= "2026-11-06")].reset_index(drop=True)

    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    opens = df["open"].values.astype(float)
    dates = df["session_date"].values
    t_mins = df["t_min"].values.astype(int)

    # Causal NWE50 and NWE30 (exact same as Jumba_WDO_GEX_NWE_Core.mqh)
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, 50, 5.0, 2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, 30, 3.0, 1.6)
    atr14 = compute_atr(highs, lows, closes, 14)

    n = len(df)
    day_open = np.zeros(n, dtype=float)
    day_high_so_far = np.zeros(n, dtype=float)
    day_low_so_far = np.zeros(n, dtype=float)
    day_move = np.zeros(n, dtype=float)
    day_eff = np.zeros(n, dtype=float)

    # Opening ranges: 30m (09:00-09:25 -> ready 09:30), 60m (09:00-09:55 -> ready 10:00)
    or30_h = np.full(n, np.nan)
    or30_l = np.full(n, np.nan)
    or60_h = np.full(n, np.nan)
    or60_l = np.full(n, np.nan)

    # Nearest wall arrays (for fast signal evaluation)
    near_wall = np.zeros(n, dtype=float)
    near_wall_dist = np.full(n, 999.0, dtype=float)
    gamma_flip = np.zeros(n, dtype=float)
    wall_above = np.full(n, np.nan, dtype=float)
    wall_below = np.full(n, np.nan, dtype=float)

    cur_d = ""
    d_open = 0.0
    d_h = -1e9
    d_l = 1e9
    o30h = -1e9
    o30l = 1e9
    o60h = -1e9
    o60l = 1e9
    cur_walls = np.array([], dtype=float)
    cur_gf = 0.0

    for i in range(n):
        d = dates[i]
        tm = t_mins[i]
        if d != cur_d:
            cur_d = d
            d_open = opens[i]
            d_h = highs[i]
            d_l = lows[i]
            o30h = -1e9
            o30l = 1e9
            o60h = -1e9
            o60l = 1e9
            g = gex_by_date.get(d)
            if g is not None:
                cur_walls = g["walls"]
                cur_gf = float(g["gamma_flip"])
            else:
                cur_walls = np.array([], dtype=float)
                cur_gf = 0.0
        else:
            if highs[i] > d_h:
                d_h = highs[i]
            if lows[i] < d_l:
                d_l = lows[i]

        if tm < 570:  # 09:00..09:25 bars
            if highs[i] > o30h:
                o30h = highs[i]
            if lows[i] < o30l:
                o30l = lows[i]
        if tm < 600:  # 09:00..09:55 bars
            if highs[i] > o60h:
                o60h = highs[i]
            if lows[i] < o60l:
                o60l = lows[i]

        day_open[i] = d_open
        day_high_so_far[i] = d_h
        day_low_so_far[i] = d_l
        mv = closes[i] - d_open
        rng = max(0.5, d_h - d_l)
        day_move[i] = mv
        day_eff[i] = abs(mv) / rng
        if o30h > -1e8:
            or30_h[i] = o30h
            or30_l[i] = o30l
        if o60h > -1e8:
            or60_h[i] = o60h
            or60_l[i] = o60l

        gamma_flip[i] = cur_gf
        if len(cur_walls) > 0:
            diffs = np.abs(cur_walls - closes[i])
            idx = int(np.argmin(diffs))
            near_wall[i] = cur_walls[idx]
            near_wall_dist[i] = diffs[idx]
            ab = cur_walls[cur_walls >= closes[i]]
            bl = cur_walls[cur_walls <= closes[i]]
            if len(ab) > 0:
                wall_above[i] = ab[0]
            if len(bl) > 0:
                wall_below[i] = bl[-1]

    # Identify WDO Fury Days (same exact definition as forensic audit: |day_close - day_open| >= 34 and eff >= 0.60)
    fury_dates = set()
    for d, grp in df.groupby("session_date"):
        o_d = float(grp["open"].iloc[0])
        c_d = float(grp["close"].iloc[-1])
        h_d = float(grp["high"].max())
        l_d = float(grp["low"].min())
        mv = abs(c_d - o_d)
        eff = mv / max(0.5, h_d - l_d)
        if mv >= 34.0 and eff >= 0.60:
            fury_dates.add(str(d))

    feats = {
        "df": df,
        "gex_by_date": gex_by_date,
        "dates": dates,
        "t_mins": t_mins,
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "n50_c": n50_c,
        "n50_u": n50_u,
        "n50_l": n50_l,
        "n50_s": n50_s,
        "n30_c": n30_c,
        "n30_u": n30_u,
        "n30_l": n30_l,
        "n30_s": n30_s,
        "atr14": atr14,
        "day_open": day_open,
        "day_move": day_move,
        "day_eff": day_eff,
        "or30_h": or30_h,
        "or30_l": or30_l,
        "or60_h": or60_h,
        "or60_l": or60_l,
        "near_wall": near_wall,
        "near_wall_dist": near_wall_dist,
        "gamma_flip": gamma_flip,
        "fury_dates": fury_dates,
    }
    return feats


def simulate_directional_strategy(
    feats: dict,
    arch: str,
    params: dict,
    cost_pts: float = 0.5,
    m1_dict: dict | None = None,
) -> list[dict]:
    """
    Simulador 100% causal em M5 (com verificacao opcional exata barra-a-barra em M1).
    - Sinal avaliado EXCLUSIVAMENTE na barra fechada b1 = i-1 (e b2 = i-2).
    - Entrada no Open de barra i (Market) ou Stop trigger na barra i (conservador: SL checado antes de TP/Trail).
    - Trailing Stop atualizado apenas no fechamento de barra (ou M1 se m1_dict fornecido), nunca olhando futuro!
    - Encerramento EOD as 17:15 (t_min >= 1035).
    """
    dates = feats["dates"]
    t_mins = feats["t_mins"]
    opens = feats["opens"]
    highs = feats["highs"]
    lows = feats["lows"]
    closes = feats["closes"]
    n50_c, n50_u, n50_l, n50_s = feats["n50_c"], feats["n50_u"], feats["n50_l"], feats["n50_s"]
    n30_c, n30_u, n30_l, n30_s = feats["n30_c"], feats["n30_u"], feats["n30_l"], feats["n30_s"]
    atr14 = feats["atr14"]
    day_move = feats["day_move"]
    day_eff = feats["day_eff"]
    or30_h, or30_l = feats["or30_h"], feats["or30_l"]
    or60_h, or60_l = feats["or60_h"], feats["or60_l"]
    gamma_flip = feats["gamma_flip"]
    gex_by_date = feats["gex_by_date"]

    sl_pts = float(params["sl"])
    tp_pts = float(params["tp"])  # 0 or >= 999 means pure trailing / EOD
    be_trig = float(params.get("be_trig", 0.0))
    be_lock = float(params.get("be_lock", 1.0))
    tr_trig = float(params["tr_trig"])
    tr_dist = float(params["tr_dist"])
    max_tr_day = int(params.get("max_tr", 2))
    min_tmin = int(params.get("min_tmin", 570))   # 09:30
    max_tmin = int(params.get("max_tmin", 960))   # 16:00
    max_hold = int(params.get("max_hold", 120))   # EOD

    n = len(closes)
    pos_dir = 0
    entry_px = 0.0
    entry_date = ""
    entry_tmin = 0
    curr_sl = 0.0
    curr_tp = 0.0
    max_fav = 0.0
    be_done = False
    bars_held = 0

    cur_day = ""
    trades_today = 0
    orb_used_dir = 0
    cur_walls = np.array([], dtype=float)
    trades = []

    def close_pos(exit_px: float, reason: str, exit_tmin: int, d_str: str):
        nonlocal pos_dir
        pts = (exit_px - entry_px) * pos_dir - cost_pts
        trades.append({
            "date": d_str,
            "entry_min": entry_tmin,
            "exit_min": exit_tmin,
            "dir": pos_dir,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "pts": pts,
            "pnl": pts * 10.0,
            "reason": reason,
        })
        pos_dir = 0

    for i in range(2, n):
        d = dates[i]
        tm = t_mins[i]
        o_i, h_i, l_i, c_i = opens[i], highs[i], lows[i], closes[i]

        if d != cur_day:
            if pos_dir != 0:
                close_pos(opens[i - 1], "EOD_OVERNIGHT", t_mins[i - 1], cur_day)
            cur_day = d
            trades_today = 0
            orb_used_dir = 0
            g = gex_by_date.get(d)
            cur_walls = g["walls"] if g is not None else np.array([], dtype=float)

        # 1. Manage open position on bar i (conservatively: SL checked BEFORE TP!)
        if pos_dir != 0:
            if tm >= 1035:  # EOD 17:15
                close_pos(o_i, "EOD", tm, d)
            else:
                # Optional exact M1 intrabar simulation for this 5-min bar
                closed_m1 = False
                if m1_dict is not None and d in m1_dict:
                    m1_day = m1_dict[d]
                    m_mins = m1_day["mins"]
                    m_o = m1_day["open"]
                    m_h = m1_day["high"]
                    m_l = m1_day["low"]
                    m_c = m1_day["close"]
                    # Slice M1 bars in [tm, tm+5)
                    idx0 = int(np.searchsorted(m_mins, tm, side="left"))
                    idx1 = int(np.searchsorted(m_mins, tm + 5, side="left"))
                    for j in range(idx0, idx1):
                        mh, ml, mo, mc = m_h[j], m_l[j], m_o[j], m_c[j]
                        # Gap check on open
                        if pos_dir == 1:
                            if mo <= curr_sl:
                                close_pos(mo, "SL_GAP", int(m_mins[j]), d); closed_m1 = True; break
                            if ml <= curr_sl:
                                close_pos(curr_sl, "SL", int(m_mins[j]), d); closed_m1 = True; break
                            if tp_pts > 0 and mh >= curr_tp:
                                close_pos(curr_tp, "TP", int(m_mins[j]), d); closed_m1 = True; break
                            fav_j = mh - entry_px
                            if fav_j > max_fav:
                                max_fav = fav_j
                        else:
                            if mo >= curr_sl:
                                close_pos(mo, "SL_GAP", int(m_mins[j]), d); closed_m1 = True; break
                            if mh >= curr_sl:
                                close_pos(curr_sl, "SL", int(m_mins[j]), d); closed_m1 = True; break
                            if tp_pts > 0 and ml <= curr_tp:
                                close_pos(curr_tp, "TP", int(m_mins[j]), d); closed_m1 = True; break
                            fav_j = entry_px - ml
                            if fav_j > max_fav:
                                max_fav = fav_j
                else:
                    # Conservative M5 intrabar check: SL first!
                    if pos_dir == 1:
                        if o_i <= curr_sl:
                            close_pos(o_i, "SL_GAP", tm, d); closed_m1 = True
                        elif l_i <= curr_sl:
                            close_pos(curr_sl, "SL", tm, d); closed_m1 = True
                        elif tp_pts > 0 and h_i >= curr_tp:
                            close_pos(curr_tp, "TP", tm, d); closed_m1 = True
                        else:
                            fav_b = h_i - entry_px
                            if fav_b > max_fav:
                                max_fav = fav_b
                    else:
                        if o_i >= curr_sl:
                            close_pos(o_i, "SL_GAP", tm, d); closed_m1 = True
                        elif h_i >= curr_sl:
                            close_pos(curr_sl, "SL", tm, d); closed_m1 = True
                        elif tp_pts > 0 and l_i <= curr_tp:
                            close_pos(curr_tp, "TP", tm, d); closed_m1 = True
                        else:
                            fav_b = entry_px - l_i
                            if fav_b > max_fav:
                                max_fav = fav_b

                if not closed_m1 and pos_dir != 0:
                    bars_held += 1
                    # Causal update of BE and Trailing Stop at bar i CLOSE (active for bar i+1)
                    if be_trig > 0 and not be_done and max_fav >= be_trig:
                        cand = round05(entry_px + be_lock) if pos_dir == 1 else round05(entry_px - be_lock)
                        if (pos_dir == 1 and c_i > cand + 0.5) or (pos_dir == -1 and c_i < cand - 0.5):
                            curr_sl = max(curr_sl, cand) if pos_dir == 1 else min(curr_sl, cand)
                            be_done = True
                    if tr_trig > 0 and max_fav >= tr_trig:
                        cand = round05(entry_px + max_fav - tr_dist) if pos_dir == 1 else round05(entry_px - max_fav + tr_dist)
                        if (pos_dir == 1 and c_i > cand + 0.5) or (pos_dir == -1 and c_i < cand - 0.5):
                            curr_sl = max(curr_sl, cand) if pos_dir == 1 else min(curr_sl, cand)
                    if bars_held >= max_hold:
                        close_pos(c_i, "TIME_STOP", tm, d)
            continue  # Never exit and re-enter on the exact same bar

        # 2. Evaluate new entry signal using ONLY closed bars b1=i-1, b2=i-2
        if dates[i - 1] != d:
            continue
        if tm < min_tmin or tm >= max_tmin:
            continue
        if trades_today >= max_tr_day:
            continue

        b1_o, b1_h, b1_l, b1_c = opens[i - 1], highs[i - 1], lows[i - 1], closes[i - 1]
        b2_o, b2_h, b2_l, b2_c = opens[i - 2], highs[i - 2], lows[i - 2], closes[i - 2]
        body1 = b1_c - b1_o
        rng1 = max(0.5, b1_h - b1_l)
        s50 = n50_s[i - 1]
        s30 = n30_s[i - 1]
        dmv = day_move[i - 1]
        deff = day_eff[i - 1]
        sig = 0

        if arch == "A1_WALL_BO":
            # Breakout through a MainWall with strong candle + NWE slope alignment
            min_body = params["min_body"]
            min_slope = params["min_slope"]
            buf = params["buf"]
            if len(cur_walls) > 0:
                for w in cur_walls:
                    if b1_o <= w + 1.0 and b1_c >= w + buf and body1 >= min_body and s50 >= min_slope and dmv >= params["min_dmv"]:
                        sig = 1; break
                    if b1_o >= w - 1.0 and b1_c <= w - buf and body1 <= -min_body and s50 <= -min_slope and dmv <= -params["min_dmv"]:
                        sig = -1; break

        elif arch == "A2_NWE_EXP":
            # Close outside NWE50/NWE30 envelope + slope + directional day
            env = params["env"]
            u1 = n50_u[i - 1] if env == 50 else n30_u[i - 1]
            l1 = n50_l[i - 1] if env == 50 else n30_l[i - 1]
            u2 = n50_u[i - 2] if env == 50 else n30_u[i - 2]
            l2 = n50_l[i - 2] if env == 50 else n30_l[i - 2]
            slp = s50 if env == 50 else s30
            min_slope = params["min_slope"]
            min_body = params["min_body"]
            min_eff = params["min_eff"]
            fresh = params.get("fresh", True)
            if (b1_c > u1) and (not fresh or b2_c <= u2) and body1 >= min_body and slp >= min_slope and deff >= min_eff and dmv > 0:
                sig = 1
            elif (b1_c < l1) and (not fresh or b2_c >= l2) and body1 <= -min_body and slp <= -min_slope and deff >= min_eff and dmv < 0:
                sig = -1

        elif arch == "A3_ORB":
            # Opening Range Breakout (30m or 60m) with NWE slope + candle confirmation
            use60 = params["or_min"] == 60
            oh = or60_h[i - 1] if use60 else or30_h[i - 1]
            ol = or60_l[i - 1] if use60 else or30_l[i - 1]
            buf = params["buf"]
            min_slope = params["min_slope"]
            min_body = params["min_body"]
            if not np.isnan(oh) and not np.isnan(ol):
                or_rng = oh - ol
                if params["min_or"] <= or_rng <= params["max_or"]:
                    if b1_c > oh + buf and b2_c <= oh + buf and body1 >= min_body and s50 >= min_slope and orb_used_dir != 1:
                        sig = 1
                    elif b1_c < ol - buf and b2_c >= ol - buf and body1 <= -min_body and s50 <= -min_slope and orb_used_dir != -1:
                        sig = -1

        elif arch == "A4_GF_TREND":
            # GammaFlip Breakout / Regime Momentum
            gf = gamma_flip[i - 1]
            min_slope = params["min_slope"]
            min_body = params["min_body"]
            buf = params["buf"]
            if gf > 0:
                if b1_o <= gf + 1.0 and b1_c >= gf + buf and body1 >= min_body and s50 >= min_slope and deff >= params["min_eff"]:
                    sig = 1
                elif b1_o >= gf - 1.0 and b1_c <= gf - buf and body1 <= -min_body and s50 <= -min_slope and deff >= params["min_eff"]:
                    sig = -1

        elif arch == "A5_PB_TREND":
            # Pullback to NWE center (or NWE30 center) in an already confirmed directional day!
            min_dmv = params["min_dmv"]
            min_eff = params["min_eff"]
            min_slope = params["min_slope"]
            cen = n30_c[i - 1] if params["cen"] == 30 else n50_c[i - 1]
            tol = params["tol"]
            if dmv >= min_dmv and deff >= min_eff and s50 >= min_slope:
                if b1_l <= cen + tol and b1_c > cen and body1 >= params["min_body"]:
                    sig = 1
            elif dmv <= -min_dmv and deff >= min_eff and s50 <= -min_slope:
                if b1_h >= cen - tol and b1_c < cen and body1 <= -params["min_body"]:
                    sig = -1

        elif arch == "A6_ANTI_FADE":
            # Failed Wall Reversal / Stop-Run: bar b2 tested Wall and reversed/paused, then b1 smashes THROUGH Wall!
            min_body = params["min_body"]
            buf = params["buf"]
            min_eff = params["min_eff"]
            if len(cur_walls) > 0 and deff >= min_eff:
                for w in cur_walls:
                    if b2_h >= w - 1.5 and b2_c <= w + 0.5 and b1_c >= w + buf and body1 >= min_body and s30 >= params["min_slope"]:
                        sig = 1; break
                    if b2_l <= w + 1.5 and b2_c >= w - 0.5 and b1_c <= w - buf and body1 <= -min_body and s30 <= -params["min_slope"]:
                        sig = -1; break

        if sig != 0:
            # Open on bar i OPEN, and immediately check bar i conservatively (SL first!)
            pos_dir = sig
            entry_px = o_i
            entry_date = d
            entry_tmin = tm
            curr_sl = round05(entry_px - sl_pts) if sig == 1 else round05(entry_px + sl_pts)
            curr_tp = (round05(entry_px + tp_pts) if sig == 1 else round05(entry_px - tp_pts)) if tp_pts > 0 else 0.0
            max_fav = 0.0
            be_done = False
            bars_held = 0
            trades_today += 1
            if arch == "A3_ORB":
                orb_used_dir = sig

            # Strict causal check on the ENTRY bar itself (no entry-bar immunity!)
            closed_entry = False
            if m1_dict is not None and d in m1_dict:
                m1_day = m1_dict[d]
                m_mins = m1_day["mins"]
                m_h = m1_day["high"]
                m_l = m1_day["low"]
                idx0 = int(np.searchsorted(m_mins, tm, side="left"))
                idx1 = int(np.searchsorted(m_mins, tm + 5, side="left"))
                for j in range(idx0, idx1):
                    if pos_dir == 1:
                        if m_l[j] <= curr_sl:
                            close_pos(curr_sl, "SL_ENTRY_M1", int(m_mins[j]), d); closed_entry = True; break
                        if tp_pts > 0 and m_h[j] >= curr_tp:
                            close_pos(curr_tp, "TP_ENTRY_M1", int(m_mins[j]), d); closed_entry = True; break
                        fav_j = m_h[j] - entry_px
                        if fav_j > max_fav:
                            max_fav = fav_j
                    else:
                        if m_h[j] >= curr_sl:
                            close_pos(curr_sl, "SL_ENTRY_M1", int(m_mins[j]), d); closed_entry = True; break
                        if tp_pts > 0 and m_l[j] <= curr_tp:
                            close_pos(curr_tp, "TP_ENTRY_M1", int(m_mins[j]), d); closed_entry = True; break
                        fav_j = entry_px - m_l[j]
                        if fav_j > max_fav:
                            max_fav = fav_j
            else:
                if pos_dir == 1:
                    if l_i <= curr_sl:
                        close_pos(curr_sl, "SL_ENTRY", tm, d); closed_entry = True
                    elif tp_pts > 0 and h_i >= curr_tp:
                        close_pos(curr_tp, "TP_ENTRY", tm, d); closed_entry = True
                    else:
                        max_fav = max(0.0, h_i - entry_px)
                else:
                    if h_i >= curr_sl:
                        close_pos(curr_sl, "SL_ENTRY", tm, d); closed_entry = True
                    elif tp_pts > 0 and l_i <= curr_tp:
                        close_pos(curr_tp, "TP_ENTRY", tm, d); closed_entry = True
                    else:
                        max_fav = max(0.0, entry_px - l_i)

            if not closed_entry and pos_dir != 0:
                # Update BE/Trailing on entry bar close for next bar
                if be_trig > 0 and not be_done and max_fav >= be_trig:
                    cand = round05(entry_px + be_lock) if pos_dir == 1 else round05(entry_px - be_lock)
                    if (pos_dir == 1 and c_i > cand + 0.5) or (pos_dir == -1 and c_i < cand - 0.5):
                        curr_sl = max(curr_sl, cand) if pos_dir == 1 else min(curr_sl, cand)
                        be_done = True
                if tr_trig > 0 and max_fav >= tr_trig:
                    cand = round05(entry_px + max_fav - tr_dist) if pos_dir == 1 else round05(entry_px - max_fav + tr_dist)
                    if (pos_dir == 1 and c_i > cand + 0.5) or (pos_dir == -1 and c_i < cand - 0.5):
                        curr_sl = max(curr_sl, cand) if pos_dir == 1 else min(curr_sl, cand)

    return trades


def eval_trades_metrics(trades: list[dict], all_dates: list[str], fury_dates: set[str], wdo_base_daily: dict, port_base_daily: dict):
    by_day = {d: 0.0 for d in all_dates}
    for t in trades:
        if t["date"] in by_day:
            by_day[t["date"]] += float(t["pnl"])

    pnls_all = np.array([by_day[d] for d in all_dates], dtype=float)
    is_dates = [d for d in all_dates if d < "2026-08-01"]
    oos_dates = [d for d in all_dates if d >= "2026-08-01"]
    h1_dates = [d for d in all_dates if d < "2026-06-01"]

    m_all = _summarize_daily_pnls([by_day[d] for d in all_dates])
    m_is = _summarize_daily_pnls([by_day[d] for d in is_dates])
    m_oos = _summarize_daily_pnls([by_day[d] for d in oos_dates])
    m_h1 = _summarize_daily_pnls([by_day[d] for d in h1_dates])

    tr_pnls = np.array([t["pnl"] for t in trades], dtype=float) if trades else np.array([], dtype=float)
    tr_is = np.array([t["pnl"] for t in trades if t["date"] < "2026-08-01"], dtype=float)
    tr_oos = np.array([t["pnl"] for t in trades if t["date"] >= "2026-08-01"], dtype=float)

    def pf_wr(arr):
        if len(arr) == 0:
            return 0.0, 0.0
        gp = float(arr[arr > 0].sum())
        gl = float(-arr[arr < 0].sum())
        pf = gp / gl if gl > 0 else (99.0 if gp > 0 else 0.0)
        wr = 100.0 * float((arr > 0).mean())
        return round(pf, 2), round(wr, 1)

    pf_all, wr_all = pf_wr(tr_pnls)
    pf_is, wr_is = pf_wr(tr_is)
    pf_oos, wr_oos = pf_wr(tr_oos)

    # Monthly positive ratio
    months = {}
    for d in all_dates:
        ym = d[:7]
        months[ym] = months.get(ym, 0.0) + by_day[d]
    pos_months = sum(1 for v in months.values() if v > 0)
    tot_months = len(months)

    # Fury days PnL
    fury_pnl = sum(by_day[d] for d in all_dates if d in fury_dates)
    fury_tr = sum(1 for t in trades if t["date"] in fury_dates)

    # Correlation with WDO-01/05/07 and Synergy with top_10
    wdo_vec = np.array([wdo_base_daily.get(d, 0.0) for d in all_dates], dtype=float)
    port_vec = np.array([port_base_daily.get(d, 0.0) for d in all_dates], dtype=float)
    corr_wdo = float(np.corrcoef(pnls_all, wdo_vec)[0, 1]) if (np.std(pnls_all) > 1e-9 and np.std(wdo_vec) > 1e-9) else 0.0

    comb_all = _summarize_daily_pnls((port_vec + pnls_all).tolist())
    comb_oos = _summarize_daily_pnls([(port_base_daily.get(d, 0.0) + by_day[d]) for d in oos_dates])

    return {
        "n": len(trades),
        "n_is": len(tr_is),
        "n_oos": len(tr_oos),
        "net": round(m_all["total_pnl"], 1),
        "dd": round(m_all["max_dd"], 1),
        "ret_dd": round(m_all["ret_dd"], 2),
        "sharpe": round(m_all["sharpe"], 2),
        "pf": pf_all,
        "wr": wr_all,
        "is_net": round(m_is["total_pnl"], 1),
        "is_pf": pf_is,
        "is_ret_dd": round(m_is["ret_dd"], 2),
        "oos_net": round(m_oos["total_pnl"], 1),
        "oos_pf": pf_oos,
        "oos_ret_dd": round(m_oos["ret_dd"], 2),
        "h1_net": round(m_h1["total_pnl"], 1),
        "h1_ret_dd": round(m_h1["ret_dd"], 2),
        "pos_months": f"{pos_months}/{tot_months}",
        "pos_months_pct": round(100.0 * pos_months / max(1, tot_months), 1),
        "fury_pnl": round(fury_pnl, 1),
        "fury_tr": fury_tr,
        "corr_wdo": round(corr_wdo, 3),
        "comb_net": round(comb_all["total_pnl"], 1),
        "comb_dd": round(comb_all["max_dd"], 1),
        "comb_ret_dd": round(comb_all["ret_dd"], 2),
        "comb_sharpe": round(comb_all["sharpe"], 2),
        "comb_oos_ret_dd": round(comb_oos["ret_dd"], 2),
        "worst_day": round(m_all["worst_day"], 1),
        "avg_pts": round(float(np.mean([t["pts"] for t in trades])) if trades else 0.0, 2),
    }


def build_candidate_grid():
    """Grid estrutural compacto e parcimonioso para os 6 arquetipos direcionais WDO."""
    exits = [
        # (sl, tp, be_trig, be_lock, tr_trig, tr_dist)
        (8.0,  35.0, 8.0,  1.0, 12.0,  8.0),
        (10.0, 45.0, 10.0, 1.5, 14.0, 10.0),
        (12.0, 60.0, 12.0, 2.0, 16.0, 12.0),
        (10.0,  0.0, 10.0, 1.5, 15.0, 10.0),  # Pure trailing / EOD
        (12.0,  0.0, 12.0, 2.0, 18.0, 12.0),  # Wide pure trailing / EOD
        (8.0,  24.0, 7.0,  1.0, 10.0,  6.0),
    ]
    grid = []

    # A1: Wall Breakout
    for sl, tp, bt, bl, tt, td in exits:
        for buf in (1.5, 3.0):
            for min_body in (2.0, 3.5):
                for min_slope in (0.15, 0.30):
                    for min_dmv in (0.0, 10.0):
                        grid.append(("A1_WALL_BO", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "buf": buf, "min_body": min_body, "min_slope": min_slope, "min_dmv": min_dmv,
                            "max_tr": 2, "min_tmin": 570, "max_tmin": 960,
                        }))

    # A2: NWE Band Expansion
    for sl, tp, bt, bl, tt, td in exits:
        for env in (30, 50):
            for min_slope in (0.20, 0.35):
                for min_body in (2.0, 3.5):
                    for min_eff in (0.35, 0.55):
                        grid.append(("A2_NWE_EXP", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "env": env, "min_slope": min_slope, "min_body": min_body, "min_eff": min_eff,
                            "fresh": True, "max_tr": 2, "min_tmin": 570, "max_tmin": 960,
                        }))

    # A3: Opening Range Breakout (30m & 60m)
    for sl, tp, bt, bl, tt, td in exits:
        for or_min in (30, 60):
            for buf in (1.0, 2.5):
                for min_slope in (0.0, 0.20):
                    for min_body in (1.5, 3.0):
                        grid.append(("A3_ORB", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "or_min": or_min, "buf": buf, "min_slope": min_slope, "min_body": min_body,
                            "min_or": 8.0, "max_or": 40.0,
                            "max_tr": 2, "min_tmin": 540 + or_min, "max_tmin": 930,
                        }))

    # A4: GammaFlip Trend Breakout
    for sl, tp, bt, bl, tt, td in exits:
        for buf in (1.5, 3.0):
            for min_body in (2.0, 3.5):
                for min_slope in (0.15, 0.30):
                    for min_eff in (0.35, 0.55):
                        grid.append(("A4_GF_TREND", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "buf": buf, "min_body": min_body, "min_slope": min_slope, "min_eff": min_eff,
                            "max_tr": 2, "min_tmin": 570, "max_tmin": 960,
                        }))

    # A5: Trend Pullback to NWE Center on Confirmed Trend Days
    for sl, tp, bt, bl, tt, td in exits:
        for cen in (30, 50):
            for min_dmv in (12.0, 20.0):
                for min_eff in (0.45, 0.60):
                    for min_body in (1.5, 3.0):
                        grid.append(("A5_PB_TREND", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "cen": cen, "min_dmv": min_dmv, "min_eff": min_eff, "min_slope": 0.20,
                            "tol": 2.0, "min_body": min_body,
                            "max_tr": 2, "min_tmin": 600, "max_tmin": 960,
                        }))

    # A6: Anti-Fade / Failed Wall Reversal (Stop-Run)
    for sl, tp, bt, bl, tt, td in exits:
        for buf in (1.5, 3.0):
            for min_body in (2.0, 3.5):
                for min_slope in (0.15, 0.30):
                    for min_eff in (0.35, 0.55):
                        grid.append(("A6_ANTI_FADE", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "buf": buf, "min_body": min_body, "min_slope": min_slope, "min_eff": min_eff,
                            "max_tr": 2, "min_tmin": 570, "max_tmin": 960,
                        }))

    return grid


def main():
    t0 = time.time()
    print("[1/4] Carregando WDO M5 + GEX MagicWalls + NWE + M1...", flush=True)
    feats = prepare_wdo_features()
    all_dates = sorted(set(feats["dates"]))
    fury_dates = feats["fury_dates"]
    print(f"      Pregões={len(all_dates)} | WDO Fury Days={len(fury_dates)}", flush=True)

    # Load top_10 baseline (prefer B3 if available, else OLD with B3 filter)
    b3_dir = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026_b3")
    old_dir = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026")
    top10_codes = PORTFOLIO_PRESETS["top_10"]["robots"]
    if os.path.isfile(os.path.join(b3_dir, "WDO07_P1.htm")):
        base_trades = load_portfolio_trades(top10_codes, htm_dir=b3_dir)
        base_src = "MT5_REAL_B3"
    else:
        raw_t = load_portfolio_trades(top10_codes, htm_dir=old_dir)
        base_trades = [
            t for t in raw_t
            if not (t["asset"] == "WDO" and t["min_in"] >= 900)
            and not (t["asset"] == "WIN" and t["min_in"] >= 960)
        ]
        base_src = "MT5_B3_SIM"

    wdo_base_daily = {}
    port_base_daily = {}
    for t in base_trades:
        port_base_daily[t["date"]] = port_base_daily.get(t["date"], 0.0) + float(t["pnl"])
        if t["asset"] == "WDO":
            wdo_base_daily[t["date"]] = wdo_base_daily.get(t["date"], 0.0) + float(t["pnl"])

    base_port_m = _summarize_daily_pnls([port_base_daily.get(d, 0.0) for d in all_dates])
    base_oos_m = _summarize_daily_pnls([port_base_daily.get(d, 0.0) for d in all_dates if d >= "2026-08-01"])
    print(
        f"      Baseline top_10 ({base_src}): Net=R$ {base_port_m['total_pnl']:,.0f} | "
        f"DD=R$ {base_port_m['max_dd']:,.0f} | Ret/DD={base_port_m['ret_dd']:.2f}x | "
        f"Sharpe={base_port_m['sharpe']:.2f} | OOS={base_oos_m['ret_dd']:.2f}x",
        flush=True,
    )

    # Run grid discovery (ranked ONLY on IS Jan-Jul!)
    grid = build_candidate_grid()
    print(f"[2/4] Rodando bateria com {len(grid)} combinacoes estruturais (6 arquetipos direcionais WDO)...", flush=True)
    rows = []
    for idx, (arch, params) in enumerate(grid):
        tr = simulate_directional_strategy(feats, arch, params, cost_pts=0.5, m1_dict=None)
        m = eval_trades_metrics(tr, all_dates, fury_dates, wdo_base_daily, port_base_daily)
        rows.append({"idx": idx, "arch": arch, "params": params, **m})

    df_res = pd.DataFrame(rows)
    df_res.to_csv(os.path.join(OUT_DIR, "all_candidates_m5.csv"), index=False)

    print("\n=== RESUMO POR ARQUETIPO (TODOS OS PARAMETROS) ===")
    for arch, grp in df_res.groupby("arch"):
        pos_is = (grp["is_net"] > 0).mean() * 100
        pos_oos = (grp["oos_net"] > 0).mean() * 100
        pos_both = ((grp["is_net"] > 0) & (grp["oos_net"] > 0)).mean() * 100
        pos_fury = (grp["fury_pnl"] > 0).mean() * 100
        best_is = grp[grp["n"] >= 50].sort_values("is_ret_dd", ascending=False).head(1)
        b_str = ""
        if not best_is.empty:
            r = best_is.iloc[0]
            b_str = f"BestIS: n={r['n']} IS_R/DD={r['is_ret_dd']:.2f}x OOS_Net={r['oos_net']:+.0f} (PF={r['oos_pf']:.2f}) Fury={r['fury_pnl']:+.0f} Corr={r['corr_wdo']:+.2f}"
        print(f"  {arch:<13} | Grid={len(grp):>3} | IS>0:{pos_is:5.1f}% | OOS>0:{pos_oos:5.1f}% | Both>0:{pos_both:5.1f}% | Fury>0:{pos_fury:5.1f}% | {b_str}")

    # [3/4] Select top IS-ranked candidates (NO OOS peeking during ranking!) and run M1 exact verification + 1.0pt stress + neighborhood
    print("\n[3/4] Validacao M1 exata + Stress de custo (1.0 pt) + Vizinhanca nos top candidatos ranqueados APENAS por IS...", flush=True)
    _, wdo_m1 = load_m1_bars()

    top_candidates = []
    for arch, grp in df_res.groupby("arch"):
        elig = grp[(grp["n"] >= 50) & (grp["is_net"] > 0)].sort_values(["is_ret_dd", "is_pf"], ascending=False).head(5)
        for _, r in elig.iterrows():
            top_candidates.append(r)
    # Also add overall top 10 by IS Ret/DD (with n >= 60, is_pf >= 1.25)
    overall_is = df_res[(df_res["n"] >= 60) & (df_res["is_pf"] >= 1.20)].sort_values("is_ret_dd", ascending=False).head(10)
    seen_idx = {int(r["idx"]) for r in top_candidates}
    for _, r in overall_is.iterrows():
        if int(r["idx"]) not in seen_idx:
            top_candidates.append(r)
            seen_idx.add(int(r["idx"]))

    verified = []
    for r in top_candidates:
        arch = r["arch"]
        params = r["params"]
        # M1 exact verification at 0.5pt and 1.0pt stress cost
        tr_m1_05 = simulate_directional_strategy(feats, arch, params, cost_pts=0.5, m1_dict=wdo_m1)
        m1_05 = eval_trades_metrics(tr_m1_05, all_dates, fury_dates, wdo_base_daily, port_base_daily)
        tr_m1_10 = simulate_directional_strategy(feats, arch, params, cost_pts=1.0, m1_dict=wdo_m1)
        m1_10 = eval_trades_metrics(tr_m1_10, all_dates, fury_dates, wdo_base_daily, port_base_daily)

        # Neighborhood stability inside same archetype (same entry trigger/params or +/-1 step in SL/TP/Trail)
        same_arch = df_res[df_res["arch"] == arch]
        nbr_pos = float(((same_arch["net"] > 0) & (same_arch["oos_net"] > 0)).mean() * 100.0)
        # Strict local neighborhood: identical entry params across all 6 exit templates
        entry_keys = [k for k in params if k not in ("sl", "tp", "be_trig", "be_lock", "tr_trig", "tr_dist")]
        local_nbrs = [
            row for row in rows
            if row["arch"] == arch and all(row["params"].get(k) == params.get(k) for k in entry_keys)
        ]
        local_pos_pct = 100.0 * sum(1 for x in local_nbrs if x["net"] > 0) / max(1, len(local_nbrs))
        local_oos_pct = 100.0 * sum(1 for x in local_nbrs if x["oos_net"] > 0) / max(1, len(local_nbrs))

        # 5 Anti-Overfitting Gates (strictly evaluated on M1 verified numbers!)
        g1 = (m1_05["n"] >= 60) and (m1_05["is_net"] > 0) and (m1_05["is_pf"] >= 1.25) and (m1_05["is_ret_dd"] >= 2.0)
        g2 = (m1_05["oos_net"] > 0) and (m1_05["oos_pf"] >= 1.15) and (m1_05["oos_ret_dd"] >= 1.2)
        g3 = (m1_05["pos_months_pct"] >= 60.0) and (m1_10["net"] > 0) and (m1_10["oos_net"] > 0)
        g4 = (local_pos_pct >= 66.0) and (local_oos_pct >= 50.0)
        g5 = (m1_05["corr_wdo"] <= 0.25) and (m1_05["fury_pnl"] > 0) and (
            m1_05["comb_ret_dd"] > base_port_m["ret_dd"] or m1_05["comb_sharpe"] > base_port_m["sharpe"]
        )
        gates_passed = int(g1) + int(g2) + int(g3) + int(g4) + int(g5)

        verified.append({
            "arch": arch,
            "params": params,
            "m1_05": m1_05,
            "m1_10_net": m1_10["net"],
            "m1_10_oos": m1_10["oos_net"],
            "m1_10_pf": m1_10["pf"],
            "local_pos_pct": round(local_pos_pct, 1),
            "local_oos_pct": round(local_oos_pct, 1),
            "arch_both_pos_pct": round(nbr_pos, 1),
            "gates": {"G1_IS": g1, "G2_OOS": g2, "G3_TIME_COST": g3, "G4_NBR": g4, "G5_SYNERGY": g5},
            "gates_passed": gates_passed,
        })

    verified.sort(key=lambda x: (x["gates_passed"], x["m1_05"]["comb_ret_dd"], x["m1_05"]["ret_dd"]), reverse=True)

    print("\n=== TOP 15 CANDIDATOS VERIFICADOS EM M1 EXATO (0.5pt spread + 1.0pt stress) ===")
    print(f"{'Gates':<5} | {'Arch':<12} | {'N':>4} | {'Net':>7} | {'DD':>6} | {'R/DD':>5} | {'PF':>4} | {'IS R/DD':>7} | {'OOS Net':>7} | {'OOS PF':>6} | {'Fury':>6} | {'Corr':>5} | {'Str1pt':>6} | {'Comb R/DD':>9} | {'Loc%':>4}")
    for v in verified[:15]:
        m = v["m1_05"]
        print(
            f"{v['gates_passed']}/5   | {v['arch']:<12} | {m['n']:>4} | {m['net']:>7.0f} | {m['dd']:>6.0f} | "
            f"{m['ret_dd']:>5.2f} | {m['pf']:>4.2f} | {m['is_ret_dd']:>6.2f}x | {m['oos_net']:>7.0f} | "
            f"{m['oos_pf']:>6.2f} | {m['fury_pnl']:>+6.0f} | {m['corr_wdo']:>+5.2f} | {v['m1_10_net']:>6.0f} | "
            f"{m['comb_ret_dd']:>8.2f}x | {v['local_pos_pct']:>4.0f}"
        )

    out_json = os.path.join(OUT_DIR, "wdo_directional_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "baseline": {"src": base_src, "full": base_port_m, "oos": base_oos_m},
            "verified_top": verified[:25],
        }, f, indent=2, default=str)
    print(f"\n[DONE in {time.time() - t0:.1f}s] Saved -> {out_json}", flush=True)


if __name__ == "__main__":
    main()
