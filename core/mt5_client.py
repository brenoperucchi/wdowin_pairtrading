# core/mt5_client.py
"""MT5 connection management and data fetching.

Extracted from server.py — all MetaTrader 5 I/O lives here.
"""
import numpy as np
import MetaTrader5 as mt5
from core.config import MT5_PATH, MT5_PORTABLE, TIMEFRAME


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
