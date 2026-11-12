"""
Sniper v2 (research/sniper2/PLANO.md): pool de entradas dos setups + filtro de divergência causal + saída própria.
Etapas: saídas e filtros por entrada → grade IS → platô → placebo → OOS uma vez (trava results/oos_log.json).
Uso: python -m research.sniper2.bt_sniper2
"""
from __future__ import annotations

import itertools
import json
import multiprocessing as mp
import os
import random
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "research", "sniper2", "results")
IS_END = "2026-07-31"
MIN_TRADES, N_PLACEBO, P_MAX = 150, 200, 0.10
SPEC = {
    "WIN": dict(sl=(200.0, 260.0), nwe_min=260.0, nwe_max=750.0, front=15.0, fixed=(450.0, 750.0), wall_min=100.0,
                be=(180.0, 20.0), cost=10.0, brl=0.20, tick=5.0, skip=("12:00", "12:55"), cap_per_ct=90.0),
    "WDO": dict(sl=(8.0, 10.5), nwe_min=5.0, nwe_max=16.0, front=0.5, fixed=(10.0, 16.0), wall_min=3.0,
                be=(7.0, 1.0), cost=0.5, brl=10.0, tick=0.5, skip=("11:00", "11:55"), cap_per_ct=120.0),
}
TPS = ("nwe30", "wall", "fixo1", "fixo2", "mix2L")


def exits(asset):
    out = [dict(name="NATIVA", sl=None, tp="nativa", be=False)]
    for sl, tp, be in itertools.product(SPEC[asset]["sl"], TPS, (False, True)):
        out.append(dict(name=f"SL{sl:g}|{tp}|{'BE' if be else 'semBE'}", sl=sl, tp=tp, be=be))
    return out


def hm(s):
    h, m = str(s).split(":")[:2]
    return int(h) * 60 + int(m)


# ───────────── barras MT5 por dia ─────────────

def day_bars(df, n30):
    out = {}
    c, u, l = n30[0], n30[1], n30[2]
    for d, idx in df.groupby("session_date").indices.items():
        idx = np.sort(idx)
        prev = idx[0] - 1 if idx[0] > 0 else idx[0]
        out[str(d)] = dict(o=df["open"].values[idx], h=df["high"].values[idx], lo=df["low"].values[idx],
                           c=df["close"].values[idx], tm=df["t_min"].values[idx].astype(int),
                           up=np.r_[u[prev], u[idx][:-1]], dn=np.r_[l[prev], l[idx][:-1]])  # banda da barra ANTERIOR
    return out


def rnd(x, tick):
    return round(x / tick) * tick


def sim_lot(b, e, ep, d, sl, tp_kind, tp_fixed, be, sp, levels):
    """Um lote. Barra de entrada: só stop. Depois: stop antes do alvo; gap preenche na abertura; BE na abertura seguinte."""
    n = len(b["o"])
    stop = ep - d * sl
    be_on = False
    mfe = 0.0

    def target(k):
        if tp_kind == "nwe30":
            raw = (b["up"][k] if d == 1 else b["dn"][k]) - d * sp["front"]
            lo_, hi_ = (ep + sp["nwe_min"], ep + sp["nwe_max"]) if d == 1 else (ep - sp["nwe_max"], ep - sp["nwe_min"])
            return rnd(min(max(raw, lo_), hi_), sp["tick"])
        return tp_fixed

    if (d == 1 and b["lo"][e] <= stop) or (d == -1 and b["h"][e] >= stop):
        return (stop - ep) * d, b["tm"][e]
    for k in range(e + 1, n):
        o, h, lo, c, tm = b["o"][k], b["h"][k], b["lo"][k], b["c"][k], b["tm"][k]
        if tm >= 1045:  # 17:25
            return (o - ep) * d, tm
        tp = target(k)
        if (d == 1 and lo <= stop) or (d == -1 and h >= stop):
            fill = o if (o - stop) * d <= 0 else stop
            return (fill - ep) * d, tm
        if (d == 1 and h >= tp) or (d == -1 and lo <= tp):
            fill = o if (o - tp) * d >= 0 else tp
            return (fill - ep) * d, tm
        mfe = max(mfe, (h - ep) if d == 1 else (ep - lo))
        if be and not be_on and mfe >= sp["be"][0] and k + 1 < n:
            cand = ep + d * sp["be"][1]
            if (b["o"][k + 1] - cand) * d > 0 and (cand - stop) * d > 0:
                stop, be_on = cand, True
        if k - e >= 24:
            return (c - ep) * d, tm
    return (b["c"][n - 1] - ep) * d, b["tm"][n - 1]


