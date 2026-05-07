# core/mt5_client.py
"""
MT5 connection management, data fetching, and beta state machine.

Extracted from server.py — all MetaTrader 5 I/O lives here.
"""
import os
import json
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from core.config import MT5_PATH, MT5_PORTABLE, TIMEFRAME, BETA_INITIAL


# ─── Beta persistence (LEGACY V1 — unused after V1 endpoint removal) ────────
# `beta_state`, `load_beta_ultimo`, `save_beta_ultimo` are dead at runtime: nothing
# in `server.py` imports them anymore. Only the import-time read of beta_ultimo.json
# (when computing `beta_state["current_beta"]` below) still touches disk.
# Scheduled for deletion in the risk_gate slice (TASK-3 AC #3), which will own
# OLS beta caching properly. Leaving in place to keep this slice strictly scoped to
# AC #1 (V1 endpoint removal).


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
