# -*- coding: utf-8 -*-
"""
Robustez da configuração escolhida na rodada 3 (WIN v2.1). Período completo (02/01–06/11/2026).
  1. Placebo de barras: barras MT5 sorteadas (mesmo nº por mês × direção) que passam nos MESMOS filtros de contexto
     (10:00–15:55, ext50 > −0,5, slope50 > −0,5), mesma saída e gestão. 300 sorteios.
  2. Sem divergência: motor v2.1 com limiar de onda −∞ (qualquer par de pivôs), mesmas âncoras, gatilho e filtros.
  3. Sem Opção C: entra na primeira barra da janela do gatilho, sem condição.
  4. Direção invertida.  5. Custo dobrado + 2 ticks de slippage.  6. Só M5 (stop primeiro na barra).
Uso: python robust.py → results/robust.json
"""
import json, os, random, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import defaultdict
import numpy as np, pandas as pd
import bt, modulo as M
from bt import mgmt

CFG = dict(sl=200.0, tp=None, tmax=12, be=(180.0, 20.0))
COL, XT = "pnl_X", "xt_X"


def filt(T):
    return T.ok & ~T.super & (T.seq <= 1) & (T.tm >= 600) & (T.tm < 960) & (T.ext50 > -0.5) & (T.slope50 > -0.5)


def run_exit(T, DS, inv=False, cost_mult=1.0, slip_ticks=1, m5_only=False):
    p, xt = np.full(len(T), np.nan), np.full(len(T), -1)
    x = bt.X["WIN"]
    for i, r in enumerate(T.itertuples()):
        if not r.ok:
            continue
        D = DS[r.date]
        if m5_only:
            D = dict(D, fb=np.ones_like(D["fb"]))
        d = -r.dir if inv else r.dir
        pts, t = bt.sim(*bt._args(D), D["u30"], int(r.e), r.ep, d, CFG["sl"], r.ep + d * 1e9, False, 0.0, 0.0, 0.0,
                        CFG["be"][0], CFG["be"][1], CFG["tmax"], x["tick"] * slip_ticks)
        p[i], xt[i] = (pts - x["cost"] * cost_mult) * x["brl"], t
    T = T.copy()
    T[COL], T[XT] = p, xt
    return T


def evaluate(T, mask=None):
    m = filt(T) if mask is None else mask
    q = mgmt(T[m & T[COL].notna()].sort_values(["date", "tm"]), COL, XT, "UM_POR_VEZ")
    return bt.stats(q, COL, XT), q


def signals_mode(trigger="ab", k=None):
    old_t, old_k = M.TRIGGER, M.COMMON["k_v21"]
    M.TRIGGER = trigger
    if k is not None:
        M.COMMON["k_v21"] = k
    try:
        return bt.signals("WIN", "v2.1")
    finally:
        M.TRIGGER, M.COMMON["k_v21"] = old_t, old_k


def placebo_bars(DS, ref, n_draw=300, seed=7):
    """Pool de barras com o mesmo contexto; sorteio pareado por mês × direção."""
    rows = []
    for d, D in DS.items():
        for e in range(1, len(D["o5"])):
            tm = int(D["tm5"][e])
            if not (600 <= tm < 960):
                continue
            half = max(D["u50"][e] - D["c50"][e], 5.0)
            for dr in (1, -1):
                ext = -dr * (D["c5"][e - 1] - D["c50"][e]) / half
                slp = dr * (D["c50"][e] - D["c50"][max(0, e - 6)]) / half
                if ext > -0.5 and slp > -0.5:
                    rows.append(dict(date=d, tm=tm, e=e, dir=dr, ep=float(D["o5"][e]), ok=True))
    P = pd.DataFrame(rows)
    P = run_exit(P, DS)
    P["mon"] = P.date.str[:7]
    pool = defaultdict(list)
    for i, r in enumerate(P.itertuples()):
        pool[(r.mon, r.dir)].append(i)
    want = defaultdict(int)
    for r in ref.itertuples():
        want[(r.date[:7], r.dir)] += 1
    rng = random.Random(seed)
    out = []
    for _ in range(n_draw):
        pick = sorted(j for kk, n in want.items() for j in rng.sample(pool[kk], min(n, len(pool[kk]))))
        q = mgmt(P.iloc[pick].sort_values(["date", "tm"]), COL, XT, "UM_POR_VEZ")
        out.append(bt.stats(q, COL, XT))
    return out, len(P)


def main():
    DS = bt.market("WIN")
    base = bt.simulate("WIN", signals_mode("ab"), DS, exits=())
    T = run_exit(base, DS)
    s0, q0 = evaluate(T)
    res = {"escolhida": s0}
    print("escolhida:", s0, flush=True)
    q0[["date", "time_in", "dir", "esp", "sub", "ep", COL, XT]].to_csv(os.path.join(bt.HERE, "results", "trades_escolhida.csv"),
                                                                       index=False)
    pb, npool = placebo_bars(DS, q0)
    r = np.array([x["rdd"] for x in pb]); nets = np.array([x["net"] for x in pb])
    res["placebo_barras"] = dict(pool=npool, draws=len(pb), rdd_med=float(np.median(r)), rdd_p95=float(np.quantile(r, .95)),
                                 net_med=float(np.median(nets)), p_rdd=float((1 + (r >= s0["rdd"]).sum()) / (1 + len(r))),
                                 p_net=float((1 + (nets >= s0["net"]).sum()) / (1 + len(nets))))
    print("placebo barras:", res["placebo_barras"], flush=True)
    for lab, kw in (("sem_divergencia", dict(trigger="ab", k=-1e18)), ("sem_opcao_c", dict(trigger="none"))):
        S = bt.simulate("WIN", signals_mode(**kw), DS, exits=())
        res[lab], _ = evaluate(run_exit(S, DS))
        print(lab, res[lab], flush=True)
    res["invertida"], _ = evaluate(run_exit(base, DS, inv=True))
    res["custo_x2_slip2"], _ = evaluate(run_exit(base, DS, cost_mult=2.0, slip_ticks=2))
    res["so_M5"], _ = evaluate(run_exit(base, DS, m5_only=True))
    for k in ("invertida", "custo_x2_slip2", "so_M5"):
        print(k, res[k])
    mon = q0.groupby(q0.date.str[:7])[COL].agg(["size", "sum"]).round(0)
    res["meses"] = mon.reset_index().to_dict("records")
    print(mon.to_string())
    json.dump(res, open(os.path.join(bt.HERE, "results", "robust.json"), "w", encoding="utf-8"), indent=1, default=str)


if __name__ == "__main__":
    main()