def sim_exit(asset, b, e, ep, d, x, levels):
    sp = SPEC[asset]
    lv = [v for v in levels if (v - ep) * d >= sp["wall_min"]]
    wall_tp = (min(lv) if d == 1 else max(lv)) - d * sp["tick"] if lv else ep + d * sp["fixed"][1]
    fx = {"wall": wall_tp, "fixo1": ep + d * sp["fixed"][0], "fixo2": ep + d * sp["fixed"][1]}
    if x["tp"] == "mix2L":
        p1, t1 = sim_lot(b, e, ep, d, x["sl"], "nwe30", None, x["be"], sp, levels)
        p2, t2 = sim_lot(b, e, ep, d, x["sl"], "fixed", fx["fixo2"], x["be"], sp, levels)
        return (p1 + p2 - 2 * sp["cost"]) * sp["brl"], max(t1, t2)
    p, t = sim_lot(b, e, ep, d, x["sl"], x["tp"], fx.get(x["tp"]), x["be"], sp, levels)
    return (p - sp["cost"]) * sp["brl"], t


# ───────────── filtros de divergência ─────────────

def sniper_signals(asset):
    """Detector do Sniper 5176 sobre as barras do dataset (mesma onda), por dia: lista (idx, dir, near_wall)."""
    from research.flow_window_asg.inject_unified_div_opt2 import detect_visual_swing_divergences
    from research.div_gate.build_gate import days_with_warm
    from core.div_wall_signal import compute_flow
    out = {}
    for d, (bars, walls, _, _) in days_with_warm(asset).items():
        fb = compute_flow(bars, asset)
        ad = [dict(b, smart_swing_wave=b["wave"], wyckoff_abs_bar=b["wyckoff_abs"], effective_force_bar=b["force"])
              for b in fb]
        ws = [w for w in walls if w["type"] in ("Wall", "MidWall")]
        sigs = detect_visual_swing_divergences(ad, ws, asset == "WIN")
        out[d] = (sigs, {b["time"]: i for i, b in enumerate(bars)})
    return out


def filters(asset, P):
    from research.div_gate import gate as G
    F = {"F0": np.ones(len(P), bool)}
    sn = sniper_signals(asset)
    for tol, wall in itertools.product((1, 2, 3), (False, True)):
        m = np.zeros(len(P), bool)
        for r in P.itertuples():
            sigs, tmap = sn.get(r.date, ([], {}))
            bi = tmap.get(r.time)
            if bi is None:
                continue
            m[r.Index] = any(s["dir"] == r.direction and bi - tol - 1 <= s["sig_idx"] <= bi - 1 and (s["near_wall"] or not wall)
                             for s in sigs)
        F[f"F1|tol{tol}|{'wall' if wall else 'livre'}"] = m
    tab, _ = G.load_table(asset)
    for cfg in G.cfgs(asset):
        t = tab[cfg]
        for ni, N in enumerate(G.JANELAS):
            bit = {1: 1 << (2 * ni), -1: 1 << (2 * ni + 1)}
            m = np.array([bool(t.get((r.date, hm(r.time) - 5), 0) & bit[r.direction]) for r in P.itertuples()])
            k, R, L, cf = cfg
            F[f"F2|k{k}|R{R:g}|L{L}|{cf}|N{N}"] = m
    return F


# ───────────── gestão e métricas ─────────────

