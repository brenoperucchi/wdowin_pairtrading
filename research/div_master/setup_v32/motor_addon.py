# -*- coding: utf-8 -*-
"""Motor do add-on v3.2 (pesquisa). Só lê core/especialista_v22 e especialistas/bt; não altera produção."""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "carteira_v22")]

import numpy as np
import pandas as pd
import modulo as M
import bt
from core import especialista_v22 as E
from research.div_wall.data import load_asset

IS_END = "2026-07-31"
H1_END = "2026-04-30"
END = bt.END  # 2026-11-11
T_START, T_END = 600, 960  # 10:00–15:55
TMAX = 12
EOD = 1045
BUF = {"WIN": 30.0, "WDO": 1.0}
SL_MAX = {"WIN": 300.0, "WDO": 10.5}
COST = {"WIN": 10.0, "WDO": 0.5}
TICK = {"WIN": 5.0, "WDO": 0.5}
BRL = {"WIN": 0.20, "WDO": 10.0}
FRONT = {"WIN": 15.0, "WDO": 0.5}
SHIFT = {"WIN": 250.0, "WDO": 5.0}
WICK_MIN = 0.40
EXT_NWE_G1 = -0.5
SLOPE_NWE_G1 = -0.5
EXT_BAND_G4 = -0.8


def hm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


def exec_bars(D: dict) -> List[dict]:
    n = len(D["o5"])
    out = []
    for k in range(n):
        out.append(dict(
            time=f"{int(D['tm5'][k]) // 60:02d}:{int(D['tm5'][k]) % 60:02d}",
            open=float(D["o5"][k]), high=float(D["h5"][k]), low=float(D["l5"][k]), close=float(D["c5"][k]),
            nwe50_line=float(D["c50"][k + 1]) if k + 1 < n else 0.0,
            nwe50_upper=float(D["u50"][k + 1]) if k + 1 < n else 0.0,
            nwe50_lower=float(D["l50"][k + 1]) if k + 1 < n else 0.0,
        ))
    return out


def day_inputs(DS, data, d, asset):
    bars, walls, _ = data[d]
    fb = M.compute_flow([dict(b) for b in bars], asset)
    return fb, walls, exec_bars(DS[d])


def nwe_ctx(D, e, d, tick):
    if e < 1:
        return None
    n50 = float(D["c50"][e])
    u50 = float(D["u50"][e])
    l50 = float(D["l50"][e])
    n50_old = float(D["c50"][max(0, e - 6)])
    if n50 <= 0 or u50 <= 0:
        return None
    half = max(u50 - n50, tick)
    ext = -d * (float(D["c5"][e - 1]) - n50) / half
    slope = d * (n50 - n50_old) / half
    return dict(n50=n50, u50=u50, l50=l50, half=half, ext=ext, slope=slope)


def classify_e22_funnel(fb, walls, ex, asset="WIN"):
    """Replay causal do funil do especialista (só WIN). Retorna trades e o detalhe de cada gatilho Opção C."""
    if asset != "WIN":
        return [], []
    P = M.PARAMS["WIN"]
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    atr = M.atr_series(fb, P["tick"])
    cands = M.engine_v32(fb, levels, P, "common", atr=atr, opt=M.V32_PROD)
    trig, _ = M.triggers(fb, cands, P)
    pos = {str(b["time"])[:5]: i for i, b in enumerate(ex)}
    seq = {1: 0, -1: 0}
    rows = []
    last_exit = -1
    ccfg = E.CFG
    produced = E.run(fb, walls, ex, is_live=False)
    by_prod = {(t["time"], t["dir_num"]): t for t in produced}
    for x in trig:
        reasons = []
        s = seq[x["dir"]]
        seq[x["dir"]] += 1
        if x["idx"] + 1 >= len(fb):
            reasons.append("sem_barra")
            rows.append(dict(x=x, seq=s, reasons=reasons, t_in=None, tm=None))
            continue
        t_in = fb[x["idx"] + 1]["time"]
        e = pos.get(t_in)
        tm = hm(t_in)
        if x["super"]:
            reasons.append("super")
        if s > 1:
            reasons.append("seq")
        if not (ccfg["t_start"] <= tm < ccfg["t_end"]):
            reasons.append("janela")
        ext = slope = None
        if e is None or e < 1:
            reasons.append("sem_exec")
        else:
            n50 = float(ex[e - 1].get("nwe50_line") or 0.0)
            u50 = float(ex[e - 1].get("nwe50_upper") or 0.0)
            n50_old = float(ex[max(0, e - 7)].get("nwe50_line") or 0.0)
            if n50 <= 0 or u50 <= 0:
                reasons.append("sem_nwe")
            else:
                half = max(u50 - n50, ccfg["tick"])
                ext = -x["dir"] * (float(ex[e - 1]["close"]) - n50) / half
                slope = x["dir"] * (n50 - n50_old) / half
                if not (ext > ccfg["ext_min"] and slope > ccfg["slope_min"]):
                    reasons.append("nwe")
        if tm <= last_exit:
            reasons.append("ocupado")
        entered = not reasons
        if entered:
            tr = by_prod.get((t_in, x["dir"]))
            if tr is not None:
                last_exit = hm(tr["exit_time"]) if not tr["is_open"] else 10 ** 6
            else:
                last_exit = tm  # fallback: at least occupy the entry bar
        rows.append(dict(x=x, seq=s, reasons=reasons, t_in=t_in, tm=tm, ext=ext, slope=slope, entered=entered))
    return produced, rows


