"""
Setup Divergência 3 Motores — teste do PLANO.md com saídas simuladas tick a tick em barras M1 (mesma ordem de ticks do
Strategy Tester "OHLC 1 minuto": O→H→L→C ou O→L→H→C). Sem M1 no dia (WDO antes de 25/02): barra M5 com stop primeiro.
Uso: python -m research.div3m.bt_div3m
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

import numba as nb
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div3m import investigar as INV  # noqa: E402

OUT = os.path.join(ROOT, "research", "div3m", "results")
IS_END, H1_END, END = "2026-07-31", "2026-04-30", "2026-11-06"
MIN_TRADES, N_PLACEBO, P_MAX = 150, 200, 0.10
SPEC = {
    "WIN": dict(tick=5.0, cost=10.0, brl=0.20, stops=(("fixo", 200.0), ("fixo", 260.0), ("piv", 30.0)), piv_clip=(100.0, 300.0),
                fixed=(450.0, 750.0), min_tp=100.0, cap=90.0, sym="WIN$N"),
    "WDO": dict(tick=0.5, cost=0.5, brl=10.0, stops=(("fixo", 8.0), ("fixo", 10.5), ("piv", 1.0)), piv_clip=(3.0, 12.0),
                fixed=(10.0, 16.0), min_tp=3.0, cap=120.0, sym="WDO$N"),
}
FILTROS = ("NWE", "TEND", "PA", "PERSEG", "FLUXO", "HORA", "SEQ")
COMBOS = [c for n in range(4) for c in itertools.combinations(FILTROS, n)]
ENTRADAS = ("E0_abertura", "E1_rompimento", "E2_limite_meio", "E3_confirmacao")
TPS = ("centro50", "oposta50", "fixo1", "fixo2", "2lotes")


def exits(asset):
    sp = SPEC[asset]
    return [dict(stop=s, tp=tp, be=be, trail=tr, tmax=tm)
            for s, tp, be, tr, tm in itertools.product(sp["stops"], TPS, (False, True), (False, True), (24, 48))]


def xname(x, asset):
    sp = SPEC[asset]
    s = f"SL {x['stop'][1]:g}" if x["stop"][0] == "fixo" else f"SL pivô+{x['stop'][1]:g}"
    tp = {"centro50": "alvo centro NWE50", "oposta50": "alvo banda oposta NWE50", "fixo1": f"alvo {sp['fixed'][0]:g}",
          "fixo2": f"alvo {sp['fixed'][1]:g}", "2lotes": f"2 lotes (centro NWE50 + {sp['fixed'][1]:g})"}[x["tp"]]
    return f"{s} · {tp} · {'BE 1R' if x['be'] else 'sem BE'} · {'trailing NWE30' if x['trail'] else 'sem trailing'} · máx {x['tmax']} barras"


# ───────────────────────── simulação tick a tick ─────────────────────────

@nb.njit(cache=True)
def _tick(px, isop, off, fb, o5, h5, l5, c5, k, j, d):
    """j-ésimo tick da barra M5 k (M1 se houver; senão O, extremo contra, extremo a favor, C)."""
    if fb[k] == 0:
        return px[off[k] + j], isop[off[k] + j]
    if j == 0:
        return o5[k], True
    if j == 1:
        return (l5[k] if d == 1 else h5[k]), False
    if j == 2:
        return (h5[k] if d == 1 else l5[k]), False
    return c5[k], False


@nb.njit(cache=True)
def sim(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, c50, u50, l50, u30, l30,
        e, j0, ep, d, sl, tpk, tpfix, be, trail, tmax, min_tp, be_lock):
    n5 = len(o5)
    stop = ep - d * sl
    mfe = 0.0
    be_on = False
    for k in range(e, n5):
        if k > e:
            if tm5[k] >= 1045 or k - e >= tmax:
                return (o5[k] - ep) * d, tm5[k]
            if be and (not be_on) and mfe >= sl:
                cand = ep + d * be_lock
                if (o5[k] - cand) * d > 0 and (cand - stop) * d > 0:
                    stop = cand
                    be_on = True
            if trail:
                band = l30[k] if d == 1 else u30[k]
                if (band - stop) * d > 0 and (o5[k] - band) * d > 0:
                    stop = band
        if tpk == 0:
            tp = c50[k]
        elif tpk == 1:
            tp = u50[k] if d == 1 else l50[k]
        else:
            tp = tpfix
        if (tp - ep) * d < min_tp:
            tp = ep + d * min_tp
        nt = nn[k] if fb[k] == 0 else 4
        for j in range(j0 if k == e else 0, nt):
            p, op = _tick(px, isop, off, fb, o5, h5, l5, c5, k, j, d)
            if (p - stop) * d <= 0:
                return ((p if op else stop) - ep) * d, tm5[k]
            if (p - tp) * d >= 0:
                return ((p if op else tp) - ep) * d, tm5[k]
            if (p - ep) * d > mfe:
                mfe = (p - ep) * d
    return (c5[n5 - 1] - ep) * d, tm5[n5 - 1]


def day_struct(asset, df, nwe, mt5, m1):
    """Por dia: arrays M5 (com NWE da barra anterior) e ticks M1 achatados por barra M5."""
    from research.discover_gex_nwe_setups import compute_nwe_series
    closes = df["close"].values.astype(float)
    c30, u30g, l30g = compute_nwe_series(closes, 30, 8.0, 3.0)[:3]
    c50, u50, l50 = nwe[50]
    out = {}
    m1g = {d: g for d, g in m1.groupby("session_date")}
    for d, idx in df.groupby("session_date").indices.items():
        d = str(d)
        if d not in mt5:
            continue
        idx = np.sort(idx)
        pv = np.maximum(idx - 1, 0)
        b = mt5[d]
        tm5 = b["tm"].astype(np.int64)
        g = m1g.get(d)
        px, op, off, nn, fb = [], [], np.zeros(len(tm5), np.int64), np.zeros(len(tm5), np.int64), np.ones(len(tm5), np.int64)
        if g is not None:
            mm = g["t_min"].values
            o1, h1, l1, c1 = (g[c].values.astype(float) for c in ("open", "high", "low", "close"))
            for k, t in enumerate(tm5):
                sel = np.where((mm >= t) & (mm < t + 5))[0]
                off[k] = len(px)
                if len(sel) == 0:
                    continue
                fb[k] = 0
                for s in sel:
                    tk = INV_ticks(o1[s], h1[s], l1[s], c1[s])
                    for q, v in enumerate(tk):
                        px.append(v)
                        op.append(q == 0)
                nn[k] = len(px) - off[k]
        out[d] = dict(px=np.array(px, float), op=np.array(op, bool), off=off, nn=nn, fb=fb,
                      o5=b["o"].astype(float), h5=b["h"].astype(float), l5=b["lo"].astype(float), c5=b["c"].astype(float),
                      tm5=tm5, c50=c50[pv], u50=u50[pv], l50=l50[pv], u30=u30g[pv], l30=l30g[pv])
    return out


def INV_ticks(o, h, l, c):
    return (o, h, l, c) if abs(h - o) <= abs(o - l) else (o, l, h, c)


def ticks_py(D, k, d):
    if D["fb"][k] == 0:
        a, n = D["off"][k], D["nn"][k]
        return list(zip(D["px"][a:a + n], D["op"][a:a + n]))
    return [(D["o5"][k], True), (D["l5"][k] if d == 1 else D["h5"][k], False),
            (D["h5"][k] if d == 1 else D["l5"][k], False), (D["c5"][k], False)]


def fill(D, entry, e, d, sig_hi, sig_lo, tick):
    """(barra, tick inicial, preço) da entrada, ou None."""
    n5 = len(D["o5"])
    if entry == "E0_abertura":
        return e, 0, ticks_py(D, e, d)[0][0]
    if entry == "E3_confirmacao":
        if e + 1 < n5 and d * (D["c5"][e] - D["o5"][e]) > 0:
            return e + 1, 0, ticks_py(D, e + 1, d)[0][0]
        return None
    if entry == "E1_rompimento":
        trig = sig_hi + tick if d == 1 else sig_lo - tick
        for k in range(e, min(e + 2, n5)):
            for j, (p, op) in enumerate(ticks_py(D, k, d)):
                if (p - trig) * d >= 0:
                    return k, j, (p if op else trig)
        return None
    lim = np.round(((sig_hi + sig_lo) / 2) / tick) * tick
    for k in range(e, min(e + 3, n5)):
        for j, (p, op) in enumerate(ticks_py(D, k, d)):
            if (p - lim) * d <= 0:
                return k, j, (p if op else lim)
    return None


def run_trade(D, k, j, ep, d, piv, x, asset, force_fb=False):
    sp = SPEC[asset]
    if x["stop"][0] == "fixo":
        sl = x["stop"][1]
    else:
        lo, hi = sp["piv_clip"]
        sl = float(np.clip(d * (ep - piv) + x["stop"][1], lo, hi))
    fb = np.ones_like(D["fb"]) if force_fb else D["fb"]
    j = 0 if (force_fb and D["fb"][k] == 0 and j > 0) else j
    args = (D["px"], D["op"], D["off"], D["nn"], fb, D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"],
            D["c50"], D["u50"], D["l50"], D["u30"], D["l30"])
    if x["tp"] == "2lotes":
        p1, t1 = sim(*args, k, j, ep, d, sl, 0, 0.0, x["be"], x["trail"], x["tmax"], sp["min_tp"], sp["cost"])
        p2, t2 = sim(*args, k, j, ep, d, sl, 2, ep + d * sp["fixed"][1], x["be"], x["trail"], x["tmax"], sp["min_tp"], sp["cost"])
        return (p1 + p2 - 2 * sp["cost"]) * sp["brl"], max(t1, t2)
    tpk = {"centro50": 0, "oposta50": 1, "fixo1": 2, "fixo2": 2}[x["tp"]]
    tpf = ep + d * (sp["fixed"][0] if x["tp"] == "fixo1" else sp["fixed"][1])
    p, t = sim(*args, k, j, ep, d, sl, tpk, tpf, x["be"], x["trail"], x["tmax"], sp["min_tp"], sp["cost"])
    return (p - sp["cost"]) * sp["brl"], t


# ───────────────────────── filtros, gestão, métricas ─────────────────────────

def filter_flags(P, asset):
    F = pd.DataFrame(index=P.index)
    if asset == "WIN":
        F["NWE"] = (P.ext80 > 0.0994) & (P.ext80 <= 0.412)
        F["PA"] = (P.wick >= 0.46) & (P.range_atr <= 1.2)
        F["FLUXO"] = (P.inst <= 5026.25) & (P.ret <= 2160.0)
    else:
        F["NWE"] = P.ext80 > 0.249
        F["PA"] = P.body_fav == 0
        F["FLUXO"] = P.ret <= -34.0
    F["TEND"] = P.slope50 > -1.0
    F["PERSEG"] = P.dist_piv <= 1.0
    F["HORA"] = P.hora != "09h"
    F["SEQ"] = P.seq >= 1
    return F


def mgmt(sel, tm, day, pnl, xt, mode, cap, cap_val):
    if mode == "LIVRE" and not cap:
        return sel
    acc, cur, last, done = [], -1, -1, []
    for i in sel:
        if day[i] != cur:
            cur, last, done = day[i], -1, []
        t = tm[i]
        if mode == "UM_POR_VEZ" and t <= last:
            continue
        if cap and sum(pnl[q] for q in done if xt[q] < t) >= cap_val:
            continue
        acc.append(i)
        done.append(i)
        last = max(last, xt[i])
    return np.array(acc, dtype=int)


def st(idx, pnl, day, mon, h1):
    if len(idx) == 0:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, rdd=0.0, meses="0/0", net_h1=0.0, net_h2=0.0)
    p = pnl[idx]
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mm = np.bincount(mon[idx], weights=p, minlength=12)
    used = np.bincount(mon[idx], minlength=12) > 0
    hh = h1[idx]
    return dict(ops=int(len(idx)), wr=round(100 * float((p > 0).mean()), 1), pf=round(float(g / l), 2) if l else 99.0,
                net=round(float(eq[-1])), dd=round(dd), rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
                meses=f"{int((mm[used] > 0).sum())}/{int(used.sum())}", net_h1=round(float(p[hh].sum())), net_h2=round(float(p[~hh].sum())))


def score(s):
    return s["rdd"] if (s["ops"] >= MIN_TRADES and s["net"] > 0 and s["net_h1"] > 0 and s["net_h2"] > 0) else 0.0


# ───────────────────────── preparo ─────────────────────────

def prepare(asset):
    from research.mt5_loader import get_mt5_rates
    t0 = datetime.now()
    P, mt5, df, nwe, _ = INV.load(asset, end=END)
    P = P.reset_index(drop=True)
    m1 = get_mt5_rates(SPEC[asset]["sym"], "M1", since="2025-12-01").copy()
    m1["session_date"] = m1["t"].dt.strftime("%Y-%m-%d")
    m1["t_min"] = m1["t"].dt.hour * 60 + m1["t"].dt.minute
    DS = day_struct(asset, df.reset_index(drop=True), nwe, mt5, m1)
    F = filter_flags(P, asset)
    X = exits(asset)
    sp = SPEC[asset]
    E = {}
    for en in ENTRADAS:
        rows, pn, xt = [], [], []
        for r in P.itertuples():
            D = DS[r.date]
            f = fill(D, en, r.e, r.direction, r.sig_hi, r.sig_lo, sp["tick"])
            if f is None:
                continue
            k, j, ep = f
            res = [run_trade(D, k, j, ep, r.direction, r.piv, x, asset) for x in X]
            rows.append(dict(sig=r.Index, date=r.date, tm=int(D["tm5"][k]), direction=r.direction, k=k, j=j, ep=ep,
                             piv=r.piv, m1=int(D["fb"][k] == 0)))
            pn.append([a for a, _ in res])
            xt.append([b for _, b in res])
        T = pd.DataFrame(rows)
        o = np.lexsort((T.tm.values, T.date.values))
        T = T.iloc[o].reset_index(drop=True)
        pn, xt = np.array(pn)[o], np.array(xt, dtype=int)[o]
        T["di"] = pd.factorize(T.date, sort=True)[0]
        T["mon"] = T.date.str[5:7].astype(int) - 1
        T["is"] = T.date <= IS_END
        T["h1"] = T.date <= H1_END
        E[en] = (T, pn, xt)
    print(f"{asset}: {len(P)} divergências · preparo {datetime.now() - t0}", flush=True)
    return P, F, X, E, DS, mt5


def run(asset):
    P, F, X, E, DS, mt5 = prepare(asset)
    sp = SPEC[asset]
    t0 = datetime.now()
    rows = []
    for en, (T, pn, xt) in E.items():
        FT = F.loc[T.sig.values].reset_index(drop=True)
        isv = T["is"].values
        day, mon, h1, tm = T.di.values, T.mon.values, T.h1.values, T.tm.values
        for combo in COMBOS:
            m = isv.copy()
            for c in combo:
                m &= FT[c].values
            sel = np.where(m)[0]
            for xi, x in enumerate(X):
                ct = 2 if x["tp"] == "2lotes" else 1
                for mode, cap in itertools.product(("LIVRE", "UM_POR_VEZ"), (False, True)):
                    acc = mgmt(sel, tm, day, pn[:, xi], xt[:, xi], mode, cap, sp["cap"] * ct)
                    s = st(acc, pn[:, xi], day, mon, h1)
                    rows.append(dict(asset=asset, entrada=en, filtros="+".join(combo) or "nenhum", n_f=len(combo), xi=xi,
                                     stop=f"{x['stop'][0]}{x['stop'][1]:g}", tp=x["tp"], be=x["be"], trail=x["trail"],
                                     tmax=x["tmax"], mode=mode, cap=cap, **s, score=score(s)))
    G = pd.DataFrame(rows)
    print(f"{asset}: grade {len(G)} · {datetime.now() - t0}", flush=True)
    # platô
    key = ["entrada", "filtros", "stop", "tp", "be", "trail", "tmax", "mode", "cap"]
    idx = {tuple(r): s for r, s in zip(G[key].itertuples(index=False, name=None), G.score.values)}
    stops = [f"{a}{b:g}" for a, b in sp["stops"]]
    plat = []
    for r in G[key + ["score"]].itertuples(index=False, name=None):
        r = list(r)
        vals = [r[-1]]
        fs = set() if r[1] == "nenhum" else set(r[1].split("+"))
        neigh = []
        for f in FILTROS:
            nfs = fs ^ {f}
            if len(nfs) <= 3:
                neigh.append(("filtros", "+".join([c for c in FILTROS if c in nfs]) or "nenhum"))
        si = stops.index(r[2])
        for sj in (si - 1, si + 1):
            if 0 <= sj < len(stops):
                neigh.append(("stop", stops[sj]))
        neigh.append(("tmax", 72 - r[6]))
        for col, v in neigh:
            rr = list(r[:-1])
            rr[key.index(col)] = v
            if tuple(rr) in idx:
                vals.append(idx[tuple(rr)])
        plat.append(float(np.median(vals)))
    G["plateau"] = plat
    G.to_csv(os.path.join(OUT, f"grid_is_{asset}.csv.gz"), index=False, compression="gzip")
    G = G.sort_values(["plateau", "score", "ops"], ascending=False)
    top = G.iloc[0].to_dict()
    # placebos
    T, pn, xt = E[top["entrada"]]
    xi = int(top["xi"])
    x = X[xi]
    ct = 2 if x["tp"] == "2lotes" else 1
    FT = F.loc[T.sig.values].reset_index(drop=True)
    isv = T["is"].values
    m = isv.copy()
    for c in ([] if top["filtros"] == "nenhum" else top["filtros"].split("+")):
        m &= FT[c].values
    sel = np.where(m)[0]
    want = defaultdict(int)
    for i in sel:
        want[(T.mon.values[i], T.direction.values[i])] += 1
    pool = defaultdict(list)
    for i in np.where(isv)[0]:
        pool[(T.mon.values[i], T.direction.values[i])].append(i)
    rng = random.Random(7)
    pa = []
    for _ in range(N_PLACEBO):
        pick = np.array(sorted(j for kk, n in want.items() for j in rng.sample(pool[kk], min(n, len(pool[kk])))), dtype=int)
        acc = mgmt(pick, T.tm.values, T.di.values, pn[:, xi], xt[:, xi], top["mode"], top["cap"], sp["cap"] * ct)
        pa.append(st(acc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)["rdd"])
    # (b) barras quaisquer do IS como "sinal"
    lo_w, hi_w = INV.WINDOW[asset]
    br = []
    for dte, D in DS.items():
        if dte > IS_END:
            continue
        for i in range(len(D["o5"]) - 1):
            if not (lo_w <= D["tm5"][i + 1] <= hi_w):
                continue
            for dirn in (1, -1):
                f = fill(D, top["entrada"], i + 1, dirn, D["h5"][i], D["l5"][i], sp["tick"])
                if f is None:
                    continue
                k, j, ep = f
                piv = D["l5"][i] if dirn == 1 else D["h5"][i]
                p_, t_ = run_trade(D, k, j, ep, dirn, piv, x, asset)
                br.append((dte, int(D["tm5"][k]), dirn, p_, t_))
    B = pd.DataFrame(br, columns=["date", "tm", "direction", "pnl", "xt"]).sort_values(["date", "tm"]).reset_index(drop=True)
    B["di"] = pd.factorize(B.date, sort=True)[0]
    B["mon"] = B.date.str[5:7].astype(int) - 1
    B["h1"] = B.date <= H1_END
    bpool = defaultdict(list)
    for i, (mo, dr) in enumerate(zip(B.mon.values, B.direction.values)):
        bpool[(mo, dr)].append(i)
    pb = []
    for _ in range(N_PLACEBO):
        pick = np.array(sorted(j for kk, n in want.items() for j in rng.sample(bpool[kk], min(n, len(bpool[kk])))), dtype=int)
        acc = mgmt(pick, B.tm.values, B.di.values, B.pnl.values, B.xt.values.astype(int), top["mode"], top["cap"], sp["cap"] * ct)
        pb.append(st(acc, B.pnl.values, B.di.values, B.mon.values, B.h1.values)["rdd"])
    p_a = (1 + sum(v >= top["rdd"] for v in pa)) / (1 + len(pa))
    p_b = (1 + sum(v >= top["rdd"] for v in pb)) / (1 + len(pb))
    top.update(placebo_div_p=p_a, placebo_div_med=float(np.median(pa)), placebo_barra_p=p_b,
               placebo_barra_med=float(np.median(pb)), ok_is=bool(top["plateau"] > 0 and p_a < P_MAX and p_b < P_MAX),
               regras=xname(x, asset))
    print(f"{asset}: ESCOLHA {top['entrada']} | filtros {top['filtros']} | {top['regras']} | {top['mode']} cap={top['cap']} | "
          f"platô {top['plateau']:.2f} ponto {top['rdd']:.2f} ({top['ops']} tr, PF {top['pf']}) | placebo div p={p_a:.3f} "
          f"(med {np.median(pa):.2f}) barra p={p_b:.3f} (med {np.median(pb):.2f})", flush=True)
    top5 = G.drop_duplicates(["entrada", "filtros"]).head(5).to_dict("records")
    return asset, dict(escolha=top, top5=top5)


def final(args):
    """Depois da trava: período completo, IS e OOS das escolhas e do top 5 do IS (top 5 = só relatório)."""
    asset, picks = args
    P, F, X, E, DS, mt5 = prepare(asset)
    sp = SPEC[asset]
    out, trades = {}, []
    cfgs = [("escolha", picks["escolha"])] + [(f"top{i + 1}", c) for i, c in enumerate(picks["top5"])]
    for label, c in cfgs:
        T, pn, xt = E[c["entrada"]]
        xi = int(c["xi"])
        ct = 2 if X[xi]["tp"] == "2lotes" else 1
        FT = F.loc[T.sig.values].reset_index(drop=True)
        m = np.ones(len(T), bool)
        for f in ([] if c["filtros"] == "nenhum" else c["filtros"].split("+")):
            m &= FT[f].values
        res = {}
        allacc = []
        for part, msk in (("is", T["is"].values), ("oos", ~T["is"].values)):
            acc = mgmt(np.where(m & msk)[0], T.tm.values, T.di.values, pn[:, xi], xt[:, xi], c["mode"], c["cap"], sp["cap"] * ct)
            res[part] = st(acc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)
            allacc += list(acc)
        allacc = np.array(sorted(allacc), dtype=int)
        res["total"] = st(allacc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)
        res["regras"] = dict(entrada=c["entrada"], filtros=c["filtros"], saida=xname(X[xi], asset), mode=c["mode"], cap=c["cap"])
        o = res["oos"]
        res["aprovado_oos"] = bool(o["pf"] >= 1.3 and o["net"] > 0 and int(o["meses"].split("/")[0]) >= 3
                                   and (label != "escolha" or c.get("ok_is")))
        # mesma escolha com a regra M5 (stop primeiro na barra), para medir o efeito do M1
        if label == "escolha":
            p5 = []
            for i in allacc:
                r = T.iloc[i]
                p5.append(run_trade(DS[r.date], int(r.k), int(r.j), float(r.ep), int(r.direction), float(r.piv), X[xi], asset,
                                    force_fb=True)[0])
            res["total_regra_m5"] = dict(net=round(float(np.sum(p5))), pf=round(float(np.sum([v for v in p5 if v > 0]) /
                                                                                   -np.sum([v for v in p5 if v < 0])), 2))
            res["pct_trades_com_m1"] = round(100 * float(T.m1.values[allacc].mean()), 1)
            for i in allacc:
                r = T.iloc[i]
                trades.append(dict(asset=asset, date=r.date, tm=int(r.tm), direction=int(r.direction), ep=float(r.ep),
                                   brl=float(pn[i, xi]), exit_tm=int(xt[i, xi]), part="is" if r["is"] else "oos"))
        out[label] = res
    return asset, out, trades


def main():
    os.makedirs(OUT, exist_ok=True)
    lock = os.path.join(OUT, "oos_log.json")
    if os.path.exists(lock):
        raise SystemExit("OOS já executado.")
    with mp.Pool(2) as pool:
        picks = dict(pool.map(run, ["WIN", "WDO"]))
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"), "picks": picks},
              open(lock, "w", encoding="utf-8"), indent=1, default=str)
    with mp.Pool(2) as pool:
        res = pool.map(final, [(a, picks[a]) for a in ("WIN", "WDO")])
    allres, trades = {}, []
    for a, o, t in res:
        allres[a] = o
        trades += t
    pd.DataFrame(trades).to_csv(os.path.join(OUT, "trades_escolhas.csv"), index=False)
    log = json.load(open(lock, encoding="utf-8"))
    log["result"] = allres
    json.dump(log, open(lock, "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(allres, indent=1, default=str))


if __name__ == "__main__":
    main()
