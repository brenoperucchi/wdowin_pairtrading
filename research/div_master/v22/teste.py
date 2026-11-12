# -*- coding: utf-8 -*-
"""
Motor v2.2 = v2.1 + módulo de abertura (pedido de 12/11/2026: mais divergências às 9h sem perder o que o v2.1 tem).

1. Equivalência: v2.2 sem módulo == v2.1 (todos os pregões, WIN e WDO, e os 16 pregões do rotulador).
2. Causalidade: paridade lote × barra a barra de cada variante (amostra de pregões).
3. Por variante: cobertura dos rótulos (geral e só abertura), volume às 9h, retorno à frente dos sinais da abertura
   (entrada na abertura seguinte ao gatilho Opção C) contra o placebo de barras das 9h, especialista (com e sem 9h),
   Sniper (mesma configuração escolhida para o v2.1) e carteira unificada.
Uso: python research/div_master/v22/teste.py → research/div_master/v22/results/
"""
import json, os, random, sys, warnings
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
H1, IS_END = "2026-04-30", "2026-07-31"
VARIANTS = {
    "v2.1 (referência)": {},
    "A  semente 09:00": dict(seed=True),
    "B8 ZigZag 0,8 na abertura": dict(zz_open=0.8),
    "B6 ZigZag 0,6 na abertura": dict(zz_open=0.6),
    "C  pivô 3 barras + candle": dict(lr_open=True),
    "A+B8": dict(seed=True, zz_open=0.8),
    "A+C": dict(seed=True, lr_open=True),
    "A+B8+C": dict(seed=True, zz_open=0.8, lr_open=True),
    "A+B8 até 10:00": dict(seed=True, zz_open=0.8, open_end="10:00"),
}
OPEN_CUT = "10:00"


def set_variant(opt):
    M.V22 = dict(seed=False, zz_open=None, lr_open=False, open_end="09:35", seed_end="09:20")
    M.V22.update(opt)


def key(c):
    return (c["dir"], c["j"], c["k"], c["conf"])


# ───────────────────────── 1 e 2 ─────────────────────────

def equivalence():
    set_variant({})
    bad, tot = 0, 0
    for a in ("WIN", "WDO"):
        P = M.PARAMS[a]
        for d, (bars, walls, _) in load_asset(a, "M5").items():
            fb = M.compute_flow([dict(b) for b in bars], a)
            lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
            for elig in ("common", "all"):
                x = sorted(key(c) for c in M.engine_v21(fb, lv, P, elig))
                y = sorted(key(c) for c in M.engine_v22(fb, lv, P, elig))
                tot += len(x)
                bad += x != y
    days = EV.load_days()
    for d, day in days.items():
        fb = [dict(b, wave=w) for b, w in zip(day["bars"], day["wave"])]
        lv = sorted(float(w["price"]) for w in day["walls"] if w.get("type") in M.LEVEL_TYPES)
        x = sorted(key(c) for c in M.engine_v21(fb, lv, M.PARAMS["WIN"], "native_v21"))
        y = sorted(key(c) for c in M.engine_v22(fb, lv, M.PARAMS["WIN"], "native_v21"))
        bad += x != y
    return bad, tot


def parity(opt, n_days=30):
    set_variant(opt)
    errs = 0
    for a in ("WIN", "WDO"):
        data = load_asset(a, "M5")
        days = sorted(data)
        random.Random(11).shuffle(days)
        for d in days[:n_days]:
            bars, walls, _ = data[d]
            _, B = M.run_day(a, bars, walls, engines=("v2.2",))
            for t in range(len(bars)):
                _, L = M.run_day(a, bars[: t + 1], walls, engines=("v2.2",))
                exp = sorted(key(c) for c in B["v2.2"]["cands"] if c["conf"] <= t)
                got = sorted(key(c) for c in L["v2.2"]["cands"])
                et = sorted((x["dir"], x["j"], x["idx"], x["esp"]) for x in B["v2.2"]["trig"] if x["idx"] <= t)
                gt = sorted((x["dir"], x["j"], x["idx"], x["esp"]) for x in L["v2.2"]["trig"])
                if exp != got or et != gt:
                    errs += 1
                    break
    return errs


# ───────────────────────── 3 ─────────────────────────

