"""
Decomposição de fluxo por barra M1 do `.min` do Profit (institucional agressor, passivo e varejo).

Mesmas fórmulas de `_build_from_profit_min_m1_m5` em `core/profit_wall_players_engine.py`
(calibração .trd → .min), mas devolvendo cada minuto em vez de agregar em M5.
`research/div_wall/test_m1_decomp.py` prova que a soma destes minutos reproduz exatamente os
campos `inst_aggr_delta`, `inst_pass_delta` e `ret_delta_bar` das barras M5 do motor.
Se as fórmulas do motor mudarem, esse teste quebra.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import numpy as np


def decompose_min_bars(arr: np.ndarray, asset: str, iso_date: str) -> List[dict]:
    """`arr` = registros `.min` M1 (MIN_FULL_DTYPE) de um dia. Devolve barras 09:00–18:25."""
    is_win = asset.upper() == "WIN"
    tick_sz = 5.0 if is_win else 0.5
    ts_raw = np.round((arr["dt"] - 25569.0) * 86400.0).astype(np.int64)
    ts_min = ((ts_raw + 30) // 60) * 60
    day_epoch = int(datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    mod = (ts_min - day_epoch) // 60
    mask = (mod >= 540) & (mod <= 1105)
    a = arr[mask]
    ts_min = ts_min[mask]
    if len(a) == 0:
        return []

    o = a["open"].astype(np.float64)
    h = a["high"].astype(np.float64)
    l = a["low"].astype(np.float64)
    c = a["close"].astype(np.float64)
    bq = a["buy_qty"].astype(np.float64)
    sq = a["sell_qty"].astype(np.float64)
    bt = np.maximum(1, a["buy_trd"].astype(np.int64))
    st = np.maximum(1, a["sell_trd"].astype(np.int64))

    bl = bq / bt
    sl = sq / st
    mean_lot = np.maximum(0.5, 0.5 * (bl + sl))
    base_inst = 0.52 if is_win else 0.64
    base_ret = 0.16 if is_win else 0.12
    w_inst_b = np.clip(base_inst * ((bl / mean_lot) ** 0.85), 0.22, 0.84)
    w_inst_s = np.clip(base_inst * ((sl / mean_lot) ** 0.85), 0.22, 0.84)
    w_ret_b = np.clip(base_ret * ((mean_lot / np.maximum(0.5, bl)) ** 0.75), 0.06, 0.45)
    w_ret_s = np.clip(base_ret * ((mean_lot / np.maximum(0.5, sl)) ** 0.75), 0.06, 0.45)
    w_hft_b = np.maximum(0.05, 1.0 - w_inst_b - w_ret_b)
    w_hft_s = np.maximum(0.05, 1.0 - w_inst_s - w_ret_s)

    rng = np.maximum(h - l, tick_sz)
    lwr = (np.minimum(o, c) - l) / rng
    uwr = (h - np.maximum(o, c)) / rng
    pas_b_frac = np.clip(0.28 + 0.42 * lwr + np.where(c >= o, 0.12, -0.05), 0.10, 0.78)
    pas_s_frac = np.clip(0.28 + 0.42 * uwr + np.where(c <= o, 0.12, -0.05), 0.10, 0.78)

    inst_aggr = bq * w_inst_b - sq * w_inst_s
    inst_pass = sq * pas_b_frac * (w_ret_s + 0.5 * w_hft_s) - bq * pas_s_frac * (w_ret_b + 0.5 * w_hft_b)
    ret_d = bq * w_ret_b - sq * w_ret_s

    out = []
    for i in range(len(a)):
        out.append({
            "ts": int(ts_min[i]),
            "time": datetime.fromtimestamp(int(ts_min[i]), tz=timezone.utc).strftime("%H:%M"),
            "open": float(o[i]), "high": float(h[i]), "low": float(l[i]), "close": float(c[i]),
            "buy_vol": float(bq[i]), "sell_vol": float(sq[i]),
            "avg_buy_lot": round(float(bl[i]), 2), "avg_sell_lot": round(float(sl[i]), 2),
            "inst_aggr_delta": float(inst_aggr[i]), "inst_pass_delta": float(inst_pass[i]),
            "ret_delta_bar": float(ret_d[i]),
        })
    return out
