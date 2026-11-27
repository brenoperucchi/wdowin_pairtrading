# -*- coding: utf-8 -*-
"""
Read-only probe: what order-flow data does a given MT5 terminal actually deliver for B3 futures?

Checks, per symbol:
  1. Time & Sales: recent ticks, how many are real trades, and whether trades carry the
     BUY/SELL aggressor flag (TICK_FLAG_BUY / TICK_FLAG_SELL).
  2. Tick fields: whether any field could identify the broker (agent) of a trade.
  3. Order book (DOM): whether market_book_add/market_book_get return depth levels.

It never sends orders. It only calls initialize, symbol_select, copy_ticks_from,
market_book_add/get/release and shutdown.

Usage, inside the MT5 container (Windows Python under Wine):
    wine "C:\\Program Files\\Python312\\python.exe" C:\\mt5_flow_capability_probe.py C:\\MT5-b3 WINZ26 WDOZ26
Arguments: <terminal_dir> [symbol ...]  (default symbols: WINZ26 WDOZ26)
Optional: --minutes N (look-back window, default 15), --book-seconds N (default 3).
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import MetaTrader5 as mt5

DEFAULT_SYMBOLS = ["WINZ26", "WDOZ26"]


def probe_time_and_sales(symbol: str, minutes: int) -> dict:
    result: dict = {"symbol": symbol}
    last = mt5.symbol_info_tick(symbol)
    if last is None or not last.time:
        result["error"] = "no last tick (symbol hidden, market closed, or no data subscription)"
        return result
    result["last_tick_time_utc"] = datetime.fromtimestamp(last.time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    from_dt = datetime.fromtimestamp(last.time - minutes * 60, tz=timezone.utc)
    ticks = mt5.copy_ticks_from(symbol, from_dt, 2_000_000, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        result["error"] = f"copy_ticks_from returned no ticks ({mt5.last_error()})"
        return result
    names = list(ticks.dtype.names or [])
    flags = ticks["flags"]
    is_buy = (flags & mt5.TICK_FLAG_BUY) != 0
    is_sell = (flags & mt5.TICK_FLAG_SELL) != 0
    is_last = (flags & mt5.TICK_FLAG_LAST) != 0
    is_volume = (flags & mt5.TICK_FLAG_VOLUME) != 0
    trade_mask = is_last | is_volume | is_buy | is_sell
    trades = int(trade_mask.sum())
    classified = int((trade_mask & (is_buy ^ is_sell)).sum())
    both = int((is_buy & is_sell).sum())
    result.update(
        {
            "lookback_minutes": minutes,
            "total_ticks": int(len(ticks)),
            "trade_ticks": trades,
            "buy_aggressor": int((is_buy & ~is_sell).sum()),
            "sell_aggressor": int((is_sell & ~is_buy).sum()),
            "both_flags": both,
            "trades_without_side": trades - classified,
            "side_coverage_pct": round(100.0 * classified / trades, 1) if trades else None,
            "tick_fields": names,
            "volume_field_sum": int(ticks["volume"].sum()) if "volume" in names else None,
            "flag_distribution": dict(Counter(int(f) for f in flags).most_common(6)),
        }
    )
    broker_like = [n for n in names if any(k in n.lower() for k in ("agent", "broker", "buyer", "seller", "order"))]
    result["broker_like_fields"] = broker_like
    return result


def probe_book(symbol: str, seconds: int) -> dict:
    result: dict = {"symbol": symbol}
    if not mt5.market_book_add(symbol):
        result["error"] = f"market_book_add refused ({mt5.last_error()}): book not available for this account/symbol"
        return result
    try:
        deadline = time.time() + seconds
        book = None
        while time.time() < deadline:
            book = mt5.market_book_get(symbol)
            if book:
                break
            time.sleep(0.5)
        if not book:
            result["error"] = "market_book_get returned empty: broker does not stream depth (or market closed)"
            return result
        buys = [b for b in book if b.type in (mt5.BOOK_TYPE_BUY, mt5.BOOK_TYPE_BUY_MARKET)]
        sells = [b for b in book if b.type in (mt5.BOOK_TYPE_SELL, mt5.BOOK_TYPE_SELL_MARKET)]
        result.update(
            {
                "levels_total": len(book),
                "bid_levels": len(buys),
                "ask_levels": len(sells),
                "best_bid": max((b.price for b in buys), default=None),
                "best_ask": min((b.price for b in sells), default=None),
                "top_sizes": [int(b.volume) for b in list(book)[:5]],
            }
        )
        return result
    finally:
        mt5.market_book_release(symbol)


def verdict(ts: dict, book: dict) -> list[str]:
    lines: list[str] = []
    if "error" in ts:
        lines.append(f"TIME&SALES: FAIL - {ts['error']}")
    else:
        cov = ts.get("side_coverage_pct")
        if ts["trade_ticks"] == 0:
            lines.append("TIME&SALES: no trades in the window (market closed or illiquid) - rerun during the session")
        elif cov is not None and cov >= 90:
            lines.append(f"TIME&SALES: OK - {cov}% of trades carry the buy/sell aggressor flag")
        else:
            lines.append(f"TIME&SALES: PARTIAL - only {cov}% of trades carry the aggressor flag")
        lines.append(
            "BROKER ID: "
            + ("present in fields " + ", ".join(ts["broker_like_fields"]) if ts["broker_like_fields"] else "NOT available (no agent/broker field in ticks)")
        )
    lines.append("BOOK: " + ("FAIL - " + book["error"] if "error" in book else f"OK - {book['levels_total']} levels ({book['bid_levels']} bid / {book['ask_levels']} ask)"))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MT5 order-flow capability probe")
    parser.add_argument("terminal_dir", help=r"Terminal folder, e.g. C:\MT5-b3")
    parser.add_argument("symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--minutes", type=int, default=15)
    parser.add_argument("--book-seconds", type=int, default=3)
    args = parser.parse_args()

    if not mt5.initialize(path=args.terminal_dir + r"\terminal64.exe", portable=True):
        print("initialize failed", mt5.last_error())
        return 1
    try:
        account = mt5.account_info()
        print(f"account {account.login} {account.server} | mode {({0: 'DEMO', 1: 'CONTEST', 2: 'REAL'}).get(account.trade_mode)}")
        for symbol in args.symbols:
            print(f"\n=== {symbol} ===")
            if not mt5.symbol_select(symbol, True):
                print(f"symbol_select failed for {symbol}: {mt5.last_error()}")
                continue
            time.sleep(1.0)
            ts = probe_time_and_sales(symbol, args.minutes)
            book = probe_book(symbol, args.book_seconds)
            for key, value in ts.items():
                print(f"  ts.{key}: {value}")
            for key, value in book.items():
                print(f"  book.{key}: {value}")
            print()
            for line in verdict(ts, book):
                print("  -> " + line)
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
