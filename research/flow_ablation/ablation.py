# -*- coding: utf-8 -*-
"""
Ablação do fluxo (16/11/2026). Roda UMA variante da onda em todas as estratégias/motores que leem a onda e grava
results/var_<nome>.pkl. Regras, filtros, saídas e limiares ficam congelados; só a função de fluxo muda
(monkeypatch de `modulo.compute_flow` + chamada direta onde o harness monta as barras).

Uso: python research/flow_ablation/ablation.py <VARIANTE> [--skip-addon]
"""
import os, sys, time, pickle, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [HERE, ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "setup_v32"),
                os.path.join(DM, "engine_v2_1"), os.path.join(DM, "v32")]
import numpy as np, pandas as pd
import flows as FL
import modulo as M, bt, robust as R
from functools import lru_cache
_market = bt.market
bt.market = lru_cache(maxsize=4)(_market)          # cache (o add-on chama market várias vezes)
import motor_addon as MA
import avaliar as AV
from core import especialista_v22 as E
from core import carteira_v32_estrategias as C32
from core import div_wall_signal as DWS
import evaluate as EV
from research.div_wall.data import load_asset

COST = {"WIN": 10.0, "WDO": 0.5}
TAPE = {"WIN": ["2026-01-05", "2026-04-13", "2026-04-14", "2026-04-15", "2026-06-17", "2026-08-11", "2026-08-12",
                "2026-11-05", "2026-11-06", "2026-11-09"],
        "WDO": ["2026-03-30", "2026-04-30", "2026-05-29", "2026-06-29", "2026-06-30", "2026-08-31", "2026-09-30",
                "2026-10-28", "2026-10-29"]}


def hm(t):
    return int(t[:2]) * 60 + int(t[3:5])


def ex4(D):
    n = len(D["o5"])
    return [dict(time=f"{int(D['tm5'][k]) // 60:02d}:{int(D['tm5'][k]) % 60:02d}", open=float(D["o5"][k]),
                 high=float(D["h5"][k]), low=float(D["l5"][k]), close=float(D["c5"][k]),
                 nwe30_upper=float(D["u30"][k + 1]) if k + 1 < n else float(D["u30"][k]),
                 nwe30_lower=float(D["l30"][k + 1]) if k + 1 < n else float(D["l30"][k]),
                 nwe50_line=float(D["c50"][k + 1]) if k + 1 < n else float(D["c50"][k]),
                 nwe50_upper=float(D["u50"][k + 1]) if k + 1 < n else float(D["u50"][k]),
                 nwe50_lower=float(D["l50"][k + 1]) if k + 1 < n else float(D["l50"][k]),
                 nwe50_prev_line=float(D["c50"][0]) if k == 0 else None) for k in range(n)]


def tape_bars(asset, d, bars):
    """Barras do div_wall_v1 com o institucional (agr/pas/varejo) trocado pelo do tape (.trd) da sessão JSON."""
    import json
    from datetime import datetime, timezone
    p = os.path.join(ROOT, "data", "processed", "gex_historical_sessions_v1", f"{d}.json")
    S = json.load(open(p, encoding="utf-8"))[asset]
    if "TRD" not in str(S.get("source", "")).upper():
        return None
    tb = {datetime.fromtimestamp(int(x["time"]), tz=timezone.utc).strftime("%H:%M"): x for x in S["m5_cvd_series"]}
    out = []
    for b in bars:
        x = tb.get(b["time"])
        nb = dict(b)
        if x is not None:
            nb.update(inst_aggr_delta=float(x["inst_aggr_delta"]), inst_pass_delta=float(x["inst_pass_delta"]),
                      ret_delta_bar=float(x["ret_delta_bar"]))
        out.append(nb)
    return out


