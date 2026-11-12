# -*- coding: utf-8 -*-
"""Rodada 1: WIN (motores v2.1, v3.1, v3) — filtros de 1 fator × saídas A, B e grade G. Tudo vai ao variations_log."""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import bt, busca as B

GRID = {"WIN": [dict(sl=sl, tp=tp, tmax=tm, be=be) for sl, tp, tm, be in itertools.product(
            (200.0, 300.0, 400.0), (None, 300.0, 500.0, 750.0), (6, 12, 24), (None, (180.0, 20.0)))],
        "WDO": [dict(sl=sl, tp=tp, tmax=tm, be=be) for sl, tp, tm, be in itertools.product(
            (6.0, 10.0, 14.0), (None, 6.0, 10.0, 16.0), (6, 12, 24), (None, (5.0, 1.0)))]}

def gname(g):
    return f"G|SL{g['sl']:g}|TP{g['tp'] or 0:g}|T{g['tmax']}|{'BE' if g['be'] else 'sBE'}"

def add_grid(asset, T, DS):
    for g in GRID[asset]:
        k = gname(g); p = np.full(len(T), np.nan); xt = np.full(len(T), -1)
        for i, r in enumerate(T.itertuples()):
            if not r.ok: continue
            p[i], xt[i] = bt.exit_G(asset, DS[r.date], int(r.e), r.ep, r.dir, g["sl"], g["tp"], g["tmax"], g["be"])
        T[f"pnl_{k}"], T[f"xt_{k}"] = p, xt
    return T

FILTERS = {
    "so_VIOL": lambda T: T.ok & (T["sub"] == "VIOL"),
    "nenhum": lambda T: T.ok,
    "nao_super": lambda T: T.ok & ~T.super,
    "lag1": lambda T: T.ok & (T.lag == 1),
    "sem09h": lambda T: T.ok & (T.tm >= 600),
    "seq0": lambda T: T.ok & (T.seq == 0),
    "so_WALL": lambda T: T.ok & (T.esp == "WALL"),
    "so_EXTREMO": lambda T: T.ok & (T.esp == "EXTREMO"),
    "sem_dup": lambda T: T.ok & ~T.dup,
}

if __name__ == "__main__":
    asset = sys.argv[1] if len(sys.argv) > 1 else "WIN"
    DS = bt.market(asset)
    rows = []
    for e in ("v2.1", "v3.1", "v3"):
        T = add_grid(asset, B.load(asset, e), DS)
        T.to_pickle(os.path.join(B.RES, f"r1_{asset}_{e.replace('.','')}.pkl"))
        cols = ["A", "B"] + [gname(g) for g in GRID[asset]]
        for fn, f in FILTERS.items():
            m = f(T)
            for c in cols:
                s = bt.stats(T[m], f"pnl_{c}", f"xt_{c}")
                rows.append(dict(rodada="r1", motor=e, esp="ambos" if fn not in ("so_WALL", "so_EXTREMO") else fn[3:],
                                 saida=c, filtro=fn, ativo=asset, **s))
        print(asset, e, "ok", flush=True)
    B.log(rows)
    R = pd.DataFrame(rows)
    R["ok"] = (R.ops >= 150) & (R.h1 > 0) & (R.h2 > 0) & (R.oos > 0)
    pd.set_option("display.width", 250)
    cols = ["motor", "filtro", "saida", "ops", "wr", "pf", "net", "dd", "rdd", "meses", "h1", "h2", "oos", "rdd_is", "rdd_oos"]
    print(R[R.ok].sort_values("rdd", ascending=False)[cols].head(40).to_string(index=False))
    print("configs:", len(R), "robustas (>=150 tr, H1/H2/OOS +):", int(R.ok.sum()))
