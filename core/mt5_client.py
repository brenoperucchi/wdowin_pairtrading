# core/mt5_client.py
"""MT5 connection management, data fetching, and order execution.

Extracted from server.py — all MetaTrader 5 I/O lives here.
Order helpers (send_market_order, close_position_by_ticket, list_open_positions)
return plain dicts so callers can stay testable without real MT5 state.
"""
import logging
import re
import numpy as np
import MetaTrader5 as mt5
from core.config import MT5_PATH, MT5_PORTABLE, TIMEFRAME

logger = logging.getLogger(__name__)

_B3_FUTURE_MONTH_CODES = "FGHJKMNQUVXZ"


def _symbol_info_text(info, fields=("basis", "description", "path", "name")) -> str:
    parts = []
    for field in fields:
        value = getattr(info, field, None)
        if value:
            parts.append(str(value))
    return " | ".join(parts)


def _extract_current_contract(continuous_symbol: str, info) -> str | None:
    prefix = continuous_symbol.split("$", 1)[0].upper()
    text = _symbol_info_text(info)
    pattern = rf"\b{re.escape(prefix)}[{_B3_FUTURE_MONTH_CODES}]\d{{2}}\b"
    match = re.search(pattern, text.upper())
    return match.group(0) if match else None


def resolve_live_symbol_win(configured_symbol: str | None = None) -> str:
    """Resolve the tradable WIN contract from WIN$N metadata.

    XP's continuous symbol exposes the active liquidity contract in
    symbol_info("WIN$N").description, for example:
    "IBOVESPA MINI - Por Liquidez (WINM26) - Sem Ajustes".
    """
    from core.config import (
        ALLOW_CONTINUOUS_LIVE_SYMBOL,
        LIVE_SYMBOL_WIN,
        SYMBOL_A,
    )

    requested = (configured_symbol if configured_symbol is not None else LIVE_SYMBOL_WIN).strip()
    if requested and requested.upper() not in {"AUTO", "DYNAMIC"}:
        if requested.endswith("$N") and not ALLOW_CONTINUOUS_LIVE_SYMBOL:
            raise ValueError(
                f"LIVE_SYMBOL_WIN={requested} is continuous; use AUTO or a tradable contract"
            )
        return requested

    continuous_symbol = SYMBOL_A
    mt5.symbol_select(continuous_symbol, True)
    info = mt5.symbol_info(continuous_symbol)
    if info is None:
        raise RuntimeError(
            f"Could not resolve live WIN symbol from {continuous_symbol}: {mt5.last_error()}"
        )

    candidate = _extract_current_contract(continuous_symbol, info)
    if not candidate:
        raise RuntimeError(
            f"Could not parse active WIN contract from {continuous_symbol}: "
            f"{_symbol_info_text(info)!r}"
        )

    mt5.symbol_select(candidate, True)
    candidate_info = mt5.symbol_info(candidate)
    if candidate_info is None:
        raise RuntimeError(
            f"Resolved {candidate} from {continuous_symbol}, but symbol_info({candidate}) failed: "
            f"{mt5.last_error()}"
        )

    trade_mode = getattr(candidate_info, "trade_mode", None)
    disabled_mode = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
    if trade_mode == disabled_mode:
        raise RuntimeError(
            f"Resolved {candidate} from {continuous_symbol}, but trade_mode is disabled"
        )
    return candidate


# ─── MT5 connection ─────────────────────────────────────────────────────────

def connect_mt5() -> bool:
    """Inicializa conexão com o MT5 especificado em MT5_PATH."""
    if mt5.terminal_info() is not None:
        return True
    kwargs = {"timeout": 10000}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
        print(f"[MT5] Conectando ao terminal: {MT5_PATH}")
    if MT5_PORTABLE:
        kwargs["portable"] = True
    if not mt5.initialize(**kwargs):
        print(f"[MT5] Falha ao inicializar: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    print(f"[MT5] Conectado — {info.name} | path: {info.path}")
    # Ensure data symbols and the live execution contract are visible.
    from core.config import LIVE_SYMBOL_WIN, SYMBOL_A, SYMBOL_B, DI_SYMBOL
    symbols = list(dict.fromkeys([SYMBOL_A, SYMBOL_B, DI_SYMBOL]))
    for sym in symbols:
        mt5.symbol_select(sym, True)
    try:
        symbols.append(resolve_live_symbol_win(LIVE_SYMBOL_WIN))
    except Exception as exc:
        logger.warning("Could not resolve live WIN symbol: %s", exc)
    print(f"[MT5] Symbols ativados: {', '.join(symbols)}")
    return True


def fetch_bars(symbol: str, count: int):
    """Retorna (closes, timestamps) para o símbolo e count de barras."""
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, count)
    if rates is None or len(rates) == 0:
        print(f"[MT5] Sem dados para {symbol}: {mt5.last_error()}")
        return None, None
    closes = np.array([r["close"] for r in rates], dtype=float)
    times = np.array([r["time"] for r in rates], dtype=np.int64)
    return closes, times


