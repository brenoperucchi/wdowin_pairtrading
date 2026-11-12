"""
Validação do WIN "rompimento da Wall com a maior força de barra do dia" (research/div_v3/RESULTADOS.md, etapa D).
1. Grade só jan–jul. Platô = mediana do score da config e das vizinhas (stop ±1, outro tempo máx., com/sem BE,
   com/sem trailing). Fica a de maior platô.
2. Placebos (jan–jul, p < 0,10 nos dois):
   (a) rompimentos sem condição de fluxo, sorteados na mesma quantidade por (mês, direção) → mede o fluxo;
   (b) barras quaisquer → mede o sinal inteiro.
3. Ago–6/nov UMA vez (trava results/oos_rom.json). Aprovação: PF ≥ 1,3, lucro > 0, ≥ 3 de 4 meses positivos.
Uso: python -m research.div_v3.valida_rom
"""
from __future__ import annotations

import itertools
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div3m import bt_div3m as BT  # noqa: E402
from research.div3m import investigar as INV  # noqa: E402
from research.div_v3 import sinais as SV3  # noqa: E402

OUT = os.path.join(ROOT, "research", "div_v3", "results")
LOCK = os.path.join(OUT, "oos_rom.json")
ASSET = "WIN"
N_PLACEBO, P_MAX = 200, 0.10


def prep(flow):
    INV.load = SV3.load
    SV3.MODE, SV3.ROM_FLOW = "rom", flow
    return BT.prepare(ASSET)


def grid(E, X):
    sp = BT.SPEC[ASSET]
    rows = []
    for en, (T, pn, xt) in E.items():
        sel = np.where(T["is"].values)[0]
        for xi, x in enumerate(X):
            ct = 2 if x["tp"] == "2lotes" else 1
            for md, cap in itertools.product(("LIVRE", "UM_POR_VEZ"), (False, True)):
                acc = BT.mgmt(sel, T.tm.values, T.di.values, pn[:, xi], xt[:, xi], md, cap, sp["cap"] * ct)
                s = BT.st(acc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)
                rows.append(dict(entrada=en, xi=xi, stop=f"{x['stop'][0]}{x['stop'][1]:g}", tp=x["tp"], be=x["be"],
                                 trail=x["trail"], tmax=x["tmax"], mode=md, cap=cap, **s, score=BT.score(s)))
    return pd.DataFrame(rows)


