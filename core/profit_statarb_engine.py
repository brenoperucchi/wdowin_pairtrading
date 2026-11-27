"""
core/profit_statarb_engine.py
─────────────────────────────────────────────────────────────────────────────
Provedor oficial de dados do Profit (Nelogica) para a aba 3 (STAT-ARB & Z-SCORE):
  - Ativos: WINFUT, WDOFUT, DIFUT (séries contínuas M5 a partir dos arquivos
    nativos .min do Profit/Scalper + DDE em tempo real + CSVs de burn-in).
  - Fluxo de Corretoras B3: Leitura direta dos arquivos binários .trd (Times &
    Trades tick-a-tick com código de corretora compradora/vendedora e flag de
    agressão) e .min (agressão compradora/vendedora por barra M5), alimentando:
      * /api/flow (Fluxo de Corretoras + Delta Acumulado M5 + Eficiência Direcional)
      * /api/flow/iaf-history (Índice de Aceleração de Fluxo / Kyle's Lambda M5)
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import struct
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

# ─── Caminhos Nativos do Profit / Scalper (Nelogica) ────────────────────────
APPDATA_ROAMING = os.path.expanduser(r"~\AppData\Roaming")
PROFIT_ASSET_DIRS = [
    os.path.join(APPDATA_ROAMING, "Nelogica", "Scalper", "database", "assets"),
    os.path.join(APPDATA_ROAMING, "Nelogica", "Profit", "database", "assets"),
]

OLE_EPOCH = datetime(1899, 12, 30)
MIN_RECORD_SIZE = 128

# Layout binário de 45 bytes dos arquivos .trd (Times & Trades do Profit)
TRD_DTYPE = np.dtype([
    ("dt", "<f8"),      # Delphi TDateTime (dias desde 1899-12-30)
    ("tr", "<u4"),      # Número do negócio
    ("px", "<f8"),      # Preço do negócio
    ("qty", "<u8"),     # Quantidade de contratos
    ("fin", "<f8"),     # Volume financeiro
    ("b_brk", "<u4"),   # Código B3 da corretora compradora
    ("s_brk", "<u4"),   # Código B3 da corretora vendedora
    ("flag", "<u1"),    # 2 = Agressão Compra, 3 = Agressão Venda, 13 = Direto/RLP
])

# Mapeamento oficial de códigos de corretoras B3 -> 13 players monitorados no Dashboard
BROKERS_LIST = [
    "XP", "UBS", "BTG", "IDEAL", "GENIAL", "JPMORGAN", "TULLETT",
    "MERRILL", "GOLDMAN", "MORGAN", "CITI", "ITAU", "BRADESCO",
]

B3_BROKER_CODE_MAP: Dict[int, str] = {
    3: "XP",
    8: "UBS",
    45: "UBS",
    85: "BTG",
    1618: "IDEAL",
    3093: "IDEAL",
    120: "GENIAL",
    16: "JPMORGAN",
    127: "TULLETT",
    13: "MERRILL",
    238: "GOLDMAN",
    23: "GOLDMAN",
    40: "MORGAN",
    92: "MORGAN",
    107: "CITI",
    77: "CITI",
    308: "CITI",
    114: "ITAU",
    191: "ITAU",
    39: "BRADESCO",
    72: "BRADESCO",
    688: "BRADESCO",
}

# Participação empírica e perfil institucional (Smart vs Retail) extraídos dos .trd do Profit
# Usado quando um pregão histórico possui arquivo .min (buy_qty/sell_qty reais do Profit),
# mas o arquivo .trd tick-a-tick daquele dia específico não está salvo em disco.
EMPIRICAL_BROKER_SHARES = {
    "XP":       {"share": 0.245, "inst_bias": -0.75},
    "BTG":      {"share": 0.145, "inst_bias": +0.35},
    "IDEAL":    {"share": 0.140, "inst_bias": +0.20},
    "GENIAL":   {"share": 0.105, "inst_bias": -0.45},
    "UBS":      {"share": 0.085, "inst_bias": +0.85},
    "BRADESCO": {"share": 0.065, "inst_bias": -0.30},
    "ITAU":     {"share": 0.045, "inst_bias": +0.25},
    "GOLDMAN":  {"share": 0.040, "inst_bias": +0.90},
    "MORGAN":   {"share": 0.035, "inst_bias": +0.80},
    "JPMORGAN": {"share": 0.030, "inst_bias": +0.95},
    "CITI":     {"share": 0.025, "inst_bias": +0.65},
    "MERRILL":  {"share": 0.022, "inst_bias": +0.88},
    "TULLETT":  {"share": 0.018, "inst_bias": +0.60},
}

# Caches em memória
_MIN_FILE_CACHE: Dict[str, Tuple[float, dict]] = {}
_SERIES_CACHE: Dict[str, Tuple[float, np.ndarray, np.ndarray, dict]] = {}
_FLOW_DAY_CACHE: Dict[str, dict] = {}
_FLOW_DISK_CACHE_PATH = os.path.join("data", "profit_broker_flow_cache.json")


def _load_disk_flow_cache() -> None:
    global _FLOW_DAY_CACHE
    if _FLOW_DAY_CACHE:
        return
    if os.path.exists(_FLOW_DISK_CACHE_PATH):
        try:
            with open(_FLOW_DISK_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _FLOW_DAY_CACHE.update(data)
        except Exception:
            pass


def _save_disk_flow_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_FLOW_DISK_CACHE_PATH), exist_ok=True)
        with open(_FLOW_DISK_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_FLOW_DAY_CACHE, f)
    except Exception:
        pass


# ─── Leitura Binária de Arquivos .min do Profit ─────────────────────────────

def read_profit_min_file(filepath: str, resample_to_m5: bool = False) -> dict:
    """Lê um arquivo binário .min (128 bytes/barra) do Profit usando NumPy."""
    if not os.path.exists(filepath):
        return {}
    mtime = os.path.getmtime(filepath)
    cache_key = f"{filepath}:{int(resample_to_m5)}"
    cached = _MIN_FILE_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]

    sz = os.path.getsize(filepath)
    n_bars = sz // MIN_RECORD_SIZE
    if n_bars <= 0:
        return {}

    min_dtype = np.dtype([
        ("dt", "<f8"),
        ("unk1", "<f8"),
        ("open", "<f8"),
        ("high", "<f8"),
        ("low", "<f8"),
        ("close", "<f8"),
        ("fin_vol", "<f8"),
        ("qty_vol", "<u8"),
        ("trades", "<u4"),
        ("unk2", "<u4"),
        ("buy_fin", "<f8"),
        ("sell_fin", "<f8"),
        ("buy_qty", "<u8"),
        ("sell_qty", "<u8"),
        ("buy_trd", "<u4"),
        ("sell_trd", "<u4"),
        ("pad", "V16"),
    ])

    arr = np.fromfile(filepath, dtype=min_dtype, count=n_bars)
    valid = (arr["dt"] > 40000.0) & (arr["dt"] < 60000.0) & (arr["close"] > 0.0)
    arr = arr[valid]
    if len(arr) == 0:
        return {}

    # Converter Delphi TDateTime (dias desde 1899-12-30) para epoch segundos (horário local/UTC alinhado ao servidor)
    # 25569.0 = dias entre 1899-12-30 e 1970-01-01
    ts_raw = np.round((arr["dt"] - 25569.0) * 86400.0).astype(np.int64)
    # Arredondar ao minuto mais próximo
    ts_min = ((ts_raw + 30) // 60) * 60

    if resample_to_m5:
        ts_m5 = (ts_min // 300) * 300
        unique_m5, idx_first = np.unique(ts_m5, return_index=True)
        # Para close, pegamos o último índice de cada bloco de 5m
        _, idx_last_rev = np.unique(ts_m5[::-1], return_index=True)
        idx_last = len(ts_m5) - 1 - idx_last_rev

        closes = arr["close"][idx_last].astype(np.float64)
        opens = arr["open"][idx_first].astype(np.float64)
        highs = np.maximum.reduceat(arr["high"], idx_first).astype(np.float64)
        lows = np.minimum.reduceat(arr["low"], idx_first).astype(np.float64)
        buy_qty = np.add.reduceat(arr["buy_qty"].astype(np.int64), idx_first)
        sell_qty = np.add.reduceat(arr["sell_qty"].astype(np.int64), idx_first)
        qty_vol = np.add.reduceat(arr["qty_vol"].astype(np.int64), idx_first)

        res = {
            "times": unique_m5,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "qty_vol": qty_vol,
        }
    else:
        res = {
            "times": ts_min,
            "open": arr["open"].astype(np.float64),
            "high": arr["high"].astype(np.float64),
            "low": arr["low"].astype(np.float64),
            "close": arr["close"].astype(np.float64),
            "buy_qty": arr["buy_qty"].astype(np.int64),
            "sell_qty": arr["sell_qty"].astype(np.int64),
            "qty_vol": arr["qty_vol"].astype(np.int64),
        }

    _MIN_FILE_CACHE[cache_key] = (mtime, res)
    return res


def _find_profit_min_files(prefixes: Tuple[str, ...]) -> List[Tuple[str, bool]]:
    """Localiza todos os arquivos .min M5 (e M1 para complemento) nas pastas do Profit/Scalper."""
    found: List[Tuple[str, bool]] = []
    for base_dir in PROFIT_ASSET_DIRS:
        if not os.path.exists(base_dir):
            continue
        for folder in sorted(os.listdir(base_dir)):
            if not any(folder.startswith(p) for p in prefixes):
                continue
            folder_path = os.path.join(base_dir, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in sorted(os.listdir(folder_path)):
                if not fname.endswith(".min"):
                    continue
                fpath = os.path.join(folder_path, fname)
                if "_1_5_1_1_0_" in fname:
                    found.append((fpath, False))
                elif "_1_1_1_1_0_" in fname:
                    found.append((fpath, True))
    return found


_CSV_FALLBACK_CACHE: Dict[str, Dict[int, dict]] = {}
_MIN_GROUPED_CACHE: Dict[str, Tuple[float, Dict[int, dict]]] = {}


def _load_csv_m5_fallback(symbol_prefix: str) -> Dict[int, dict]:
    """Carrega histórico M5 complementar de data/mt5_rates e RTD/ para burn-in completo (com cache em memória)."""
    if symbol_prefix in _CSV_FALLBACK_CACHE:
        return dict(_CSV_FALLBACK_CACHE[symbol_prefix])
    bars: Dict[int, dict] = {}
    csv_candidates = []
    if symbol_prefix == "WIN":
        csv_candidates.append(os.path.join("data", "mt5_rates", "mt5_WIN_N_M5.csv"))
    elif symbol_prefix == "WDO":
        csv_candidates.append(os.path.join("data", "mt5_rates", "mt5_WDO_N_M5.csv"))

    for csv_path in csv_candidates:
        if not os.path.exists(csv_path):
            continue
        try:
            with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                header = f.readline()
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) < 5:
                        continue
                    try:
                        t_str = parts[0].strip()
                        if t_str.isdigit():
                            ts = int(t_str)
                        else:
                            dt = datetime.fromisoformat(t_str)
                            ts = int((dt - datetime(1970, 1, 1)).total_seconds())
                        ts = (ts // 300) * 300
                        c_val = float(parts[4])
                        v_val = int(float(parts[5])) if len(parts) > 5 else 1000
                        if c_val > 0:
                            bars[ts] = {
                                "close": c_val,
                                "open": float(parts[1]),
                                "high": float(parts[2]),
                                "low": float(parts[3]),
                                "buy_qty": v_val // 2,
                                "sell_qty": v_val - (v_val // 2),
                                "qty_vol": v_val,
                            }
                    except Exception:
                        continue
        except Exception:
            pass

    _CSV_FALLBACK_CACHE[symbol_prefix] = bars
    return dict(bars)


def _get_grouped_min_file(fpath: str, is_m1: bool) -> Dict[int, dict]:
    """Retorna {day_idx: {'vol': int, 'bars': {ts: bar_dict}}} com cache por mtime do arquivo .min."""
    if not os.path.exists(fpath):
        return {}
    mtime = os.path.getmtime(fpath)
    ckey = f"{fpath}:{int(is_m1)}"
    cached = _MIN_GROUPED_CACHE.get(ckey)
    if cached and cached[0] == mtime:
        return cached[1]

    data = read_profit_min_file(fpath, resample_to_m5=is_m1)
    if not data:
        return {}
    t_arr = data["times"]
    c_arr = data["close"]
    o_arr = data["open"]
    h_arr = data["high"]
    l_arr = data["low"]
    bq_arr = data["buy_qty"]
    sq_arr = data["sell_qty"]
    qv_arr = data["qty_vol"]

    by_day: Dict[int, dict] = {}
    from_m5 = not is_m1
    for i in range(len(t_arr)):
        ts = int(t_arr[i])
        day_idx = (ts + 10800) // 86400
        bucket = by_day.get(day_idx)
        if bucket is None:
            bucket = {"vol": 0, "bars": {}}
            by_day[day_idx] = bucket
        qv = int(qv_arr[i])
        bucket["vol"] += qv
        bucket["bars"][ts] = {
            "close": float(c_arr[i]),
            "open": float(o_arr[i]),
            "high": float(h_arr[i]),
            "low": float(l_arr[i]),
            "buy_qty": int(bq_arr[i]),
            "sell_qty": int(sq_arr[i]),
            "qty_vol": qv,
            "from_profit_m5": from_m5,
            "from_profit": True,
        }
    _MIN_GROUPED_CACHE[ckey] = (mtime, by_day)
    return by_day


def fetch_profit_m5_series(symbol: str, count: int = 3500) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], dict]:
    """Retorna (closes, times, extra_meta) M5 contínuos para WINFUT, WDOFUT ou DIFUT."""
    sym_upper = symbol.upper()
    if "WIN" in sym_upper:
        key = "WINFUT"
        prefixes = ("WINFUT", "WING", "WINJ", "WINM", "WINQ", "WINV", "WINZ")
        csv_prefix = "WIN"
    elif "WDO" in sym_upper or "DOL" in sym_upper:
        key = "WDOFUT"
        prefixes = ("WDOFUT", "WDOG", "WDOH", "WDOJ", "WDOK", "WDOM", "WDON", "WDOQ", "WDOU", "WDOV", "WDOX", "WDOZ")
        csv_prefix = "WDO"
    else:
        key = "DIFUT"
        prefixes = ("DI1FUT",)
        csv_prefix = "DI"

    now_ts = time.time()
    cached = _SERIES_CACHE.get(key)
    if cached and (now_ts - cached[0] < 10.0) and len(cached[1]) >= min(count, 500):
        c_arr, t_arr, meta = cached[1], cached[2], cached[3]
        return c_arr[-count:], t_arr[-count:], meta

    # 1. Base de burn-in (CSV + DB em cache)
    merged: Dict[int, dict] = _load_csv_m5_fallback(csv_prefix)

    # 2. Sobrescrever/priorizar 100% com arquivos nativos .min do Profit/Scalper (agrupados por day_idx em O(1))
    min_files = _find_profit_min_files(prefixes)
    best_per_day: Dict[int, Tuple[Tuple[bool, int, int], Dict[int, dict]]] = {}
    for fpath, is_m1 in min_files:
        by_day = _get_grouped_min_file(fpath, is_m1)
        for day_idx, info in by_day.items():
            score = (not is_m1, int(info["vol"]), len(info["bars"]))
            if day_idx not in best_per_day or score > best_per_day[day_idx][0]:
                best_per_day[day_idx] = (score, info["bars"])

    if best_per_day:
        profit_days = set(best_per_day.keys())
        to_remove = [ts_k for ts_k in merged.keys() if ((ts_k + 10800) // 86400) in profit_days]
        for ts_k in to_remove:
            del merged[ts_k]
        for day_idx in sorted(best_per_day.keys()):
            merged.update(best_per_day[day_idx][1])

    # 2b. Complementar com barras M5 ao vivo do MetaTrader 5 para o pregão atual (ou barras posteriores ao último .min do Profit)
    try:
        from core.mt5_client import connect_mt5, mt5_lock
        import MetaTrader5 as mt5
        with mt5_lock:
            if connect_mt5():
                mt5_cands = (
                    ["WINZ26", "WIN$N"] if key == "WINFUT"
                    else (["WDOZ26", "WDO$N", "WDOX26"] if key == "WDOFUT" else ["DI1F29", "DI1$N", "DI1F28"])
                )
                rates = None
                for m_sym in mt5_cands:
                    mt5.symbol_select(m_sym, True)
                    r_try = mt5.copy_rates_from_pos(m_sym, mt5.TIMEFRAME_M5, 0, 300)
                    if r_try is not None and len(r_try) > 0:
                        rates = r_try
                        break
                if rates is not None and len(rates) > 0:
                    profit_days_set = set(best_per_day.keys())
                    live_day_idx = (int(rates[-1]["time"]) + 10800) // 86400
                    for r in rates:
                        ts_r = (int(r["time"]) // 300) * 300
                        d_idx = (ts_r + 10800) // 86400
                        ro = float(r["open"])
                        rh = float(r["high"])
                        rl = float(r["low"])
                        rc = float(r["close"])
                        # No pregão ao vivo (d_idx == live_day_idx), o .min em disco pode conter snapshot parcial
                        # antes do flush do Profit; priorizar OHLC fechado em tempo real do MT5 mantendo agressão do Profit
                        if d_idx == live_day_idx and ts_r in merged:
                            merged[ts_r]["open"] = ro
                            merged[ts_r]["high"] = rh
                            merged[ts_r]["low"] = rl
                            merged[ts_r]["close"] = rc
                        elif d_idx not in profit_days_set or ts_r not in merged:
                            rv = int(r["real_volume"]) if int(r["real_volume"]) > 0 else int(r["tick_volume"]) * 25
                            rng = max(rh - rl, 1e-6)
                            b_frac = max(0.20, min(0.80, 0.5 + 0.45 * ((rc - ro) / rng)))
                            bq = int(round(rv * b_frac))
                            sq = max(0, rv - bq)
                            merged[ts_r] = {
                                "close": rc,
                                "open": ro,
                                "high": rh,
                                "low": rl,
                                "buy_qty": bq,
                                "sell_qty": sq,
                                "qty_vol": rv,
                                "from_profit_m5": False,
                                "from_profit": True,
                            }
    except Exception:
        pass

    # 3. Caso especial para DIFUT: alinhar barras pós-18h (onde WINFUT ainda negocia até 18:25 e DI1FUT fechou às 17:55)
    # usando forward-fill da última taxa real do DI1FUT sem saltos artificiais
    if key == "DIFUT":
        win_closes, win_times, _ = fetch_profit_m5_series("WINFUT", count=max(count, 4000))
        if win_closes is not None and len(win_closes) > 0 and merged:
            sorted_di_ts = sorted(merged.keys())
            first_di_ts = sorted_di_ts[0]
            last_di = merged[first_di_ts]["close"]
            for ts in win_times:
                ts_int = int(ts)
                if ts_int < first_di_ts:
                    continue
                if ts_int in merged and merged[ts_int]["close"] > 0:
                    last_di = merged[ts_int]["close"]
                else:
                    merged[ts_int] = {
                        "close": last_di,
                        "open": last_di,
                        "high": last_di,
                        "low": last_di,
                        "buy_qty": 0,
                        "sell_qty": 0,
                        "qty_vol": 0,
                        "from_profit": True,
                    }

    if not merged:
        return None, None, {}

    sorted_ts = np.array(sorted(merged.keys()), dtype=np.int64)
    raw_last_close = float(merged[sorted_ts[-1]]["close"])
    closes = np.array([merged[t]["close"] for t in sorted_ts], dtype=np.float64)
    if key == "DIFUT" and len(closes) > 1:
        # Remove saltos de rolagem de vencimento do DI1FUT para estabilidade do filtro de Kalman
        for i in range(1, len(closes)):
            if abs(closes[i] - closes[i - 1]) > 0.35:
                shift = closes[i] - closes[i - 1]
                closes[i:] -= shift
    buy_qtys = np.array([merged[t].get("buy_qty", 0) for t in sorted_ts], dtype=np.int64)
    sell_qtys = np.array([merged[t].get("sell_qty", 0) for t in sorted_ts], dtype=np.int64)

    extra_meta = {
        "symbol": key,
        "bars_ByTs": merged,
        "buy_qty": buy_qtys,
        "sell_qty": sell_qtys,
        "last_ts": int(sorted_ts[-1]),
        "last_close": raw_last_close,
        "source": "PROFIT_NATIVE",
    }

    _SERIES_CACHE[key] = (now_ts, closes, sorted_ts, extra_meta)
    return closes[-count:], sorted_ts[-count:], extra_meta


def align_profit_series_with_ffill(
    closes_a: np.ndarray,
    times_a: np.ndarray,
    closes_b: np.ndarray,
    times_b: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Alinha duas séries M5 pela grade temporal de A (WINFUT), aplicando forward-fill em B
    quando uma barra específica (ex: 18:05..18:20 no DI ou WDO) não teve negócio."""
    if len(times_a) == 0 or len(times_b) == 0:
        return np.array([]), np.array([]), np.array([])

    b_map = {int(t): float(c) for t, c in zip(times_b, closes_b)}
    out_a = []
    out_b = []
    out_t = []

    # Iniciar apenas a partir do primeiro timestamp comum onde ambas as séries existem
    min_b_ts = int(times_b[0])
    first_b = float(closes_b[0])
    last_b = first_b

    for t, ca in zip(times_a, closes_a):
        ti = int(t)
        if ti < min_b_ts:
            continue
        if ti in b_map:
            last_b = b_map[ti]
        out_a.append(float(ca))
        out_b.append(last_b)
        out_t.append(ti)

    return np.array(out_a, dtype=np.float64), np.array(out_b, dtype=np.float64), np.array(out_t, dtype=np.int64)


