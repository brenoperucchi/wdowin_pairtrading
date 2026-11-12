# -*- coding: utf-8 -*-
"""
Motor de divergencia v2.1 (pesquisa, WIN M5, preco x Fluxo Smart Money).

Regra (causal, sem barra do futuro):
  1. Pivo evidente = extremo de um zigzag com reversao de 1,2 x ATR(14) causal.
     O pivo so e conhecido no fechamento da barra que confirma a reversao.
  2. F2 so entra se for nova maxima (venda) / nova minima (compra) do pregao
     ate aquela barra, OU estiver a <= 150 pts de uma Wall ou MidWall.
  3. F1 = pivo zigzag anterior do mesmo lado, no maximo 48 barras (~4 h),
     com estrutura de preco (F2 nao muito pior que F1, tolerancia 60 pts) e
     onda que NAO confirma o movimento (divergencia > 0,15 x mediana causal |onda|).
  4. Cada pivo e F1 de no maximo um candidato (sem leque).

Parametros poucos e interpretaveis; valores default escolhidos no conjunto de
treino (6 pregoes) e reportados no hold-out e em leave-one-session-out.
Nao depende de core/ nem do motor ao vivo.
"""
from __future__ import annotations

import statistics

DEFAULTS = dict(
    r_atr=1.2,
    wave_k=0.15,
    max_gap=48,
    min_gap=2,
    price_tol=60.0,
    zone=150.0,
)


def atr14(bars, i):
    """ATR de Wilder (14), causal, so com barras 1..i."""
    trs = []
    for j in range(1, i + 1):
        tr = max(
            bars[j]["high"] - bars[j]["low"],
            abs(bars[j]["high"] - bars[j - 1]["close"]),
            abs(bars[j]["low"] - bars[j - 1]["close"]),
        )
        trs.append(tr)
    if not trs:
        return max(bars[0]["high"] - bars[0]["low"], 5.0)
    atr = sum(trs[:14]) / len(trs[:14])
    for tr in trs[14:]:
        atr = (atr * 13 + tr) / 14
    return max(atr, 5.0)


def is_new_extreme(bars, idx, side):
    """side=1 minima, side=-1 maxima. Causal: barras 0..idx. Comparacao estrita."""
    if idx < 0 or idx >= len(bars):
        return False
    if side == 1:
        px = bars[idx]["low"]
        return idx == 0 or px < min(b["low"] for b in bars[:idx])
    px = bars[idx]["high"]
    return idx == 0 or px > max(b["high"] for b in bars[:idx])


def nearest_wall(px, walls):
    if not walls:
        return None, None
    w = min(walls, key=lambda x: abs(x["price"] - px))
    return w, px - w["price"]


def zigzag(bars, r_atr=1.2):
    """Pivos de zigzag confirmados na barra da reversao. side=1 fundo, -1 topo."""
    n = len(bars)
    if n < 3:
        return []
    peak_i, peak = 0, bars[0]["high"]
    trough_i, trough = 0, bars[0]["low"]
    direction = 0
    pivots = []
    for i in range(1, n):
        R = max(r_atr * atr14(bars, i), 80.0)
        h, l = bars[i]["high"], bars[i]["low"]
        if direction == 0:
            if h > peak:
                peak, peak_i = h, i
            if l < trough:
                trough, trough_i = l, i
            if peak - trough >= R:
                if peak_i > trough_i:
                    pivots.append(dict(idx=trough_i, side=1, px=trough, confirm=i, r=R))
                    direction = 1
                elif trough_i > peak_i:
                    pivots.append(dict(idx=peak_i, side=-1, px=peak, confirm=i, r=R))
                    direction = -1
            continue
        if direction == 1:
            if h >= peak:
                peak, peak_i = h, i
            if l <= peak - R:
                pivots.append(dict(idx=peak_i, side=-1, px=peak, confirm=i, r=R))
                direction = -1
                trough, trough_i = l, i
        else:
            if l <= trough:
                trough, trough_i = l, i
            if h >= trough + R:
                pivots.append(dict(idx=trough_i, side=1, px=trough, confirm=i, r=R))
                direction = 1
                peak, peak_i = h, i
    return pivots


def detect(bars, wave, walls, params=None):
    """Devolve candidatos de divergencia (lista de dicts) e os pivos do zigzag."""
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    zone, max_gap, min_gap = p["zone"], p["max_gap"], p["min_gap"]
    price_tol, wave_k = p["price_tol"], p["wave_k"]
    piv = zigzag(bars, p["r_atr"])
    out = []
    used_f1 = {1: set(), -1: set()}
    last_same = {1: [], -1: []}
    for pv in piv:
        i, side = pv["idx"], pv["side"]
        absw = [abs(wave[j]) for j in range(0, pv["confirm"] + 1)]
        thr = wave_k * (statistics.median(absw) if absw else 1.0)
        wall, dist = nearest_wall(pv["px"], walls)
        near = dist is not None and abs(dist) <= zone
        day = is_new_extreme(bars, i, side)
        if not (near or day):
            last_same[side].append(pv)
            continue
        f1 = None
        for q in reversed(last_same[side]):
            gap = i - q["idx"]
            if gap > max_gap:
                break
            if gap < min_gap or q["idx"] in used_f1[side]:
                continue
            price_ok = (pv["px"] <= q["px"] + price_tol) if side == 1 else (pv["px"] >= q["px"] - price_tol)
            if not price_ok:
                continue
            wd = (wave[i] - wave[q["idx"]]) if side == 1 else (wave[q["idx"]] - wave[i])
            if wd <= thr:
                continue
            f1 = q
            break
        if f1 is None:
            last_same[side].append(pv)
            continue
        used_f1[side].add(f1["idx"])
        out.append({
            "dir": side,
            "kind": "DIV",
            "f1_idx": f1["idx"],
            "f2_idx": i,
            "sig_idx": pv["confirm"],
            "f1_time": bars[f1["idx"]]["time"],
            "f2_time": bars[i]["time"],
            "sig_time": bars[pv["confirm"]]["time"],
            "f1_price": f1["px"],
            "f2_price": pv["px"],
            "wall_price": wall["price"] if wall else None,
            "wall_type": wall["type"] if wall else None,
            "wall_dist": None if dist is None else round(dist, 1),
            "day_ext": day,
            "near_wall": near,
            "wave_div": (wave[i] - wave[f1["idx"]]) if side == 1 else (wave[f1["idx"]] - wave[i]),
        })
        last_same[side].append(pv)
    return out, piv
