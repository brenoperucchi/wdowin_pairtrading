"""
Tabelas de fluxo dos 18 filtros dos setups a partir do `.min` do Profit (fonte única BT + ao vivo).

Substitui `mt5_tick_flow_tables_2026.pkl` (não reproduzível, só filtros 1–11) e o fallback por JSON de sessão
(que misturava `.trd` e `.min`). Cada dia: M5 da decomposição `.min` → `_session_features` → `_bar_masks`.

Saída: data/research/setup_flow_min_v1/flow_masks.pkl  +  research/setup_parity/flow_min_manifest.json (sha256)
Uso: python -m research.setup_parity.build_flow_min
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.profit_wall_players_engine import _build_from_profit_min_m1_m5, _load_profit_min_index  # noqa: E402
from research.flow_window_asg.flow_filters import FILTER_NAMES, _bar_masks, _session_features  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "research", "setup_flow_min_v1")
OUT_PKL = os.path.join(OUT_DIR, "flow_masks.pkl")
MANIFEST = os.path.join(ROOT, "research", "setup_parity", "flow_min_manifest.json")
START, END = "2025-12-01", "2026-11-11"


def session_masks(asset: str, date: str, rec: dict) -> dict:
    """{(date, t_min): {filtro: (compra_ok, venda_ok)}} de um dia — mesma função usada ao vivo."""
    is_win = asset == "WIN"
    pay = _build_from_profit_min_m1_m5(rec, asset, date, [], 60.0 if is_win else 2.5, 5.0 if is_win else 0.5)
    series = (pay or {}).get("m5_cvd_series", [])
    out = {}
    for f in _session_features(series, is_win=is_win):
        out[(date, f["t_min"])] = _bar_masks(f, is_win=is_win)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    flow = {a: {fn: {} for fn in FILTER_NAMES[1:]} for a in ("WIN", "WDO")}
    days = {}
    for asset in ("WIN", "WDO"):
        idx = _load_profit_min_index(asset)
        ds = [d for d in sorted(idx) if START <= d <= END]
        for d in ds:
            for key, masks in session_masks(asset, d, idx[d]).items():
                for fn, ok in masks.items():
                    if fn in flow[asset]:
                        flow[asset][fn][key] = ok
        days[asset] = ds
        print(f"{asset}: {len(ds)} dias")
    missing = {a: [fn for fn in FILTER_NAMES[1:] if not flow[a][fn]] for a in flow}
    if any(missing.values()):
        raise RuntimeError(f"filtros sem dado: {missing}")
    with open(OUT_PKL, "wb") as f:
        pickle.dump({"flow": flow, "days": days}, f)
    h = hashlib.sha256(open(OUT_PKL, "rb").read()).hexdigest()
    json.dump({"built_at": datetime.now().isoformat(timespec="seconds"), "source": "Profit .min M1+M5",
               "range": [START, END], "days": {a: len(v) for a, v in days.items()},
               "filters": FILTER_NAMES[1:], "sha256": h}, open(MANIFEST, "w", encoding="utf-8"), indent=1)
    print("ok", h[:12])


if __name__ == "__main__":
    main()
