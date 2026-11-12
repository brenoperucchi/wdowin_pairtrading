# -*- coding: utf-8 -*-
"""
Frente 2 do PLANO_UNIFICACAO_ROMPIMENTO_LIMITE.md — rompimentos de Wall/MidWall (sem rotulagem nova, decisão de 12/11).

Sinais (compra; venda espelhada), barras M5 do Profit; entrada na abertura MT5 da barra seguinte:
  R0  controle: fechamento cruza W + b vindo de baixo (barra anterior fechou ≤ W).
  R3  R0 + onda Smart Money no maior valor do dia no sentido do rompimento.
  R1  aceitação depois do reteste (regra do usuário, caso 11/11 10:10): depois do rompimento em i, uma barra k ≤ i+N
      volta a W + 30 (toque) e uma barra m ≥ k (m ≤ i+N) fecha de novo acima de W + b; invalida se algum fechamento
      entre i e m ficar abaixo de W − r.
  R2  R1 + divergência oculta no reteste: mínima do reteste acima da mínima das 12 barras antes do rompimento, e onda
      mínima do reteste abaixo da onda naquela mínima (preço fundo mais alto, fluxo fundo mais baixo).
  R4  falha de rompimento, operada ao contrário: rompe e em até N barras fecha de volta abaixo de W − b, com divergência
      regular do motor v2.1 (topo F2 entre o rompimento e a volta). Entrada vendida.
Um sinal por nível, tipo e sentido no dia. Saídas: stop do outro lado da Wall (W ∓ 150 / 4,0; aborta se o risco
passar de 300 / 10,5); alvo na próxima Wall/MidWall (−15 / −0,5) ou sem alvo com saída em 12/24 barras; BE opcional.
Uso: python research/div_master/frente2/rompimento.py → frente2/results/
"""
import itertools, os, random, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "research", "div_master", "especialistas")]
from collections import defaultdict
import numpy as np, pandas as pd
import bt, modulo as M
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
H1, IS_END = "2026-04-30", "2026-07-31"
SP = {"WIN": dict(b=(0.0, 20.0), r=(100.0, 150.0), touch=30.0, sl_far=150.0, slmax=300.0, slmin=60.0, front=15.0,
                  be=(180.0, 20.0)),
      "WDO": dict(b=(0.0, 0.5), r=(3.0, 4.0), touch=1.0, sl_far=4.0, slmax=10.5, slmin=1.5, front=0.5, be=(5.0, 1.0))}
NS = (6, 12)


