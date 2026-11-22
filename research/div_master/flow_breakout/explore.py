"""Exploração sistemática M1 (bt.sim): Seguidoras de Fluxo (A) e Rompimento de Wall/Gamma (B) em WIN e WDO."""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import bt, modulo as M


def build_cache(asset):
    DS = bt.market(asset)
    raw = {d: v for d, v in load_asset(asset, "M5").items() if d <= bt.END and d in DS}
    cache = {}
    for d in sorted(raw):
        bars, walls, _ = raw[d]
        fb = M.compute_flow(bars, asset)
        lv_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
        lv_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        gflip = [float(w["price"]) for w in walls if w.get("type") == "GammaFlip"]
        ming = [float(w["price"]) for w in walls if w.get("type") == "MinGamma"]
        maxg = [float(w["price"]) for w in walls if w.get("type") == "MaxGamma"]
        atr = M.atr_series(fb, bt.X[asset]["tick"])
        cache[d] = dict(fb=fb, walls=walls, lv_wall=lv_wall, lv_all=lv_all,
                        gflip=gflip, ming=ming, maxg=maxg, atr=atr, D=DS[d])
    return DS, cache


def extract_features(asset, cache):
    """Para cada barra profit i -> entrada na barra MT5 e = pos[tm(i+1)], calcula features 100% causais até barra i."""
    X = bt.X[asset]
    tick = X["tick"]
    lo_w, hi_w = bt.WINDOW[asset]
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
        retd = np.array([float(b.get("ret_delta_bar", 0.0)) for b in fb])
        tot_v = bv + sv

        # Medianas causais expansivas de |aggr| e |pasv| e range para normalização sem lookahead
        abs_aggr = np.abs(aggr)
        abs_pasv = np.abs(pasv)
        rng = np.maximum(h - l, tick)

        for i in range(4, n - 1):
            tm_in = bt.hm(fb[i + 1]["time"])
            if not (lo_w <= tm_in <= hi_w) or tm_in not in D["pos"]:
                continue
            e = D["pos"][tm_in]
            if e < 2:
                continue
            ep = float(D["o5"][e])

            # Médias causais até barra i
            med_aggr = float(np.median(abs_aggr[: i + 1])) or 1.0
            med_pasv = float(np.median(abs_pasv[: i + 1])) or 1.0
            med_v = float(np.median(tot_v[: i + 1])) or 1.0
            atr_i = float(atr[i])

            half50 = max(float(D["u50"][e] - D["c50"][e]), tick)
            half30 = max(0.5 * float(D["u30"][e] - D["l30"][e]), tick)
            slope50 = float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            slope30 = (0.5 * (D["u30"][e] + D["l30"][e]) - 0.5 * (D["u30"][max(0, e - 4)] + D["l30"][max(0, e - 4)])) / half30
            ext50 = float(D["c5"][e - 1] - D["c50"][e]) / half50
            ext30 = float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / half30

            # Direção candidata baseada em múltiplos gatilhos (testamos BUY e SELL separadamente!)
            body = c[i] - o[i]
            close_pos = (c[i] - l[i]) / rng[i]  # 0..1

            # Cruzamento de Wall / MidWall nesta barra
            cross_w_up = any(c[i - 1] <= w < c[i] for w in lv_wall)
            cross_w_dn = any(c[i - 1] >= w > c[i] for w in lv_wall)
            cross_a_up = any(c[i - 1] <= w < c[i] for w in lv_all)
            cross_a_dn = any(c[i - 1] >= w > c[i] for w in lv_all)
            cross_gf_up = (not np.isnan(gf)) and (c[i - 1] <= gf < c[i])
            cross_gf_dn = (not np.isnan(gf)) and (c[i - 1] >= gf > c[i])
            below_gf = (not np.isnan(gf)) and (c[i] < gf)
            above_gf = (not np.isnan(gf)) and (c[i] > gf)

            # Cruzamento de abertura (ORB 15min / 30min)
            hi30 = np.max(h[:6]) if i >= 6 else np.nan
            lo30 = np.min(l[:6]) if i >= 6 else np.nan
            orb30_up = (i >= 6) and (c[i - 1] <= hi30 < c[i])
            orb30_dn = (i >= 6) and (c[i - 1] >= lo30 > c[i])

            # Fluxo acumulado 3 barras e 6 barras
            ag3 = float(np.sum(aggr[i - 2 : i + 1]))
            ps3 = float(np.sum(pasv[i - 2 : i + 1]))
            dw = wv[i] - wv[i - 1]
            wv_max_day = float(np.max(wv[: i + 1]))
            wv_min_day = float(np.min(wv[: i + 1]))

            # Pullback até centro NWE30 após tendência
            c30_e = 0.5 * float(D["u30"][e] + D["l30"][e])
            pb_up = (slope50 > 0.15) and (l[i] <= c30_e or l[i - 1] <= c30_e) and (c[i] > c30_e) and (body > 0)
            pb_dn = (slope50 < -0.15) and (h[i] >= c30_e or h[i - 1] >= c30_e) and (c[i] < c30_e) and (body < 0)

            for dr in (1, -1):
                ag_n = dr * aggr[i] / med_aggr
                ps_n = dr * pasv[i] / med_pasv
                ag3_n = dr * ag3 / med_aggr
                ps3_n = dr * ps3 / med_pasv
                lot_adv = (abl[i] > asl[i]) if dr == 1 else (asl[i] > abl[i])
                bar_str = dr * body / rng[i]
                close_ext = close_pos if dr == 1 else (1.0 - close_pos)
                cross_w = cross_w_up if dr == 1 else cross_w_dn
                cross_a = cross_a_up if dr == 1 else cross_a_dn
                cross_gf = cross_gf_up if dr == 1 else cross_gf_dn
                orb30 = orb30_up if dr == 1 else orb30_dn
                pb = pb_up if dr == 1 else pb_dn
                nw = bt.next_level(lv_all, ep, dr, (50.0 if asset == "WIN" else 2.0) + X["front"])
                nw_d = dr * (nw - ep) - X["front"] if nw is not None else np.nan
                sl50 = dr * slope50
                sl30 = dr * slope30
                ex50 = dr * ext50
                ex30 = dr * ext30
                wv_ext_day = (wv[i] >= wv_max_day) if dr == 1 else (wv[i] <= wv_min_day)
                vol_r = tot_v[i] / med_v
                retd_f = dr * retd[i]

                recs.append(dict(
                    date=d, i=i, e=e, ep=ep, dir=dr, tm=tm_in, hh=tm_in // 60,
                    ag_n=ag_n, ps_n=ps_n, ag3_n=ag3_n, ps3_n=ps3_n, lot_adv=lot_adv,
                    bar_str=bar_str, close_ext=close_ext, rng_atr=rng[i] / atr_i,
                    vol_r=vol_r, retd_f=retd_f, dw_f=dr * dw, wv_f=dr * wv[i], wv_ext_day=wv_ext_day,
                    sl50=sl50, sl30=sl30, ex50=ex50, ex30=ex30,
                    cross_w=cross_w, cross_a=cross_a, cross_gf=cross_gf,
                    below_gf=below_gf, above_gf=above_gf, orb30=orb30, pb=pb, nw_d=nw_d,
                ))
    return pd.DataFrame(recs).sort_values(["date", "tm", "i", "dir"]).reset_index(drop=True)


