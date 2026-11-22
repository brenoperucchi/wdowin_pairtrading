# -*- coding: utf-8 -*-
"""Agrega results/var_*.pkl, nulo e reajuste em tabelas (results/tabelas.md + CSVs)."""
import os, sys, glob, pickle, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import flows as FL
ROOT = FL.ROOT
sys.path[:0] = [os.path.join(ROOT, "research", "div_master", "setup_v32"), os.path.join(ROOT, "research", "div_master", "especialistas")]
from motor_addon import stats_table

RES = os.path.join(HERE, "results")
V = {}
for p in sorted(glob.glob(os.path.join(RES, "var_*.pkl"))):
    o = pickle.load(open(p, "rb"))
    V[o["variant"]] = o
ORDER = [v for v in FL.ALL if v in V]
STRATS = ["E22", "V21", "C1a_BRK_WIN", "SYM_DIV_WIN", "V1a_DIV_WDO", "SYM_DIV_WDO"]
L = []


def P(s=""):
    L.append(s)


def fmt(x, n=2):
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def keyset(T):
    return set(zip(T.date, T.tm.astype(int), T.d.astype(int))) if len(T) else set()


rows = []
for s in STRATS + sorted(k for k in V["A_BASE"] if k.startswith("ADD|")):
    base = keyset(V["A_BASE"][s])
    for v in ORDER:
        T = V[v][s]
        st = stats_table(T)
        ks = keyset(T)
        rows.append(dict(strat=s, var=v, N=st["ops"], net=st["net"], pf=st["pf"], wr=st["wr"], dd=st["dd"], rdd=st["rdd"],
                         n_is=st["n_is"], pf_is=st["pf_is"], net_is=st["net_is"], rdd_is=st["rdd_is"], n_oos=st["n_oos"],
                         net_oos=st["oos"], rdd_oos=st["rdd_oos"], meses=st["meses"],
                         kept=len(base & ks) / len(base) if base else np.nan,
                         jacc=len(base & ks) / len(base | ks) if (base | ks) else np.nan))
S = pd.DataFrame(rows)
S.to_csv(os.path.join(RES, "estrategias_por_variante.csv"), index=False)

for s in STRATS:
    P(f"### {s}")
    P("| Variante | N | Lucro R$ | PF | WR % | DD R$ | Ret/DD | jan–jul Ret/DD (N) | ago–nov Ret/DD (R$) | Meses + | Trades da base mantidos | Jaccard |")
    P("| :-- | --: | --: | --: | --: | --: | --: | --: | --: | :-: | --: | --: |")
    for r in S[S.strat == s].itertuples():
        P(f"| {r.var} | {r.N} | {fmt(r.net, 0)} | {fmt(r.pf)} | {fmt(r.wr, 1)} | {fmt(r.dd, 0)} | **{fmt(r.rdd)}** | "
          f"{fmt(r.rdd_is)} ({r.n_is}) | {fmt(r.rdd_oos)} ({fmt(r.net_oos, 0)}) | {r.meses} | {fmt(100 * r.kept, 0)}% | {fmt(r.jacc)} |")
    P()

P("### Add-ons setup_v32 (1 contrato, jan–jul = escolha; ago–nov = relatório)")
P("| Config | " + " | ".join(ORDER) + " |")
P("| :-- | " + " | ".join("--:" for _ in ORDER) + " |")
for s in sorted(k for k in V["A_BASE"] if k.startswith("ADD|")):
    cells = []
    for v in ORDER:
        r = S[(S.strat == s) & (S["var"] == v)].iloc[0]
        cells.append(f"{r.n_is}/{fmt(r.pf_is)}/{fmt(r.net_is, 0)}")
    P(f"| {s[4:]} | " + " | ".join(cells) + " |")
P("(célula = N jan–jul / PF jan–jul / lucro jan–jul R$)")
P()

