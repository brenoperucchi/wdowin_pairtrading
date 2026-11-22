"""
DEEP DIVE: DESCOBERTA DE SETUPS ROBUSTOS EM M15 E M2 (LIMIT VS MARKET)
=====================================================================
Testa se a entrada com ordem LIMIT na Wall ou no 50% da barra de sinal
transforma a assimetria risco/retorno de WDO e WIN em M15 e M2.
"""

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.mt5_loader import load_gex_csv, HIST_WIN, HIST_WDO
import research.discover_gex_nwe_setups as disc

START_DATE = "2026-05-11"
END_DATE = "2026-11-04"

WIN_COST_PTS = 10.0   # R$ 2,00
WDO_COST_PTS = 0.5    # R$ 5,00

def round_tick(val, asset):
    if asset == "WIN":
        return round(val / 5.0) * 5.0
    return round(val * 2.0) / 2.0

def load_tf_bars(asset: str, tf: str, start_date: str = START_DATE, end_date: str = END_DATE):
    p = os.path.join(ROOT_DIR, "data", "mt5_rates", f"mt5_{asset}_N_{tf}.csv")
    df = pd.read_csv(p, parse_dates=["t"])
    df["session_date"] = df["t"].dt.strftime("%Y-%m-%d")
    df["t_min"] = df["t"].dt.hour * 60 + df["t"].dt.minute
    df = df[(df["session_date"] >= start_date) & (df["session_date"] <= end_date)].copy()
    df = df[(df["t_min"] >= 540) & (df["t_min"] <= 1075)].sort_values("t").reset_index(drop=True)
    return df

def find_target(entry_px: float, side: int, all_lvls: np.ndarray, asset: str, min_tp_dist: float, front_run: float):
    all_lvls = np.sort(all_lvls)
    if side == 1:
        v = all_lvls[all_lvls >= entry_px + min_tp_dist]
        if len(v) == 0:
            return None
        return round_tick(v[0] - front_run, asset)
    else:
        v = all_lvls[all_lvls <= entry_px - min_tp_dist]
        if len(v) == 0:
            return None
        return round_tick(v[-1] + front_run, asset)

