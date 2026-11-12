"""
Ponte entre o motor ao vivo (`gex_live_dealer_engine`) e o runner único dos setups (`core/setups_runner.py`).

- Dia passado: `run_setups(dia, dia)` sem corte — idêntico ao BT.
- Pregão corrente: anexa ao cache do MT5 as barras recentes (WIN$N/WDO$N M5 e WIN$N M1, do fim do cache até agora),
  recalcula as máscaras de fluxo do dia a partir do `.min` do Profit e roda com corte = última barra M5 fechada.
Resultados ficam em cache por (data, corte), então cada barra M5 é calculada uma única vez para os dois ativos.
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from research import mt5_loader
from research.flow_window_asg.flow_filters import load_flow_tables

WARMUP_DAYS = 7
CSV_END = "2026-11-11"   # último pregão nos caches data/mt5_rates (research/append_mt5_rates.py); depois disso vem do MT5 ao vivo
_lock = threading.Lock()
_cache: Dict[tuple, Dict[str, List[dict]]] = {}
_base_flow = None
LAST_STATUS: Dict[str, object] = {}


def _flow_tables():
    global _base_flow
    if _base_flow is None:
        _base_flow, _ = load_flow_tables("min")
    return _base_flow


def _today_flow(day: str):
    """Tabelas base + máscaras do dia recalculadas do `.min` (índice do Profit relido a cada chamada)."""
    from core import profit_wall_players_engine as pwe
    from research.setup_parity.build_flow_min import session_masks

    pwe._PROFIT_MIN_INDEX_CACHE.clear()
    ft = copy.copy(_flow_tables())
    ft = {a: {fn: dict(tbl) for fn, tbl in ft[a].items()} for a in ft}
    n_bars = {}
    for asset in ("WIN", "WDO"):
        rec = pwe._load_profit_min_index(asset).get(day)
        masks = session_masks(asset, day, rec) if rec else {}
        n_bars[asset] = len(masks)
        for key, m in masks.items():
            for fn, ok in m.items():
                if fn in ft[asset]:
                    ft[asset][fn][key] = ok
    return ft, n_bars


def _refresh_mt5_extension(now: datetime, cutoff=None) -> Dict[str, int]:
    """
    Barras do fim do cache CSV até `now`, via a thread única do MT5 (`core.mt5_client.mt5_lock`).
    Logo após conectar, o terminal pode devolver histórico parcial: exige que a última barra M5 chegue até
    o corte (tenta 3 vezes) e, se não chegar, levanta erro — nunca roda os setups com barras faltando.
    """
    import time as _time
    for attempt in range(3):
        out, last = _fetch_mt5_extension(now)
        if cutoff is None or all(v is not None and v + pd.Timedelta(minutes=5) >= pd.Timestamp(cutoff)
                                 for k, v in last.items() if k.endswith("_M5")):
            return out
        _time.sleep(2.0)
    raise RuntimeError(f"MT5 devolveu barras incompletas até {cutoff}: {last}")


def _fetch_mt5_extension(now: datetime):
    import MetaTrader5 as mt5
    from core.mt5_client import connect_mt5, mt5_lock

    out, last = {}, {}
    if not connect_mt5():
        raise RuntimeError("MT5 indisponível para barras do pregão")
    tf = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5}
    for sym, tfs in (("WIN$N", ("M5", "M1")), ("WDO$N", ("M5",))):
        for tfn in tfs:
            base = mt5_loader._get_mt5_rates_raw(sym, tfn, "2026-04-01", CSV_END, False)
            start = pd.Timestamp(base["t"].max()).to_pydatetime() + timedelta(minutes=1)
            with mt5_lock:
                raw = mt5.copy_rates_range(sym, tf[tfn], start, now + timedelta(days=1))
            df = pd.DataFrame(raw) if raw is not None and len(raw) else pd.DataFrame()
            if len(df):
                df["t"] = pd.to_datetime(df["time"], unit="s")
                df = df[["t", "open", "high", "low", "close", "tick_volume", "real_volume"]]
            mt5_loader.set_live_extension(sym, tfn, df if len(df) else None)
            out[f"{sym}_{tfn}"] = int(len(df))
            last[f"{sym}_{tfn}"] = pd.Timestamp(df["t"].max()) if len(df) else None
    return out, last


def trades_for(day: str, asset: str, is_live: bool, now: Optional[datetime] = None) -> List[dict]:
    """Trades do runner único para `asset` em `day` (mesmo formato dos trades do JSON do BT)."""
    from core.setups_runner import run_setups

    csv_end = CSV_END
    with _lock:
        now = now or datetime.now()
        if not is_live:
            key = (day, None)
            if key not in _cache:
                if str(day) > csv_end:
                    _refresh_mt5_extension(now, cutoff=None)
                    ft, n_flow = _today_flow(day)
                else:
                    ft, n_flow = _flow_tables(), {}
                run_res = run_setups(day, day, flow_tables=ft, warmup_days=WARMUP_DAYS)
                if any(run_res.values()) or str(day) <= csv_end:
                    _cache[key] = run_res
                LAST_STATUS.update({"day": day, "cutoff": None, "flow_bars_min": n_flow})
                res = _cache.get(key, run_res)
            else:
                res = _cache[key]
        else:
            # Depois do fechamento não existem barras novas: o corte para no fim do pregão (última M5 18:30),
            # senão a checagem de barras completas falha a cada chamada e trava o servidor.
            cutoff = min(pd.Timestamp(now).floor("5min"), pd.Timestamp(f"{day} 18:30"))
            key = (day, cutoff)
            if key not in _cache:
                ext = _refresh_mt5_extension(now, cutoff)
                ft, n_flow = _today_flow(day)
                _cache[key] = run_setups(day, day, flow_tables=ft, warmup_days=WARMUP_DAYS, cutoff=cutoff)
                LAST_STATUS.update({"day": day, "cutoff": str(cutoff), "mt5_bars": ext, "flow_bars_min": n_flow})
                for k in [k for k in _cache if k[0] == day and k[1] is not None and k != key]:
                    _cache.pop(k, None)
            res = _cache[key]
    return [dict(t) for sid, v in res.items() for t in v if t.get("asset") == asset]
