"""
Absorção rápida na Wall + divergência v3 como entrada própria (só jan–jul; ago–nov não é lido nem impresso).
Absorção = `research.div_entry.bt_entry.absorption`: barra que encosta numa Wall/MidWall (até R) e fecha do lado
defendido, com Wyckoff a favor, institucional passivo a favor e varejo contra.
Variantes: absorção até N ∈ {0, 3, 6, 12} barras depois de uma divergência v3 no mesmo sentido, e absorção sozinha
(controle), com 2 raios de Wall. Simulação = research.div3m.bt_div3m (M1 tick a tick, 4 entradas × 120 saídas).
Uso: python -m research.div_v3.bt_abs_v3_is
"""
from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div3m import bt_div3m as BT  # noqa: E402
from research.div3m import investigar as INV  # noqa: E402
from research.div_v3 import sinais as SV3  # noqa: E402

OUT = os.path.join(ROOT, "research", "div_v3", "results")
RADII = {"WIN": (40.0, 100.0), "WDO": (1.5, 4.0)}
VARIANTS = [("abs_div", n) for n in (0, 3, 6, 12)] + [("abs", None)]


def run(args):
    asset, mode, n, r = args
    INV.load = SV3.load
    SV3.MODE, SV3.ABS_N = mode, (n or 0)
    SV3.ABS_R = {**SV3.ABS_R, asset: r}
    P, F, X, E, DS, mt5 = BT.prepare(asset)
    sp = BT.SPEC[asset]
    name = f"absorção sozinha R{r:g}" if mode == "abs" else f"absorção até {n} barras após div v3 R{r:g}"
    rows = []
    for en, (T, pn, xt) in E.items():
        sel = np.where(T["is"].values)[0]
        for xi, x in enumerate(X):
            ct = 2 if x["tp"] == "2lotes" else 1
            for md, cap in itertools.product(("LIVRE", "UM_POR_VEZ"), (False, True)):
                acc = BT.mgmt(sel, T.tm.values, T.di.values, pn[:, xi], xt[:, xi], md, cap, sp["cap"] * ct)
                s = BT.st(acc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)
                rows.append(dict(asset=asset, variante=name, entrada=en, saida=BT.xname(x, asset), mode=md, cap=cap,
                                 **s, score=BT.score(s)))
    n_is = int((P.date <= BT.IS_END).sum())
    return name, asset, n_is, pd.DataFrame(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [(a, m, n, r) for a in ("WIN", "WDO") for (m, n) in VARIANTS for r in RADII[a]]
    with mp.Pool(4) as pool:
        res = pool.map(run, jobs)
    G = pd.concat([g for *_, g in res])
    G.to_csv(os.path.join(OUT, "grid_is_abs_v3.csv.gz"), index=False, compression="gzip")
    rows = []
    for name, asset, n_is, g in res:
        ok = g[g.score > 0]
        best = g.sort_values(["pf"], ascending=False)
        b150 = g[g.ops >= 150].sort_values("pf", ascending=False)
        rows.append(dict(ativo=asset, variante=name, sinais_is=n_is, sinais_dia=round(n_is / 143, 2),
                         pf_mediano=round(g.pf.median(), 2), pf_max=best.pf.iloc[0],
                         pf_max_150tr=b150.pf.iloc[0] if len(b150) else np.nan,
                         rdd_max_150tr=b150.rdd.max() if len(b150) else np.nan,
                         aprovaveis=len(ok), configs=len(g)))
    S = pd.DataFrame(rows).sort_values(["ativo", "variante"])
    S.to_csv(os.path.join(OUT, "resumo_abs_v3_is.csv"), index=False)
    print(S.to_string(index=False))
    cols = ["variante", "entrada", "saida", "mode", "cap", "ops", "wr", "pf", "net", "dd", "rdd", "meses", "net_h1", "net_h2"]
    for a in ("WIN", "WDO"):
        top = G[(G.asset == a) & (G.score > 0)].sort_values("score", ascending=False)
        print(f"\n### {a}: melhores com ≥150 trades e lucro nas duas metades ({len(top)})")
        print(top[cols].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