def apply_mgmt(sel, P, pnl, xt, asset, skip, cap, mode, contracts):
    """sel: índices (ordenados por data/hora). Retorna índices aceitos."""
    sp = SPEC[asset]
    s0, s1 = hm(sp["skip"][0]), hm(sp["skip"][1])
    if not skip and not cap and mode == "LIVRE":
        return sel
    acc, day, last_exit, done = [], None, -1, []
    tmins, dates = P["tm"].values, P["date"].values
    for i in sel:
        if dates[i] != day:
            day, last_exit, done = dates[i], -1, []
        tm = tmins[i]
        if skip and s0 <= tm <= s1:
            continue
        if mode == "UM_POR_VEZ" and tm <= last_exit:
            continue
        if cap and sum(pnl[j] for j in done if xt[j] < tm) >= sp["cap_per_ct"] * contracts:
            continue
        acc.append(i)
        done.append(i)
        last_exit = max(last_exit, xt[i])
    return np.array(acc, dtype=int)


def stats(idx, P, pnl, xt):
    if len(idx) == 0:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, mdd=0.0, ret_dd=0.0, pos_m="0/0")
    o = np.lexsort((xt[idx], P["di"].values[idx]))
    p = pnl[idx][o]
    eq = np.cumsum(p)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = pd.Series(pnl[idx]).groupby(P["month"].values[idx]).sum()
    return dict(ops=int(len(idx)), wr=round(100 * float((p > 0).mean()), 1), pf=round(float(g / l), 2) if l else 99.0,
                net=round(float(eq[-1]), 0), mdd=round(mdd, 0), ret_dd=round(float(eq[-1]) / mdd, 2) if mdd else 99.0,
                pos_m=f"{int((m > 0).sum())}/{len(m)}")


def score(s):
    return s["ret_dd"] if (s["ops"] >= MIN_TRADES and s["net"] > 0) else 0.0


# ───────────── preparo por ativo ─────────────

def prepare(asset, pool_kind="sem_fluxo"):
    from research.div_gate import bt_gate_grid as B
    from research.div_gate import select_oos as SO
    SO._init_full()
    df_win, gex_win, _, n30w, _, df_wdo, gex_wdo, _, n30d, _ = B._MK
    df, gex, n30 = (df_win, gex_win, n30w) if asset == "WIN" else (df_wdo, gex_wdo, n30d)
    bars = day_bars(df, n30)
    P = pd.read_csv(os.path.join(OUT, f"pool_{asset}{'_fluxo' if pool_kind == 'com_fluxo' else ''}.csv"))
    P = P[~P["dup"]].copy()
    P["tm"] = P["time"].map(hm)
    P = P[P["date"].isin(bars.keys())].sort_values(["date", "tm"]).reset_index(drop=True)
    P["month"] = P["date"].str[:7]
    P["di"] = pd.factorize(P["date"], sort=True)[0]
    X = exits(asset)
    pnl = np.zeros((len(P), len(X)))
    xt = np.zeros((len(P), len(X)), dtype=int)
    keep = np.ones(len(P), bool)
    for r in P.itertuples():
        b = bars[r.date]
        e = np.where(b["tm"] == r.tm)[0]
        if not len(e):
            keep[r.Index] = False
            continue
        e = int(e[0])
        g = gex.get(r.date, {})
        levels = sorted(list(np.asarray(g.get("walls", []), float)) + list(np.asarray(g.get("mid_walls", []), float)))
        for xi, x in enumerate(X):
            if x["tp"] == "nativa":
                pnl[r.Index, xi] = r.native_brl
                xt[r.Index, xi] = hm(r.native_exit) if isinstance(r.native_exit, str) and ":" in r.native_exit else r.tm
            else:
                pnl[r.Index, xi], xt[r.Index, xi] = sim_exit(asset, b, e, r.entry_price, r.direction, x, levels)
    P, pnl, xt = P[keep].reset_index(drop=True), pnl[keep], xt[keep]
    P["di"] = pd.factorize(P["date"], sort=True)[0]
    F = filters(asset, P)
    return P, X, pnl, xt, F


