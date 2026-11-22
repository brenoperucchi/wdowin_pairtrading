# -*- coding: utf-8 -*-
"""
Exploração de gestão sobre TODAS as marcações do motor oficial v3.2 (sem abertura), WIN, 02/01–11/11.

Pergunta do usuário (12/11/2026): o especialista opera pouco (222 de 716 marcações); com outra gestão de risco
dá para operar todas, ou quase todas? Ideias dele:
  (A) 3 contratos, stop curto: lote 1 sai rápido e puxa os outros para o zero, lote 2 sai na próxima Wall,
      lote 3 é conduzido até o mais longe;
  (B) entra com 1 contrato e põe outro quando anda contra, com stop maior (preço médio).

Universo: cada divergência do motor (com extensões), âncora Wall/MidWall ou extremo do dia, conhecida na barra de
confirmação. Entradas:
  CONF = a mercado na abertura da barra seguinte à confirmação (toda divergência tem);
  OPC  = gatilho Opção C como hoje (só as que têm).
Execução tick a tick em M1 (O→H→L→C ou O→L→H→C, como o Strategy Tester), custo 10 pts por contrato,
stop sem gap preenche 1 tick pior, saída forçada 17:25. Uma posição por vez (a próxima só depois de zerar).
Avaliação: jan–jul (escolha) × ago–nov (conferência). Ago–nov já foi muito usado → não é OOS limpo.
Uso: python research/div_master/gestao/explorar.py → results/
"""
import itertools, os, pickle, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas")]
import numba as nb
import numpy as np
import pandas as pd
import modulo as M, bt
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
TICK, COST, BRL = 5.0, 10.0, 0.20
EOD = 1045
IS_END = "2026-07-31"


# ───────────────────────── universo ─────────────────────────

def universe():
    cache = os.path.join(OUT, "universo.pkl")
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    M.V32 = dict(M.V32_PROD)
    rows = []
    for d, (bars, walls, _) in sorted(load_asset("WIN", "M5").items()):
        if d > bt.END:
            continue
        fb, R = M.run_day("WIN", bars, walls, engines=("v3.2",))
        lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        cands = R["v3.2"]["cands"]
        trig, seqd, seqk = {}, {1: 0, -1: 0}, {}
        for x in R["v3.2"]["trig"]:                         # em ordem de barra, como no core
            if x["idx"] + 1 >= len(fb):
                continue
            if (x["dir"], x["j"]) not in trig:
                trig[(x["dir"], x["j"])] = x                   # primeiro gatilho Opção C do candidato
                seqk[(x["dir"], x["j"])] = seqd[x["dir"]]      # ordem do gatilho no dia, na direção
            seqd[x["dir"]] += 1
        seen_leg = {}
        for c in cands:
            key = (c["dir"], c["j"])
            leg = (c["dir"], c["k"])
            seen_leg[leg] = seen_leg.get(leg, 0) + 1
            x = trig.get(key)
            wall = c["c1"] is not None or c["c2"] is not None
            rows.append(dict(date=d, dir=int(c["dir"]), j=c["j"], k=c["k"], conf=c["conf"],
                             f2=fb[c["j"]]["time"], conf_t=fb[c["conf"]]["time"],
                             t_conf=fb[c["conf"] + 1]["time"] if c["conf"] + 1 < len(fb) else None,
                             t_opc=fb[x["idx"] + 1]["time"] if x is not None and x["idx"] + 1 < len(fb) else None,
                             piv=float(c["px2"]), wall=wall, day=c["day"] is not None,
                             super=wall and c["day"] is not None, ext_n=seen_leg[leg] - 1, levels=lv,
                             seq=seqk.get(key, 99),
                             wd_ratio=c["wd"] / max(c["thr"], 1e-9)))
    U = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    pickle.dump(U, open(cache, "wb"))
    return U


# ───────────────────────── simulador de 3 lotes ─────────────────────────

