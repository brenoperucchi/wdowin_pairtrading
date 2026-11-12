# -*- coding: utf-8 -*-
"""Rodada 2: WIN v2.1 — combinações de 2 e 3 filtros × grade de saídas de r1 × gestão. Platô = mediana do Ret/DD
das vizinhas (troca de 1 filtro, SL vizinho, tempo vizinho)."""
import sys, os, itertools, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import bt, busca as B, r1

asset, eng = (sys.argv[1] if len(sys.argv) > 1 else "WIN"), (sys.argv[2] if len(sys.argv) > 2 else "v2.1")
T = pd.read_pickle(os.path.join(B.RES, f"r1_{asset}_{eng.replace('.','')}.pkl")).copy()
T = T[T.ok].reset_index(drop=True)
FL = {
    "nao_super": ~T.super, "seq0": T.seq == 0, "seq01": T.seq <= 1, "lag12": T.lag <= 2, "sem09h": T.tm >= 600,
    "so_WALL": T.esp == "WALL", "dia_favor": T.dmov > 0, "tend_favor": T.slope50 > 0, "sem_dup": ~T.dup,
}
FN = list(FL)
combos = [c for n in (1, 2, 3) for c in itertools.combinations(FN, n)
          if not ({"seq0", "seq01"} <= set(c))]
EX = ["A", "B"] + [r1.gname(g) for g in r1.GRID[asset]]

def mgmt(Tf, col, xt, mode):
    if mode == "LIVRE":
        return Tf
    keep, day, last = [], None, -1
    for i, r in zip(Tf.index, Tf.itertuples()):
        if r.date != day:
            day, last = r.date, -1
        if r.tm <= last:
            continue
        keep.append(i); last = getattr(r, xt) if False else Tf.at[i, xt]
    return Tf.loc[keep]

rows = []
for c in combos:
    m = np.ones(len(T), bool)
    for f in c:
        m &= FL[f].values
    Tf = T[m].sort_values(["date", "tm"])
    for x in EX:
        for mode in ("LIVRE", "UM_POR_VEZ"):
            q = mgmt(Tf[Tf[f"pnl_{x}"].notna()], f"pnl_{x}", f"xt_{x}", mode)
            s = bt.stats(q, f"pnl_{x}", f"xt_{x}")
            rows.append(dict(rodada="r2", motor=eng, esp="ambos", saida=x, filtro="+".join(c), gestao=mode, ativo=asset, **s))
R = pd.DataFrame(rows)
R["score"] = np.where((R.ops >= 150) & (R.h1 > 0) & (R.h2 > 0) & (R.oos > 0), R.rdd, 0.0)
# platô
key = {(r.filtro, r.saida, r.gestao): r.score for r in R.itertuples()}
def neigh(r):
    fs = set(r.filtro.split("+")); out = [r.score]
    for f in FN:
        nf = fs ^ {f}
        if 1 <= len(nf) <= 3:
            k = ("+".join([x for x in FN if x in nf]), r.saida, r.gestao)
            if k in key: out.append(key[k])
    if r.saida.startswith("G|"):
        _, sl, tp, tmx, be = r.saida.split("|")
        sls = ["SL200", "SL300", "SL400"] if asset == "WIN" else ["SL6", "SL10", "SL14"]
        tms = ["T6", "T12", "T24"]
        for lst, cur, pos in ((sls, sl, 1), (tms, tmx, 3)):
            i = lst.index(cur)
            for j in (i - 1, i + 1):
                if 0 <= j < len(lst):
                    p = r.saida.split("|"); p[pos] = lst[j]
                    k = (r.filtro, "|".join(p), r.gestao)
                    if k in key: out.append(key[k])
    return float(np.median(out))
R["plato"] = [neigh(r) for r in R.itertuples()]
B.log(R.drop(columns=["score", "plato"]).to_dict("records"))
R.to_csv(os.path.join(B.RES, f"r2_{asset}_{eng.replace('.','')}.csv.gz"), index=False, compression="gzip")
pd.set_option("display.width", 260)
cols = ["filtro", "saida", "gestao", "ops", "wr", "pf", "net", "dd", "rdd", "plato", "meses", "h1", "h2", "oos", "rdd_is", "rdd_oos"]
print("por Ret/DD (robustas):"); print(R[R.score > 0].sort_values("rdd", ascending=False)[cols].head(25).to_string(index=False))
print("\npor platô:"); print(R.sort_values(["plato", "rdd"], ascending=False)[cols].head(25).to_string(index=False))
print("configs:", len(R), "robustas:", int((R.score > 0).sum()), "rdd>10 robustas:", int((R.score > 10).sum()))
