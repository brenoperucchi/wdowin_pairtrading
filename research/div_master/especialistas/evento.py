# -*- coding: utf-8 -*-
"""Estudo de evento dos gatilhos (período completo): retorno à frente em 6/12/24 barras MT5, líquido de custo,
por característica disponível no sinal. Só leitura dos caches de busca.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import bt, busca as B, modulo as M

def fwd(asset, T, DS):
    c = bt.X[asset]["cost"]
    for k in (6, 12, 24):
        v = []
        for r in T.itertuples():
            D = DS[r.date]; n = len(D["c5"]); j = min(int(r.e) + k - 1, n - 1)
            v.append(r.dir * (D["c5"][j] - r.ep) - c)
        T[f"r{k}"] = v
    T["hora"] = (T.tm // 60).astype(int)
    T["wdr"] = pd.qcut(T.wd_ratio, 4, labels=False, duplicates="drop")
    T["ext"] = pd.cut(T.ext50, [-9, -0.5, 0, 0.5, 1, 9])
    T["slp"] = pd.cut(T.slope50, [-9, -0.5, 0, 0.5, 9])
    T["dmv"] = pd.cut(T.dmov, [-99, -2, -1, 0, 1, 99])
    T["seqc"] = T.seq.clip(upper=3)
    return T

pd.set_option("display.width", 220)
for a in ("WIN", "WDO"):
    DS = bt.market(a)
    for e in ("v3", "v2.1", "v3.1"):
        T = B.load(a, e); T = fwd(a, T[T.ok].copy(), DS)
        T["half"] = np.where(T.date <= bt.IS_END, "IS", "OOS")
        print(f"\n######## {a} {e} n={len(T)} r12 médio={T.r12.mean():.1f}")
        for col in ("esp", "sub", "lag", "super", "hora", "wdr", "ext", "slp", "dmv", "seqc", "dir"):
            g = T.groupby([col, "half"], observed=True).r12.agg(["size", "mean"]).unstack("half").round(1)
            print(f"-- {col}\n{g.to_string()}")
        T.to_pickle(os.path.join(B.RES, f"evento_{a}_{e.replace('.','')}.pkl"))
