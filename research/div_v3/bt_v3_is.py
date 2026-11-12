"""
Etapa A (só jan–jul): entrar em TODA divergência v3, sem filtro, com as 4 entradas e as 120 saídas do div3m
(simulação tick a tick em M1, regras MT5). Não lê nem imprime ago–nov.
Uso: python -m research.div_v3.bt_v3_is
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


def run(asset):
    INV.load = SV3.load                      # troca só a fonte de sinais
    P, F, X, E, DS, mt5 = BT.prepare(asset)
    sp = BT.SPEC[asset]
    rows, trades = [], []
    for en, (T, pn, xt) in E.items():
        isv = T["is"].values
        sel = np.where(isv)[0]
        day, mon, h1, tm = T.di.values, T.mon.values, T.h1.values, T.tm.values
        for xi, x in enumerate(X):
            ct = 2 if x["tp"] == "2lotes" else 1
            for mode, cap in itertools.product(("LIVRE", "UM_POR_VEZ"), (False, True)):
                acc = BT.mgmt(sel, tm, day, pn[:, xi], xt[:, xi], mode, cap, sp["cap"] * ct)
                s = BT.st(acc, pn[:, xi], day, mon, h1)
                rows.append(dict(asset=asset, entrada=en, xi=xi, saida=BT.xname(x, asset), mode=mode, cap=cap, **s,
                                 score=BT.score(s)))
        # P&L por sinal (IS) para quebrar por tipo, saída de referência = mediana de PF entre saídas, modo LIVRE
        T2 = T[isv].copy()
        for xi in range(len(X)):
            T2[f"x{xi}"] = pn[isv, xi]
        trades.append((en, T2))
    G = pd.DataFrame(rows)
    G.to_csv(os.path.join(OUT, f"grid_is_sem_filtro_{asset}.csv"), index=False)
    return asset, G, trades, P[P.date <= BT.IS_END]


def main():
    os.makedirs(OUT, exist_ok=True)
    with mp.Pool(2) as pool:
        res = pool.map(run, ["WIN", "WDO"])
    for asset, G, trades, P in res:
        print(f"\n===== {asset} (jan–jul) — {len(P)} divergências v3, sem filtro")
        for en in BT.ENTRADAS:
            g = G[(G.entrada == en) & (G["mode"] == "LIVRE") & (~G.cap)]
            print(f"  {en:16s} trades {int(g.ops.median()):4d} | PF mediana {g.pf.median():.2f} · melhor {g.pf.max():.2f} · "
                  f"pior {g.pf.min():.2f} | saídas com lucro {int((g.net > 0).sum())}/{len(g)} | "
                  f"lucro nas 2 metades {int(((g.net_h1 > 0) & (g.net_h2 > 0)).sum())}/{len(g)}")
        ok = G[G.score > 0].sort_values("score", ascending=False)
        print(f"  configs com ≥150 trades e lucro nas 2 metades: {len(ok)}/{len(G)}")
        cols = ["entrada", "saida", "mode", "cap", "ops", "wr", "pf", "net", "dd", "rdd", "meses", "net_h1", "net_h2"]
        if len(ok):
            print(ok[cols].head(8).to_string(index=False))
        # quebra por tipo de sinal (entrada E0, todas as saídas: PF médio)
        en, T2 = trades[0]
        X = [c for c in T2.columns if c.startswith("x") and c[1:].isdigit()]
        Pm = P.reset_index(drop=True)
        T2 = T2.merge(Pm[["date", "tm", "direction", "wall_kind", "hora", "seq"]].rename(columns={"tm": "tm_sig"}),
                      left_on=["date", "direction"], right_on=["date", "direction"], how="left")
        T2 = T2[T2.tm - T2.tm_sig == 0] if "tm_sig" in T2 else T2

        def pf_row(df):
            v = df[X].values
            g, l = np.clip(v, 0, None).sum(0), -np.clip(v, None, 0).sum(0)
            pf = np.where(l > 0, g / np.maximum(l, 1e-9), 99)
            return f"n={len(df):4d} PF mediana entre saídas {np.median(pf):.2f} (melhor {pf.max():.2f})"
        print("  Por tipo (entrada E0):")
        for col in ("wall_kind", "hora"):
            for k, df in T2.groupby(col):
                print(f"    {col}={k}: {pf_row(df)}")
        print(f"    1ª do dia no sentido: {pf_row(T2[T2.seq == 0])}")
        print(f"    demais:               {pf_row(T2[T2.seq > 0])}")


if __name__ == "__main__":
    main()
