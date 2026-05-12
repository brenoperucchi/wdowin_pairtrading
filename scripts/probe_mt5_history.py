"""Probe how far back MT5 has M5 history for our 3 symbols.

Walks backwards a chunk at a time until the broker stops returning bars.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone

import MetaTrader5 as mt5
import numpy as np

sys.path.insert(0, ".")
from core.config import MT5_PATH, MT5_PORTABLE, SYMBOL_A, SYMBOL_B, DI_SYMBOL


def connect() -> None:
    kwargs = {"timeout": 10000}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if MT5_PORTABLE:
        kwargs["portable"] = True
    if not mt5.initialize(**kwargs):
        print(f"[ERR] mt5.initialize failed: {mt5.last_error()}")
        sys.exit(1)
    for s in (SYMBOL_A, SYMBOL_B, DI_SYMBOL):
        mt5.symbol_select(s, True)
    info = mt5.terminal_info()
    print(f"[MT5] Connected: {info.name} ({info.path})")


def probe_symbol(symbol: str) -> None:
    tf = mt5.TIMEFRAME_M5
    print(f"\n=== {symbol} ===")

    # 1) Pull a giant chunk via copy_rates_from_pos and see the earliest bar.
    for count in (50_000, 100_000, 200_000, 500_000, 1_000_000):
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            print(f"  count={count:>8}: no data ({mt5.last_error()})")
            continue
        first_ts = int(rates[0]["time"])
        last_ts = int(rates[-1]["time"])
        first = datetime.fromtimestamp(first_ts, tz=timezone.utc).astimezone()
        last = datetime.fromtimestamp(last_ts, tz=timezone.utc).astimezone()
        print(f"  count={count:>8}: got {len(rates):>7} bars, first={first.isoformat()}, last={last.isoformat()}")
        if len(rates) < count:
            # broker returned everything it has — no point going larger
            print(f"  -> broker capped at {len(rates)} bars (asked {count})")
            break

    # 2) Try copy_rates_range from explicit 2025-01-01.
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime.now(tz=timezone.utc)
    rates = mt5.copy_rates_range(symbol, tf, start, end)
    if rates is None or len(rates) == 0:
        print(f"  copy_rates_range 2025-01-01 -> now: no data ({mt5.last_error()})")
    else:
        first = datetime.fromtimestamp(int(rates[0]["time"]), tz=timezone.utc).astimezone()
        last = datetime.fromtimestamp(int(rates[-1]["time"]), tz=timezone.utc).astimezone()
        print(f"  copy_rates_range 2025-01-01 -> now: {len(rates)} bars, {first.isoformat()} .. {last.isoformat()}")

    # 3) Walk in 3-month chunks back to find earliest available bar.
    print(f"  -- walking back in 90-day chunks --")
    cur_end = datetime.now(tz=timezone.utc)
    earliest_seen = None
    for _ in range(24):  # up to 6 years
        from_dt = cur_end - (90 * 86400 - 0) * __import__("datetime").timedelta(seconds=1)
        # Simpler: use timedelta
        from datetime import timedelta
        from_dt = cur_end - timedelta(days=90)
        rates = mt5.copy_rates_range(symbol, tf, from_dt, cur_end)
        if rates is None or len(rates) == 0:
            print(f"    {from_dt.date()} .. {cur_end.date()}: empty - stopping")
            break
        first_ts = int(rates[0]["time"])
        earliest_seen = datetime.fromtimestamp(first_ts, tz=timezone.utc).astimezone()
        print(f"    {from_dt.date()} .. {cur_end.date()}: {len(rates):>6} bars, first={earliest_seen.date()}")
        cur_end = from_dt
    if earliest_seen:
        print(f"  -> EARLIEST AVAILABLE: {earliest_seen.isoformat()}")


def main() -> None:
    connect()
    for s in (SYMBOL_A, SYMBOL_B, DI_SYMBOL):
        probe_symbol(s)
    mt5.shutdown()


if __name__ == "__main__":
    main()