def g2_ok(fb, c, t):
    d, j = c["dir"], c["j"]
    if t < 1 or t >= len(fb):
        return False
    b, bj = fb[t], fb[j]
    brk = (b["close"] > bj["high"]) if d == 1 else (b["close"] < bj["low"])
    flow = d * (float(b["wave"]) - float(fb[t - 1]["wave"])) > 0
    return brk and flow


def g3_ok(fb, c, t, levels, P):
    d, j = c["dir"], c["j"]
    if t >= len(fb):
        return False
    b = fb[t]
    rng = b["high"] - b["low"]
    if rng <= 0:
        return False
    if d == 1:
        wick = (min(b["open"], b["close"]) - b["low"]) / rng
    else:
        wick = (b["high"] - max(b["open"], b["close"])) / rng
    if wick < WICK_MIN:
        return False
    if d * (b["close"] - b["open"]) <= 0:
        return False
    if d * (float(b["wave"]) - float(fb[j]["wave"])) <= 0:
        return False
    # testa a zona: extremo da barra t ainda perto da âncora
    px = b["low"] if d == 1 else b["high"]
    wall = c["c1"] if c["c1"] is not None else c["c2"]
    near = wall is not None and abs(px - wall) <= P["zone"]
    day = False
    if c.get("day") is not None:
        e = c["day"]["e"]
        day = (px <= e + P["day_tol"]) if d == 1 else (px >= e - P["day_tol"])
    return near or day


def g4_ok(fb, c, t, D, pos, tick):
    d, j = c["dir"], c["j"]
    if t >= len(fb) or d * (fb[t]["close"] - fb[j]["close"]) <= 0:
        return False
    times = [fb[j]["time"], fb[max(0, t - 1)]["time"], fb[t]["time"]]
    exts = []
    inside = False
    for tm in times:
        e = pos.get(hm(tm))
        if e is None or e < 1:
            continue
        ctx = nwe_ctx(D, e, d, tick)
        if ctx is None:
            continue
        exts.append(ctx["ext"])
        if tm == fb[t]["time"]:
            close = fb[t]["close"]
            inside = (close > ctx["l50"]) if d == 1 else (close < ctx["u50"])
    if not exts or not inside:
        return False
    return min(exts[0], exts[1] if len(exts) > 1 else exts[0]) <= EXT_BAND_G4


def first_hit(fb, c, P, kind, D=None, pos=None, tick=5.0, levels=None):
    j, conf = c["j"], c["conf"]
    lo, hi = max(j + 1, conf), j + M.COMMON["trig_max"]
    n = len(fb)
    if lo > hi:
        return None
    for t in range(lo, min(hi, n - 2) + 1):  # precisa existir t+1
        ok = False
        if kind == "G1":
            # uses official Option C; handled elsewhere
            return None
        elif kind == "G2":
            ok = g2_ok(fb, c, t)
        elif kind == "G3":
            ok = g3_ok(fb, c, t, levels or [], P)
        elif kind == "G4":
            ok = g4_ok(fb, c, t, D, pos, tick)
        if ok:
            return t
    return None


def addon_sim(D, e, ep, d, sl, tp, tmax, tick, cost, slip_ticks=1):
    """Retorna (pts líquidos 1 ct, minuto de saída, razão). Stop em gap = abertura; senão, slip_ticks pior."""
    o5, h5, l5, c5, tm5 = D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"]
    px, isop, off, nn, fb = D["px"], D["op"], D["off"], D["nn"], D["fb"]
    n5 = len(o5)
    stop = ep - d * sl
    for k in range(e, n5):
        if k > e:
            if tm5[k] >= EOD or k - e > tmax:
                return (o5[k] - ep) * d - cost, int(tm5[k]), "TEMPO"
        nt = int(nn[k]) if fb[k] == 0 else 4
        for j in range(nt):
            p, op = bt._tick(px, isop, off, fb, o5, h5, l5, c5, k, j, d)
            if (p - stop) * d <= 0:
                fill = p if op else stop - d * tick * slip_ticks
                return (fill - ep) * d - cost, int(tm5[k]), "STOP"
            if (p - tp) * d >= 0:
                fill = p if op else tp
                return (fill - ep) * d - cost, int(tm5[k]), "ALVO"
    return (c5[n5 - 1] - ep) * d - cost, int(tm5[n5 - 1]), "FIM"


