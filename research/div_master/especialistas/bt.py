# -*- coding: utf-8 -*-
"""
Backtest dos especialistas (SPEC_ESPECIALISTAS_5176.md §4/§5), execução tick a tick em M1 (ordem do Strategy Tester
"OHLC 1 minuto": O→H→L→C ou O→L→H→C). Sem M1 no dia (WDO antes de 25/02): barra M5 com stop primeiro.

Regras fixas:
  - sinal no fechamento da barra Profit t; entrada na abertura da barra MT5 com o horário de t+1;
  - janela de entrada WIN 09:05–16:45 · WDO 09:00–17:00; saída forçada 17:25; máx. 24 barras;
  - custo WIN 10 pts / WDO 0,5 pt por contrato; stop sem gap preenche 1 tick pior; stop em gap = abertura;
  - DD trade a trade (ordem de saída). Carteira = 2 contratos WIN + 1 WDO.
Saídas:
  A (Sniper): WIN 2 lotes (L1 banda oposta NWE30 −15, 260–750, SL 240 · L2 750, SL 260 · BE +180→+20);
              WDO 1 lote (próxima Wall/MidWall −0,5, 5,5–14, SL 10, BE +3,5→+1,0).
  B (estrutural): stop no pivô F2 ± buffer (30 / 1,0), aborta se > 300 / 10,5; alvo próxima Wall/MidWall −15 / −0,5;
                  sem alvo (nenhum nível a ≥ 4 ticks) aborta.
"""
from __future__ import annotations

import os
import sys

import numba as nb
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modulo as M  # noqa: E402
from research.discover_gex_nwe_setups import compute_nwe_series  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402

RATES = os.path.join(M.ROOT, "data", "mt5_rates")
IS_END, H1_END, END = "2026-07-31", "2026-04-30", "2026-11-11"   # END estendido de 06/11 em 12/11/2026
WINDOW = {"WIN": (545, 1005), "WDO": (540, 1020)}
N50 = (50, 8.0, 3.0)   # NWE dos filtros de contexto; trocado só em testes de sensibilidade
X = {
    "WIN": dict(tick=5.0, cost=10.0, brl=0.20, ct=2, buf=30.0, sl_max=300.0, front=15.0),
    "WDO": dict(tick=0.5, cost=0.5, brl=10.0, ct=1, buf=1.0, sl_max=10.5, front=0.5),
}


def hm(t):
    return int(t[:2]) * 60 + int(t[3:5])


# ───────────────────────── mercado ─────────────────────────

def _ticks(o, h, l, c):
    return (o, h, l, c) if abs(h - o) <= abs(o - l) else (o, l, h, c)


def market(asset):
    sym = "WIN_N" if asset == "WIN" else "WDO_N"
    m5 = pd.read_csv(os.path.join(RATES, f"mt5_{sym}_M5.csv"), parse_dates=["t"])
    m5["date"] = m5.t.dt.strftime("%Y-%m-%d")
    m5["tm"] = m5.t.dt.hour * 60 + m5.t.dt.minute
    m5 = m5[(m5.tm >= 540) & (m5.tm <= 1075) & (m5.date <= END)].reset_index(drop=True)
    cl = m5.close.values.astype(float)
    n30 = compute_nwe_series(cl, 30, 3.0, 1.6)[:3]
    n50 = compute_nwe_series(cl, *N50)[:3]   # envelope dos filtros de contexto (ext50 / slope50)
    m1 = pd.read_csv(os.path.join(RATES, f"mt5_{sym}_M1.csv"), parse_dates=["t"])
    m1["date"] = m1.t.dt.strftime("%Y-%m-%d")
    m1["tm"] = m1.t.dt.hour * 60 + m1.t.dt.minute
    m1g = {d: g for d, g in m1.groupby("date")}
    DS = {}
    for d, idx in m5.groupby("date").indices.items():
        idx = np.sort(idx)
        pv = np.maximum(idx - 1, 0)
        tm5 = m5.tm.values[idx].astype(np.int64)
        px, op = [], []
        off, nn, fb = np.zeros(len(idx), np.int64), np.zeros(len(idx), np.int64), np.ones(len(idx), np.int64)
        g = m1g.get(d)
        if g is not None:
            mm = g.tm.values
            o1, h1, l1, c1 = (g[c].values.astype(float) for c in ("open", "high", "low", "close"))
            for k, t in enumerate(tm5):
                sel = np.where((mm >= t) & (mm < t + 5))[0]
                off[k] = len(px)
                if len(sel) == 0:
                    continue
                fb[k] = 0
                for s in sel:
                    for q, v in enumerate(_ticks(o1[s], h1[s], l1[s], c1[s])):
                        px.append(v)
                        op.append(q == 0)
                nn[k] = len(px) - off[k]
        DS[d] = dict(px=np.array(px, float), op=np.array(op, np.bool_), off=off, nn=nn, fb=fb,
                     o5=m5.open.values[idx].astype(float), h5=m5.high.values[idx].astype(float),
                     l5=m5.low.values[idx].astype(float), c5=m5.close.values[idx].astype(float), tm5=tm5,
                     u30=n30[1][pv], l30=n30[2][pv], c50=n50[0][pv], u50=n50[1][pv], l50=n50[2][pv],
                     pos={int(t): k for k, t in enumerate(tm5)})
    return DS