def labels(opt):
    set_variant(opt)
    days = EV.load_days()
    pre, manual, raw = EV.load_labels()
    gts = EV.ground_truth(days, pre, manual)
    fal = EV.falses(days, pre)
    labeled = sorted({r["date"] for r in raw})
    dets = {}
    for d, day in days.items():
        fb = [dict(b, wave=w) for b, w in zip(day["bars"], day["wave"])]
        lv = sorted(float(w["price"]) for w in day["walls"] if w.get("type") in M.LEVEL_TYPES)
        dets[d] = [dict(dir=c["dir"], f2_idx=c["j"], f1_idx=c["k"], sig_idx=c["conf"],
                        f2_time=fb[c["j"]]["time"]) for c in M.engine_v22(fb, lv, M.PARAMS["WIN"], "common")]
    ev = EV.eval_dets(dets, gts, dates=labeled, falses_list=fal)
    hold = EV.eval_dets(dets, gts, dates=EV.HOLD, falses_list=fal)
    op_g = [g for g in gts if g["date"] in labeled and g.get("f2_time") and g["f2_time"] < OPEN_CUT]
    hit = 0
    for g in op_g:
        hit += any(x["dir"] == g["side"] and g["f2"] is not None and abs(x["f2_idx"] - g["f2"]) <= 2 for x in dets[g["date"]])
    op_det = sum(1 for d in labeled for x in dets[d] if x["f2_time"] < OPEN_CUT)
    return dict(cob=round(100 * ev["rec"], 1), prec=round(100 * ev["prec"], 1), prec_rev=round(100 * ev["prec_reviewed"], 1),
                cob_holdout=round(100 * hold["rec"], 1), rot_abertura=len(op_g), cob_abertura=hit,
                sinais_abertura_rotulados=op_det)


def signals_all(opt, DSS):
    set_variant(opt)
    out = {}
    for a in ("WIN", "WDO"):
        S = bt.simulate(a, bt.signals(a, "v2.2"), DSS[a], exits=())
        out[a] = S
    return out


def fwd(S, DS, asset):
    c = bt.X[asset]["cost"]
    r = []
    for x in S.itertuples():
        if not x.ok:
            r.append(np.nan)
            continue
        D = DS[x.date]
        j = min(int(x.e) + 11, len(D["c5"]) - 1)
        r.append(x.dir * (D["c5"][j] - x.ep) - c)
    return np.array(r)


def placebo_open(DS, asset):
    """Retorno 12 barras de entrar em qualquer barra das 9h (09:05–09:55), nas duas direções."""
    c = bt.X[asset]["cost"]
    v = {"jan–abr": [], "mai–jul": [], "ago–nov": []}
    for d, D in DS.items():
        per = "jan–abr" if d <= H1 else "mai–jul" if d <= IS_END else "ago–nov"
        for e in range(1, len(D["o5"])):
            if 545 <= D["tm5"][e] < 600:
                j = min(e + 11, len(D["c5"]) - 1)
                for dr in (1, -1):
                    v[per].append(dr * (D["c5"][j] - D["o5"][e]) - c)
    return {k: round(float(np.mean(x)), 1) for k, x in v.items()}


def esp_eval(S_win, DS, start):
    T = R.run_exit(S_win, DS)
    m = T.ok & ~T.super & (T.seq <= 1) & (T.tm >= start) & (T.tm < 960) & (T.ext50 > -0.5) & (T.slope50 > -0.5)
    q = bt.mgmt(T[m & T[R.COL].notna()].sort_values(["date", "tm"]), R.COL, R.XT, "UM_POR_VEZ")
    rows = [(r.date, r.time_in, f"{int(r.xt_X) // 60:02d}:{int(r.xt_X) % 60:02d}", 2.0 * float(r.pnl_X)) for r in q.itertuples()]
    n9 = int((q.tm < 600).sum())
    return rows, n9


