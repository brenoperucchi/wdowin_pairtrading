"""
Fase 2a: grade do gate no IS (jan–jul) para as 31 versões. Os dados são cortados em 01/08 (mt5_loader),
então nenhuma barra do OOS entra no cálculo.
Cada versão: 2 linhas de base (sem filtro · filtro atual) + 2×3×3×2×4×2×2 = 576 combinações do gate (v2).
Todas as linhas exigem dia coberto pela tabela do gate (mesmos dias para base e gate).
Saída: research/div_gate/results/grid_is.csv
Uso: python -m research.div_gate.bt_gate_grid [workers]
"""
from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

START, IS_END = "2026-01-02", "2026-07-31"
CUTOFF = "2026-08-01 00:00"
OUT = os.path.join(ROOT, "research", "div_gate", "results")

_MK = _FT = None


def combos(asset, has_flow):
    from research.div_gate import gate as G
    out = []
    for mode, N, k, R, L, cf, fl in itertools.product(("EXIGIR", "VETAR"), G.JANELAS, G.WAVE_K, G.RADIUS[asset],
                                                      G.NWE_L, G.CONFIRM, (False, True)):
        if fl and not has_flow:
            continue
        out.append(dict(mode=mode, N=N, k=k, R=R, L=L, conf=cf, flow=fl))
    return out


def AND(*fs):
    fs = [f for f in fs if f is not None]
    return lambda d, t, s: all(f(d, t, s) for f in fs)


def _init():
    global _MK, _FT
    import pandas as pd_
    from core.setups_runner import _load_market, _window
    from research.flow_window_asg.flow_filters import load_flow_tables
    ctx = _window(START, IS_END, pd_.Timestamp(CUTOFF), None)
    ctx.__enter__()  # mantém corte/janela durante toda a vida do processo
    _MK = _load_market()
    _FT, _ = load_flow_tables("min")


def run_one(vid, gate_spec, flow_on):
    """Trades IS de uma versão com o gate (`gate_spec` dict ou None) e/ou o filtro atual."""
    from research.div_gate import gate as G
    from research.div_gate.versions import VERSIONS, run_version
    from research.flow_window_asg.flow_filters import make_sig_filter
    asset, _, _, _, _, flt = VERSIONS[vid]
    cov = G.coverage_filter(asset)
    f_flow = make_sig_filter(_FT, asset, flt) if (flow_on and flt and vid != "WIN_E2") else None
    if vid == "WIN_E2" and flow_on:
        f_flow = make_sig_filter(_FT, asset, flt)
    g = None
    if gate_spec is not None:
        g = G.make_gate(asset, (gate_spec["k"], gate_spec["R"], gate_spec["L"], gate_spec["conf"]), gate_spec["N"],
                        gate_spec["mode"], gate_spec.get("inverted", False))
        if "placebo" in gate_spec:
            g = gate_spec["placebo"]
    return run_version(vid, _MK, _FT, AND(cov, f_flow, g), flow_on, START, IS_END)


def work(vid):
    from research.div_gate.versions import VERSIONS
    from research.setup_parity.bt_32_slots import stats
    t0 = time.time()
    asset, fam, _, _, _, flt = VERSIONS[vid]
    rows = []
    for name, fl in (("BASE_SEM_FILTRO", False), ("BASE_FILTRO_ATUAL", True)):
        if fl and not flt:
            continue
        rows.append(dict(vid=vid, asset=asset, family=fam, kind=name, mode="", N=0, k=0, R=0, L=0, conf="", flow=fl,
                         **stats(run_one(vid, None, fl))))
    for c in combos(asset, bool(flt)):
        rows.append(dict(vid=vid, asset=asset, family=fam, kind="GATE", **c, **stats(run_one(vid, c, c["flow"]))))
    return vid, rows, time.time() - t0


def main(workers=6):
    from research.div_gate.versions import VERSIONS
    os.makedirs(OUT, exist_ok=True)
    order = sorted(VERSIONS, key=lambda v: VERSIONS[v][2] != "sg")  # sg_sim (mais lento) primeiro
    all_rows = []
    with mp.Pool(workers, initializer=_init) as pool:
        for vid, rows, dt in pool.imap_unordered(work, order):
            all_rows += rows
            b = rows[0]
            best = max((r for r in rows if r["kind"] == "GATE"), key=lambda r: r["ret_dd"])
            print(f"{vid}: base {b['ops']} tr RetDD {b['ret_dd']} | melhor gate pontual RetDD {best['ret_dd']} "
                  f"({best['ops']} tr) · {dt / 60:.1f} min", flush=True)
            pd.DataFrame(all_rows).to_csv(os.path.join(OUT, "grid_is.csv"), index=False)
    print("GRADE IS completa:", len(all_rows), "linhas")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
