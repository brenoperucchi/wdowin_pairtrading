"""
Bateria Anti-Overfitting Round 2: Robos Direcionais Estruturais no WDO (M5 + M15 + Limit Retest + Macro WINxWDO)
=================================================================================================================
Round 1 provou que breakouts ingenuos a mercado em M5 lucram +R$ 3.1k..+4.6k nos 38 Dias de Furia,
mas sangram nos 174 dias laterais (IS>0 = 0%).
Round 2 testa 6 arquetipos direcionais adaptados a microestrutura do WDO na B3:
  R1_REGIME_GATED : So liga quando o dia JA confirmou furia (|mov|>=22..35 & eff>=0.55..0.70)
  R2_WALL_RETEST  : Rompe MainWall + Ordem LIMIT no reteste da Wall rompida (estilo EST-04 no WDO)
  R3_M15_TREND    : Rompimento / Expansao NWE / Wall em M15 (filtra ruido M5)
  R4_AFTERNOON    : Continuacao da tarde (12:30-16:00) a favor do dia (espelho do corte das 15h!)
  R5_NDH_NDL      : Rompimento de Maxima/Minima do Dia (New Day High/Low) + eficiencia + trailing
  R6_MACRO_WINWDO : Dia macro alinhado (WIN caindo forte + WDO subindo forte, ou vice-versa)

Ranking ESTRITAMENTE por IS (Jan-Jul 2026); OOS (Ago-Nov 2026) 100% cego + verificacao M1 exata + stress 1.0pt.
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
from research.mt5_loader import get_mt5_rates
from research.stop_diario.data_loader import load_portfolio_trades, load_m1_bars, PORTFOLIO_PRESETS
from research.wdo_directional_battery.discover_wdo_trend import (
    _summarize_daily_pnls,
    eval_trades_metrics,
)

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "wdo_directional_battery")
os.makedirs(OUT_DIR, exist_ok=True)


def prepare_r2_data():
    df, gex_by_date = load_wdo_mt5_raw()
    df = df[(df["session_date"] >= "2026-01-02") & (df["session_date"] <= "2026-11-06")].reset_index(drop=True)

    # Merge WIN M5 day_ret (causal intraday % move from WIN day open!)
    df_win = get_mt5_rates("WIN$N", "M5")[["t", "open", "close"]].copy()
    df_win["session_date"] = df_win["t"].dt.strftime("%Y-%m-%d")
    win_day_open = df_win.groupby("session_date")["open"].transform("first")
    df_win["win_day_ret"] = (df_win["close"] / win_day_open - 1.0) * 100.0  # in %
    df = df.merge(df_win[["t", "win_day_ret"]], on="t", how="left")
    df["win_day_ret"] = df["win_day_ret"].ffill().fillna(0.0)

    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    opens = df["open"].values.astype(float)
    dates = df["session_date"].values
    t_mins = df["t_min"].values.astype(int)
    win_day_ret = df["win_day_ret"].values.astype(float)

    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, 50, 5.0, 2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, 30, 3.0, 1.6)
    ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean().values
    ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean().values

    n = len(df)
    day_open = np.zeros(n, dtype=float)
    day_high = np.zeros(n, dtype=float)
    day_low = np.zeros(n, dtype=float)
    prev_day_high = np.zeros(n, dtype=float)
    prev_day_low = np.zeros(n, dtype=float)
    day_move = np.zeros(n, dtype=float)
    day_eff = np.zeros(n, dtype=float)
    # Causal VWAP proxy (typical price cumulative mean since open)
    vwap = np.zeros(n, dtype=float)

    cur_d = ""
    d_open = 0.0
    d_h = -1e9
    d_l = 1e9
    tp_sum = 0.0
    tp_cnt = 0
    for i in range(n):
        d = dates[i]
        if d != cur_d:
            cur_d = d
            d_open = opens[i]
            prev_day_high[i] = highs[i]
            prev_day_low[i] = lows[i]
            d_h = highs[i]
            d_l = lows[i]
            tp_sum = (highs[i] + lows[i] + closes[i]) / 3.0
            tp_cnt = 1
        else:
            prev_day_high[i] = d_h
            prev_day_low[i] = d_l
            if highs[i] > d_h:
                d_h = highs[i]
            if lows[i] < d_l:
                d_l = lows[i]
            tp_sum += (highs[i] + lows[i] + closes[i]) / 3.0
            tp_cnt += 1
        day_open[i] = d_open
        day_high[i] = d_h
        day_low[i] = d_l
        mv = closes[i] - d_open
        day_move[i] = mv
        day_eff[i] = abs(mv) / max(0.5, d_h - d_l)
        vwap[i] = tp_sum / tp_cnt

    # Fury dates
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

    # Also load WDO M15 for R3_M15_TREND
    df15 = get_mt5_rates("WDO$N", "M15").copy().reset_index(drop=True)
    df15["session_date"] = df15["t"].dt.strftime("%Y-%m-%d")
    df15["t_min"] = df15["t"].dt.hour * 60 + df15["t"].dt.minute
    df15 = df15[(df15["session_date"] >= "2026-01-02") & (df15["session_date"] <= "2026-11-06")].reset_index(drop=True)
    c15 = df15["close"].values.astype(float)
    h15 = df15["high"].values.astype(float)
    l15 = df15["low"].values.astype(float)
    o15 = df15["open"].values.astype(float)
    d15 = df15["session_date"].values
    tm15 = df15["t_min"].values.astype(int)
    n15_c, n15_u, n15_l, _, n15_s = compute_nwe_series(c15, 30, 3.0, 1.6)
    e15_9 = pd.Series(c15).ewm(span=9, adjust=False).mean().values
    e15_21 = pd.Series(c15).ewm(span=21, adjust=False).mean().values

    m15_dmove = np.zeros(len(df15), dtype=float)
    m15_deff = np.zeros(len(df15), dtype=float)
    cd = ""; do = 0.0; dh = -1e9; dl = 1e9
    for i in range(len(df15)):
        if d15[i] != cd:
            cd = d15[i]; do = o15[i]; dh = h15[i]; dl = l15[i]
        else:
            dh = max(dh, h15[i]); dl = min(dl, l15[i])
        mv = c15[i] - do
        m15_dmove[i] = mv
        m15_deff[i] = abs(mv) / max(0.5, dh - dl)

    return {
        "m5": {
            "df": df, "gex_by_date": gex_by_date, "dates": dates, "t_mins": t_mins,
            "opens": opens, "highs": highs, "lows": lows, "closes": closes,
            "n50_c": n50_c, "n50_u": n50_u, "n50_l": n50_l, "n50_s": n50_s,
            "n30_c": n30_c, "n30_u": n30_u, "n30_l": n30_l, "n30_s": n30_s,
            "ema9": ema9, "ema21": ema21, "vwap": vwap,
            "day_open": day_open, "day_high": day_high, "day_low": day_low,
            "prev_day_high": prev_day_high, "prev_day_low": prev_day_low,
            "day_move": day_move, "day_eff": day_eff, "win_day_ret": win_day_ret,
        },
        "m15": {
            "gex_by_date": gex_by_date, "dates": d15, "t_mins": tm15,
            "opens": o15, "highs": h15, "lows": l15, "closes": c15,
            "n_c": n15_c, "n_u": n15_u, "n_l": n15_l, "n_s": n15_s,
            "ema9": e15_9, "ema21": e15_21, "day_move": m15_dmove, "day_eff": m15_deff,
        },
        "fury_dates": fury_dates,
        "all_dates": sorted(set(dates)),
    }


def sim_r2_strategy(data: dict, arch: str, params: dict, cost_pts: float = 0.5, m1_dict: dict | None = None) -> list[dict]:
    is_m15 = (arch == "R3_M15_TREND")
    f = data["m15"] if is_m15 else data["m5"]
    bar_span = 15 if is_m15 else 5

    dates = f["dates"]
    t_mins = f["t_mins"]
    opens = f["opens"]
    highs = f["highs"]
    lows = f["lows"]
    closes = f["closes"]
    gex_by_date = f["gex_by_date"]

    sl_pts = float(params["sl"])
    tp_pts = float(params["tp"])
    be_trig = float(params.get("be_trig", 0.0))
    be_lock = float(params.get("be_lock", 1.0))
    tr_trig = float(params.get("tr_trig", 0.0))
    tr_dist = float(params.get("tr_dist", 8.0))
    max_tr_day = int(params.get("max_tr", 2))
    min_tmin = int(params.get("min_tmin", 570))
    max_tmin = int(params.get("max_tmin", 960))
    max_hold = int(params.get("max_hold", 120))
    use_limit = bool(params.get("use_limit", False))
    lim_bars = int(params.get("lim_bars", 2))

    n = len(closes)
    pos_dir = 0
    entry_px = 0.0
    entry_tmin = 0
    curr_sl = 0.0
    curr_tp = 0.0
    max_fav = 0.0
    be_done = False
    bars_held = 0

    pend_dir = 0
    pend_px = 0.0
    pend_left = 0

    cur_day = ""
    trades_today = 0
    cur_walls = np.array([], dtype=float)
    trades = []

    def close_pos(exit_px: float, reason: str, exit_tmin: int, d_str: str):
        nonlocal pos_dir
        pts = (exit_px - entry_px) * pos_dir - cost_pts
        trades.append({
            "date": d_str, "entry_min": entry_tmin, "exit_min": exit_tmin,
            "dir": pos_dir, "entry_px": entry_px, "exit_px": exit_px,
            "pts": pts, "pnl": pts * 10.0, "reason": reason,
        })
        pos_dir = 0

    def step_open_position(i_bar: int, d: str, tm: int, o_i: float, h_i: float, l_i: float, c_i: float, is_entry_bar: bool):
        nonlocal pos_dir, curr_sl, max_fav, be_done, bars_held
        if tm >= 1035:
            close_pos(o_i, "EOD", tm, d)
            return
        closed = False
        if m1_dict is not None and d in m1_dict:
            m1d = m1_dict[d]
            m_mins, m_o, m_h, m_l = m1d["mins"], m1d["open"], m1d["high"], m1d["low"]
            idx0 = int(np.searchsorted(m_mins, tm, side="left"))
            idx1 = int(np.searchsorted(m_mins, tm + bar_span, side="left"))
            for j in range(idx0, idx1):
                mo, mh, ml = m_o[j], m_h[j], m_l[j]
                if pos_dir == 1:
                    if not is_entry_bar and mo <= curr_sl:
                        close_pos(mo, "SL_GAP", int(m_mins[j]), d); closed = True; break
                    if ml <= curr_sl:
                        close_pos(curr_sl, "SL", int(m_mins[j]), d); closed = True; break
                    if tp_pts > 0 and mh >= curr_tp:
                        close_pos(curr_tp, "TP", int(m_mins[j]), d); closed = True; break
                    if mh - entry_px > max_fav:
                        max_fav = mh - entry_px
                else:
                    if not is_entry_bar and mo >= curr_sl:
                        close_pos(mo, "SL_GAP", int(m_mins[j]), d); closed = True; break
                    if mh >= curr_sl:
                        close_pos(curr_sl, "SL", int(m_mins[j]), d); closed = True; break
                    if tp_pts > 0 and ml <= curr_tp:
                        close_pos(curr_tp, "TP", int(m_mins[j]), d); closed = True; break
                    if entry_px - ml > max_fav:
                        max_fav = entry_px - ml
        else:
            if pos_dir == 1:
                if not is_entry_bar and o_i <= curr_sl:
                    close_pos(o_i, "SL_GAP", tm, d); closed = True
                elif l_i <= curr_sl:
                    close_pos(curr_sl, "SL", tm, d); closed = True
                elif tp_pts > 0 and h_i >= curr_tp:
                    close_pos(curr_tp, "TP", tm, d); closed = True
                else:
                    if h_i - entry_px > max_fav:
                        max_fav = h_i - entry_px
            else:
                if not is_entry_bar and o_i >= curr_sl:
                    close_pos(o_i, "SL_GAP", tm, d); closed = True
                elif h_i >= curr_sl:
                    close_pos(curr_sl, "SL", tm, d); closed = True
                elif tp_pts > 0 and l_i <= curr_tp:
                    close_pos(curr_tp, "TP", tm, d); closed = True
                else:
                    if entry_px - l_i > max_fav:
                        max_fav = entry_px - l_i

        if not closed and pos_dir != 0:
            if not is_entry_bar:
                bars_held += 1
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

    for i in range(2, n):
        d = dates[i]
        tm = t_mins[i]
        o_i, h_i, l_i, c_i = opens[i], highs[i], lows[i], closes[i]

        if d != cur_day:
            if pos_dir != 0:
                close_pos(opens[i - 1], "EOD_OVERNIGHT", t_mins[i - 1], cur_day)
            cur_day = d
            trades_today = 0
            pend_dir = 0
            pend_left = 0
            g = gex_by_date.get(d)
            cur_walls = g["walls"] if g is not None else np.array([], dtype=float)

        if pos_dir != 0:
            step_open_position(i, d, tm, o_i, h_i, l_i, c_i, is_entry_bar=False)
            continue

        # Check active pending Limit order (if any)
        if pend_dir != 0:
            if tm >= max_tmin or tm >= 1020:
                pend_dir = 0; pend_left = 0
            else:
                filled = False
                if pend_dir == 1 and l_i <= pend_px:
                    fill_px = min(o_i, pend_px)
                    filled = True
                elif pend_dir == -1 and h_i >= pend_px:
                    fill_px = max(o_i, pend_px)
                    filled = True
                if filled:
                    pos_dir = pend_dir
                    entry_px = fill_px
                    entry_tmin = tm
                    curr_sl = round05(entry_px - sl_pts) if pos_dir == 1 else round05(entry_px + sl_pts)
                    curr_tp = (round05(entry_px + tp_pts) if pos_dir == 1 else round05(entry_px - tp_pts)) if tp_pts > 0 else 0.0
                    max_fav = 0.0
                    be_done = False
                    bars_held = 0
                    trades_today += 1
                    pend_dir = 0; pend_left = 0
                    # Conservative check on fill bar (SL first!)
                    step_open_position(i, d, tm, o_i, h_i, l_i, c_i, is_entry_bar=True)
                    continue
                else:
                    pend_left -= 1
                    if pend_left <= 0:
                        pend_dir = 0

        if dates[i - 1] != d or tm < min_tmin or tm >= max_tmin or trades_today >= max_tr_day:
            continue

        b1_o, b1_h, b1_l, b1_c = opens[i - 1], highs[i - 1], lows[i - 1], closes[i - 1]
        b2_c = closes[i - 2]
        body1 = b1_c - b1_o
        sig = 0
        lim_px = 0.0

        if arch == "R1_REGIME_GATED":
            dmv = f["day_move"][i - 1]
            deff = f["day_eff"][i - 1]
            s30 = f["n30_s"][i - 1]
            e9 = f["ema9"][i - 1]
            e21 = f["ema21"][i - 1]
            min_dmv = params["min_dmv"]
            min_eff = params["min_eff"]
            mode = params["mode"]
            if dmv >= min_dmv and deff >= min_eff and s30 >= 0.10:
                if mode == "PB_EMA9" and b1_l <= e9 + 1.0 and b1_c > e9 and body1 >= 0.5:
                    sig = 1
                elif mode == "PB_LIM_EMA9" and b1_c > e9 and e9 > e21:
                    sig = 1; lim_px = round05(e9)
                elif mode == "CONT_BAR" and body1 >= 1.5 and b1_c >= f["day_high"][i - 1] - 2.0:
                    sig = 1
            elif dmv <= -min_dmv and deff >= min_eff and s30 <= -0.10:
                if mode == "PB_EMA9" and b1_h >= e9 - 1.0 and b1_c < e9 and body1 <= -0.5:
                    sig = -1
                elif mode == "PB_LIM_EMA9" and b1_c < e9 and e9 < e21:
                    sig = -1; lim_px = round05(e9)
                elif mode == "CONT_BAR" and body1 <= -1.5 and b1_c <= f["day_low"][i - 1] + 2.0:
                    sig = -1

        elif arch == "R2_WALL_RETEST":
            s50 = f["n50_s"][i - 1]
            dmv = f["day_move"][i - 1]
            deff = f["day_eff"][i - 1]
            min_eff = params["min_eff"]
            min_slope = params["min_slope"]
            buf = params["buf"]
            if len(cur_walls) > 0 and deff >= min_eff:
                for w in cur_walls:
                    if b1_o <= w + 1.5 and b1_c >= w + buf and body1 >= params["min_body"] and s50 >= min_slope and dmv > 0:
                        sig = 1; lim_px = round05(w + params["lim_off"]); break
                    if b1_o >= w - 1.5 and b1_c <= w - buf and body1 <= -params["min_body"] and s50 <= -min_slope and dmv < 0:
                        sig = -1; lim_px = round05(w - params["lim_off"]); break

        elif arch == "R3_M15_TREND":
            dmv = f["day_move"][i - 1]
            deff = f["day_eff"][i - 1]
            ns = f["n_s"][i - 1]
            nu = f["n_u"][i - 1]
            nl = f["n_l"][i - 1]
            e9 = f["ema9"][i - 1]
            e21 = f["ema21"][i - 1]
            mode = params["mode"]
            if mode == "NWE_BO":
                if b1_c > nu and b2_c <= f["n_u"][i - 2] and body1 >= params["min_body"] and ns >= params["min_slope"] and deff >= params["min_eff"]:
                    sig = 1
                elif b1_c < nl and b2_c >= f["n_l"][i - 2] and body1 <= -params["min_body"] and ns <= -params["min_slope"] and deff >= params["min_eff"]:
                    sig = -1
            elif mode == "EMA_PB":
                if dmv >= params["min_dmv"] and deff >= params["min_eff"] and e9 > e21 and b1_l <= e9 + 1.5 and b1_c > e9 and body1 >= 1.0:
                    sig = 1
                elif dmv <= -params["min_dmv"] and deff >= params["min_eff"] and e9 < e21 and b1_h >= e9 - 1.5 and b1_c < e9 and body1 <= -1.0:
                    sig = -1
            elif mode == "WALL_BO" and len(cur_walls) > 0:
                for w in cur_walls:
                    if b1_o <= w + 1.5 and b1_c >= w + 2.0 and body1 >= params["min_body"] and ns >= params["min_slope"] and deff >= params["min_eff"]:
                        sig = 1; break
                    if b1_o >= w - 1.5 and b1_c <= w - 2.0 and body1 <= -params["min_body"] and ns <= -params["min_slope"] and deff >= params["min_eff"]:
                        sig = -1; break

        elif arch == "R4_AFTERNOON":
            # Afternoon continuation (13:00-16:00 or 14:00-16:00) in direction of established day trend!
            dmv = f["day_move"][i - 1]
            deff = f["day_eff"][i - 1]
            s50 = f["n50_s"][i - 1]
            vw = f["vwap"][i - 1]
            e9 = f["ema9"][i - 1]
            mode = params["mode"]
            if dmv >= params["min_dmv"] and deff >= params["min_eff"] and b1_c > vw and s50 >= 0.05:
                if mode == "MKT_NDH" and b1_c > f["prev_day_high"][i - 1] and body1 >= 1.5:
                    sig = 1
                elif mode == "PB_EMA9" and b1_l <= e9 + 1.0 and b1_c > e9 and body1 >= 0.5:
                    sig = 1
                elif mode == "LIM_EMA9" and b1_c > e9:
                    sig = 1; lim_px = round05(e9)
            elif dmv <= -params["min_dmv"] and deff >= params["min_eff"] and b1_c < vw and s50 <= -0.05:
                if mode == "MKT_NDH" and b1_c < f["prev_day_low"][i - 1] and body1 <= -1.5:
                    sig = -1
                elif mode == "PB_EMA9" and b1_h >= e9 - 1.0 and b1_c < e9 and body1 <= -0.5:
                    sig = -1
                elif mode == "LIM_EMA9" and b1_c < e9:
                    sig = -1; lim_px = round05(e9)

        elif arch == "R5_NDH_NDL":
            # New Day High / Low breakout after 10:00 with efficiency + slope (Market or Limit pullback)
            dmv = f["day_move"][i - 1]
            deff = f["day_eff"][i - 1]
            s50 = f["n50_s"][i - 1]
            pdh = f["prev_day_high"][i - 1]
            pdl = f["prev_day_low"][i - 1]
            if dmv >= params["min_dmv"] and deff >= params["min_eff"] and s50 >= params["min_slope"]:
                if b1_c > pdh + params["buf"] and body1 >= params["min_body"]:
                    sig = 1
                    if use_limit:
                        lim_px = round05(pdh)
            elif dmv <= -params["min_dmv"] and deff >= params["min_eff"] and s50 <= -params["min_slope"]:
                if b1_c < pdl - params["buf"] and body1 <= -params["min_body"]:
                    sig = -1
                    if use_limit:
                        lim_px = round05(pdl)

        elif arch == "R6_MACRO_WINWDO":
            # True B3 Macro Risk-Off / Risk-On: WIN and WDO trending in OPPOSITE directions strongly!
            dmv = f["day_move"][i - 1]
            deff = f["day_eff"][i - 1]
            wr = f["win_day_ret"][i - 1]
            s30 = f["n30_s"][i - 1]
            e9 = f["ema9"][i - 1]
            w_thr = params["win_ret_thr"]
            if wr <= -w_thr and dmv >= params["min_dmv"] and deff >= params["min_eff"] and s30 >= 0.05:
                if params["entry"] == "PB_EMA9":
                    if b1_l <= e9 + 1.5 and b1_c > e9 and body1 >= 0.5:
                        sig = 1
                elif params["entry"] == "LIM_EMA9":
                    if b1_c > e9:
                        sig = 1; lim_px = round05(e9)
                else:
                    if body1 >= 1.5:
                        sig = 1
            elif wr >= w_thr and dmv <= -params["min_dmv"] and deff >= params["min_eff"] and s30 <= -0.05:
                if params["entry"] == "PB_EMA9":
                    if b1_h >= e9 - 1.5 and b1_c < e9 and body1 <= -0.5:
                        sig = -1
                elif params["entry"] == "LIM_EMA9":
                    if b1_c < e9:
                        sig = -1; lim_px = round05(e9)
                else:
                    if body1 <= -1.5:
                        sig = -1

        if sig != 0:
            if use_limit and lim_px > 0.0:
                pend_dir = sig
                pend_px = lim_px
                pend_left = lim_bars
                # Check if limit fills immediately on bar i
                filled = (pend_dir == 1 and l_i <= pend_px) or (pend_dir == -1 and h_i >= pend_px)
                if filled:
                    fill_px = min(o_i, pend_px) if pend_dir == 1 else max(o_i, pend_px)
                    pos_dir = pend_dir
                    entry_px = fill_px
                    entry_tmin = tm
                    curr_sl = round05(entry_px - sl_pts) if pos_dir == 1 else round05(entry_px + sl_pts)
                    curr_tp = (round05(entry_px + tp_pts) if pos_dir == 1 else round05(entry_px - tp_pts)) if tp_pts > 0 else 0.0
                    max_fav = 0.0; be_done = False; bars_held = 0; trades_today += 1
                    pend_dir = 0; pend_left = 0
                    step_open_position(i, d, tm, o_i, h_i, l_i, c_i, is_entry_bar=True)
            else:
                pos_dir = sig
                entry_px = o_i
                entry_tmin = tm
                curr_sl = round05(entry_px - sl_pts) if pos_dir == 1 else round05(entry_px + sl_pts)
                curr_tp = (round05(entry_px + tp_pts) if pos_dir == 1 else round05(entry_px - tp_pts)) if tp_pts > 0 else 0.0
                max_fav = 0.0; be_done = False; bars_held = 0; trades_today += 1
                step_open_position(i, d, tm, o_i, h_i, l_i, c_i, is_entry_bar=True)

    return trades


def build_r2_grid():
    exits = [
        # (sl, tp, be_trig, be_lock, tr_trig, tr_dist)
        (6.0,  24.0, 6.0, 1.0,  9.0,  5.0),
        (8.0,  35.0, 8.0, 1.0, 12.0,  7.0),
        (10.0, 50.0, 9.0, 1.5, 14.0,  9.0),
        (8.0,   0.0, 7.0, 1.0, 11.0,  7.0),
        (10.0,  0.0, 9.0, 1.5, 14.0, 10.0),
    ]
    grid = []

    # R1: Regime-Gated Trend Rider
    for sl, tp, bt, bl, tt, td in exits:
        for mode in ("PB_EMA9", "PB_LIM_EMA9", "CONT_BAR"):
            for min_dmv in (20.0, 28.0, 35.0):
                for min_eff in (0.55, 0.68):
                    grid.append(("R1_REGIME_GATED", {
                        "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                        "mode": mode, "min_dmv": min_dmv, "min_eff": min_eff,
                        "use_limit": (mode == "PB_LIM_EMA9"), "lim_bars": 2,
                        "max_tr": 2, "min_tmin": 600, "max_tmin": 990,
                    }))

    # R2: Wall Breakout + Limit Retest (EST-04 style!)
    for sl, tp, bt, bl, tt, td in exits:
        for buf in (1.5, 2.5):
            for lim_off in (0.0, 1.0):
                for min_eff in (0.35, 0.55):
                    for min_slope in (0.10, 0.25):
                        grid.append(("R2_WALL_RETEST", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "buf": buf, "lim_off": lim_off, "min_body": 2.0, "min_eff": min_eff, "min_slope": min_slope,
                            "use_limit": True, "lim_bars": 3,
                            "max_tr": 2, "min_tmin": 570, "max_tmin": 960,
                        }))

    # R3: M15 Trend Rider
    for sl, tp, bt, bl, tt, td in exits:
        for mode in ("NWE_BO", "EMA_PB", "WALL_BO"):
            for min_eff in (0.40, 0.58):
                for min_dmv in (12.0, 22.0):
                    grid.append(("R3_M15_TREND", {
                        "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                        "mode": mode, "min_body": 2.5, "min_slope": 0.15, "min_eff": min_eff, "min_dmv": min_dmv,
                        "use_limit": False, "max_tr": 2, "min_tmin": 570, "max_tmin": 960, "max_hold": 40,
                    }))

    # R4: Afternoon Continuation (13:00-16:00 & 14:00-16:00 — mirror of 15h cutoff!)
    for sl, tp, bt, bl, tt, td in exits:
        for mode in ("MKT_NDH", "PB_EMA9", "LIM_EMA9"):
            for min_tmin in (780, 840):  # 13:00, 14:00
                for min_dmv in (15.0, 25.0):
                    for min_eff in (0.50, 0.65):
                        grid.append(("R4_AFTERNOON", {
                            "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                            "mode": mode, "min_dmv": min_dmv, "min_eff": min_eff,
                            "use_limit": (mode == "LIM_EMA9"), "lim_bars": 2,
                            "max_tr": 2, "min_tmin": min_tmin, "max_tmin": 990,
                        }))

    # R5: New Day High/Low Breakout
    for sl, tp, bt, bl, tt, td in exits:
        for use_lim in (False, True):
            for min_dmv in (15.0, 25.0):
                for min_eff in (0.50, 0.65):
                    grid.append(("R5_NDH_NDL", {
                        "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                        "buf": 0.5, "min_body": 1.5, "min_slope": 0.15, "min_dmv": min_dmv, "min_eff": min_eff,
                        "use_limit": use_lim, "lim_bars": 3,
                        "max_tr": 2, "min_tmin": 600, "max_tmin": 960,
                    }))

    # R6: Macro WIN x WDO Aligned Trend Day
    for sl, tp, bt, bl, tt, td in exits:
        for entry in ("PB_EMA9", "LIM_EMA9", "MKT"):
            for win_ret_thr in (0.7, 1.1):
                for min_dmv in (15.0, 22.0):
                    grid.append(("R6_MACRO_WINWDO", {
                        "sl": sl, "tp": tp, "be_trig": bt, "be_lock": bl, "tr_trig": tt, "tr_dist": td,
                        "entry": entry, "win_ret_thr": win_ret_thr, "min_dmv": min_dmv, "min_eff": 0.50,
                        "use_limit": (entry == "LIM_EMA9"), "lim_bars": 2,
                        "max_tr": 2, "min_tmin": 600, "max_tmin": 990,
                    }))

    return grid


def main():
    t0 = time.time()
    print("[1/4] Preparando WDO M5 + M15 + WIN Macro + GEX Walls...", flush=True)
    data = prepare_r2_data()
    all_dates = data["all_dates"]
    fury_dates = data["fury_dates"]

    b3_dir = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026_b3")
    base_trades = load_portfolio_trades(PORTFOLIO_PRESETS["top_10"]["robots"], htm_dir=b3_dir)
    wdo_base_daily = {}
    port_base_daily = {}
    for t in base_trades:
        port_base_daily[t["date"]] = port_base_daily.get(t["date"], 0.0) + float(t["pnl"])
        if t["asset"] == "WDO":
            wdo_base_daily[t["date"]] = wdo_base_daily.get(t["date"], 0.0) + float(t["pnl"])
    base_port_m = _summarize_daily_pnls([port_base_daily.get(d, 0.0) for d in all_dates])
    base_oos_m = _summarize_daily_pnls([port_base_daily.get(d, 0.0) for d in all_dates if d >= "2026-08-01"])
    print(f"      Baseline MT5 REAL B3: Net=R$ {base_port_m['total_pnl']:,.0f} | DD=R$ {base_port_m['max_dd']:,.0f} | Ret/DD={base_port_m['ret_dd']:.2f}x | OOS={base_oos_m['ret_dd']:.2f}x", flush=True)

    grid = build_r2_grid()
    print(f"[2/4] Testando {len(grid)} combinacoes Round 2 (6 arquetipos estruturais WDO)...", flush=True)
    rows = []
    for idx, (arch, params) in enumerate(grid):
        tr = sim_r2_strategy(data, arch, params, cost_pts=0.5, m1_dict=None)
        m = eval_trades_metrics(tr, all_dates, fury_dates, wdo_base_daily, port_base_daily)
        rows.append({"idx": idx, "arch": arch, "params": params, **m})

    df_res = pd.DataFrame(rows)
    df_res.to_csv(os.path.join(OUT_DIR, "r2_all_candidates.csv"), index=False)

    print("\n=== RESUMO ROUND 2 POR ARQUETIPO ===")
    for arch, grp in df_res.groupby("arch"):
        pos_is = (grp["is_net"] > 0).mean() * 100
        pos_oos = (grp["oos_net"] > 0).mean() * 100
        pos_both = ((grp["is_net"] > 0) & (grp["oos_net"] > 0)).mean() * 100
        pos_fury = (grp["fury_pnl"] > 0).mean() * 100
        best = grp[grp["n"] >= 30].sort_values("is_ret_dd", ascending=False).head(1)
        b_str = ""
        if not best.empty:
            r = best.iloc[0]
            b_str = f"BestIS: n={r['n']} Net={r['net']:+.0f} IS_R/DD={r['is_ret_dd']:.2f}x OOS={r['oos_net']:+.0f}(PF={r['oos_pf']:.2f}) Fury={r['fury_pnl']:+.0f} Corr={r['corr_wdo']:+.2f}"
        print(f"  {arch:<16} | Grid={len(grp):>3} | IS>0:{pos_is:5.1f}% | OOS>0:{pos_oos:5.1f}% | Both>0:{pos_both:5.1f}% | Fury>0:{pos_fury:5.1f}% | {b_str}")

    # [3/4] Verify top IS-ranked candidates (with n >= 30) on M1 exact bars + 1.0pt stress + neighborhood
    print("\n[3/4] Verificacao M1 exata + Stress 1.0pt + Vizinhanca nos top candidatos por IS...", flush=True)
    _, wdo_m1 = load_m1_bars()

    cands = []
    seen = set()
    for arch, grp in df_res.groupby("arch"):
        elig = grp[(grp["n"] >= 30) & (grp["is_net"] > 0)].sort_values(["is_ret_dd", "is_pf"], ascending=False).head(6)
        for _, r in elig.iterrows():
            if int(r["idx"]) not in seen:
                cands.append(r); seen.add(int(r["idx"]))
    overall = df_res[(df_res["n"] >= 35) & (df_res["is_net"] > 0)].sort_values("is_ret_dd", ascending=False).head(15)
    for _, r in overall.iterrows():
        if int(r["idx"]) not in seen:
            cands.append(r); seen.add(int(r["idx"]))

    verified = []
    for r in cands:
        arch = r["arch"]
        params = r["params"]
        tr05 = sim_r2_strategy(data, arch, params, cost_pts=0.5, m1_dict=wdo_m1)
        m05 = eval_trades_metrics(tr05, all_dates, fury_dates, wdo_base_daily, port_base_daily)
        tr10 = sim_r2_strategy(data, arch, params, cost_pts=1.0, m1_dict=wdo_m1)
        m10 = eval_trades_metrics(tr10, all_dates, fury_dates, wdo_base_daily, port_base_daily)

        entry_keys = [k for k in params if k not in ("sl", "tp", "be_trig", "be_lock", "tr_trig", "tr_dist")]
        nbrs = [x for x in rows if x["arch"] == arch and all(x["params"].get(k) == params.get(k) for k in entry_keys)]
        loc_pos = 100.0 * sum(1 for x in nbrs if x["net"] > 0) / max(1, len(nbrs))
        loc_oos = 100.0 * sum(1 for x in nbrs if x["oos_net"] > 0) / max(1, len(nbrs))

        # 5 Strict Anti-Overfitting Gates
        g1 = (m05["n"] >= 35) and (m05["is_net"] > 0) and (m05["is_pf"] >= 1.25) and (m05["is_ret_dd"] >= 1.8)
        g2 = (m05["oos_net"] > 0) and (m05["oos_pf"] >= 1.15) and (m05["oos_ret_dd"] >= 1.0)
        g3 = (m05["pos_months_pct"] >= 55.0) and (m10["net"] > 0) and (m10["oos_net"] > 0)
        g4 = (loc_pos >= 60.0) and (loc_oos >= 50.0)
        g5 = (m05["corr_wdo"] <= 0.25) and (m05["fury_pnl"] > 0) and (
            m05["comb_ret_dd"] > base_port_m["ret_dd"] or m05["comb_sharpe"] > base_port_m["sharpe"]
        )
        gp = int(g1) + int(g2) + int(g3) + int(g4) + int(g5)
        verified.append({
            "arch": arch, "params": params, "m1_05": m05,
            "m1_10_net": m10["net"], "m1_10_oos": m10["oos_net"],
            "loc_pos": round(loc_pos, 1), "loc_oos": round(loc_oos, 1),
            "gates": {"G1_IS": g1, "G2_OOS": g2, "G3_TIME_COST": g3, "G4_NBR": g4, "G5_SYNERGY": g5},
            "gates_passed": gp,
        })

    verified.sort(key=lambda x: (x["gates_passed"], x["m1_05"]["comb_ret_dd"], x["m1_05"]["ret_dd"]), reverse=True)

    print(f"\n=== TOP 15 CANDIDATOS ROUND 2 VERIFICADOS EM M1 EXATO (Baseline Comb R/DD = {base_port_m['ret_dd']:.2f}x) ===")
    print(f"{'Gates':<5} | {'Arch':<15} | {'N':>4} | {'Net':>6} | {'DD':>5} | {'R/DD':>5} | {'PF':>4} | {'IS R/DD':>7} | {'OOSNet':>6} | {'OOSPF':>5} | {'Fury':>6} | {'Corr':>5} | {'Str1p':>5} | {'CombR/DD':>8} | {'Loc%':>4}")
    for v in verified[:15]:
        m = v["m1_05"]
        print(
            f"{v['gates_passed']}/5   | {v['arch']:<15} | {m['n']:>4} | {m['net']:>6.0f} | {m['dd']:>5.0f} | "
            f"{m['ret_dd']:>5.2f} | {m['pf']:>4.2f} | {m['is_ret_dd']:>6.2f}x | {m['oos_net']:>6.0f} | "
            f"{m['oos_pf']:>5.2f} | {m['fury_pnl']:>+6.0f} | {m['corr_wdo']:>+5.2f} | {v['m1_10_net']:>5.0f} | "
            f"{m['comb_ret_dd']:>7.2f}x | {v['loc_pos']:>4.0f}"
        )

    if verified:
        print("\n=== DETALHES DOS TOP 3 CANDIDATOS ===")
        for idx, v in enumerate(verified[:3], 1):
            print(f"#{idx} [{v['gates_passed']}/5] {v['arch']} | Gates={v['gates']}")
            print(f"   Params: {v['params']}")
            print(f"   M1(0.5pt): {v['m1_05']}")
            print(f"   M1(1.0pt): Net={v['m1_10_net']} | OOS={v['m1_10_oos']} | LocPos={v['loc_pos']}% | LocOOS={v['loc_oos']}%")

    out_json = os.path.join(OUT_DIR, "wdo_directional_r2_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"baseline": {"full": base_port_m, "oos": base_oos_m}, "verified_top": verified[:25]}, f, indent=2, default=str)
    print(f"\n[DONE in {time.time() - t0:.1f}s] Saved -> {out_json}", flush=True)


if __name__ == "__main__":
    main()
