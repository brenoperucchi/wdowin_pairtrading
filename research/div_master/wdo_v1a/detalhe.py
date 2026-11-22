# -*- coding: utf-8 -*-
"""Detalhes da validação do V1a: leituras possíveis do alvo ProxWall (para bater os 184 trades informados) e de onde
vem o resultado (hora, módulo de abertura). Uso: python research/div_master/wdo_v1a/detalhe.py"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import pandas as pd
import validar as V
import bt
from research.div_wall.data import load_asset


def run_variant(T, DS, mode):
    X = V.X
    m = (T.d_wall <= 3.5) & (T.ext30 > 0) & ((T.tm // 60) != 11) & (T.tm >= 540) & (T.tm <= 1020)
    rows, last = [], {}
    for r in T[m].sort_values(["date", "tm"]).itertuples():
        if r.tm <= last.get(r.date, -1):
            continue
        d = r.dir
        lv = r.levels if mode != "todos níveis" else r.all_levels
        nxt = sorted([w for w in lv if (w - r.ep) * d > 0], key=lambda w: (w - r.ep) * d)
        if mode == "pula Wall colada":
            nxt = [w for w in nxt if d * (w - r.ep) - 0.5 >= 2.5]
        if not nxt:
            if mode == "sem Wall → 22":
                tp = 22.0
            else:
                continue
        else:
            nw_d = d * (nxt[0] - r.ep) - 0.5
            if nw_d < 2.5 and mode not in ("sem abortar",):
                continue
            tp = min(max(nw_d, 4.0), 22.0)
        D = DS[r.date]
        pts, xt = bt.sim(*bt._args(D), D["u30"], int(r.e), r.ep, d, 14.0, r.ep + d * tp, False, 0.0, 0.0, 0.0, 0.0, 0.0,
                         24, X["tick"])
        last[r.date] = xt
        rows.append((r.date, r.tm, int(xt), (pts - X["cost"]) * X["brl"], d))
    return rows


def main():
    data = load_asset("WDO", "M5")
    DS = bt.market("WDO")
    T = V.candidates(data, DS)
    allv = {d: sorted(float(w["price"]) for w in v[1] if w.get("type") in ("Wall", "MidWall")) for d, v in data.items()}
    T["all_levels"] = T.date.map(allv)
    print("leituras do alvo ProxWall (informado: 184 tr · R$ 4.498 · Ret/DD 7,62):")
    for mode in ("como descrito", "pula Wall colada", "sem Wall → 22", "sem abortar", "todos níveis"):
        V.line(mode, V.stats(run_variant(T, DS, mode)))
    print("\nTP fixo 12 por hora de entrada:")
    R = pd.DataFrame(V.run(T, DS, tp_mode="fix"), columns=["date", "tm", "xt", "brl", "dir"])
    R["h"] = R.tm // 60
    print(R.groupby("h").brl.agg(["count", "sum", "mean"]).round(1).to_string())
    T0 = V.candidates(data, DS, opt=dict(V.OPT_V1A, open_module=False))
    R0 = pd.DataFrame(V.run(T0, DS, tp_mode="fix"), columns=["date", "tm", "xt", "brl", "dir"])
    k1 = set(zip(R.date, R.tm, R.dir))
    k0 = set(zip(R0.date, R0.tm, R0.dir))
    only1 = R[[k not in k0 for k in zip(R.date, R.tm, R.dir)]]
    print(f"\nTP12 com abertura: {len(R)} tr R$ {R.brl.sum():.0f} · sem abertura: {len(R0)} tr R$ {R0.brl.sum():.0f} · "
          f"trades que só existem com o módulo: {len(only1)} (R$ {only1.brl.sum():.0f}), por hora: "
          f"{only1.groupby(only1.tm // 60).brl.agg(['count', 'sum']).round(0).to_dict('index')}")


if __name__ == "__main__":
    main()
