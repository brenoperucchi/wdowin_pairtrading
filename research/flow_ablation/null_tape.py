# -*- coding: utf-8 -*-
"""Nulo dos pregões de tape: HP_PROJ com a força embaralhada dentro do pregão (30 sementes, var_HPS_*.pkl).
Compara o R$ nos pregões de tape de cada variante H_/HP_ com a distribuição do nulo. Saída: results/nulo_tape.csv/.md"""
import os, sys, glob, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flows2 as F2
RES = os.path.join(HERE, "results")
STRATS = ["E22", "V21", "C1a_BRK_WIN", "SYM_DIV_WIN", "V1a_DIV_WDO", "SYM_DIV_WDO"]
ASSET = {"E22": "WIN", "V21": "WIN", "C1a_BRK_WIN": "WIN", "SYM_DIV_WIN": "WIN", "V1a_DIV_WDO": "WDO", "SYM_DIV_WDO": "WDO"}
V = {}
for p in glob.glob(os.path.join(RES, "var_*.pkl")):
    n = os.path.basename(p)[4:-4]
    if n in ["A_BASE"] + F2.TAPE_VARS or n.startswith("HPS_"):
        V[n] = pickle.load(open(p, "rb"))
SG = V["A_BASE"]["SIG"]
days = {a: sorted(set(F2.tape_comp(a)) & set(SG[SG.asset == a].date)) for a in ("WIN", "WDO")}


def row(v):
    r = dict(var=v)
    tot = 0.0
    for s in STRATS:
        T = V[v][s]
        x = float(T[T.date.isin(days[ASSET[s]])].brl.sum())
        r[s] = x
        if s != "V21":
            tot += x
    r["soma"] = tot
    S = V[v]["SIG"]
    for a in ("WIN", "WDO"):
        g = S[(S.asset == a) & S.date.isin(days[a])]
        r[f"sig_{a}"] = float(g.pts.mean())
    return r


R = pd.DataFrame([row(v) for v in V])
nul = R[R["var"].str.startswith("HPS_")]
obs = R[~R["var"].str.startswith("HPS_")].copy()
L = [f"### Nulo dos pregões de tape ({len(nul)} sementes: força HP_PROJ embaralhada dentro de cada pregão de tape)",
     "| Variante | E22 R$ | SYM_WDO R$ | V1a_WDO R$ | Soma (sem V21) R$ | percentil da soma no nulo | sinais WIN média pts | percentil | sinais WDO média pts | percentil |",
     "| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |"]
for c in ("E22", "SYM_DIV_WDO", "V1a_DIV_WDO", "soma", "sig_WIN", "sig_WDO"):
    obs[f"pct_{c}"] = [float((nul[c] < x).mean() + 0.5 * (nul[c] == x).mean()) for x in obs[c]]
for r in obs.sort_values("var").itertuples():
    L.append(f"| {r.var} | {r.E22:.0f} | {r.SYM_DIV_WDO:.0f} | {r.V1a_DIV_WDO:.0f} | {r.soma:.0f} | {100 * r.pct_soma:.0f}% | "
             f"{r.sig_WIN:.1f} | {100 * r.pct_sig_WIN:.0f}% | {r.sig_WDO:.2f} | {100 * r.pct_sig_WDO:.0f}% |")
L.append(f"| **nulo** mediana [p5–p95] | {nul.E22.median():.0f} [{nul.E22.quantile(.05):.0f}–{nul.E22.quantile(.95):.0f}] | "
         f"{nul.SYM_DIV_WDO.median():.0f} | {nul.V1a_DIV_WDO.median():.0f} | {nul.soma.median():.0f} [{nul.soma.quantile(.05):.0f}–{nul.soma.quantile(.95):.0f}] | — | "
         f"{nul.sig_WIN.median():.1f} [{nul.sig_WIN.quantile(.05):.1f}–{nul.sig_WIN.quantile(.95):.1f}] | — | "
         f"{nul.sig_WDO.median():.2f} [{nul.sig_WDO.quantile(.05):.2f}–{nul.sig_WDO.quantile(.95):.2f}] | — |")
R.to_csv(os.path.join(RES, "nulo_tape.csv"), index=False)
open(os.path.join(RES, "nulo_tape.md"), "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
