# -*- coding: utf-8 -*-
"""
Realismo de execução das gestões de 3 lotes com alvo curto (explorar.py / analise.py).
Alvo de 30 pts e zero a +20 ficam a 2 ticks um do outro — exatamente onde a simulação em M1 pode ser otimista.
Estresses:
  R0 base         : como na grade (alvo preenche ao tocar, stop 1 tick pior, caminho M1 pelo extremo mais próximo)
  R1 alvo +1 tick : o limite só preenche se o preço passar 1 tick além (fila)
  R2 stop 2 ticks : stops preenchem 2 ticks piores
  R3 caminho ruim : em cada barra M1 o extremo CONTRA a posição vem primeiro
  R4 entrada pior : entrada 1 tick pior que a abertura
  R5 tudo junto   : R1 + R2 + R3 + R4
Uso: python research/div_master/gestao/robustez.py
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import pandas as pd
import explorar as X
import bt
import modulo as M
from research.discover_gex_nwe_setups import compute_nwe_series

pd.set_option("display.width", 250)


def market_order(asset, low_first):
    """bt.market com a ordem dos ticks M1 fixa: O→L→H→C (low_first) ou O→H→L→C."""
    sym = "WIN_N" if asset == "WIN" else "WDO_N"
    m5 = pd.read_csv(os.path.join(bt.RATES, f"mt5_{sym}_M5.csv"), parse_dates=["t"])
    m5["date"] = m5.t.dt.strftime("%Y-%m-%d")
    m5["tm"] = m5.t.dt.hour * 60 + m5.t.dt.minute
    m5 = m5[(m5.tm >= 540) & (m5.tm <= 1075) & (m5.date <= bt.END)].reset_index(drop=True)
    cl = m5.close.values.astype(float)
    n30 = compute_nwe_series(cl, 30, 3.0, 1.6)[:3]
    n50 = compute_nwe_series(cl, *bt.N50)[:3]
    m1 = pd.read_csv(os.path.join(bt.RATES, f"mt5_{sym}_M1.csv"), parse_dates=["t"])
    m1["date"] = m1.t.dt.strftime("%Y-%m-%d")
    m1["tm"] = m1.t.dt.hour * 60 + m1.t.dt.minute
    m1g = {d: g for d, g in m1.groupby("date")}
    DS = {}
    for d, idx in m5.groupby("date").indices.items():
        idx = np.sort(idx)
        pv = np.maximum(idx - 1, 0)
        tm5 = m5.tm.values[idx].astype(np.int64)
        px, op = [], []
        off, nn, fb = np.zeros(len(idx), np.int64), np.zeros(len(idx), np.int64), np.ones(len(idx), np.int64)
        g = m1g.get(d)
        if g is not None:
            mm = g.tm.values
            o1, h1, l1, c1 = (g[c].values.astype(float) for c in ("open", "high", "low", "close"))
            for k, t in enumerate(tm5):
                sel = np.where((mm >= t) & (mm < t + 5))[0]
                off[k] = len(px)
                if len(sel) == 0:
                    continue
                fb[k] = 0
                for s in sel:
                    seq = (o1[s], l1[s], h1[s], c1[s]) if low_first else (o1[s], h1[s], l1[s], c1[s])
                    for q, v in enumerate(seq):
                        px.append(v)
                        op.append(q == 0)
                nn[k] = len(px) - off[k]
        DS[d] = dict(px=np.array(px, float), op=np.array(op, np.bool_), off=off, nn=nn, fb=fb,
                     o5=m5.open.values[idx].astype(float), h5=m5.high.values[idx].astype(float),
                     l5=m5.low.values[idx].astype(float), c5=m5.close.values[idx].astype(float), tm5=tm5,
                     u30=n30[1][pv], l30=n30[2][pv], c50=n50[0][pv], u50=n50[1][pv], l50=n50[2][pv],
                     pos={int(t): k for k, t in enumerate(tm5)})
    return DS


def cfg3(tp1, lots=3, be=20.0, **kw):
    g = dict(name="", kind="3L", lots=lots, stop="piv", sl=150.0, tp1=tp1, lot2="wall", tp2_fix=300.0, lot3="600",
             trail=150.0, be=be, tmax=24, tmax3=200)
    g.update(kw)
    return g


STRESS = {
    "R0 base": dict(),
    "R1 alvo +1 tick": dict(tp_thru=5.0),
    "R2 stop 2 ticks": dict(slip=2.0),
    "R3 caminho ruim": dict(adverse=True),
    "R4 entrada pior": dict(slip_in=5.0),
    "R5 tudo junto": dict(tp_thru=5.0, slip=2.0, adverse=True, slip_in=5.0),
}


def main():
    U = X.universe()
    DS = bt.market("WIN")
    DSadv = {1: market_order("WIN", True), -1: market_order("WIN", False)}   # compra: mínima primeiro; venda: máxima
    T = {m: X.entries(U, DS, m) for m in ("CONF", "OPC")}
    tests = [
        ("CONF", "todas", "3L T1 30", cfg3(30.0)),
        ("CONF", "todas", "3L T1 60", cfg3(60.0)),
        ("CONF", "todas", "3L T1 100", cfg3(100.0)),
        ("CONF", "sem super · 10–16h", "3L T1 30", cfg3(30.0)),
        ("CONF", "sem super · 10–16h", "3L T1 60", cfg3(60.0)),
        ("OPC", "regra atual", "ATUAL 2c", X.grid()[0]),
    ]
    rows = []
    for m, f, gname, g in tests:
        Tf = X.FILTERS[f](T[m])
        for sname, s in STRESS.items():
            gg = dict(g, **{k: v for k, v in s.items() if k != "adverse"})
            R = X.run_cfg(Tf, DSadv if s.get("adverse") else DS, gg)
            st = X.stats(R)
            rows.append(dict(entrada=m, filtro=f, gestao=gname, estresse=sname, lote1=round(R.lote1.sum()),
                             lote2=round(R.lote2.sum()), lote3=round(R.lote3.sum()), **st))
            print(f"{m:4s} {f:20s} {gname:9s} {sname:16s} {st['ops']:5d} tr · PF {st['pf']:4.2f} · R$ {st['net']:7.0f} · "
                  f"DD {st['dd']:5.0f} · Ret/DD {st['rdd']:5.2f} (jan–jul {st['rdd_is']:5.2f} · ago–nov {st['rdd_oos']:5.2f}) · "
                  f"lotes {R.lote1.sum():6.0f}/{R.lote2.sum():6.0f}/{R.lote3.sum():6.0f}", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(X.OUT, "robustez.csv"), index=False)


if __name__ == "__main__":
    main()
