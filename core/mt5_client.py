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

def _is_mt5_visible_running(target_path: str) -> bool:
    """Verifica se o terminal64.exe em target_path já está em execução no Windows (evita lançar instância invisível)."""
    if not target_path:
        return True
    try:
        import ctypes
        from ctypes import wintypes
        norm_target = os.path.normcase(os.path.normpath(target_path))
        kernel32 = ctypes.windll.kernel32
        TH32CS_SNAPPROCESS = 0x00000002
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        hsnap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if hsnap == wintypes.HANDLE(-1).value:
            return True
        try:
            pe = PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(hsnap, ctypes.byref(pe)):
                return False
            while True:
                if pe.szExeFile.lower() == "terminal64.exe":
                    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pe.th32ProcessID)
                    if hproc:
                        try:
                            buf = ctypes.create_unicode_buffer(1024)
                            size = wintypes.DWORD(1024)
                            if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                                proc_path = os.path.normcase(os.path.normpath(buf.value))
                                if proc_path == norm_target:
                                    return True
                        finally:
                            kernel32.CloseHandle(hproc)
                if not kernel32.Process32NextW(hsnap, ctypes.byref(pe)):
                    break
        finally:
            kernel32.CloseHandle(hsnap)
        return False
    except Exception:
        return True


def connect_mt5() -> bool:
    """Inicializa conexão com o MT5 especificado em MT5_PATH (apenas se já estiver aberto)."""
    with mt5_lock:
        if mt5.terminal_info() is not None:
            return True
        candidates = []
        for cand in [
            MT5_PATH,
            "C:/Program Files/MetaTrader 5/terminal64.exe",
            "C:/Program Files/MetaTrader 5 Terminal - milhao/terminal64.exe",
            "C:/Program Files/MetaTrader 5 Terminal/terminal64.exe",
        ]:
            if cand and cand not in candidates:
                candidates.append(cand)
        for cand in candidates:
            if not _is_mt5_visible_running(cand):
                continue
            print(f"[MT5] Conectando ao terminal: {cand}")
            if mt5.initialize(path=cand, timeout=8000):
                info = mt5.terminal_info()
                print(f"[MT5] Conectado — {info.name} | path: {info.path}")
                from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL
                for sym in [SYMBOL_A, SYMBOL_B, DI_SYMBOL, "WINZ26", "WDOZ26", "DI1F29", "DI1F28"]:
                    mt5.symbol_select(sym, True)
                return True
        return False


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
