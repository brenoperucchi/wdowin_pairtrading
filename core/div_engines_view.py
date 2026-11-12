"""
Divergências dos motores V2.1 e V3.1 para visualização no painel 5176, independente dos trades.

Roda os MESMOS motores da pesquisa (`research/div_master/especialistas/modulo.py`, causais e com teste de paridade)
sobre as barras M5 que o painel já está mostrando (OHLC + `smart_swing_wave`) e as Walls/MidWalls do dia.
Não altera nenhuma estratégia, sinal ou trade: só devolve os pares F1→F2 / T1→T2 para desenhar.

Elegibilidade = a mesma dos especialistas: F2 a ≤ 150 pts (WIN) / 3,5 pts (WDO) de Wall/MidWall, furo de até
220 / 6,0, ou extremo do dia depois das 09:30. Cada divergência é conhecida na barra de confirmação (`conf`).
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List

_ESP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "div_master", "especialistas")
if _ESP not in sys.path:
    sys.path.insert(0, _ESP)

import modulo as _M  # noqa: E402

ENGINES = ("v2.1", "v2.2", "v3.1", "v3.2")   # v2.2 = v2.1 + abertura (V22_ABERTURA) · v3.2 = F1 no fluxo extremo, 1 por perna, sem abertura (motor da carteira)


def _anchor_label(c: dict) -> str:
    wall = c["c1"] is not None or c["c2"] is not None
    day = c["day"] is not None
    if wall and day:
        return "WALL + EXTREMO"
    if wall:
        return "WALL (furo)" if c["c1"] is not None else "WALL"
    return "EXTREMO DO DIA"


def sniper_divs(asset: str, bars: List[dict]) -> List[tuple]:
    """Divergências do motor da carteira 5176 — v3.2 sem módulo de abertura (V32_PROD, desde 12/11/2026) — para o
    filtro do Sniper: (barra de confirmação, direção), sem exigir âncora e com todas as extensões — a mesma
    configuração do backtest (frente1/motores.py: conf · sem âncora · janela 2)."""
    fb = [dict(time=str(b["time"])[:5], open=float(b["open"]), high=float(b["high"]), low=float(b["low"]),
               close=float(b["close"]), wave=float(b.get("wave", b.get("smart_swing_wave", 0.0)) or 0.0)) for b in bars]
    if len(fb) < 5:
        return []
    P = _M.PARAMS[asset]
    cands = _M.engine_v32(fb, [], P, "all", atr=_M.atr_series(fb, P["tick"]), opt=_M.V32_PROD)
    return [(int(c["conf"]), int(c["dir"])) for c in cands]


def detect(asset: str, bars: List[dict], walls: List[dict], engine: str) -> List[Dict]:
    """bars: [{time, open, high, low, close, wave}] só do pregão (sem barras do dia anterior), em ordem.
    walls: [{type, price}]. Retorna as divergências do motor com horários, preços, onda e âncora."""
    if asset not in _M.PARAMS:
        raise ValueError(f"ativo inválido: {asset}")
    if engine not in ENGINES:
        raise ValueError(f"motor inválido: {engine}")
    fb = []
    for b in bars:
        fb.append(dict(time=str(b["time"])[:5], open=float(b["open"]), high=float(b["high"]), low=float(b["low"]),
                       close=float(b["close"]), wave=float(b.get("wave", b.get("smart_swing_wave", 0.0)) or 0.0)))
    if len(fb) < 5:
        return []
    P = _M.PARAMS[asset]
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in _M.LEVEL_TYPES and w.get("price") is not None)
    atr = _M.atr_series(fb, P["tick"])
    if engine == "v2.1":
        cands = _M.engine_v21(fb, levels, P, "common", atr=atr)
    elif engine == "v2.2":
        cands = _M.engine_v22(fb, levels, P, "common", atr=atr, opt=_M.V22_ABERTURA)
    elif engine == "v3.2":
        # Uma divergência por perna: das extensões do mesmo F1 (mesma direção) fica só a mais recente.
        # Isso é só de exibição — ao vivo, a linha se estende quando o preço faz um extremo novo.
        # Variante da carteira 5176 (sem módulo de abertura) — o mesmo motor que gera os trades.
        allc = _M.engine_v32(fb, levels, P, "common", atr=atr, opt=_M.V32_PROD)
        last = {}
        for c in allc:
            last[(c["dir"], c["k"])] = c
        cands = sorted(last.values(), key=lambda c: c["conf"])
    else:
        cands = _M.engine_v31(fb, levels, P, "common", require_micro=False, atr=atr)
    trig, _ = _M.triggers(fb, cands, P)
    first_trig = {}
    for x in trig:
        key = (x["dir"], x["j"])
        if key not in first_trig or x["idx"] < first_trig[key]["idx"]:
            first_trig[key] = x
    out = []
    for c in cands:
        t = first_trig.get((c["dir"], c["j"]))
        out.append(dict(
            dir=int(c["dir"]),
            f1_time=fb[c["k"]]["time"], f1_px=float(c["px1"]), f1_wave=float(fb[c["k"]]["wave"]),
            f1_wave_ref=float(c["w1"]),
            f2_time=fb[c["j"]]["time"], f2_px=float(c["px2"]), f2_wave=float(c["w2"]),
            conf_time=fb[c["conf"]]["time"],
            anchor=_anchor_label(c),
            wall_px=c["c1"] if c["c1"] is not None else c["c2"],
            day_extreme=(c["day"] or {}).get("e"),
            wave_div=round(float(c["wd"]), 0), wave_thr=round(float(c["thr"]), 0),
            trigger_time=fb[t["idx"]]["time"] if t else None,
            trigger_kind=(f"{t['esp']} {t['sub']}" if t else None),
            src=c.get("src"),
        ))
    out.sort(key=lambda d: (d["conf_time"], d["f2_time"]))
    return out
