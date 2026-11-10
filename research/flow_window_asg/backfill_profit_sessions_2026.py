# -*- coding: utf-8 -*-
"""
research/flow_window_asg/backfill_profit_sessions_2026.py
=========================================================
Atualiza todas as 212+ sessões de 2026 em `data/processed/gex_historical_sessions_v1/*.json`
substituindo o fluxo antigo do MT5 (baseado em lote >= 50) pela Decomposição Nativa dos
4 Players do Profit (`.trd` tick-a-tick + `.min` M1/M5 com Book Central B3 + RLP isolado).
"""
import os
import sys
import glob
import json
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.profit_wall_players_engine import (
    build_profit_session_payload,
    _load_profit_min_index,
)
from core.profit_mt5_flow_engine import list_available_gex_dates

HIST_CACHE_DIR = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")


def main():
    os.makedirs(HIST_CACHE_DIR, exist_ok=True)
    t0 = time.time()
    idx_w = _load_profit_min_index("WIN")
    idx_d = _load_profit_min_index("WDO")
    existing_files = sorted(glob.glob(os.path.join(HIST_CACHE_DIR, "*.json")))
    existing_dates = [os.path.basename(f)[:-5] for f in existing_files]
    gex_dates = [d for d in list_available_gex_dates(limit=300) if d >= "2026-01-02"]
    all_dates = sorted(set(existing_dates) | set(gex_dates))

    print(f"Loaded Profit .min index (WIN={len(idx_w)}, WDO={len(idx_d)}) in {time.time()-t0:.2f}s")
    print(f"Upgrading {len(all_dates)} sessions ({all_dates[0]} .. {all_dates[-1]}) to Profit 4-Player Microstructure...")

    updated = 0
    trd_count = 0
    min_count = 0

    for i, d_str in enumerate(all_dates, 1):
        fp = os.path.join(HIST_CACHE_DIR, f"{d_str}.json")
        old_data = {}
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    old_data = json.load(fh)
            except Exception:
                old_data = {}

        win_p = build_profit_session_payload("WIN", d_str) or old_data.get("WIN")
        wdo_p = build_profit_session_payload("WDO", d_str) or old_data.get("WDO")

        if win_p and wdo_p and len(win_p.get("m5_cvd_series", [])) > 0 and len(wdo_p.get("m5_cvd_series", [])) > 0:
            if "TRD NATIVO" in str(win_p.get("source", "")) or "TRD NATIVO" in str(wdo_p.get("source", "")):
                trd_count += 1
            else:
                min_count += 1
            with open(fp, "w", encoding="utf-8") as fh:
                json.dump({"WIN": win_p, "WDO": wdo_p}, fh)
            updated += 1

        if i % 25 == 0 or i == len(all_dates):
            print(f"  [{i}/{len(all_dates)}] {d_str} | Updated={updated} (TRD={trd_count}, MIN_M1_M5={min_count}) | Elapsed={time.time()-t0:.1f}s")

    print(f"Done! Upgraded {updated} sessions (TRD tick-by-tick={trd_count}, Profit M1+M5 native={min_count}) in {time.time()-t0:.1f}s.")


if __name__ == "__main__":
    main()
