# -*- coding: utf-8 -*-
"""
Teste nulo da busca `busca_win_v32.py`: roda EXATAMENTE a mesma grade (configs × âncoras × janelas × contextos ×
saídas, mesmo critério de aprovação: ≥ 100 trades, Ret/DD ≥ 5, H1 > 0, H2 > 0, ago–nov > 0), mas com a DIREÇÃO de
cada sinal sorteada (moeda honesta). Os horários, a quantidade de sinais, os filtros e as saídas são os mesmos —
só não existe mais vantagem direcional. Quantas "estratégias aprovadas" a busca acha no puro ruído?
Uso: python research/div_master/win_especialista/nulo_busca.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.div_master.especialistas import bt, modulo as M
import research.div_master.win_especialista.busca_win_v32 as B


def search(df, presims, mode):
    """Mesmo laço de aprovação do busca_win_v32 (copiado), devolve a lista de Ret/DD aprovados e o total testado."""
    if mode == "OPC":
        anc = {"ALL": np.ones(len(df), bool), "WALL_ESP": (df.esp == "WALL").values, "EXT_ESP": (df.esp == "EXTREMO").values,
               "NO_SUP_SEQ2": (~df.is_super & (df.seq <= 1)).values, "DWALL150": (df.d_wall <= 150.0).values}
    else:
        anc = {"COMMON": (df.has_w | df.has_d).values, "ANY_WALL": df.has_w.values, "DWALL150": (df.d_wall <= 150.0).values,
               "C1_ONLY": df.has_c1.values}
    tms = {"ALL": np.ones(len(df), bool), "09_12": (df.tm <= 720).values, "09_13": (df.tm <= 780).values,
           "09_15": (df.tm <= 900).values, "10_16": ((df.tm >= 600) & (df.tm < 960)).values,
           "HH_NE_11": (df.hh != 11).values, "MANHA_09_11": (df.tm < 660).values}
    ctx = {"NONE": np.ones(len(df), bool), "ext30>0": (df.ext30 > 0).values,
           "ext50>-0.5&sl>-0.5": ((df.ext50 > -0.5) & (df.slope50 > -0.5)).values, "ext50>0": (df.ext50 > 0).values,
           "pass>0": (df.pass_ > 0).values, "candle_fav": df.candle_fav.values}
    hits, tested = [], 0
    for ma in anc.values():
        for mt in tms.values():
            if (ma & mt).sum() < 100:
                continue
            for mc in ctx.values():
                mask = ma & mt & mc
                if mask.sum() < 100:
                    continue
                base = df.loc[mask, ["date", "tm"]]
                for p_arr, x_arr in presims.values():
                    sp = p_arr[mask]
                    v = ~np.isnan(sp)
                    if v.sum() < 100:
                        continue
                    sub = base.iloc[v].copy()
                    sub["pnl"] = sp[v]
                    sub["xt"] = x_arr[mask][v]
                    sub = bt.mgmt(sub, "pnl", "xt", "UM")
                    if len(sub) < 100:
                        continue
                    tested += 1
                    st = bt.stats(sub, "pnl", "xt")
                    if st["rdd"] >= 5.0 and st["h1"] > 0 and st["h2"] > 0 and st["oos"] > 0:
                        hits.append(st["rdd"])
    return hits, tested


def main(seeds=5):
    configs = [
        (B.make_PW(150, 220), "all", M.V32_PROD, "CONF"), (B.make_PW(150, 220), "all", M.V32_PROD, "OPC"),
        (B.make_PW(150, 220), "wall", M.V32_PROD, "CONF"), (B.make_PW(150, 220), "wall", M.V32_PROD, "OPC"),
        (B.make_PW(150, 220), "all", B.OPT_WIN_OPEN, "CONF"), (B.make_PW(150, 220), "all", B.OPT_WIN_OPEN, "OPC"),
        (B.make_PW(150, 220), "wall", B.OPT_WIN_OPEN, "CONF"), (B.make_PW(150, 220), "wall", B.OPT_WIN_OPEN, "OPC"),
        (B.make_PW(100, 150), "wall", M.V32_PROD, "CONF"), (B.make_PW(100, 150), "wall", B.OPT_WIN_OPEN, "CONF"),
    ]
    bases = [(B.collect_base(P, lv, opt, mode), mode) for P, lv, opt, mode in configs]
    real_hits, real_tested = [], 0
    for df, mode in bases:
        h, t = search(df, {n: B.presim_exit(df, c) for n, c in B.EXITS}, mode)
        real_hits += h
        real_tested += t
    print(f"REAL: {real_tested} estratégias testadas · {len(real_hits)} aprovadas · maior Ret/DD {max(real_hits):.2f}", flush=True)
    for s in range(seeds):
        rng = np.random.default_rng(s)
        hits, tested = [], 0
        for df, mode in bases:
            dfr = df.copy()
            dfr["dir"] = rng.choice((-1, 1), len(dfr))
            h, t = search(dfr, {n: B.presim_exit(dfr, c) for n, c in B.EXITS}, mode)
            hits += h
            tested += t
        print(f"NULO {s} (direção sorteada): {tested} testadas · {len(hits)} aprovadas · "
              f"maior Ret/DD {max(hits) if hits else 0:.2f} · aprovadas com Ret/DD ≥ 7: {sum(x >= 7 for x in hits)}", flush=True)


if __name__ == "__main__":
    main()
