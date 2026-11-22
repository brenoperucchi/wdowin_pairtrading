"""Fase 2: Busca calibrada para WDO (Wall-only, parâmetros WDO, v3.2 com abertura, e filtros simples) em Numba."""
import sys
import time
from pathlib import Path
import numpy as np
import numba as nb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import modulo as M
from research.div_master.especialistas import bt

t0 = time.time()
raw_m5 = {d: v for d, v in load_asset("WDO", "M5").items() if d <= bt.END}
DS = bt.market("WDO")
X = bt.X["WDO"]
lo_w, hi_w = bt.WINDOW["WDO"]
D_args = {d: bt._args(D) for d, D in DS.items()}

# Pré-calcula flow e walls por pregão
days_cache = {}
for d in sorted(raw_m5):
    D = DS.get(d)
    if D is None:
        continue
    bars, walls, _ = raw_m5[d]
    fb = M.compute_flow(bars, "WDO")
    w_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    w_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
    w_mid = sorted(float(w["price"]) for w in walls if w.get("type") == "MidWall")
    w_gamma = sorted(float(w["price"]) for w in walls if w.get("type") in ("GammaFlip", "MaxGamma", "MinGamma"))
    days_cache[d] = (fb, w_all, w_wall, w_mid, w_gamma, D)

date_list = sorted(days_cache.keys())
date_to_id = {d: i for i, d in enumerate(date_list)}
is_h1_d = np.array([d <= bt.H1_END for d in date_list], dtype=np.bool_)
is_h2_d = np.array([(d > bt.H1_END) and (d <= bt.IS_END) for d in date_list], dtype=np.bool_)
is_oos_d = np.array([d > bt.IS_END for d in date_list], dtype=np.bool_)
mon_d, _ = pd.factorize(pd.Series(date_list).str[:7])
n_mon = int(mon_d.max()) + 1

print(f"Precomputed flow for {len(date_list)} days in {time.time()-t0:.1f}s")


@nb.njit(cache=True)
def eval_subset_nb(idxs, pnl_col, xt_col, date_ids, tm_vals, is_h1_d, is_h2_d, is_oos_d, mon_d, n_mon, um):
    n = len(idxs)
    if n < 50:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0
    # Seleciona não-NaN e (se um=True) UM_POR_VEZ (idxs já ordenados por date_id, tm, j)
    sel_p = np.empty(n, dtype=np.float64)
    sel_xt = np.empty(n, dtype=np.int64)
    sel_d = np.empty(n, dtype=np.int64)
    sel_tm = np.empty(n, dtype=np.int64)
    k = 0
    last_d = -1
    last_xt = -1
    for i in range(n):
        idx = idxs[i]
        p = pnl_col[idx]
        if np.isnan(p):
            continue
        did = date_ids[idx]
        tm = tm_vals[idx]
        if um:
            if did != last_d:
                last_d = did
                last_xt = -1
            if tm <= last_xt:
                continue
            last_xt = xt_col[idx]
        sel_p[k] = p
        sel_xt[k] = xt_col[idx]
        sel_d[k] = did
        sel_tm[k] = tm
        k += 1
    if k < 50:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0

    # Ordena dentro de cada dia por (xt, tm) via chave composta did * 10^8 + xt * 10^4 + tm
    keys = np.empty(k, dtype=np.int64)
    for i in range(k):
        keys[i] = sel_d[i] * 100000000 + sel_xt[i] * 10000 + sel_tm[i]
    order = np.argsort(keys)

    eq = 0.0
    peak = 0.0
    dd = 0.0
    gains = 0.0
    losses = 0.0
    wins = 0
    h1 = 0.0
    h2 = 0.0
    oos = 0.0
    mon_sum = np.zeros(n_mon, dtype=np.float64)
    mon_cnt = np.zeros(n_mon, dtype=np.int64)

    for m in range(k):
        pos = order[m]
        p = sel_p[pos]
        did = sel_d[pos]
        eq += p
        if eq > peak:
            peak = eq
        cur_dd = peak - eq
        if cur_dd > dd:
            dd = cur_dd
        if p > 0.0:
            gains += p
            wins += 1
        elif p < 0.0:
            losses -= p
        if is_h1_d[did]:
            h1 += p
        elif is_h2_d[did]:
            h2 += p
        else:
            oos += p
        mc = mon_d[did]
        mon_sum[mc] += p
        mon_cnt[mc] += 1

    if eq <= 0.0 or dd <= 0.0:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0
    rdd = eq / dd
    pf = gains / losses if losses > 0.0 else 99.0
    wr = 100.0 * wins / k
    m_pos = 0
    m_tot = 0
    for c in range(n_mon):
        if mon_cnt[c] > 0:
            m_tot += 1
            if mon_sum[c] > 0.0:
                m_pos += 1
    return k, wr, pf, eq, dd, rdd, h1, h2, oos, m_pos, m_tot