def main():
    os.makedirs(OUT, exist_ok=True)
    bad, tot = equivalence()
    print(f"1) v2.2 sem módulo == v2.1: {tot} divergências comparadas, pregões diferentes: {bad}", flush=True)
    DSS = {a: bt.market(a) for a in ("WIN", "WDO")}
    plc = {a: placebo_open(DSS[a], a) for a in ("WIN", "WDO")}
    print("placebo (qualquer barra das 9h, 12 barras, líquido):", plc, flush=True)
    pool, _ = F1.sniper_pool()
    rows = []
    trades = {}
    for name, opt in VARIANTS.items():
        perr = parity(opt, n_days=15) if opt else 0
        lab = labels(opt)
        S = signals_all(opt, DSS)
        r = dict(variante=name, paridade_erros=perr, **lab)
        for a in ("WIN", "WDO"):
            T = S[a]
            T = T[T.ok].copy()
            T["r12"] = fwd(T, DSS[a], a)
            nd = T.date.nunique()
            op = T[T.time_in < OPEN_CUT]
            r[f"{a}_gatilhos_dia"] = round(len(T) / max(1, len(bt.market(a)) if False else 222), 2)
            r[f"{a}_9h_por_dia"] = round(len(op) / 222, 2)
            for per, lo, hi in (("jan–abr", "", H1), ("mai–jul", H1, IS_END), ("ago–nov", IS_END, "9999")):
                sel = op[(op.date > lo) & (op.date <= hi)]
                r[f"{a}_9h_r12_{per}"] = round(float(sel.r12.mean()), 1) if len(sel) else np.nan
            r[f"{a}_9h_n"] = len(op)
        # especialista (WIN): janela atual (10:00) e com 9h (09:05)
        for lab_s, start in (("esp", 600), ("esp9h", 545)):
            rr, n9 = esp_eval(S["WIN"], DSS["WIN"], start)
            per = F1.by_period(rr)
            r[f"{lab_s}_ops"], r[f"{lab_s}_rdd"], r[f"{lab_s}_net"], r[f"{lab_s}_dd"] = (per["completo"]["ops"], per["completo"]["rdd"],
                                                                                         per["completo"]["net"], per["completo"]["dd"])
            r[f"{lab_s}_pf_partes"] = "/".join(f"{per[p]['pf']:.2f}" for p in ("jan–abr", "mai–jul", "ago–nov"))
            r[f"{lab_s}_trades_9h"] = n9
            trades[(name, lab_s)] = rr
        # Sniper com a configuração escolhida para o v2.1 (gatilho, âncora, ativo 6) e a janela atual (conf, sem âncora, 2)
        for lab_s, (mom, anc, win) in (("snp", ("trig", True, ("ativo", 6))), ("snp_tol2", ("conf", False, ("tol", 2)))):
            trs = []
            for a in ("WIN", "WDO"):
                mp = F1.engine_map(a, "v2.2", mom, anc)
                trs += F1.sniper_filter(pool[a], mp, win, a)
            rr = F1.rows_sniper(trs)
            per = F1.by_period(rr)
            r[f"{lab_s}_ops"], r[f"{lab_s}_rdd"], r[f"{lab_s}_net"] = per["completo"]["ops"], per["completo"]["rdd"], per["completo"]["net"]
            r[f"{lab_s}_pf_partes"] = "/".join(f"{per[p]['pf']:.2f}" for p in ("jan–abr", "mai–jul", "ago–nov"))
            trades[(name, lab_s)] = rr
        for lab_c, e_key in (("cart", "esp"), ("cart9h", "esp9h")):
            cc = trades[(name, "snp")] + trades[(name, e_key)]
            per = F1.by_period(cc)
            isr = F1.stats_brl([x for x in cc if x[0] <= IS_END])["rdd"]
            r[f"{lab_c}_net"], r[f"{lab_c}_dd"], r[f"{lab_c}_rdd"], r[f"{lab_c}_rdd_jan_jul"] = (per["completo"]["net"], per["completo"]["dd"],
                                                                                                  per["completo"]["rdd"], isr)
            r[f"{lab_c}_pf_partes"] = "/".join(f"{per[p]['pf']:.2f}" for p in ("jan–abr", "mai–jul", "ago–nov"))
        rows.append(r)
        print(name, {k: v for k, v in r.items() if k in ("paridade_erros", "cob", "prec", "cob_abertura", "rot_abertura",
                                                          "WIN_9h_por_dia", "WIN_9h_r12_jan–abr", "WIN_9h_r12_mai–jul", "WIN_9h_r12_ago–nov",
                                                          "esp_rdd", "esp9h_rdd", "snp_rdd", "cart_rdd", "cart9h_rdd")}, flush=True)
    Rdf = pd.DataFrame(rows)
    Rdf.to_csv(os.path.join(OUT, "variantes.csv"), index=False)
    json.dump({f"{k[0]}|{k[1]}": v for k, v in trades.items()}, open(os.path.join(OUT, "trades.json"), "w"))
    json.dump(plc, open(os.path.join(OUT, "placebo_9h.json"), "w"))
    pd.set_option("display.width", 300)
    print("\n" + Rdf.T.to_string())


if __name__ == "__main__":
    main()
