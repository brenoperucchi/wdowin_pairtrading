"""Fase 1: Busca sistemática WDO via M1 tick-a-tick nos 6 motores + Walls + filtros + saídas."""
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import modulo as M
from research.div_master.especialistas import bt

t0 = time.time()
print("M.LEVEL_TYPES:", M.LEVEL_TYPES)
print("M.TRIGGER:", M.TRIGGER)
print("M.COMMON:", M.COMMON)
print("M.PARAMS['WDO']:", M.PARAMS["WDO"])
print("M.V32:", M.V32)
print("M.V32_PROD:", M.V32_PROD)

# Carrega M5 Profit e M1 MT5 WDO
raw_m5 = {d: v for d, v in load_asset("WDO", "M5").items() if d <= bt.END}
DS = bt.market("WDO")
X = bt.X["WDO"]
P = M.PARAMS["WDO"]
lo_w, hi_w = bt.WINDOW["WDO"]

print(f"Loaded WDO M5={len(raw_m5)} days, MT5={len(DS)} days in {time.time()-t0:.1f}s")

# Extrai todos os sinais (CONF e OPC) com metadados detalhados de Walls e fluxo
rows = []
engines = ("v2.1", "v2.2", "v3", "v3.1", "v3.2", "v3.2_ab")

for d in sorted(raw_m5):
    D = DS.get(d)
    if D is None:
        continue
    bars, walls, _ = raw_m5[d]
    fb = M.compute_flow(bars, "WDO")
    atr = M.atr_series(fb, P["tick"])

    w_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    w_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
    w_mid = sorted(float(w["price"]) for w in walls if w.get("type") == "MidWall")
    w_flip = [float(w["price"]) for w in walls if w.get("type") == "GammaFlip"]
    w_maxg = [float(w["price"]) for w in walls if w.get("type") == "MaxGamma"]
    w_ming = [float(w["price"]) for w in walls if w.get("type") == "MinGamma"]

    res_eng = {
        "v2.1": M.engine_v21(fb, w_all, P, "all", atr=atr),
        "v2.2": M.engine_v22(fb, w_all, P, "all", atr=atr, opt=M.V22_ABERTURA),
        "v3": M.engine_v3(fb, w_all, P, "all"),
        "v3.1": M.engine_v31(fb, w_all, P, "all", atr=atr),
        "v3.2": M.engine_v32(fb, w_all, P, "all", atr=atr, opt=M.V32_PROD),
        "v3.2_ab": M.engine_v32(fb, w_all, P, "all", atr=atr, opt={**M.V32_PROD, "abertura": M.V22_ABERTURA}),
    }

    for eng in engines:
        cands = res_eng[eng]
        by_jk = {(c["dir"], c["j"]): c for c in cands}
        trigs, _ = M.triggers(fb, cands, P)
        opc_by = {(tr["dir"], tr["j"]): tr for tr in trigs if not tr["dup"]}

        seq = {1: 0, -1: 0}
        for c in cands:
            dir_ = c["dir"]
            j = c["j"]
            conf = c["conf"]
            if conf + 1 >= len(fb):
                continue

            # Âncora detalhada
            has_wall = c["c1"] is not None or c["c2"] is not None
            has_day = c["day"] is not None
            if has_wall and has_day:
                anc = "SUPER"
            elif c["c1"] is not None:
                anc = "FURO_WALL"
            elif c["c2"] is not None:
                anc = "WALL_ZONA"
            elif has_day:
                anc = "EXTREMO"
            else:
                anc = "SEM_ANC"

            px2 = float(c["px2"])
            d_wall = min((abs(px2 - w) for w in w_wall), default=999.0)
            d_mid = min((abs(px2 - w) for w in w_mid), default=999.0)
            d_flip = min((abs(px2 - w) for w in w_flip), default=999.0)
            d_maxg = min((abs(px2 - w) for w in w_maxg), default=999.0)
            d_ming = min((abs(px2 - w) for w in w_ming), default=999.0)
            near_kind = "WALL" if d_wall <= P["zone"] else ("MID" if d_mid <= P["zone"] else "NENHUMA")

            # Fluxo na janela j..conf
            wyck_sum = dir_ * sum(float(fb[x].get("wyckoff_abs", 0)) for x in range(j, conf + 1))
            pass_sum = dir_ * sum(float(fb[x].get("inst_pass_delta", 0)) for x in range(j, conf + 1))
            aggr_sum = dir_ * sum(float(fb[x].get("inst_aggr_delta", 0)) for x in range(j, conf + 1))
            force_c = dir_ * float(fb[conf].get("force", 0))
            candle_dir = dir_ * (float(fb[conf]["close"]) - float(fb[conf]["open"])) > 0

            # Reclaim: c1 existia (furou wall) e conf fechou do lado certo da c1
            reclaim_wall = False
            if c["c1"] is not None:
                reclaim_wall = dir_ * (float(fb[conf]["close"]) - float(c["c1"])) > 0

            # Conf entry bar in MT5
            tm_conf = bt.hm(fb[conf + 1]["time"])
            e_conf = D["pos"].get(tm_conf, -1) if (lo_w <= tm_conf <= hi_w) else -1

            # OPC entry bar in MT5
            tr_opc = opc_by.get((dir_, j))
            e_opc = -1
            tm_opc = -1
            opc_esp = ""
            opc_sub = ""
            if tr_opc is not None and tr_opc["idx"] + 1 < len(fb):
                tm_opc = bt.hm(fb[tr_opc["idx"] + 1]["time"])
                if lo_w <= tm_opc <= hi_w:
                    e_opc = D["pos"].get(tm_opc, -1)
                    opc_esp = tr_opc["esp"]
                    opc_sub = tr_opc["sub"]

            # Contexto no e_conf (se existir) ou e_opc
            for mode, e_idx, tm_in in [("CONF", e_conf, tm_conf), ("OPC", e_opc, tm_opc)]:
                if e_idx < 0:
                    continue
                ep = float(D["o5"][e_idx])
                half = max(float(D["u50"][e_idx] - D["c50"][e_idx]), X["tick"])
                ext50 = -dir_ * float(D["c5"][e_idx - 1] - D["c50"][e_idx]) / half if e_idx >= 1 else np.nan
                slope50 = dir_ * float(D["c50"][e_idx] - D["c50"][max(0, e_idx - 6)]) / half
                ext30 = -dir_ * float(D["c5"][e_idx - 1] - (D["u30"][e_idx] + D["l30"][e_idx]) * 0.5) / max(0.5 * (D["u30"][e_idx] - D["l30"][e_idx]), X["tick"]) if e_idx >= 1 else np.nan
                dmov = dir_ * float(D["c5"][e_idx - 1] - D["o5"][0]) / half if e_idx >= 1 else 0.0

                # Próxima Wall / MidWall a favor
                nw = bt.next_level(w_all, ep, dir_, 2.0 + X["front"])
                nw_dist = dir_ * (nw - ep) - X["front"] if nw is not None else np.nan
                nw_w = bt.next_level(w_wall, ep, dir_, 2.0 + X["front"])
                nww_dist = dir_ * (nw_w - ep) - X["front"] if nw_w is not None else np.nan

                # SL no pivô + buf
                sl_piv = dir_ * (ep - (px2 - dir_ * X["buf"]))

                rows.append(dict(
                    date=d, engine=eng, mode=mode, dir=dir_, j=j, k=c["k"], conf=conf,
                    e=e_idx, ep=ep, tm=tm_in, hora=tm_in // 100,
                    seq_c=seq[dir_], lag=conf - j, anc=anc,
                    has_wall=has_wall, has_day=has_day,
                    c1=c["c1"] if c["c1"] is not None else np.nan,
                    c2=c["c2"] if c["c2"] is not None else np.nan,
                    near_kind=near_kind, d_wall=d_wall, d_mid=d_mid,
                    d_flip=d_flip, d_maxg=d_maxg, d_ming=d_ming,
                    reclaim=reclaim_wall, micro=bool(c["micro"]), candle_dir=candle_dir,
                    wd_ratio=float(c["wd"]) / max(float(c["thr"]), 1e-9),
                    wyck=wyck_sum, pass_=pass_sum, aggr=aggr_sum, force=force_c,
                    ext50=ext50, slope50=slope50, ext30=ext30, dmov=dmov,
                    sl_piv=sl_piv, nw_dist=nw_dist, nww_dist=nww_dist,
                    opc_esp=opc_esp, opc_sub=opc_sub,
                    period=("H1" if d <= bt.H1_END else ("H2" if d <= bt.IS_END else "OOS")),
                ))
            if mode == "CONF" or e_conf >= 0:
                pass
            seq[dir_] += 1

