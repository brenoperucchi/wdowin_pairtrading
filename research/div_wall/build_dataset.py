"""
Congela o dataset do BT de Divergência na Wall (`data/research/div_wall_v1/`).

Fonte única (decisão de 10/11/2026): decomposição `.min` M1+M5 do Profit em TODOS os dias
(mesma usada pelo ao vivo), nunca o `.trd`. Walls reais do pipeline GEX (`jumba_gex_*_history.csv`).
NWE 100/8/3 aquecida com as barras anteriores do MESMO contrato (sem back-adjust).

Uso:  python -m research.div_wall.build_dataset
Saída: {asset}_bars.parquet, {asset}_walls.json, manifest.json (com sha256), e uma cópia do
manifest em research/div_wall/dataset_manifest.json (versionada no git).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.profit_statarb_engine import PROFIT_ASSET_DIRS  # noqa: E402
from core.profit_wall_players_engine import (  # noqa: E402
    MIN_FULL_DTYPE,
    _build_from_profit_min_m1_m5,
    _load_profit_min_index,
)
from core.profit_mt5_flow_engine import load_daily_magic_walls  # noqa: E402
from core.div_wall_signal import nwe_for_session  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "research", "div_wall_v1")
START, END = "2026-01-02", "2026-11-09"   # 10/11 é o pregão corrente (incompleto)
KEEP_COLS = ["open", "high", "low", "close", "buy_vol", "sell_vol", "avg_buy_lot", "avg_sell_lot",
             "inst_aggr_delta", "inst_pass_delta", "ret_delta_bar"]
WALL_TYPES = ("Wall", "MidWall", "GammaFlip", "MaxGamma", "MinGamma")


def load_contract_m5(asset: str, tag: str = "_1_5_1_1_0_", bucket: int = 300) -> dict:
    """{contrato: DataFrame(ts, date, close)} das barras regulares (M5 por padrão; M1 com tag `_1_1_1_1_0_`)."""
    pref = "WIN" if asset == "WIN" else "WDO"
    out = {}
    for base in PROFIT_ASSET_DIRS:
        if not os.path.exists(base):
            continue
        for folder in sorted(os.listdir(base)):
            if not folder.startswith(pref):
                continue
            fp_dir = os.path.join(base, folder)
            if not os.path.isdir(fp_dir):
                continue
            contract = folder.split("_")[0]
            for fname in os.listdir(fp_dir):
                if not (fname.endswith(".min") and tag in fname):
                    continue
                fpath = os.path.join(fp_dir, fname)
                n = os.path.getsize(fpath) // 128
                if n <= 0:
                    continue
                arr = np.fromfile(fpath, dtype=MIN_FULL_DTYPE, count=n)
                arr = arr[(arr["dt"] >= 45900.0) & (arr["dt"] < 47500.0) & (arr["close"] > 0)]
                ts = np.round((arr["dt"] - 25569.0) * 86400.0).astype(np.int64)
                ts = (((ts + 30) // 60) * 60 // bucket) * bucket
                dts = pd.to_datetime(ts, unit="s", utc=True)
                mins = dts.hour * 60 + dts.minute
                df = pd.DataFrame({"ts": ts, "date": dts.strftime("%Y-%m-%d"), "close": arr["close"]})
                df = df[(mins >= 540) & (mins <= 1105)]
                prev = out.get(contract)
                if prev is None or len(df) > len(prev):
                    out[contract] = df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    return out


def build_asset(asset: str):
    is_win = asset == "WIN"
    idx = _load_profit_min_index(asset)
    cm5 = load_contract_m5(asset)
    rows, walls_out, days_meta = [], {}, []
    for d in sorted(x for x in idx if START <= x <= END):
        rec = idx[d]
        walls = load_daily_magic_walls(asset, d)
        walls = [{"type": w["type"], "price": float(w["price"])} for w in walls if w.get("type") in WALL_TYPES]
        if not any(w["type"] == "Wall" for w in walls):
            days_meta.append({"date": d, "skipped": "sem walls reais"})
            continue
        pay = _build_from_profit_min_m1_m5(rec, asset, d, walls, 60.0 if is_win else 2.5, 5.0 if is_win else 0.5)
        bars = (pay or {}).get("m5_cvd_series", [])
        if len(bars) < 100:
            days_meta.append({"date": d, "skipped": f"sessao incompleta ({len(bars)} barras)"})
            continue
        contract = rec["contract"]
        cdf = cm5.get(contract)
        warm = cdf[cdf["date"] < d]["close"].values[-200:] if cdf is not None else np.array([])
        closes = [float(b["close"]) for b in bars]
        c, u, l = nwe_for_session(warm, closes)
        for i, b in enumerate(bars):
            r = {"date": d, "contract": contract,
                 "time": datetime.fromtimestamp(int(b["time"]), tz=timezone.utc).strftime("%H:%M")}
            r.update({k: float(b.get(k, 0.0)) for k in KEEP_COLS})
            r.update({"nwe_c": float(c[i]), "nwe_u": float(u[i]), "nwe_l": float(l[i])})
            rows.append(r)
        walls_out[d] = walls
        days_meta.append({"date": d, "contract": contract, "bars": len(bars), "walls": len(walls),
                          "warmup_bars": int(len(warm)), "m5_indiv": bool(rec["is_indiv_m5"])})
    df = pd.DataFrame(rows)
    return df, walls_out, days_meta


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {"version": "div_wall_v1", "built_at": datetime.now().isoformat(timespec="seconds"),
                "source": "Profit .min M1+M5 decomposition (sem .trd) + jumba_gex_*_history.csv",
                "nwe": {"lookback": 100, "bw": 8.0, "mult": 3.0}, "range": [START, END], "assets": {}}
    for asset in ("WIN", "WDO"):
        df, walls, meta = build_asset(asset)
        p_bars = os.path.join(OUT_DIR, f"{asset}_bars.parquet")
        p_walls = os.path.join(OUT_DIR, f"{asset}_walls.json")
        df.to_parquet(p_bars, index=False)
        with open(p_walls, "w", encoding="utf-8") as f:
            json.dump(walls, f)
        ok = [m for m in meta if "skipped" not in m]
        manifest["assets"][asset] = {
            "days": len(ok), "rows": len(df),
            "skipped": [m for m in meta if "skipped" in m],
            "low_warmup_days": [m["date"] for m in ok if m["warmup_bars"] < 100],
            "sha256": {"bars": sha256(p_bars), "walls": sha256(p_walls)},
            "days_meta": ok,
        }
        print(f"{asset}: {len(ok)} dias, {len(df)} barras, pulados {len(meta) - len(ok)}, "
              f"aquecimento NWE curto em {len(manifest['assets'][asset]['low_warmup_days'])} dias")
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(ROOT, "research", "div_wall", "dataset_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)


if __name__ == "__main__":
    main()