# Menu de saídas compacto e limpo
exit_defs = []
for sl in (5.0, 6.5, 8.5, 10.0, 12.0):
    for tp in (5.0, 6.5, 8.0, 10.0, 12.0, 16.0):
        for tmax in (8, 12, 24):
            exit_defs.append((f"F_sl{sl}_tp{tp}_tm{tmax}", "fix", sl, tp, 0.0, 0.0, tmax))
    for tp in (10.0, 14.0):
        exit_defs.append((f"B_sl{sl}_tp{tp}_be4_tm24", "fix", sl, tp, 4.0, 1.0, 24))
    exit_defs.append((f"N30_sl{sl}_tm24", "nwe30", sl, 0.0, 0.0, 0.0, 24))
    exit_defs.append((f"N30_sl{sl}_be4_tm24", "nwe30", sl, 0.0, 4.0, 1.0, 24))
    exit_defs.append((f"N50_sl{sl}_tm24", "nwe50", sl, 0.0, 0.0, 0.0, 24))
    exit_defs.append((f"NW_sl{sl}_tm24", "nw", sl, 0.0, 0.0, 0.0, 24))


def build_P(**kw):
    P = dict(M.PARAMS["WDO"])
    P.update(kw)
    return P


# Configurações de motores para testar (calibração WDO + padrão + Wall-only)
engine_configs = [
    ("v32_std_all", "v3.2", build_P(), "all", "all", M.V32_PROD),
    ("v32_open_all", "v3.2", build_P(), "all", "all", {**M.V32, "abertura": M.V22_ABERTURA}),
    ("v32_wall_only", "v3.2", build_P(), "wall", "all", M.V32_PROD),
    ("v32_tightW", "v3.2", build_P(zone=2.5, pierce_max=4.0), "wall", "all", M.V32_PROD),
    ("v32_wideW", "v3.2", build_P(zone=5.0, pierce_max=8.0), "all", "all", M.V32_PROD),
    ("v32_zz15", "v3.2", build_P(zz_floor=1.5, tol_v21=2.5), "all", "all", M.V32_PROD),
    ("v31_com_all", "v3.1", build_P(), "all", "common", None),
    ("v31_all_all", "v3.1", build_P(), "all", "all", None),
    ("v31_wall_only", "v3.1", build_P(), "wall", "common", None),
    ("v31_tightW", "v3.1", build_P(zone=2.5, pierce_max=4.0), "wall", "common", None),
    ("v31_wideW", "v3.1", build_P(zone=5.0, pierce_max=8.0), "wall", "common", None),
    ("v21_std_com", "v2.1", build_P(), "all", "common", None),
    ("v21_wall_only", "v2.1", build_P(), "wall", "common", None),
    ("v22_std_com", "v2.2", build_P(), "all", "common", M.V22_ABERTURA),
    ("v3_std_com", "v3", build_P(), "all", "common", None),
    ("v3_wall_only", "v3", build_P(), "wall", "common", None),
]

all_hits = []

