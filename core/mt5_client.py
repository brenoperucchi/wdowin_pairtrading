# core/mt5_client.py
"""
MT5 connection management, data fetching, and beta state machine.

Extracted from server.py — all MetaTrader 5 I/O lives here.
"""
import os
import json
import threading
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from core.config import MT5_PATH, TIMEFRAME, BETA_INITIAL

# Global RLock to serialize all MetaTrader 5 IPC C-extension calls across threads
mt5_lock = threading.RLock()


# ─── Beta persistence ───────────────────────────────────────────────────────

def load_beta_ultimo() -> float:
    """Load last computed beta from disk."""
    try:
        if os.path.exists("beta_ultimo.json"):
            with open("beta_ultimo.json", "r") as f:
                d = json.load(f)
                return float(d.get("beta", BETA_INITIAL))
    except Exception:
        pass
    return BETA_INITIAL


def save_beta_ultimo(b_val: float) -> None:
    """Persist current beta to disk."""
    try:
        with open("beta_ultimo.json", "w") as f:
            json.dump({"beta": b_val, "ts": datetime.now().isoformat()}, f)
    except Exception:
        pass


# ─── Beta state machine (module-level) ──────────────────────────────────────

beta_state = {
    "current_beta": load_beta_ultimo(),
    "last_calc_date": None,
    "last_calc_hour": None,
    "previous_beta": BETA_INITIAL,
    "unstable": False,
}


# ─── MT5 connection ─────────────────────────────────────────────────────────

def connect_mt5() -> bool:
    """Inicializa conexão com o MT5 especificado em MT5_PATH."""
    with mt5_lock:
        if mt5.terminal_info() is not None:
            return True
        kwargs = {"timeout": 10000}
        if MT5_PATH:
            kwargs["path"] = MT5_PATH
            print(f"[MT5] Conectando ao terminal: {MT5_PATH}")
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
    with mt5_lock:
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, count)
        if rates is None or len(rates) == 0:
            print(f"[MT5] Sem dados para {symbol}: {mt5.last_error()}")
            return None, None
        closes = np.array([r["close"] for r in rates], dtype=float)
        times = np.array([r["time"] for r in rates], dtype=np.int64)
        return closes, times


def align_series_by_time(closes_a, times_a, closes_b, times_b):
    """Alinha duas séries de barras M5 pela interseção exata de timestamps."""
    if closes_a is None or closes_b is None or times_a is None or times_b is None:
        return None, None, None
    common_ts, idx_a, idx_b = np.intersect1d(times_a, times_b, return_indices=True)
    if len(common_ts) > 0:
        return closes_a[idx_a], closes_b[idx_b], common_ts
    min_len = min(len(closes_a), len(closes_b))
    return closes_a[-min_len:], closes_b[-min_len:], times_a[-min_len:]
