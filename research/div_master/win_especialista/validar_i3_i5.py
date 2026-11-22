# -*- coding: utf-8 -*-
"""
Validação independente da proposta "I3 / I5" (WIN, complementares ao especialista) — código próprio, sem importar
os scripts da proposta (só o motor de pesquisa `modulo` e o simulador `bt`).

I3: V32_PROD · gatilho Opção C (todos, 1 por candidato) · entrada 09:05–10:55 · ext50 > 0 · SL 250 TP 250 · 24 barras
I5: v3.2 COM módulo de abertura · entrada CONF · F2 a ≤ 150 da Wall mais próxima · entrada até 12:00 ·
    passivo institucional (j..conf) a favor > 0 · SL 200 TP 300 · 24 barras
Um trade por vez, 1 contrato, custo 10 pts, stop 1 tick pior, saída 17:25.

Testes: reprodução · placebo de Walls (níveis deslocados) · inversão · fila no alvo (+1 tick) · posição na grade de
vizinhos e walk-forward (escolhe em jan–jul, mede ago–nov) · sobreposição com o especialista de PRODUÇÃO
(core/especialista_v22.run, 252 trades) · carteira com o especialista real (2c) e o V1a TP12 (1c).
Uso: python research/div_master/win_especialista/validar_i3_i5.py
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "wdo_ima"), os.path.join(DM, "wdo_v1a"),
                os.path.join(DM, "carteira_v22")]
import numpy as np
import pandas as pd
import modulo as M, bt
from research.div_wall.data import load_asset
from teste import placebo
from core import especialista_v22 as E
from paridade_especialista import day_inputs

IS_END = "2026-07-31"
XW = bt.X["WIN"]
OPEN = dict(f1="flow", reset=False, rep=True, used=False, open_module=True)


def universe(data, DS, opt, shift=None):
    """Todas as divergências do dia com as duas entradas possíveis (CONF e 1º gatilho Opção C) e o contexto."""
    P = M.PARAMS["WIN"]
    rows = []
    for d in sorted(data):
        if d > bt.END or d not in DS:
            continue
        bars, walls, _ = data[d]
        lv_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        lv_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
        if shift is not None:
            lv_all, lv_wall = shift[d]
        fb = M.compute_flow([dict(b) for b in bars], "WIN")
        cs = M.engine_v32(fb, lv_all, P, "common", atr=M.atr_series(fb, P["tick"]), opt=opt)
        trig, _ = M.triggers(fb, cs, P)
        first = {}
        for x in trig:
            first.setdefault((x["dir"], x["j"]), x)
        D = DS[d]
        for c in cs:
            dr = int(c["dir"])
            for mode, sig in (("CONF", c["conf"]), ("OPC", first[(dr, c["j"])]["idx"] if (dr, c["j"]) in first else None)):
                if sig is None or sig + 1 >= len(fb):
                    continue
                tm = bt.hm(fb[sig + 1]["time"])
                if tm not in D["pos"] or not (545 <= tm <= 1005):
                    continue
                e = D["pos"][tm]
                if e < 1:
                    continue
                half50 = max(D["u50"][e] - D["c50"][e], XW["tick"])
                rows.append(dict(date=d, mode=mode, dir=dr, tm=tm, e=e, ep=float(D["o5"][e]),
                                 ext50=-dr * (D["c5"][e - 1] - D["c50"][e]) / half50,
                                 d_wall=min((abs(c["px2"] - w) for w in lv_wall), default=1e9),
                                 pass_=dr * sum(float(fb[x].get("inst_pass_delta", 0.0)) for x in range(c["j"], sig + 1))))
    return pd.DataFrame(rows)


def run(T, DS, sl, tp, tmax=24, tp_thru=0.0, inv=False):
    rows, last = [], {}
    for r in T.sort_values(["date", "tm"]).itertuples():
        if r.tm <= last.get(r.date, -1):
            continue
        D = DS[r.date]
        d = -r.dir if inv else r.dir
        pts, xt = bt.sim(*bt._args(D), D["u30"], int(r.e), r.ep, d, sl, r.ep + d * (tp + tp_thru), False, 0.0, 0.0, 0.0,
                         0.0, 0.0, tmax, XW["tick"])
        if tp_thru and pts >= tp + tp_thru - 1e-9:
            pts = tp
        last[r.date] = xt
        rows.append((r.date, r.tm, int(xt), (pts - XW["cost"]) * XW["brl"], d))
    return pd.DataFrame(rows, columns=["date", "tm", "xt", "brl", "dir"])


def stats(R, col="brl"):
    if len(R) == 0:
        return dict(ops=0, pf=0.0, net=0, dd=0, rdd=0.0, rdd_is=0.0, rdd_oos=0.0, meses="0/0", net_is=0, net_oos=0)
    R = R.sort_values(["date", "xt", "tm"])
    p = R[col].values

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
                net_oos=round(no), meses=f"{int((mon > 0).sum())}/{len(mon)}")


def line(lbl, s):
    print(f"   {lbl:46s} {s['ops']:4d} tr · PF {s['pf']:4.2f} · R$ {s['net']:6d} · DD {s['dd']:5d} · Ret/DD {s['rdd']:5.2f} "
          f"(jan–jul {s['rdd_is']:5.2f} · ago–nov {s['rdd_oos']:5.2f}) · {s['meses']}", flush=True)


def sel_i3(U, tm_end=660, ext=0.0):
    return U[(U["mode"] == "OPC") & (U.tm < tm_end) & (U.ext50 > ext)]


def sel_i5(U, tm_end=720, dz=150.0, pmin=0.0):
    return U[(U["mode"] == "CONF") & (U.tm <= tm_end) & (U.d_wall <= dz) & (U.pass_ > pmin)]


def main():
    data = load_asset("WIN", "M5")
    DS = bt.market("WIN")
    U_prod = universe(data, DS, M.V32_PROD)
    U_open = universe(data, DS, OPEN)

    print("1) REPRODUÇÃO (informado: I3 116 tr · R$ 1.528 · DD 217 · 7,04 | I5 119 tr · R$ 1.246 · DD 228 · 5,46)")
    I3 = run(sel_i3(U_prod), DS, 250, 250)
    I5 = run(sel_i5(U_open), DS, 200, 300)
    s3, s5 = stats(I3), stats(I5)
    line("I3", s3)
    line("I5", s5)

    print("\n2) PLACEBO DE WALLS (10 sorteios; âncora e d_wall usam o placebo) · INVERSÃO · FILA NO ALVO")
    for name, U, fsel, sl, tp in (("I3", None, sel_i3, 250, 250), ("I5", None, sel_i5, 200, 300)):
        opt = M.V32_PROD if name == "I3" else OPEN
        pr = []
        for s in range(10):
            sh = {}
            for i, d in enumerate(sorted(data)):
                walls = data[d][1]
                la = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
                rng = np.random.default_rng(1000 * s + i)
                pa = placebo(la, rng)
                off = (pa[0] - la[0]) if la else 0.0
                sh[d] = (pa, sorted(float(w["price"]) + off for w in walls if w.get("type") == "Wall"))
            pr.append(stats(run(fsel(universe(data, DS, opt, shift=sh)), DS, sl, tp))["rdd"])
        base = s3 if name == "I3" else s5
        Ub = U_prod if name == "I3" else U_open
        print(f"   {name}: placebo Ret/DD mediana {np.median(pr):.2f} · máx {max(pr):.2f} · real {base['rdd']:.2f}")
        line(f"{name} invertido", stats(run(fsel(Ub), DS, sl, tp, inv=True)))
        line(f"{name} alvo só passando 1 tick", stats(run(fsel(Ub), DS, sl, tp, tp_thru=5.0)))

    print("\n3) VIZINHOS E WALK-FORWARD")
    for name in ("I3", "I5"):
        rows = []
        if name == "I3":
            grid = itertools.product((150, 200, 250, 300), (150, 200, 250, 300, 350), (600, 630, 660, 720), (-0.5, 0.0, 0.3))
            for sl, tp, te, ex in grid:
                rows.append(dict(sl=sl, tp=tp, janela=te, filtro=ex, **stats(run(sel_i3(U_prod, te, ex), DS, sl, tp))))
        else:
            grid = itertools.product((150, 200, 250, 300), (150, 200, 250, 300, 350), (660, 720, 780), (100.0, 150.0, 200.0))
            for sl, tp, te, dz in grid:
                rows.append(dict(sl=sl, tp=tp, janela=te, filtro=dz, **stats(run(sel_i5(U_open, te, dz), DS, sl, tp))))
        G = pd.DataFrame(rows)
        G.to_csv(os.path.join(HERE, f"validar_{name}_grade.csv"), index=False)
        G = G[G.ops >= 80]
        base = s3 if name == "I3" else s5
        top = G.sort_values("rdd_is", ascending=False).head(10)
        print(f"   {name}: {len(G)} vizinhos · Ret/DD mediano {G.rdd.median():.2f} · positivos {int((G.net > 0).sum())} · "
              f"percentil do escolhido {100 * (G.rdd < base['rdd']).mean():.0f}% · top 10 de jan–jul em ago–nov: "
              f"Ret/DD mediano {top.rdd_oos.median():.2f}, positivos {int((top.net_oos > 0).sum())}/10")

    print("\n4) ESPECIALISTA DE PRODUÇÃO (core) · SOBREPOSIÇÃO · CARTEIRA")
    DSm = DS
    esp = []
    for d in sorted(data):
        if d > bt.END or d not in DSm:
            continue
        fb, walls, ex = day_inputs(DSm, data, d)
        esp += [(d, E._hm(t["time"]), E._hm(t["exit_time"]), t["brl_1c"], t["dir_num"]) for t in E.run(fb, walls, ex)]
    ES = pd.DataFrame(esp, columns=["date", "tm", "xt", "brl", "dir"])          # brl_1c já é dos 2 contratos
    line("especialista de produção (2c)", stats(ES))
    for name, R in (("I3", I3), ("I5", I5)):
        k = set(zip(ES.date, ES.dir))
        same_day_dir = sum((dd, dr) in k for dd, dr in zip(R.date, R.dir))
        near = 0
        esd = ES.groupby("date")
        for r in R.itertuples():
            if r.date in esd.groups:
                g = esd.get_group(r.date)
                near += int(((g.dir == r.dir) & ((g.tm - r.tm).abs() <= 30)).any())
        idx = pd.Index(sorted(set(ES.date) | set(R.date)))
        corr = ES.groupby("date").brl.sum().reindex(idx, fill_value=0).corr(R.groupby("date").brl.sum().reindex(idx, fill_value=0))
        print(f"   {name}: correlação diária com o especialista {corr:+.3f} · mesmo dia e direção {same_day_dir}/{len(R)} · "
              f"mesma direção a ≤ 30 min de um trade do especialista {near}/{len(R)}")

    import validar as V1
    dw = load_asset("WDO", "M5")
    DSw = bt.market("WDO")
    V1a = pd.DataFrame(V1.run(V1.candidates(dw, DSw), DSw, tp_mode="fix"), columns=["date", "tm", "xt", "brl", "dir"])
    for lbl, parts in (("especialista (2c)", [ES]), ("especialista + V1a TP12", [ES, V1a]),
                       ("especialista + I3 + V1a", [ES, I3, V1a]), ("especialista + I5 + V1a", [ES, I5, V1a]),
                       ("especialista + I3", [ES, I3]), ("especialista + I5", [ES, I5])):
        line(lbl, stats(pd.concat(parts, ignore_index=True)))


if __name__ == "__main__":
    main()
