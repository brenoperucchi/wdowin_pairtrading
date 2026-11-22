# -*- coding: utf-8 -*-
"""Tabelas da seção de componentes (player / forma de apregoar / lote): results/tabelas_componentes.md + CSVs."""
import os, sys, glob, json, pickle, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import flows as FL
import flows2 as F2
ROOT = FL.ROOT
sys.path[:0] = [os.path.join(ROOT, "research", "div_master", "setup_v32"), os.path.join(ROOT, "research", "div_master", "especialistas")]
from motor_addon import stats_table  # noqa: E402

RES = os.path.join(HERE, "results")
L = []


def P(s=""):
    L.append(s)


def fmt(x, n=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


V = {}
for p in glob.glob(os.path.join(RES, "var_*.pkl")):
    o = pickle.load(open(p, "rb"))
    V[o["variant"]] = o
STRATS = ["E22", "V21", "C1a_BRK_WIN", "SYM_DIV_WIN", "V1a_DIV_WDO", "SYM_DIV_WDO"]
ASSET = {"E22": "WIN", "V21": "WIN", "C1a_BRK_WIN": "WIN", "SYM_DIV_WIN": "WIN", "V1a_DIV_WDO": "WDO", "SYM_DIV_WDO": "WDO"}
REF = ["A_BASE", "X_WYCKOFF", "E1_PLAC_GEOM", "B_PURO", "D_MIX"]


def keyset(T):
    return set(zip(T.date, T.tm.astype(int), T.d.astype(int))) if len(T) else set()


def cart(v):
    C = pd.concat([V[v][s][["date", "tm", "xt", "brl"]] for s in STRATS if s != "V21"], ignore_index=True)
    return stats_table(C)


# ── 1) backtest completo dos componentes do .min ──
rows = []
P("### Backtest completo — componentes do .min (todos os pregões, jan–11/nov/2026)")
P("| Variante | E22 Ret/DD (lucro R$) | V21 Ret/DD (R$) | SYM_WDO Ret/DD (R$) | V1a_WDO Ret/DD (R$) | C1a | SYM_WIN | Carteira Ret/DD (R$) | Carteira jan–jul / ago–nov |")
P("| :-- | --: | --: | --: | --: | --: | --: | --: | :-- |")
for v in REF + F2.MIN_VARS:
    if v not in V:
        continue
    cells, rec = [], dict(var=v)
    for s in STRATS:
        st = stats_table(V[v][s])
        rec[f"{s}_rdd"], rec[f"{s}_net"], rec[f"{s}_n"] = st["rdd"], st["net"], st["ops"]
        rec[f"{s}_rdd_is"], rec[f"{s}_rdd_oos"] = st["rdd_is"], st["rdd_oos"]
    c = cart(v)
    rec.update(cart_rdd=c["rdd"], cart_net=c["net"], cart_is=c["rdd_is"], cart_oos=c["rdd_oos"])
    rows.append(rec)
    P(f"| {v} | **{fmt(rec['E22_rdd'])}** ({fmt(rec['E22_net'], 0)}) | {fmt(rec['V21_rdd'])} ({fmt(rec['V21_net'], 0)}) | "
      f"{fmt(rec['SYM_DIV_WDO_rdd'])} ({fmt(rec['SYM_DIV_WDO_net'], 0)}) | {fmt(rec['V1a_DIV_WDO_rdd'])} ({fmt(rec['V1a_DIV_WDO_net'], 0)}) | "
      f"{fmt(rec['C1a_BRK_WIN_rdd'])} | {fmt(rec['SYM_DIV_WIN_rdd'])} | **{fmt(c['rdd'])}** ({fmt(c['net'], 0)}) | {fmt(c['rdd_is'])} / {fmt(c['rdd_oos'])} |")
pd.DataFrame(rows).to_csv(os.path.join(RES, "componentes_min_backtest.csv"), index=False)
nul = os.path.join(RES, "nulo_embaralhado.csv")
if os.path.exists(nul):
    N = pd.read_csv(nul)
    P("p95 do nulo (força base embaralhada no pregão), Ret/DD: " + ", ".join(f"{s} {fmt(N[f'{s}_rdd'].quantile(.95))}" for s in STRATS))
P()

# ── 2) dias de tape: trades e sinais ──
TD = {a: sorted(F2.tape_comp(a).keys()) for a in ("WIN", "WDO")}
SG0 = V["A_BASE"]["SIG"]
days_in = {a: sorted(set(TD[a]) & set(SG0[SG0.asset == a].date)) for a in ("WIN", "WDO")}
P(f"### Pregões com tape completo dentro do período das estratégias: WIN {days_in['WIN']} · WDO {days_in['WDO']}")
P("Fora desses pregões as variantes H_/HP_ são idênticas à base; tudo abaixo é só o efeito NOS pregões de tape.")
P()
P("| Variante | E22 N / R$ | V21 N / R$ | C1a N / R$ | SYM_WIN N / R$ | V1a_WDO N / R$ | SYM_WDO N / R$ | Soma R$ | Trades da base mantidos |")
P("| :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: | --: |")
trows = []
for v in ["A_BASE"] + F2.TAPE_VARS:
    if v not in V:
        continue
    cells, tot, kept, nb = [], 0.0, 0, 0
    rec = dict(var=v)
    for s in STRATS:
        T = V[v][s]
        T = T[T.date.isin(days_in[ASSET[s]])]
        B = V["A_BASE"][s]
        B = B[B.date.isin(days_in[ASSET[s]])]
        kb = keyset(B)
        kept += len(kb & keyset(T))
        nb += len(kb)
        cells.append(f"{len(T)} / {fmt(T.brl.sum(), 0)}")
        rec[f"{s}_n"], rec[f"{s}_brl"] = len(T), float(T.brl.sum())
        if s != "V21":
            tot += T.brl.sum()
    rec["soma_sem_v21"] = tot
    trows.append(rec)
    P(f"| {v} | " + " | ".join(cells) + f" | {fmt(tot, 0)} | {kept}/{nb} |")
pd.DataFrame(trows).to_csv(os.path.join(RES, "componentes_tape_trades.csv"), index=False)
P("(Soma sem V21, que é pesquisa e se sobrepõe ao E22.)")
P()

P("### Sinais dos motores nos pregões de tape (entrada na abertura seguinte, saída 12 barras, líquido de custo, pts)")
P("| Variante | WIN v2.1 N / média | WIN v3.2 N / média | WIN divv2 N / média | WDO v2.1 | WDO v3.2 | WDO divv2 |")
P("| :-- | :-- | :-- | :-- | :-- | :-- | :-- |")
srows = []
for v in ["A_BASE"] + F2.TAPE_VARS:
    if v not in V:
        continue
    S = V[v]["SIG"]
    cells = []
    for a in ("WIN", "WDO"):
        for eng in ("v2.1", "v3.2", "divv2"):
            g = S[(S.asset == a) & (S.eng == eng) & S.date.isin(days_in[a])]
            cells.append(f"{len(g)} / {fmt(g.pts.mean(), 1 if a == 'WIN' else 2)}")
            srows.append(dict(var=v, asset=a, eng=eng, n=len(g), mean=g.pts.mean(), sd=g.pts.std()))
    P(f"| {v} | " + " | ".join(cells) + " |")
pd.DataFrame(srows).to_csv(os.path.join(RES, "componentes_tape_sinais.csv"), index=False)
P()

# ── 3) poder estatístico ──
P("### Quantos pregões de tape seriam precisos")
IC = pd.read_csv(os.path.join(RES, "ic_componentes.csv"))
pw = []
for a in ("WIN", "WDO"):
    g = IC[(IC.universo == "TAPE (todos)") & (IC.ativo == a)]
    nd = int(g.n_dias.iloc[0])
    se = float(g.pic1_se.median())
    for ic_t in (0.02, 0.03, 0.05):
        for tt, lab in ((2.0, "t=2 (1 teste)"), (3.3, "t=3,3 (Bonferroni ~45 componentes)")):
            need = nd * (tt * se / ic_t) ** 2
            pw.append(dict(ativo=a, ic=ic_t, criterio=lab, dias=need, se_obs=se, dias_obs=nd))
P("| Ativo | IC parcial alvo | Critério | Pregões necessários | (EP observado com N pregões) |")
P("| :-- | --: | :-- | --: | :-- |")
for r in pw:
    P(f"| {r['ativo']} | {fmt(r['ic'], 2)} | {r['criterio']} | {fmt(r['dias'], 0)} | {fmt(r['se_obs'], 3)} com {r['dias_obs']} |")
# estratégia: E22 e SYM_WDO
for s in ("E22", "SYM_DIV_WDO", "V1a_DIV_WDO"):
    B = V["A_BASE"][s]
    nd = B.date.nunique()
    SG = V["A_BASE"]["SIG"]
    days_tot = SG[SG.asset == ASSET[s]].date.nunique()
    tpd = len(B) / days_tot
    sd, mu = B.brl.std(), B.brl.mean()
    for frac in (0.25, 0.5):
        d = frac * mu
        ntr = (2.0 * sd / d) ** 2 * 2          # duas amostras independentes
        pw.append(dict(ativo=s, ic=np.nan, criterio=f"Δ média/trade = {int(frac * 100)}% da base", dias=ntr / tpd, se_obs=sd, dias_obs=days_tot))
        P(f"| {s} | — | Δ R$/trade = {int(frac * 100)}% de {fmt(mu, 0)} (DP {fmt(sd, 0)}, {fmt(tpd, 2)} trades/pregão) | {fmt(ntr / tpd, 0)} | trades necessários {fmt(ntr, 0)} |")
pd.DataFrame(pw).to_csv(os.path.join(RES, "poder_estatistico.csv"), index=False)
P()
open(os.path.join(RES, "tabelas_componentes.md"), "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
