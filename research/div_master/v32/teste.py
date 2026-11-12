# -*- coding: utf-8 -*-
"""
Motor v3.2 = v3.1 com F1 no fluxo mais extremo da perna e sem reset (marcações do usuário em WIN 05/11, 12/11/2026).
Mede, por variante: as 3 marcações de 05/11, a cobertura dos rótulos (9 pregões), sinais por dia, e as estratégias
(Sniper na janela atual, especialista congelado, carteira) — mesma bancada do v22/teste.py.
Uso: python research/div_master/v32/teste.py → research/div_master/v32/results/
"""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "frente1"), os.path.join(DM, "engine_v2_1")]
import numpy as np, pandas as pd
import modulo as M, bt, robust as R
import motores as F1
import evaluate as EV
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
IS_END = "2026-07-31"
BASE32 = dict(f1="flow", reset=False, rep=True, used=False, open_module=True)
VARIANTS = {
    "v2.2 (produção)": ("v2.2", None),
    "v3.1 (referência)": ("v3.1", None),
    "v3.2 F1 fluxo da barra": ("v3.2", {}),
    "v3.2 F1 fluxo k±1": ("v3.2", dict(f1="flow_k1")),
    "v3.2 sem módulo de abertura": ("v3.2", dict(open_module=False)),
    "v3.2 com reset": ("v3.2", dict(reset=True)),
}
# marcações do usuário em WIN 05/11: (direção, F1, F2)
MARKS = [(-1, "09:00", "11:25"), (1, "09:15", "09:40"), (1, "12:15", "14:00")]


def setv(engine, opt):
    M.V22 = dict(M.V22, **M.V22_ABERTURA)
    M.V32 = dict(BASE32, **(opt or {}))


def engine_fn(engine):
    P = M.PARAMS["WIN"]
    if engine == "v2.2":
        return lambda fb, lv: M.engine_v22(fb, lv, P, "common", opt=M.V22_ABERTURA)
    if engine == "v3.1":
        return lambda fb, lv: M.engine_v31(fb, lv, P, "common")
    return lambda fb, lv: M.engine_v32(fb, lv, P, "common")


def consolidate(cands):
    """Para exibição: das extensões do mesmo F1 (mesma direção), fica só a última."""
    keep = {}
    for c in cands:
        keep[(c["dir"], c["k"])] = c
    return sorted(keep.values(), key=lambda c: c["conf"])


def tmin(t):
    return int(t[:2]) * 60 + int(t[3:5])


def marks_hit(engine):
    bars, walls, _ = load_asset("WIN", "M5")["2026-11-05"]
    fb = M.compute_flow([dict(b) for b in bars], "WIN")
    lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    cs = consolidate(engine_fn(engine)(fb, lv)) if engine == "v3.2" else engine_fn(engine)(fb, lv)
    hit = 0
    shown = []
    for d, f1, f2 in MARKS:
        ok = any(c["dir"] == d and abs(tmin(fb[c["j"]]["time"]) - tmin(f2)) <= 10 and abs(tmin(fb[c["k"]]["time"]) - tmin(f1)) <= 15 for c in cs)
        hit += ok
    shown = [f"{'▲' if c['dir'] == 1 else '▼'}{fb[c['k']]['time']}→{fb[c['j']]['time']}" for c in cs]
    return hit, len(cs), shown


def labels(engine, consolidated):
    days = EV.load_days()
    pre, manual, raw = EV.load_labels()
    gts = EV.ground_truth(days, pre, manual)
    fal = EV.falses(days, pre)
    labeled = sorted({r["date"] for r in raw})
    dets = {}
    for d, day in days.items():
        fb = [dict(b, wave=w) for b, w in zip(day["bars"], day["wave"])]
        lv = sorted(float(w["price"]) for w in day["walls"] if w.get("type") in M.LEVEL_TYPES)
        cs = engine_fn(engine)(fb, lv)
        if consolidated:
            cs = consolidate(cs)
        dets[d] = [dict(dir=c["dir"], f2_idx=c["j"], f1_idx=c["k"], sig_idx=c["conf"]) for c in cs]
    ev = EV.eval_dets(dets, gts, dates=labeled, falses_list=fal)
    hold = EV.eval_dets(dets, gts, dates=EV.HOLD, falses_list=fal)
    n = sum(len(dets[d]) for d in labeled) / len(labeled)
    return round(100 * ev["rec"], 1), round(100 * ev["prec"], 1), round(100 * hold["rec"], 1), round(n, 1)


def strategies(engine, DSS, pool):
    S = bt.simulate("WIN", bt.signals("WIN", engine), DSS["WIN"], exits=())
    T = R.run_exit(S, DSS["WIN"])
    m = T.ok & ~T.super & (T.seq <= 1) & (T.tm >= 600) & (T.tm < 960) & (T.ext50 > -0.5) & (T.slope50 > -0.5)
    q = bt.mgmt(T[m & T[R.COL].notna()].sort_values(["date", "tm"]), R.COL, R.XT, "UM_POR_VEZ")
    esp = [(r.date, r.time_in, f"{int(r.xt_X) // 60:02d}:{int(r.xt_X) % 60:02d}", 2.0 * float(r.pnl_X)) for r in q.itertuples()]
    trs = []
    for a in ("WIN", "WDO"):
        trs += F1.sniper_filter(pool[a], F1.engine_map(a, engine, "conf", False), ("tol", 2), a)
    snp = F1.rows_sniper(trs)
    out = {}
    for lab, rr in (("esp", esp), ("snp", snp), ("cart", esp + snp)):
        per = F1.by_period(rr)
        c = per["completo"]
        out[lab] = dict(ops=c["ops"], pf=c["pf"], net=c["net"], dd=c["dd"], rdd=c["rdd"], meses=c["meses"],
                        rdd_jan_jul=F1.stats_brl([x for x in rr if x[0] <= IS_END])["rdd"],
                        pf_partes="/".join(f"{per[p]['pf']:.2f}" for p in ("jan–abr", "mai–jul", "ago–nov")))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    DSS = {a: bt.market(a) for a in ("WIN", "WDO")}
    pool, _ = F1.sniper_pool()
    rows = []
    for name, (eng, opt) in VARIANTS.items():
        setv(eng, opt)
        h, n05, shown = marks_hit(eng)
        cov, prec, hold, per_day = labels(eng, False)
        covc, precc, holdc, per_dayc = labels(eng, True) if eng == "v3.2" else (cov, prec, hold, per_day)
        st = strategies(eng, DSS, pool)
        r = dict(variante=name, marcas_0511=f"{h}/3", linhas_0511=n05, cob=cov, prec=prec, cob_holdout=hold, sinais_dia=per_day,
                 cob_consol=covc, prec_consol=precc, sinais_dia_consol=per_dayc,
                 **{f"{k}_{m}": v for k, d in st.items() for m, v in d.items()})
        rows.append(r)
        print(name, "| 05/11:", " ".join(shown), flush=True)
        print("   ", {k: r[k] for k in ("marcas_0511", "cob", "prec", "cob_consol", "prec_consol", "sinais_dia_consol",
                                       "esp_rdd", "snp_rdd", "cart_rdd", "cart_rdd_jan_jul", "cart_net", "cart_dd",
                                       "esp_pf_partes", "snp_pf_partes")}, flush=True)
    Rdf = pd.DataFrame(rows)
    Rdf.to_csv(os.path.join(OUT, "variantes.csv"), index=False)
    pd.set_option("display.width", 300)
    print("\n" + Rdf.T.to_string())


if __name__ == "__main__":
    main()