def run_cfg(T, pn, xt, xi, mode, cap, mask):
    sp = BT.SPEC[ASSET]
    ct = 2 if BT.exits(ASSET)[xi]["tp"] == "2lotes" else 1
    acc = BT.mgmt(np.where(mask)[0], T.tm.values, T.di.values, pn[:, xi], xt[:, xi], mode, cap, sp["cap"] * ct)
    return acc, BT.st(acc, pn[:, xi], T.di.values, T.mon.values, T.h1.values)


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(LOCK):
        raise SystemExit("OOS já executado (results/oos_rom.json).")
    t0 = datetime.now()
    sp = BT.SPEC[ASSET]
    P, F, X, E, DS, mt5 = prep("force")
    g0 = grid(E, X)
    key = ["entrada", "stop", "tp", "be", "trail", "tmax", "mode", "cap"]
    idx = {tuple(k): s for k, s in zip(g0[key].itertuples(index=False, name=None), g0.score.values)}
    stops = [f"{a}{b:g}" for a, b in sp["stops"]]
    plat = []
    for row in g0[key + ["score"]].itertuples(index=False, name=None):
        k = list(row[:-1])
        vals = [row[-1]]
        si = stops.index(k[1])
        for sj in (si - 1, si + 1):
            if 0 <= sj < len(stops):
                kk = list(k); kk[1] = stops[sj]; vals.append(idx.get(tuple(kk), 0.0))
        for col, alt in ((5, 72 - k[5]), (3, not k[3]), (4, not k[4])):
            kk = list(k); kk[col] = alt; vals.append(idx.get(tuple(kk), 0.0))
        plat.append(float(np.median(vals)))
    g0["plateau"] = plat
    g0.to_csv(os.path.join(OUT, "valida_rom_grid.csv.gz"), index=False, compression="gzip")
    g0 = g0.sort_values(["plateau", "score", "ops"], ascending=False)
    top = g0.iloc[0].to_dict()
    X = BT.exits(ASSET)
    xi = int(top["xi"])
    print(f"Escolha IS: {top['entrada']} | {BT.xname(X[xi], ASSET)} | {top['mode']} meta={top['cap']} | platô "
          f"{top['plateau']:.2f} | IS {top['ops']} tr PF {top['pf']} R$ {top['net']} DD {top['dd']} Ret/DD {top['rdd']} "
          f"meses {top['meses']} H1 {top['net_h1']} H2 {top['net_h2']}", flush=True)
    vals = g0.plateau.values
    print(f"Platô: configs com platô > 0: {int((vals > 0).sum())}/{len(vals)} · top-10 platôs {np.round(vals[:10], 2).tolist()}")

    # placebos (só IS)
    T, pn, xt = E[top["entrada"]]
    isv = T["is"].values
    acc, s_is = run_cfg(T, pn, xt, xi, top["mode"], top["cap"], isv)
    want = defaultdict(int)
    for i in acc:
        want[(T.mon.values[i], T.direction.values[i])] += 1
    _, _, _, EA, _, _ = prep("none")
    TA, pa_, xa_ = EA[top["entrada"]]
    pool = defaultdict(list)
    for i in np.where(TA["is"].values)[0]:
        pool[(TA.mon.values[i], TA.direction.values[i])].append(i)
    rng = random.Random(7)
    ct = 2 if X[xi]["tp"] == "2lotes" else 1
    pa = []
    for _ in range(N_PLACEBO):
        pick = np.array(sorted(j for kk, nn in want.items() for j in rng.sample(pool[kk], min(nn, len(pool[kk])))), int)
        a2 = BT.mgmt(pick, TA.tm.values, TA.di.values, pa_[:, xi], xa_[:, xi], top["mode"], top["cap"], sp["cap"] * ct)
        pa.append(BT.st(a2, pa_[:, xi], TA.di.values, TA.mon.values, TA.h1.values)["rdd"])
    lo_w, hi_w = INV.WINDOW[ASSET]
    br = []
    for dte, D in DS.items():
        if dte > BT.IS_END:
            continue
        for i in range(len(D["o5"]) - 1):
            if not (lo_w <= D["tm5"][i + 1] <= hi_w):
                continue
            for dirn in (1, -1):
                f = BT.fill(D, top["entrada"], i + 1, dirn, D["h5"][i], D["l5"][i], sp["tick"])
                if f is None:
                    continue
                k, j, ep = f
                piv = D["l5"][i] if dirn == 1 else D["h5"][i]
                p_, t_ = BT.run_trade(D, k, j, ep, dirn, piv, X[xi], ASSET)
                br.append((dte, int(D["tm5"][k]), dirn, p_, t_))
    B = pd.DataFrame(br, columns=["date", "tm", "direction", "pnl", "xt"]).sort_values(["date", "tm"]).reset_index(drop=True)
    B["di"] = pd.factorize(B.date, sort=True)[0]
    B["mon"] = B.date.str[5:7].astype(int) - 1
    B["h1"] = B.date <= BT.H1_END
    bpool = defaultdict(list)
    for i, (mo, dr) in enumerate(zip(B.mon.values, B.direction.values)):
        bpool[(mo, dr)].append(i)
    pb = []
    for _ in range(N_PLACEBO):
        pick = np.array(sorted(j for kk, nn in want.items() for j in rng.sample(bpool[kk], min(nn, len(bpool[kk])))), int)
        a2 = BT.mgmt(pick, B.tm.values, B.di.values, B.pnl.values, B.xt.values.astype(int), top["mode"], top["cap"], sp["cap"] * ct)
        pb.append(BT.st(a2, B.pnl.values, B.di.values, B.mon.values, B.h1.values)["rdd"])
    p_a = (1 + sum(v >= s_is["rdd"] for v in pa)) / (1 + len(pa))
    p_b = (1 + sum(v >= s_is["rdd"] for v in pb)) / (1 + len(pb))
    ok_is = bool(top["plateau"] > 0 and p_a < P_MAX and p_b < P_MAX)
    print(f"Placebo (a) rompimento sem fluxo: p={p_a:.3f} (Ret/DD mediano {np.median(pa):.2f}) · "
          f"(b) barras: p={p_b:.3f} (mediano {np.median(pb):.2f}) · passa no IS: {ok_is}", flush=True)

    # trava e OOS
    regras = dict(sinal="rompimento de Wall/MidWall no fechamento com a maior força de barra do dia no sentido",
                  entrada=top["entrada"], saida=BT.xname(X[xi], ASSET), mode=top["mode"], meta_diaria=bool(top["cap"]))
    json.dump({"executed_at": datetime.now().isoformat(timespec="seconds"), "regras": regras,
               "is": {k: top[k] for k in ("ops", "wr", "pf", "net", "dd", "rdd", "meses", "net_h1", "net_h2", "plateau")},
               "placebo_a_p": p_a, "placebo_b_p": p_b, "ok_is": ok_is}, open(LOCK, "w", encoding="utf-8"), indent=1, default=str)
    acc_o, s_o = run_cfg(T, pn, xt, xi, top["mode"], top["cap"], ~isv)
    acc_all = np.array(sorted(list(acc) + list(acc_o)), int)
    s_all = BT.st(acc_all, pn[:, xi], T.di.values, T.mon.values, T.h1.values)
    aprov = bool(ok_is and s_o["pf"] >= 1.3 and s_o["net"] > 0 and int(s_o["meses"].split("/")[0]) >= 3)
    mon = pd.Series(pn[acc_all, xi]).groupby(T.date.values[acc_all].astype(str)).sum()
    mensal = mon.groupby(mon.index.str[:7]).sum().round().to_dict()
    log = json.load(open(LOCK, encoding="utf-8"))
    log.update(oos=s_o, total=s_all, aprovado_oos=aprov, mensal=mensal)
    json.dump(log, open(LOCK, "w", encoding="utf-8"), indent=1, default=str)
    pd.DataFrame(dict(date=T.date.values[acc_all], tm=T.tm.values[acc_all], direction=T.direction.values[acc_all],
                      ep=T.ep.values[acc_all], brl=pn[acc_all, xi], exit_tm=xt[acc_all, xi],
                      part=np.where(isv[acc_all], "is", "oos"))).to_csv(os.path.join(OUT, "oos_rom_trades.csv"), index=False)
    print(f"OOS ago–6/nov: {s_o}")
    print(f"Completo: {s_all}")
    print(f"Mensal: {mensal}")
    print(f"Aprovado: {aprov} · {datetime.now() - t0}")


if __name__ == "__main__":
    main()
