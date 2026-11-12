"""
Grade de otimização IN-SAMPLE (jan–jul/2026) do setup Divergência Preço × Fluxo na Wall.

Regras pré-registradas (não mudar depois de ver o OOS):
  - Só dias IS. O OOS (ago–nov) nunca é lido aqui.
  - Elegível: >= 80 trades no IS, PF >= 1.30, MDD > 0.
  - Ranking por "platô": mediana do Ret/DD da config e de todos os vizinhos (configs que
    diferem em UM parâmetro). Isso penaliza picos isolados.
  - Todas as configs testadas ficam registradas em `results/{asset}_is_grid.csv`.

Uso: python -m research.div_wall.bt_grid [WIN|WDO]
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
    ExitParams, SignalParams, build_trade, compute_flow, detect_signals, simulate_trade,
)
from research.div_wall.data import load_asset, metrics, split  # noqa: E402

OUT = os.path.join(ROOT, "research", "div_wall", "results")

SIG_GRID = {
    "pivot_right": [1, 2],
    "wave_k": [0.25, 0.5, 1.0],
    "wall_radius": {"WIN": [60.0, 100.0, 150.0], "WDO": [2.0, 3.0, 4.5]},
    "wall_types": [("Wall", "MidWall"), ("Wall",)],
    "nwe_filter": ["none", "extreme", "slope_with", "slope_against"],
}
EXIT_GRID = {
    "sl_mode": ["pivot", "wall"],
    "tp": [("rr", 1.0), ("rr", 1.5), ("rr", 2.0), ("next_wall", None), ("nwe_center", None), ("nwe_band", None)],
    "be_trigger_r": [None, 1.0],
}
MIN_TRADES, MIN_PF = 80, 1.30


def sig_combos(asset):
    keys = ["pivot_right", "wave_k", "wall_radius", "wall_types", "nwe_filter"]
    vals = [SIG_GRID[k][asset] if isinstance(SIG_GRID[k], dict) else SIG_GRID[k] for k in keys]
    for combo in itertools.product(*vals):
        yield dict(zip(keys, combo))


def exit_combos(asset):
    for sl_mode, (tp_mode, rr), be in itertools.product(EXIT_GRID["sl_mode"], EXIT_GRID["tp"], EXIT_GRID["be_trigger_r"]):
        kw = dict(sl_mode=sl_mode, tp_mode=tp_mode, be_trigger_r=be)
        if rr is not None:
            kw["rr"] = rr
        yield kw


_DATA = None


def _init(asset):
    global _DATA
    raw = split(load_asset(asset), "IS")
    _DATA = {d: (compute_flow(b, asset), w, n) for d, (b, w, n) in raw.items()}


def _eval_sig(args):
    asset, skw = args
    sp = SignalParams.default(asset, **skw)
    per_day = {d: detect_signals(fb, w, n, sp) for d, (fb, w, n) in _DATA.items()}
    rows = []
    for ekw in exit_combos(asset):
        ep = ExitParams.default(asset, **ekw)
        trades = []
        for d, sigs in per_day.items():
            fb, w, n = _DATA[d]
            for s in sigs:
                tr = build_trade(d, asset, s, fb, w, n, ep)
                if tr is not None:
                    trades.append(simulate_trade(tr, fb, n, ep))
        m = metrics(trades, asset)
        row = {**{f"s_{k}": ("+".join(v) if isinstance(v, tuple) else v) for k, v in skw.items()},
               **{f"e_{k}": v for k, v in ekw.items()}, **m}
        row["e_rr"] = ekw.get("rr")
        rows.append(row)
    return rows


def plateau(df: pd.DataFrame) -> pd.Series:
    """Mediana de Ret/DD da config + vizinhos que diferem em 1 parâmetro."""
    pcols = [c for c in df.columns if c.startswith(("s_", "e_"))]
    sdf = df[pcols].apply(lambda col: col.map(str))
    keyed = sdf.agg("|".join, axis=1)
    lut = dict(zip(keyed, df["ret_dd_eff"]))
    levels = {c: sorted(sdf[c].unique()) for c in pcols}
    scores = []
    for _, r in sdf.iterrows():
        vals = [lut["|".join(r.values)]]
        for ci, c in enumerate(pcols):
            for alt in levels[c]:
                if alt == r[c]:
                    continue
                k = list(r.values)
                k[ci] = alt
                v = lut.get("|".join(k))
                if v is not None:
                    vals.append(v)
        scores.append(float(np.median(vals)))
    return pd.Series(scores, index=df.index)


def main(asset):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    combos = [(asset, s) for s in sig_combos(asset)]
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) - 2), initializer=_init, initargs=(asset,)) as ex:
        for r in ex.map(_eval_sig, combos, chunksize=2):
            rows.extend(r)
    df = pd.DataFrame(rows)
    df["eligible"] = (df["trades"] >= MIN_TRADES) & (df["pf"] >= MIN_PF) & (df["mdd"] > 0)
    # Ret/DD efetivo: configs inelegíveis valem 0 no platô (vizinho ruim puxa a nota para baixo)
    df["ret_dd_eff"] = np.where(df["eligible"], df["ret_dd"], 0.0)
    df["plateau"] = plateau(df)
    df = df.sort_values(["eligible", "plateau", "ret_dd"], ascending=False)
    path = os.path.join(OUT, f"{asset}_is_grid.csv")
    df.to_csv(path, index=False)
    print(f"{asset}: {len(df)} configs em {time.time() - t0:.0f}s · elegíveis {int(df['eligible'].sum())} · salvo {path}")
    cols = [c for c in df.columns if c.startswith(("s_", "e_"))] + ["trades", "wr", "pf", "net", "mdd", "ret_dd", "pos_months", "plateau"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(df[df["eligible"]].head(15)[cols].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "WIN")
