# -*- coding: utf-8 -*-
"""
Módulo unificado dos dois especialistas de divergência do painel 5176 (SPEC_ESPECIALISTAS_5176.md, revisão 2).

Três motores de divergência (preço × onda "Fluxo Smart Money"):
  - "v3"   : pivô L2/R1, barra 0 elegível como F1, onda do F1 em k±1, F1 = onda mais extrema, reset do F1
             (porta de core.div_wall_signal.detect_divergences_v3 sem a condição de Wall e sem NWE);
  - "v2.1" : ZigZag causal 1,2×ATR14, F1 = pivô anterior mais recente que passa, sem leque
             (porta de research/div_master/engine_v2_1/detect.py);
  - "v3.1" : fusão (SPEC §2.3).
Dois especialistas (gatilho Opção C, SPEC §3):
  - "WALL"   : ESP_DIV_WALL, subcasos C1 (furou e retomou) e C2 (tocou e rejeitou);
  - "EXTREMO": ESP_DIV_EXTREMO_DIA (a partir das 09:30).

Causalidade: na barra t, tudo é calculado só com bars[0..t]. Um candidato do motor nasce na barra `conf`
(confirmação do pivô); o gatilho do especialista dispara no fechamento da primeira barra
t ∈ [max(j+1, conf), j+3] que satisfaz a condição. Entrada = abertura de t+1. Verificado por paridade.py.

Não depende do painel, do motor ao vivo nem de core/ além de compute_flow.
"""
from __future__ import annotations

import os
import bisect
import statistics
import sys
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from core.div_wall_signal import compute_flow  # noqa: E402
except ImportError:
    compute_flow = None  # noqa: E402

LEVEL_TYPES = ("Wall", "MidWall")
# Gatilho Opção C: "ab" = revisão (a)+(b) aprovada em 12/11/2026 (padrão); "orig" = texto da revisão 2 da SPEC.
TRIGGER = "ab"
ENGINES = ("v3", "v2.1", "v3.1")
ESPS = ("WALL", "EXTREMO")

# Parâmetros congelados da revisão 2 da SPEC. WDO é provisório (SPEC §6.2).
PARAMS = {
    "WIN": dict(tick=5.0, zone=150.0, pierce_max=220.0, day_tol=30.0, buf=20.0, zz_floor=80.0,
                tol_v21=60.0, tol_v3=50.0),
    "WDO": dict(tick=0.5, zone=3.5, pierce_max=6.0, day_tol=1.0, buf=0.5, zz_floor=2.5,
                tol_v21=2.0, tol_v3=1.5),
}
COMMON = dict(
    r_atr=1.2,            # ZigZag v2.1 / v3.1
    r_atr_open=0.8,       # v3.1: reversão reduzida na abertura
    open_conf_end="09:35",  # v3.1: até quando vale a confirmação reduzida
    seed_end="09:20",     # v3.1: janela da semente de F1
    day_start="09:30",    # ESP_DIV_EXTREMO_DIA
    k_v3=0.50, k_v21=0.15, k_v31=0.15,   # limiar da onda × mediana causal |onda|
    min_dist_v3=3, min_gap=2, max_gap=48,
    trig_max=3,           # gatilho até j+3
)


def hm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


# ─────────────────────────────── utilidades causais ───────────────────────────────

def atr_series(bars: List[dict], tick: float) -> List[float]:
    """ATR(14) de Wilder idêntico a engine_v2_1.detect.atr14, com piso de 1 tick (o original usava 5,0 fixo = 1 tick do WIN)."""
    out, s, cnt, atr = [], 0.0, 0, None
    for i, b in enumerate(bars):
        if i == 0:
            out.append(max(b["high"] - b["low"], tick))
            continue
        p = bars[i - 1]
        tr = max(b["high"] - b["low"], abs(b["high"] - p["close"]), abs(b["low"] - p["close"]))
        cnt += 1
        if cnt <= 14:
            s += tr
            atr = s / cnt
        else:
            atr = (atr * 13 + tr) / 14
        out.append(max(atr, tick))
    return out


