"""
Congela o dataset M1 (`data/research/div_wall_m1_v1/`): barras de 1 minuto do `.min` do Profit com a
mesma decomposição de fluxo do motor (`core/profit_min_decomp.py`), walls reais do dia e
NWE 100/8/3 calculada sobre o M1, aquecida com os minutos anteriores do MESMO contrato.
Também grava a NWE 100/8/3 do M5 (barra M5 anterior já fechada) como contexto opcional.

Uso: python -m research.div_wall.build_dataset_m1
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.div_wall_signal import nwe_for_session  # noqa: E402
from core.profit_min_decomp import decompose_min_bars  # noqa: E402
from core.profit_mt5_flow_engine import load_daily_magic_walls  # noqa: E402
from core.profit_wall_players_engine import _load_profit_min_index  # noqa: E402
from research.div_wall.build_dataset import END, START, WALL_TYPES, load_contract_m5, sha256  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "research", "div_wall_m1_v1")
COLS = ["open", "high", "low", "close", "buy_vol", "sell_vol", "avg_buy_lot", "avg_sell_lot",
        "inst_aggr_delta", "inst_pass_delta", "ret_delta_bar"]


def _match_contract(c_m1, d, bars):
    """Contrato cujo arquivo M1 tem exatamente os mesmos fechamentos do dia (o rótulo do índice vem do M5)."""
    want = [round(b["close"], 2) for b in bars[:30]]
    for name, df in c_m1.items():
        got = df[df["date"] == d]["close"].round(2).tolist()[:30]
        if got and got == want:
            return name
    return None


def build_asset(asset):
    idx = _load_profit_min_index(asset)
    c_m1 = load_contract_m5(asset, tag="_1_1_1_1_0_", bucket=60)
    rows, walls_out, meta = [], {}, []
    for d in sorted(x for x in idx if START <= x <= END):
        rec = idx[d]
        if rec["m1"] is None:
            meta.append({"date": d, "skipped": "sem M1"})
            continue
        walls = [{"type": w["type"], "price": float(w["price"])} for w in load_daily_magic_walls(asset, d)
                 if w.get("type") in WALL_TYPES]
        if not any(w["type"] == "Wall" for w in walls):
            meta.append({"date": d, "skipped": "sem walls reais"})
            continue
        bars = decompose_min_bars(rec["m1"], asset, d)
        if len(bars) < 500:
            meta.append({"date": d, "skipped": f"sessao incompleta ({len(bars)} min)"})
            continue
        contract = _match_contract(c_m1, d, bars) or rec["contract"]
        cdf = c_m1.get(contract)
        warm = cdf[cdf["date"] < d]["close"].values[-200:] if cdf is not None else np.array([])
        closes = [b["close"] for b in bars]
        c, u, l = nwe_for_session(warm, closes)
        for i, b in enumerate(bars):
            r = {"date": d, "contract": contract, "time": b["time"]}
            r.update({k: b[k] for k in COLS})
            r.update({"nwe_c": float(c[i]), "nwe_u": float(u[i]), "nwe_l": float(l[i])})
            rows.append(r)
        walls_out[d] = walls
        meta.append({"date": d, "contract": contract, "bars": len(bars), "warmup_bars": int(len(warm))})
    return pd.DataFrame(rows), walls_out, meta


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    man = {"version": "div_wall_m1_v1", "built_at": datetime.now().isoformat(timespec="seconds"),
           "source": "Profit .min M1 + core/profit_min_decomp.py + jumba_gex_*_history.csv",
           "nwe": {"lookback": 100, "bw": 8.0, "mult": 3.0, "tf": "M1"}, "range": [START, END], "assets": {}}
    for asset in ("WIN", "WDO"):
        df, walls, meta = build_asset(asset)
        pb, pw = os.path.join(OUT_DIR, f"{asset}_bars.parquet"), os.path.join(OUT_DIR, f"{asset}_walls.json")
        df.to_parquet(pb, index=False)
        json.dump(walls, open(pw, "w", encoding="utf-8"))
        ok = [m for m in meta if "skipped" not in m]
        man["assets"][asset] = {"days": len(ok), "rows": len(df), "skipped": [m for m in meta if "skipped" in m],
                                "low_warmup_days": [m["date"] for m in ok if m["warmup_bars"] < 100],
                                "sha256": {"bars": sha256(pb), "walls": sha256(pw)}, "days_meta": ok}
        print(f"{asset}: {len(ok)} dias, {len(df)} minutos, pulados {len(meta) - len(ok)}")
    for p in (os.path.join(OUT_DIR, "manifest.json"), os.path.join(ROOT, "research", "div_wall", "dataset_manifest_m1.json")):
        json.dump(man, open(p, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
