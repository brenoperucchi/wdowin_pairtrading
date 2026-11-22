# -*- coding: utf-8 -*-
"""
Variantes da onda "Fluxo Smart Money" para a ablação de fluxo (research/flow_ablation, 16/11/2026).

Nada aqui altera core/ ou os motores: as variantes são funções `flow(bars, asset)` com a MESMA assinatura de
`core.div_wall_signal.compute_flow` e o MESMO pipeline depois da força (impulso 3 barras, acumulado do dia,
EMA rápida α=0,5 − EMA lenta α=2/11, onda = 0,55·(EMAf−EMAs) + 0,45·imp3). Só a força por barra muda.

A variante C precisa do institucional SEM pavio. Ele é recalculado minuto a minuto do `.min` bruto do Profit
(mesmo loader do dataset, `_load_profit_min_index`), com as fórmulas de `core/profit_min_decomp.py`, trocando
apenas as frações passivas dependentes do pavio por uma constante (média do próprio ativo no período), e
somado nos baldes de 5 min. A versão "pavio" do mesmo recálculo é conferida contra o `div_wall_v1` (paridade).
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.div_wall_signal import compute_flow as core_flow  # noqa: E402

TICK = {"WIN": 5.0, "WDO": 0.5}
START, END = "2026-01-02", "2026-11-11"


# ───────────────────────── decomposição M1 (cópia de core/profit_min_decomp.py com pas configurável) ─────────────

def _decomp(a, asset, pas_const=None):
    is_win = asset == "WIN"
    tick_sz = TICK[asset]
    o, h, l, c = (a[k].astype(np.float64) for k in ("open", "high", "low", "close"))
    bq, sq = a["buy_qty"].astype(np.float64), a["sell_qty"].astype(np.float64)
    btr = np.maximum(1, a["buy_trd"].astype(np.int64))
    st = np.maximum(1, a["sell_trd"].astype(np.int64))
    bl, sl = bq / btr, sq / st
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
    pb = np.clip(0.28 + 0.42 * lwr + np.where(c >= o, 0.12, -0.05), 0.10, 0.78)
    ps = np.clip(0.28 + 0.42 * uwr + np.where(c <= o, 0.12, -0.05), 0.10, 0.78)
    if pas_const is not None:
        pb = np.full_like(pb, pas_const)
        ps = np.full_like(ps, pas_const)
    inst_aggr = bq * w_inst_b - sq * w_inst_s
    inst_pass = sq * pb * (w_ret_s + 0.5 * w_hft_s) - bq * ps * (w_ret_b + 0.5 * w_hft_b)
    ret_d = bq * w_ret_b - sq * w_ret_s
    return inst_aggr, inst_pass, ret_d, pb, ps


def _minutes(arr, iso_date):
    from datetime import datetime, timezone
    ts_raw = np.round((arr["dt"] - 25569.0) * 86400.0).astype(np.int64)
    ts_min = ((ts_raw + 30) // 60) * 60
    day_epoch = int(datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    mod = (ts_min - day_epoch) // 60
    m = (mod >= 540) & (mod <= 1105)
    return arr[m], mod[m]


@lru_cache(maxsize=2)
def m1_raw(asset):
    from core.profit_wall_players_engine import _load_profit_min_index
    idx = _load_profit_min_index(asset)
    out = {}
    for d in sorted(idx):
        if not (START <= d <= END) or idx[d].get("m1") is None:
            continue
        a, mod = _minutes(idx[d]["m1"], d)
        if len(a):
            out[d] = (a, mod)
    return out


@lru_cache(maxsize=2)
def pas_mean(asset):
    """Constante passiva = média das frações pb e ps (com pavio) no período, ponderada por minuto."""
    vals = []
    for d, (a, _) in m1_raw(asset).items():
        _, _, _, pb, ps = _decomp(a, asset)
        vals.append(np.r_[pb, ps])
    return float(np.mean(np.concatenate(vals)))


@lru_cache(maxsize=4)
def inst_m5(asset, mode):
    """{date: {"HH:MM": (inst_aggr, inst_pass, ret, buy_qty, sell_qty)}} somado em baldes de 5 min.
    mode = "wick" (fórmula original) ou "const" (frações passivas constantes)."""
    pc = None if mode == "wick" else pas_mean(asset)
    out = {}
    for d, (a, mod) in m1_raw(asset).items():
        ia, ip, rd, _, _ = _decomp(a, asset, pc)
        b5 = (mod // 5) * 5
        dd = {}
        for k in np.unique(b5):
            s = b5 == k
            dd[f"{int(k) // 60:02d}:{int(k) % 60:02d}"] = (float(ia[s].sum()), float(ip[s].sum()), float(rd[s].sum()),
                                                        float(a["buy_qty"][s].sum()), float(a["sell_qty"][s].sum()))
        out[d] = dd
    return out


def parity(asset, data):
    """Compara o recálculo 'wick' com os campos do div_wall_v1. Devolve estatísticas e dias sem paridade."""
    W = inst_m5(asset, "wick")
    tot = ok = 0
    bad_days, miss_days = [], []
    for d, (bars, _, _) in data.items():
        if d not in W:
            miss_days.append(d)
            continue
        nb = 0
        for b in bars:
            x = W[d].get(str(b["time"])[:5])
            tot += 1
            if x is None:
                nb += 1
                continue
            ref = (b["inst_aggr_delta"], b["inst_pass_delta"], b["ret_delta_bar"], b["buy_vol"], b["sell_vol"])
            if all(abs(u - v) <= 1.0 + 1e-6 * abs(v) for u, v in zip(x, ref)):
                ok += 1
            else:
                nb += 1
        if nb:
            bad_days.append((d, nb, len(bars)))
    return dict(bars=tot, ok=ok, bad_days=bad_days, miss_days=miss_days)


# ───────────────────────── pipeline comum ─────────────────────────

PIPE = dict(af=0.50, as_=2.0 / 11.0, mt=0.55, mi=0.45)   # memória/mistura da onda (fixas, exceto no reajuste)


def _pipeline(bars, forces, extra=None):
    af, as_, mt, mi = PIPE["af"], PIPE["as_"], PIPE["mt"], PIPE["mi"]
    out = []
    cum = ef = es = 0.0
    for i, (b, f) in enumerate(zip(bars, forces)):
        f1 = forces[i - 1] if i >= 1 else f
        f2 = forces[i - 2] if i >= 2 else f1
        imp3 = 0.45 * f + 0.35 * f1 + 0.20 * f2
        cum += f
        if i == 0:
            ef = es = cum
        else:
            ef = af * cum + (1 - af) * ef
            es = as_ * cum + (1.0 - as_) * es
        nb = dict(b)
        nb.update(force=f, impulse3=imp3, wave=mt * (ef - es) + mi * imp3)
        if extra:
            nb.update(extra[i])
        out.append(nb)
    return out


def _parts(b, asset):
    o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
    rng = max(h - l, TICK[asset])
    bv, sv = float(b.get("buy_vol", 0.0)), float(b.get("sell_vol", 0.0))
    tv = max(1.0, bv + sv)
    lw, uw = max(0.0, min(o, c) - l), max(0.0, h - max(o, c))
    wyk = sv * ((c - l) / rng) * (0.80 + 1.40 * (lw / rng)) - bv * ((h - c) / rng) * (0.80 + 1.40 * (uw / rng))
    is_win = asset == "WIN"
    bl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
    sl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))
    porte = tv * ((bl - sl) / max(0.5, bl + sl)) * 2.2
    inst = 0.55 * float(b.get("inst_aggr_delta", 0.0)) + 1.15 * float(b.get("inst_pass_delta", 0.0)) \
        - 0.85 * float(b.get("ret_delta_bar", 0.0))
    return dict(o=o, h=h, l=l, c=c, rng=rng, bv=bv, sv=sv, tv=tv, lw=lw, uw=uw, wyk=wyk, porte=porte, inst=inst)


class Ctx:
    """Contexto: a assinatura compute_flow(bars, asset) não traz a data; ela é achada pela impressão digital das
    3 primeiras barras (fechamento + agressão) no div_wall_v1."""
    date = None
    shuffle_seed = 11


@lru_cache(maxsize=2)
def _fingerprints(asset):
    from research.div_wall.data import load_asset
    fp = {}
    for d, (bars, _, _) in load_asset(asset, "M5").items():
        fp[tuple((str(b["time"])[:5], float(b["close"]), float(b["buy_vol"])) for b in bars[:3])] = d
    return fp


def _set_date(bars, asset):
    key = tuple((str(b["time"])[:5], float(b["close"]), float(b.get("buy_vol", 0.0))) for b in bars[:3])
    d = _fingerprints(asset).get(key)
    if d is None:
        raise KeyError(f"pregão não identificado ({asset}, {key[:1]})")
    Ctx.date = d


def _inst_const(bars, asset):
    C = inst_m5(asset, "const").get(Ctx.date)
    if C is None:
        raise KeyError(f"sem M1 bruto para {asset} {Ctx.date}")
    out = []
    for b in bars:
        x = C.get(str(b["time"])[:5])
        out.append(0.0 if x is None else 0.55 * x[0] + 1.15 * x[1] - 0.85 * x[2])
    return out


def make(name):
    """Devolve flow(bars, asset) da variante."""
    if name == "A_BASE":
        return core_flow

    def flow(bars, asset):
        if name in ("C_SEM_OHLC", "D_MIX", "X_INST_SEM_PAVIO", "E3_EMBARALHADO"):
            _set_date(bars, asset)
        P = [_parts(b, asset) for b in bars]
        if name == "A_BASE_P":            # base pelo pipeline próprio (sem arredondamento), p/ o reajuste
            F = [0.45 * p["wyk"] + 0.25 * p["porte"] + 0.30 * p["inst"] for p in P]
        elif name == "B_PURO":
            F = [p["bv"] - p["sv"] for p in P]
        elif name in ("C_SEM_OHLC", "D_MIX", "X_INST_SEM_PAVIO"):
            ic = _inst_const(bars, asset)
            if name == "C_SEM_OHLC":
                F = [(0.25 * p["porte"] + 0.30 * i) / 0.55 for p, i in zip(P, ic)]
            elif name == "D_MIX":
                F = [0.45 * (p["bv"] - p["sv"]) + 0.25 * p["porte"] + 0.30 * i for p, i in zip(P, ic)]
            else:
                F = ic
        elif name == "E1_PLAC_GEOM":     # geometria do Wyckoff com volume constante (só preço)
            F = [((p["c"] - p["l"]) / p["rng"]) * (0.80 + 1.40 * p["lw"] / p["rng"])
                 - ((p["h"] - p["c"]) / p["rng"]) * (0.80 + 1.40 * p["uw"] / p["rng"]) for p in P]
        elif name == "E2_PLAC_CORPO":    # corpo do candle (só preço)
            F = [p["c"] - p["o"] for p in P]
        elif name == "E3_EMBARALHADO":   # força da base embaralhada dentro do pregão (mata o timing)
            base = [0.45 * p["wyk"] + 0.25 * p["porte"] + 0.30 * p["inst"] for p in P]
            rs = np.random.RandomState(int(Ctx.date.replace('-', '')) % 100000 + Ctx.shuffle_seed)
            F = list(np.asarray(base)[rs.permutation(len(base))])
        elif name == "X_WYCKOFF":
            F = [p["wyk"] for p in P]
        elif name == "X_PORTE":
            F = [p["porte"] for p in P]
        elif name == "X_INST_PAVIO":
            F = [p["inst"] for p in P]
        elif name == "X_BASE_SEM_WYK":   # porte + inst ORIGINAL (com pavio), sem Wyckoff
            F = [(0.25 * p["porte"] + 0.30 * p["inst"]) / 0.55 for p in P]
        else:
            raise ValueError(name)
        return _pipeline(bars, [float(x) for x in F])
    return flow


MAIN = ["A_BASE", "B_PURO", "C_SEM_OHLC", "D_MIX", "E1_PLAC_GEOM", "E2_PLAC_CORPO", "E3_EMBARALHADO"]
DIAG = ["X_WYCKOFF", "X_PORTE", "X_INST_PAVIO", "X_INST_SEM_PAVIO", "X_BASE_SEM_WYK"]
ALL = MAIN + DIAG
