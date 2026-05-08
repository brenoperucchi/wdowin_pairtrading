# core/mt5_client.py
"""MT5 connection management, data fetching, and order execution.

Extracted from server.py — all MetaTrader 5 I/O lives here.
Order helpers (send_market_order, close_position_by_ticket, list_open_positions)
return plain dicts so callers can stay testable without real MT5 state.
"""
import logging
import numpy as np
import MetaTrader5 as mt5
from core.config import MT5_PATH, MT5_PORTABLE, TIMEFRAME

logger = logging.getLogger(__name__)


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
    # Ensure B3 symbols are visible in Market Watch
    from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL
    for sym in [SYMBOL_A, SYMBOL_B, DI_SYMBOL]:
        mt5.symbol_select(sym, True)
    print(f"[MT5] Symbols ativados: {SYMBOL_A}, {SYMBOL_B}, {DI_SYMBOL}")
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
        "ticket": ticket,
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