df = pd.DataFrame(rows).sort_values(["date", "tm", "j"]).reset_index(drop=True)
print(f"Extracted {len(df)} mode-rows across {df['date'].nunique()} days in {time.time()-t0:.1f}s")

# Pré-calcula array de datas e períodos para cálculo ultra-rápido de métricas
# Definimos um conjunto rico de saídas para testar vetorizadamente
exit_defs = []
for sl in (4.0, 5.5, 7.0, 8.5, 10.0, 12.0):
    for tp in (0.0, 6.0, 9.0, 12.0, 15.0, 20.0):
        for tmax in (6, 12, 24):
            if tp == 0.0 and tmax == 24:
                continue
            exit_defs.append((f"F_sl{sl}_tp{tp}_tm{tmax}", "fix", sl, tp, 0.0, 0.0, tmax))
    # Com BE
    for tp in (10.0, 14.0, 18.0, 0.0):
        for be_t, be_l in ((4.0, 1.0), (5.5, 1.5), (7.0, 2.0)):
            exit_defs.append((f"B_sl{sl}_tp{tp}_be{be_t}_{be_l}_tm24", "fix", sl, tp, be_t, be_l, 24))
    # NWE30 banda oposta
    exit_defs.append((f"N30_sl{sl}_tm24", "nwe30", sl, 0.0, 0.0, 0.0, 24))
    exit_defs.append((f"N30_sl{sl}_be4_tm24", "nwe30", sl, 0.0, 4.0, 1.0, 24))
    # NWE50 banda oposta
    exit_defs.append((f"N50_sl{sl}_tm24", "nwe50", sl, 0.0, 0.0, 0.0, 24))
    # Próxima Wall / MidWall (clipped 4..20)
    exit_defs.append((f"NW_sl{sl}_tm24", "nw", sl, 0.0, 4.0, 1.0, 24))
    exit_defs.append((f"NW_sl{sl}_nobe_tm24", "nw", sl, 0.0, 0.0, 0.0, 24))