def plan_exit(asset, D, e, ep, d, piv, levels, tp_mode, cost_mult=1.0, slip_ticks=1):
    tick, front, buf = TICK[asset], FRONT[asset], BUF[asset]
    cost = COST[asset] * cost_mult
    stop = piv - d * buf
    sl = d * (ep - stop)
    if sl < 2 * tick or sl > SL_MAX[asset]:
        return None
    if tp_mode == "S2b":
        w = bt.next_level(levels, ep, d, sl)
        if w is None:
            return None
        tp = w - d * front
        if d * (tp - ep) + 1e-9 < sl:
            return None
    else:  # S2a
        ctx = nwe_ctx(D, e, d, tick)
        if ctx is None:
            return None
        line_tp, opp = ctx["n50"], (ctx["u50"] if d == 1 else ctx["l50"])
        if abs(ep - ctx["n50"]) / ctx["half"] > 0.5 and d * (line_tp - ep) >= 4 * tick:
            tp = line_tp
        elif d * (opp - ep) >= 4 * tick:
            tp = opp - d * front
        else:
            return None
    pts, xt, why = addon_sim(D, e, ep, d, sl, tp, TMAX, tick, cost, slip_ticks)
    return dict(pts=pts, brl=pts * BRL[asset], xt=xt, why=why, sl=sl, tp=tp)


def allowed_vs_e22(tm, d, e22_day):
    """e22_day: list of dicts tm, xt, d, be_tm (minutos). None e22_day = ativo sem especialista (WDO)."""
    if not e22_day:
        return True
    for tr in e22_day:
        if tr["tm"] == tm:
            return False
        if tr["tm"] <= tm < tr["xt"]:
            if tr["d"] != d:
                return False
            if tr["be_tm"] is None or tm <= tr["be_tm"]:
                return False
            return True
    return True


def stats_table(T, col="brl", xtcol="xt"):
    if T is None or len(T) == 0:
        empty = dict(ops=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, rdd=0.0, meses="0/0",
                     h1=0.0, h2=0.0, is_=0.0, oos=0.0, rdd_is=0.0, rdd_oos=0.0,
                     rdd_h1=0.0, rdd_h2=0.0, meses_is="0/0", n_is=0, n_h1=0, n_h2=0, n_oos=0,
                     pf_is=0.0, net_is=0.0, dd_is=0.0, mon_is_pos=0, mon_is_n=0, h1_pos=False, h2_pos=False)
        return empty
    T = T[T[col].notna()].copy()
    if len(T) == 0:
        return stats_table(None)
    T = T.sort_values(["date", xtcol, "tm"])

    def _pack(q):
        if len(q) == 0:
            return dict(ops=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, rdd=0.0, meses="0/0")
        eq = np.cumsum(q)
        dd = float(np.max(np.maximum.accumulate(np.r_[0.0, eq])[1:] - eq))
        g, l = float(q[q > 0].sum()), float(-q[q < 0].sum())
        return dict(
            ops=int(len(q)), wr=round(100 * float((q > 0).mean()), 1),
            pf=round(g / l, 2) if l else 99.0,
            net=round(float(eq[-1]), 2), dd=round(dd, 2),
            rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
        )

    p = T[col].values.astype(float)
    base = _pack(p)
    mon = pd.Series(p, index=T.index).groupby(T.date.str[:7].values).sum()
    base["meses"] = f"{int((mon > 0).sum())}/{len(mon)}"
    isv = (T.date <= IS_END).values
    h1 = (T.date <= H1_END).values
    h2 = isv & ~h1
    oos = ~isv
    si, sh1, sh2, so = _pack(p[isv]), _pack(p[h1]), _pack(p[h2]), _pack(p[oos])
    mon_is = pd.Series(p[isv]).groupby(T.date[isv].str[:7].values).sum() if isv.any() else pd.Series(dtype=float)
    base.update(dict(
        h1=sh1["net"], h2=sh2["net"], is_=si["net"], oos=so["net"],
        rdd_is=si["rdd"], rdd_oos=so["rdd"], rdd_h1=sh1["rdd"], rdd_h2=sh2["rdd"],
        meses_is=f"{int((mon_is > 0).sum())}/{len(mon_is)}" if len(mon_is) else "0/0",
        n_is=si["ops"], n_h1=sh1["ops"], n_h2=sh2["ops"], n_oos=so["ops"],
        pf_is=si["pf"], net_is=si["net"], dd_is=si["dd"],
        mon_is_pos=int((mon_is > 0).sum()) if len(mon_is) else 0,
        mon_is_n=int(len(mon_is)),
        h1_pos=sh1["net"] > 0, h2_pos=sh2["net"] > 0,
    ))
    return base


def daily_corr(a: pd.DataFrame, b: pd.DataFrame, col="brl"):
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return float("nan")
    idx = pd.Index(sorted(set(a.date) | set(b.date)))
    sa = a.groupby("date")[col].sum().reindex(idx, fill_value=0.0)
    sb = b.groupby("date")[col].sum().reindex(idx, fill_value=0.0)
    if sa.std() == 0 or sb.std() == 0:
        return float("nan")
    return float(sa.corr(sb))