for cfg_name, eng, P_cfg, lv_mode, elig, opt in engine_configs:
    t_c = time.time()
    rows = []
    for d in date_list:
        fb, w_all, w_wall, w_mid, w_gamma, D = days_cache[d]
        levels = w_wall if lv_mode == "wall" else w_all
        atr = M.atr_series(fb, P_cfg["tick"])
        if eng == "v3.2":
            cands = M.engine_v32(fb, levels, P_cfg, elig, atr=atr, opt=opt)
        elif eng == "v3.1":
            cands = M.engine_v31(fb, levels, P_cfg, elig, atr=atr)
        elif eng == "v2.1":
            cands = M.engine_v21(fb, levels, P_cfg, elig, atr=atr)
        elif eng == "v2.2":
            cands = M.engine_v22(fb, levels, P_cfg, elig, atr=atr, opt=opt)
        else:
            cands = M.engine_v3(fb, levels, P_cfg, elig)

        trigs, _ = M.triggers(fb, cands, P_cfg)
        opc_by = {(t["dir"], t["j"]): t for t in trigs if not t["dup"]}

        for c in cands:
            dr, j, conf = c["dir"], c["j"], c["conf"]
            if conf + 1 >= len(fb):
                continue
            has_w = c["c1"] is not None or c["c2"] is not None
            has_d = c["day"] is not None
            px2 = float(c["px2"])
            d_wall = min((abs(px2 - w) for w in w_wall), default=999.0)
            d_mid = min((abs(px2 - w) for w in w_mid), default=999.0)
            d_gam = min((abs(px2 - w) for w in w_gamma), default=999.0)
            reclaim = bool(c["c1"] is not None and dr * (float(fb[conf]["close"]) - float(c["c1"])) > 0)
            pass_s = dr * sum(float(fb[x].get("inst_pass_delta", 0)) for x in range(j, conf + 1))
            wyck_s = dr * sum(float(fb[x].get("wyckoff_abs", 0)) for x in range(j, conf + 1))
            aggr_s = dr * sum(float(fb[x].get("inst_aggr_delta", 0)) for x in range(j, conf + 1))
            force_c = dr * float(fb[conf].get("force", 0))
            candle_fav = dr * (float(fb[conf]["close"]) - float(fb[conf]["open"])) > 0

            # CONF & OPC
            pairs = [("CONF", conf + 1)]
            tr = opc_by.get((dr, j))
            if tr is not None and tr["idx"] + 1 < len(fb):
                pairs.append(("OPC", tr["idx"] + 1))

            for mode, idx_in in pairs:
                tm = bt.hm(fb[idx_in]["time"])
                if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                    continue
                e = D["pos"][tm]
                ep = float(D["o5"][e])
                half = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
                ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half if e >= 1 else np.nan
                slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half
                ext30 = -dr * float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / max(0.5 * (D["u30"][e] - D["l30"][e]), X["tick"]) if e >= 1 else np.nan
                nw = bt.next_level(w_all, ep, dr, 2.0 + X["front"])
                nw_d = dr * (nw - ep) - X["front"] if nw is not None else np.nan
                rows.append(dict(
                    did=date_to_id[d], date=d, mode=mode, dir=dr, j=j, e=e, ep=ep, tm=tm, hora=tm // 100,
                    has_w=has_w, has_c1=c["c1"] is not None, has_c2=c["c2"] is not None, has_d=has_d,
                    reclaim=reclaim, d_wall=d_wall, d_mid=d_mid, d_gam=d_gam,
                    ext50=ext50, slope50=slope50, ext30=ext30,
                    pass_=pass_s, wyck=wyck_s, aggr=aggr_s, force=force_c,
                    candle=candle_fav, micro=bool(c["micro"]),
                    wd=float(c["wd"]) / max(float(c["thr"]), 1e-9), nw_d=nw_d,
                ))

    if not rows:
        continue
    df = pd.DataFrame(rows).sort_values(["did", "tm", "j"]).reset_index(drop=True)
    n_r = len(df)
    n_e = len(exit_defs)
    pnl_mat = np.full((n_r, n_e), np.nan, dtype=np.float64)
    xt_mat = np.full((n_r, n_e), -1, dtype=np.int64)

    dids = df["did"].values
    dts = df["date"].values
    es = df["e"].values
    eps = df["ep"].values
    drs = df["dir"].values
    tms = df["tm"].values
    nws = df["nw_d"].values

    for i in range(n_r):
        d = dts[i]
        D = DS[d]
        args = D_args[d]
        e = int(es[i])
        ep = float(eps[i])
        dr = int(drs[i])
        b30 = D["u30"] if dr == 1 else D["l30"]
        b50 = D["u50"] if dr == 1 else D["l50"]
        nwd = float(nws[i])
        for j, (_, kind, sl, tp, bt_, bl, tmax) in enumerate(exit_defs):
            if kind == "fix":
                p, xt = bt.sim(*args, b30, e, ep, dr, sl, ep + dr * tp, False, 0.0, 0.0, 0.0, bt_, bl, tmax, X["tick"])
            elif kind == "nwe30":
                p, xt = bt.sim(*args, b30, e, ep, dr, sl, 0.0, True, X["front"], 2.0, 30.0, bt_, bl, tmax, X["tick"])
            elif kind == "nwe50":
                p, xt = bt.sim(*args, b50, e, ep, dr, sl, 0.0, True, X["front"], 2.0, 40.0, bt_, bl, tmax, X["tick"])
            else:
                if np.isnan(nwd) or nwd < 2.5:
                    continue
                p, xt = bt.sim(*args, b30, e, ep, dr, sl, ep + dr * min(max(nwd, 4.0), 22.0), False, 0.0, 0.0, 0.0, 0.0, 0.0, tmax, X["tick"])
            pnl_mat[i, j] = (p - X["cost"]) * X["brl"]
            xt_mat[i, j] = xt

    # Filtros limpos (âncora × no máx 1 contexto)
    ancs = [
        ("ALL", np.ones(n_r, bool)),
        ("COMMON", (df["has_w"] | df["has_d"]).values),
        ("ANY_WALL", df["has_w"].values),
        ("WALL_ONLY", (df["d_wall"] <= P_cfg["zone"]).values),
        ("FURO", df["has_c1"].values),
        ("RECLAIM", df["reclaim"].values),
        ("EXTREMO", (df["has_d"] & ~df["has_w"]).values),
        ("EXT_OR_FURO", (df["has_d"] | df["has_c1"]).values),
        ("HAS_DAY", df["has_d"].values),
        ("GAMMA", (df["d_gam"] <= 5.0).values),
    ]
    ctxs = [
        ("NONE", np.ones(n_r, bool)),
        ("e50>0", (df["ext50"] > 0.0).values),
        ("e50>0.2", (df["ext50"] > 0.2).values),
        ("e50>0.3", (df["ext50"] > 0.3).values),
        ("e30>0", (df["ext30"] > 0.0).values),
        ("slp<=0", (df["slope50"] <= 0.0).values),
        ("slp>0", (df["slope50"] > 0.0).values),
        ("win_ctx", ((df["ext50"] > -0.5) & (df["slope50"] > -0.5)).values),
        ("pass>0", (df["pass_"] > 0.0).values),
        ("wyck>0", (df["wyck"] > 0.0).values),
        ("aggr>0", (df["aggr"] > 0.0).values),
        ("force>0", (df["force"] > 0.0).values),
        ("micro", df["micro"].values),
        ("candle", df["candle"].values),
        ("wd<=2", (df["wd"] <= 2.0).values),
        ("wd>=1.2", (df["wd"] >= 1.2).values),
        ("no11", (df["hora"] != 11).values),
        ("9a15", ((df["hora"] >= 9) & (df["hora"] <= 15)).values),
        ("10a15", ((df["hora"] >= 10) & (df["hora"] <= 15)).values),
        ("dir=-1", (df["dir"] == -1).values),
        ("dir=1", (df["dir"] == 1).values),
    ]

    cfg_hits = 0
    for mode in ("CONF", "OPC"):
        m_m = (df["mode"] == mode).values
        for aname, amask in ancs:
            m_ma = m_m & amask
            if m_ma.sum() < 55:
                continue
            for cname, cmask in ctxs:
                idxs = np.flatnonzero(m_ma & cmask)
                if len(idxs) < 55:
                    continue
                for j, ex in enumerate(exit_defs):
                    k, wr, pf, net, dd, rdd, h1, h2, oos, mp, mt = eval_subset_nb(
                        idxs, pnl_mat[:, j], xt_mat[:, j], dids, tms,
                        is_h1_d, is_h2_d, is_oos_d, mon_d, n_mon, True
                    )
                    if k >= 55 and rdd >= 4.5 and h1 > 0 and h2 > 0 and oos > 0:
                        all_hits.append(dict(
                            cfg=cfg_name, mode=mode, anc=aname, ctx=cname, exit=ex[0],
                            ops=k, wr=round(wr, 1), pf=round(pf, 2), net=round(net), dd=round(dd),
                            rdd=round(rdd, 2), meses=f"{mp}/{mt}",
                            h1=round(h1), h2=round(h2), oos=round(oos),
                        ))
                        cfg_hits += 1
    print(f"  {cfg_name:15s}: rows={n_r:4d}, hits(ops>=55,rdd>=4.5,all3)={cfg_hits:3d} ({time.time()-t_c:.1f}s)")

res = pd.DataFrame(all_hits)
print(f"\nTotal hits: {len(res)} in {time.time()-t0:.1f}s")
if len(res):
    res.to_pickle(Path(__file__).resolve().parent / "phase2_hits.pkl")
    print("\n=== TOP 40 DISTINCT CLUSTERS (ops>=60, all3, rdd>=5.0) ===")
    p60 = res[(res["ops"] >= 60) & (res["rdd"] >= 5.0)].sort_values("rdd", ascending=False)
    if len(p60):
        print(p60.groupby(["cfg", "mode", "anc", "ctx"], as_index=False).first().sort_values("rdd", ascending=False).head(40).to_string(index=False))
    else:
        print("(none >= 5.0 with ops>=60; showing top 30 >= 4.5)")
        print(res.sort_values("rdd", ascending=False).head(30).to_string(index=False))
