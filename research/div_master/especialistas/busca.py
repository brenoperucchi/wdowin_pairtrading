# -*- coding: utf-8 -*-
"""
Busca de gatilho (pedido do usuário em 12/11/2026: período completo jan–6/nov, continuar até Ret/DD > 10).
Toda configuração avaliada vai para results/variations_log.csv (conta tudo o que foi tentado).
Uso: python busca.py prep   → results/cache_{ativo}_{motor}.pkl
     python busca.py r0     → rodada 0 (SPEC como está)
"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bt  # noqa: E402
import modulo as M  # noqa: E402

RES = os.path.join(HERE, "results")
LOG = os.path.join(RES, "variations_log.csv")


def cache(asset, engine):
    return os.path.join(RES, f"cache_{asset}_{engine.replace('.', '')}.pkl")


def prep():
    for a in ("WIN", "WDO"):
        DS = bt.market(a)
        for e in M.ENGINES:
            S = bt.signals(a, e)
            T = bt.simulate(a, S, DS)
            pickle.dump(T, open(cache(a, e), "wb"))
            print(a, e, len(T), "sinais", int(T.ok.sum()), "com entrada", flush=True)


def load(asset, engine):
    return pickle.load(open(cache(asset, engine), "rb"))


def log(rows):
    df = pd.DataFrame(rows)
    df["ts"] = datetime.now().isoformat(timespec="seconds")
    df.to_csv(LOG, mode="a", header=not os.path.exists(LOG), index=False)


def sel_esp(T, esp):
    T = T[T.ok]
    if esp == "AMBOS":
        return T[~T.dup]
    return T[T.esp == esp]


def r0():
    rows = []
    for e in M.ENGINES:
        TT = {a: load(a, e) for a in ("WIN", "WDO")}
        for esp in ("WALL", "EXTREMO", "AMBOS"):
            for x in ("A", "B"):
                sw = bt.stats(sel_esp(TT["WIN"], esp), f"pnl_{x}", f"xt_{x}")
                sd = bt.stats(sel_esp(TT["WDO"], esp), f"pnl_{x}", f"xt_{x}")
                mult = 1.0 if x == "A" else 2.0
                sp = bt.portfolio(sel_esp(TT["WIN"], esp), sel_esp(TT["WDO"], esp), f"pnl_{x}", f"pnl_{x}",
                                  f"xt_{x}", f"xt_{x}", mult_w=mult)
                for lab, s in (("WIN", sw), ("WDO", sd), ("CARTEIRA", sp)):
                    rows.append(dict(rodada="r0", motor=e, esp=esp, saida=x, filtro="nenhum", ativo=lab, **s))
    log(rows)
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(R[["motor", "esp", "saida", "ativo", "ops", "wr", "pf", "net", "dd", "rdd", "meses", "rdd_is", "rdd_oos"]]
          .to_string(index=False))


if __name__ == "__main__":
    os.makedirs(RES, exist_ok=True)
    {"prep": prep, "r0": r0}[sys.argv[1]]()
