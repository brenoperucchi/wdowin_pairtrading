# -*- coding: utf-8 -*-
"""
Testes complementares da ablação (16/11/2026):
  1. Referência da pesquisa (M1) das 4 estratégias da carteira V3.2 (sim_portfolio_4_estrategias.build_strategies).
  2. Nulo por embaralhamento: 30 sementes da força base embaralhada dentro do pregão (E22, V21 e carteira V3.2).
  3. Reajuste justo (só jan–jul): limiar k do motor × memória da onda × mistura, para A/B/C/D/E1/Wyckoff no E22,
     e k para o V21. Escolhe pelo Ret/DD de jan–jul (N_IS ≥ 100) e mede ago–nov.
Uso: python research/flow_ablation/extra.py [ref|null|retune]
"""
import os, sys, time, pickle, itertools, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ablation as AB
from ablation import FL, M, bt, R, MA, E, C32, load_asset, hm, ex4
import numpy as np, pandas as pd

data = {a: {d: v for d, v in load_asset(a, "M5").items() if d <= bt.END} for a in ("WIN", "WDO")}
DS = {a: bt.market(a) for a in ("WIN", "WDO")}
EXW = {d: MA.exec_bars(DS["WIN"][d]) for d in data["WIN"] if d in DS["WIN"]}


def e22(flow):
    rows = []
    for d, (bars, walls, _) in data["WIN"].items():
        if d not in EXW:
            continue
        fb = flow([dict(b) for b in bars], "WIN")
        for t in E.run(fb, walls, EXW[d]):
            rows.append(dict(date=d, tm=hm(t["time"]), xt=hm(t["exit_time"]), d=t["dir_num"], brl=float(t["brl_1c"])))
    return pd.DataFrame(rows)


def v21(flow):
    M.compute_flow = flow
    T = R.run_exit(bt.simulate("WIN", R.signals_mode("ab"), DS["WIN"], exits=()), DS["WIN"])
    s, q = R.evaluate(T)
    return pd.DataFrame(dict(date=q.date.values, tm=q.tm.values, xt=q[R.XT].values, d=q.dir.values, brl=q[R.COL].values))


def c32(flow, sid):
    a = C32.STRAT_CFGS[sid]["asset"]
    rows = []
    for d, (bars, walls, _) in data[a].items():
        if d not in DS[a]:
            continue
        fb = flow([dict(b) for b in bars], a)
        for t in C32.run_strategy(sid, fb, walls, ex4(DS[a][d]), is_live=False):
            rows.append(dict(date=d, tm=hm(t["time"]), xt=hm(t["exit_time"]), d=t["dir_num"], brl=float(t["brl_1c"])))
    return pd.DataFrame(rows)


def st(T):
    s = MA.stats_table(T)
    return {k: s[k] for k in ("ops", "pf", "net", "dd", "rdd", "wr", "n_is", "pf_is", "net_is", "rdd_is", "n_oos", "oos", "rdd_oos", "meses")}


def ref():
    from research.div_master.sim_portfolio_4_estrategias import build_strategies
    rm = build_strategies()
    out = {}
    for k, df in rm.items():
        out[k] = dict(ops=len(df), net=float(df["pnl"].sum()))
        print(k, out[k], flush=True)
    pickle.dump(out, open(os.path.join(HERE, "results", "ref_c32.pkl"), "wb"))


def null(n=30):
    f = FL.make("E3_EMBARALHADO")
    rows = []
    for seed in range(1, n + 1):
        FL.Ctx.shuffle_seed = seed
        r = dict(seed=seed)
        for lab, T in (("E22", e22(f)), ("V21", v21(f)), *[(sid, c32(f, sid)) for sid in C32.STRAT_CFGS]):
            s = st(T)
            r.update({f"{lab}_{k}": v for k, v in s.items()})
        rows.append(r)
        print(seed, r["E22_net"], r["E22_rdd"], r["V21_net"], r["V21_rdd"], flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "results", "nulo_embaralhado.csv"), index=False)


def retune():
    K = [0.0, 0.05, 0.10, 0.15, 0.25, 0.35, 0.50, 0.75]
    MEM = [(0.50, 2 / 11), (0.40, 2 / 21), (0.60, 2 / 9)]
    MIX = [(0.55, 0.45), (0.92, 0.08), (0.30, 0.70)]
    rows = []
    k0, k21 = M.COMMON["k_v31"], M.COMMON["k_v21"]
    for var in ("A_BASE_P", "B_PURO", "C_SEM_OHLC", "D_MIX", "E1_PLAC_GEOM", "X_WYCKOFF"):
        f = FL.make(var)
        t0 = time.time()
        for (af, as_), (mt, mi) in itertools.product(MEM, MIX):
            FL.PIPE.update(af=af, as_=as_, mt=mt, mi=mi)
            for k in K:
                M.COMMON["k_v31"] = k
                s = st(e22(f))
                rows.append(dict(strat="E22", var=var, af=af, as_=round(as_, 4), mt=mt, mi=mi, k=k, **s))
        M.COMMON["k_v31"] = k0
        FL.PIPE.update(af=0.50, as_=2 / 11, mt=0.55, mi=0.45)
        for k in K:
            M.COMMON["k_v21"] = k
            s = st(v21(f))
            rows.append(dict(strat="V21", var=var, af=0.5, as_=round(2 / 11, 4), mt=0.55, mi=0.45, k=k, **s))
        M.COMMON["k_v21"] = k21
        print(var, round(time.time() - t0), "s", flush=True)
        pd.DataFrame(rows).to_csv(os.path.join(HERE, "results", "reajuste_grade.csv"), index=False)


if __name__ == "__main__":
    {"ref": ref, "null": null, "retune": retune}[sys.argv[1]]()