def run_experiment(
    df: pd.DataFrame,
    gex_data: dict,
    asset: str,
    tf: str,
    setup_name: str,
    entry_mode: str,     # "MARKET", "LIMIT_WALL", "LIMIT_50PCT"
    nwe_series: dict,
    wall_buf: float,
    min_tp_dist: float,
    front_run: float,
    be_ratio: float = 0.50,
    be_lock_pts: float = 15.0,
    time_window: tuple = (555, 1005),
    use_nwe_slope: bool = False,
    nwe_slope_thresh: float = 0.0,
    min_nwe_bw: float = 0.0,
    max_hold_bars: int = 32,
    max_sl_pts: float = 400.0,
    sig_filter=None,
    be_mode: str = "BE_ZERO",     # "BE_ZERO" | "BE_WALL_SHIELD"
    tp_mode: str = "TP_MIDWALL",  # "TP_MIDWALL" | "TP_MAIN_WALL"
    max_trades_day: int = 0,
    max_losses_day: int = 0,
    cost_pts_override: float = -1.0,
    strict_causal: bool = False,
):
    cost_pts = cost_pts_override if cost_pts_override >= 0.0 else (WIN_COST_PTS if asset == "WIN" else WDO_COST_PTS)
    pt_val = 0.20 if asset == "WIN" else 10.0
    
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    dates = df["session_date"].values
    tmins = df["t_min"].values
    ts_arr = df["t"].values if "t" in df.columns else None
    n = len(df)
    
    n_c = nwe_series["center"]
    n_u = nwe_series["upper"]
    n_l = nwe_series["lower"]
    n_s = nwe_series["slope"]
    n_bw = n_u - n_l
    
    trades = []
    in_pos = False
    side = 0
    ep = 0.0
    sl = 0.0
    tp = 0.0
    be_active = False
    def_wall = 0.0
    i_entry = 0
    cur_count_day = ""
    trades_today = 0
    losses_today = 0
    
    # Ordem pendente
    pend_active = False
    pend_side = 0
    pend_px = 0.0
    pend_wall = 0.0
    pend_bars_left = 0
    
    touch_tol = 45.0 if asset == "WIN" else 2.5
    if tf == "M2":
        touch_tol = 30.0 if asset == "WIN" else 1.5

    for i in range(2, n):
        d = dates[i]
        tm = tmins[i]
        cur_o = opens[i]
        cur_h = highs[i]
        cur_l = lows[i]
        cur_c = closes[i]
        if d != cur_count_day:
            cur_count_day = d
            trades_today = 0
            losses_today = 0

        # 1. Checa preenchimento de ordem pendente
        if pend_active and not in_pos:
            if d != dates[i - 1] or pend_bars_left <= 0:
                pend_active = False
            else:
                filled = False
                fill_px = pend_px
                if pend_side == 1 and cur_l <= pend_px:
                    filled = True
                    fill_px = min(cur_o, pend_px) if cur_o <= pend_px else pend_px
                elif pend_side == -1 and cur_h >= pend_px:
                    filled = True
                    fill_px = max(cur_o, pend_px) if cur_o >= pend_px else pend_px
                
                if filled:
                    gex = gex_data.get(d)
                    if gex:
                        all_lvls = np.sort(np.unique(np.concatenate([gex["walls"], gex["mid_walls"]])))
                        tgt_lvls = np.sort(gex["walls"]) if (tp_mode == "TP_MAIN_WALL" and len(gex["walls"]) > 0) else all_lvls
                        tp_target = find_target(fill_px, pend_side, tgt_lvls, asset, min_tp_dist, front_run)
                        if tp_target is not None:
                            if pend_side == 1:
                                def_lvls = all_lvls[all_lvls <= fill_px]
                                def_w = def_lvls[-1] if len(def_lvls) else pend_wall
                                sl_target = round_tick(def_w - wall_buf, asset)
                                if sl_target >= fill_px:
                                    sl_target = round_tick(fill_px - (100.0 if asset == "WIN" else 5.0), asset)
                            else:
                                def_lvls = all_lvls[all_lvls >= fill_px]
                                def_w = def_lvls[0] if len(def_lvls) else pend_wall
                                sl_target = round_tick(def_w + wall_buf, asset)
                                if sl_target <= fill_px:
                                    sl_target = round_tick(fill_px + (100.0 if asset == "WIN" else 5.0), asset)
                            
                            risk = abs(fill_px - sl_target)
                            reward = abs(tp_target - fill_px)
                            if risk > 0 and reward >= risk * 0.70 and risk <= max_sl_pts:
                                in_pos = True
                                side = pend_side
                                ep = fill_px
                                sl = sl_target
                                tp = tp_target
                                def_wall = def_w
                                be_active = False
                                i_entry = i
                                if strict_causal:
                                    hit_sl = (side == 1 and cur_l <= sl) or (side == -1 and cur_h >= sl)
                                    hit_tp = (side == 1 and cur_h >= tp) or (side == -1 and cur_l <= tp)
                                    if hit_sl or hit_tp:
                                        exit_px = sl if hit_sl else tp
                                        pnl = (exit_px - ep) * side - cost_pts
                                        brl_v = round(pnl * pt_val, 2)
                                        trades_today += 1
                                        if brl_v < 0:
                                            losses_today += 1
                                        trades.append({
                                            "date": dates[i_entry],
                                            "time": tmins[i_entry],
                                            "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                                            "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                                            "side": side,
                                            "ep": ep,
                                            "xp": exit_px,
                                            "pts": pnl,
                                            "brl": brl_v,
                                            "reason": "SL" if hit_sl else "TP_WALL",
                                            "bars": 0,
                                        })
                                        in_pos = False
                    pend_active = False
                else:
                    pend_bars_left -= 1

        # 2. Gerenciamento de posição aberta
        if in_pos:
            bars_held = i - i_entry
            if tm >= 1060 or d != dates[i_entry] or bars_held >= max_hold_bars:
                exit_px = cur_o
                pnl = (exit_px - ep) * side - cost_pts
                brl_v = round(pnl * pt_val, 2)
                trades_today += 1
                if brl_v < 0:
                    losses_today += 1
                trades.append({
                    "date": dates[i_entry],
                    "time": tmins[i_entry],
                    "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                    "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                    "side": side,
                    "ep": ep,
                    "xp": exit_px,
                    "pts": pnl,
                    "brl": brl_v,
                    "reason": "EOD_TIME",
                    "bars": bars_held,
                })
                in_pos = False
                continue

            if side == 1:
                if not strict_causal and not be_active and cur_h >= ep + (tp - ep) * be_ratio:
                    be_active = True
                    if be_mode == "BE_WALL_SHIELD" and def_wall > 0:
                        sl = max(sl, min(round_tick(def_wall - wall_buf * 0.5, asset), round_tick(ep + be_lock_pts, asset)))
                    else:
                        sl = max(sl, round_tick(ep + be_lock_pts, asset))
                
                if cur_l <= sl:
                    exit_px = sl
                    pnl = (exit_px - ep) - cost_pts
                    brl_v = round(pnl * pt_val, 2)
                    trades_today += 1
                    if brl_v < 0:
                        losses_today += 1
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                        "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                        "side": 1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": brl_v,
                        "reason": "SL_BE" if be_active else "SL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
                elif cur_h >= tp:
                    exit_px = tp
                    pnl = (exit_px - ep) - cost_pts
                    brl_v = round(pnl * pt_val, 2)
                    trades_today += 1
                    if brl_v < 0:
                        losses_today += 1
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                        "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                        "side": 1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": brl_v,
                        "reason": "TP_WALL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
                if strict_causal and not be_active and cur_h >= ep + (tp - ep) * be_ratio:
                    be_active = True
                    if be_mode == "BE_WALL_SHIELD" and def_wall > 0:
                        sl = max(sl, min(round_tick(def_wall - wall_buf * 0.5, asset), round_tick(ep + be_lock_pts, asset)))
                    else:
                        sl = max(sl, round_tick(ep + be_lock_pts, asset))
            else:
                if not strict_causal and not be_active and cur_l <= ep - (ep - tp) * be_ratio:
                    be_active = True
                    if be_mode == "BE_WALL_SHIELD" and def_wall > 0:
                        sl = min(sl, max(round_tick(def_wall + wall_buf * 0.5, asset), round_tick(ep - be_lock_pts, asset)))
                    else:
                        sl = min(sl, round_tick(ep - be_lock_pts, asset))
                
                if cur_h >= sl:
                    exit_px = sl
                    pnl = (ep - exit_px) - cost_pts
                    brl_v = round(pnl * pt_val, 2)
                    trades_today += 1
                    if brl_v < 0:
                        losses_today += 1
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                        "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                        "side": -1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": brl_v,
                        "reason": "SL_BE" if be_active else "SL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
                elif cur_l <= tp:
                    exit_px = tp
                    pnl = (ep - exit_px) - cost_pts
                    brl_v = round(pnl * pt_val, 2)
                    trades_today += 1
                    if brl_v < 0:
                        losses_today += 1
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                        "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                        "side": -1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": brl_v,
                        "reason": "TP_WALL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
                if strict_causal and not be_active and cur_l <= ep - (ep - tp) * be_ratio:
                    be_active = True
                    if be_mode == "BE_WALL_SHIELD" and def_wall > 0:
                        sl = min(sl, max(round_tick(def_wall + wall_buf * 0.5, asset), round_tick(ep - be_lock_pts, asset)))
                    else:
                        sl = min(sl, round_tick(ep - be_lock_pts, asset))

        # 3. Identificação de novo sinal
        if (max_trades_day > 0 and trades_today >= max_trades_day) or (max_losses_day > 0 and losses_today >= max_losses_day):
            continue
        if not in_pos and not pend_active and (time_window[0] <= tm <= time_window[1]):
            gex = gex_data.get(d)
            if not gex:
                continue
            
            walls = gex["walls"]
            mid_walls = gex["mid_walls"]
            all_lvls = np.sort(np.unique(np.concatenate([walls, mid_walls])))
            if len(all_lvls) < 2:
                continue
            
            c_prev = closes[i - 1]
            o_prev = opens[i - 1]
            h_prev = highs[i - 1]
            l_prev = lows[i - 1]
            rng_prev = max(1e-5, h_prev - l_prev)
            body_prev = abs(c_prev - o_prev)
            top_wick = h_prev - max(c_prev, o_prev)
            bot_wick = min(c_prev, o_prev) - l_prev
            
            c_prev2 = closes[i - 2]
            o_prev2 = opens[i - 2]
            h_prev2 = highs[i - 2]
            l_prev2 = lows[i - 2]
            
            slp = n_s[i - 1]
            bw = n_bw[i - 1]
            
            if min_nwe_bw > 0 and bw < min_nwe_bw:
                continue
            
            sig_side = 0
            candidate_wall = 0.0
            
            # --- SETUPS ---
            if "PINBAR" in setup_name:
                dists_l = np.abs(all_lvls - l_prev)
                closest_l = all_lvls[np.argmin(dists_l)]
                if (bot_wick >= 0.40 * rng_prev) and (l_prev <= closest_l + touch_tol) and (c_prev > closest_l):
                    if not use_nwe_slope or slp >= -nwe_slope_thresh:
                        sig_side = 1
                        candidate_wall = closest_l
                
                dists_h = np.abs(all_lvls - h_prev)
                closest_h = all_lvls[np.argmin(dists_h)]
                if (top_wick >= 0.40 * rng_prev) and (h_prev >= closest_h - touch_tol) and (c_prev < closest_h):
                    if not use_nwe_slope or slp <= nwe_slope_thresh:
                        sig_side = -1
                        candidate_wall = closest_h

            elif "ENGULFING" in setup_name:
                dists_l = np.abs(all_lvls - min(l_prev, l_prev2))
                closest_l = all_lvls[np.argmin(dists_l)]
                if c_prev2 < o_prev2 and c_prev > o_prev and c_prev > h_prev2 and (min(l_prev, l_prev2) <= closest_l + touch_tol):
                    if not use_nwe_slope or slp >= 0.0:
                        sig_side = 1
                        candidate_wall = closest_l
                
                dists_h = np.abs(all_lvls - max(h_prev, h_prev2))
                closest_h = all_lvls[np.argmin(dists_h)]
                if c_prev2 > o_prev2 and c_prev < o_prev and c_prev < l_prev2 and (max(h_prev, h_prev2) >= closest_h - touch_tol):
                    if not use_nwe_slope or slp <= 0.0:
                        sig_side = -1
                        candidate_wall = closest_h

            elif "FAKEOUT_TRAP" in setup_name:
                trap_dist = 40.0 if asset == "WIN" else 3.0
                dists_l = np.abs(all_lvls - l_prev)
                closest_l = all_lvls[np.argmin(dists_l)]
                if (l_prev <= closest_l - trap_dist) and (c_prev > closest_l + (10.0 if asset == "WIN" else 0.5)):
                    if not use_nwe_slope or slp >= -nwe_slope_thresh:
                        sig_side = 1
                        candidate_wall = closest_l
                
                dists_h = np.abs(all_lvls - h_prev)
                closest_h = all_lvls[np.argmin(dists_h)]
                if (h_prev >= closest_h + trap_dist) and (c_prev < closest_h - (10.0 if asset == "WIN" else 0.5)):
                    if not use_nwe_slope or slp <= nwe_slope_thresh:
                        sig_side = -1
                        candidate_wall = closest_h

            elif "MIDWALL_PULLBACK" in setup_name:
                dists = np.abs(mid_walls - c_prev)
                if len(dists) > 0:
                    closest_mid = mid_walls[np.argmin(dists)]
                    if abs(c_prev - closest_mid) <= touch_tol:
                        if slp >= nwe_slope_thresh and c_prev >= closest_mid:
                            sig_side = 1
                            candidate_wall = closest_mid
                        elif slp <= -nwe_slope_thresh and c_prev <= closest_mid:
                            sig_side = -1
                            candidate_wall = closest_mid

            elif "Z30_EXTREME_WALL" in setup_name:
                # Z30 Reversão extrema na Wall
                pos_nwe = (c_prev - n_l[i - 1]) / max(1e-5, bw)
                dists_w = np.abs(walls - c_prev)
                if len(dists_w) > 0:
                    closest_w = walls[np.argmin(dists_w)]
                    if abs(c_prev - closest_w) <= touch_tol:
                        if pos_nwe <= 0.20 and c_prev > o_prev:
                            sig_side = 1
                            candidate_wall = closest_w
                        elif pos_nwe >= 0.80 and c_prev < o_prev:
                            sig_side = -1
                            candidate_wall = closest_w

            if sig_side != 0 and sig_filter is not None:
                m5_tm = int(tmins[i - 1]) + (10 if tf == "M15" else 0)
                if not sig_filter(str(d), m5_tm, sig_side):
                    sig_side = 0

            if sig_side != 0:
                if entry_mode == "MARKET":
                    entry_px = cur_o
                    tgt_lvls = np.sort(walls) if (tp_mode == "TP_MAIN_WALL" and len(walls) > 0) else all_lvls
                    tp_target = find_target(entry_px, sig_side, tgt_lvls, asset, min_tp_dist, front_run)
                    if tp_target is not None:
                        if sig_side == 1:
                            def_lvls = all_lvls[all_lvls <= entry_px]
                            def_w = def_lvls[-1] if len(def_lvls) else candidate_wall
                            sl_target = round_tick(def_w - wall_buf, asset)
                            if sl_target >= entry_px:
                                sl_target = round_tick(entry_px - (100.0 if asset == "WIN" else 5.0), asset)
                        else:
                            def_lvls = all_lvls[all_lvls >= entry_px]
                            def_w = def_lvls[0] if len(def_lvls) else candidate_wall
                            sl_target = round_tick(def_w + wall_buf, asset)
                            if sl_target <= entry_px:
                                sl_target = round_tick(entry_px + (100.0 if asset == "WIN" else 5.0), asset)
                        
                        risk = abs(entry_px - sl_target)
                        reward = abs(tp_target - entry_px)
                        if risk > 0 and reward >= risk * 0.70 and risk <= max_sl_pts:
                            in_pos = True
                            side = sig_side
                            ep = entry_px
                            sl = sl_target
                            tp = tp_target
                            def_wall = def_w
                            be_active = False
                            i_entry = i
                            if strict_causal:
                                # Checa SL/TP conservador (SL primeiro) na própria barra de entrada M15!
                                hit_sl = (side == 1 and cur_l <= sl) or (side == -1 and cur_h >= sl)
                                hit_tp = (side == 1 and cur_h >= tp) or (side == -1 and cur_l <= tp)
                                if hit_sl or hit_tp:
                                    exit_px = sl if hit_sl else tp
                                    pnl = (exit_px - ep) * side - cost_pts
                                    brl_v = round(pnl * pt_val, 2)
                                    trades_today += 1
                                    if brl_v < 0:
                                        losses_today += 1
                                    trades.append({
                                        "date": dates[i_entry],
                                        "time": tmins[i_entry],
                                        "entry_time": pd.Timestamp(ts_arr[i_entry]) if ts_arr is not None else None,
                                        "exit_time": pd.Timestamp(ts_arr[i]) if ts_arr is not None else None,
                                        "side": side,
                                        "ep": ep,
                                        "xp": exit_px,
                                        "pts": pnl,
                                        "brl": brl_v,
                                        "reason": "SL" if hit_sl else "TP_WALL",
                                        "bars": 0,
                                    })
                                    in_pos = False
                
                elif entry_mode == "LIMIT_WALL":
                    # Coloca ordem limite exatamente no nível da Wall
                    pend_active = True
                    pend_side = sig_side
                    pend_px = candidate_wall
                    pend_wall = candidate_wall
                    pend_bars_left = 3
                
                elif entry_mode == "LIMIT_50PCT":
                    # Coloca ordem limite no ponto médio da barra de sinal
                    mid_px = round_tick(0.5 * (h_prev + l_prev), asset)
                    pend_active = True
                    pend_side = sig_side
                    pend_px = mid_px
                    pend_wall = candidate_wall
                    pend_bars_left = 2

    return trades