# ───────────────────────── simulação ─────────────────────────

@nb.njit(cache=True)
def _tick(px, isop, off, fb, o5, h5, l5, c5, k, j, d):
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
def sim(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, band, e, ep, d, sl, tp_fix, use_band, front, tp_lo, tp_hi,
        be_trig, be_lock, tmax, tick):
    """Um lote. Retorna (pontos brutos, minuto de saída). band[k] = banda oposta da barra k−1 (causal)."""
    n5 = len(o5)
    stop = ep - d * sl
    mfe = 0.0
    for k in range(e, n5):
        if k > e:
            if tm5[k] >= 1045 or k - e > tmax:
                return (o5[k] - ep) * d, tm5[k]
            if be_trig > 0 and mfe >= be_trig:
                cand = ep + d * be_lock
                if (o5[k] - cand) * d > 0 and (cand - stop) * d > 0:
                    stop = cand
        if use_band:
            raw = band[k] - d * front
            lo = ep + d * tp_lo
            hi = ep + d * tp_hi
            if d == 1:
                tp = min(max(raw, lo), hi)
            else:
                tp = max(min(raw, lo), hi)
            tp = np.round(tp / tick) * tick
        else:
            tp = tp_fix
        nt = nn[k] if fb[k] == 0 else 4
        for j in range(nt):
            p, op = _tick(px, isop, off, fb, o5, h5, l5, c5, k, j, d)
            if (p - stop) * d <= 0:
                return ((p if op else stop - d * tick) - ep) * d, tm5[k]
            if (p - tp) * d >= 0:
                return ((p if op else tp) - ep) * d, tm5[k]
            if (p - ep) * d > mfe:
                mfe = (p - ep) * d
    return (c5[n5 - 1] - ep) * d, tm5[n5 - 1]