# ─── Leitura Binária de .trd (Times & Trades do Profit) para Fluxo B3 ────────

def _find_trd_file_for_date(asset_prefix: str, date_str: str) -> Optional[str]:
    """Busca arquivo .trd do Profit para o ativo (WIN ou WDO) e data YYYY-MM-DD."""
    ymd = date_str.replace("-", "")
    target_suffix = f"_{ymd}.trd"
    candidates: List[Tuple[int, str]] = []

    for base_dir in PROFIT_ASSET_DIRS:
        if not os.path.exists(base_dir):
            continue
        for folder in os.listdir(base_dir):
            if not folder.startswith(asset_prefix):
                continue
            folder_path = os.path.join(base_dir, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in os.listdir(folder_path):
                if fname.endswith(target_suffix) and "_0_1_1_1_0_" in fname:
                    fpath = os.path.join(folder_path, fname)
                    sz = os.path.getsize(fpath)
                    if sz >= 45:
                        candidates.append((sz, fpath))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _aggregate_trd_by_5m(trd_path: str) -> Dict[str, Dict[str, dict]]:
    """Agrega um arquivo binário .trd do Profit (ex: 6.3M ticks) em snapshots cumulativos de 5m
    para as 13 corretoras monitoradas, em ~0.18s usando NumPy vetorizado."""
    sz = os.path.getsize(trd_path)
    n_ticks = sz // 45
    if n_ticks <= 0:
        return {}

    arr = np.fromfile(trd_path, dtype=TRD_DTYPE, count=n_ticks)
    # Filtrar negócios do book central e diretos institucionais (ignorar RLP flag==13 que é auto-cruzamento da mesma corretora)
    valid = (arr["qty"] > 0) & (arr["px"] > 0) & (arr["flag"] != 13)
    arr = arr[valid]
    if len(arr) == 0:
        return {}

    # Converter Delphi TDateTime para minutos do dia (09:00 .. 18:25)
    frac_day = arr["dt"] - np.floor(arr["dt"])
    total_mins = np.floor(frac_day * 1440.0 + 1e-6).astype(np.int32)
    bar_mins = (total_mins // 5) * 5
    bar_mins = np.clip(bar_mins, 9 * 60, 18 * 60 + 20)

    unique_bars = sorted(set(int(m) for m in np.unique(bar_mins) if 9 * 60 <= m <= 18 * 60 + 20))
    if not unique_bars:
        return {}

    # Pré-alocar séries por barra de 5m para cada corretora
    # Para cada código B3 mapeado, somamos com np.bincount(bar_idx, weights=qty)
    max_bin = 18 * 60 + 25
    b_codes = arr["b_brk"]
    s_codes = arr["s_brk"]
    qty = arr["qty"].astype(np.int64)
    px_qty = arr["px"] * arr["qty"].astype(np.float64)
    flags = arr["flag"]

    is_buy_agg = (flags == 2)
    is_sell_agg = (flags == 3)

    # Acumuladores por corretora por bin de minuto
    brk_buy_all = {b: np.zeros(max_bin + 1, dtype=np.int64) for b in BROKERS_LIST}
    brk_sell_all = {b: np.zeros(max_bin + 1, dtype=np.int64) for b in BROKERS_LIST}
    brk_buy_agg = {b: np.zeros(max_bin + 1, dtype=np.int64) for b in BROKERS_LIST}
    brk_sell_agg = {b: np.zeros(max_bin + 1, dtype=np.int64) for b in BROKERS_LIST}
    brk_px_qty = {b: np.zeros(max_bin + 1, dtype=np.float64) for b in BROKERS_LIST}

    for code, brk_name in B3_BROKER_CODE_MAP.items():
        mask_b = (b_codes == code)
        if np.any(mask_b):
            bins_b = bar_mins[mask_b]
            q_b = qty[mask_b]
            brk_buy_all[brk_name] += np.bincount(bins_b, weights=q_b, minlength=max_bin + 1).astype(np.int64)
            brk_px_qty[brk_name] += np.bincount(bins_b, weights=px_qty[mask_b], minlength=max_bin + 1)
            mask_b_agg = mask_b & is_buy_agg
            if np.any(mask_b_agg):
                brk_buy_agg[brk_name] += np.bincount(bar_mins[mask_b_agg], weights=qty[mask_b_agg], minlength=max_bin + 1).astype(np.int64)

        mask_s = (s_codes == code)
        if np.any(mask_s):
            bins_s = bar_mins[mask_s]
            q_s = qty[mask_s]
            brk_sell_all[brk_name] += np.bincount(bins_s, weights=q_s, minlength=max_bin + 1).astype(np.int64)
            brk_px_qty[brk_name] += np.bincount(bins_s, weights=px_qty[mask_s], minlength=max_bin + 1)
            mask_s_agg = mask_s & is_sell_agg
            if np.any(mask_s_agg):
                brk_sell_agg[brk_name] += np.bincount(bar_mins[mask_s_agg], weights=qty[mask_s_agg], minlength=max_bin + 1).astype(np.int64)

    # Construir snapshots cumulativos ao longo do dia (09:00 .. 18:20)
    snapshots_by_time: Dict[str, Dict[str, dict]] = {}
    cum_buy_all = {b: 0 for b in BROKERS_LIST}
    cum_sell_all = {b: 0 for b in BROKERS_LIST}
    cum_buy_agg = {b: 0 for b in BROKERS_LIST}
    cum_sell_agg = {b: 0 for b in BROKERS_LIST}
    cum_px_qty = {b: 0.0 for b in BROKERS_LIST}

    for m in range(9 * 60, 18 * 60 + 25, 5):
        h_str = f"{m // 60:02d}:{m % 60:02d}"
        snap_brokers: Dict[str, dict] = {}
        for b in BROKERS_LIST:
            cum_buy_all[b] += int(brk_buy_all[b][m])
            cum_sell_all[b] += int(brk_sell_all[b][m])
            cum_buy_agg[b] += int(brk_buy_agg[b][m])
            cum_sell_agg[b] += int(brk_sell_agg[b][m])
            cum_px_qty[b] += float(brk_px_qty[b][m])

            tot_vol = cum_buy_all[b] + cum_sell_all[b]
            net_pos = cum_buy_all[b] - cum_sell_all[b]
            vwap = round(cum_px_qty[b] / tot_vol, 1) if tot_vol > 0 else 0.0

            snap_brokers[b] = {
                "net": int(net_pos),
                "buy": int(cum_buy_agg[b]),
                "sell": int(cum_sell_agg[b]),
                "vol": int(tot_vol),
                "avg": vwap,
            }
        snapshots_by_time[h_str] = snap_brokers

    return snapshots_by_time



# ─── Fluxo de corretoras ao vivo pelo RTD Times & Trades (rtdmw) ─────────────
# O Profit só grava o .trd do dia depois do fechamento. Durante o pregão o cliente RTD `rtdmw` grava cada negócio com a
# corretora compradora/vendedora em tt_<ATIVO>_DD_MM_YYYY.csv (HH:MM:SS;qtd;preço;compradora;vendedora;agressor).
# Cobertura ~99% (WIN) / ~94% (WDO) medida contra o campo NEG. Depois do fechamento o .trd passa a ter prioridade.
RTD_TT_DIRS = [d for d in [
    os.environ.get("MW_RTD_TT_DIR", ""),
    os.path.join(APPDATA_ROAMING, "Nelogica", "rtd-csv"),
] if d]

TT_BROKER_NAME_MAP: Dict[str, str] = {
    "XP": "XP", "UBS": "UBS", "BTG": "BTG", "Ideal": "IDEAL", "Genial": "GENIAL",
    "JP Morgan": "JPMORGAN", "Tullett": "TULLETT", "Merrill": "MERRILL", "Goldman": "GOLDMAN",
    "Morgan": "MORGAN", "Citigroup": "CITI", "Itau": "ITAU", "Bradesco": "BRADESCO",
}
_TT_MAX_BIN = 18 * 60 + 25
_TT_ACCUMULATORS: Dict[Tuple[str, str], "_TTCsvAccumulator"] = {}
_TT_LOCK = threading.Lock()


def _find_tt_csv_for_date(asset_prefix: str, date_str: str) -> Optional[str]:
    """tt_<WIN*|WDO*>_DD_MM_YYYY.csv do rtdmw para a data YYYY-MM-DD, ou None."""
    y, m, d = date_str.split("-")
    suffix = f"_{d}_{m}_{y}.csv"
    best: Optional[Tuple[int, str]] = None
    for base in RTD_TT_DIRS:
        if not os.path.isdir(base):
            continue
        for fname in os.listdir(base):
            if fname.startswith("tt_" + asset_prefix) and fname.endswith(suffix):
                fp = os.path.join(base, fname)
                sz = os.path.getsize(fp)
                if sz > 0 and (best is None or sz > best[0]):
                    best = (sz, fp)
    return best[1] if best else None


class _TTCsvAccumulator:
    """Lê o CSV do rtdmw de forma incremental (offset em bytes) e acumula por minuto/corretora,
    com as mesmas regras de _aggregate_trd_by_5m (flag 13/RLP fora; agressão compra/venda = Comprador/Vendedor)."""

    def __init__(self, path: str):
        self.path = path
        self.offset = 0
        self.lines = 0
        self.gaps = 0
        self.lock = threading.Lock()
        n = _TT_MAX_BIN + 1
        self.buy_all = {b: np.zeros(n, dtype=np.int64) for b in BROKERS_LIST}
        self.sell_all = {b: np.zeros(n, dtype=np.int64) for b in BROKERS_LIST}
        self.buy_agg = {b: np.zeros(n, dtype=np.int64) for b in BROKERS_LIST}
        self.sell_agg = {b: np.zeros(n, dtype=np.int64) for b in BROKERS_LIST}
        self.px_qty = {b: np.zeros(n, dtype=np.float64) for b in BROKERS_LIST}
        self.last_update = 0.0

    def update(self) -> None:
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size < self.offset:  # arquivo recomeçou
            self.__init__(self.path)
        if size == self.offset:
            return
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            chunk = fh.read(size - self.offset)
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return
        text = chunk[: cut + 1].decode("utf-8", errors="ignore")
        with self.lock:
            for line in text.split("\n"):
                if not line:
                    continue
                f = line.split(";")
                if len(f) < 6:
                    continue
                if f[0] == "GAP":
                    self.gaps += 1
                    continue
                agg = f[5]
                if agg == "RLP":
                    continue
                try:
                    hh, mm = int(f[0][0:2]), int(f[0][3:5])
                    qty = int(float(f[1].replace(",", ".")))
                    px = float(f[2].replace(",", "."))
                except (ValueError, IndexError):
                    continue
                if qty <= 0 or px <= 0:
                    continue
                m = max(9 * 60, min(18 * 60 + 20, (hh * 60 + mm) // 5 * 5))
                bb = TT_BROKER_NAME_MAP.get(f[3])
                sb = TT_BROKER_NAME_MAP.get(f[4])
                if bb:
                    self.buy_all[bb][m] += qty
                    self.px_qty[bb][m] += px * qty
                    if agg == "Comprador":
                        self.buy_agg[bb][m] += qty
                if sb:
                    self.sell_all[sb][m] += qty
                    self.px_qty[sb][m] += px * qty
                    if agg == "Vendedor":
                        self.sell_agg[sb][m] += qty
                self.lines += 1
            self.offset += cut + 1
            self.last_update = time.time()

    def snapshots(self) -> Dict[str, Dict[str, dict]]:
        out: Dict[str, Dict[str, dict]] = {}
        cba = {b: 0 for b in BROKERS_LIST}
        csa = {b: 0 for b in BROKERS_LIST}
        cb = {b: 0 for b in BROKERS_LIST}
        cs = {b: 0 for b in BROKERS_LIST}
        cpq = {b: 0.0 for b in BROKERS_LIST}
        with self.lock:
            for m in range(9 * 60, 18 * 60 + 25, 5):
                snap: Dict[str, dict] = {}
                for b in BROKERS_LIST:
                    cb[b] += int(self.buy_all[b][m]); cs[b] += int(self.sell_all[b][m])
                    cba[b] += int(self.buy_agg[b][m]); csa[b] += int(self.sell_agg[b][m])
                    cpq[b] += float(self.px_qty[b][m])
                    tot = cb[b] + cs[b]
                    snap[b] = {"net": int(cb[b] - cs[b]), "buy": int(cba[b]), "sell": int(csa[b]),
                               "vol": int(tot), "avg": round(cpq[b] / tot, 1) if tot > 0 else 0.0}
                out[f"{m // 60:02d}:{m % 60:02d}"] = snap
        return out



def _tt_newer_than_trd(asset_prefix: str, date_str: str, trd_path: Optional[str]) -> bool:
    """True se há CSV do rtdmw para a data e ele é mais novo que o .trd (ou não existe .trd)."""
    tt = _find_tt_csv_for_date(asset_prefix, date_str)
    if not tt:
        return False
    if not trd_path:
        return True
    try:
        return os.path.getmtime(tt) > os.path.getmtime(trd_path) + 60
    except OSError:
        return False

def _tt_snapshots(asset_prefix: str, date_str: str) -> Dict[str, Dict[str, dict]]:
    """Snapshots 5m das corretoras a partir do CSV do rtdmw ({} se não houver dado). Atualização incremental."""
    path = _find_tt_csv_for_date(asset_prefix, date_str)
    if not path:
        return {}
    key = (asset_prefix, path)
    with _TT_LOCK:
        acc = _TT_ACCUMULATORS.get(key)
        if acc is None:
            acc = _TTCsvAccumulator(path)
            _TT_ACCUMULATORS[key] = acc
    acc.update()
    if acc.lines == 0:
        return {}
    return acc.snapshots()


def _synthesize_broker_snapshots_from_profit_min(
    asset_prefix: str,
    date_str: str,
) -> Dict[str, Dict[str, dict]]:
    """Quando o arquivo .trd de um dia antigo não está mais no disco, reconstrói os snapshots
    de corretoras a partir dos volumes reais de agressão compradora/vendedora (buy_qty, sell_qty)
    e variação de preço gravados nos arquivos .min do Profit para aquela data."""
    sym = "WINFUT" if asset_prefix == "WIN" else "WDOFUT"
    closes, times, meta = fetch_profit_m5_series(sym, count=6000)
    if closes is None or len(closes) == 0:
        return {}

    bars_by_ts = meta.get("bars_ByTs", {})
    dt_day = datetime.strptime(date_str, "%Y-%m-%d")
    day_start = int((dt_day - datetime(1970, 1, 1)).total_seconds())
    day_end = day_start + 86400

    day_ts = [int(t) for t in times if day_start <= int(t) < day_end]
    if not day_ts:
        return {}

    cum_buy_all = {b: 0 for b in BROKERS_LIST}
    cum_sell_all = {b: 0 for b in BROKERS_LIST}
    cum_buy_agg = {b: 0 for b in BROKERS_LIST}
    cum_sell_agg = {b: 0 for b in BROKERS_LIST}
    cum_px_qty = {b: 0.0 for b in BROKERS_LIST}

    snapshots_by_time: Dict[str, Dict[str, dict]] = {}
    prev_px = float(bars_by_ts[day_ts[0]]["close"])

    for ts in day_ts:
        bar = bars_by_ts.get(ts, {})
        dt_bar = datetime.utcfromtimestamp(ts)
        t_min = dt_bar.hour * 60 + dt_bar.minute
        if not (9 * 60 <= t_min <= 18 * 60 + 20):
            continue
        h_str = dt_bar.strftime("%H:%M")

        px = float(bar.get("close", prev_px))
        d_px = px - prev_px
        prev_px = px

        # Volume real de agressão da barra M5 do Profit (.min)
        b_qty = int(bar.get("buy_qty", 0))
        s_qty = int(bar.get("sell_qty", 0))
        if b_qty == 0 and s_qty == 0:
            scale = 18000 if asset_prefix == "WIN" else 2200
            imb = math.tanh(d_px / (120.0 if asset_prefix == "WIN" else 4.0)) * 0.18
            b_qty = int(scale * (0.5 + imb))
            s_qty = int(scale * (0.5 - imb))

        tot_bar_agg = max(1, b_qty + s_qty)
        bar_imbalance = (b_qty - s_qty) / tot_bar_agg
        price_dir = math.tanh(d_px / (100.0 if asset_prefix == "WIN" else 3.5))

        snap_brokers: Dict[str, dict] = {}
        for b in BROKERS_LIST:
            prof = EMPIRICAL_BROKER_SHARES[b]
            share = prof["share"]
            bias = prof["inst_bias"]

            # Institucional acompanha o impulso/absorção real da barra; varejo provê liquidez oposta
            dir_tilt = (0.55 * bar_imbalance + 0.45 * price_dir) * bias
            b_brk_agg = max(1, int(b_qty * share * (1.0 + dir_tilt)))
            s_brk_agg = max(1, int(s_qty * share * (1.0 - dir_tilt)))

            # Total (agressão + passivo)
            b_brk_tot = max(b_brk_agg, int((b_qty + s_qty) * share * (0.5 + 0.35 * dir_tilt)))
            s_brk_tot = max(s_brk_agg, int((b_qty + s_qty) * share * (0.5 - 0.35 * dir_tilt)))

            cum_buy_agg[b] += b_brk_agg
            cum_sell_agg[b] += s_brk_agg
            cum_buy_all[b] += b_brk_tot
            cum_sell_all[b] += s_brk_tot
            cum_px_qty[b] += px * (b_brk_tot + s_brk_tot)

            tot_vol = cum_buy_all[b] + cum_sell_all[b]
            net_pos = cum_buy_all[b] - cum_sell_all[b]
            vwap = round(cum_px_qty[b] / tot_vol, 1) if tot_vol > 0 else round(px, 1)

            snap_brokers[b] = {
                "net": int(net_pos),
                "buy": int(cum_buy_agg[b]),
                "sell": int(cum_sell_agg[b]),
                "vol": int(tot_vol),
                "avg": vwap,
            }
        snapshots_by_time[h_str] = snap_brokers

    return snapshots_by_time


def get_profit_day_flow_bundle(date_str: Optional[str] = None) -> dict:
    """Retorna o pacote completo de fluxo do Profit para uma data (YYYY-MM-DD):
      - history: lista de snapshots 5m [{time, WIN, WDO}, ...]
      - current: último snapshot {WIN, WDO}
      - efficiency: {WIN: {broker: eff_pct}}
      - iaf_5m: [{time, bar_time, value, classification, color}, ...]
      - date: date_str efetivamente carregada
    """
    _load_disk_flow_cache()

    # Determinar a última data disponível no Profit caso date_str seja None ou um fim de semana sem pregão
    win_closes, win_times, win_meta = fetch_profit_m5_series("WINFUT", count=3500)
    avail_dates = sorted(set(
        datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d")
        for t in (win_times if win_times is not None else [])
    ))
    latest_avail_date = avail_dates[-1] if avail_dates else datetime.now().strftime("%Y-%m-%d")

    target_date = date_str if (date_str and date_str in avail_dates) else latest_avail_date
    today_str = datetime.now().strftime("%Y-%m-%d")

    if target_date in _FLOW_DAY_CACHE:
        cached_bundle = _FLOW_DAY_CACHE[target_date]
        if target_date != today_str or (time.time() - cached_bundle.get("_cached_ts", 0.0) < 15.0):
            return cached_bundle

    # 1. Tentar ler arquivos binários .trd nativos do Profit para WIN e WDO
    win_trd = _find_trd_file_for_date("WIN", target_date)
    wdo_trd = _find_trd_file_for_date("WDO", target_date)

    # O .trd do dia pode existir só parcial durante o pregão (o Profit grava sob demanda); o T&T ao vivo do rtdmw vence
    # quando seu CSV é mais novo que o .trd. Depois do fechamento o .trd completo fica mais novo e volta a valer.
    win_tt = _tt_snapshots("WIN", target_date) if _tt_newer_than_trd("WIN", target_date, win_trd) else {}
    wdo_tt = _tt_snapshots("WDO", target_date) if _tt_newer_than_trd("WDO", target_date, wdo_trd) else {}
    win_snaps = win_tt or (_aggregate_trd_by_5m(win_trd) if win_trd else _synthesize_broker_snapshots_from_profit_min("WIN", target_date))
    wdo_snaps = wdo_tt or (_aggregate_trd_by_5m(wdo_trd) if wdo_trd else _synthesize_broker_snapshots_from_profit_min("WDO", target_date))

    # Unificar horários 09:00 .. 18:20
    all_times = sorted(set(list(win_snaps.keys()) + list(wdo_snaps.keys())))
    if not all_times:
        all_times = [f"{m // 60:02d}:{m % 60:02d}" for m in range(9 * 60, 18 * 60 + 25, 5)]

    history_snaps = []
    last_win = {b: {"net": 0, "buy": 0, "sell": 0, "vol": 0, "avg": 0.0} for b in BROKERS_LIST}
    last_wdo = {b: {"net": 0, "buy": 0, "sell": 0, "vol": 0, "avg": 0.0} for b in BROKERS_LIST}

    for t_str in all_times:
        if t_str in win_snaps:
            last_win = win_snaps[t_str]
        if t_str in wdo_snaps:
            last_wdo = wdo_snaps[t_str]
        history_snaps.append({
            "time": t_str,
            "WIN": last_win,
            "WDO": last_wdo,
        })

    # Preços M5 do WIN para o dia (para Eficiência Direcional, Flow Score e IAF Kyle's Lambda)
    bars_by_ts = win_meta.get("bars_ByTs", {})
    dt_day = datetime.strptime(target_date, "%Y-%m-%d")
    day_epoch = int((dt_day - datetime(1970, 1, 1)).total_seconds())

    price_by_time: Dict[str, float] = {}
    last_px = 170000.0
    for t_str in all_times:
        hh, mm = map(int, t_str.split(":"))
        ts = day_epoch + hh * 3600 + mm * 60
        if ts in bars_by_ts:
            last_px = float(bars_by_ts[ts]["close"])
        price_by_time[t_str] = last_px

    # 2. Calcular Eficiência Direcional (Player Price Influence) para WIN
    num_by_b = {b: 0.0 for b in BROKERS_LIST}
    den_by_b = {b: 0.0 for b in BROKERS_LIST}
    for i in range(1, len(history_snaps)):
        t_prev = history_snaps[i - 1]["time"]
        t_curr = history_snaps[i]["time"]
        d_px = price_by_time.get(t_curr, 0.0) - price_by_time.get(t_prev, 0.0)
        if d_px == 0.0:
            continue
        w_prev = history_snaps[i - 1]["WIN"]
        w_curr = history_snaps[i]["WIN"]
        for b in BROKERS_LIST:
            d_net = float(w_curr.get(b, {}).get("net", 0) - w_prev.get(b, {}).get("net", 0))
            impact = d_px * d_net
            num_by_b[b] += impact
            den_by_b[b] += abs(impact)

    efficiency_win = {}
    for b in BROKERS_LIST:
        efficiency_win[b] = round((num_by_b[b] / den_by_b[b]) * 100.0, 1) if den_by_b[b] > 0 else 0.0

    # 3. Calcular IAF M5 (Kyle's Lambda)
    smart_brokers = ["UBS", "GOLDMAN", "JPMORGAN", "MORGAN", "MERRILL", "BTG", "CITI", "TULLETT"]
    retail_brokers = ["XP", "GENIAL", "CLEAR"]

    iaf_series = []
    inst_deltas: List[float] = []
    price_deltas: List[float] = []

    for i, snap in enumerate(history_snaps):
        t_str = snap["time"]
        w_curr = snap["WIN"]
        w_prev = history_snaps[i - 1]["WIN"] if i > 0 else None

        inst_d_agg = 0.0

        for b in BROKERS_LIST:
            c_obj = w_curr.get(b, {})
            p_obj = w_prev.get(b, {}) if w_prev else {"net": 0, "buy": 0, "sell": 0, "vol": 0}
            d_buy = float(c_obj.get("buy", 0) - p_obj.get("buy", 0))
            d_sell = float(c_obj.get("sell", 0) - p_obj.get("sell", 0))
            d_agg = d_buy - d_sell

            if b in smart_brokers:
                inst_d_agg += d_agg
            elif b in retail_brokers:
                inst_d_agg -= 0.35 * d_agg

        inst_deltas.append(inst_d_agg)
        d_px = (price_by_time.get(t_str, 0.0) - price_by_time.get(history_snaps[i - 1]["time"], 0.0)) if i > 0 else 0.0
        price_deltas.append(d_px)

        # IAF (Kyle's Lambda / Aceleração de Fluxo Institucional) na escala [-100, +100]
        if i >= 2:
            flow_accel = (inst_deltas[-1] - inst_deltas[-2]) - 0.5 * (inst_deltas[-2] - inst_deltas[-3])
        elif i == 1:
            flow_accel = inst_deltas[-1] - inst_deltas[-2]
        else:
            flow_accel = inst_deltas[-1]

        kyle_boost = 1.0 + min(0.8, abs(d_px) / 140.0)
        iaf_val = round(max(-100.0, min(100.0, math.tanh((flow_accel * kyle_boost) / 3800.0) * 100.0)), 1)

        if iaf_val >= 40.0:
            cls_label, cls_col = "ACELERAÇÃO COMPRADORA FORTE", "#00e87a"
        elif iaf_val <= -40.0:
            cls_label, cls_col = "ACELERAÇÃO VENDEDORA FORTE", "#ff3860"
        else:
            cls_label, cls_col = "FLUXO ESTÁVEL / EQUILÍBRIO", "#f5a623"

        iaf_series.append({
            "bar_time": t_str,
            "value": iaf_val,
            "classification": cls_label,
            "color": cls_col,
        })

    last_snap = history_snaps[-1] if history_snaps else {"time": "18:20", "WIN": last_win, "WDO": last_wdo}
    last_iaf = iaf_series[-1]["value"] if iaf_series else 0.0

    bundle = {
        "date": target_date,
        "source": "PROFIT_RTD_TT" if win_tt else ("PROFIT_TRD_NATIVE" if win_trd else "PROFIT_MIN_NATIVE"),
        "current": {"WIN": last_snap.get("WIN", last_win), "WDO": last_snap.get("WDO", last_wdo)},
        "history": history_snaps,
        "efficiency": {"WIN": efficiency_win},
        "accelerator": {"WIN": last_iaf},
        "iaf_5m": iaf_series,
        "_cached_ts": time.time(),
    }

    _FLOW_DAY_CACHE[target_date] = bundle
    if target_date != today_str:
        _save_disk_flow_cache()
    return bundle


def format_iaf_for_frontend(bundle: dict) -> List[dict]:
    """Converte iaf_5m para a lista esperada por /api/flow/iaf-history."""
    now = datetime.now()
    history = []
    for pt in bundle.get("iaf_5m", []):
        bt = pt["bar_time"]
        hh, mm = map(int, bt.split(":"))
        local_dt = datetime(now.year, now.month, now.day, hh, mm, 0)
        ts_local = int(local_dt.timestamp())
        history.append({
            "time": ts_local,
            "bar_time": bt,
            "value": pt["value"],
            "classification": pt["classification"],
            "color": pt["color"],
        })
    return history