# carteira total (5 estratégias de produção: E22 2c + C1a + SYM_W + V1a + SYM_D)
P("### Carteira de produção somada (E22 2c + C1a + SYM_WIN + V1a + SYM_WDO)")
P("| Variante | N | Lucro R$ | PF | DD R$ | Ret/DD | jan–jul Ret/DD | ago–nov Ret/DD |")
P("| :-- | --: | --: | --: | --: | --: | --: | --: |")
cart = []
for v in ORDER:
    C = pd.concat([V[v][s][["date", "tm", "xt", "brl"]] for s in STRATS if s != "V21"], ignore_index=True)
    st = stats_table(C)
    cart.append(dict(var=v, **{k: st[k] for k in ("ops", "net", "pf", "dd", "rdd", "rdd_is", "rdd_oos")}))
    P(f"| {v} | {st['ops']} | {fmt(st['net'], 0)} | {fmt(st['pf'])} | {fmt(st['dd'], 0)} | **{fmt(st['rdd'])}** | {fmt(st['rdd_is'])} | {fmt(st['rdd_oos'])} |")
pd.DataFrame(cart).to_csv(os.path.join(RES, "carteira_por_variante.csv"), index=False)
P()

# nulo embaralhado
pn = os.path.join(RES, "nulo_embaralhado.csv")
if os.path.exists(pn):
    N = pd.read_csv(pn)
    P(f"### Nulo: força base embaralhada dentro do pregão ({len(N)} sementes)")
    P("| Estratégia | Lucro R$ mediana [p5–p95] | Ret/DD mediana [p95; máx] | jan–jul Ret/DD p95 | Base | Variantes acima do p95 do nulo (Ret/DD) |")
    P("| :-- | :-- | :-- | --: | --: | :-- |")
    for s in STRATS:
        net, rdd, ris = N[f"{s}_net"], N[f"{s}_rdd"], N[f"{s}_rdd_is"]
        b = S[(S.strat == s) & (S["var"] == "A_BASE")].iloc[0]
        above = [v for v in ORDER if v != "E3_EMBARALHADO" and S[(S.strat == s) & (S["var"] == v)].iloc[0].rdd > rdd.quantile(.95)]
        P(f"| {s} | {fmt(net.median(), 0)} [{fmt(net.quantile(.05), 0)}–{fmt(net.quantile(.95), 0)}] | {fmt(rdd.median())} "
          f"[{fmt(rdd.quantile(.95))}; {fmt(rdd.max())}] | {fmt(ris.quantile(.95))} | {fmt(b.rdd)} | {', '.join(above)} |")
    P()

# sinais / estudo de evento
P("### Estudo de evento dos candidatos (entrada na abertura após a confirmação, saída 12 barras depois, líquido de custo, pts)")
P("| Ativo · motor | Variante | N | média pts | t | jan–jul média | ago–nov média | % candidatos da base mantidos |")
P("| :-- | :-- | --: | --: | --: | --: | --: | --: |")
ev = []
for a in ("WIN", "WDO"):
    for eng in ("v2.1", "v3.2", "divv2"):
        B = V["A_BASE"]["SIG"]; B = B[(B.asset == a) & (B.eng == eng)]
        bk = set(zip(B.date, B.dir, B.j))
        for v in ORDER:
            G = V[v]["SIG"]; G = G[(G.asset == a) & (G.eng == eng)]
            x = G.pts.values
            t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan
            isv = G.date <= "2026-07-31"
            kept = len(bk & set(zip(G.date, G.dir, G.j))) / len(bk) if bk else np.nan
            ev.append(dict(asset=a, eng=eng, var=v, N=len(x), mean=x.mean(), t=t, mean_is=G.pts[isv].mean(), mean_oos=G.pts[~isv].mean(), kept=kept))
            P(f"| {a} · {eng} | {v} | {len(x)} | {fmt(x.mean(), 1 if a == 'WIN' else 2)} | {fmt(t)} | {fmt(G.pts[isv].mean(), 1 if a == 'WIN' else 2)} | "
              f"{fmt(G.pts[~isv].mean(), 1 if a == 'WIN' else 2)} | {fmt(100 * kept, 0)}% |")
pd.DataFrame(ev).to_csv(os.path.join(RES, "evento_sinais.csv"), index=False)
P()