def main(var, skip_addon=False):
    t0 = time.time()
    flow = FL.make(var)
    M.compute_flow = flow
    out = dict(variant=var)
    data = {a: {d: v for d, v in load_asset(a, "M5").items() if d <= bt.END} for a in ("WIN", "WDO")}
    DS = {a: bt.market(a) for a in ("WIN", "WDO")}
    FB = {a: {} for a in ("WIN", "WDO")}
    for a in ("WIN", "WDO"):
        for d, (bars, walls, nwe) in data[a].items():
            FB[a][d] = flow([dict(b) for b in bars], a)
    print(var, "fluxo pronto", round(time.time() - t0), "s", flush=True)

    # 1) ESP_DIV_V22_WIN (produção, core/especialista_v22.run)
    rows = []
    for d, fb in FB["WIN"].items():
        if d not in DS["WIN"]:
            continue
        ex = MA.exec_bars(DS["WIN"][d])
        for t in E.run(fb, data["WIN"][d][1], ex):
            rows.append(dict(date=d, tm=hm(t["time"]), xt=hm(t["exit_time"]), d=t["dir_num"], brl=float(t["brl_1c"]),
                             why=t["exit_reason"], f2=t["f2_time"]))
    out["E22"] = pd.DataFrame(rows)
    print(var, "E22", len(rows), round(sum(r["brl"] for r in rows)), flush=True)

    # 2) ESP_DIV_V21_WIN (pesquisa, motor v2.1, robust.py)
    S = R.signals_mode("ab")
    T = R.run_exit(bt.simulate("WIN", S, DS["WIN"], exits=()), DS["WIN"])
    s21, q = R.evaluate(T)
    out["V21"] = pd.DataFrame(dict(date=q.date.values, tm=q.tm.values, xt=q[R.XT].values, d=q.dir.values,
                                   brl=q[R.COL].values))
    out["V21_bt_stats"] = s21
    print(var, "V21", s21, flush=True)

    # 3) Carteira V3.2 (4 estratégias, core/carteira_v32_estrategias.run_strategy)
    for sid, cfg in C32.STRAT_CFGS.items():
        a = cfg["asset"]
        rows = []
        for d, fb in FB[a].items():
            if d not in DS[a]:
                continue
            for t in C32.run_strategy(sid, fb, data[a][d][1], ex4(DS[a][d]), is_live=False):
                rows.append(dict(date=d, tm=hm(t["time"]), xt=hm(t["exit_time"]), d=int(t.get("dir_num", 1 if t.get("direction") == "COMPRA" else -1)),
                                 brl=float(t["brl_1c"])))
        out[sid] = pd.DataFrame(rows)
        print(var, sid, len(rows), round(sum(r["brl"] for r in rows)), flush=True)

    # 4) Add-ons setup_v32 (avaliar.py; E22 recalculado com a mesma variante, coexistência igual)
    if not skip_addon:
        win, _ = AV.build_days("WIN")
        _, e22per = AV.e22_trades(win)
        wdo, _ = AV.build_days("WDO")
        cfgs = [("WIN", t, g, tp) for t, gs in (("T1", ("G1", "G2")), ("T2", ("G3", "G4"))) for g in gs for tp in ("S2a", "S2b")]
        cfgs += [("WDO", t, g, tp) for t in ("T3A", "T3B") for g in ("G1", "G2") for tp in ("S2a", "S2b")]
        for asset, tese, g, tp in cfgs:
            days = win if asset == "WIN" else wdo
            per = e22per if asset == "WIN" else {}
            Sg = AV.gen_signals(asset, days, per, tese, g)
            Tg = AV.execute(asset, days, Sg, per, tp, one_per_dir=(tese == "T1"))
            out[f"ADD|{asset}|{tese}|{g}|{tp}"] = Tg
        print(var, "add-ons ok", round(time.time() - t0), "s", flush=True)

    # 5) Nível de sinal: candidatos dos motores + estudo de evento (12 barras, líquido de custo, barras Profit)
    sig = []
    for a in ("WIN", "WDO"):
        P = M.PARAMS[a]
        for d, fb in FB[a].items():
            bars, walls, nwe = data[a][d]
            lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
            atr = M.atr_series(fb, P["tick"])
            n = len(fb)
            engs = {"v2.1": M.engine_v21(fb, lv, P, "common", atr=atr),
                    "v3.2": M.engine_v32(fb, lv, P, "common", atr=atr, opt=M.V32_PROD)}
            for eng, cs in engs.items():
                for c in cs:
                    s_ = c["conf"]
                    if s_ + 1 >= n:
                        continue
                    ep, xp = fb[s_ + 1]["open"], fb[min(s_ + 12, n - 1)]["close"]
                    sig.append(dict(asset=a, eng=eng, date=d, dir=c["dir"], j=c["j"], k=c["k"], s=s_,
                                    pts=c["dir"] * (xp - ep) - COST[a]))
            pv2 = DWS.DivParamsV2.default(a, wave_k=0.5, nwe_filter="none", confirm="PIVO",
                                          **({"wall_radius": 150.0} if a == "WIN" else {}))
            for sg in DWS.detect_divergences_v2(fb, walls, nwe, pv2):
                s_ = sg.idx
                if s_ + 1 >= n:
                    continue
                ep, xp = fb[s_ + 1]["open"], fb[min(s_ + 12, n - 1)]["close"]
                sig.append(dict(asset=a, eng="divv2", date=d, dir=sg.direction, j=sg.pivot_idx, k=sg.f1_idx, s=s_,
                                pts=sg.direction * (xp - ep) - COST[a]))
    out["SIG"] = pd.DataFrame(sig)
    print(var, "sinais", len(sig), flush=True)

    # 6) Rótulos do usuário (9 pregões WIN, labeler/data) — onda da variante alinhada por horário
    days = EV.load_days()
    pre, manual, raw = EV.load_labels()
    gts = EV.ground_truth(days, pre, manual)
    fal = EV.falses(days, pre)
    labeled = sorted({r["date"] for r in raw})
    dets = {"v2.1(detect.py)": {}, "v3.2": {}, "v3.2 consol.": {}, "divv2": {}}
    par = {}
    for d, day in days.items():
        if d not in FB["WIN"]:
            continue
        wmap = {b["time"]: b["wave"] for b in FB["WIN"][d]}
        base_w = day["wave"]
        wave = [float(wmap.get(b["time"], 0.0)) for b in day["bars"]]
        if var == "A_BASE":
            par[d] = float(max(abs(x - y) for x, y in zip(wave, base_w)))
        fb = [dict(b, wave=w) for b, w in zip(day["bars"], wave)]
        lv = sorted(float(w["price"]) for w in day["walls"] if w.get("type") in M.LEVEL_TYPES)
        P = M.PARAMS["WIN"]
        dv, _ = EV.detect(day["bars"], wave, day["walls"], None)
        dets["v2.1(detect.py)"][d] = dv
        cs = M.engine_v32(fb, lv, P, "common", atr=M.atr_series(fb, P["tick"]), opt=M.V32_PROD)
        dets["v3.2"][d] = [dict(dir=c["dir"], f2_idx=c["j"], f1_idx=c["k"], sig_idx=c["conf"]) for c in cs]
        keep = {}
        for c in cs:
            keep[(c["dir"], c["k"])] = c
        dets["v3.2 consol."][d] = [dict(dir=c["dir"], f2_idx=c["j"], f1_idx=c["k"], sig_idx=c["conf"]) for c in keep.values()]
        nwe = tuple(np.asarray(day["nwe"][k], float) for k in ("c", "u", "l"))
        pv2 = DWS.DivParamsV2.default("WIN", wave_k=0.5, wall_radius=150.0, nwe_filter="none", confirm="PIVO")
        dets["divv2"][d] = [dict(dir=s.direction, f2_idx=s.pivot_idx, f1_idx=s.f1_idx, sig_idx=s.idx)
                            for s in DWS.detect_divergences_v2(fb, day["walls"], nwe, pv2)]
    lab = {}
    for eng, dd in dets.items():
        ev = EV.eval_dets(dd, gts, dates=labeled, falses_list=fal)
        ho = EV.eval_dets(dd, gts, dates=EV.HOLD, falses_list=fal)
        tr = EV.eval_dets(dd, gts, dates=EV.TRAIN, falses_list=fal)
        lab[eng] = dict(rec=ev["rec"], prec=ev["prec"], prec_rev=ev["prec_reviewed"], tp=ev["TP"], n_gt=ev["n_gt"],
                        n_det=ev["n_det"], rec_hold=ho["rec"], rec_train=tr["rec"], prec_hold=ho["prec"],
                        per_day=round(ev["n_det"] / len(labeled), 1))
    out["LABELS"] = lab
    out["LABEL_PARITY"] = par
    print(var, "rótulos", {k: (round(v["rec"], 3), round(v["prec"], 3), round(v["rec_hold"], 3)) for k, v in lab.items()}, flush=True)

    # 7) Dias de tape real: mesma variante sobre barras com o institucional do .trd
    tp_out = {}
    for a in ("WIN", "WDO"):
        for d in TAPE[a]:
            if d not in data[a] or d not in DS[a]:
                continue
            tb = tape_bars(a, d, data[a][d][0])
            if tb is None:
                continue
            fbt = flow([dict(b) for b in tb], a) if var not in ("C_SEM_OHLC", "D_MIX", "X_INST_SEM_PAVIO") else None
            if fbt is None:
                # nas variantes sem pavio o institucional do tape já não tem pavio: usa o do tape direto
                P_ = [FL._parts(b, a) for b in tb]
                if var == "C_SEM_OHLC":
                    F = [(0.25 * p["porte"] + 0.30 * p["inst"]) / 0.55 for p in P_]
                elif var == "D_MIX":
                    F = [0.45 * (p["bv"] - p["sv"]) + 0.25 * p["porte"] + 0.30 * p["inst"] for p in P_]
                else:
                    F = [p["inst"] for p in P_]
                fbt = FL._pipeline(tb, F)
            fbm = FB[a][d]
            wm, wt = np.array([b["wave"] for b in fbm]), np.array([b["wave"] for b in fbt])
            P = M.PARAMS[a]
            lv = sorted(float(w["price"]) for w in data[a][d][1] if w.get("type") in M.LEVEL_TYPES)
            cm = {(c["dir"], c["j"]) for c in M.engine_v32(fbm, lv, P, "common", atr=M.atr_series(fbm, P["tick"]), opt=M.V32_PROD)}
            ct = {(c["dir"], c["j"]) for c in M.engine_v32(fbt, lv, P, "common", atr=M.atr_series(fbt, P["tick"]), opt=M.V32_PROD)}
            e_m = E.run(fbm, data[a][d][1], MA.exec_bars(DS[a][d])) if a == "WIN" else []
            e_t = E.run(fbt, data[a][d][1], MA.exec_bars(DS[a][d])) if a == "WIN" else []
            tp_out[(a, d)] = dict(corr_wave=float(np.corrcoef(wm, wt)[0, 1]) if wm.std() > 0 and wt.std() > 0 else float("nan"),
                                  corr_dwave=float(np.corrcoef(np.diff(wm), np.diff(wt))[0, 1]) if len(wm) > 2 else float("nan"),
                                  n_min=len(cm), n_tape=len(ct), both=len(cm & ct),
                                  e22_min=[(t["time"], t["dir_num"], t["brl_1c"]) for t in e_m],
                                  e22_tape=[(t["time"], t["dir_num"], t["brl_1c"]) for t in e_t])
    out["TAPE"] = tp_out
    print(var, "tape", len(tp_out), "dias", round(time.time() - t0), "s", flush=True)
    pickle.dump(out, open(os.path.join(HERE, "results", f"var_{var}.pkl"), "wb"))


if __name__ == "__main__":
    main(sys.argv[1], skip_addon="--skip-addon" in sys.argv)