def zigzag(bars: List[dict], atr: List[float], r_atr: float, floor: float) -> List[dict]:
    """Pivôs de ZigZag confirmados na barra da reversão (cópia de engine_v2_1.detect.zigzag com ATR pré-calculado)."""
    n = len(bars)
    if n < 3:
        return []
    peak_i, peak = 0, bars[0]["high"]
    trough_i, trough = 0, bars[0]["low"]
    direction = 0
    piv = []
    for i in range(1, n):
        R = max(r_atr * atr[i], floor)
        h, l = bars[i]["high"], bars[i]["low"]
        if direction == 0:
            if h > peak:
                peak, peak_i = h, i
            if l < trough:
                trough, trough_i = l, i
            if peak - trough >= R:
                if peak_i > trough_i:
                    piv.append(dict(idx=trough_i, side=1, px=trough, conf=i))
                    direction = 1
                elif trough_i > peak_i:
                    piv.append(dict(idx=peak_i, side=-1, px=peak, conf=i))
                    direction = -1
            continue
        if direction == 1:
            if h >= peak:
                peak, peak_i = h, i
            if l <= peak - R:
                piv.append(dict(idx=peak_i, side=-1, px=peak, conf=i))
                direction = -1
                trough, trough_i = l, i
        else:
            if l <= trough:
                trough, trough_i = l, i
            if h >= trough + R:
                piv.append(dict(idx=trough_i, side=1, px=trough, conf=i))
                direction = 1
                peak, peak_i = h, i
    return piv


def is_piv(bars, j, d, L, R):
    if j - L < 0 or j + R >= len(bars):
        return False
    if d == 1:
        x = bars[j]["low"]
        return all(x <= bars[k]["low"] for k in range(j - L, j)) and all(x < bars[k]["low"] for k in range(j + 1, j + R + 1))
    x = bars[j]["high"]
    return all(x >= bars[k]["high"] for k in range(j - L, j)) and all(x > bars[k]["high"] for k in range(j + 1, j + R + 1))


