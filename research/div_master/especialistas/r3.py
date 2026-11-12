# -*- coding: utf-8 -*-
"""Rodada 3: WIN v2.1, base nao_super+seq01+sem09h + subconjuntos de {ate15h, ext_ok, slope_ok, lag12} × saídas × gestão."""
import sys, os, itertools, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import bt, busca as B, r1


def mgmt(Tf, col, xt, mode):
    """Igual a r2.mgmt (cópia para não reexecutar r2 no import). UM_POR_VEZ: entrada só depois da saída anterior."""
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

T = pd.read_pickle(os.path.join(B.RES, "r1_WIN_v21.pkl")).copy()
T = T[T.ok].reset_index(drop=True)
base = (~T.super) & (T.seq <= 1) & (T.tm >= 600)
EXTRA = {"ate15h": T.tm < 960, "ext_ok": T.ext50 > -0.5, "slope_ok": T.slope50 > -0.5, "lag12": T.lag <= 2}
EX = ["A", "B"] + [r1.gname(g) for g in r1.GRID["WIN"]]
rows = []
for n in range(0, 5):
    for c in itertools.combinations(EXTRA, n):
        m = base.copy()
        for f in c:
            m &= EXTRA[f]
        Tf = T[m].sort_values(["date", "tm"])
        for x in EX:
            for mode in ("LIVRE", "UM_POR_VEZ"):
                q = mgmt(Tf[Tf[f"pnl_{x}"].notna()], f"pnl_{x}", f"xt_{x}", mode)
                s = bt.stats(q, f"pnl_{x}", f"xt_{x}")
                rows.append(dict(rodada="r3", motor="v2.1", esp="ambos", saida=x,
                                 filtro="+".join(("nao_super", "seq01", "sem09h") + c), gestao=mode, ativo="WIN", **s))
R = pd.DataFrame(rows)
R["score"] = np.where((R.ops >= 150) & (R.h1 > 0) & (R.h2 > 0) & (R.oos > 0), R.rdd, 0.0)
B.log(R.drop(columns=["score"]).to_dict("records"))
R.to_csv(os.path.join(B.RES, "r3_WIN_v21.csv.gz"), index=False, compression="gzip")
pd.set_option("display.width", 260)
cols = ["filtro", "saida", "gestao", "ops", "wr", "pf", "net", "dd", "rdd", "meses", "h1", "h2", "oos", "rdd_is", "rdd_oos"]
print(R[R.score > 0].sort_values("rdd", ascending=False)[cols].head(30).to_string(index=False))
# mesma saída do melhor da r2 em todos os filtros
print("\nsaída G|SL300|TP0|T24|BE, UM_POR_VEZ:")
print(R[(R.saida == "G|SL300|TP0|T24|BE") & (R.gestao == "UM_POR_VEZ")][cols].to_string(index=False))
print("configs:", len(R), "rdd>10 robustas:", int((R.score > 10).sum()))
