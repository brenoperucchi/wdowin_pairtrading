"""Teste de validação cruzada (mesmos filtros exatos em WIN e WDO) para Divergência v3.2 e Rompimento de Wall."""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import win_cache, DS_WIN, XW
from research.div_master.wdo_especialista.robustez_final import days_cache as wdo_cache, DS as DS_WDO, X as X_WDO
from research.div_master.flow_breakout.explore import build_cache as build_fb_cache
from research.div_master.flow_breakout.refine_win import extract_win_rich

OPT_OPEN = {**M.V32, "abertura": M.V22_ABERTURA}


def collect_v32_asset(asset, lv_mode, opt, mode):
    """Coleta candidatos v3.2 (CONF ou OPC) com exatamente as mesmas colunas normalizadas para WIN ou WDO."""
    cache = win_cache if asset == "WIN" else wdo_cache
    X = XW if asset == "WIN" else X_WDO
    P = dict(M.PARAMS[asset])
    lo_w, hi_w = bt.WINDOW[asset]
    min_nw = 50.0 if asset == "WIN" else 2.0

    recs = []
    for d in sorted(cache):
        fb, w_all, w_wall, D = cache[d]
        levels = w_all if lv_mode == "all" else w_wall
        atr = M.atr_series(fb, P["tick"])
        cands = M.engine_v32(fb, levels, P, "common", atr=atr, opt=opt)

        raw = []
        if mode == "OPC":
            trigs, _ = M.triggers(fb, cands, P)
            by = {(c["dir"], c["j"]): c for c in cands}
            seq = {1: 0, -1: 0}
            for tr in trigs:
                if tr.get("dup"):
                    continue
                s = seq[tr["dir"]]
                seq[tr["dir"]] += 1
                t = tr["idx"]
                if t + 1 >= len(fb):
                    continue
                raw.append((by[(tr["dir"], tr["j"])], t, t + 1, s, bool(tr.get("super")), tr.get("esp", "")))
        else:
            seq = {1: 0, -1: 0}
            for c in cands:
                conf = c["conf"]
                if conf + 1 >= len(fb):
                    continue
                s = seq[c["dir"]]
                seq[c["dir"]] += 1
                raw.append((c, conf, conf + 1, s, False, "CONF"))

        for c, idx_sig, idx_in, seq_n, is_super, esp in raw:
            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            ep = float(D["o5"][e])
            dr = int(c["dir"])
            half50 = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
            half30 = max(0.5 * float(D["u30"][e] - D["l30"][e]), X["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            ext30 = -dr * float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / half30
            d_wall = min((abs(float(c["px2"]) - w) for w in w_wall), default=99999.0)
            pass_s = dr * sum(float(fb[x].get("inst_pass_delta", 0.0)) for x in range(c["j"], idx_sig + 1))
            candle_fav = dr * (float(fb[idx_sig]["close"]) - float(fb[idx_sig]["open"])) > 0
            nw = bt.next_level(w_all, ep, dr, min_nw + X["front"])
            nw_d = dr * (nw - ep) - X["front"] if nw is not None else np.nan

            recs.append(dict(
                date=d, e=e, ep=ep, dir=dr, j=c["j"], tm=tm, hh=tm // 60,
                seq=seq_n, is_super=is_super, esp=esp,
                has_w=(c["c1"] is not None or c["c2"] is not None),
                has_d=(c["day"] is not None),
                d_wall_z=(d_wall <= P["zone"]),
                ext50=ext50, slope50=slope50, ext30=ext30,
                pass_=pass_s, candle_fav=candle_fav, nw_d=nw_d,
            ))
    return pd.DataFrame(recs).sort_values(["date", "tm", "j"]).reset_index(drop=True)


# Saídas proporcionais equivalentes (WIN pts vs WDO pts: escala ~20x = PARAMS_WIN / PARAMS_WDO)
JOINT_EXITS = [
    ("E22_BE_t12",    dict(WIN=(200.0, "none", 0.0, 180.0, 20.0, 12), WDO=(10.0, "none", 0.0, 9.0, 1.0, 12))),
    ("SL14_NW_t24",   dict(WIN=(280.0, "nw",   0.0,   0.0,  0.0, 24), WDO=(14.0, "nw",   0.0, 0.0, 0.0, 24))),
    ("SL14_TP12_t24", dict(WIN=(280.0, "fix", 240.0,  0.0,  0.0, 24), WDO=(14.0, "fix", 12.0, 0.0, 0.0, 24))),
    ("SL14_TP12_t12", dict(WIN=(280.0, "fix", 240.0,  0.0,  0.0, 12), WDO=(14.0, "fix", 12.0, 0.0, 0.0, 12))),
    ("SL12_TP12_t24", dict(WIN=(250.0, "fix", 250.0,  0.0,  0.0, 24), WDO=(12.5, "fix", 12.5, 0.0, 0.0, 24))),
    ("SL10_TP15_t24", dict(WIN=(200.0, "fix", 300.0,  0.0,  0.0, 24), WDO=(10.0, "fix", 15.0, 0.0, 0.0, 24))),
    ("SL12_TP10_t18", dict(WIN=(250.0, "fix", 200.0,  0.0,  0.0, 18), WDO=(12.5, "fix", 10.0, 0.0, 0.0, 18))),
]


def presim_asset(asset, df, ex_spec):
    DS = DS_WIN if asset == "WIN" else DS_WDO
    X = XW if asset == "WIN" else X_WDO
    sl, tk, tv, bt_t, bt_l, tmax = ex_spec[asset]
    nw_min, nw_lo, nw_hi = (50.0, 80.0, 440.0) if asset == "WIN" else (2.5, 4.0, 22.0)
    n = len(df)
    pnl = np.full(n, np.nan)
    xt = np.zeros(n, dtype=np.int64)
    for i, r in enumerate(df.itertuples()):
        D = DS[r.date]
        if tk == "fix":
            tp_px = r.ep + r.dir * tv
        elif tk == "none":
            tp_px = r.ep + r.dir * 999999.0
        else:
            if np.isnan(r.nw_d) or r.nw_d < nw_min:
                continue
            tp_px = r.ep + r.dir * min(max(r.nw_d, nw_lo), nw_hi)
        p, x = bt.sim(*bt._args(D), D["u30"], r.e, r.ep, r.dir, sl, tp_px, False,
                      0.0, 0.0, 0.0, bt_t, bt_l, tmax, X["tick"])
        pnl[i] = (p - X["cost"]) * X["brl"]
        xt[i] = x
    return pnl, xt


def test_breakout_both():
    """Aplica exatamente B_dw_ex10 e B_dw_vol11 nos dois ativos (WIN e WDO) com os mesmos filtros adimensionais."""
    print("\n=== 1. TESTE DIRETO DE ROMPIMENTO DE WALL (B_dw_ex10 e B_dw_vol11) EM WIN vs WDO ===")
    for asset in ("WIN", "WDO"):
        DS, cache = build_fb_cache(asset)
        X = bt.X[asset]
        tick = X["tick"]
        lo_w, hi_w = bt.WINDOW[asset]
        min_free = 200.0 if asset == "WIN" else 8.0   # 40 ticks livres (200 pts WIN = 40 ticks; 8 pts WDO = 16 ticks, testamos 5 e 8 pts)
        sl_ex10, tp_ex10 = (280.0, 280.0) if asset == "WIN" else (11.0, 11.0)
        sl_vol11, tp_vol11 = (250.0, 250.0) if asset == "WIN" else (10.0, 10.0)

        for free_thr in ([200.0] if asset == "WIN" else [4.0, 6.0, 8.0]):
            rows_ex10, rows_vol11 = [], []
            for d, day in cache.items():
                fb, D, lv_wall, lv_all = day["fb"], day["D"], day["lv_wall"], day["lv_all"]
                n = len(fb)
                if n < 10:
                    continue
                o = np.array([float(b["open"]) for b in fb])
                h = np.array([float(b["high"]) for b in fb])
                l = np.array([float(b["low"]) for b in fb])
                c = np.array([float(b["close"]) for b in fb])
                wv = np.array([float(b["wave"]) for b in fb])
                aggr = np.array([float(b.get("inst_aggr_delta", 0.0)) for b in fb])
                tot_v = np.array([float(b.get("buy_vol", 0.0)) + float(b.get("sell_vol", 0.0)) for b in fb])
                abs_aggr = np.abs(aggr)
                rng = np.maximum(h - l, tick)

                for i in range(4, n - 1):
                    tm_in = bt.hm(fb[i + 1]["time"])
                    if not (lo_w <= tm_in <= 900) or tm_in not in D["pos"]:
                        continue
                    e = D["pos"][tm_in]
                    if e < 2:
                        continue
                    ep = float(D["o5"][e])
                    med_aggr = float(np.median(abs_aggr[: i + 1])) or 1.0
                    med_v = float(np.median(tot_v[: i + 1])) or 1.0
                    half50 = max(float(D["u50"][e] - D["c50"][e]), tick)
                    ext50 = float(D["c5"][e - 1] - D["c50"][e]) / half50
                    close_pos = (c[i] - l[i]) / rng[i]

                    for dr in (1, -1):
                        cross_w = any((c[i - 1] <= w < c[i]) if dr == 1 else (c[i - 1] >= w > c[i]) for w in lv_wall)
                        if not cross_w:
                            continue
                        close_ext = close_pos if dr == 1 else (1.0 - close_pos)
                        ag_n = dr * aggr[i] / med_aggr
                        dw_f = dr * (wv[i] - wv[i - 1])
                        if not (close_ext >= 0.65 and ag_n >= 1.0 and dw_f > 0):
                            continue
                        nwa = bt.next_level(lv_all, ep, dr, (50.0 if asset == "WIN" else 2.0) + X["front"])
                        nwa_d = dr * (nwa - ep) - X["front"] if nwa is not None else np.nan
                        if np.isnan(nwa_d) or nwa_d < free_thr:
                            continue
                        if dr * ext50 < 1.0:
                            p, xt = bt.sim(*bt._args(D), D["u30"], e, ep, dr, sl_ex10, ep + dr * tp_ex10, False, 0.0, 0.0, 0.0, 0.0, 0.0, 24, tick)
                            rows_ex10.append(dict(date=d, tm=tm_in, pnl=(p - X["cost"]) * X["brl"], xt=xt))
                        if tot_v[i] / med_v >= 1.1:
                            p, xt = bt.sim(*bt._args(D), D["u30"], e, ep, dr, sl_vol11, ep + dr * tp_vol11, False, 0.0, 0.0, 0.0, 0.0, 0.0, 18, tick)
                            rows_vol11.append(dict(date=d, tm=tm_in, pnl=(p - X["cost"]) * X["brl"], xt=xt))

            for lbl, rlist in [(f"{asset} B_dw_ex10 (free>={free_thr})", rows_ex10),
                               (f"{asset} B_dw_vol11 (free>={free_thr})", rows_vol11)]:
                if not rlist:
                    print(f"  {lbl:34s}: 0 ops")
                else:
                    df_t = bt.mgmt(pd.DataFrame(rlist), "pnl", "xt", "UM")
                    print(f"  {lbl:34s}: {bt.stats(df_t, 'pnl', 'xt')}")


if __name__ == "__main__":
    t0 = time.time()
    test_breakout_both()

    print("\n=== 2. BUSCA SIMÉTRICA v3.2: EXATAMENTE A MESMA REGRA EM WIN E WDO (>=80 ops e H1/H2/OOS>0 em AMBOS) ===")
    joint_hits = []
    for cfg_lbl, lv_mode, opt, mode in [
        ("V32_OPEN_wall", "wall", OPT_OPEN, "CONF"),
        ("V32_OPEN_all",  "all",  OPT_OPEN, "CONF"),
        ("V32_PROD_wall", "wall", M.V32_PROD, "CONF"),
        ("V32_PROD_all",  "all",  M.V32_PROD, "CONF"),
        ("V32_OPEN_wall", "wall", OPT_OPEN, "OPC"),
        ("V32_OPEN_all",  "all",  OPT_OPEN, "OPC"),
        ("V32_PROD_wall", "wall", M.V32_PROD, "OPC"),
        ("V32_PROD_all",  "all",  M.V32_PROD, "OPC"),
    ]:
        df_w = collect_v32_asset("WIN", lv_mode, opt, mode)
        df_d = collect_v32_asset("WDO", lv_mode, opt, mode)
        pre_w = {en: presim_asset("WIN", df_w, es) for en, es in JOINT_EXITS}
        pre_d = {en: presim_asset("WDO", df_d, es) for en, es in JOINT_EXITS}

        def build_masks(df):
            anc = {
                "COMMON": (df["has_w"] | df["has_d"]).values,
                "ANY_WALL": df["has_w"].values,
                "DWALL_Z": df["d_wall_z"].values,
                "NO_SUP_SEQ2": (~df["is_super"] & (df["seq"] <= 1)).values,
            }
            tm = {
                "ALL": np.ones(len(df), dtype=bool),
                "HH_NE_11": (df["hh"] != 11).values,
                "09_12": (df["tm"] <= 720).values,
                "09_15": (df["tm"] <= 900).values,
                "10_16": ((df["tm"] >= 600) & (df["tm"] < 960)).values,
            }
            ctx = {
                "NONE": np.ones(len(df), dtype=bool),
                "ext30>0": (df["ext30"] > 0.0).values,
                "ext50>0": (df["ext50"] > 0.0).values,
                "ext50>-0.5&sl>-0.5": ((df["ext50"] > -0.5) & (df["slope50"] > -0.5)).values,
                "pass>0": (df["pass_"] > 0.0).values,
                "candle_fav": df["candle_fav"].values,
            }
            return anc, tm, ctx

        anc_w, tm_w, ctx_w = build_masks(df_w)
        anc_d, tm_d, ctx_d = build_masks(df_d)

        for a_k in anc_w:
            for t_k in tm_w:
                for c_k in ctx_w:
                    mw = anc_w[a_k] & tm_w[t_k] & ctx_w[c_k]
                    md = anc_d[a_k] & tm_d[t_k] & ctx_d[c_k]
                    if mw.sum() < 75 or md.sum() < 75:
                        continue
                    for ex_name, _ in JOINT_EXITS:
                        pw, xw = pre_w[ex_name]
                        pd_, xd = pre_d[ex_name]
                        vw = ~np.isnan(pw[mw])
                        vd = ~np.isnan(pd_[md])
                        if vw.sum() < 75 or vd.sum() < 75:
                            continue
                        sw = df_w.loc[mw, ["date", "tm"]].iloc[vw].copy()
                        sw["pnl"], sw["xt"] = pw[mw][vw], xw[mw][vw]
                        sw = bt.mgmt(sw, "pnl", "xt", "UM")

                        sd = df_d.loc[md, ["date", "tm"]].iloc[vd].copy()
                        sd["pnl"], sd["xt"] = pd_[md][vd], xd[md][vd]
                        sd = bt.mgmt(sd, "pnl", "xt", "UM")

                        if len(sw) < 75 or len(sd) < 75:
                            continue
                        stw = bt.stats(sw, "pnl", "xt")
                        std = bt.stats(sd, "pnl", "xt")
                        if (stw["rdd"] >= 2.5 and std["rdd"] >= 2.5
                                and stw["h1"] > 0 and stw["h2"] > 0 and stw["oos"] > 0
                                and std["h1"] > 0 and std["h2"] > 0 and std["oos"] > 0):
                            port = bt.portfolio(sw, sd, "pnl", "pnl", "xt", "xt")
                            joint_hits.append(dict(
                                cfg=cfg_lbl, mode=mode, anc=a_k, time=t_k, ctx=c_k, exit=ex_name,
                                w_ops=stw["ops"], w_pf=stw["pf"], w_net=stw["net"], w_rdd=stw["rdd"], w_m=stw["meses"],
                                d_ops=std["ops"], d_pf=std["pf"], d_net=std["net"], d_rdd=std["rdd"], d_m=std["meses"],
                                min_rdd=round(min(stw["rdd"], std["rdd"]), 2),
                                port_rdd=port["rdd"], port_net=port["net"], port_m=port["meses"],
                            ))

    jdf = pd.DataFrame(joint_hits).sort_values(["min_rdd", "port_rdd"], ascending=[False, False]).reset_index(drop=True) if joint_hits else pd.DataFrame()
    print(f"Concluído em {time.time()-t0:.1f}s | Regras idênticas aprovadas nos 2 ativos: {len(jdf)}")
    if not jdf.empty:
        print(jdf.head(25).to_string(index=False))