@nb.njit(cache=True)
def sim3(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, e, ep, d, sl, tp1, tp2_px, tp3_px, trail, be_lock,
         tmax12, tmax3, tick, nlots, be_mfe, be_mfe_lock, tp_thru=0.0, slip=1.0):
    """
    Até 3 lotes com stop comum inicial (ep − d·sl).
      lote 1: alvo ep + d·tp1; quando sai no alvo, os outros vão para ep + d·be_lock (se be_lock >= 0);
      lote 2: alvo no preço tp2_px (0 = sem alvo);
      lote 3: alvo tp3_px (0 = sem alvo); depois do alvo do lote 1, trailing de `trail` pts sobre o melhor preço.
    Lotes 1–2 saem no tempo após tmax12 barras; lote 3 após tmax3. Todos saem às 17:25.
    be_mfe > 0: BE da gestão atual (na abertura da barra, se o MFE já passou de be_mfe, stop → ep + d·be_mfe_lock).
    Retorna (pts brutos somados, minuto da última saída).
    """
    n5 = len(o5)
    stop = np.full(3, ep - d * sl)
    alive = np.zeros(3, np.bool_)
    for i in range(nlots):
        alive[i] = True
    res = np.zeros(3)
    tgt = np.array([ep + d * tp1, tp2_px, tp3_px])
    hit1 = False
    best = ep
    last_t = tm5[e]
    for k in range(e, n5):
        if k > e:
            if be_mfe > 0.0 and (best - ep) * d >= be_mfe:
                cand = ep + d * be_mfe_lock
                if (o5[k] - cand) * d > 0:
                    for i in range(3):
                        if (cand - stop[i]) * d > 0:
                            stop[i] = cand
            for i in range(3):
                if alive[i]:
                    lim = tmax3 if i == 2 else tmax12
                    if tm5[k] >= 1045 or k - e > lim:
                        res[i] = (o5[k] - ep) * d
                        alive[i] = False
                        last_t = tm5[k]
        if not (alive[0] or alive[1] or alive[2]):
            break
        if fb[k] == 0:
            nt = nn[k]
        else:
            nt = 4
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
            for i in range(3):
                if alive[i] and (p - stop[i]) * d <= 0:
                    res[i] = ((p if op else stop[i] - d * tick * slip) - ep) * d
                    alive[i] = False
                    last_t = tm5[k]
            for i in range(3):
                if alive[i] and tgt[i] != 0.0 and ((p - tgt[i]) * d >= tp_thru or (op and (p - tgt[i]) * d >= 0)):
                    res[i] = ((p if op else tgt[i]) - ep) * d
                    alive[i] = False
                    last_t = tm5[k]
                    if i == 0:
                        hit1 = True
                        if be_lock >= 0.0:
                            nb_ = ep + d * be_lock
                            for q in range(1, 3):
                                if (nb_ - stop[q]) * d > 0:
                                    stop[q] = nb_
            if (p - best) * d > 0:
                best = p
            if hit1 and trail > 0.0 and alive[2]:
                ts = best - d * trail
                if (ts - stop[2]) * d > 0:
                    stop[2] = ts
            if not (alive[0] or alive[1] or alive[2]):
                break
    for i in range(3):
        if alive[i]:
            res[i] = (c5[n5 - 1] - ep) * d
            last_t = tm5[n5 - 1]
    return res[0], res[1], res[2], last_t


@nb.njit(cache=True)
def sim_avg(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, e, ep, d, add, sl, tp, tp_add, tmax, tick):
    """
    Preço médio: 1 contrato na entrada; o 2º entra (limite) em ep − d·add se tocar. Stop comum em ep − d·sl.
    Alvo: ep + d·tp com 1 contrato; com 2 contratos, ambos saem no preço médio + d·tp_add.
    Retorna (pts brutos somados, minuto de saída, contratos usados).
    """
    n5 = len(o5)
    stop = ep - d * sl
    added = False
    lim_px = ep - d * add
    for k in range(e, n5):
        if k > e and (tm5[k] >= 1045 or k - e > tmax):
            p = o5[k]
            r = (p - ep) * d + ((p - lim_px) * d if added else 0.0)
            return r, tm5[k], 2 if added else 1
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
            if not added and (p - lim_px) * d <= 0:
                added = True
                lim_px = p if op else lim_px          # gap: limite preenchido na abertura (melhor)
            if (p - stop) * d <= 0:
                fill = p if op else stop - d * tick
                r = (fill - ep) * d + ((fill - lim_px) * d if added else 0.0)
                return r, tm5[k], 2 if added else 1
            tgt = (ep + lim_px) / 2.0 + d * tp_add if added else ep + d * tp
            if (p - tgt) * d >= 0:
                fill = p if op else tgt
                r = (fill - ep) * d + ((fill - lim_px) * d if added else 0.0)
                return r, tm5[k], 2 if added else 1
    p = c5[n5 - 1]
    return (p - ep) * d + ((p - lim_px) * d if added else 0.0), tm5[n5 - 1], 2 if added else 1