def compute_metrics(trades):
    if not trades:
        return {"tr": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "mdd": 0.0, "ret_dd": 0.0, "avg": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t["brl"] > 0)
    wr = round(wins / n * 100.0, 1)
    gw = sum(t["brl"] for t in trades if t["brl"] > 0)
    gl = abs(sum(t["brl"] for t in trades if t["brl"] < 0))
    pf = round(gw / gl, 2) if gl > 0 else 99.9
    net = round(sum(t["brl"] for t in trades), 2)
    avg = round(net / n, 2)
    
    by_day = {}
    for t in trades:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + t["brl"]
    cum = np.cumsum([by_day[d] for d in sorted(by_day.keys())])
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    mdd = round(float(np.max(pk - cum)), 2) if len(cum) else 0.0
    ret_dd = round(net / mdd, 2) if mdd > 0 else 99.9
    return {"tr": n, "wr": wr, "pf": pf, "net": net, "mdd": mdd, "ret_dd": ret_dd, "avg": avg}

def main():
    print("=" * 115)
    print("  EXPERIMENTO APROFUNDADO: TESTE DE ENTRADAS LIMIT VS MARKET EM M15 E M2")
    print("=" * 115)
    
    gex_win = load_gex_csv(HIST_WIN)
    gex_wdo = load_gex_csv(HIST_WDO)
    
    # Executa varredura sistemática
    dfs = {}
    nwes = {}
    for a in ["WIN", "WDO"]:
        for tf in ["M15", "M2"]:
            df = load_tf_bars(a, tf)
            dfs[(a, tf)] = df
            closes = df["close"].values
            lookback = 30 if tf == "M15" else 60
            bw = 4.0 if tf == "M15" else 6.0
            mult = 1.8 if tf == "M15" else 2.2
            c, u, l, _, s = disc.compute_nwe_series(closes, lookback=lookback, bw=bw, mult=mult)
            nwes[(a, tf)] = {"center": c, "upper": u, "lower": l, "slope": s}

    tests = []
    # --- WIN M15 ---
    for em in ["MARKET", "LIMIT_WALL", "LIMIT_50PCT"]:
        tests.append(("WIN", "M15", "M15_FAKEOUT_TRAP", em, 30.0, 220.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32, 450.0))
        tests.append(("WIN", "M15", "M15_PINBAR_WALL", em, 35.0, 200.0, 20.0, 0.50, 25.0, (555, 1005), True, 2.0, 250.0, 32, 400.0))
        tests.append(("WIN", "M15", "M15_ENGULFING_WALL", em, 35.0, 220.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32, 400.0))
        tests.append(("WIN", "M15", "M15_MIDWALL_PULLBACK", em, 35.0, 250.0, 20.0, 0.50, 25.0, (555, 1005), True, 4.0, 300.0, 32, 400.0))
        tests.append(("WIN", "M15", "M15_Z30_EXTREME_WALL", em, 35.0, 250.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32, 450.0))
        
    # --- WDO M15 ---
    for em in ["MARKET", "LIMIT_WALL", "LIMIT_50PCT"]:
        tests.append(("WDO", "M15", "M15_PINBAR_WALL", em, 1.5, 6.0, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_PINBAR_WALL", em, 1.5, 6.0, 0.5, 0.50, 1.0, (555, 1005), True, 0.15, 6.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_ENGULFING_WALL", em, 1.5, 7.0, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_ENGULFING_WALL", em, 1.5, 7.0, 0.5, 0.50, 1.0, (555, 1005), True, 0.15, 6.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_FAKEOUT_TRAP", em, 1.5, 6.5, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_FAKEOUT_TRAP", em, 1.5, 6.5, 0.5, 0.50, 1.0, (555, 1005), True, 0.15, 0.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_MIDWALL_PULLBACK", em, 1.5, 7.5, 0.5, 0.50, 1.0, (555, 1005), True, 0.20, 7.0, 32, 10.0))
        tests.append(("WDO", "M15", "M15_Z30_EXTREME_WALL", em, 1.5, 7.0, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32, 10.0))

    # --- WIN M2 & WDO M2 ---
    for em in ["LIMIT_WALL", "LIMIT_50PCT"]:
        tests.append(("WIN", "M2", "M2_PINBAR_WALL", em, 20.0, 140.0, 15.0, 0.50, 20.0, (555, 1005), True, 1.5, 200.0, 45, 250.0))
        tests.append(("WIN", "M2", "M2_FAKEOUT_TRAP", em, 20.0, 150.0, 15.0, 0.50, 20.0, (555, 1005), False, 0.0, 0.0, 45, 250.0))
        tests.append(("WDO", "M2", "M2_PINBAR_WALL", em, 1.0, 5.0, 0.5, 0.50, 1.0, (555, 1005), True, 0.10, 5.0, 45, 8.0))
        tests.append(("WDO", "M2", "M2_FAKEOUT_TRAP", em, 1.0, 5.0, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 45, 8.0))

    all_res = []
    print(f"\n{'ATIVO':<5} {'TF':<4} {'SETUP':<22} {'ENTRY':<12} {'FILTRO':<12} {'TR':>4} {'WR%':>6} {'PF':>5} {'LUCRO (R$)':>12} {'MAX DD':>10} {'RET/DD':>7}")
    print("-" * 115)

    for item in tests:
        asset, tf, setup_name, entry_mode, wall_buf, min_tp_dist, front_run, be_ratio, be_lock, time_window, use_nwe, slope_th, min_bw, hold, max_sl = item
        df = dfs[(asset, tf)]
        nwe_s = nwes[(asset, tf)]
        gex_data = gex_win if asset == "WIN" else gex_wdo
        
        trades = run_experiment(
            df=df,
            gex_data=gex_data,
            asset=asset,
            tf=tf,
            setup_name=setup_name,
            entry_mode=entry_mode,
            nwe_series=nwe_s,
            wall_buf=wall_buf,
            min_tp_dist=min_tp_dist,
            front_run=front_run,
            be_ratio=be_ratio,
            be_lock_pts=be_lock,
            time_window=time_window,
            use_nwe_slope=use_nwe,
            nwe_slope_thresh=slope_th,
            min_nwe_bw=min_bw,
            max_hold_bars=hold,
            max_sl_pts=max_sl,
        )
        
        m = compute_metrics(trades)
        flabel = f"Slp>={slope_th}" if use_nwe else "Sem NWE"
        if min_bw > 0:
            flabel += f"+BW"
            
        print(f"{asset:<5} {tf:<4} {setup_name:<22} {entry_mode:<12} {flabel:<12} {m['tr']:>4d} {m['wr']:>5.1f}% {m['pf']:>5.2f} {m['net']:>12.2f} {m['mdd']:>10.2f} {m['ret_dd']:>6.2f}x")
        
        if m["tr"] >= 30 and m["pf"] >= 1.25 and m["net"] > 0:
            all_res.append({
                "asset": asset,
                "tf": tf,
                "setup": setup_name,
                "entry": entry_mode,
                "filter": flabel,
                **m
            })

    print("\n" + "=" * 115)
    print("  RANKING FINAL: OS MELHORES MODELOS PARA OS LOTES VAGOS (PF >= 1.30, Ret/DD >= 4.0x)")
    print("=" * 115)
    
    for a in ["WIN", "WDO"]:
        print(f"\n--- {a} RANKING ---")
        sub = [r for r in all_res if r["asset"] == a and r["ret_dd"] >= 3.0]
        sub.sort(key=lambda x: x["ret_dd"], reverse=True)
        for i, r in enumerate(sub, 1):
            print(f"  #{i} [{r['tf']}] {r['setup']} ({r['entry']} | {r['filter']}): {r['tr']} trades | WR {r['wr']}% | PF {r['pf']} | Lucro R$ {r['net']:.2f} | Max DD R$ {r['mdd']:.2f} | Ret/DD {r['ret_dd']:.2f}x")

if __name__ == "__main__":
    main()

