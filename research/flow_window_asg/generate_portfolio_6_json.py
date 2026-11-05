import os
import sys
import json
import inspect
import numpy as np
import pandas as pd

ROOT_DIR = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import eval_mt5_with_dashboard_filters as emdf
from eval_mt5_with_dashboard_filters import (
    load_all_dashboard_features,
    align_dashboard_arrays,
    build_filter_masks,
    precompute_grid_bars,
    run_win_strategy,
    run_wdo_strategy,
    mod_est16,
    mod_wdo16,
    mod_wdo_mix,
    compute_nwe_series,
    find_next_wall_behind,
)

def fmt_tmin(tm_val):
    tm_i = int(tm_val)
    return f"{tm_i // 60:02d}:{tm_i % 60:02d}"

import importlib
importlib.reload(mod_est16)
importlib.reload(mod_wdo_mix)

# 1. Patch mod_est16.simulate_single_est_slot to also include entry_time, exit_time, entry_price, exit_price, stop_price, tp_price
src_est16 = inspect.getsource(mod_est16.simulate_single_est_slot)
src_est16 = src_est16.replace(
    "        if sig_dir == 0:\n            idx += 1\n            continue",
    "        if not _check_dash_filter(b1_idx, sig_dir):\n            sig_dir = 0\n        if sig_dir == 0:\n            idx += 1\n            continue",
    1,
)
target_est16 = """            trades.append({
                "date": today_str,
                "est_id": est_id,
                "side": int(sig_dir),
                "pnl_pts": net_pts_unit * lots,
                "contracts": lots,
                "pnl_brl": net_pts_unit * lots * 0.20,
            })"""
repl_est16 = """            trades.append({
                "date": today_str,
                "est_id": est_id,
                "side": int(sig_dir),
                "entry_time": f"{int(t_mins[idx])//60:02d}:{int(t_mins[idx])%60:02d}",
                "exit_time": f"{int(t_mins[min(j, n-1)])//60:02d}:{int(t_mins[min(j, n-1)])%60:02d}",
                "entry_price": float(avg_price),
                "exit_price": float(exit_px),
                "stop_price": float(round5(avg_price - sl_pts) if sig_dir == 1 else round5(avg_price + sl_pts)),
                "tp_price": float(tp2_px),
                "be_triggered": bool(be_active),
                "pnl_pts": net_pts_unit * lots,
                "contracts": lots,
                "pnl_brl": net_pts_unit * lots * 0.20,
            })"""
assert target_est16 in src_est16, "target_est16 not found"
ns_est16 = dict(mod_est16.__dict__)
ns_est16["_check_dash_filter"] = lambda b_idx, s_dir: (
    True if (emdf._ACTIVE_FILTER_BUY is None or s_dir == 0)
    else (bool(emdf._ACTIVE_FILTER_BUY[b_idx]) if s_dir == 1 else bool(emdf._ACTIVE_FILTER_SELL[b_idx]))
)
exec(src_est16.replace(target_est16, repl_est16, 1), ns_est16)
mod_est16.simulate_single_est_slot = ns_est16["simulate_single_est_slot"]

# 2. Patch mod_wdo_mix.simulate_decorrelated_wdo_family to also include entry_time, exit_time, entry_price, exit_price, stop_price, tp_price
src_wdo_mix = inspect.getsource(mod_wdo_mix.simulate_decorrelated_wdo_family)
src_wdo_mix = src_wdo_mix.replace(
    "        if sig == 0:\n            idx += 1\n            continue",
    "        if not _check_dash_filter(b1, sig):\n            sig = 0\n        if sig == 0:\n            idx += 1\n            continue",
    1,
)
target_wdo_mix = """        trades.append({
            "date": d_str,
            "slot_id": slot_id,
            "side": sig,
            "contracts": 1.0,
            "pnl_pts": float(pts),
            "pnl_brl": float(pts * 10.0),
        })"""
repl_wdo_mix = """        trades.append({
            "date": d_str,
            "slot_id": slot_id,
            "side": sig,
            "entry_time": f"{int(t_mins[fbar])//60:02d}:{int(t_mins[fbar])%60:02d}",
            "exit_time": f"{int(t_mins[min(k, n-1)])//60:02d}:{int(t_mins[min(k, n-1)])%60:02d}",
            "entry_price": float(epx),
            "exit_price": float(ex_px),
            "stop_price": float(round05(epx - sl_pts) if sig == 1 else round05(epx + sl_pts)),
            "tp_price": float(c_tp),
            "be_triggered": bool(bea),
            "contracts": 1.0,
            "pnl_pts": float(pts),
            "pnl_brl": float(pts * 10.0),
        })"""