# Também SL no pivô (clipped 2.5..12.0)
for tp in (8.0, 12.0, 16.0):
    exit_defs.append((f"PIV_tp{tp}_tm24", "piv", 0.0, tp, 4.0, 1.0, 24))
exit_defs.append(("PIV_nw_tm24", "piv_nw", 0.0, 0.0, 4.0, 1.0, 24))

print(f"Simulating {len(exit_defs)} exit specs on {len(df)} candidate entries...")
t_sim = time.time()

n_rows = len(df)
n_ex = len(exit_defs)
pnl_mat = np.full((n_rows, n_ex), np.nan, dtype=np.float64)
xt_mat = np.full((n_rows, n_ex), -1, dtype=np.int64)

# Cache _args(D)
D_args = {d: bt._args(D) for d, D in DS.items()}

dates_arr = df["date"].values
e_arr = df["e"].values
ep_arr = df["ep"].values
dir_arr = df["dir"].values
sl_piv_arr = df["sl_piv"].values
nw_arr = df["nw_dist"].values

for i in range(n_rows):
    d = dates_arr[i]
    D = DS[d]
    args = D_args[d]
    e = int(e_arr[i])
    ep = float(ep_arr[i])
    dr = int(dir_arr[i])
    band30 = D["u30"] if dr == 1 else D["l30"]
    band50 = D["u50"] if dr == 1 else D["l50"]
    slp = float(sl_piv_arr[i])
    nwd = float(nw_arr[i])

    for j, (name, kind, sl, tp, bt_, bl, tmax) in enumerate(exit_defs):
        if kind == "fix":
            tp_px = ep + dr * (tp if tp > 0 else 1e9)
            p, xt = bt.sim(*args, band30, e, ep, dr, sl, tp_px, False, 0.0, 0.0, 0.0, bt_, bl, tmax, X["tick"])
        elif kind == "nwe30":
            p, xt = bt.sim(*args, band30, e, ep, dr, sl, 0.0, True, X["front"], 2.0, 30.0, bt_, bl, tmax, X["tick"])
        elif kind == "nwe50":
            p, xt = bt.sim(*args, band50, e, ep, dr, sl, 0.0, True, X["front"], 2.0, 40.0, bt_, bl, tmax, X["tick"])
        elif kind == "nw":
            if np.isnan(nwd) or nwd < 2.5:
                continue
            tp_px = ep + dr * min(max(nwd, 4.0), 22.0)
            p, xt = bt.sim(*args, band30, e, ep, dr, sl, tp_px, False, 0.0, 0.0, 0.0, bt_, bl, tmax, X["tick"])
        elif kind == "piv":
            if slp < 2.0 or slp > 12.0:
                continue
            tp_px = ep + dr * tp
            p, xt = bt.sim(*args, band30, e, ep, dr, slp, tp_px, False, 0.0, 0.0, 0.0, bt_, bl, tmax, X["tick"])
        elif kind == "piv_nw":
            if slp < 2.0 or slp > 12.0 or np.isnan(nwd) or nwd < 2.5:
                continue
            tp_px = ep + dr * min(max(nwd, 4.0), 22.0)
            p, xt = bt.sim(*args, band30, e, ep, dr, slp, tp_px, False, 0.0, 0.0, 0.0, bt_, bl, tmax, X["tick"])
        pnl_mat[i, j] = (p - X["cost"]) * X["brl"]
        xt_mat[i, j] = xt

