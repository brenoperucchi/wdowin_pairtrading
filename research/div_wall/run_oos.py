"""
Roda o OOS (ago–nov/2026) UMA VEZ para a config nº 1 de uma grade IS, conforme o pré-registro.
Grava o resultado em `results/oos_log.json` e se recusa a rodar de novo a mesma grade.

Uso: python -m research.div_wall.run_oos WIN m1_div_strong
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.div_wall_signal import ExitParams, compute_flow, run_session  # noqa: E402
from research.div_wall.bt_grid_m1 import EXIT_BASE, make_sig  # noqa: E402
from research.div_wall.data import load_asset, metrics, split  # noqa: E402

RES = os.path.join(ROOT, "research", "div_wall", "results")
LOG = os.path.join(RES, "oos_log.json")
APPROVE = {"pf": 1.20, "net": 0.0, "pos_month_frac": 0.5}


def _val(v):
    if isinstance(v, float) and v != v:
        return None
    return v


def row_to_params(asset, kind, row):
    skw, ekw = {}, {}
    for c, v in row.items():
        v = _val(v)
        if c.startswith("s_"):
            k = c[2:]
            if k == "wall_types":
                v = tuple(str(v).split("+"))
            elif k == "pierce":
                v = tuple(float(x) for x in str(v).split("+"))
            elif k in ("pivot_right", "n_back"):
                v = int(v)
            skw[k] = v
        elif c.startswith("e_"):
            k = c[2:]
            if k == "rr" and v is None:
                continue
            if k == "max_bars":
                v = int(v)
            ekw[k] = v
    sp = make_sig(asset, kind.replace("m1_", ""), skw)
    ep = ExitParams.default(asset, **EXIT_BASE[asset], **ekw)
    return sp, ep, skw, ekw


def main(asset, grid):
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    key = f"{asset}_{grid}"
    if any(e["key"] == key for e in log):
        print(f"OOS de {key} já foi rodado em {[e['ran_at'] for e in log if e['key'] == key][0]} — não roda de novo.")
        return
    df = pd.read_csv(os.path.join(RES, f"{asset}_{grid}_is_grid.csv"))
    top = df[df["eligible"]].iloc[0]
    if float(top["plateau"]) <= 1.0:
        print(f"Platô {top['plateau']} <= 1,0 — pela regra, o OOS fica fechado.")
        return
    sp, ep, skw, ekw = row_to_params(asset, grid, top.to_dict())
    tf = "M1" if grid.startswith("m1") else "M5"
    trades = []
    for d, (bars, walls, nwe) in split(load_asset(asset, tf), "OOS").items():
        _, tr = run_session(d, asset, bars, walls, nwe, sp, ep, fbars=compute_flow(bars, asset))
        trades += tr
    m = metrics(trades, asset)
    approved = m["pf"] >= APPROVE["pf"] and m["net"] > APPROVE["net"] and m["months"] > 0 and \
        m["pos_months"] / m["months"] >= APPROVE["pos_month_frac"]
    is_m = {k: _val(top[k]) for k in ("trades", "wr", "pf", "net", "mdd", "ret_dd", "pos_months", "plateau")}
    entry = {"key": key, "ran_at": datetime.now().isoformat(timespec="seconds"), "signal": {k: str(v) for k, v in skw.items()},
             "exit": {k: str(v) for k, v in ekw.items()}, "is": is_m, "oos": m, "approved": bool(approved)}
    log.append(entry)
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1, default=str)
    pd.DataFrame([t.as_row() for t in trades]).to_csv(os.path.join(RES, f"{key}_oos_trades.csv"), index=False)
    print(json.dumps(entry, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