def _args(D):
    return (D["px"], D["op"], D["off"], D["nn"], D["fb"], D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"])


def next_level(levels, ep, d, min_dist):
    lv = [v for v in levels if (v - ep) * d >= min_dist]
    return (min(lv) if d == 1 else max(lv)) if lv else None


def exit_A(asset, D, e, ep, d, levels):
    x = X[asset]
    if asset == "WIN":
        band = D["u30"] if d == 1 else D["l30"]
        p1, t1 = sim(*_args(D), band, e, ep, d, 240.0, 0.0, True, 15.0, 260.0, 750.0, 180.0, 20.0, 24, x["tick"])
        p2, t2 = sim(*_args(D), band, e, ep, d, 260.0, ep + d * 750.0, False, 0.0, 0.0, 0.0, 180.0, 20.0, 24, x["tick"])
        return (p1 + p2 - 2 * x["cost"]) * x["brl"], max(t1, t2)
    w = next_level(levels, ep, d, 5.5 + 0.5)
    tp = ep + d * 14.0 if w is None else ep + d * min(max(d * (w - 0.5 - ep), 5.5), 14.0)
    p, t = sim(*_args(D), D["u30"], e, ep, d, 10.0, tp, False, 0.0, 0.0, 0.0, 3.5, 1.0, 24, x["tick"])
    return (p - x["cost"]) * x["brl"], t


def exit_B(asset, D, e, ep, d, levels, piv, buf=None, sl_max=None, tp_mode="wall", be=None):
    """Saída B. Retorna (R$ por contrato, minuto de saída) ou None se abortada."""
    x = X[asset]
    buf = x["buf"] if buf is None else buf
    sl_max = x["sl_max"] if sl_max is None else sl_max
    stop = piv - d * buf
    sl = d * (ep - stop)
    if sl < 2 * x["tick"] or sl > sl_max:
        return None
    if tp_mode == "wall":
        w = next_level(levels, ep, d, 4 * x["tick"] + x["front"])
        if w is None:
            return None
        tp = w - d * x["front"]
        p, t = sim(*_args(D), D["u30"], e, ep, d, sl, tp, False, 0.0, 0.0, 0.0,
                   0.0 if be is None else be[0] * sl, 0.0 if be is None else be[1], 24, x["tick"])
    elif tp_mode.startswith("R"):
        tp = ep + d * float(tp_mode[1:]) * sl
        p, t = sim(*_args(D), D["u30"], e, ep, d, sl, tp, False, 0.0, 0.0, 0.0,
                   0.0 if be is None else be[0] * sl, 0.0 if be is None else be[1], 24, x["tick"])
    else:   # banda oposta NWE50
        band = D["u50"] if d == 1 else D["l50"]
        p, t = sim(*_args(D), band, e, ep, d, sl, 0.0, True, x["front"], 2 * x["tick"], 1e9,
                   0.0 if be is None else be[0] * sl, 0.0 if be is None else be[1], 24, x["tick"])
    return (p - x["cost"]) * x["brl"], t


# ───────────────────────── sinais → trades ─────────────────────────

def signals(asset, engine, require_micro=False):
    """Todos os gatilhos (WALL e EXTREMO) do motor no período completo, com contexto para filtros posteriores."""
    data = {d: v for d, v in load_asset(asset, "M5").items() if d <= END}
    rows = []
    for d in sorted(data):
        bars, walls, _ = data[d]
        fb, R = M.run_day(asset, bars, walls, engines=(engine,), require_micro=require_micro)
        lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        by = {(c["dir"], c["j"]): c for c in R[engine]["cands"]}
        seq = {1: 0, -1: 0}
        for x in R[engine]["trig"]:
            t = x["idx"]
            if t + 1 >= len(fb):
                continue
            c = by[(x["dir"], x["j"])]
            rows.append(dict(date=d, engine=engine, esp=x["esp"], sub=x["sub"], dir=x["dir"], j=x["j"], t=t,
                             k=x["k"], conf=x["conf"],
                             time_in=fb[t + 1]["time"], lag=x["lag"], dup=x["dup"], super=x["super"],
                             piv=c["px2"], wd_ratio=c["wd"] / max(c["thr"], 1e-9), seq=seq[x["dir"]],
                             c1=c["c1"], c2=c["c2"], levels=lv, open0=fb[0]["open"],
                             sig_c=fb[t]["close"], sig_h=fb[t]["high"], sig_l=fb[t]["low"], sig_o=fb[t]["open"]))
            seq[x["dir"]] += 1
    return pd.DataFrame(rows)


def simulate(asset, S, DS, exits=("A", "B")):
    """Acrescenta e (barra MT5), ep e resultados das saídas. Linhas sem barra MT5/fora da janela ficam com ok=False."""
    lo_w, hi_w = WINDOW[asset]
    out = {f"pnl_{x}": np.full(len(S), np.nan) for x in exits}
    out.update({f"xt_{x}": np.full(len(S), -1, np.int64) for x in exits})
    ok = np.zeros(len(S), bool)
    eidx, epx, ctx = np.full(len(S), -1), np.full(len(S), np.nan), {k: np.full(len(S), np.nan) for k in
                                                                    ("ext50", "slope50", "dmov")}
    for i, r in enumerate(S.itertuples()):
        D = DS.get(r.date)
        tm = hm(r.time_in)
        if D is None or tm not in D["pos"] or not (lo_w <= tm <= hi_w):
            continue
        e = D["pos"][tm]
        ep = float(D["o5"][e])
        ok[i], eidx[i], epx[i] = True, e, ep
        half = max(D["u50"][e] - D["c50"][e], X[asset]["tick"])
        ctx["ext50"][i] = -r.dir * (D["c5"][e - 1] - D["c50"][e]) / half if e >= 1 else np.nan
        ctx["slope50"][i] = r.dir * (D["c50"][e] - D["c50"][max(0, e - 6)]) / half
        ctx["dmov"][i] = r.dir * (D["c5"][e - 1] - D["o5"][0]) / half if e >= 1 else 0.0
        for x in exits:
            res = exit_A(asset, D, e, ep, r.dir, r.levels) if x == "A" else \
                exit_B(asset, D, e, ep, r.dir, r.levels, r.piv)
            if res is not None:
                out[f"pnl_{x}"][i], out[f"xt_{x}"][i] = res
    S = S.copy()
    S["ok"], S["e"], S["ep"], S["tm"] = ok, eidx, epx, [hm(t) for t in S.time_in]
    for k, v in {**out, **ctx}.items():
        S[k] = v
    return S


# ───────────────────────── métricas ─────────────────────────

def stats(T, col, xtcol, mult=1.0):
    """T já filtrado. DD trade a trade na ordem de saída."""
    T = T[T[col].notna()]
    if len(T) == 0:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, rdd=0.0, meses="0/0", h1=0.0, h2=0.0, is_=0.0, oos=0.0,
                    rdd_is=0.0, rdd_oos=0.0)
    T = T.sort_values(["date", xtcol, "tm"])
    p = T[col].values * mult
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby(T.date.str[:7].values).sum()
    isv = (T.date <= IS_END).values
    h1 = (T.date <= H1_END).values

    def rdd(q):
        if len(q) == 0:
            return 0.0
        e = np.cumsum(q)
        dd_ = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e))
        return round(float(e[-1]) / dd_, 2) if dd_ else 99.0

    return dict(ops=int(len(p)), wr=round(100 * float((p > 0).mean()), 1), pf=round(float(g / l), 2) if l else 99.0,
                net=round(float(eq[-1])), dd=round(dd), rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
                meses=f"{int((mon > 0).sum())}/{len(mon)}", h1=round(float(p[h1].sum())),
                h2=round(float(p[isv & ~h1].sum())), is_=round(float(p[isv].sum())), oos=round(float(p[~isv].sum())),
                rdd_is=rdd(p[isv]), rdd_oos=rdd(p[~isv]))


