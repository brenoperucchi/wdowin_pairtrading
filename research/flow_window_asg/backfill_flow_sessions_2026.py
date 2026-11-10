import os
import sys
import json
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.profit_mt5_flow_engine import (
    SymbolMicrostructureState,
    MT5_PATH,
    list_available_gex_dates,
)

HIST_CACHE_DIR = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")


def main():
    os.makedirs(HIST_CACHE_DIR, exist_ok=True)
    all_dates = sorted(list_available_gex_dates(limit=300))
    print(f"Total GEX dates found: {len(all_dates)} ({all_dates[0]} .. {all_dates[-1]})")

    missing_dates = [
        d for d in all_dates
        if not os.path.exists(os.path.join(HIST_CACHE_DIR, f"{d}.json"))
    ]
    print(f"Already cached: {len(all_dates) - len(missing_dates)} | Missing to backfill: {len(missing_dates)}")

    if not missing_dates:
        print("All sessions already cached!")
        return

    if not mt5.initialize(MT5_PATH, timeout=10000):
        if not mt5.initialize():
            raise RuntimeError(f"Failed to initialize MT5: {mt5.last_error()}")

    win_cont = "WIN" + chr(36) + "N"
    wdo_cont = "WDO" + chr(36) + "N"
    mt5.symbol_select(win_cont, True)
    mt5.symbol_select(wdo_cont, True)

    t0_all = time.time()
    generated = 0
    for idx, target_date in enumerate(missing_dates, 1):
        t0 = time.time()
        disk_cache_path = os.path.join(HIST_CACHE_DIR, f"{target_date}.json")
        if os.path.exists(disk_cache_path):
            continue

        win_st = SymbolMicrostructureState("WIN", 50, 10, 5.0, 60.0)
        wdo_st = SymbolMicrostructureState("WDO", 20, 5, 0.5, 2.5)
        win_st.reset_session(target_date)
        wdo_st.reset_session(target_date)
        win_st.active_contract = win_cont
        wdo_st.active_contract = wdo_cont

        dt_base = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt_start = dt_base.replace(hour=9, minute=0, second=0, microsecond=0)
        dt_end = dt_base.replace(hour=18, minute=35, second=0, microsecond=0)
        nine_thirty_epoch = int(dt_base.replace(hour=9, minute=30, second=0, microsecond=0).timestamp())

        for asset_key, st, cont_sym in [("WIN", win_st, win_cont), ("WDO", wdo_st, wdo_cont)]:
            best_ticks = mt5.copy_ticks_range(cont_sym, dt_start, dt_end, mt5.COPY_TICKS_ALL)
            if best_ticks is not None and len(best_ticks) > 0:
                flags = best_ticks["flags"]
                is_buy = (flags & mt5.TICK_FLAG_BUY) != 0
                is_sell = (flags & mt5.TICK_FLAG_SELL) != 0
                has_dual_flags = (np.sum(is_sell) > 0.05 * len(best_ticks)) and (np.sum(is_buy) > 0.05 * len(best_ticks))
                if has_dual_flags:
                    valid_dir = (is_buy ^ is_sell) & (best_ticks["volume"] > 0) & (best_ticks["last"] > 0)
                else:
                    valid_dir = (best_ticks["volume"] > 0) & (best_ticks["last"] > 0)

                if np.any(valid_dir):
                    t_valid = best_ticks[valid_dir]
                    post_930 = t_valid[t_valid["time"] >= nine_thirty_epoch]
                    if len(post_930) > 100:
                        ref_open_px = float(post_930["last"][0])
                        max_gap = 1800.0 if asset_key == "WIN" else 35.0
                        keep_mask = (t_valid["time"] >= nine_thirty_epoch) | (
                            np.abs(t_valid["last"].astype(np.float64) - ref_open_px) <= max_gap
                        )
                        if np.any(keep_mask):
                            t_valid = t_valid[keep_mask]

                    if has_dual_flags:
                        side_arr = np.where((t_valid["flags"] & mt5.TICK_FLAG_BUY) != 0, 1, -1).astype(np.int8)
                    else:
                        px_arr = t_valid["last"].astype(np.float64)
                        diffs = np.diff(px_arr, prepend=px_arr[0])
                        raw_signs = np.where(diffs > 0, 1, np.where(diffs < 0, -1, 0)).astype(np.int8)
                        nz_idx = np.where(raw_signs != 0, np.arange(len(raw_signs)), 0)
                        np.maximum.accumulate(nz_idx, out=nz_idx)
                        side_arr = raw_signs[nz_idx]
                        side_arr[side_arr == 0] = 1

                    st.ingest_batch_vectorized(
                        t_valid["time"].astype(np.int64),
                        t_valid["last"].astype(np.float64),
                        t_valid["volume"].astype(np.float64),
                        side_arr,
                    )
                    st.source = f"HISTÓRICO MT5 ({target_date} · {cont_sym})"

        win_payload = win_st.get_summary_payload()
        wdo_payload = wdo_st.get_summary_payload()

        n_win = len(win_payload.get("m5_cvd_series", []))
        n_wdo = len(wdo_payload.get("m5_cvd_series", []))
        if n_win > 0 and n_wdo > 0:
            with open(disk_cache_path, "w", encoding="utf-8") as cf:
                json.dump({"WIN": win_payload, "WDO": wdo_payload}, cf)
            generated += 1

        if idx % 10 == 0 or idx == len(missing_dates):
            el = time.time() - t0
            tot_el = time.time() - t0_all
            print(
                f"[{idx}/{len(missing_dates)}] {target_date}: WIN M5={n_win}, WDO M5={n_wdo} "
                f"({el:.2f}s | total {tot_el:.1f}s)"
            )

    print(f"Done! Generated {generated}/{len(missing_dates)} historical flow sessions in {time.time() - t0_all:.1f}s.")


if __name__ == "__main__":
    main()
