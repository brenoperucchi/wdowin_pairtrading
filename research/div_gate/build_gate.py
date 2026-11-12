"""
Fase 0: gera as tabelas do gate (24 configs por ativo × 3 janelas) a partir do dataset congelado `div_wall_v1`
(`.min` do Profit + Walls reais B3) e roda o teste de causalidade.
Uso: python -m research.div_gate.build_gate [--test-only]
"""
from __future__ import annotations

import json
import os
import pickle
import random
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from research.div_gate import gate as G  # noqa: E402
from research.div_wall.build_dataset import load_contract_m5  # noqa: E402
from research.div_wall.data import DATA_DIRS, load_asset  # noqa: E402


def days_with_warm(asset):
    data = load_asset(asset, "M5")
    df = pd.read_parquet(os.path.join(DATA_DIRS["M5"], f"{asset}_bars.parquet"), columns=["date", "contract"])
    contract = df.drop_duplicates("date").set_index("date")["contract"].to_dict()
    cm5 = load_contract_m5(asset)
    out = {}
    for d, (bars, walls, nwe100) in data.items():
        cdf = cm5.get(contract[d])
        warm = cdf[cdf["date"] < d]["close"].values[-G.WARM_BARS:] if cdf is not None else np.array([])
        out[d] = (bars, walls, warm, nwe100)
    return out


def build(asset, days):
    tab = {}
    for cfg in G.cfgs(asset):
        k, r, L, conf = cfg
        t = {}
        for d, (bars, walls, warm, _) in days.items():
            bits = G.day_bits(asset, bars, walls, warm, k, r, L, conf)
            for b, v in zip(bars, bits):
                t[(d, G.tmin(b["time"]))] = v
        tab[cfg] = t
        n = len(t)
        print(f"{asset} cfg k={k} R={r} L={L} {conf}: {n} barras · compra ativa(N=6) "
              f"{sum(1 for v in t.values() if v & 4) / n:.1%} · venda {sum(1 for v in t.values() if v & 8) / n:.1%}",
              flush=True)
    return tab


def check_nwe(asset, days):
    """NWE L=100 recalculada aqui tem que bater com a gravada no dataset (mesmo aquecimento)."""
    bad = 0
    for d, (bars, _, warm, nwe100) in days.items():
        c, _, _ = G.nwe_day(warm, [b["close"] for b in bars], 100)
        if np.max(np.abs(c - nwe100[0])) > 1e-6:
            bad += 1
    print(f"{asset}: NWE 100 recalculada ≠ dataset em {bad} dias")
    return bad == 0


def causal_test(asset, days, tab, n_days=8, seed=7):
    """Recalcula o gate com os dados CORTADOS na barra t (só barras <= t) e compara com a tabela inteira."""
    rnd = random.Random(seed)
    ds = sorted(rnd.sample(sorted(days), n_days))
    cfg_list = rnd.sample(G.cfgs(asset), 6)
    errs = checks = 0
    for d in ds:
        bars, walls, warm, _ = days[d]
        for cfg in cfg_list:
            k, r, L, conf = cfg
            for t in range(5, len(bars), 3):
                bits_cut = G.day_bits(asset, bars[:t + 1], walls, warm, k, r, L, conf)[-1]
                checks += 1
                if bits_cut != tab[cfg][(d, G.tmin(bars[t]["time"]))]:
                    errs += 1
    print(f"{asset}: teste causal {checks} cortes ({n_days} dias × 6 configs) → {errs} diferenças")
    return errs == 0


def main(test_only=False):
    os.makedirs(G.OUT_DIR, exist_ok=True)
    man = {"version": "div_gate_v2", "built_at": datetime.now().isoformat(timespec="seconds"),
           "source": "div_wall_v1 (.min Profit + Walls B3) · detector core/div_wall_signal.py",
           "janelas": list(G.JANELAS), "wave_k": list(G.WAVE_K), "radius": G.RADIUS, "nwe_l": list(G.NWE_L),
           "nwe_bw": G.NWE_BW, "nwe_mult": G.NWE_MULT, "nwe_filter": "extreme", "confirm": list(G.CONFIRM),
           "detector": "detect_divergences_v2", "assets": {}}
    ok = True
    for asset in ("WIN", "WDO"):
        days = days_with_warm(asset)
        ok &= check_nwe(asset, days)
        p = os.path.join(G.OUT_DIR, f"{asset}_gate.pkl")
        if test_only:
            tab = pickle.load(open(p, "rb"))
        else:
            tab = build(asset, days)
            pickle.dump(tab, open(p, "wb"), protocol=4)
        man["assets"][asset] = {"days": sorted(days), "n_days": len(days), "sha256": G._sha(p)}
        ok &= causal_test(asset, days, tab)
    if not test_only:
        json.dump(man, open(G.MANIFEST, "w", encoding="utf-8"), indent=1)
    print("FASE 0:", "OK" if ok else "FALHOU")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main("--test-only" in sys.argv) else 1)
