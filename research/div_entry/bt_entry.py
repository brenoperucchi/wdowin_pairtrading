"""
BT das entradas próprias com divergência v2 / absorção rápida (research/div_entry/PLANO.md).
Etapas: grade IS → platô → placebo → OOS uma vez (trava results/oos_log.json).
Uso: python -m research.div_entry.bt_entry
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

from core.div_wall_signal import (  # noqa: E402
    DivParamsV2, ExitParams, Signal, build_trade, compute_flow, detect_divergences_v2, hhmm_to_min, simulate_trade,
)
from research.div_gate.build_gate import days_with_warm  # noqa: E402
from research.div_gate.gate import nwe_day  # noqa: E402

OUT = os.path.join(ROOT, "research", "div_entry", "results")
IS_END = "2026-07-31"
KS = (0.5, 1.0, 1.5)
RADIUS = {"WIN": (40.0, 100.0), "WDO": (1.5, 4.0)}
LS = (30, 50, 80, 100)
CONFS = ("PIVO", "FECHA_WALL")
ZS = (0.5, 0.8, 1.0)
NS = (3, 6, 12)
MODES = ("LIVRE", "UM_POR_VEZ")
MIN_TRADES, N_PLACEBO, P_MAX = 150, 200, 0.10
T0, T1 = hhmm_to_min("09:15"), hhmm_to_min("17:00")
EXITS = [dict(sl_mode=s, tp_mode=tp, rr=rr, be_trigger_r=be)
         for s in ("pivot", "wall")
         for tp, rr in (("rr", 1.5), ("rr", 2.0), ("next_wall", 1.5), ("nwe_center", 1.5))
         for be in (None, 1.0)]


def exit_name(e):
    tp = f"rr{e['rr']}" if e["tp_mode"] == "rr" else e["tp_mode"]
    return f"{e['sl_mode']}|{tp}|{'BE1R' if e['be_trigger_r'] else 'semBE'}"


def configs(asset):
    out = []
    for k, R, L, cf, z in itertools.product(KS, RADIUS[asset], LS, CONFS, ZS):
        out.append(dict(fam="E1_DIV_NWE", k=k, R=R, L=L, conf=cf, z=z, N=0))
    for k, R, L, N in itertools.product(KS, RADIUS[asset], LS, NS):
        out.append(dict(fam="E2_ABS_DIV", k=k, R=R, L=L, conf="PIVO", z=0.0, N=N))
    for k, R, L, N, z in itertools.product(KS, RADIUS[asset], LS, NS, ZS):
        out.append(dict(fam="E3_ABS_DIV_NWE", k=k, R=R, L=L, conf="PIVO", z=z, N=N))
    for R in RADIUS[asset]:
        out.append(dict(fam="E4_ABS", k=0.0, R=R, L=50, conf="", z=0.0, N=0))
    return out


def cfg_key(c):
    return (c["fam"], c["k"], c["R"], c["L"], c["conf"], c["z"], c["N"])


# ───────────── preparação por dia ─────────────

def zdist(nwe, idx, d, px):
    c, u, l = nwe
    half = (c[idx] - l[idx]) if d == 1 else (u[idx] - c[idx])
    return ((c[idx] - px) if d == 1 else (px - c[idx])) / max(half, 1e-9)


def absorption(fb, levels, R):
    out = []
    for i, b in enumerate(fb):
        if not (T0 <= hhmm_to_min(b["time"]) <= T1):
            continue
        for d in (1, -1):
            ext = b["low"] if d == 1 else b["high"]
            near = [x for x in levels if abs(x - ext) <= R]
            if not near:
                continue
            lvl = min(near, key=lambda x: abs(x - ext))
            if not ((b["close"] > lvl) if d == 1 else (b["close"] < lvl)):
                continue
            if b["wyckoff_abs"] * d > 0 and b["inst_pass_delta"] * d > 0 and b["ret_delta_bar"] * d < 0:
                out.append((i, d, float(ext), float(lvl)))
    return out


def touch_pool(fb, levels, R):
    """Placebo: barras que tocam a Wall (até R) e fecham do lado defendido — sem nenhuma condição de fluxo."""
    out = []
    for i, b in enumerate(fb):
        if not (T0 <= hhmm_to_min(b["time"]) <= T1):
            continue
        for d in (1, -1):
            ext = b["low"] if d == 1 else b["high"]
            near = [x for x in levels if abs(x - ext) <= R]
            if near:
                lvl = min(near, key=lambda x: abs(x - ext))
                if (b["close"] > lvl) if d == 1 else (b["close"] < lvl):
                    out.append((i, d, float(ext), float(lvl)))
    return out


def prep_day(asset, bars, walls, warm):
    fb = compute_flow(bars, asset)
    levels = sorted(float(w["price"]) for w in walls if w["type"] in ("Wall", "MidWall"))
    nwe = {L: nwe_day(warm, [b["close"] for b in bars], L) for L in LS}
    det_none = {}
    for k, R, cf in itertools.product(KS, RADIUS[asset], CONFS):
        p = DivParamsV2.default(asset, wave_k=k, wall_radius=R, confirm=cf, nwe_filter="none")
        det_none[(k, R, cf)] = [(s.idx, s.direction, s.pivot_px, s.wall_px)
                                for s in detect_divergences_v2(fb, walls, nwe[50], p)]
    det_ext = {}
    for k, R, L in itertools.product(KS, RADIUS[asset], LS):
        p = DivParamsV2.default(asset, wave_k=k, wall_radius=R, confirm="PIVO", nwe_filter="extreme")
        det_ext[(k, R, L)] = [(s.idx, s.direction) for s in detect_divergences_v2(fb, walls, nwe[L], p)]
    absb = {R: absorption(fb, levels, R) for R in RADIUS[asset]}
    pool = {R: touch_pool(fb, levels, R) for R in RADIUS[asset]}
    return dict(fb=fb, walls=walls, nwe=nwe, det_none=det_none, det_ext=det_ext, absb=absb, pool=pool)


def signals_for(day, c):
    """Lista de (idx, dir, pivot_px, wall_px) da config c no dia (um sinal por barra e direção)."""
    out, seen = [], set()
    if c["fam"] == "E1_DIV_NWE":
        nwe = day["nwe"][c["L"]]
        for (i, d, px, w) in day["det_none"][(c["k"], c["R"], c["conf"])]:
            if T0 <= hhmm_to_min(day["fb"][i]["time"]) <= T1 and zdist(nwe, i, d, px) >= c["z"]:
                out.append((i, d, px, w))
    elif c["fam"] == "E4_ABS":
        out = list(day["absb"][c["R"]])
    else:
        divs = defaultdict(list)
        for (i, d) in day["det_ext"][(c["k"], c["R"], c["L"])]:
            divs[d].append(i)
        nwe = day["nwe"][c["L"]]
        for (i, d, ext, lvl) in day["absb"][c["R"]]:
            if not any(i - c["N"] < j <= i for j in divs[d]):
                continue
            if c["fam"] == "E3_ABS_DIV_NWE" and zdist(nwe, i, d, ext) < c["z"]:
                continue
            out.append((i, d, ext, lvl))
    res = []
    for s in sorted(out):
        if (s[0], s[1]) not in seen:
            seen.add((s[0], s[1]))
            res.append(s)
    return res


class Sim:
    def __init__(self, asset, days):
        self.asset, self.days, self.memo = asset, days, {}
        self.ep = [ExitParams.default(asset, max_bars=24, **e) for e in EXITS]

    def trade(self, date, s, ei, L):
        key = (date, s, ei, L if EXITS[ei]["tp_mode"] == "nwe_center" else 0)
        if key in self.memo:
            return self.memo[key]
        day = self.days[date]
        i, d, px, w = s
        sig = Signal(idx=i, time=day["fb"][i]["time"], direction=d, pivot_idx=i, pivot_px=px, f1_idx=i, f1_px=px,
                     wave_f1=0.0, wave_f2=0.0, wall_px=w, wall_type="")
        nwe = day["nwe"][L]
        tr = build_trade(date, self.asset, sig, day["fb"], day["walls"], nwe, self.ep[ei])
        r = None
        if tr is not None:
            tr = simulate_trade(tr, day["fb"], nwe, self.ep[ei])
            r = (date, tr.entry_idx, tr.exit_idx, tr.exit_time, float(tr.brl), d)
        self.memo[key] = r
        return r

    def trades(self, c, ei, dates, sig_override=None):
        out = []
        for date in dates:
            sigs = sig_override[date] if sig_override is not None else signals_for(self.days[date], c)
            for s in sigs:
                r = self.trade(date, s, ei, c["L"])
                if r is not None:
                    out.append(r)
        return out


def one_at_a_time(trs):
    out, last = [], {}
    for t in sorted(trs, key=lambda x: (x[0], x[1])):
        if t[1] > last.get(t[0], -1):
            out.append(t)
            last[t[0]] = t[2]
    return out


def stats(trs):
    if not trs:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, mdd=0.0, ret_dd=0.0, pos_m="0/0")
    trs = sorted(trs, key=lambda x: (x[0], x[2], x[1]))
    p = np.array([t[4] for t in trs])
    eq = np.cumsum(p)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = defaultdict(float)
    for t in trs:
        m[t[0][:7]] += t[4]
    return dict(ops=len(trs), wr=round(100 * float((p > 0).mean()), 1), pf=round(float(g / l), 2) if l else 99.0,
                net=round(float(eq[-1]), 0), mdd=round(mdd, 0),
                ret_dd=round(float(eq[-1]) / mdd, 2) if mdd else 99.0,
                pos_m=f"{sum(1 for v in m.values() if v > 0)}/{len(m)}")


def score(s):
    return s["ret_dd"] if (s["ops"] >= MIN_TRADES and s["net"] > 0) else 0.0


# ───────────── etapas por ativo ─────────────

def load(asset):
    raw = days_with_warm(asset)
    return {d: prep_day(asset, b, w, warm) for d, (b, w, warm, _) in raw.items()}


def grid(asset, sim, is_dates):
    rows = []
    for c in configs(asset):
        sigs = {d: signals_for(sim.days[d], c) for d in is_dates}
        for ei, e in enumerate(EXITS):
            trs = sim.trades(c, ei, is_dates, sig_override=sigs)
            for mode in MODES:
                s = stats(trs if mode == "LIVRE" else one_at_a_time(trs))
                rows.append(dict(asset=asset, **c, exit=exit_name(e), ei=ei, mode=mode, **s, score=score(s)))
    return pd.DataFrame(rows)


def plateau(G, asset):
    ords = dict(k=list(KS), R=list(RADIUS[asset]), L=list(LS), z=list(ZS), N=list(NS), conf=list(CONFS))
    idx = {(r.fam, r.ei, r.mode, r.k, r.R, r.L, r.conf, r.z, r.N): r.score for r in G.itertuples()}
    out = []
    for r in G.itertuples():
        vals = [r.score]
        base = dict(k=r.k, R=r.R, L=r.L, conf=r.conf, z=r.z, N=r.N)
        params = {"E1_DIV_NWE": ("k", "R", "L", "conf", "z"), "E2_ABS_DIV": ("k", "R", "L", "N"),
                  "E3_ABS_DIV_NWE": ("k", "R", "L", "N", "z"), "E4_ABS": ("R",)}[r.fam]
        for p in params:
            seq = ords[p]
            j = seq.index(base[p])
            for jj in (j - 1, j + 1):
                if 0 <= jj < len(seq):
                    nb = dict(base, **{p: seq[jj]})
                    key = (r.fam, r.ei, r.mode, nb["k"], nb["R"], nb["L"], nb["conf"], nb["z"], nb["N"])
                    if key in idx:
                        vals.append(idx[key])
        out.append(float(np.median(vals)))
    G = G.copy()
    G["plateau"] = out
    return G


def placebo(sim, c, ei, mode, dates, seed=11):
    """Mesmo nº de sinais por (mês, direção) sorteados entre barras que tocam a Wall e fecham defendendo."""
    real = defaultdict(int)
    for date in dates:
        for s in signals_for(sim.days[date], c):
            real[(date[:7], s[1])] += 1
    pool = defaultdict(list)
    for date in dates:
        for s in sim.days[date]["pool"][c["R"]]:
            pool[(date[:7], s[1])].append((date, s))
    rnd = random.Random(seed)
    res = []
    for _ in range(N_PLACEBO):
        pick = defaultdict(list)
        for key, n in real.items():
            cand = pool.get(key, [])
            for date, s in rnd.sample(cand, min(n, len(cand))):
                pick[date].append(s)
        trs = sim.trades(c, ei, dates, sig_override={d: sorted(pick.get(d, [])) for d in dates})
        res.append(stats(trs if mode == "LIVRE" else one_at_a_time(trs))["ret_dd"])
    return res


def run_asset(asset):
    t0 = datetime.now()
    days = load(asset)
    sim = Sim(asset, days)
    is_dates = sorted(d for d in days if d <= IS_END)
    oos_dates = sorted(d for d in days if d > IS_END)
    print(f"{asset}: {len(is_dates)} dias IS, {len(oos_dates)} OOS · preparo {datetime.now() - t0}", flush=True)
    G = plateau(grid(asset, sim, is_dates), asset)
    G.to_csv(os.path.join(OUT, f"grid_is_{asset}.csv"), index=False)
    print(f"{asset}: grade IS {len(G)} linhas · {datetime.now() - t0}", flush=True)
    picks = []
    for (fam, mode), g in G.groupby(["fam", "mode"]):
        top = g.sort_values(["plateau", "ops"], ascending=False).iloc[0]
        c = dict(fam=fam, k=top["k"], R=top["R"], L=int(top["L"]), conf=top["conf"], z=top["z"], N=int(top["N"]))
        ei = int(top["ei"])
        pl = placebo(sim, c, ei, mode, is_dates) if (top["plateau"] > 0 or fam == "E4_ABS") else []
        p = (1 + sum(x >= top["ret_dd"] for x in pl)) / (1 + len(pl)) if pl else 1.0
        ok_is = bool(top["plateau"] > 0 and p < P_MAX)
        picks.append(dict(asset=asset, fam=fam, mode=mode, cfg=c, ei=ei, exit=EXITS[ei], plateau=float(top["plateau"]),
                          is_point=float(top["ret_dd"]), is_ops=int(top["ops"]), placebo_med=float(np.median(pl)) if pl else None,
                          placebo_p=p, ok_is=ok_is))
        print(f"{asset} {fam:15s} {mode:10s} platô {top['plateau']:.2f} ponto {top['ret_dd']:.2f} "
              f"({int(top['ops'])} tr) placebo p={p:.3f} → {'OK' if ok_is else 'não'}", flush=True)
    return asset, picks, sim


def main():
    os.makedirs(OUT, exist_ok=True)
    lock = os.path.join(OUT, "oos_log.json")
    if os.path.exists(lock):
        raise SystemExit("OOS já executado.")
    with mp.Pool(2) as pool:
        res = pool.map(run_asset_is_only, ["WIN", "WDO"])
    picks = [p for _, ps in res for p in ps]
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"), "picks": picks},
              open(lock, "w", encoding="utf-8"), indent=1, default=str)
    with mp.Pool(2) as pool:
        out = pool.map(run_asset_oos, [(a, [p for p in picks if p["asset"] == a]) for a in ("WIN", "WDO")])
    rows, trades = [], []
    for asset, rr, tt in out:
        rows += rr
        trades += tt
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "oos_results.csv"), index=False)
    pd.DataFrame(trades).to_csv(os.path.join(OUT, "oos_trades.csv"), index=False)
    log = json.load(open(lock, encoding="utf-8"))
    log["oos"] = rows
    json.dump(log, open(lock, "w", encoding="utf-8"), indent=1, default=str)
    with pd.option_context("display.width", 260, "display.max_columns", 40):
        print(R.drop(columns=["cfg"]).to_string(index=False))


def run_asset_is_only(asset):
    a, picks, _ = run_asset(asset)
    return a, picks


def run_asset_oos(args):
    asset, picks = args
    days = load(asset)
    sim = Sim(asset, days)
    is_dates = sorted(d for d in days if d <= IS_END)
    oos_dates = sorted(d for d in days if d > IS_END)
    rows, trades = [], []
    for p in picks:
        if not (p["ok_is"] or p["fam"] == "E4_ABS"):
            continue
        c = dict(p["cfg"])
        for part, dates in (("IS", is_dates), ("OOS", oos_dates)):
            trs = sim.trades(c, p["ei"], dates)
            trs = trs if p["mode"] == "LIVRE" else one_at_a_time(trs)
            s = stats(trs)
            if part == "IS":
                s_is = s
            else:
                n_pos, n_m = map(int, s["pos_m"].split("/"))
                ok = s["pf"] >= 1.2 and s["net"] > 0 and n_pos * 2 >= n_m
                rows.append(dict(asset=asset, fam=p["fam"], mode=p["mode"], cfg=c, exit=exit_name(p["exit"]),
                                 placebo_p=p["placebo_p"], aprovado_is=p["ok_is"],
                                 **{f"is_{k}": v for k, v in s_is.items()}, **{f"oos_{k}": v for k, v in s.items()},
                                 aprovado_oos=bool(ok and p["ok_is"])))
            trades += [dict(asset=asset, fam=p["fam"], mode=p["mode"], part=part, date=t[0], entry_idx=t[1],
                            exit_idx=t[2], exit_time=t[3], brl=t[4], dir=t[5]) for t in trs]
    return asset, rows, trades


if __name__ == "__main__":
    main()