assert target_wdo_mix in src_wdo_mix, "target_wdo_mix not found"
ns_wdo_mix = dict(mod_wdo_mix.__dict__)
ns_wdo_mix["_check_dash_filter"] = lambda b_idx, s_dir: (
    True if (emdf._ACTIVE_FILTER_BUY is None or s_dir == 0)
    else (bool(emdf._ACTIVE_FILTER_BUY[b_idx]) if s_dir == 1 else bool(emdf._ACTIVE_FILTER_SELL[b_idx]))
)
exec(src_wdo_mix.replace(target_wdo_mix, repl_wdo_mix, 1), ns_wdo_mix)
mod_wdo_mix.simulate_decorrelated_wdo_family = ns_wdo_mix["simulate_decorrelated_wdo_family"]

# 3. Patch sim_smart_grid in emdf
def sim_smart_grid_detailed(pb, gex_map, sig_arr, def_w_arr, cfg, is_wdo: bool, f_buy=None, f_sell=None):
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
        init_sl = rnd(p2 - sl2_pts) if sig == 1 else rnd(p2 + sl2_pts)
        c_sl = init_sl
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
        ex_rsn = "TEMPO"

        while k < n:
            if dates[k] != d_str or int(t_mins[k]) >= 1035:
                ex_px = opens[k] if dates[k] == d_str else closes[k - 1]
                ex_rsn = "EOD_1715"
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
                ex_rsn = "PROTEÇÃO BE" if bea else "STOP"
                break
            if (sig == 1 and highs[k] >= c_tp) or (sig == -1 and lows[k] <= c_tp):
                ex_px = c_tp
                ex_rsn = "ALVO PERNA 2 (3C)" if leg == 2 else "ALVO MIDWALL"
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
                    ex_rsn = "TEMPO"
                    k += 1
                    break
            k += 1

        pts_unit = (ex_px - avg_p) * sig - slip
        pts_tot = pts_unit * lots
        ex_k = min(n - 1, k)
        trades.append({
            "date": str(d_str),
            "side": sig,
            "contracts": float(lots),
            "leg_reached": leg,
            "entry_time": fmt_tmin(t_mins[fbar]),
            "exit_time": fmt_tmin(t_mins[ex_k]),
            "entry_price": float(avg_p),
            "exit_price": float(ex_px),
            "stop_price": float(init_sl),
            "tp_price": float(c_tp),
            "be_triggered": bool(bea),
            "exit_reason": ex_rsn,
            "pnl_pts": float(pts_tot),
            "pnl_brl": float(pts_tot * mult_brl),
            "pnl_1c_brl": float(pts_unit * mult_brl),
        })
        day_cnt[d_str] = day_cnt.get(d_str, 0) + 1
        idx = max(idx + 1, k + 1)

    return trades

emdf.sim_smart_grid = sim_smart_grid_detailed