# ───────────────────────── execução das configurações ─────────────────────────

def entries(U, DS, mode):
    """Linhas com barra de entrada (e), preço (ep) e contexto NWE50 na entrada."""
    col = "t_conf" if mode == "CONF" else "t_opc"
    rows = []
    for r in U.itertuples():
        t = getattr(r, col)
        D = DS.get(r.date)
        if not isinstance(t, str) or D is None:
            continue
        tm = bt.hm(t)
        if tm not in D["pos"] or not (545 <= tm <= 990):      # 09:05–16:30
            continue
        e = D["pos"][tm]
        if e < 1:
            continue
        half = max(D["u50"][e] - D["c50"][e], TICK)
        ext50 = -r.dir * (D["c5"][e - 1] - D["c50"][e]) / half
        slope50 = r.dir * (D["c50"][e] - D["c50"][max(0, e - 6)]) / half
        rows.append(dict(r._asdict(), e=e, ep=float(D["o5"][e]), tm=tm, ext50=ext50, slope50=slope50))
    return pd.DataFrame(rows).drop(columns=["Index"])


def next_wall(levels, ep, d, min_dist):
    lv = [v for v in levels if (v - ep) * d >= min_dist]
    return (min(lv) if d == 1 else max(lv)) if lv else None


def run_cfg(T, DS, g):
    """Uma configuração sobre as entradas T. Retorna o DataFrame de trades (um por vez)."""
    out = []
    last = {}
    for r in T.sort_values(["date", "tm"]).itertuples():
        if r.tm <= last.get(r.date, -1):
            continue
        D = DS[r.dir][r.date] if 1 in DS else DS[r.date]   # {1: DS compra, -1: DS venda} = caminho adverso
        a = bt._args(D)
        ep = r.ep + r.dir * g.get("slip_in", 0.0)                                    # entrada pior em N pts
        r = r._replace(ep=ep)
        if g["kind"] == "AVG":
            pts, xt, n = sim_avg(*a, r.e, r.ep, r.dir, g["add"], g["sl"], g["tp"], g["tp_add"], g["tmax"], TICK)
            pnl = (pts - COST * n) * BRL
            ncon = n
        else:
            sl = g["sl"]
            if g.get("stop") == "piv":     # stop estrutural: além do extremo do F2 + 30, com teto
                sl = min(max(r.dir * (r.ep - (r.piv - r.dir * 30.0)), 2 * TICK), g["sl"])
            tp2 = 0.0
            if g["lot2"] == "wall":
                w = next_wall(r.levels, r.ep, r.dir, g["tp1"] + 2 * TICK)
                tp2 = (w - r.dir * 15.0) if w is not None else r.ep + r.dir * g["tp2_fix"]
            elif g["lot2"] != "none":
                tp2 = r.ep + r.dir * float(g["lot2"])
            tp3 = 0.0 if g["lot3"] in ("trail", "none") else r.ep + r.dir * float(g["lot3"])
            trail = g.get("trail", 0.0) if g["lot3"] == "trail" else 0.0
            a1, a2, a3, xt = sim3(*a, r.e, r.ep, r.dir, sl, g["tp1"], tp2, tp3, trail, g["be"], g["tmax"],
                                  g["tmax3"], TICK, g["lots"], g.get("be_mfe", 0.0), g.get("be_mfe_lock", 0.0),
                                  g.get("tp_thru", 0.0), g.get("slip", 1.0))
            lots = [(a1 - COST) * BRL, (a2 - COST) * BRL, (a3 - COST) * BRL][: g["lots"]]
            pnl = sum(lots)
            ncon = g["lots"]
        if g["kind"] == "AVG":
            lots = [pnl]
        last[r.date] = xt
        out.append((r.date, r.tm, xt, pnl, ncon, *(lots + [0.0] * (3 - len(lots))), r.super, r.seq, r.dir))
    return pd.DataFrame(out, columns=["date", "tm", "xt", "pnl", "ncon", "lote1", "lote2", "lote3", "super", "seq", "dir"])


