"""
Rompimento da Wall com o maior fluxo do dia (definição do usuário, 11/11/2026) como entrada própria — só jan–jul.
Variantes: onda no máximo do dia ("wave"), força da barra no máximo ("force") e sem condição de fluxo ("none", controle).
Simulação = research.div3m.bt_div3m (M1 tick a tick, 4 entradas × 120 saídas × gestão). Ago–nov não é lido.
Uso: python -m research.div_v3.bt_rom_is
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


def run(args):
    asset, flow = args
    INV.load = SV3.load
    SV3.MODE, SV3.ROM_FLOW = "rom", flow
    P, F, X, E, DS, mt5 = BT.prepare(asset)
    sp = BT.SPEC[asset]
    rows = []
    for en, (T, pn, xt) in E.items():
        sel = np.where(T["is"].values)[0]
        for xi, x in enumerate(X):
            ct = 2 if x["tp"] == "2lotes" else 1
            for md, cap in itertools.product(("LIVRE", "UM_POR_VEZ"), (False, True)):
                acc = BT.mgmt(sel, T.tm.values, T.di.values, pn[:, xi], xt[:, xi], md, cap, sp["cap"] * ct)
                s = BT.st(acc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)
                rows.append(dict(asset=asset, fluxo=flow, entrada=en, saida=BT.xname(x, asset), mode=md, cap=cap, **s,
                                 score=BT.score(s)))
    Pi = P[P.date <= BT.IS_END]
    raw = {h: (len(X_), round(X_.r12.mean(), 1), round(X_.r24.mean(), 1), round(100 * (X_.r12 > 0).mean())) for h, X_ in Pi.groupby("half")}
    return asset, flow, len(Pi), raw, pd.DataFrame(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    with mp.Pool(4) as pool:
        res = pool.map(run, [(a, f) for a in ("WIN", "WDO") for f in ("wave", "force", "none")])
    G = pd.concat([g for *_, g in res])
    G.to_csv(os.path.join(OUT, "grid_is_rom.csv.gz"), index=False, compression="gzip")
    for asset, flow, n, raw, g in res:
        b = g[g.ops >= 150].sort_values("pf", ascending=False)
        print(f"{asset} fluxo={flow:5s}: {n} sinais ({n / 143:.1f}/dia) | bruto H1/H2 (n, r12, r24, acerto%) {raw} | PF mediano {g.pf.median():.2f} "
              f"| melhor PF ≥150tr {b.pf.iloc[0] if len(b) else float('nan')} | aprováveis {int((g.score > 0).sum())}/{len(g)}")
    cols = ["fluxo", "entrada", "saida", "mode", "cap", "ops", "wr", "pf", "net", "dd", "rdd", "meses", "net_h1", "net_h2"]
    for a in ("WIN", "WDO"):
        top = G[(G.asset == a) & (G.score > 0)].sort_values("score", ascending=False)
        print(f"\n### {a}: melhores aprováveis ({len(top)})")
        print(top[cols].head(6).to_string(index=False))


if __name__ == "__main__":
    main()
