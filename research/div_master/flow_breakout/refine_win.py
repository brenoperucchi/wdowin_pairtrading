"""Refinamento M1 (bt.sim) no WIN: Rompimento de Wall pura (B1) e Seguidora de Fluxo Institucional (A1)."""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.flow_breakout.explore import build_cache
from research.div_master.win_especialista.audit_e22_win import get_e22_signals, eval_e22, sim_win_exact


def extract_win_rich(cache):
    X = bt.X["WIN"]
    tick = X["tick"]
    lo_w, hi_w = bt.WINDOW["WIN"]
    recs = []
    for d, day in cache.items():
        fb, D, atr = day["fb"], day["D"], day["atr"]
        lv_wall, lv_all = day["lv_wall"], day["lv_all"]
        gf = np.mean(day["gflip"]) if day["gflip"] else np.nan
        mg = np.mean(day["maxg"]) if day["maxg"] else np.nan
        n = len(fb)
        if n < 10:
            continue

        o = np.array([float(b["open"]) for b in fb])
        h = np.array([float(b["high"]) for b in fb])
        l = np.array([float(b["low"]) for b in fb])
        c = np.array([float(b["close"]) for b in fb])
        wv = np.array([float(b["wave"]) for b in fb])
        aggr = np.array([float(b.get("inst_aggr_delta", 0.0)) for b in fb])
        pasv = np.array([float(b.get("inst_pass_delta", 0.0)) for b in fb])
        bv = np.array([float(b.get("buy_vol", 0.0)) for b in fb])
        sv = np.array([float(b.get("sell_vol", 0.0)) for b in fb])
        abl = np.array([float(b.get("avg_buy_lot", 0.0)) for b in fb])
        asl = np.array([float(b.get("avg_sell_lot", 0.0)) for b in fb])
        tot_v = bv + sv
        abs_aggr = np.abs(aggr)
        abs_pasv = np.abs(pasv)
        rng = np.maximum(h - l, tick)

        seen_wall_dir = set()
        for i in range(4, n - 1):
            tm_in = bt.hm(fb[i + 1]["time"])
            if not (lo_w <= tm_in <= hi_w) or tm_in not in D["pos"]:
                continue
            e = D["pos"][tm_in]
            if e < 2:
                continue
            ep = float(D["o5"][e])

            med_aggr = float(np.median(abs_aggr[: i + 1])) or 1.0
            med_pasv = float(np.median(abs_pasv[: i + 1])) or 1.0
            med_v = float(np.median(tot_v[: i + 1])) or 1.0
            atr_i = float(atr[i])

            half50 = max(float(D["u50"][e] - D["c50"][e]), tick)
            half30 = max(0.5 * float(D["u30"][e] - D["l30"][e]), tick)
            slope50 = float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            ext50 = float(D["c5"][e - 1] - D["c50"][e]) / half50
            ext30 = float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / half30

            close_pos = (c[i] - l[i]) / rng[i]
            body = c[i] - o[i]

            for dr in (1, -1):
                # Rompimento de Wall pura (com tolerância de origem na barra anterior)
                w_crossed = [w for w in lv_wall if (c[i - 1] <= w < c[i] if dr == 1 else c[i - 1] >= w > c[i])]
                cross_w = len(w_crossed) > 0
                first_w = False
                dist_w = 0.0
                if cross_w:
                    w0 = w_crossed[-1] if dr == 1 else w_crossed[0]
                    dist_w = dr * (c[i] - w0)
                    if (w0, dr) not in seen_wall_dir:
                        first_w = True
                        seen_wall_dir.add((w0, dr))

                nw = bt.next_level(lv_wall, ep, dr, 50.0 + X["front"])
                nw_d = dr * (nw - ep) - X["front"] if nw is not None else np.nan
                nwa = bt.next_level(lv_all, ep, dr, 50.0 + X["front"])
                nwa_d = dr * (nwa - ep) - X["front"] if nwa is not None else np.nan

                ag_n = dr * aggr[i] / med_aggr
                ps_n = dr * pasv[i] / med_pasv
                ag2_n = dr * (aggr[i] + aggr[i - 1]) / med_aggr
                ps2_n = dr * (pasv[i] + pasv[i - 1]) / med_pasv
                ag3_n = dr * float(np.sum(aggr[i - 2 : i + 1])) / med_aggr
                lot_adv = (abl[i] > asl[i]) if dr == 1 else (asl[i] > abl[i])
                close_ext = close_pos if dr == 1 else (1.0 - close_pos)
                bar_str = dr * body / rng[i]
                vol_r = tot_v[i] / med_v
                dw_f = dr * (wv[i] - wv[i - 1])

                recs.append(dict(
                    date=d, i=i, e=e, ep=ep, dir=dr, tm=tm_in, hh=tm_in // 60,
                    cross_w=cross_w, first_w=first_w, dist_w=dist_w,
                    nw_d=nw_d, nwa_d=nwa_d,
                    ag_n=ag_n, ps_n=ps_n, ag2_n=ag2_n, ps2_n=ps2_n, ag3_n=ag3_n,
                    lot_adv=lot_adv, close_ext=close_ext, bar_str=bar_str,
                    rng_atr=rng[i] / atr_i, vol_r=vol_r, dw_f=dw_f,
                    sl50=dr * slope50, ex50=dr * ext50, ex30=dr * ext30,
                    neg_gam=(not np.isnan(gf)) and ((c[i] < gf) if dr == -1 else (c[i] < gf)),
                    away_mg=(not np.isnan(mg)) and (abs(c[i] - mg) >= 150.0),
                ))
    return pd.DataFrame(recs).sort_values(["date", "tm", "i", "dir"]).reset_index(drop=True)