print(f"Finished Numba M1 simulation in {time.time()-t_sim:.1f}s")

# Constrói subgrupos econômicos limpos (df já ordenado por date, tm, j)
tm_vals = df["tm"].values
is_h1_all = dates_arr <= bt.H1_END
is_h2_all = (dates_arr > bt.H1_END) & (dates_arr <= bt.IS_END)
is_oos_all = dates_arr > bt.IS_END
mon_codes, _ = pd.factorize(pd.Series(dates_arr).str[:7])
n_mon = int(mon_codes.max()) + 1

def metrics_fast(idxs, ex_idx, mgmt="LIVRE"):
    pnls = pnl_mat[idxs, ex_idx]
    valid = ~np.isnan(pnls)
    if valid.sum() < 35:
        return None
    idxs = idxs[valid]
    pnls = pnls[valid]
    xts = xt_mat[idxs, ex_idx]
    dts = dates_arr[idxs]

    if mgmt == "UM":
        keep = np.empty(len(idxs), dtype=np.int64)
        k_n = 0
        last_d = ""
        last_xt = -1
        tms = tm_vals[idxs]
        for pos in range(len(idxs)):
            d_ = dts[pos]
            if d_ != last_d:
                last_d, last_xt = d_, -1
            if tms[pos] <= last_xt:
                continue
            keep[k_n] = pos
            k_n += 1
            last_xt = xts[pos]
        if k_n < 35:
            return None
        keep = keep[:k_n]
        idxs, pnls, xts = idxs[keep], pnls[keep], xts[keep]

    # Sort por date, xt, tm (em df ordenado por date, tm, basta sort estável em (date_rank, xt) ou np.lexsort)
    order = np.lexsort((tm_vals[idxs], xts, idxs))  # wait: idxs já preserva date, mas dates difere; usa dates_arr[idxs]
    # Na verdade date já é monotônico em idxs! Então basta só ordenar dentro de cada dia? Não, lexsort com dts é rápido (~5µs p/ n=200)
    order = np.lexsort((tm_vals[idxs], xts, dates_arr[idxs]))
    p = pnls[order]
    sel = idxs[order]

    eq = np.cumsum(p)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    dd = float(np.max(peak - eq))
    net = float(eq[-1])
    if net <= 0 or dd <= 0:
        return None
    rdd = net / dd
    if rdd < 2.2:
        return None

    h1 = float(p[is_h1_all[sel]].sum())
    h2 = float(p[is_h2_all[sel]].sum())
    oos = float(p[is_oos_all[sel]].sum())
    gains = float(p[p > 0].sum())
    losses = float(-p[p < 0].sum())
    pf = gains / losses if losses > 0 else 99.0
    wr = 100.0 * float((p > 0).mean())
    m_sum = np.bincount(mon_codes[sel], weights=p, minlength=n_mon)
    m_cnt = np.bincount(mon_codes[sel], minlength=n_mon)
    m_pos = int(((m_sum > 0) & (m_cnt > 0)).sum())
    m_tot = int((m_cnt > 0).sum())
    return dict(
        ops=len(p), wr=round(wr, 1), pf=round(pf, 2),
        net=round(net), dd=round(dd), rdd=round(rdd, 2),
        meses=f"{m_pos}/{m_tot}",
        h1=round(h1), h2=round(h2), oos=round(oos),
        all3=(h1 > 0 and h2 > 0 and oos > 0),
    )

