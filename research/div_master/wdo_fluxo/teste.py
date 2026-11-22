# -*- coding: utf-8 -*-
"""
Dólar: o problema é a Wall ou o fluxo? (pergunta do usuário em 12/11/2026: "o dólar respeita muito as Walls, talvez
precisemos repensar o fluxo")

Mesma máquina do especialista V3.2 (pivôs ZigZag 1,2×ATR, F1 no fluxo mais extremo, extensões, gatilho Opção C,
filtros), trocando só a SÉRIE DE FLUXO que define a divergência. Cada força por barra passa pela mesma
transformação da onda atual (0,55·(EMA2 − EMA10) do acumulado + 0,45·impulso de 3 barras):
  atual        · força do painel (Wyckoff 45% + porte 25% + institucional 30%)
  wyckoff      · só a absorção Wyckoff        porte · só o porte dos lotes
  inst         · só o institucional (0,55 agressão + 1,15 passivo − 0,85 varejo)
  delta        · agressão compradora − vendedora (CVD)
  inst_aggr / inst_pass / varejo_inv · cada componente institucional isolado (varejo invertido)
  aleatório    · placebo: força sorteada (a divergência vira sorteio)
  SÓ WALL      · sem fluxo nenhum: todo pivô na Wall que passa pela regra de preço vira sinal
Âncora: Wall/MidWall ou extremo do dia (como o especialista) e só Wall/MidWall.
Saídas (1 contrato, custo 0,5 pt, tick a tick em M1): SL 5/7/10 · alvo próxima Wall ou sem alvo · BE 4→0,5 ou sem ·
12/24 barras. Filtros: regra do especialista (sem super, 1º/2º gatilho, 10:00–15:55, NWE50) e "solto" (só 09:05–16:45).
Escolha em jan–jul, conferência em ago–nov.
Uso: python research/div_master/wdo_fluxo/teste.py → results/
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "research", "div_master", "especialistas")]
import numpy as np
import pandas as pd
import modulo as M, bt
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
IS_END = "2026-07-31"
ASSET = "WDO"
FLOWS = ["atual", "wyckoff", "porte", "inst", "delta", "inst_aggr", "inst_pass", "varejo_inv", "aleatório", "SÓ WALL"]


def wave_from(force):
    out, cum, ef, es = [], 0.0, 0.0, 0.0
    for i, f in enumerate(force):
        f1 = force[i - 1] if i >= 1 else f
        f2 = force[i - 2] if i >= 2 else f1
        imp3 = 0.45 * f + 0.35 * f1 + 0.20 * f2
        cum += f
        if i == 0:
            ef = es = cum
        else:
            ef = 0.5 * cum + 0.5 * ef
            es = (2 / 11) * cum + (9 / 11) * es
        out.append(0.55 * (ef - es) + 0.45 * imp3)
    return out


def forces(fb, kind, rng):
    if kind == "atual":
        return [b["force"] for b in fb]
    if kind == "wyckoff":
        return [b["wyckoff_abs"] for b in fb]
    if kind == "porte":
        return [b["lot_urgency"] for b in fb]
    if kind == "inst":
        return [b["smart_inst"] for b in fb]
    if kind == "delta":
        return [float(b.get("buy_vol", 0)) - float(b.get("sell_vol", 0)) for b in fb]
    if kind == "inst_aggr":
        return [float(b.get("inst_aggr_delta", 0)) for b in fb]
    if kind == "inst_pass":
        return [float(b.get("inst_pass_delta", 0)) for b in fb]
    if kind == "varejo_inv":
        return [-float(b.get("ret_delta_bar", 0)) for b in fb]
    if kind == "aleatório":
        return list(rng.normal(0, 1000, len(fb)))
    raise ValueError(kind)


def signals(data, kind, anchor, seed=7):
    rng = np.random.default_rng(seed)
    P = M.PARAMS[ASSET]
    rows = []
    orig_elig, orig_k = M.eligible, M.COMMON["k_v31"]

    def elig_wall(a, mode, *args, **kw):
        return a["c1"] is not None or a["c2"] is not None

    try:
        if anchor == "wall":
            M.eligible = elig_wall
        for d in sorted(data):
            if d > bt.END:
                continue
            bars, walls, _ = data[d]
            fb = M.compute_flow([dict(b) for b in bars], ASSET)
            if kind == "SÓ WALL":
                w = [1.0] * len(fb)
                M.COMMON["k_v31"] = -1e12          # sem condição de fluxo: só preço + âncora
            else:
                w = wave_from(forces(fb, kind, rng))
                M.COMMON["k_v31"] = orig_k
            for b, x in zip(fb, w):
                b["wave"] = float(x)
            lv = sorted(float(x["price"]) for x in walls if x.get("type") in M.LEVEL_TYPES)
            cands = M.engine_v32(fb, lv, P, "common", atr=M.atr_series(fb, P["tick"]), opt=M.V32_PROD)
            trig, _ = M.triggers(fb, cands, P)
            by = {(c["dir"], c["j"]): c for c in cands}
            seq = {1: 0, -1: 0}
            for x in trig:
                t = x["idx"]
                if t + 1 >= len(fb):
                    continue
                c = by[(x["dir"], x["j"])]
                rows.append(dict(date=d, dir=x["dir"], time_in=fb[t + 1]["time"], super=x["super"], seq=seq[x["dir"]],
                                 piv=c["px2"], levels=lv))
                seq[x["dir"]] += 1
    finally:
        M.eligible, M.COMMON["k_v31"] = orig_elig, orig_k
    return pd.DataFrame(rows)


def run(T, DS, sl, tp, be, tmax):
    x = bt.X[ASSET]
    rows, last = [], {}
    for r in T.sort_values(["date", "tm"]).itertuples():
        if r.tm <= last.get(r.date, -1):
            continue
        D = DS[r.date]
        if tp == "wall":
            w = bt.next_level(r.levels, r.ep, r.dir, 4 * x["tick"] + x["front"])
            tpx = (w - r.dir * x["front"]) if w is not None else r.ep + r.dir * 1e9
        else:
            tpx = r.ep + r.dir * 1e9
        pts, t = bt.sim(*bt._args(D), D["u30"], int(r.e), r.ep, r.dir, sl, tpx, False, 0.0, 0.0, 0.0,
                        be[0], be[1], tmax, x["tick"])
        last[r.date] = t
        rows.append((r.date, r.tm, t, (pts - x["cost"]) * x["brl"]))
    return rows


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0.0, net=0, dd=0, rdd=0.0, rdd_is=0.0, rdd_oos=0.0, meses="0/0", net_is=0, net_oos=0)
    R = pd.DataFrame(rows, columns=["date", "tm", "xt", "brl"]).sort_values(["date", "xt", "tm"])
    p = R.brl.values

    def part(q):
        if len(q) == 0:
            return 0.0, 0.0, 0.0
        eq = np.cumsum(q)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
        return float(eq[-1]), dd, (float(eq[-1]) / dd if dd else 99.0)

    net, dd, r = part(p)
    isv = (R.date <= IS_END).values
    ni, _, ri = part(p[isv])
    no, _, ro = part(p[~isv])
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby(R.date.str[:7].values).sum()
    return dict(ops=len(p), pf=round(g / l, 2) if l else 99.0, net=round(net), dd=round(dd), rdd=round(r, 2),
                rdd_is=round(ri, 2), rdd_oos=round(ro, 2), net_is=round(ni), net_oos=round(no),
                meses=f"{int((mon > 0).sum())}/{len(mon)}")


def main():
    os.makedirs(OUT, exist_ok=True)
    data = load_asset(ASSET, "M5")
    DS = bt.market(ASSET)
    EXITS = list(itertools.product((5.0, 7.0, 10.0), ("wall", "sem"), ((4.0, 0.5), (0.0, 0.0)), (12, 24)))
    rows = []
    for kind, anchor in itertools.product(FLOWS, ("wall+extremo", "wall")):
        S = signals(data, kind, "wall" if anchor == "wall" else "common")
        if len(S) == 0:
            continue
        S = bt.simulate(ASSET, S, DS, exits=())
        sets = {"regra": S[S.ok & ~S.super & (S.seq <= 1) & (S.tm >= 600) & (S.tm < 960) & (S.ext50 > -0.5) & (S.slope50 > -0.5)],
                "solto": S[S.ok]}
        for fname, T in sets.items():
            res = [dict(sl=sl, tp=tp, be=f"{be[0]}→{be[1]}" if be[0] else "sem", tmax=tm, **stats(run(T, DS, sl, tp, be, tm)))
                   for sl, tp, be, tm in EXITS]
            Rr = pd.DataFrame(res)
            best = Rr.sort_values("rdd_is", ascending=False).iloc[0]
            rows.append(dict(fluxo=kind, ancora=anchor, filtro=fname, sinais=len(T),
                             pf_mediano=round(Rr.pf.median(), 2), rdd_mediano=round(Rr.rdd.median(), 2),
                             positivas=f"{int((Rr.net > 0).sum())}/{len(Rr)}",
                             melhor=f"SL{best.sl:.0f} TP {best.tp} BE {best.be} {best.tmax}b",
                             melhor_ops=int(best.ops), melhor_pf=best.pf, melhor_net=int(best.net),
                             melhor_rdd=best.rdd, melhor_is=best.rdd_is, melhor_oos=best.rdd_oos, melhor_meses=best.meses))
            r = rows[-1]
            print(f"{kind:10s} {anchor:12s} {fname:5s} {len(T):5d} sinais · PF med {r['pf_mediano']:4.2f} · "
                  f"positivas {r['positivas']:5s} · melhor jan–jul: {r['melhor']:28s} {r['melhor_ops']:4d} tr PF {r['melhor_pf']:4.2f} "
                  f"R$ {r['melhor_net']:6d} Ret/DD {r['melhor_rdd']:5.2f} (jan–jul {r['melhor_is']:5.2f} · ago–nov {r['melhor_oos']:5.2f})",
                  flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "fluxos.csv"), index=False)


if __name__ == "__main__":
    main()