class RunMedian:
    """Mediana causal de |onda| (igual a statistics.median da lista acumulada)."""
    def __init__(self):
        self.v = []

    def add(self, x):
        bisect.insort(self.v, x)

    def get(self):
        v, n = self.v, len(self.v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _px(b, d):
    return b["low"] if d == 1 else b["high"]


# ─────────────────────────────── âncoras (SPEC §1 / §3) ───────────────────────────────

def anchors(bars: List[dict], j: int, d: int, levels: List[float], P: dict) -> dict:
    """Âncoras do F2 na barra j. Só lê bars[0..j]."""
    b = bars[j]
    px, cj = _px(b, d), b["close"]
    a = {"c1": None, "c2": None, "day": None}
    if TRIGGER == "orig":
        if d == 1:
            up = [w for w in levels if px < w <= px + P["pierce_max"]]
            dn = [w for w in levels if px - P["zone"] <= w <= px]
            a["c1"] = min(up) if up else None
            a["c2"] = max(dn) if dn else None
        else:
            dn = [w for w in levels if px - P["pierce_max"] <= w < px]
            up = [w for w in levels if px <= w <= px + P["zone"]]
            a["c1"] = max(dn) if dn else None
            a["c2"] = min(up) if up else None
    else:
        # revisão (a): C1 só com furo REAL (a barra do pivô FECHOU além da Wall); furo só de pavio vira C2.
        if d == 1:
            c1 = [w for w in levels if cj < w <= px + P["pierce_max"]]
            c2 = [w for w in levels if px - P["zone"] <= w <= min(cj, px + P["pierce_max"])]
            a["c1"] = min(c1) if c1 else None
            a["c2"] = max(c2) if c2 else None
        else:
            c1 = [w for w in levels if px - P["pierce_max"] <= w < cj]
            c2 = [w for w in levels if max(cj, px - P["pierce_max"]) <= w <= px + P["zone"]]
            a["c1"] = max(c1) if c1 else None
            a["c2"] = min(c2) if c2 else None
    if hm(b["time"]) >= hm(COMMON["day_start"]) and j >= 2:
        ref = px if TRIGGER == "orig" else cj   # (a): "violou" só com FECHAMENTO fora do range anterior
        if d == 1:
            e = min(x["low"] for x in bars[: j - 1])
            if px <= e + P["day_tol"]:
                a["day"] = dict(e=e, viol=ref < e)
        else:
            e = max(x["high"] for x in bars[: j - 1])
            if px >= e - P["day_tol"]:
                a["day"] = dict(e=e, viol=ref > e)
    return a


def eligible(a: dict, mode: str, bars=None, j=None, d=None, levels=None, P=None) -> bool:
    if mode == "all":
        return True
    if mode == "native_v21":   # regra original do v2.1: ≤ zona de Wall/MidWall ou nova extrema estrita do pregão
        px = _px(bars[j], d)
        near = bool(levels) and min(abs(px - w) for w in levels) <= P["zone"]
        if j == 0:
            day = True
        else:
            day = px < min(x["low"] for x in bars[:j]) if d == 1 else px > max(x["high"] for x in bars[:j])
        return near or day
    return a["c1"] is not None or a["c2"] is not None or a["day"] is not None   # "common": WALL ou EXTREMO


def micro_ok(fb: List[dict], j: int, conf: int, d: int) -> bool:
    """Item 5 do v3.1: defesa na janela j..conf (wyckoff_abs, inst_pass_delta ou force a favor)."""
    for x in range(j, conf + 1):
        b = fb[x]
        if d * float(b.get("wyckoff_abs", 0)) > 0 or d * float(b.get("inst_pass_delta", 0)) > 0 \
                or d * float(b.get("force", 0)) > 0:
            return True
    return False


def _cand(engine, d, j, k, conf, fb, w1, w2, thr, a):
    return dict(engine=engine, dir=d, j=j, k=k, conf=conf, px1=_px(fb[k], d), px2=_px(fb[j], d),
                w1=float(w1), w2=float(w2), wd=float(d * (w2 - w1)), thr=float(thr),
                c1=a["c1"], c2=a["c2"], day=a["day"], time_j=fb[j]["time"], time_conf=fb[conf]["time"],
                micro=micro_ok(fb, j, conf, d))


# ─────────────────────────────── motor v3 ───────────────────────────────

def engine_v3(fb, levels, P, elig="common"):
    n = len(fb)
    if n == 0:
        return []
    tol = P["tol_v3"]
    piv = {1: [(0, fb[0]["low"])], -1: [(0, fb[0]["high"])]}
    last = {1: None, -1: None}
    anchor = {1: 0, -1: 0}
    absw, out = RunMedian(), []

    def w1f(k, d, i):
        ws = [float(fb[x]["wave"]) for x in range(max(0, k - 1), min(i, k + 1) + 1)]
        return min(ws) if d == 1 else max(ws)

    for i in range(n):
        absw.add(abs(float(fb[i]["wave"])))
        j = i - 1
        if j - 2 < 0:
            continue
        thr = COMMON["k_v3"] * absw.get()
        for d in (1, -1):
            if not is_piv(fb, j, d, 2, 1):   # lê só até a barra j+1 = i
                continue
            px2, w2 = _px(fb[j], d), float(fb[j]["wave"])
            prev = piv[d]
            piv[d] = prev + [(j, px2)]
            cs = [(k, pk, w1f(k, d, i)) for (k, pk) in prev if anchor[d] <= k <= j - COMMON["min_dist_v3"] and
                  ((px2 <= pk + tol) if d == 1 else (px2 >= pk - tol))]
            if not cs:
                continue
            k, px1, w1 = (min if d == 1 else max)(cs, key=lambda x: x[2])
            if not d * (w2 - w1) > thr:
                continue
            a = anchors(fb, j, d, levels, P)
            if not eligible(a, elig, fb, j, d, levels, P):
                continue
            if last[d] is not None:
                lp, lk = last[d]
                t = 0.0 if k == lk else tol
                if not (px2 < lp + t if d == 1 else px2 > lp - t):
                    continue
                last[d] = (min(lp, px2) if d == 1 else max(lp, px2), k)
            else:
                last[d] = (px2, k)
            anchor[d] = j
            out.append(_cand("v3", d, j, k, i, fb, w1, w2, thr, a))
    return out


# ─────────────────────────────── motor v2.1 ───────────────────────────────

def engine_v21(fb, levels, P, elig="common", atr=None):
    atr = atr or atr_series(fb, P["tick"])
    piv = zigzag(fb, atr, COMMON["r_atr"], P["zz_floor"])
    tol = P["tol_v21"]
    used = {1: set(), -1: set()}
    pool = {1: [], -1: []}
    out = []
    for pv in piv:
        j, d, conf = pv["idx"], pv["side"], pv["conf"]
        thr = COMMON["k_v21"] * statistics.median([abs(float(fb[x]["wave"])) for x in range(conf + 1)])
        a = anchors(fb, j, d, levels, P)
        if not eligible(a, elig, fb, j, d, levels, P):
            pool[d].append(pv)
            continue
        f1 = None
        for q in reversed(pool[d]):
            gap = j - q["idx"]
            if gap > COMMON["max_gap"]:
                break
            if gap < COMMON["min_gap"] or q["idx"] in used[d]:
                continue
            if not ((pv["px"] <= q["px"] + tol) if d == 1 else (pv["px"] >= q["px"] - tol)):
                continue
            if not d * (float(fb[j]["wave"]) - float(fb[q["idx"]]["wave"])) > thr:
                continue
            f1 = q
            break
        if f1 is not None:
            used[d].add(f1["idx"])
            out.append(_cand("v2.1", d, j, f1["idx"], conf, fb, fb[f1["idx"]]["wave"], fb[j]["wave"], thr, a))
        pool[d].append(pv)
    return out


# ─────────────────────────────── motor v2.2 (v2.1 + módulo de abertura) ───────────────────────────────
# Mesmas regras de pareamento do v2.1 (F1 = pivô anterior mais recente que passa, cada F1 uma vez, onda da própria barra,
# limiar 0,15 × mediana, sem reset e sem regra de repetição). O módulo de abertura só acrescenta pivôs:
#   seed     : barra 0 (09:00) e o primeiro pivô L1/R1 até 09:20 entram como F1 (não como F2);
#   zz_open  : ZigZag com reversão menor (r × ATR14) cujos pivôs são confirmados até `open_end` também valem como F2;
#   lr_open  : pivô L2/R1 com o candle da barra de confirmação a favor, confirmado até `open_end`, vale como F2.
# Sem nenhuma opção ligada, o v2.2 reproduz o v2.1 exatamente (testado em v22/teste.py).
V22 = dict(seed=False, zz_open=None, lr_open=False, open_end="09:35", seed_end="09:20")
# Variante escolhida em v22/teste.py (12/11/2026): semente 09:00 + ZigZag 0,8 × ATR confirmado até 10:00.
V22_ABERTURA = dict(seed=True, zz_open=0.8, open_end="10:00")


def engine_v22(fb, levels, P, elig="common", atr=None, opt=None):
    o = dict(V22)
    o.update(opt or {})
    n = len(fb)
    if n == 0:
        return []
    atr = atr or atr_series(fb, P["tick"])
    t_open, t_seed = hm(o["open_end"]), hm(o["seed_end"])
    ev = [(p["conf"], p["idx"], p["side"], True, "zz", p["px"]) for p in zigzag(fb, atr, COMMON["r_atr"], P["zz_floor"])]
    if o["zz_open"]:
        for p in zigzag(fb, atr, o["zz_open"], P["zz_floor"]):
            if hm(fb[p["conf"]]["time"]) <= t_open:
                ev.append((p["conf"], p["idx"], p["side"], True, "zzo", p["px"]))
    seeded = {1: False, -1: False}
    for j in range(1, n - 1):
        conf = j + 1
        for d in (1, -1):
            if o["lr_open"] and hm(fb[conf]["time"]) <= t_open and is_piv(fb, j, d, 2, 1) \
                    and d * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                ev.append((conf, j, d, True, "lr", _px(fb[j], d)))
            if o["seed"] and not seeded[d] and hm(fb[j]["time"]) <= t_seed and is_piv(fb, j, d, 1, 1):
                ev.append((conf, j, d, False, "seed", _px(fb[j], d)))
                seeded[d] = True
    if o["seed"]:
        ev.append((0, 0, 1, False, "seed0", fb[0]["low"]))
        ev.append((0, 0, -1, False, "seed0", fb[0]["high"]))
    order = ("seed0", "seed", "zz", "zzo", "lr")
    ev.sort(key=lambda e: (e[0], e[1], order.index(e[4])))
    tol = P["tol_v21"]
    pool = {1: [], -1: []}
    seen = {1: set(), -1: set()}
    tried = {1: set(), -1: set()}
    used = {1: set(), -1: set()}
    out = []
    for conf, j, d, f2_ok, src, px2 in ev:
        if f2_ok and j not in tried[d]:
            tried[d].add(j)
            a = anchors(fb, j, d, levels, P)
            if eligible(a, elig, fb, j, d, levels, P):
                thr = COMMON["k_v21"] * statistics.median([abs(float(fb[x]["wave"])) for x in range(conf + 1)])
                w2 = float(fb[j]["wave"])
                f1 = None
                for k, pk in reversed(pool[d]):
                    gap = j - k
                    if gap > COMMON["max_gap"]:
                        break
                    if gap < COMMON["min_gap"] or k in used[d]:
                        continue
                    if not ((px2 <= pk + tol) if d == 1 else (px2 >= pk - tol)):
                        continue
                    if not d * (w2 - float(fb[k]["wave"])) > thr:
                        continue
                    f1 = k
                    break
                if f1 is not None:
                    used[d].add(f1)
                    c = _cand("v2.2", d, j, f1, conf, fb, fb[f1]["wave"], w2, thr, a)
                    c["src"] = src
                    out.append(c)
        if j not in seen[d]:
            seen[d].add(j)
            pool[d].append((j, px2))
            pool[d].sort()
    out.sort(key=lambda c: (c["conf"], c["j"]))
    return out


# ─────────────────────────────── motor v3.1 (fusão) ───────────────────────────────

def engine_v31(fb, levels, P, elig="common", require_micro=False, atr=None):
    n = len(fb)
    if n == 0:
        return []
    atr = atr or atr_series(fb, P["tick"])
    t_open, t_seed = hm(COMMON["open_conf_end"]), hm(COMMON["seed_end"])
    ev = []   # (conf, idx, side, f2_ok, src)
    for p in zigzag(fb, atr, COMMON["r_atr"], P["zz_floor"]):
        ev.append((p["conf"], p["idx"], p["side"], True, "zz"))
    for p in zigzag(fb, atr, COMMON["r_atr_open"], P["zz_floor"]):
        if hm(fb[p["conf"]]["time"]) <= t_open:
            ev.append((p["conf"], p["idx"], p["side"], True, "zz08"))
    seeded = {1: False, -1: False}
    for j in range(1, n - 1):
        conf = j + 1
        for d in (1, -1):
            if hm(fb[conf]["time"]) <= t_open and is_piv(fb, j, d, 2, 1) and d * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                ev.append((conf, j, d, True, "lr"))
            if not seeded[d] and hm(fb[j]["time"]) <= t_seed and is_piv(fb, j, d, 1, 1):
                ev.append((conf, j, d, False, "seed"))
                seeded[d] = True
    ev.append((0, 0, 1, False, "seed0"))
    ev.append((0, 0, -1, False, "seed0"))
    ev.sort(key=lambda e: (e[0], e[1], ("seed0", "seed", "zz", "zz08", "lr").index(e[4])))

    tol = P["tol_v21"]
    pool = {1: [], -1: []}
    seen = {1: set(), -1: set()}
    tried = {1: set(), -1: set()}
    used = {1: set(), -1: set()}
    anchor = {1: 0, -1: 0}
    last_px = {1: None, -1: None}
    out = []
    for conf, j, d, f2_ok, src in ev:
        px2 = _px(fb[j], d)
        if f2_ok and j not in tried[d]:
            tried[d].add(j)
            a = anchors(fb, j, d, levels, P)
            if eligible(a, elig, fb, j, d, levels, P):
                thr = COMMON["k_v31"] * statistics.median([abs(float(fb[x]["wave"])) for x in range(conf + 1)])
                w2 = float(fb[j]["wave"])
                f1 = None
                for k, pk in reversed(pool[d]):
                    gap = j - k
                    if gap > COMMON["max_gap"]:
                        break
                    if gap < COMMON["min_gap"] or k in used[d] or k < anchor[d]:
                        continue
                    if not ((px2 <= pk + tol) if d == 1 else (px2 >= pk - tol)):
                        continue
                    ws = [float(fb[x]["wave"]) for x in range(max(0, k - 1), min(conf, k + 1) + 1)]
                    w1 = min(ws) if d == 1 else max(ws)
                    if not d * (w2 - w1) > thr:
                        continue
                    f1 = (k, w1)
                    break
                rep_ok = last_px[d] is None or (px2 < last_px[d] + tol if d == 1 else px2 > last_px[d] - tol)
                if f1 is not None and rep_ok:
                    c = _cand("v3.1", d, j, f1[0], conf, fb, f1[1], w2, thr, a)
                    c["src"] = src
                    if c["micro"] or not require_micro:
                        used[d].add(f1[0])
                        anchor[d] = j
                        last_px[d] = px2 if last_px[d] is None else (min(last_px[d], px2) if d == 1 else max(last_px[d], px2))
                        out.append(c)
        if j not in seen[d]:
            seen[d].add(j)
            pool[d].append((j, px2))
            pool[d].sort()
    out.sort(key=lambda c: (c["conf"], c["j"]))
    return out


# ─────────────────────────────── motor v3.2 (v3.1 com F1 no fluxo extremo, sem reset) ───────────────────────────────
# Pedido de 12/11/2026, a partir das marcações do usuário em WIN 05/11: o F1 é o pivô da perna com o fluxo mais extremo
# e o F2 é o último extremo de preço; uma divergência por perna. Mesmos pivôs do v3.1 (abertura incluída).
#   f1    : "flow" (onda mais extrema da própria barra) | "flow_k1" (extremo em k±1, como o v3.1) | "recent" (v3.1)
#   reset : True = v3.1 (o próximo F1 só pode ser o último F2 ou depois); False = sem reset
#   rep   : regra de repetição do v3 (mesmo F1 → F2 com extremo novo; outro F1 → até price_tol do último F2)
#   used  : cada F1 uma vez (v2.1/v3.1). Com f1="flow" fica False para permitir extensões do mesmo F1.
V32 = dict(f1="flow", reset=False, rep=True, used=False, open_module=True)
# Motor da carteira 5176 a partir de 12/11/2026 (escolha do usuário): v3.2 SEM o módulo de abertura (só o ZigZag 1,2×ATR).
V32_PROD = dict(f1="flow", reset=False, rep=True, used=False, open_module=False)


def engine_v32(fb, levels, P, elig="common", atr=None, opt=None):
    o = dict(V32)
    o.update(opt or {})
    n = len(fb)
    if n == 0:
        return []
    atr = atr or atr_series(fb, P["tick"])
    t_open, t_seed = hm(COMMON["open_conf_end"]), hm(COMMON["seed_end"])
    ev = [(p["conf"], p["idx"], p["side"], True, "zz") for p in zigzag(fb, atr, COMMON["r_atr"], P["zz_floor"])]
    if o["open_module"]:
        for p in zigzag(fb, atr, COMMON["r_atr_open"], P["zz_floor"]):
            if hm(fb[p["conf"]]["time"]) <= t_open:
                ev.append((p["conf"], p["idx"], p["side"], True, "zz08"))
        seeded = {1: False, -1: False}
        for j in range(1, n - 1):
            conf = j + 1
            for d in (1, -1):
                if hm(fb[conf]["time"]) <= t_open and is_piv(fb, j, d, 2, 1) and d * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                    ev.append((conf, j, d, True, "lr"))
                if not seeded[d] and hm(fb[j]["time"]) <= t_seed and is_piv(fb, j, d, 1, 1):
                    ev.append((conf, j, d, False, "seed"))
                    seeded[d] = True
        ev.append((0, 0, 1, False, "seed0"))
        ev.append((0, 0, -1, False, "seed0"))
    ev.sort(key=lambda e: (e[0], e[1], ("seed0", "seed", "zz", "zz08", "lr").index(e[4])))
    tol = P["tol_v21"]
    pool = {1: [], -1: []}
    seen = {1: set(), -1: set()}
    tried = {1: set(), -1: set()}
    used = {1: set(), -1: set()}
    anchor = {1: 0, -1: 0}
    last = {1: None, -1: None}      # (preço extremo do último F2, F1 do último sinal)
    out = []
    for conf, j, d, f2_ok, src in ev:
        px2 = _px(fb[j], d)
        if f2_ok and j not in tried[d]:
            tried[d].add(j)
            a = anchors(fb, j, d, levels, P)
            if eligible(a, elig, fb, j, d, levels, P):
                thr = COMMON["k_v31"] * statistics.median([abs(float(fb[x]["wave"])) for x in range(conf + 1)])
                w2 = float(fb[j]["wave"])
                cs = []
                for k, pk in pool[d]:
                    gap = j - k
                    if gap > COMMON["max_gap"] or gap < COMMON["min_gap"] or k < anchor[d] or (o["used"] and k in used[d]):
                        continue
                    if not ((px2 <= pk + tol) if d == 1 else (px2 >= pk - tol)):
                        continue
                    if o["f1"] == "flow_k1" or o["f1"] == "recent":
                        ws = [float(fb[x]["wave"]) for x in range(max(0, k - 1), min(conf, k + 1) + 1)]
                        w1 = min(ws) if d == 1 else max(ws)
                    else:
                        w1 = float(fb[k]["wave"])
                    if not d * (w2 - w1) > thr:
                        continue
                    cs.append((k, w1))
                f1 = None
                if cs:
                    if o["f1"] == "recent":
                        f1 = max(cs, key=lambda x: x[0])
                    else:
                        f1 = (min if d == 1 else max)(cs, key=lambda x: x[1])
                ok = f1 is not None
                ext = False
                if ok and o["rep"] and last[d] is not None:
                    lp, lk = last[d]
                    same = f1[0] == lk
                    t_ = 0.0 if same else tol
                    ok = px2 < lp + t_ if d == 1 else px2 > lp - t_
                    ext = ok and same
                if ok:
                    c = _cand("v3.2", d, j, f1[0], conf, fb, f1[1], w2, thr, a)
                    c["src"], c["ext"] = src, ext
                    used[d].add(f1[0])
                    if o["reset"]:
                        anchor[d] = j
                    lp = last[d][0] if last[d] is not None else px2
                    last[d] = ((min(lp, px2) if d == 1 else max(lp, px2)), f1[0])
                    out.append(c)
        if j not in seen[d]:
            seen[d].add(j)
            pool[d].append((j, px2))
            pool[d].sort()
    out.sort(key=lambda c: (c["conf"], c["j"]))
    return out


# ─────────────────────────────── especialistas (gatilho Opção C) ───────────────────────────────

def _trig_wall(fb, c, t, P):
    d, j, b, bj = c["dir"], c["j"], fb[t], fb[c["j"]]
    if c["c1"] is not None and (b["close"] > c["c1"] + P["buf"] if d == 1 else b["close"] < c["c1"] - P["buf"]) \
            and (TRIGGER == "orig" or d * (b["close"] - bj["close"]) > 0):   # (b): além do fechamento do pivô
        return "C1"
    if c["c2"] is not None and d * (b["close"] - c["c2"]) > 0 and d * (b["close"] - b["open"]) > 0 \
            and d * (b["close"] - bj["close"]) > 0:
        return "C2"
    return None


def _trig_day(fb, c, t, P):
    d, b, bj, e = c["dir"], fb[t], fb[c["j"]], c["day"]
    if e["viol"]:
        if d * (b["close"] - e["e"]) > 0 and d * (b["close"] - b["open"]) > 0 \
                and (TRIGGER == "orig" or d * (b["close"] - bj["close"]) > 0):   # (b)
            return "VIOL"
        return None
    if (b["close"] > bj["high"]) if d == 1 else (b["close"] < bj["low"]):
        return "DUPLO"
    return None


def triggers(fb, cands, P, n=None):
    """Gatilhos dos dois especialistas sobre os candidatos de um motor. Só usa barras < n."""
    n = len(fb) if n is None else n
    out, discard = [], []
    for c in cands:
        j = c["j"]
        lo, hi = max(j + 1, c["conf"]), j + COMMON["trig_max"]
        for esp, ok, fn in (("WALL", c["c1"] is not None or c["c2"] is not None, _trig_wall),
                            ("EXTREMO", c["day"] is not None, _trig_day)):
            if not ok:
                continue
            if lo > hi:
                discard.append(dict(esp=esp, engine=c["engine"], dir=c["dir"], j=j, conf=c["conf"]))
                continue
            for t in range(lo, min(hi, n - 1) + 1):
                sub = "NONE" if TRIGGER == "none" else fn(fb, c, t, P)   # "none" = controle sem Opção C
                if sub:
                    out.append(dict(engine=c["engine"], esp=esp, sub=sub, dir=c["dir"], j=j, k=c["k"],
                                    conf=c["conf"], idx=t, lag=t - j, time=fb[t]["time"], time_j=c["time_j"],
                                    micro=c["micro"]))
                    break
    out.sort(key=lambda x: (x["idx"], x["engine"], x["esp"], x["dir"]))
    # super-confluência (SPEC §1): F2 com as duas âncoras, conhecido na confirmação. `dup` = o outro especialista
    # já disparou para o mesmo candidato numa barra anterior (ou na mesma, com prioridade para WALL): na carteira
    # combinada essa entrada é descartada.
    first = {}
    for x in out:
        key = (x["engine"], x["dir"], x["j"])
        x["dup"] = key in first
        first.setdefault(key, x["esp"])
    by = {(c["engine"], c["dir"], c["j"]): c for c in cands}
    for x in out:
        c = by[(x["engine"], x["dir"], x["j"])]
        x["super"] = (c["c1"] is not None or c["c2"] is not None) and c["day"] is not None
    return out, discard


def run_day(asset: str, bars: List[dict], walls: List[dict], engines=ENGINES, require_micro=False, elig="common"):
    """Pipeline completo de um pregão (ou de bars[:t+1] no teste de paridade)."""
    P = PARAMS[asset]
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in LEVEL_TYPES)
    fb = compute_flow([dict(b) for b in bars], asset)
    atr = atr_series(fb, P["tick"])
    res = {}
    for e in engines:
        if e == "v3":
            cs = engine_v3(fb, levels, P, elig)
        elif e == "v2.1":
            cs = engine_v21(fb, levels, P, elig, atr=atr)
        elif e == "v2.2":
            cs = engine_v22(fb, levels, P, elig, atr=atr)
        elif e == "v3.2":
            cs = engine_v32(fb, levels, P, elig, atr=atr)
        else:
            cs = engine_v31(fb, levels, P, elig, require_micro=require_micro, atr=atr)
        tr, disc = triggers(fb, cs, P)
        res[e] = dict(cands=cs, trig=tr, discard=disc)
    return fb, res