def plateau(G, asset):
    ords = {"tol": [1, 2, 3], "k": [0.5, 1.0, 1.5], "R": sorted(set(G["R"].dropna())), "L": [30, 50, 80, 100],
            "N": [3, 6, 12], "sl": list(SPEC[asset]["sl"])}
    key_cols = ["fam", "tol", "wall", "k", "R", "L", "conf", "N", "sl", "tp", "be", "skip", "cap", "mode"]
    idx = {tuple(r[c] for c in key_cols): r["score"] for _, r in G.iterrows()}
    out = []
    for _, r in G.iterrows():
        vals = [r["score"]]
        params = {"F0": [], "F1": ["tol"], "F2": ["k", "R", "L", "N"]}[r["fam"]] + (["sl"] if r["tp"] != "nativa" else [])
        for p in params:
            seq = ords[p]
            j = seq.index(r[p])
            for jj in (j - 1, j + 1):
                if 0 <= jj < len(seq):
                    nb = dict(r)
                    nb[p] = seq[jj]
                    key = tuple(nb[c] for c in key_cols)
                    if key in idx:
                        vals.append(idx[key])
        out.append(float(np.median(vals)))
    G = G.copy()
    G["plateau"] = out
    return G


def parse_filter(fn):
    p = fn.split("|")
    base = dict(fam=p[0], tol=0, wall="", k=0.0, R=0.0, L=0, conf="", N=0)
    if p[0] == "F1":
        base.update(tol=int(p[1][3:]), wall=p[2])
    elif p[0] == "F2":
        base.update(k=float(p[1][1:]), R=float(p[2][1:]), L=int(p[3][1:]), conf=p[4], N=int(p[5][1:]))
    return base


def run_is(args):
    asset, pool_kind = args
    t0 = datetime.now()
    P, X, pnl, xt, F = prepare(asset, pool_kind)
    is_mask = (P["date"] <= IS_END).values
    print(f"{asset}: {len(P)} entradas ({int(is_mask.sum())} IS) · {len(F)} filtros · {len(X)} saídas · preparo {datetime.now() - t0}", flush=True)
    rows = []
    for fn, m in F.items():
        sel = np.where(m & is_mask)[0]
        fp = parse_filter(fn)
        for xi, x in enumerate(X):
            ct = 2 if x["tp"] == "mix2L" else 1
            for skip, cap, mode in itertools.product((False, True), (False, True), ("LIVRE", "UM_POR_VEZ")):
                acc = apply_mgmt(sel, P, pnl[:, xi], xt[:, xi], asset, skip, cap, mode, ct)
                s = stats(acc, P, pnl[:, xi], xt[:, xi])
                rows.append(dict(asset=asset, pool=pool_kind, filtro=fn, **fp, saida=x["name"], xi=xi, sl=x["sl"] or 0.0, tp=x["tp"],
                                 be=x["be"], skip=skip, cap=cap, mode=mode, **s, score=score(s)))
    G = plateau(pd.DataFrame(rows), asset)
    G.to_csv(os.path.join(OUT, f"grid_is_{asset}_{pool_kind}.csv"), index=False)
    print(f"{asset}: grade IS {len(G)} linhas · {datetime.now() - t0}", flush=True)
    picks = {}
    for label, g in (("melhor_com_div", G[G["fam"] != "F0"]), ("melhor_sem_div", G[G["fam"] == "F0"])):
        top = g.sort_values(["plateau", "ops"], ascending=False).iloc[0]
        picks[label] = top.to_dict()
    # placebo para a escolha com divergência
    top = picks["melhor_com_div"]
    xi = int(top["xi"])
    ct = 2 if X[xi]["tp"] == "mix2L" else 1
    sel = np.where(F[top["filtro"]] & is_mask)[0]
    want = defaultdict(int)
    for i in sel:
        want[(P["month"].values[i], int(P["direction"].values[i]))] += 1
    pool = defaultdict(list)
    for i in np.where(is_mask)[0]:
        pool[(P["month"].values[i], int(P["direction"].values[i]))].append(i)
    rng = random.Random(7)
    pl = []
    for _ in range(N_PLACEBO):
        pick = sorted(j for kk, n in want.items() for j in rng.sample(pool[kk], min(n, len(pool[kk]))))
        acc = apply_mgmt(np.array(pick, dtype=int), P, pnl[:, xi], xt[:, xi], asset, top["skip"], top["cap"], top["mode"], ct)
        pl.append(stats(acc, P, pnl[:, xi], xt[:, xi])["ret_dd"])
    p = (1 + sum(v >= top["ret_dd"] for v in pl)) / (1 + len(pl))
    picks["melhor_com_div"].update(placebo_p=p, placebo_med=float(np.median(pl)), ok_is=bool(top["plateau"] > 0 and p < P_MAX))
    print(f"{asset} {pool_kind}: escolha com divergência {top['filtro']} {top['saida']} skip={top['skip']} cap={top['cap']} {top['mode']} "
          f"platô {top['plateau']:.2f} ponto {top['ret_dd']:.2f} ({top['ops']} tr) · placebo med {np.median(pl):.2f} p={p:.3f}", flush=True)
    t = picks["melhor_sem_div"]
    print(f"{asset} {pool_kind}: melhor SEM divergência {t['saida']} skip={t['skip']} cap={t['cap']} {t['mode']} platô {t['plateau']:.2f} "
          f"ponto {t['ret_dd']:.2f} ({t['ops']} tr)", flush=True)
    return (asset, pool_kind), picks