def day_signals(asset, bars, walls, fb, cands_v21):
    """Lista de sinais: dict(kind, params, i_sig (barra Profit do sinal), d, W)."""
    sp = SP[asset]
    lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    n = len(fb)
    C = [float(b["close"]) for b in fb]
    Lo = [float(b["low"]) for b in fb]
    Hi = [float(b["high"]) for b in fb]
    Wv = [float(b["wave"]) for b in fb]
    out = []
    for W, d, b in itertools.product(lv, (1, -1), sp["b"]):
        for i in range(1, n - 1):
            if not (d * (C[i] - W) > b and d * (C[i - 1] - W) <= 0):
                continue
            out.append(dict(kind="R0", b=b, N=0, r=0, i=i, d=d, W=W))
            wmax = max(d * x for x in Wv[: i + 1])
            if d * Wv[i] >= wmax:
                out.append(dict(kind="R3", b=b, N=0, r=0, i=i, d=d, W=W))
            for N in NS:
                # R1 / R2
                for r in sp["r"]:
                    touched, k_t = False, None
                    for m in range(i + 1, min(i + N, n - 1) + 1):
                        if d * (C[m] - (W - d * r)) < 0:
                            break
                        ext = Lo[m] if d == 1 else Hi[m]
                        if not touched and d * (ext - W) <= sp["touch"]:
                            touched, k_t = True, m
                        if touched and d * (C[m] - W) > b and m > i:
                            out.append(dict(kind="R1", b=b, N=N, r=r, i=m, d=d, W=W))
                            pre = range(max(0, i - 12), i)
                            if pre:
                                j0 = min(pre, key=lambda x: Lo[x]) if d == 1 else max(pre, key=lambda x: Hi[x])
                                rt = range(k_t, m + 1)
                                ext_rt = min(Lo[x] for x in rt) if d == 1 else max(Hi[x] for x in rt)
                                w_rt = min(Wv[x] for x in rt) if d == 1 else max(Wv[x] for x in rt)
                                if d * (ext_rt - (Lo[j0] if d == 1 else Hi[j0])) > 0 and d * (w_rt - Wv[j0]) < 0:
                                    out.append(dict(kind="R2", b=b, N=N, r=r, i=m, d=d, W=W))
                            break
                # R4: falha + divergência regular v2.1 no extremo
                for m in range(i + 1, min(i + N, n - 1) + 1):
                    if d * (C[m] - (W - d * b)) < 0:
                        ok = any(c["dir"] == -d and i <= c["j"] <= m and c["conf"] <= m for c in cands_v21)
                        if ok:
                            out.append(dict(kind="R4", b=b, N=N, r=0, i=m, d=-d, W=W))
                        break
    # um sinal por nível, tipo, parâmetros e sentido no dia (o primeiro)
    seen, uniq = set(), []
    for s in sorted(out, key=lambda x: x["i"]):
        key = (s["kind"], s["b"], s["N"], s["r"], s["d"], s["W"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return uniq, lv


def exits(asset):
    out = []
    for tp, be in itertools.product(("wall", "T12", "T24"), (False, True)):
        out.append(dict(tp=tp, be=be))
    return out


def simulate(asset, s, D, e, lv):
    sp, x = SP[asset], bt.X[asset]
    d, ep, W = s["d"], float(D["o5"][e]), s["W"]
    # stop do outro lado do nível (na falha R4, o nível fica acima para a venda: W + sl_far)
    stop = W - d * sp["sl_far"]
    sl = d * (ep - stop)
    if sl > sp["slmax"]:
        return None
    sl = max(sl, sp["slmin"])
    res = {}
    for xx in exits(asset):
        be = sp["be"] if xx["be"] else (0.0, 0.0)
        if xx["tp"] == "wall":
            nxt = [v for v in lv if d * (v - ep) >= 4 * x["tick"] + sp["front"]]
            if not nxt:
                res[(xx["tp"], xx["be"])] = None
                continue
            tp = (min(nxt) if d == 1 else max(nxt)) - d * sp["front"]
            tmax = 24
        else:
            tp, tmax = ep + d * 1e9, int(xx["tp"][1:])
        pts, t = bt.sim(*bt._args(D), D["u30"], e, ep, d, sl, tp, False, 0.0, 0.0, 0.0, be[0], be[1], tmax, x["tick"])
        res[(xx["tp"], xx["be"])] = ((pts - x["cost"]) * x["brl"], int(t))
    return res


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0.0, net=0, dd=0, rdd=0.0, meses="0/0", pf_h1=0, pf_h2=0, pf_oos=0)
    rows = sorted(rows, key=lambda r: (r[0], r[2], r[1]))
    p = np.array([r[3] for r in rows])
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    pf = lambda q: round(float(q[q > 0].sum() / -q[q < 0].sum()), 2) if (q < 0).any() else (99.0 if len(q) else 0.0)
    dts = np.array([r[0] for r in rows])
    mon = pd.Series(p).groupby([x[:7] for x in dts]).sum()
    return dict(ops=len(p), pf=pf(p), net=round(float(eq[-1])), dd=round(dd), rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
                meses=f"{int((mon > 0).sum())}/{len(mon)}", pf_h1=pf(p[dts <= H1]), pf_h2=pf(p[(dts > H1) & (dts <= IS_END)]),
                pf_oos=pf(p[dts > IS_END]))


def one_at_a_time(rows):
    rows = sorted(rows, key=lambda r: (r[0], r[1]))
    acc, cur, last = [], None, -1
    for r in rows:
        if r[0] != cur:
            cur, last = r[0], -1
        if r[1] <= last:
            continue
        acc.append(r)
        last = r[2]
    return acc


def main():
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 250)
    allres = []
    for asset in ("WIN", "WDO"):
        DS = bt.market(asset)
        lo_w, hi_w = bt.WINDOW[asset]
        recs = []      # um registro por sinal executável
        for date, (bars, walls, _) in sorted(load_asset(asset, "M5").items()):
            if date > bt.END or date not in DS:
                continue
            fb, Rr = M.run_day(asset, bars, walls, engines=("v2.1",), elig="all")
            sigs, lv = day_signals(asset, bars, walls, fb, Rr["v2.1"]["cands"])
            D = DS[date]
            for s in sigs:
                if s["i"] + 1 >= len(fb):
                    continue
                tm = bt.hm(fb[s["i"] + 1]["time"])
                if tm not in D["pos"] or not (lo_w <= tm <= hi_w):
                    continue
                e = D["pos"][tm]
                res = simulate(asset, s, D, e, lv)
                if res is None:
                    continue
                n5 = len(D["c5"])
                fwd = {k: s["d"] * (D["c5"][min(e + k - 1, n5 - 1)] - D["o5"][e]) - bt.X[asset]["cost"] for k in (6, 12, 24)}
                recs.append(dict(date=date, tm=tm, **{k: s[k] for k in ("kind", "b", "N", "r", "d")}, res=res, **{f"r{k}": v for k, v in fwd.items()}))
        Rdf = pd.DataFrame(recs)
        Rdf["per"] = np.where(Rdf.date <= H1, "jan–abr", np.where(Rdf.date <= IS_END, "mai–jul", "ago–nov"))
        ev = Rdf.groupby(["kind", "per"]).r12.agg(["size", "mean"]).unstack("per").round(1)
        print(f"\n===== {asset} — estudo de evento: retorno 12 barras líquido de custo (pts), por hipótese e período")
        print(ev.to_string())
        # backtest: cada combinação de parâmetros × saída, um trade por vez
        for (kind, b, N, r), g in Rdf.groupby(["kind", "b", "N", "r"]):
            for xx in exits(asset):
                key = (xx["tp"], xx["be"])
                rows = [(q.date, q.tm, q.res[key][1], q.res[key][0]) for q in g.itertuples() if q.res.get(key)]
                st = stats(one_at_a_time(rows))
                allres.append(dict(ativo=asset, hip=kind, b=b, N=N, r=r, alvo=xx["tp"], be=xx["be"], **st))
        Rdf.drop(columns=["res"]).to_csv(os.path.join(OUT, f"sinais_{asset}.csv"), index=False)
    A = pd.DataFrame(allres)
    A["valida"] = (A.ops >= 100) & (A.pf_h1 > 1.0) & (A.pf_h2 > 1.0) & (A.pf_oos > 1.0)
    A.to_csv(os.path.join(OUT, "grade_rompimento.csv"), index=False)
    cols = ["ativo", "hip", "b", "N", "r", "alvo", "be", "ops", "pf", "net", "dd", "rdd", "meses", "pf_h1", "pf_h2", "pf_oos"]
    print("\n===== melhor configuração por ativo × hipótese (por Ret/DD, entre as válidas; se nenhuma, a melhor geral)")
    for (a, h), g in A.groupby(["ativo", "hip"]):
        v = g[g.valida]
        best = (v if len(v) else g).sort_values("rdd", ascending=False).head(1)
        print(("[válida] " if len(v) else "[nenhuma válida] ") + best[cols].to_string(index=False, header=False))
    print("\nconfigs:", len(A), " válidas (≥100 trades, PF>1 em jan–abr, mai–jul e ago–nov):", int(A.valida.sum()))
    print("mediana do PF por hipótese:", A.groupby(["ativo", "hip"]).pf.median().round(2).to_dict())


if __name__ == "__main__":
    main()
