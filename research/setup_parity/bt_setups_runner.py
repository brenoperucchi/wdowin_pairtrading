"""
BT oficial novo dos setups registrados pelo runner único (fluxo `.min`, filtros 1–18 ativos, filtro estrito).
Compara com os números do JSON antigo (`portfolio_4_sistematicas_equity_v1.json` → all_11_comparison).
Não sobrescreve o JSON de produção. Saída: results/bt_runner_2026_summary.csv e results/bt_runner_2026_trades.csv
Uso: python -m research.setup_parity.bt_setups_runner
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.setups_runner import run_setups  # noqa: E402
from research.flow_window_asg.flow_filters import MISSING_FLOW_LOOKUPS  # noqa: E402

START, END, SPLIT = "2026-01-02", "2026-11-06", "2026-07-31"
OUT = os.path.join(ROOT, "research", "setup_parity", "results")


def stats(trs):
    if not trs:
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, mdd=0.0, ret_dd=0.0, pos_m="0/0", is_net=0.0, oos_net=0.0)
    df = pd.DataFrame(trs).sort_values(["date", "exit_time"])
    p = df["brl_1c"].values
    eq = np.cumsum(p)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = df.groupby("month")["brl_1c"].sum()
    return dict(ops=len(df), wr=round(100 * float((p > 0).mean()), 1), pf=round(g / l, 2) if l else 99.0,
                net=round(float(eq[-1]), 0), mdd=round(mdd, 0), ret_dd=round(float(eq[-1]) / mdd, 2) if mdd else 99.0,
                pos_m=f"{int((m > 0).sum())}/{len(m)}",
                is_net=round(float(df[df["date"] <= SPLIT]["brl_1c"].sum()), 0),
                oos_net=round(float(df[df["date"] > SPLIT]["brl_1c"].sum()), 0))


def main():
    os.makedirs(OUT, exist_ok=True)
    flow = run_setups(START, END, use_flow=True)
    miss = dict(MISSING_FLOW_LOOKUPS)
    base = run_setups(START, END, use_flow=False)
    old = {s["id"]: s for s in json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"),
                                              encoding="utf-8"))["all_11_comparison"]}
    rows, all_tr = [], []
    for sid in sorted(flow):
        f, b = stats(flow[sid]), stats(base[sid])
        o = old.get(sid, {}).get("with_flow", {})
        rows.append({"sid": sid, **{f"flow_{k}": v for k, v in f.items()}, **{f"base_{k}": v for k, v in b.items()},
                     "json_ops": o.get("ops"), "json_net": o.get("tot_brl_1c"), "json_pf": o.get("pf")})
        all_tr += [dict(t, sid=sid, mode="flow") for t in flow[sid]] + [dict(t, sid=sid, mode="base") for t in base[sid]]
    S = pd.DataFrame(rows)
    S.to_csv(os.path.join(OUT, "bt_runner_2026_summary.csv"), index=False)
    pd.DataFrame(all_tr).to_csv(os.path.join(OUT, "bt_runner_2026_trades.csv"), index=False)
    cols = ["sid", "flow_ops", "flow_wr", "flow_pf", "flow_net", "flow_mdd", "flow_pos_m", "flow_is_net", "flow_oos_net",
            "base_ops", "base_pf", "base_net", "json_ops", "json_pf", "json_net"]
    with pd.option_context("display.width", 250):
        print(S[cols].to_string(index=False))
    print("consultas de fluxo sem dado (bloqueadas):", miss)


if __name__ == "__main__":
    main()
