"""
Gate de divergência F1→F2 / T1→T2 na Wall — fonte única para BT e ao vivo (research/div_gate/PLANO.md).

Estado por barra M5 fechada t (chave (data, minuto da abertura da barra), mesma convenção dos filtros de fluxo):
  bit 2n   = divergência de COMPRA confirmada em alguma barra de [t−N+1, t]   (N = JANELAS[n])
  bit 2n+1 = divergência de VENDA  confirmada em alguma barra de [t−N+1, t]
Detector v2: `core.div_wall_signal.detect_divergences_v2` (definição revisada em 11/11: F1 = qualquer fundo
anterior do pregão com a onda mais extrema, sem limite de extensão; Wall "perto" (raio R) ou "furou e voltou";
confirmação PIVO ou FECHA_WALL), NWE "extreme" (F2 na metade externa da banda) com período L, bw 8, mult 3.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
from functools import lru_cache
from typing import Dict, Tuple

import numpy as np

from core.div_wall_signal import DivParamsV2, compute_flow, detect_divergences_v2, nwe_series

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "data", "research", "div_gate_v2")
MANIFEST = os.path.join(ROOT, "research", "div_gate", "gate_manifest.json")

JANELAS = (3, 6, 12)
WAVE_K = (0.5, 1.0, 1.5)
RADIUS = {"WIN": (40.0, 100.0), "WDO": (1.5, 4.0)}
NWE_L = (30, 50, 80, 100)
CONFIRM = ("PIVO", "FECHA_WALL")
NWE_BW, NWE_MULT, WARM_BARS = 8.0, 3.0, 200


def cfgs(asset):
    return [(k, r, L, c) for k in WAVE_K for r in RADIUS[asset] for L in NWE_L for c in CONFIRM]


def nwe_day(warm, closes, L):
    allc = np.concatenate([np.asarray(warm, float)[-WARM_BARS:], np.asarray(closes, float)])
    c, u, l = nwe_series(allc, lookback=L, bw=NWE_BW, mult=NWE_MULT)
    k = len(allc) - len(closes)
    return c[k:], u[k:], l[k:]


def params(asset, k, r, conf):
    return DivParamsV2.default(asset, wave_k=k, wall_radius=r, confirm=conf, nwe_filter="extreme")


def day_bits(asset, bars, walls, warm, k, r, L, conf):
    """Bits do gate para cada barra do dia (lista de int), usando só barras <= t em cada t."""
    fb = compute_flow(bars, asset)
    nwe = nwe_day(warm, [b["close"] for b in bars], L)
    sigs = detect_divergences_v2(fb, walls, nwe, params(asset, k, r, conf))
    n = len(bars)
    bull = np.zeros(n, bool)
    bear = np.zeros(n, bool)
    for s in sigs:
        (bull if s.direction == 1 else bear)[s.idx] = True
    out = np.zeros(n, np.int16)
    for ni, N in enumerate(JANELAS):
        for t in range(n):
            lo = max(0, t - N + 1)
            if bull[lo:t + 1].any():
                out[t] |= 1 << (2 * ni)
            if bear[lo:t + 1].any():
                out[t] |= 1 << (2 * ni + 1)
    return out.tolist()


def tmin(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


@lru_cache(maxsize=2)
def load_table(asset: str) -> Tuple[Dict, frozenset]:
    """{cfg: {(data, tmin): bits}}, dias cobertos. Falha se o hash não bater com o manifesto."""
    p = os.path.join(OUT_DIR, f"{asset}_gate.pkl")
    man = json.load(open(MANIFEST, encoding="utf-8"))
    if _sha(p) != man["assets"][asset]["sha256"]:
        raise RuntimeError(f"Tabela do gate {asset} diverge do manifesto — rode build_gate.py")
    tab = pickle.load(open(p, "rb"))
    return tab, frozenset(man["assets"][asset]["days"])


def make_gate(asset, cfg, N, mode, inverted=False):
    """f(date, tmin, dir) -> bool. Barra sem estado (dia não coberto) BLOQUEIA."""
    tab, _ = load_table(asset)
    t = tab[cfg]
    ni = JANELAS.index(N)
    b_bull, b_bear = 1 << (2 * ni), 1 << (2 * ni + 1)

    def f(date, tm, d):
        bits = t.get((str(date), int(tm)))
        if bits is None:
            return False
        dd = -d if inverted else d
        same = bool(bits & (b_bull if dd == 1 else b_bear))
        opp = bool(bits & (b_bear if dd == 1 else b_bull))
        return same if mode == "EXIGIR" else not opp
    return f


def coverage_filter(asset):
    _, days = load_table(asset)
    return lambda date, tm, d: str(date) in days