# rótulos
P(f"### Rótulos do usuário (9 pregões WIN; {V['A_BASE']['LABELS']['v3.2']['n_gt']} divergências válidas de rejeição/absorção; casamento F2 ± 2 barras)")
P("| Motor | Variante | Recall | Recall hold-out (3 pregões) | Precisão | Detecções/dia |")
P("| :-- | :-- | --: | --: | --: | --: |")
lb = []
for eng in V["A_BASE"]["LABELS"]:
    for v in ORDER:
        x = V[v]["LABELS"][eng]
        lb.append(dict(eng=eng, var=v, **x))
        P(f"| {eng} | {v} | {fmt(100 * x['rec'], 0)}% | {fmt(100 * x['rec_hold'], 0)}% | {fmt(100 * x['prec'], 0)}% | {fmt(x['per_day'], 1)} |")
pd.DataFrame(lb).to_csv(os.path.join(RES, "rotulos.csv"), index=False)
P(f"Paridade da onda base com o rotulador (máx |Δonda| por pregão): {V['A_BASE']['LABEL_PARITY']}")
P()

# tape
P("### Dias de tape real (.trd): mesma variante com o institucional do tape × do .min")
P("| Variante | WIN corr onda | WIN corr Δonda | WIN candidatos v3.2 iguais (min∩tape / min) | WDO corr onda | WDO corr Δonda | WDO candidatos iguais | E22 nos dias de tape: R$ .min → R$ tape (N) |")
P("| :-- | --: | --: | --: | --: | --: | --: | :-- |")
for v in ORDER:
    T = V[v]["TAPE"]
    cells = []
    for a in ("WIN", "WDO"):
        xs = [x for (aa, d), x in T.items() if aa == a]
        cw = np.nanmedian([x["corr_wave"] for x in xs]); cd = np.nanmedian([x["corr_dwave"] for x in xs])
        both = sum(x["both"] for x in xs); nm = sum(x["n_min"] for x in xs); nt = sum(x["n_tape"] for x in xs)
        cells += [fmt(cw), fmt(cd), f"{both}/{nm} ({fmt(100 * both / max(nm, 1), 0)}%; tape {nt})"]
    xs = [x for (aa, d), x in T.items() if aa == "WIN"]
    em = sum(t[2] for x in xs for t in x["e22_min"]); et = sum(t[2] for x in xs for t in x["e22_tape"])
    nm_ = sum(len(x["e22_min"]) for x in xs); nt_ = sum(len(x["e22_tape"]) for x in xs)
    P(f"| {v} | " + " | ".join(cells) + f" | {fmt(em, 0)} ({nm_}) → {fmt(et, 0)} ({nt_}) |")
P(f"Dias: {sorted(V['A_BASE']['TAPE'].keys())}")
P()

# reajuste
pr = os.path.join(RES, "reajuste_grade.csv")
if os.path.exists(pr):
    G = pd.read_csv(pr)
    P("### Reajuste justo (escolha só em jan–jul, N jan–jul ≥ 100; E22: k × memória × mistura = 72 configs; V21: k = 8 configs)")
    P("| Estratégia | Variante | Melhor jan–jul: config | jan–jul Ret/DD | ago–nov Ret/DD (R$) | Mediana ago–nov Ret/DD dos 10 melhores de jan–jul | Config original: jan–jul / ago–nov |")
    P("| :-- | :-- | :-- | --: | --: | --: | :-- |")
    for s_ in ("E22", "V21"):
        for v in G["var"].unique():
            g = G[(G.strat == s_) & (G["var"] == v) & (G.n_is >= 100)]
            if not len(g):
                continue
            g = g.sort_values("rdd_is", ascending=False)
            b = g.iloc[0]
            o = G[(G.strat == s_) & (G["var"] == v) & (G.af == 0.5) & (G.mt == 0.55) & (np.isclose(G.k, 0.15))]
            ocell = f"{fmt(o.iloc[0].rdd_is)} / {fmt(o.iloc[0].rdd_oos)}" if len(o) else "—"
            P(f"| {s_} | {v} | k={b.k} mem=({b.af},{b.as_}) mix=({b.mt},{b.mi}) | {fmt(b.rdd_is)} | {fmt(b.rdd_oos)} ({fmt(b.oos, 0)}) | "
              f"{fmt(g.head(10).rdd_oos.median())} | {ocell} |")
    P()

open(os.path.join(RES, "tabelas.md"), "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))
