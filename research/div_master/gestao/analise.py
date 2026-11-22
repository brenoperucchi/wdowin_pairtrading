# -*- coding: utf-8 -*-
"""
2ª passada da exploração de gestão (explorar.py):
  1. de onde vem o resultado da melhor gestão de 3 lotes (lote a lote);
  2. em quais grupos de marcação ela funciona (super-confluência, sem gatilho Opção C, hora);
  3. quantos lotes valem a pena e o alvo do lote 1 (borda da grade), com jan–jul × ago–nov.
Uso: python research/div_master/gestao/analise.py
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import pandas as pd
import explorar as X
import bt

pd.set_option("display.width", 250)
OUT = X.OUT


def base3(**kw):
    g = dict(name="", kind="3L", lots=3, stop="piv", sl=150.0, tp1=60.0, lot2="wall", tp2_fix=300.0, lot3="600",
             trail=150.0, be=20.0, tmax=24, tmax3=200)
    g.update(kw)
    return g


ATUAL = X.grid()[0]


def part_stats(R, mask):
    q = R[mask]
    if len(q) == 0:
        return dict(ops=0)
    p = q.sort_values(["date", "xt", "tm"]).pnl.values
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    return dict(ops=len(p), wr=round(100 * (p > 0).mean(), 1), pf=round(g / l, 2) if l else 99.0, net=round(eq[-1]),
                media=round(p.mean(), 1), dd=round(dd))


def main():
    U = X.universe()
    DS = bt.market("WIN")
    T = {m: X.entries(U, DS, m) for m in ("CONF", "OPC")}
    best = base3()

    print("1) LOTE A LOTE — 3L piv SL150 · T1 60 · BE+20 · L2 Wall · L3 600 (R$, custo já descontado)")
    for m, f in (("CONF", "todas"), ("CONF", "regra atual"), ("OPC", "todas")):
        R = X.run_cfg(X.FILTERS[f](T[m]), DS, best)
        print(f"   {m:4s} {f:12s} {len(R):5d} tr · lote1 R$ {R.lote1.sum():7.0f} · lote2 R$ {R.lote2.sum():7.0f} · "
              f"lote3 R$ {R.lote3.sum():7.0f} · total R$ {R.pnl.sum():7.0f}")

    print("\n2) POR GRUPO DE MARCAÇÃO — entrada na confirmação, cada gestão no grupo inteiro (sem os filtros)")
    Ta = T["CONF"]
    for name, g in (("ATUAL 2c", ATUAL), ("3L melhor", best)):
        R = X.run_cfg(Ta, DS, g)
        R["h"] = R.tm // 60
        groups = {
            "super-confluência": R.super, "sem super-confluência": ~R.super,
            "tem gatilho Opção C (1º/2º)": R.seq <= 1, "3º+ gatilho": (R.seq >= 2) & (R.seq < 99),
            "sem gatilho Opção C": R.seq == 99,
            "09h": R.h == 9, "10–11h": (R.h >= 10) & (R.h < 12), "12–13h": (R.h >= 12) & (R.h < 14),
            "14–15h": (R.h >= 14) & (R.h < 16), "16h+": R.h >= 16,
            "compra": R.dir == 1, "venda": R.dir == -1,
        }
        print(f"   {name}:")
        for gname, msk in groups.items():
            s = part_stats(R, msk.values)
            if s["ops"]:
                print(f"      {gname:28s} {s['ops']:5d} tr · WR {s['wr']:4.1f}% · PF {s['pf']:4.2f} · R$ {s['net']:7.0f} · "
                      f"média R$ {s['media']:6.1f}")

    print("\n3) QUANTOS LOTES E ALVO DO LOTE 1 (stop piv ≤150, BE +20, lote 2 na Wall, lote 3 alvo 600)")
    rows = []
    for m, f in (("CONF", "todas"), ("CONF", "sem super · 10–16h"), ("CONF", "regra atual"), ("OPC", "regra atual")):
        Tf = X.FILTERS[f](T[m])
        for lots, tp1, be in itertools.product((1, 2, 3), (30.0, 40.0, 60.0, 80.0, 100.0), (0.0, 20.0)):
            st = X.stats(X.run_cfg(Tf, DS, base3(lots=lots, tp1=tp1, be=be)))
            rows.append(dict(entrada=m, filtro=f, lotes=lots, tp1=tp1, be=be, **st))
        st = X.stats(X.run_cfg(Tf, DS, ATUAL))
        rows.append(dict(entrada=m, filtro=f, lotes=2, tp1=0, be=-1, **st, ref="ATUAL"))
    Q = pd.DataFrame(rows)
    Q.to_csv(os.path.join(OUT, "lotes_alvo.csv"), index=False)
    c = ["entrada", "filtro", "lotes", "tp1", "be", "ops", "wr", "pf", "net", "dd", "rdd", "rdd_is", "rdd_oos", "meses"]
    for (m, f), g in Q.groupby(["entrada", "filtro"], sort=False):
        print(f"\n   {m} · {f}")
        print(g.sort_values("rdd_is", ascending=False).head(6)[c].to_string(index=False))
        print("   ref ATUAL:", g[g.get("ref") == "ATUAL"][["ops", "net", "dd", "rdd", "rdd_is", "rdd_oos"]].to_dict("records"))


if __name__ == "__main__":
    main()