# Máscaras de filtros candidatos
base_groups = []
for eng in engines:
    for mode in ("CONF", "OPC"):
        m_em = (df["engine"] == eng) & (df["mode"] == mode)
        anc_sets = [
            ("ALL_ANC", np.ones(n_rows, bool)),
            ("COMMON", df["anc"] != "SEM_ANC"),
            ("EXTREMO", df["anc"] == "EXTREMO"),
            ("EXT_OR_SUP", df["anc"].isin(["EXTREMO", "SUPER"])),
            ("EXT_OR_FURO", df["anc"].isin(["EXTREMO", "FURO_WALL"])),
            ("HAS_DAY", df["has_day"]),
            ("WALL_ONLY", df["d_wall"] <= 3.5),
            ("MID_ONLY", df["d_mid"] <= 3.5),
            ("FURO_WALL", df["anc"] == "FURO_WALL"),
            ("RECLAIM", df["reclaim"]),
            ("GAMMA_LVL", (df["d_flip"] <= 5.0) | (df["d_maxg"] <= 5.0) | (df["d_ming"] <= 5.0)),
        ]
        ctx_sets = [
            ("SEM_FILTRO", np.ones(n_rows, bool)),
            ("9a16", (df["hora"] >= 9) & (df["hora"] <= 15)),
            ("10a16", (df["hora"] >= 10) & (df["hora"] <= 15)),
            ("SEM_11H", (df["hora"] != 11) & (df["hora"] <= 16)),
            ("TARDE_12_16", (df["hora"] >= 12) & (df["hora"] <= 16)),
            ("SLOPE_DN", df["slope50"] <= 0.0),
            ("SLOPE_WIN", (df["ext50"] > -0.5) & (df["slope50"] > -0.5)),
            ("EXT50_POS", df["ext50"] > 0.0),
            ("EXT50_GT03", df["ext50"] > 0.3),
            ("EXT30_POS", df["ext30"] > 0.0),
            ("MICRO", df["micro"]),
            ("CANDLE_FAV", df["candle_dir"]),
            ("LAG01", df["lag"] <= 1),
            ("WYCK_POS", df["wyck"] > 0),
            ("PASS_POS", df["pass_"] > 0),
            ("AGGR_POS", df["aggr"] > 0),
            ("FORCE_POS", df["force"] > 0),
            ("VENDA", df["dir"] == -1),
            ("COMPRA", df["dir"] == 1),
            ("WD_LT2", df["wd_ratio"] <= 2.0),
            ("WD_GT12", df["wd_ratio"] >= 1.2),
            ("EXT50_POS+NO11", (df["ext50"] > 0.0) & (df["hora"] != 11)),
            ("DAY+EXT50", df["has_day"] & (df["ext50"] > 0.0)),
            ("DAY+SLOPE_DN", df["has_day"] & (df["slope50"] <= 0.0)),
            ("DAY+10_16", df["has_day"] & (df["hora"] >= 10) & (df["hora"] <= 15)),
            ("DAY+NO11", df["has_day"] & (df["hora"] != 11)),
            ("WALL+CANDLE", (df["d_wall"] <= 4.0) & df["candle_dir"]),
            ("WALL+MICRO", (df["d_wall"] <= 4.0) & df["micro"]),
            ("WALL+EXT50", (df["d_wall"] <= 4.0) & (df["ext50"] > 0.0)),
        ]
        for aname, amask in anc_sets:
            m_ema = m_em & amask
            if m_ema.sum() < 40:
                continue
            for cname, cmask in ctx_sets:
                m_final = (m_ema & cmask).values
                if m_final.sum() >= 35:
                    base_groups.append((eng, mode, aname, cname, np.flatnonzero(m_final)))

print(f"Testing {len(base_groups)} filter groups x {n_ex} exits...")
t_eval = time.time()

hits = []
for eng, mode, aname, cname, idxs in base_groups:
    for j, ex in enumerate(exit_defs):
        m = metrics_fast(idxs, j, mgmt="UM")
        if m is not None and (m["rdd"] >= 3.2 or (m["all3"] and m["rdd"] >= 2.2)):
            hits.append(dict(eng=eng, mode=mode, anc=aname, ctx=cname, exit=ex[0], mgmt="UM", **m))

res_df = pd.DataFrame(hits)
print(f"Evaluated in {time.time()-t_eval:.1f}s | Hits (rdd>=3.2 or all3&>=2.5): {len(res_df)}")

if len(res_df):
    res_df = res_df.sort_values(["all3", "rdd", "ops"], ascending=[False, False, False])
    res_df.to_pickle(Path(__file__).resolve().parent / "phase1_hits.pkl")
    print("\n=== TOP 35 ALL-3-PERIODS POSITIVE ===")
    p3 = res_df[res_df["all3"]]
    print(p3.head(35).to_string(index=False))
    print("\n=== TOP 25 OVERALL BY RET/DD (ops >= 50) ===")
    print(res_df[res_df["ops"] >= 50].sort_values("rdd", ascending=False).head(25).to_string(index=False))
else:
    print("No hits >= 2.5 Ret/DD found in Phase 1.")