def fetch_rates(symbol: str, count: int):
    """Return the raw MT5 rates array (OHLC + time + volume + spread) for `count` bars.

    Callers receive the structured numpy array straight from
    `mt5.copy_rates_from_pos` so any field can be read (open/high/low/close/time/
    tick_volume/spread/real_volume). Returns None when the call fails or yields
    no data — same failure semantics as fetch_bars.
    """
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, count)
    if rates is None or len(rates) == 0:
        logger.warning("fetch_rates: sem dados para %s: %s", symbol, mt5.last_error())
        return None
    return rates


def fetch_rates_range(symbol: str, dt_start, dt_end):
    """Return MT5 rates array for a date range — used by historical backfill.

    `dt_start` and `dt_end` are datetime objects (MT5 converts them internally).
    Returns the raw structured np.ndarray from `mt5.copy_rates_range`, or None
    on error / empty result.
    """
    rates = mt5.copy_rates_range(symbol, TIMEFRAME, dt_start, dt_end)
    if rates is None or len(rates) == 0:
        logger.warning(
            "fetch_rates_range: sem dados para %s [%s, %s]: %s",
            symbol, dt_start, dt_end, mt5.last_error(),
        )
        return None
    return rates


# ─── Order helpers (TASK-2) ─────────────────────────────────────────────────
# All three functions are pure wrappers around mt5.* calls. They own no state
# and do not know about TradeEngine — that keeps them unit-testable via monkeypatch.
#
# Return schema (all functions):
#   {ok: bool, ticket: int|None, retcode: int, message: str, price: float|None}
#
# Callers must check ok before using ticket/price.

def send_market_order(
    symbol: str,
    side: str,          # "BUY" or "SELL"
    volume: float,
    magic: int,
    deviation: int,
    comment: str = "",
) -> dict:
    """Send a market order and return a normalised result dict.

    No retry — caller decides whether to retry on failure (TASK-2 design:
    one attempt per bar; a failed attempt is logged, not silently retried,
    so the audit trail is clean).
    """
    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_filling": mt5.ORDER_FILLING_RETURN,
        "type_time": mt5.ORDER_TIME_GTC,
    }
    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        logger.error("send_market_order order_send returned None error=%s", err)
        return {"ok": False, "ticket": None, "retcode": -1, "message": str(err), "price": None}

    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    if not ok:
        logger.warning(
            "send_market_order failed symbol=%s side=%s retcode=%s comment=%s",
            symbol, side, result.retcode, result.comment,
        )
    else:
        logger.info(
            "send_market_order ok symbol=%s side=%s ticket=%s price=%s magic=%s",
            symbol, side, result.order, result.price, magic,
        )
    return {
        "ok": ok,
        "ticket": result.order if ok else None,
        "retcode": result.retcode,
        "message": result.comment,
        "price": result.price if ok else None,
    }


def close_position_by_ticket(
    ticket: int,
    magic: int,
    comment: str = "",
) -> dict:
    """Close an open position identified by its ticket.

    Looks up the position first so we can send the correct counter-side order.
    Returns ok=False with reason if the position is not found — caller handles
    the POSITION_NOT_FOUND case (e.g., already closed by SL/TP, or wrong ticket).
    """
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        logger.warning("close_position_by_ticket ticket=%s not found", ticket)
        return {
            "ok": False,
            "ticket": ticket,
            "retcode": -1,
            "message": "POSITION_NOT_FOUND",
            "price": None,
        }

    pos = positions[0]
    # Counter-side: BUY position needs a SELL to close, and vice versa.
    close_type = (
        mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    )
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": ticket,
        "deviation": 50,
        "magic": magic,
        "comment": comment,
        "type_filling": mt5.ORDER_FILLING_RETURN,
        "type_time": mt5.ORDER_TIME_GTC,
    }
    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        logger.error("close_position_by_ticket order_send None ticket=%s error=%s", ticket, err)
        return {"ok": False, "ticket": ticket, "retcode": -1, "message": str(err), "price": None}

    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    if not ok:
        logger.warning(
            "close_position_by_ticket failed ticket=%s retcode=%s comment=%s",
            ticket, result.retcode, result.comment,
        )
    else:
        logger.info(
            "close_position_by_ticket ok ticket=%s price=%s magic=%s",
            ticket, result.price, magic,
        )
    return {
        "ok": ok,
        "ticket": result.order if ok else ticket,
        "retcode": result.retcode,
        "message": result.comment,
        "price": result.price if ok else None,
    }


def list_open_positions(symbol: str = None, magic: int = None) -> list:
    """Return open positions filtered by symbol and/or magic number.

    Each item is a plain dict with keys:
      ticket, symbol, type ("BUY"|"SELL"), volume, price_open, magic, comment.
    Returns empty list on error or no positions (never raises).
    """
    kwargs = {}
    if symbol is not None:
        kwargs["symbol"] = symbol
    try:
        positions = mt5.positions_get(**kwargs) or []
    except Exception as exc:
        logger.error("list_open_positions positions_get raised %s", exc)
        return []

    out = []
    for pos in positions:
        if magic is not None and pos.magic != magic:
            continue
        out.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": pos.volume,
            "price_open": pos.price_open,
            "magic": pos.magic,
            "comment": pos.comment,
        })
    return out
