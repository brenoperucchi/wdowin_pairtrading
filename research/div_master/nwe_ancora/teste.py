# -*- coding: utf-8 -*-
"""
Terceira âncora para o especialista: divergência na MÉDIA da NWE (centro da NWE50 · bw 8 — com bw 8 o centro da
NWE50 é igual ao da NWE100, que é o `nwe_c` do dataset div_wall_v1, causal e aquecido no mesmo contrato).
Pedido do usuário em 12/11/2026: "dá para operar divergência também na média de 50 da NWE? aumentaria trades e
Ret/DD?"

Âncora NWE (só para divergências que NÃO têm âncora Wall nem extremo do dia — as outras já são do especialista):
  compra: centro − furo ≤ mínima do F2 ≤ centro + tol   (o preço veio até a média por cima, ou furou um pouco)
  venda : centro − tol ≤ máxima do F2 ≤ centro + furo
Gatilho (janela igual à Opção C: max(F2+1, confirmação) … F2+3):
  RETOMADA : fecha além da média + 20 pts a favor, com corpo a favor e além do fechamento do pivô
  DUPLO    : fecha além da máxima (compra) / mínima (venda) da barra do pivô
Filtros e saída iguais ao especialista: 1º/2º gatilho do dia por direção, entrada 10:00–15:55, contexto NWE50
(opcional aqui), um trade por vez, SL 200 · BE 180→20 · 12 barras · 2 contratos.
Carteira: SEPARADO (o especialista NWE é uma estratégia à parte) e JUNTO (um livro só com o especialista atual:
seq e um-por-vez compartilhados).
Uso: python research/div_master/nwe_ancora/teste.py → results/
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "carteira_v22")]
import numpy as np
import pandas as pd
import modulo as M, bt
from core import especialista_v22 as E
from paridade_especialista import day_inputs
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
IS_END = "2026-07-31"
BUF = 20.0


def nwe_cands(fb, levels, P, atr, nc, tol, pierce):
    """Divergências v3.2 cujo F2 está na média da NWE e não tem âncora Wall nem extremo do dia."""
    orig = M.eligible

    def elig(a, mode, bars=None, j=None, d=None, levels=None, P=None):
        if orig(a, "common"):
            return False
        px, c = M._px(bars[j], d), float(nc[j])
        return (c - pierce <= px <= c + tol) if d == 1 else (c - tol <= px <= c + pierce)

    M.eligible = elig
    try:
        cs = M.engine_v32(fb, levels, P, "nwe", atr=atr, opt=M.V32_PROD)
    finally:
        M.eligible = orig
    return cs


def nwe_triggers(fb, cands, nc, kind):
    out = []
    for c in cands:
        d, j = c["dir"], c["j"]
        for t in range(max(j + 1, c["conf"]), min(j + M.COMMON["trig_max"], len(fb) - 1) + 1):
            b, bj = fb[t], fb[j]
            if kind == "RETOMADA":
                ok = d * (b["close"] - (float(nc[t]) + d * BUF)) > 0 and d * (b["close"] - b["open"]) > 0 \
                    and d * (b["close"] - bj["close"]) > 0
            else:
                ok = (b["close"] > bj["high"]) if d == 1 else (b["close"] < bj["low"])
            if ok:
                out.append(dict(idx=t, dir=d, j=j, super=False, src="NWE"))
                break
    return out


def book(trigs, fb, ex, is_live=False):
    """Mesmo funil do core/especialista_v22.run sobre uma lista de gatilhos (de uma ou mais âncoras).
    Cada gatilho diz se exige o contexto NWE50 (`ctx`, padrão True como no especialista)."""
    c = E.CFG
    pos = {str(b["time"])[:5]: i for i, b in enumerate(ex)}
    seq = {1: 0, -1: 0}
    rows = []
    for x in sorted(trigs, key=lambda z: (z["idx"], z["src"])):
        t = x["idx"]
        if t + 1 >= len(fb):
            continue
        s = seq[x["dir"]]
        seq[x["dir"]] += 1
        e = pos.get(fb[t + 1]["time"])
        if e is None or e < 1:
            continue
        rows.append(dict(e=e, tm=E._hm(fb[t + 1]["time"]), d=int(x["dir"]), seq=s, super=x["super"], src=x["src"],
                         ctx=x.get("ctx", True)))
    out, last_exit = [], -1
    for r in sorted(rows, key=lambda z: z["tm"]):
        e, d = r["e"], r["d"]
        if r["super"] or r["seq"] > 1 or not (c["t_start"] <= r["tm"] < c["t_end"]):
            continue
        n50 = float(ex[e - 1].get("nwe50_line") or 0.0)
        u50 = float(ex[e - 1].get("nwe50_upper") or 0.0)
        n50_old = float(ex[max(0, e - 7)].get("nwe50_line") or 0.0)
        if n50 <= 0 or u50 <= 0:
            continue
        half = max(u50 - n50, c["tick"])
        ext = -d * (float(ex[e - 1]["close"]) - n50) / half
        slope = d * (n50 - n50_old) / half
        if r["ctx"] and not (ext > c["ext_min"] and slope > c["slope_min"]):
            continue
        if r["tm"] <= last_exit:
            continue
        ep = float(ex[e]["open"])
        res = E._sim(ex, e, ep, d, is_live)
        pts = ((res["px"] - ep) * d - c["cost"]) * c["contracts"]
        out.append(dict(tm=r["tm"], xt=E._hm(ex[res["k"]]["time"]), brl=round(pts * c["brl_pt"], 2), src=r["src"], dir=d))
        last_exit = E._hm(ex[res["k"]]["time"])
    return out


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0, net=0, dd=0, rdd=0, rdd_is=0, rdd_oos=0, dias=0)
    R = pd.DataFrame(rows).sort_values(["date", "xt", "tm"])
    p = R.brl.values

    def rdd(q):
        if len(q) == 0:
            return 0.0, 0.0, 0.0
        eq = np.cumsum(q)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
        return float(eq[-1]), dd, (float(eq[-1]) / dd if dd else 99.0)

    net, dd, r = rdd(p)
    isv = (R.date <= IS_END).values
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby(R.date.str[:7].values).sum()
    return dict(ops=len(p), wr=round(100 * (p > 0).mean(), 1), pf=round(g / l, 2) if l else 99.0, net=round(net),
                dd=round(dd), rdd=round(r, 2), rdd_is=round(rdd(p[isv])[2], 2), rdd_oos=round(rdd(p[~isv])[2], 2),
                meses=f"{int((mon > 0).sum())}/{len(mon)}", dias=R.date.nunique())


def main():
    os.makedirs(OUT, exist_ok=True)
    DS = bt.market("WIN")
    data = load_asset("WIN", "M5")
    P = M.PARAMS["WIN"]
    days = []
    for d in sorted(data):
        if d > bt.END or d not in DS:
            continue
        fb, walls, ex = day_inputs(DS, data, d)
        nc = data[d][2][0]
        levels = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES and w.get("price") is not None)
        atr = M.atr_series(fb, P["tick"])
        base_c = M.engine_v32(fb, levels, P, "common", atr=atr, opt=M.V32_PROD)
        bt_, _ = M.triggers(fb, base_c, P)
        base_t = [dict(idx=x["idx"], dir=x["dir"], j=x["j"], super=x["super"], src=x["esp"]) for x in bt_]
        days.append((d, fb, ex, nc, levels, atr, base_t))
    print(f"{len(days)} pregões")

    base = []
    for d, fb, ex, nc, levels, atr, bt_ in days:
        base += [dict(r, date=d) for r in book(bt_, fb, ex)]
    sb = stats(base)
    print("ESPECIALISTA ATUAL:", sb)

    rows = []
    for tol, pierce, kind, ctx in itertools.product((40.0, 80.0, 120.0), (80.0, 150.0), ("RETOMADA", "DUPLO"), (True, False)):
        sep, jun, ncand = [], [], 0
        for d, fb, ex, nc, levels, atr, bt_ in days:
            cs = nwe_cands(fb, levels, P, atr, nc, tol, pierce)
            ncand += len(cs)
            nt = nwe_triggers(fb, cs, nc, kind)
            sep += [dict(r, date=d) for r in book([dict(x, ctx=ctx) for x in nt], fb, ex)]
            # junto: um livro só (seq e um-por-vez compartilhados); o contexto NWE50 vale para as âncoras antigas
            jun += [dict(r, date=d) for r in book(bt_ + [dict(x, ctx=ctx) for x in nt], fb, ex)]
        s1, s2 = stats(sep), stats(jun)
        sep_both = stats(base + sep)
        rows.append(dict(tol=tol, furo=pierce, gatilho=kind, ctx_nwe50=ctx, divergencias_nwe=ncand,
                         **{f"nwe_{k}": v for k, v in s1.items()},
                         **{f"separado_{k}": v for k, v in sep_both.items()},
                         **{f"junto_{k}": v for k, v in s2.items()}))
        print(f"tol {tol:.0f} furo {pierce:.0f} {kind:8s} ctx {'on ' if ctx else 'off'} · div NWE {ncand:4d} · "
              f"NWE sozinho {s1['ops']:3d} tr PF {s1['pf']:4.2f} R$ {s1['net']:6.0f} Ret/DD {s1['rdd']:5.2f} "
              f"({s1['rdd_is']:5.2f}/{s1['rdd_oos']:5.2f}) · separado {sep_both['ops']} tr R$ {sep_both['net']} "
              f"Ret/DD {sep_both['rdd']} · junto {s2['ops']} tr R$ {s2['net']} Ret/DD {s2['rdd']} "
              f"({s2['rdd_is']}/{s2['rdd_oos']})", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "grade.csv"), index=False)


if __name__ == "__main__":
    main()