def run_grid(df, DS, s_e22, all_dates, masks, time_masks, exits, tag):
    X = bt.X["WIN"]
    any_m = np.zeros(len(df), dtype=bool)
    for m in masks.values():
        any_m |= m
    cand_idx = np.where(any_m)[0]
    sub_all = df.iloc[cand_idx].reset_index(drop=True)
    idx_map = np.full(len(df), -1, dtype=np.int64)
    idx_map[cand_idx] = np.arange(len(cand_idx))

    presim = {}
    for ex_name, sl, tp, be_t, be_l, tmax in exits:
        pnls = np.empty(len(sub_all))
        xts = np.empty(len(sub_all), dtype=np.int64)
        for k_i, r in enumerate(sub_all.itertuples()):
            D = DS[r.date]
            p, xt = bt.sim(*bt._args(D), D["u30"], r.e, r.ep, r.dir, sl, r.ep + r.dir * tp, False,
                           0.0, 0.0, 0.0, be_t, be_l, tmax, X["tick"])
            pnls[k_i] = (p - X["cost"]) * X["brl"]
            xts[k_i] = xt
        presim[ex_name] = (pnls, xts)

    rows = []
    for m_name, m_arr in masks.items():
        for t_name, t_arr in time_masks.items():
            sel = idx_map[m_arr & t_arr]
            sel = sel[sel >= 0]
            if len(sel) < 100:
                continue
            base_df = sub_all.iloc[sel][["date", "tm"]].copy()
            for ex_name, *_ in exits:
                p_arr, x_arr = presim[ex_name]
                df_t = base_df.copy()
                df_t["pnl"] = p_arr[sel]
                df_t["xt"] = x_arr[sel]
                df_t = bt.mgmt(df_t, "pnl", "xt", "UM")
                if len(df_t) < 100:
                    continue
                st = bt.stats(df_t, "pnl", "xt")
                if st["rdd"] >= 3.5 and st["h1"] > 0 and st["h2"] > 0 and st["oos"] > 0:
                    s_c = df_t.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)
                    rows.append(dict(tag=tag, rule=m_name, time=t_name, exit=ex_name, corr=round(float(s_c.corr(s_e22)), 3), **st))
    return pd.DataFrame(rows).sort_values(["rdd", "pf"], ascending=[False, False]).reset_index(drop=True) if rows else pd.DataFrame()