def stats(R):
    if len(R) == 0:
        return dict(ops=0)
    R = R.sort_values(["date", "xt", "tm"])
    p = R.pnl.values

    def part(q):
        if len(q) == 0:
            return 0.0, 0.0, 0.0
        eq = np.cumsum(q)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
        return float(eq[-1]), dd, (float(eq[-1]) / dd if dd else 99.0)

    net, dd, rdd = part(p)
    isv = (R.date <= IS_END).values
    ni, di, ri = part(p[isv])
    no, do, ro = part(p[~isv])
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby(R.date.str[:7].values).sum()
    return dict(ops=len(p), wr=round(100 * (p > 0).mean(), 1), pf=round(g / l, 2) if l else 99.0, net=round(net),
                dd=round(dd), rdd=round(rdd, 2), rdd_is=round(ri, 2), rdd_oos=round(ro, 2), net_is=round(ni),
                net_oos=round(no), meses=f"{int((mon > 0).sum())}/{len(mon)}",
                ct_med=round(float(R.ncon.mean()), 2), media=round(float(p.mean()), 1))


FILTERS = {
    "todas": lambda T: T,
    "sem super": lambda T: T[~T.super],
    "10–16h": lambda T: T[(T.tm >= 600) & (T.tm < 960)],
    "sem super · 10–16h": lambda T: T[~T.super & (T.tm >= 600) & (T.tm < 960)],
    "regra atual": lambda T: T[~T.super & (T.seq <= 1) & (T.tm >= 600) & (T.tm < 960) & (T.ext50 > -0.5)
                               & (T.slope50 > -0.5)],
    "NWE50 a favor": lambda T: T[(T.ext50 > -0.5) & (T.slope50 > -0.5)],
}


def grid():
    G = []
    # referência: gestão atual do especialista (2c, SL 200, sem alvo, BE 180→20, 12 barras)
    G.append(dict(name="ATUAL 2c", kind="3L", lots=2, sl=200.0, tp1=1e9, lot2="none", lot3="none", be=-1.0,
                  tmax=12, tmax3=12, be_mfe=180.0, be_mfe_lock=20.0))
    # (A) 3 lotes: stop curto, lote 1 rápido + zero, lote 2 na próxima Wall, lote 3 conduzido
    for stop, sl, tp1, be, lot3, trail in itertools.product(("fixo", "piv"), (100.0, 150.0, 200.0), (60.0, 100.0, 150.0),
                                                            (0.0, 20.0), ("trail", "600"), (150.0, 250.0)):
        if lot3 != "trail" and trail != 150.0:
            continue
        G.append(dict(name=f"3L {stop} SL{sl:.0f} T1 {tp1:.0f} BE+{be:.0f} L2 wall L3 {lot3}{'' if lot3 != 'trail' else f' {trail:.0f}'}",
                      kind="3L", lots=3, stop=stop, sl=sl, tp1=tp1, lot2="wall", tp2_fix=300.0, lot3=lot3,
                      trail=trail, be=be, tmax=24, tmax3=200))
    # (B) preço médio
    for add, sl, tp, tp_add in itertools.product((80.0, 120.0, 160.0), (200.0, 250.0, 300.0), (80.0, 150.0), (40.0, 80.0)):
        if add >= sl:
            continue
        G.append(dict(name=f"PM add{add:.0f} SL{sl:.0f} TP{tp:.0f} TPm{tp_add:.0f}", kind="AVG", add=add, sl=sl,
                      tp=tp, tp_add=tp_add, tmax=24))
    return G


def main():
    os.makedirs(OUT, exist_ok=True)
    U = universe()
    DS = bt.market("WIN")
    print(f"universo: {len(U)} divergências · {U.groupby(['date', 'dir', 'k']).ngroups} pernas · {U.date.nunique()} pregões")
    rows = []
    G = grid()
    for mode in ("CONF", "OPC"):
        T = entries(U, DS, mode)
        print(f"{mode}: {len(T)} entradas possíveis", flush=True)
        for fname, ff in FILTERS.items():
            Tf = ff(T)
            for g in G:
                st = stats(run_cfg(Tf, DS, g))
                rows.append(dict(entrada=mode, filtro=fname, gestao=g["name"], tipo=g["kind"], **st))
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "grade.csv"), index=False)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "grade.csv"), index=False)
    pd.set_option("display.width", 250)
    cols = ["entrada", "filtro", "gestao", "ops", "wr", "pf", "net", "dd", "rdd", "rdd_is", "rdd_oos", "meses", "ct_med"]
    print("\nreferência (gestão atual):")
    print(R[R.gestao == "ATUAL 2c"][cols].to_string(index=False))
    print("\ntop 25 por Ret/DD jan–jul (com ≥ 300 trades):")
    print(R[R.ops >= 300].sort_values("rdd_is", ascending=False).head(25)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