def run_oos(args):
    (asset, pool_kind), picks = args
    P, X, pnl, xt, F = prepare(asset, pool_kind)
    out, trades = {}, []
    for label, top in picks.items():
        xi = int(top["xi"])
        ct = 2 if X[xi]["tp"] == "mix2L" else 1
        res = {}
        for part, msk in (("is", (P["date"] <= IS_END).values), ("oos", (P["date"] > IS_END).values)):
            sel = np.where(F[top["filtro"]] & msk)[0]
            acc = apply_mgmt(sel, P, pnl[:, xi], xt[:, xi], asset, top["skip"], top["cap"], top["mode"], ct)
            res[part] = stats(acc, P, pnl[:, xi], xt[:, xi])
            trades += [dict(asset=asset, pool=pool_kind, escolha=label, part=part, date=P["date"].values[i], time=P["time"].values[i],
                            direction=int(P["direction"].values[i]), vid=P["vid"].values[i], brl=float(pnl[i, xi]),
                            exit_tm=int(xt[i, xi])) for i in acc]
        o = res["oos"]
        n_pos, n_m = map(int, o["pos_m"].split("/"))
        res["aprovado_oos"] = bool(o["pf"] >= 1.3 and o["net"] > 0 and n_pos >= 3 and (label != "melhor_com_div" or top.get("ok_is")))
        out[label] = res
    return f"{asset}|{pool_kind}", out, trades


def main():
    os.makedirs(OUT, exist_ok=True)
    lock = os.path.join(OUT, "oos_log.json")
    if os.path.exists(lock):
        raise SystemExit("OOS já executado.")
    keys = [(a, k) for a in ("WIN", "WDO") for k in ("sem_fluxo", "com_fluxo")]
    with mp.Pool(4) as pool:
        picks = dict(pool.map(run_is, keys))
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"),
               "picks": {f"{a}|{k}": v for (a, k), v in picks.items()}},
              open(lock, "w", encoding="utf-8"), indent=1, default=str)
    with mp.Pool(4) as pool:
        res = pool.map(run_oos, [(k, picks[k]) for k in keys])
    allres, trades = {}, []
    for a, o, t in res:
        allres[a] = o
        trades += t
    T = pd.DataFrame(trades)
    T.to_csv(os.path.join(OUT, "oos_trades.csv"), index=False)
    log = json.load(open(lock, encoding="utf-8"))
    log["result"] = allres
    json.dump(log, open(lock, "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(allres, indent=1, default=str))


if __name__ == "__main__":
    main()