def run_asset_study(asset):
    t0 = time.time()
    DS, cache = build_cache(asset)
    df = extract_features(asset, cache)
    X = bt.X[asset]
    print(f"\n{'#'*90}\nATIVO: {asset} | linhas={len(df)} | prep={time.time()-t0:.1f}s\n{'#'*90}")

    # Definição de famílias de sinais (seguidoras de fluxo + rompimentos)
    if asset == "WIN":
        exits = [
            ("SL200_TP250_t12", 200.0, "fix", 250.0, 0.0, 0.0, 12),
            ("SL200_TP300_t18", 200.0, "fix", 300.0, 0.0, 0.0, 18),
            ("SL250_TP250_t18", 250.0, "fix", 250.0, 0.0, 0.0, 18),
            ("SL250_TP400_t24", 250.0, "fix", 400.0, 180.0, 20.0, 24),
            ("SL200_T12_BE", 200.0, "none", 0.0, 180.0, 20.0, 12),
            ("SL250_NW_t18", 250.0, "nw", 0.0, 0.0, 0.0, 18),
        ]
        nw_lo, nw_hi, nw_min = 120.0, 600.0, 80.0
    else:
        exits = [
            ("SL8_TP10_t12", 8.0, "fix", 10.0, 0.0, 0.0, 12),
            ("SL10_TP12_t18", 10.0, "fix", 12.0, 0.0, 0.0, 18),
            ("SL10_TP15_t24", 10.0, "fix", 15.0, 0.0, 0.0, 24),
            ("SL12_TP18_t24", 12.0, "fix", 18.0, 6.0, 1.0, 24),
            ("SL10_T12_BE", 10.0, "none", 0.0, 6.0, 1.0, 12),
            ("SL10_NW_t18", 10.0, "nw", 0.0, 0.0, 0.0, 18),
        ]
        nw_lo, nw_hi, nw_min = 4.0, 25.0, 3.0

    # Famílias de sinais (100% sem divergência!)
    fams = {
        # A. Seguidoras de Fluxo
        "A1_surge_ag2_sl": (df["ag_n"] >= 2.0) & (df["close_ext"] >= 0.70) & (df["sl50"] > 0.1) & (df["ex50"] < 1.2) & (df["dw_f"] > 0),
        "A1_surge_ag2_lot": (df["ag_n"] >= 2.0) & (df["ps_n"] > 0) & df["lot_adv"] & (df["close_ext"] >= 0.70) & (df["sl50"] > 0.0),
        "A1_surge_ag3_wmax": (df["ag_n"] >= 1.5) & (df["ag3_n"] >= 3.0) & df["wv_ext_day"] & (df["close_ext"] >= 0.65) & (df["ex50"] < 1.3),
        "A1_ag_pas_vol": (df["ag_n"] >= 1.5) & (df["ps_n"] >= 1.0) & (df["vol_r"] >= 1.3) & (df["bar_str"] >= 0.45) & (df["sl50"] > 0.0),
        "A2_pullback_flow": df["pb"] & (df["ag_n"] >= 0.8) & (df["dw_f"] > 0),
        "A2_pullback_ag3": df["pb"] & (df["ag3_n"] > 1.0) & (df["ps_n"] > 0),
        "A3_orb30_flow": df["orb30"] & (df["ag_n"] >= 1.0) & (df["close_ext"] >= 0.65),
        "A3_orb30_ag_ps": df["orb30"] & (df["ag_n"] >= 1.0) & (df["ps_n"] > 0) & df["lot_adv"],
        # B. Rompimento de Wall / GammaFlip
        "B1_wbreak_pure": df["cross_w"] & (df["close_ext"] >= 0.65),
        "B1_wbreak_ag": df["cross_w"] & (df["ag_n"] >= 1.0) & (df["close_ext"] >= 0.65) & (df["dw_f"] > 0),
        "B1_wbreak_ag_ps": df["cross_w"] & (df["ag_n"] >= 1.0) & (df["ps_n"] > 0) & (df["close_ext"] >= 0.65),
        "B1_abreak_ag_sl": df["cross_a"] & (df["ag_n"] >= 1.2) & (df["sl50"] > 0.0) & (df["close_ext"] >= 0.65),
        "B2_wbreak_neg_gam": df["cross_w"] & df["below_gf"] & (df["ag_n"] >= 0.8) & (df["close_ext"] >= 0.60),
        "B2_gflip_break_flow": df["cross_gf"] & (df["ag_n"] >= 0.5) & (df["close_ext"] >= 0.60),
        "B2_abreak_neg_gam": df["cross_a"] & df["below_gf"] & (df["ag_n"] >= 1.0) & (df["close_ext"] >= 0.65),
        "B4_wbreak_free": df["cross_w"] & (df["ag_n"] >= 1.0) & (df["nw_d"] >= nw_lo * 1.5) & (df["close_ext"] >= 0.60),
    }

    time_slices = {
        "ALL": np.ones(len(df), dtype=bool),
        "09_12": (df["tm"] <= 720).values,
        "10_16": ((df["tm"] >= 600) & (df["tm"] < 960)).values,
    }

    # União de todos os sinais que pertencem a qualquer família para simular apenas ~1x por saída
    any_m = np.zeros(len(df), dtype=bool)
    for m in fams.values():
        any_m |= m.values
    cand_idx = np.where(any_m)[0]
    sub_all = df.iloc[cand_idx].reset_index(drop=True)
    idx_map = np.full(len(df), -1, dtype=np.int64)
    idx_map[cand_idx] = np.arange(len(cand_idx))
    print(f"Candidatos únicos em alguma família: {len(sub_all)}")

    # Pré-simula as saídas sobre sub_all
    presim = {}
    for ex_name, sl, tk, tv, bt_t, bt_l, tmax in exits:
        pnls = np.full(len(sub_all), np.nan)
        xts = np.zeros(len(sub_all), dtype=np.int64)
        for k_i, r in enumerate(sub_all.itertuples()):
            D = DS[r.date]
            if tk == "fix":
                tp_px = r.ep + r.dir * tv
            elif tk == "none":
                tp_px = r.ep + r.dir * 999999.0
            else:
                if np.isnan(r.nw_d) or r.nw_d < nw_min:
                    continue
                tp_px = r.ep + r.dir * min(max(r.nw_d, nw_lo), nw_hi)
            p, xt = bt.sim(*bt._args(D), D["u30"], r.e, r.ep, r.dir, sl, tp_px, False,
                           0.0, 0.0, 0.0, bt_t, bt_l, tmax, X["tick"])
            pnls[k_i] = (p - X["cost"]) * X["brl"]
            xts[k_i] = xt
        presim[ex_name] = (pnls, xts)

    results = []
    for f_name, fm in fams.items():
        for t_name, tm_m in time_slices.items():
            mask = fm.values & tm_m
            sel_sub = idx_map[mask]
            sel_sub = sel_sub[sel_sub >= 0]
            if len(sel_sub) < 60:
                continue
            for ex_name, *_ in exits:
                p_arr, x_arr = presim[ex_name]
                pv = p_arr[sel_sub]
                ok = ~np.isnan(pv)
                if ok.sum() < 60:
                    continue
                df_t = sub_all.iloc[sel_sub[ok]][["date", "tm"]].copy()
                df_t["pnl"] = pv[ok]
                df_t["xt"] = x_arr[sel_sub[ok]]
                df_t = bt.mgmt(df_t, "pnl", "xt", "UM")
                if len(df_t) < 60:
                    continue
                st = bt.stats(df_t, "pnl", "xt")
                results.append(dict(fam=f_name, time=t_name, exit=ex_name, **st))

    res = pd.DataFrame(results).sort_values(["rdd", "pf"], ascending=[False, False]).reset_index(drop=True)
    if res.empty:
        print("Nenhum resultado >= 60 ops.")
        return res
    print(f"Total combinações (>=60 ops): {len(res)} | >=100 ops & rdd>=2.0 & 3 subper>0: "
          f"{len(res[(res['ops']>=100)&(res['rdd']>=2.0)&(res['h1']>0)&(res['h2']>0)&(res['oos']>0)])}")
    print("\n--- Melhor de cada família (>=60 ops) ---")
    best_fam = res.sort_values("rdd", ascending=False).groupby("fam", as_index=False).first().sort_values("rdd", ascending=False)
    print(best_fam.to_string(index=False))

    pos_all = res[(res["ops"] >= 100) & (res["h1"] > 0) & (res["h2"] > 0) & (res["oos"] > 0)]
    print(f"\n--- Top 20 (>=100 ops, H1>0, H2>0, OOS>0) [{len(pos_all)} hits] ---")
    if not pos_all.empty:
        print(pos_all.head(20).to_string(index=False))
    return res


if __name__ == "__main__":
    for asset in ("WIN", "WDO"):
        res = run_asset_study(asset)
        res.to_pickle(Path(__file__).with_name(f"explore_{asset.lower()}.pkl"))
