# -*- coding: utf-8 -*-
"""
WDO — confirmação do filtro achado em filtros.py: só Walls principais (sem MidWall), ordem limite no 1º toque.
1) combinações por evento (alvo 6 / stop 4); 2) grade completa de alvo/stop, um trade por vez, toque × fila, placebo.
Uso: python research/div_master/wdo_ima/so_walls.py
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "research", "div_master", "especialistas")]
import numpy as np
import pandas as pd
import teste as T
import limite as LM
import filtros as F
import bt
from research.div_wall.data import load_asset

pd.set_option("display.width", 220)


def show(lbl, g):
    s = {p: F.summ(x) for p, x in g.groupby("per")}
    parts = []
    for p in ("jan-jul", "ago-nov"):
        v = s.get(p)
        if v:
            parts.append(f"{p}: n {v['n']:3d} resp {v['resp']:4.1f}% PFtoq {v['pf_toque']:.2f} PFfila {v['pf_fila']:.2f} "
                         f"R$fila {v['rs_fila']:+.0f}")
    print(f"{lbl:24s} " + " | ".join(parts))


def main():
    E = pd.read_csv(os.path.join(T.OUT, "eventos_toque.csv"))
    E["per"] = np.where(E.date <= T.IS_END, "jan-jul", "ago-nov")
    q = E.loc[E.per == "jan-jul", "nwe"].quantile(2 / 3)
    show("todas", E)
    show("só Wall", E[E.tipo == "Wall"])
    show("Wall largura ≥ 2", E[(E.tipo == "Wall") & (E.largura >= 2)])
    show("Wall + NWE esticada", E[(E.tipo == "Wall") & (E.nwe > q)])
    show("MidWall", E[E.tipo == "MidWall"])

    data = load_asset("WDO", "M5")
    DS = bt.market("WDO")
    walls = {d: sorted(float(w["price"]) for w in v[1] if w.get("type") == "Wall") for d, v in data.items() if d in DS}
    plac = [{d: T.placebo(lv, np.random.default_rng(1000 * s + i)) for i, (d, lv) in enumerate(sorted(walls.items()))}
            for s in range(5)]
    rows = []
    for tp, sl, qq in itertools.product((3.0, 4.0, 6.0, 8.0), (3.0, 4.0, 6.0, 8.0), (False, True)):
        r = LM.evaluate(DS, walls, tp, sl, 12, qq)
        pp = np.mean([LM.evaluate(DS, p, tp, sl, 12, qq)["pf"] for p in plac])
        rows.append(dict(tp=tp, sl=sl, fila=qq, **r, placebo=round(pp, 2)))
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(T.OUT, "so_walls.csv"), index=False)
    for qq in (False, True):
        X = R[R.fila == qq]
        print(f"\n{'FILA (passa 1 tick)' if qq else 'TOQUE'} · só Walls, um trade por vez, 16 alvo/stop: PF mediano "
              f"{X.pf.median():.2f} (placebo {X.placebo.median():.2f}) · PF > 1 nas duas metades em "
              f"{int(((X.pf_is > 1) & (X.pf_oos > 1)).sum())}/16")
        print(X.sort_values("pf", ascending=False).head(8)[["tp", "sl", "ops", "wr", "pf", "pf_is", "pf_oos", "net", "dd",
                                                           "rdd", "placebo"]].to_string(index=False))


if __name__ == "__main__":
    main()