def portfolio(Tw, Td, col_w, col_d, xt_w, xt_d, mult_w=1.0):
    a = Tw[Tw[col_w].notna()][["date", "tm", xt_w, col_w]].rename(columns={xt_w: "xt", col_w: "pnl"})
    a["pnl"] = a["pnl"] * mult_w
    b = Td[Td[col_d].notna()][["date", "tm", xt_d, col_d]].rename(columns={xt_d: "xt", col_d: "pnl"})
    return stats(pd.concat([a, b], ignore_index=True), "pnl", "xt")


def exit_G(asset, D, e, ep, d, sl, tp_pts, tmax, be=None, lots=1):
    """Saída genérica: SL fixo, alvo fixo em pts (None = sem alvo), tempo máx., BE opcional (gatilho, trava) em pts."""
    x = X[asset]
    tp = ep + d * (tp_pts if tp_pts else 1e9)
    p, t = sim(*_args(D), D["u30"], e, ep, d, sl, tp, False, 0.0, 0.0, 0.0,
               0.0 if be is None else be[0], 0.0 if be is None else be[1], tmax, x["tick"])
    return (p - x["cost"]) * x["brl"], t


def mgmt(Tf, col, xt, mode):
    """Gestão. LIVRE = todos; UM_POR_VEZ = nova entrada só depois do minuto de saída do trade anterior (mesmo dia)."""
    if mode == "LIVRE":
        return Tf
    keep, day, last = [], None, -1
    for i, r in zip(Tf.index, Tf.itertuples()):
        if r.date != day:
            day, last = r.date, -1
        if r.tm <= last:
            continue
        keep.append(i)
        last = Tf.at[i, xt]
    return Tf.loc[keep]
