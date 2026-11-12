"""
Grade IN-SAMPLE (jan–jul/2026) no M1: micro-divergência na Wall e spring/upthrust na Wall.

Critérios pré-registrados (iguais para os dois detectores, definidos antes de rodar):
  - Elegível: >= 120 trades no IS (~0,85/dia), PF >= 1,30, MDD > 0.
  - Ranking por platô (mediana do Ret/DD da config + vizinhos de 1 parâmetro; inelegível vale 0).
  - O OOS não é lido aqui.
Fase 2 (`div_strong`): mínimo de 50 trades, ver PREREG_M1_FASE2.md.
Uso: python -m research.div_wall.bt_grid_m1 [WIN|WDO] [div|spring|div_strong]
"""
from __future__ import annotations

import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.div_wall_signal import (  # noqa: E402
    ExitParams, SignalParams, SpringParams, build_trade, compute_flow, detect_signals, detect_springs, simulate_trade,
)
from research.div_wall.bt_grid import plateau  # noqa: E402
from research.div_wall.data import load_asset, metrics, split  # noqa: E402

OUT = os.path.join(ROOT, "research", "div_wall", "results")
MIN_TRADES, MIN_PF = 120, 1.30

M1_SIG_BASE = {"WIN": dict(max_ext=200.0, price_tol=25.0, cooldown=10),
               "WDO": dict(max_ext=6.0, price_tol=1.0, cooldown=10)}
EXIT_BASE = {"WIN": dict(sl_buf=15.0, sl_min=40.0, sl_max=150.0, tp_min=40.0, be_offset=5.0),
             "WDO": dict(sl_buf=0.5, sl_min=1.5, sl_max=5.0, tp_min=1.5, be_offset=0.5)}

DIV_GRID = {
    "pivot_right": [1, 2], "wave_k": [0.5, 1.0, 1.5],
    "wall_radius": {"WIN": [25.0, 40.0, 60.0], "WDO": [1.0, 1.5, 2.5]},
    "wall_types": [("Wall", "MidWall"), ("Wall",)],
    "nwe_filter": ["none", "extreme", "slope_with", "slope_against"],
}
DIV_STRONG_GRID = {  # Fase 2 — ver PREREG_M1_FASE2.md
    "pivot_right": [1, 2], "wave_k": [1.5, 2.0, 2.5, 3.0, 4.0],
    "wall_radius": {"WIN": [25.0, 40.0, 60.0], "WDO": [1.0, 1.5, 2.5]},
    "wall_types": [("Wall", "MidWall"), ("Wall",)],
    "nwe_filter": ["none", "slope_against", "extreme"],
}
MIN_TRADES_BY_KIND = {"div": 120, "spring": 120, "div_strong": 50}

SPRING_GRID = {
    "n_back": [2, 3, 5],
    "pierce": {"WIN": [(10.0, 60.0), (15.0, 120.0)], "WDO": [(0.5, 2.5), (0.5, 4.0)]},
    "wall_types": [("Wall", "MidWall"), ("Wall",)],
    "flow_mode": ["none", "force", "absorb", "wave_up"],
    "nwe_filter": ["none", "extreme", "slope_with", "slope_against"],
}
EXIT_GRID = {
    "sl_mode": ["pivot", "wall"],
    "tp": [("rr", 1.0), ("rr", 1.5), ("rr", 2.0), ("next_wall", None), ("nwe_center", None), ("nwe_band", None)],
    "be_trigger_r": [None, 1.0],
    "max_bars": [30, 60],
}


def _expand(grid, asset):
    keys = list(grid)
    vals = [grid[k][asset] if isinstance(grid[k], dict) else grid[k] for k in keys]
    for combo in itertools.product(*vals):
        yield dict(zip(keys, combo))


def exit_combos():
    for sl, (tp, rr), be, mb in itertools.product(*EXIT_GRID.values()):
        kw = dict(sl_mode=sl, tp_mode=tp, be_trigger_r=be, max_bars=mb)
        if rr is not None:
            kw["rr"] = rr
        yield kw


def make_sig(asset, kind, skw):
    if kind in ("div", "div_strong"):
        return SignalParams.default(asset, **M1_SIG_BASE[asset], **skw)
    kw = dict(skw)
    pmin, pmax = kw.pop("pierce")
    return SpringParams.default(asset, pierce_min=pmin, pierce_max=pmax, **kw)


_DATA = None


def _init(asset):
    global _DATA
    raw = split(load_asset(asset, "M1"), "IS")
    _DATA = {d: (compute_flow(b, asset), w, n) for d, (b, w, n) in raw.items()}


def _eval(args):
    asset, kind, skw = args
    sp = make_sig(asset, kind, skw)
    det = detect_springs if kind == "spring" else detect_signals
    per_day = {d: det(fb, w, n, sp) for d, (fb, w, n) in _DATA.items()}
    rows = []
    for ekw in exit_combos():
        ep = ExitParams.default(asset, **EXIT_BASE[asset], **ekw)
        trades = []
        for d, sigs in per_day.items():
            fb, w, n = _DATA[d]
            for s in sigs:
                tr = build_trade(d, asset, s, fb, w, n, ep)
                if tr is not None:
                    trades.append(simulate_trade(tr, fb, n, ep))
        m = metrics(trades, asset)
        row = {**{f"s_{k}": ("+".join(map(str, v)) if isinstance(v, tuple) else v) for k, v in skw.items()},
               **{f"e_{k}": v for k, v in ekw.items()}, **m}
        row["e_rr"] = ekw.get("rr")
        rows.append(row)
    return rows


def main(asset, kind):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    grid = {"div": DIV_GRID, "div_strong": DIV_STRONG_GRID, "spring": SPRING_GRID}[kind]
    combos = [(asset, kind, s) for s in _expand(grid, asset)]
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) - 2), initializer=_init, initargs=(asset,)) as ex:
        for r in ex.map(_eval, combos, chunksize=1):
            rows.extend(r)
    df = pd.DataFrame(rows)
    df["eligible"] = (df["trades"] >= MIN_TRADES_BY_KIND[kind]) & (df["pf"] >= MIN_PF) & (df["mdd"] > 0)
    df["ret_dd_eff"] = np.where(df["eligible"], df["ret_dd"], 0.0)
    df["plateau"] = plateau(df)
    df = df.sort_values(["eligible", "plateau", "ret_dd"], ascending=False)
    path = os.path.join(OUT, f"{asset}_m1_{kind}_is_grid.csv")
    df.to_csv(path, index=False)
    print(f"{asset} M1 {kind}: {len(df)} configs em {time.time() - t0:.0f}s · elegíveis {int(df['eligible'].sum())} · "
          f"PF mediano {df['pf'].median():.2f} · {path}")
    cols = [c for c in df.columns if c.startswith(("s_", "e_"))] + ["trades", "wr", "pf", "net", "mdd", "ret_dd", "pos_months", "plateau"]
    with pd.option_context("display.width", 260, "display.max_columns", 30):
        print(df[df["eligible"]].head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "WIN", sys.argv[2] if len(sys.argv) > 2 else "div")