if __name__ == "__main__":
    t0 = time.time()
    DS, cache = build_cache("WIN")
    df = extract_win_rich(cache)
    _, df_e22 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=1.0)
    all_dates = pd.Index(sorted(cache.keys()))
    s_e22 = df_e22.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)

    exits = [
        ("SL200_TP250_t12", 200.0, 250.0, 0.0, 0.0, 12),
        ("SL200_TP300_t18", 200.0, 300.0, 0.0, 0.0, 18),
        ("SL200_TP300_BE180_t18", 200.0, 300.0, 180.0, 20.0, 18),
        ("SL220_TP250_t18", 220.0, 250.0, 0.0, 0.0, 18),
        ("SL250_TP250_t18", 250.0, 250.0, 0.0, 0.0, 18),
        ("SL250_TP300_t24", 250.0, 300.0, 0.0, 0.0, 24),
        ("SL250_TP300_BE180_t24", 250.0, 300.0, 180.0, 20.0, 24),
        ("SL280_TP280_t24", 280.0, 280.0, 0.0, 0.0, 24),
        ("SL300_TP250_t18", 300.0, 250.0, 0.0, 0.0, 18),
    ]
    time_masks = {
        "ALL": np.ones(len(df), dtype=bool),
        "09_12": (df["tm"] <= 720).values,
        "09_15": (df["tm"] <= 900).values,
        "10_16": ((df["tm"] >= 600) & (df["tm"] < 960)).values,
    }

    # --- Frente B1: Rompimento de Wall pura ---
    cw = df["cross_w"].values
    fw = df["first_w"].values
    b1_masks = {
        "B_pure_ce65": cw & (df["close_ext"] >= 0.65).values,
        "B_1st_ce65": fw & (df["close_ext"] >= 0.65).values,
        "B_ce65_ag05": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 0.5).values,
        "B_ce65_ag10": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values,
        "B_ce65_ag10_dw": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values,
        "B_ce65_ag15_dw": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.5).values & (df["dw_f"] > 0).values,
        "B_ce70_ag10_dw": cw & (df["close_ext"] >= 0.70).values & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values,
        "B_1st_ce65_ag10_dw": fw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["dw_f"] > 0).values,
        "B_ce65_ag10_ex12": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["ex50"] < 1.2).values,
        "B_ce65_ag10_sl0": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["sl50"] > 0.0).values,
        "B_ce65_ag10_lot": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & df["lot_adv"].values,
        "B_ce65_ag10_ps0": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["ps_n"] > 0).values,
        "B_ce65_ag10_nw200": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["nw_d"] >= 200.0).values,
        "B_ce65_ag10_nwa200": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["nwa_d"] >= 200.0).values,
        "B_ce65_ag10_dist30": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & (df["dist_w"] >= 30.0).values,
        "B_ce65_ag2_ps0": cw & (df["close_ext"] >= 0.65).values & (df["ag2_n"] >= 1.5).values & (df["ps_n"] > 0).values,
        "B_ce65_ag10_ng": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & df["neg_gam"].values,
        "B_ce65_ag10_nomg": cw & (df["close_ext"] >= 0.65).values & (df["ag_n"] >= 1.0).values & df["away_mg"].values,
    }
    res_b = run_grid(df, DS, s_e22, all_dates, b1_masks, time_masks, exits, "BREAK_WALL")

    # --- Frente A1: Seguidora de Fluxo Institucional (sem precisar cruzar Wall) ---
    a1_masks = {
        "A_ag15_ps05_sl0_ce65": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 0.5).values & (df["sl50"] > 0.0).values & (df["close_ext"] >= 0.65).values,
        "A_ag15_ps10_vol12_sl0": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 1.0).values & (df["vol_r"] >= 1.2).values & (df["sl50"] > 0.0).values & (df["bar_str"] >= 0.4).values,
        "A_ag15_ps05_vol12_ce65": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 0.5).values & (df["vol_r"] >= 1.2).values & (df["close_ext"] >= 0.65).values & (df["sl50"] > 0.0).values,
        "A_ag20_ps05_ce65": (df["ag_n"] >= 2.0).values & (df["ps_n"] >= 0.5).values & (df["close_ext"] >= 0.65).values & (df["sl50"] > 0.0).values,
        "A_ag20_ps05_lot_ce65": (df["ag_n"] >= 2.0).values & (df["ps_n"] >= 0.5).values & df["lot_adv"].values & (df["close_ext"] >= 0.65).values,
        "A_ag15_ps05_ex10_sl0": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 0.5).values & (df["ex50"] < 1.0).values & (df["sl50"] > 0.0).values & (df["close_ext"] >= 0.65).values,
        "A_ag2_ps2_sl0_ce65": (df["ag2_n"] >= 2.5).values & (df["ps2_n"] >= 1.0).values & (df["sl50"] > 0.0).values & (df["close_ext"] >= 0.65).values,
        "A_ag3_dw_sl0_ce65": (df["ag3_n"] >= 3.5).values & (df["dw_f"] > 0).values & (df["sl50"] > 0.0).values & (df["close_ext"] >= 0.65).values,
        "A_ag15_ps05_nw250": (df["ag_n"] >= 1.5).values & (df["ps_n"] >= 0.5).values & (df["nw_d"] >= 250.0).values & (df["close_ext"] >= 0.65).values,
    }
    res_a = run_grid(df, DS, s_e22, all_dates, a1_masks, time_masks, exits, "FLOW_FOLLOW")

    print(f"Concluído em {time.time()-t0:.1f}s")
    print(f"\n=== ROMPIMENTO DE WALL WIN (hits >= 3.5): {len(res_b)} ===")
    if not res_b.empty:
        print(res_b.head(25).to_string(index=False))
    print(f"\n=== SEGUIDORA DE FLUXO WIN (hits >= 3.5): {len(res_a)} ===")
    if not res_a.empty:
        print(res_a.head(25).to_string(index=False))
    pd.concat([res_b, res_a], ignore_index=True).to_pickle(Path(__file__).with_name("refine_win_hits.pkl"))
