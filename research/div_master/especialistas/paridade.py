# -*- coding: utf-8 -*-
"""
Etapa 1 — testes de causalidade e de porta do módulo unificado (SPEC_ESPECIALISTAS_5176.md §5).

  1. Porta v3   : engine_v3(elig="all") == core.detect_divergences_v3 com raio de Wall infinito e sem NWE.
  2. Porta v2.1 : engine_v21(elig="native_v21") == engine_v2_1/detections.json (16 pregões do rotulador).
  3. Paridade   : para cada barra t, roda o pipeline inteiro em bars[:t+1] e compara com o lote do dia:
                  candidatos com conf <= t, gatilhos com idx <= t (inclusive tags) e descartes com conf <= t.
                  Qualquer diferença = leitura do futuro ou repintura.
Só pregões de jan–jul (IS). Uso: python paridade.py [n_dias_por_ativo|all]
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modulo as M  # noqa: E402

sys.path.insert(0, M.ROOT)
from core.div_wall_signal import DivParamsV2, compute_flow, detect_divergences_v3  # noqa: E402
from research.div_wall.data import IS_END, load_asset  # noqa: E402

LAB = os.path.join(M.ROOT, "research", "div_master", "labeler", "data")
DET21 = os.path.join(M.ROOT, "research", "div_master", "engine_v2_1", "detections.json")


def ck(c):
    return (c["engine"], c["dir"], c["j"], c["k"], c["conf"], c["micro"])


def tk(x):
    return (x["engine"], x["esp"], x["sub"], x["dir"], x["j"], x["k"], x["idx"], x["dup"], x["super"])


def dk(x):
    return (x["engine"], x["esp"], x["dir"], x["j"], x["conf"])


def port_v3(asset, days):
    bad, tot = [], 0
    P = M.PARAMS[asset]
    for d in days:
        bars, walls, nwe = DATA[asset][d]
        fb = compute_flow([dict(b) for b in bars], asset)
        lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        mine = [(c["conf"], c["dir"], c["j"], c["k"]) for c in M.engine_v3(fb, lv, P, elig="all")]
        ref = detect_divergences_v3(fb, walls, nwe, DivParamsV2.default(asset, wall_radius=1e12, nwe_filter="none",
                                                                       confirm="PIVO"))
        ref = [(s.idx, s.direction, s.pivot_idx, s.f1_idx) for s in ref]
        tot += len(ref)
        if sorted(mine) != sorted(ref):
            bad.append((d, sorted(set(mine) ^ set(ref))[:4]))
    return bad, tot


def port_v21():
    ref = json.load(open(DET21, encoding="utf-8"))
    bad, tot = [], 0
    for d, dets in ref.items():
        day = json.load(open(os.path.join(LAB, f"{d}.json"), encoding="utf-8"))
        fb = [dict(b, wave=w) for b, w in zip(day["bars"], day["wave"])]
        lv = sorted(float(w["price"]) for w in day["walls"] if w.get("type") in M.LEVEL_TYPES)
        mine = [(c["conf"], c["dir"], c["j"], c["k"]) for c in M.engine_v21(fb, lv, M.PARAMS["WIN"], elig="native_v21")]
        r = [(x["sig_idx"], x["dir"], x["f2_idx"], x["f1_idx"]) for x in dets]
        tot += len(r)
        if sorted(mine) != sorted(r):
            bad.append((d, sorted(set(mine) ^ set(r))[:4]))
    return bad, tot, len(ref)


def parity_day(asset, d):
    bars, walls, _ = DATA[asset][d]
    _, B = M.run_day(asset, bars, walls)
    errs = []
    for t in range(len(bars)):
        _, L = M.run_day(asset, bars[: t + 1], walls)
        for e in M.ENGINES:
            for name, key, f, src in (("cand", ck, lambda c: c["conf"] <= t, "cands"),
                                      ("trig", tk, lambda x: x["idx"] <= t, "trig"),
                                      ("desc", dk, lambda x: x["conf"] <= t, "discard")):
                exp = sorted(key(x) for x in B[e][src] if f(x))
                got = sorted(key(x) for x in L[e][src])
                if exp != got:
                    errs.append(f"{asset} {d} t={t} {e} {name}: lote-ao_vivo={sorted(set(exp)-set(got))[:2]} "
                                f"ao_vivo-lote={sorted(set(got)-set(exp))[:2]}")
        if errs:
            break
    n_c = sum(len(B[e]["cands"]) for e in M.ENGINES)
    n_t = sum(len(B[e]["trig"]) for e in M.ENGINES)
    return errs, n_c, n_t


DATA = {}


def main(n_days="all"):
    out = {}
    for a in ("WIN", "WDO"):
        DATA[a] = {d: v for d, v in load_asset(a, "M5").items() if d <= IS_END}
    print("1) porta v3 (core.detect_divergences_v3, raio infinito, sem NWE)")
    for a in ("WIN", "WDO"):
        bad, tot = port_v3(a, sorted(DATA[a]))
        print(f"   {a}: {len(DATA[a])} pregões, {tot} sinais do core, pregões diferentes: {len(bad)}", bad[:3])
        out[f"port_v3_{a}"] = dict(days=len(DATA[a]), signals=tot, bad=len(bad))
    print("2) porta v2.1 (engine_v2_1/detections.json)")
    bad, tot, nd = port_v21()
    print(f"   {nd} pregões, {tot} detecções, pregões diferentes: {len(bad)}", bad[:3])
    out["port_v21"] = dict(days=nd, signals=tot, bad=len(bad))
    print("3) paridade lote × barra a barra (3 motores, 2 especialistas)")
    for a in ("WIN", "WDO"):
        days = sorted(DATA[a])
        if n_days != "all":
            random.Random(7).shuffle(days)
            days = sorted(days[: int(n_days)])
        t0, errs, nc, nt = time.time(), [], 0, 0
        for d in days:
            e, c, t = parity_day(a, d)
            errs += e
            nc += c
            nt += t
        print(f"   {a}: {len(days)} pregões, {nc} candidatos, {nt} gatilhos, erros: {len(errs)} "
              f"({time.time() - t0:.0f}s)")
        for x in errs[:5]:
            print("     ", x)
        out[f"parity_{a}"] = dict(days=len(days), cands=nc, trig=nt, errors=len(errs), first=errs[:5])
    json.dump(out, open(os.path.join(HERE, "results", "paridade.json"), "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
