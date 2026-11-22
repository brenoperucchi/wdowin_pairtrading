# -*- coding: utf-8 -*-
"""
Gestão pelas Walls (pedido do usuário em 12/11/2026): esconder o SL atrás da Wall, fazer o BE quando o preço
cruza a próxima Wall e pôr o alvo na Wall seguinte — no lugar do SL 200 / BE 180→20 / saída em 12 barras.

Sinais: os mesmos do especialista (motor v3.2, gatilho Opção C, regra atual → 252 trades), e dois conjuntos
mais largos (sem super · 10–16h; todos os gatilhos) para ver se a gestão por Walls libera mais trades.
Níveis = Walls + MidWalls do dia (as mesmas da âncora). Execução tick a tick em M1, 2 contratos, custo 10 pts
por contrato, uma posição por vez, saída às 17:25.

  STOP   fixo200 · wall_ent−B (primeira Wall abaixo da entrada na compra, − B pts) · wall_piv−B (primeira Wall
         além do extremo do F2, − B) · piv−30 (extremo do F2 − 30). Teto 300, piso 80; sem Wall → 200.
  ALVO   sem (sai no tempo) · W1 (próxima Wall ≥ 60 pts, −15) · W2 (a segunda) · W1+W2 (um lote em cada) ·
         W1+tempo (lote 1 em W1, lote 2 no tempo)
  BE     atual (MFE ≥ 180 → +20 na abertura) · cruzou W1 (+X além dela) → +20 · escada (cada Wall cruzada → stop
         B pts atrás dela) · sem BE
  TEMPO  12 ou 24 barras
Uso: python research/div_master/gestao_walls/teste.py → results/
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "gestao")]
import numba as nb
import numpy as np
import pandas as pd
import bt
import explorar as X
from robustez import market_order

OUT = os.path.join(HERE, "results")
TICK, COST, BRL = 5.0, 10.0, 0.20


@nb.njit(cache=True)
def simw(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, e, ep, d, stop0, tp1, tp2, lv, be_mode, be_trig, be_lock,
         cross_buf, tmax, tick, slip, tp_thru):
    """2 lotes, stop comum. tp1/tp2 = preço do alvo de cada lote (0 = sem alvo, sai no tempo).
    lv = níveis a favor (ordenados a partir da entrada). be_mode: 0 sem · 1 MFE (atual) · 2 cruzou lv[0] → ep+be_lock
    · 3 escada: cruzou lv[i] (+cross_buf) → stop em lv[i] − d·be_lock."""
    n5 = len(o5)
    stop = stop0
    alive = np.array([True, True])
    res = np.zeros(2)
    tgt = np.array([tp1, tp2])
    best = ep
    nxt = 0
    last_t = tm5[e]
    for k in range(e, n5):
        if k > e:
            if be_mode == 1 and (best - ep) * d >= be_trig:
                cand = ep + d * be_lock
                if (o5[k] - cand) * d > 0 and (cand - stop) * d > 0:
                    stop = cand
            if tm5[k] >= 1045 or k - e > tmax:
                for i in range(2):
                    if alive[i]:
                        res[i] = (o5[k] - ep) * d
                        alive[i] = False
                last_t = tm5[k]
                break
        nt = nn[k] if fb[k] == 0 else 4
        for j in range(nt):
            if fb[k] == 0:
                p, op = px[off[k] + j], isop[off[k] + j]
            else:
                if j == 0:
                    p, op = o5[k], True
                elif j == 1:
                    p, op = (l5[k] if d == 1 else h5[k]), False
                elif j == 2:
                    p, op = (h5[k] if d == 1 else l5[k]), False
                else:
                    p, op = c5[k], False
            if k == e and j == 0:
                continue
            for i in range(2):
                if alive[i] and (p - stop) * d <= 0:
                    res[i] = ((p if op else stop - d * tick * slip) - ep) * d
                    alive[i] = False
                    last_t = tm5[k]
            for i in range(2):
                if alive[i] and tgt[i] != 0.0 and ((p - tgt[i]) * d >= tp_thru or (op and (p - tgt[i]) * d >= 0)):
                    res[i] = ((p if op else tgt[i]) - ep) * d
                    alive[i] = False
                    last_t = tm5[k]
            if not (alive[0] or alive[1]):
                return res[0] + res[1], last_t
            if (p - best) * d > 0:
                best = p
            if be_mode == 2 and len(lv) > 0 and (p - (lv[0] + d * cross_buf)) * d >= 0:
                cand = ep + d * be_lock
                if (cand - stop) * d > 0:
                    stop = cand
            if be_mode == 3:
                while nxt < len(lv) and (p - (lv[nxt] + d * cross_buf)) * d >= 0:
                    cand = lv[nxt] - d * be_lock
                    if (cand - stop) * d > 0:
                        stop = cand
                    nxt += 1
    for i in range(2):
        if alive[i]:
            res[i] = (c5[n5 - 1] - ep) * d
            last_t = tm5[n5 - 1]
    return res[0] + res[1], last_t


def levels_dir(levels, ep, d, min_dist):
    lv = sorted([v for v in levels if (v - ep) * d >= min_dist], key=lambda v: (v - ep) * d)
    return np.array(lv, float)


def stop_price(r, g):
    ep, d = r.ep, r.dir
    s = g["stop"]
    if s == "fixo200":
        return ep - d * 200.0
    if s == "piv-30":
        sp = r.piv - d * 30.0
    else:
        buf = g["sbuf"]
        ref = ep if s == "wall_ent" else r.piv
        adv = [v for v in r.levels if (ref - v) * d >= 0 and (ep - v) * d <= 300.0]
        if not adv:
            return ep - d * 200.0
        w = max(adv) if d == 1 else min(adv)          # a Wall mais próxima do lado contra
        sp = w - d * buf
    dist = (ep - sp) * d
    dist = min(max(dist, 80.0), 300.0)
    return ep - d * dist


def run(T, DS, g):
    out, last = [], {}
    for r in T.sort_values(["date", "tm"]).itertuples():
        if r.tm <= last.get(r.date, -1):
            continue
        D = DS[r.dir][r.date] if 1 in DS else DS[r.date]
        ep = r.ep + r.dir * g.get("slip_in", 0.0)
        r = r._replace(ep=ep)
        lv = levels_dir(r.levels, ep, r.dir, 60.0)
        w1 = (lv[0] - r.dir * 15.0) if len(lv) > 0 else 0.0
        w2 = (lv[1] - r.dir * 15.0) if len(lv) > 1 else w1
        t1, t2 = {"sem": (0.0, 0.0), "W1": (w1, w1), "W2": (w2, w2), "W1+W2": (w1, w2), "W1+tempo": (w1, 0.0)}[g["tp"]]
        bem = {"sem": 0, "atual": 1, "cruzou W1": 2, "escada": 3}[g["be"]]
        pts, xt = simw(*bt._args(D), r.e, ep, r.dir, stop_price(r, g), t1, t2, lv, bem, 180.0,
                       20.0 if bem in (1, 2) else g.get("lbuf", 20.0), g.get("cross", 15.0), g["tmax"], TICK,
                       g.get("slip", 1.0), g.get("tp_thru", 0.0))
        last[r.date] = xt
        out.append((r.date, r.tm, xt, (pts - 2 * COST) * BRL, 2, 0.0, 0.0, 0.0, r.super, r.seq, r.dir))
    return pd.DataFrame(out, columns=["date", "tm", "xt", "pnl", "ncon", "lote1", "lote2", "lote3", "super", "seq", "dir"])


def grid():
    G = [dict(nome="ATUAL (SL200 · BE 180→20 · 12 barras)", stop="fixo200", tp="sem", be="atual", tmax=12)]
    stops = [("fixo200", 0), ("piv-30", 0)] + [(s, b) for s in ("wall_ent", "wall_piv") for b in (20.0, 40.0, 60.0)]
    for (s, b), tp, be, tmax in itertools.product(stops, ("sem", "W1", "W2", "W1+W2", "W1+tempo"),
                                                  ("sem", "atual", "cruzou W1", "escada"), (12, 24)):
        if tp == "sem" and be == "sem":
            continue
        nome = f"SL {s}{'' if not b else f'−{b:.0f}'} · TP {tp} · BE {be} · {tmax}b"
        G.append(dict(nome=nome, stop=s, sbuf=b, tp=tp, be=be, tmax=tmax, lbuf=20.0))
    return G


def main():
    os.makedirs(OUT, exist_ok=True)
    U = X.universe()
    DS = bt.market("WIN")
    T = X.entries(U, DS, "OPC")
    sets = {"regra atual": X.FILTERS["regra atual"](T),
            "sem super · 10–16h": X.FILTERS["sem super · 10–16h"](T),
            "todos os gatilhos": T}
    G = grid()
    rows = []
    for sname, Ts in sets.items():
        for g in G:
            st = X.stats(run(Ts, DS, g))
            rows.append(dict(sinais=sname, gestao=g["nome"], **st))
        print(sname, "ok", flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "grade.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 70)
    c = ["sinais", "gestao", "ops", "wr", "pf", "net", "dd", "rdd", "rdd_is", "rdd_oos", "meses"]
    for sname in sets:
        Q = R[R.sinais == sname]
        print(f"\n== {sname} · referência:")
        print(Q[Q.gestao.str.startswith("ATUAL")][c].to_string(index=False))
        print("top 10 por Ret/DD jan–jul:")
        print(Q.sort_values("rdd_is", ascending=False).head(10)[c].to_string(index=False))
        print("mediana da grade por tipo de stop / alvo / BE (Ret/DD completo):")
        Q = Q.assign(st=Q.gestao.str.extract(r"SL (\S+)")[0], tp=Q.gestao.str.extract(r"TP (\S+)")[0],
                     be=Q.gestao.str.extract(r"BE ([^·]+)")[0].str.strip())
        for k in ("st", "tp", "be"):
            print("  ", Q.groupby(k).rdd.median().round(2).to_dict())

    # estresse de execução nas 5 melhores (jan–jul) de cada conjunto + a atual
    DSadv = {1: market_order("WIN", True), -1: market_order("WIN", False)}
    STRESS = {"base": {}, "alvo +1 tick": dict(tp_thru=5.0), "stop 2 ticks": dict(slip=2.0),
              "caminho ruim": dict(adv=True), "entrada pior": dict(slip_in=5.0),
              "tudo junto": dict(tp_thru=5.0, slip=2.0, adv=True, slip_in=5.0)}
    byname = {g["nome"]: g for g in G}
    srows = []
    print("\nESTRESSE (Ret/DD completo · jan–jul / ago–nov):")
    for sname, Ts in sets.items():
        Q = R[R.sinais == sname].sort_values("rdd_is", ascending=False)
        names = [G[0]["nome"]] + [n for n in Q.gestao.head(5) if n != G[0]["nome"]][:4]
        for n in names:
            line = []
            for k, s in STRESS.items():
                gg = dict(byname[n], **{a: b for a, b in s.items() if a != "adv"})
                st = X.stats(run(Ts, DSadv if s.get("adv") else DS, gg))
                srows.append(dict(sinais=sname, gestao=n, estresse=k, **st))
                line.append(f"{k} {st['rdd']:5.2f}")
            print(f"  {sname:18s} {n[:62]:62s} | " + " · ".join(line), flush=True)
    pd.DataFrame(srows).to_csv(os.path.join(OUT, "estresse.csv"), index=False)


if __name__ == "__main__":
    main()