dash_eq_path = os.path.join(ROOT_DIR, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
with open(dash_eq_path, "r", encoding="utf-8") as fp:
    old_dash_data = json.load(fp)

dash_win_map, dash_wdo_map = load_all_dashboard_features()
all_dates = sorted(dash_win_map.keys())
wdos2_by_date = {d: [] for d in all_dates}
for d_obj in old_dash_data.get("days", []):
    d_str = d_obj["date"]
    if d_str in wdos2_by_date:
        for t in d_obj.get("trades", []):
            if t.get("strategy_id") == "WDO_S2":
                t_copy = dict(t)
                t_copy["type"] = f"WDO_S2 · {t_copy.get('direction', 'COMPRA')}"
                wdos2_by_date[d_str].append(t_copy)

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

est01_filt = run_win_strategy(1, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, *win_filters["6_COMBO_SMART"])
est07_filt = run_win_strategy(7, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, *win_filters["3_FLUXO_INST"])
est13_filt = run_win_strategy(13, df_win, gex_win, pb_win, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s_w, *win_filters["4_FLUXO_ABSORCAO"])

wdo09_filt = run_wdo_strategy(9, df_wdo, gex_wdo, pb_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, *wdo_filters["1_JANELA_ASG"])
wdo11_filt = run_wdo_strategy(11, df_wdo, gex_wdo, pb_wdo, d_n50_c, d_n50_u, d_n50_l, d_n50_s, d_n30_c, d_n30_u, d_n30_l, d_n30_s, d_rsi7s, *wdo_filters["4_FLUXO_ABSORCAO"])

def format_mt5_trade(t, sid, asset):
    d_str = str(t["date"])
    side = int(t["side"])
    dir_lbl = "COMPRA" if side == 1 else "VENDA"
    pts = round(float(t["pnl_pts"]), 1 if asset == "WDO" else 0)
    brl = round(float(t["pnl_brl"]), 2)
    lots = int(round(float(t.get("contracts", 1.0))))
    leg_tag = f" ({lots}C Grid)" if lots > 1 else ""
    if pts > 0:
        if "exit_reason" in t and "PERNA 2" in t["exit_reason"]:
            lbl = f"✅ ALVO GRID 1+2C (+{pts:.0f}p)" if asset == "WIN" else f"✅ ALVO GRID 1+2C (+{pts:.1f}p)"
        elif (asset == "WIN" and pts >= 180) or (asset == "WDO" and pts >= 7.0):
            lbl = f"✅ ALVO WALL (+{pts:.0f} pts)" if asset == "WIN" else f"✅ ALVO WALL (+{pts:.1f} pts)"
        else:
            lbl = f"✅ PROTEÇÃO BE / TEMPO (+{pts:.0f} pts)" if asset == "WIN" else f"✅ PROTEÇÃO BE / TEMPO (+{pts:.1f} pts)"
    else:
        if t.get("be_triggered"):
            lbl = f"❌ ESCUDO WALL ({pts:.0f} pts)" if asset == "WIN" else f"❌ ESCUDO WALL ({pts:.1f} pts)"
        else:
            lbl = f"❌ STOP ({pts:.0f} pts{leg_tag})" if asset == "WIN" else f"❌ STOP ({pts:.1f} pts{leg_tag})"

    return {
        "date": d_str,
        "month": d_str[:7],
        "time": t.get("entry_time", "10:00"),
        "exit_time": t.get("exit_time", "11:00"),
        "asset": asset,
        "strategy_id": sid,
        "direction": dir_lbl,
        "type": f"{sid} · {dir_lbl}",
        "entry_price": round(float(t.get("entry_price", 0.0)), 1 if asset == "WDO" else 0),
        "exit_price": round(float(t.get("exit_price", 0.0)), 1 if asset == "WDO" else 0),
        "stop_price": round(float(t.get("stop_price", 0.0)), 1 if asset == "WDO" else 0),
        "tp_price": round(float(t.get("tp_price", 0.0)), 1 if asset == "WDO" else 0),
        "pts": pts,
        "brl_1c": brl,
        "label": lbl,
        "status": "FECHADA",
    }

STRAT_IDS = ["EST_01", "EST_07", "EST_13", "WDO_09", "WDO_11", "WDO_S2"]
by_date_strats = {d: {s: [] for s in STRAT_IDS} for d in all_dates}

for t in est01_filt:
    if str(t["date"]) in by_date_strats:
        by_date_strats[str(t["date"])]["EST_01"].append(format_mt5_trade(t, "EST_01", "WIN"))
for t in est07_filt:
    if str(t["date"]) in by_date_strats:
        by_date_strats[str(t["date"])]["EST_07"].append(format_mt5_trade(t, "EST_07", "WIN"))
for t in est13_filt:
    if str(t["date"]) in by_date_strats:
        by_date_strats[str(t["date"])]["EST_13"].append(format_mt5_trade(t, "EST_13", "WIN"))
for t in wdo09_filt:
    if str(t["date"]) in by_date_strats:
        by_date_strats[str(t["date"])]["WDO_09"].append(format_mt5_trade(t, "WDO_09", "WDO"))
for t in wdo11_filt:
    if str(t["date"]) in by_date_strats:
        by_date_strats[str(t["date"])]["WDO_11"].append(format_mt5_trade(t, "WDO_11", "WDO"))
for d_str, t_list in wdos2_by_date.items():
    if d_str in by_date_strats:
        by_date_strats[d_str]["WDO_S2"].extend(t_list)

days_out = []
for d_str in all_dates:
    day_trades = []
    rec = {
        "date": d_str,
        "month": d_str[:7],
        "is_live": False,
    }
    for sid in STRAT_IDS:
        t_list = by_date_strats[d_str][sid]
        rec[f"{sid}_pts"] = round(sum(float(x["pts"]) for x in t_list), 2)
        rec[f"{sid}_ops"] = len(t_list)
        day_trades.extend(t_list)
    day_trades.sort(key=lambda x: (x.get("time", ""), x.get("strategy_id", "")))
    rec["trades"] = day_trades
    days_out.append(rec)

def build_summary_entry(trades_list, all_dates_list):
    ops = len(trades_list)
    wins = sum(1 for x in trades_list if float(x["brl_1c"]) > 0)
    g_win = round(sum(float(x["brl_1c"]) for x in trades_list if float(x["brl_1c"]) > 0), 2)
    g_loss = round(sum(abs(float(x["brl_1c"])) for x in trades_list if float(x["brl_1c"]) < 0), 2)
    tot_pts = round(sum(float(x["pts"]) for x in trades_list), 2)
    tot_brl = round(sum(float(x["brl_1c"]) for x in trades_list), 2)
    wr_pct = round((wins / ops) * 100.0, 1) if ops > 0 else 0.0
    pf = round(g_win / g_loss, 2) if g_loss > 0 else 99.9

    daily_map = {d: 0.0 for d in all_dates_list}
    by_m = {}
    for d in all_dates_list:
        by_m[d[:7]] = 0.0
    for x in trades_list:
        daily_map[x["date"]] = daily_map.get(x["date"], 0.0) + float(x["brl_1c"])
        by_m[x["month"]] = round(by_m.get(x["month"], 0.0) + float(x["brl_1c"]), 2)

    eq = np.cumsum([daily_map[d] for d in all_dates_list])
    pk = np.maximum.accumulate(np.maximum(0.0, eq))
    mdd = round(float(np.max(pk - eq)), 2) if len(eq) > 0 else 0.0
    ret_dd = round(tot_brl / mdd, 2) if mdd > 0 else 99.9
    pos_m = sum(1 for v in by_m.values() if v > 0)
    return {
        "ops": ops,
        "wins": wins,
        "wr_pct": wr_pct,
        "pf": pf,
        "gross_win_1c": g_win,
        "gross_loss_1c": g_loss,
        "tot_pts": tot_pts,
        "tot_brl_1c": tot_brl,
        "max_dd_brl_1c": mdd,
        "ret_dd": ret_dd,
        "pos_months": pos_m,
        "total_months": len(by_m),
        "by_month_1c": by_m,
    }

all_by_sid = {sid: [] for sid in STRAT_IDS}
for d_rec in days_out:
    for tr in d_rec["trades"]:
        all_by_sid[tr["strategy_id"]].append(tr)

summary_1c = {}
for sid in STRAT_IDS:
    summary_1c[sid] = build_summary_entry(all_by_sid[sid], all_dates)

win_all = all_by_sid["EST_01"] + all_by_sid["EST_07"] + all_by_sid["EST_13"]
wdo_all = all_by_sid["WDO_09"] + all_by_sid["WDO_11"] + all_by_sid["WDO_S2"]
port_all = win_all + wdo_all

summary_1c["WIN_TOTAL"] = build_summary_entry(win_all, all_dates)
summary_1c["WDO_TOTAL"] = build_summary_entry(wdo_all, all_dates)
summary_1c["PORTFOLIO_1_1"] = build_summary_entry(port_all, all_dates)

# Also compute 2 WIN : 1 WDO portfolio summary
port_2_1 = [dict(x, brl_1c=float(x["brl_1c"]) * 2.0) for x in win_all] + wdo_all
summary_1c["PORTFOLIO_2_1"] = build_summary_entry(port_2_1, all_dates)

out_payload = {
    "version": "3.0_6_STRATEGIES_FLOW",
    "start_date": all_dates[0],
    "last_bt_date": all_dates[-1],
    "total_bt_sessions": len(all_dates),
    "summary_1c": summary_1c,
    "days": days_out,
}

with open(dash_eq_path, "w", encoding="utf-8") as fp:
    json.dump(out_payload, fp, ensure_ascii=False)

print("=== SALVO portfolio_4_sistematicas_equity_v1.json COM AS 6 ESTRATEGIAS C/ FLUXO ===")
for k, v in summary_1c.items():
    print(f"  {k:<15} | Tr={v['ops']:4d} | WR={v['wr_pct']:5.1f}% | PF={v['pf']:4.2f} | Net=R${v['tot_brl_1c']:8.0f} | MDD=R${v['max_dd_brl_1c']:5.0f} | Ret/DD={v['ret_dd']:5.2f} | Meses={v['pos_months']}/{v['total_months']}")
