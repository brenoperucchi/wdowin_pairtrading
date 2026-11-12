"""Carregamento do dataset congelado div_wall_v1 com verificação de hash."""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIRS = {"M5": os.path.join(ROOT, "data", "research", "div_wall_v1"),
             "M1": os.path.join(ROOT, "data", "research", "div_wall_m1_v1")}
MANIFESTS = {"M5": os.path.join(ROOT, "research", "div_wall", "dataset_manifest.json"),
             "M1": os.path.join(ROOT, "research", "div_wall", "dataset_manifest_m1.json")}

IS_END = "2026-07-31"     # In-sample: jan–jul (otimização)
OOS_START = "2026-08-01"  # Out-of-sample: ago–nov (trancado; só roda via run_oos.py)

BAR_COLS = ["time", "open", "high", "low", "close", "buy_vol", "sell_vol", "avg_buy_lot", "avg_sell_lot",
            "inst_aggr_delta", "inst_pass_delta", "ret_delta_bar"]


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


@lru_cache(maxsize=4)
def load_asset(asset: str, tf: str = "M5"):
    """Retorna {date: (bars:list[dict], walls:list[dict], nwe:(c,u,l))}. Falha se o hash não bater."""
    man = json.load(open(MANIFESTS[tf], encoding="utf-8"))["assets"][asset]["sha256"]
    p_bars = os.path.join(DATA_DIRS[tf], f"{asset}_bars.parquet")
    p_walls = os.path.join(DATA_DIRS[tf], f"{asset}_walls.json")
    if _sha(p_bars) != man["bars"] or _sha(p_walls) != man["walls"]:
        raise RuntimeError(f"Dataset {asset} diverge do manifest — rode build_dataset.py e versione o manifest.")
    df = pd.read_parquet(p_bars)
    walls = json.load(open(p_walls, encoding="utf-8"))
    out = {}
    for d, g in df.groupby("date", sort=True):
        if d not in walls or not walls[d]:
            raise RuntimeError(f"{asset} {d}: sem walls — dia não pode entrar no BT.")
        bars = g[BAR_COLS].to_dict("records")
        nwe = (g["nwe_c"].to_numpy(), g["nwe_u"].to_numpy(), g["nwe_l"].to_numpy())
        out[d] = (bars, walls[d], nwe)
    return out


def split(data: dict, part: str) -> dict:
    if part == "IS":
        return {d: v for d, v in data.items() if d <= IS_END}
    if part == "OOS":
        return {d: v for d, v in data.items() if d >= OOS_START}
    return dict(data)


def metrics(trades: list, asset: str) -> dict:
    """Métricas em 1 contrato, curva de capital por ordem de saída."""
    closed = [t for t in trades if t.exit_reason not in ("OPEN",)]
    if not closed:
        return {"trades": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "mdd": 0.0, "ret_dd": 0.0,
                "pos_months": 0, "months": 0, "avg": 0.0, "days": 0}
    closed = sorted(closed, key=lambda t: (t.date, t.exit_time, t.entry_time))
    pnl = np.array([t.brl for t in closed])
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    mdd = float(np.max(peak - eq)) if len(eq) else 0.0
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    by_m = {}
    for t in closed:
        by_m[t.date[:7]] = by_m.get(t.date[:7], 0.0) + t.brl
    net = float(eq[-1])
    return {
        "trades": len(closed), "wr": round(100.0 * float((pnl > 0).mean()), 1),
        "pf": round(float(gains / losses), 2) if losses > 0 else 99.0,
        "net": round(net, 2), "mdd": round(mdd, 2), "ret_dd": round(net / mdd, 2) if mdd > 0 else 99.0,
        "pos_months": sum(1 for v in by_m.values() if v > 0), "months": len(by_m),
        "avg": round(float(pnl.mean()), 2), "days": len({t.date for t in closed}),
    }
