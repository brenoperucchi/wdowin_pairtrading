# -*- coding: utf-8 -*-
"""
Validação independente do setup WDO "V1a" (achado trazido pelo usuário em 12/11/2026), reescrito do zero a partir
da descrição — sem usar o script que o encontrou.

Regra descrita:
  motor engine_v32 (f1 flow, sem reset, repetição, sem used, COM módulo de abertura), PARAMS["WDO"], elig "common",
  níveis = só Walls; entrada a mercado na abertura da barra conf+1, 09:00–17:00 sem a hora 11;
  F2 a ≤ 3,5 pts da Wall mais próxima; ext30 > 0 (fechamento anterior do lado da reversão em relação ao centro da
  NWE30, normalizado por meia banda); saída: SL 14, TP = min(max(dist. até a próxima Wall − 0,5, 4), 22) (aborta se
  < 2,5), 24 barras, sem BE, 17:25; um trade por vez; 1 contrato, custo 0,5 pt, stop 1 tick pior.
Números informados: ProxWall 184 tr · PF 1,72 · R$ 4.498 · DD 590 · Ret/DD 7,62 · 11/11 · TP12 190 tr · R$ 3.985 · 6,87.

Testes:
  1. reprodução;
  2. placebo de Walls (os mesmos níveis deslocados 25–75% do espaçamento, 10 sorteios) — âncora E alvo;
  3. posição na grade (quantas vizinhas chegam lá) e walk-forward (escolhe em jan–jul, mede ago–nov);
  4. dependências: sem módulo de abertura (motor de produção), sem ext30, sem a regra das 11h, Wall+MidWall.
Uso: python research/div_master/wdo_v1a/validar.py
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "research", "div_master", "especialistas"), os.path.join(ROOT, "research", "div_master", "wdo_ima")]
import numpy as np
import pandas as pd
import modulo as M, bt
from research.div_wall.data import load_asset
from teste import placebo

OUT = os.path.join(HERE, "results")
IS_END = "2026-07-31"
X = bt.X["WDO"]
OPT_V1A = dict(f1="flow", reset=False, rep=True, used=False, open_module=True)


def candidates(data, DS, lv_kind="wall", opt=OPT_V1A, shift=None, zone=None, pierce=None):
    """Lista de divergências com entrada CONF e contexto. shift = {data: níveis placebo}."""
    P = dict(M.PARAMS["WDO"])
    if zone is not None:
        P["zone"], P["pierce_max"] = zone, pierce
    rows = []
    for d in sorted(data):
        if d > bt.END or d not in DS:
            continue
        bars, walls, _ = data[d]
        types = ("Wall",) if lv_kind == "wall" else ("Wall", "MidWall")
        lv = sorted(float(w["price"]) for w in walls if w.get("type") in types)
        if shift is not None:
            lv = shift.get(d, lv)
        if not lv:
            continue
        fb = M.compute_flow([dict(b) for b in bars], "WDO")
        cs = M.engine_v32(fb, lv, P, "common", atr=M.atr_series(fb, P["tick"]), opt=opt)
        D = DS[d]
        for c in cs:
            if c["conf"] + 1 >= len(fb):
                continue
            t_in = fb[c["conf"] + 1]["time"]
            tm = bt.hm(t_in)
            if tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            dd = int(c["dir"])
            c30 = (D["u30"][e] + D["l30"][e]) / 2.0          # centro da NWE30 da barra anterior (causal)
            half30 = max((D["u30"][e] - D["l30"][e]) / 2.0, X["tick"])
            rows.append(dict(date=d, dir=dd, tm=tm, e=e, ep=float(D["o5"][e]), piv=float(c["px2"]),
                             d_wall=min(abs(c["px2"] - w) for w in lv), levels=lv,
                             ext30=-dd * (D["c5"][e - 1] - c30) / half30))
    return pd.DataFrame(rows)


def run(T, DS, sl=14.0, tp_mode="wall", tp_fix=12.0, tp_min=4.0, tp_max=22.0, tmax=24, zone_max=3.5, ext_min=0.0,
        skip11=True, livre=False, cost=None, slip=1.0, inv=False, tp_thru=0.0, skip_close=False):
    cost = X["cost"] if cost is None else cost
    if len(T) == 0:
        return []
    m = (T.d_wall <= zone_max) & (T.ext30 > ext_min) & (T.tm >= 540) & (T.tm <= 1020)
    if skip11:
        m &= (T.tm // 60) != 11
    rows, last = [], {}
    for r in T[m].sort_values(["date", "tm"]).itertuples():
        if not livre and r.tm <= last.get(r.date, -1):
            continue
        d = -r.dir if inv else r.dir
        if tp_mode == "wall":
            nxt = [w for w in r.levels if (w - r.ep) * d > 0]
            if skip_close:                                   # leitura que bate o informado: ignora Walls a < 3 pts
                nxt = [w for w in nxt if d * (w - r.ep) - 0.5 >= 2.5]
            if not nxt:
                continue
            nw = (min(nxt) if d == 1 else max(nxt))
            nw_d = d * (nw - r.ep) - 0.5
            if nw_d < 2.5:
                continue
            tp = min(max(nw_d, tp_min), tp_max)
        else:
            tp = tp_fix
        D = DS[r.date]
        # tp_thru: o alvo (limite) só é executado se o preço negociar tp_thru além dele; o ganho fica no alvo
        pts, xt = bt.sim(*bt._args(D), D["u30"], int(r.e), r.ep, d, sl, r.ep + d * (tp + tp_thru), False, 0.0, 0.0,
                         0.0, 0.0, 0.0, tmax, X["tick"] * slip)
        if tp_thru and pts >= tp + tp_thru - 1e-9:
            pts = tp
        last[r.date] = xt
        rows.append((r.date, r.tm, int(xt), (pts - cost) * X["brl"], d))
    return rows


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0.0, net=0, dd=0, rdd=0.0, rdd_is=0.0, rdd_oos=0.0, meses="0/0", net_is=0, net_oos=0)
    R = pd.DataFrame(rows, columns=["date", "tm", "xt", "brl", "dir"]).sort_values(["date", "xt", "tm"])
    p = R.brl.values

    def part(q):
        if len(q) == 0:
            return 0.0, 0.0, 0.0
        eq = np.cumsum(q)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
        return float(eq[-1]), dd, (float(eq[-1]) / dd if dd else 99.0)

    net, dd, r = part(p)
    isv = (R.date <= IS_END).values
    ni, _, ri = part(p[isv])
    no, _, ro = part(p[~isv])
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby(R.date.str[:7].values).sum()
    return dict(ops=len(p), wr=round(100 * (p > 0).mean(), 1), pf=round(g / l, 2) if l else 99.0, net=round(net),
                dd=round(dd), rdd=round(r, 2), rdd_is=round(ri, 2), rdd_oos=round(ro, 2), net_is=round(ni),
                net_oos=round(no), meses=f"{int((mon > 0).sum())}/{len(mon)}",
                compras=int((R.dir == 1).sum()), vendas=int((R.dir == -1).sum()))


def line(lbl, s):
    print(f"   {lbl:44s} {s['ops']:4d} tr · PF {s['pf']:4.2f} · R$ {s['net']:6d} · DD {s['dd']:5d} · Ret/DD {s['rdd']:5.2f} "
          f"(jan–jul {s['rdd_is']:5.2f} · ago–nov {s['rdd_oos']:5.2f}) · {s['meses']}", flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    data = load_asset("WDO", "M5")
    DS = bt.market("WDO")
    T = candidates(data, DS)
    print(f"divergências v3.2 (com abertura) ancoradas, com entrada CONF: {len(T)} · pregões {T.date.nunique()}")

    print("\n1) REPRODUÇÃO")
    base = stats(run(T, DS))
    line("V1a ProxWall (informado 184 · 4.498 · 7,62)", base)
    line("V1a TP fixo 12 (informado 190 · 3.985 · 6,87)", stats(run(T, DS, tp_mode="fix")))

    print("\n2) PLACEBO DE WALLS (mesmos níveis deslocados; âncora e alvo usam o placebo)")
    real_lv = {d: sorted(float(w["price"]) for w in v[1] if w.get("type") == "Wall") for d, v in data.items()}
    pl = []
    for s in range(10):
        sh = {d: placebo(lv, np.random.default_rng(1000 * s + i)) for i, (d, lv) in enumerate(sorted(real_lv.items()))}
        st = stats(run(candidates(data, DS, shift=sh), DS))
        pl.append(st)
        line(f"placebo {s}", st)
    print(f"   → Ret/DD placebo: mediana {np.median([x['rdd'] for x in pl]):.2f} · máx {max(x['rdd'] for x in pl):.2f} "
          f"· real {base['rdd']:.2f}")

    print("\n3) DEPENDÊNCIAS")
    line("motor de produção (sem módulo de abertura)",
         stats(run(candidates(data, DS, opt=dict(OPT_V1A, open_module=False)), DS)))
    line("sem filtro ext30", stats(run(T, DS, ext_min=-1e9)))
    line("sem pular as 11h", stats(run(T, DS, skip11=False)))
    line("Wall + MidWall", stats(run(candidates(data, DS, lv_kind="all"), DS)))
    line("LIVRE (sem um por vez)", stats(run(T, DS, livre=True)))
    line("direção invertida", stats(run(T, DS, inv=True)))
    line("custo 2× + stop 2 ticks + entrada 1 tick pior",
         stats(run(T.assign(ep=T.ep + T.dir * 0.5), DS, cost=1.0, slip=2.0)))

    print("\n4) GRADE (SL × TPmáx × zona × ext30 × tempo) — onde o V1a fica e walk-forward")
    rows = []
    for sl, tpmax, zmax, ext, tmax in itertools.product((8.0, 10.0, 12.0, 14.0, 16.0, 18.0), (12.0, 16.0, 22.0, 30.0),
                                                        (2.0, 3.5, 5.0), (-1e9, -0.2, 0.0, 0.2), (12, 24)):
        st = stats(run(T, DS, sl=sl, tp_max=tpmax, zone_max=zmax, ext_min=ext, tmax=tmax))
        rows.append(dict(sl=sl, tpmax=tpmax, zona=zmax, ext30=ext, tmax=tmax, **st))
    G = pd.DataFrame(rows)
    G.to_csv(os.path.join(OUT, "grade.csv"), index=False)
    G = G[G.ops >= 100]
    print(f"   {len(G)} combinações com ≥ 100 trades · Ret/DD mediano {G.rdd.median():.2f} · "
          f"≥ 7 em {int((G.rdd >= 7).sum())} · PF>1 nas duas metades em {int(((G.net_is > 0) & (G.net_oos > 0)).sum())}")
    print(f"   percentil do V1a (Ret/DD {base['rdd']}): {100 * (G.rdd < base['rdd']).mean():.0f}%")
    w = G.sort_values("rdd_is", ascending=False).iloc[0]
    print(f"   walk-forward: melhor em jan–jul = SL {w.sl} TPmáx {w.tpmax} zona {w.zona} ext30 {w.ext30} {w.tmax}b → "
          f"jan–jul Ret/DD {w.rdd_is} · ago–nov Ret/DD {w.rdd_oos} (R$ {w.net_oos})")
    top = G.sort_values("rdd_is", ascending=False).head(20)
    print(f"   top 20 de jan–jul em ago–nov: Ret/DD mediano {top.rdd_oos.median():.2f} · positivas {int((top.net_oos > 0).sum())}/20")
    print(f"   grade inteira em ago–nov: Ret/DD mediano {G.rdd_oos.median():.2f} · positivas {int((G.net_oos > 0).sum())}/{len(G)}")


if __name__ == "__main__":
    main()
