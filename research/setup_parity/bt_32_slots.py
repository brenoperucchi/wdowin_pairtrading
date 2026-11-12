"""
BT dos 32 sinais dos EAs (16 slots WIN `Jumba_GEX_NWE_Core` + 16 slots WDO `Jumba_WDO_GEX_NWE_Core`),
com os mesmos simuladores alinhados ao MT5 e o mesmo fluxo `.min` (filtro estrito) do runner único.

Configuração de cada slot = a do EA (sem os overrides de BE/TP dos 14 registrados):
  WIN 1–12: `o16.simulate_single_est_slot` (CURRENT / BE_ZERO / TP_CURRENT) · WIN 13–16: `sg_sim`
  WDO 1–16: `wdo_mt5_sim.simulate_wdo_core_slot`
Filtro de fluxo: escolhido SÓ no IS (jan–jul) entre os 18, pelo Ret/DD do IS (mín. 40 trades no IS e lucro IS > 0);
o OOS (ago–6/nov) mostra o resultado do filtro escolhido sem reotimizar.
Saída: results/bt_32_slots_summary.csv, results/bt_32_slots_trades.csv
Uso: python -m research.setup_parity.bt_32_slots
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.setups_runner import _load_market, _window  # noqa: E402
from research.flow_window_asg import generate_portfolio_6_json as gp  # noqa: E402
from research.flow_window_asg.flow_filters import FILTER_NAMES, MISSING_FLOW_LOOKUPS, load_flow_tables, make_sig_filter  # noqa: E402
from research.optimizers import sg_sim  # noqa: E402

START, END, SPLIT = "2026-01-02", "2026-11-06", "2026-07-31"
MIN_IS_TRADES = 40
OUT = os.path.join(ROOT, "research", "setup_parity", "results")


def stats(trs, lo=None, hi=None):
    df = pd.DataFrame(trs)
    if len(df):
        if lo:
            df = df[df["date"] > lo]
        if hi:
            df = df[df["date"] <= hi]
    if not len(df):
        return dict(ops=0, wr=0.0, pf=0.0, net=0.0, mdd=0.0, ret_dd=0.0, pos_m="0/0")
    df = df.sort_values(["date", "exit_time"])
    p = df["brl_1c"].values
    eq = np.cumsum(p)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = df.groupby("month")["brl_1c"].sum()
    return dict(ops=len(df), wr=round(100 * float((p > 0).mean()), 1), pf=round(g / l, 2) if l else 99.0,
                net=round(float(eq[-1]), 0), mdd=round(mdd, 0),
                ret_dd=round(float(eq[-1]) / mdd, 2) if mdd else 99.0, pos_m=f"{int((m > 0).sum())}/{len(m)}")


def run_slot(asset, k, mk, ft, fname):
    df_win, gex_win, n50w, n30w, rsi7w, df_wdo, gex_wdo, n50d, n30d, rsi7d = mk
    sf = make_sig_filter(ft, asset, fname)
    sid = f"{asset}_S{k:02d}"
    if asset == "WIN" and k <= 12:
        A = (df_win, gex_win, n50w[0], n50w[1], n50w[2], n50w[4], n30w[0], n30w[1], n30w[2], n30w[4], rsi7w)
        tr, _ = gp.o16.simulate_single_est_slot(k, *A, cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START)
        out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
    elif asset == "WIN":
        out = gp.format_sg_trades(sg_sim.run(slots=(k,), start=START, cost_pts=gp.COST_WIN_PTS, sig_filter=sf))
    else:
        out = gp.format_wdo_trades(gp.wsim.simulate_wdo_core_slot(
            k, df_wdo, gex_wdo, n50d[0], n50d[1], n50d[2], n50d[4], n30d[0], n30d[1], n30d[2], n30d[4], rsi7d,
            start_date=START, end_date=END, cost_pts=gp.COST_WDO_PTS, sig_filter=sf), sid)
    return [t for t in out if START <= t["date"] <= END]


def main():
    os.makedirs(OUT, exist_ok=True)
    ft, _ = load_flow_tables("min")
    rows, all_tr = [], []
    with _window(START, END, None, None):
        mk = _load_market()
        for asset in ("WIN", "WDO"):
            for k in range(1, 17):
                sid = f"{asset}_S{k:02d}"
                res = {fn: run_slot(asset, k, mk, ft, fn) for fn in FILTER_NAMES}
                base = res["0_BASE_MT5"]
                cands = []
                for fn in FILTER_NAMES[1:]:
                    s_is = stats(res[fn], hi=SPLIT)
                    if s_is["ops"] >= MIN_IS_TRADES and s_is["net"] > 0:
                        cands.append((s_is["ret_dd"], fn))
                best = max(cands)[1] if cands else None
                b, b_is, b_oos = stats(base), stats(base, hi=SPLIT), stats(base, lo=SPLIT)
                row = {"sid": sid, **{f"base_{x}": v for x, v in b.items()},
                       "base_is_net": b_is["net"], "base_oos_net": b_oos["net"], "base_oos_pf": b_oos["pf"],
                       "flow_filter": best or "—"}
                if best:
                    f, f_is, f_oos = stats(res[best]), stats(res[best], hi=SPLIT), stats(res[best], lo=SPLIT)
                    row.update({**{f"flow_{x}": v for x, v in f.items()}, "flow_is_net": f_is["net"],
                                "flow_is_ret_dd": f_is["ret_dd"], "flow_oos_ops": f_oos["ops"],
                                "flow_oos_net": f_oos["net"], "flow_oos_pf": f_oos["pf"]})
                    all_tr += [dict(t, sid=sid, mode="flow", filter=best) for t in res[best]]
                all_tr += [dict(t, sid=sid, mode="base", filter="0_BASE_MT5") for t in base]
                rows.append(row)
                print(f"{sid}: base {b['ops']} tr PF {b['pf']} R$ {b['net']} | fluxo {best} "
                      f"{row.get('flow_ops', 0)} tr PF {row.get('flow_pf', 0)} OOS R$ {row.get('flow_oos_net', 0)}",
                      flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "bt_32_slots_summary.csv"), index=False)
    pd.DataFrame(all_tr).to_csv(os.path.join(OUT, "bt_32_slots_trades.csv"), index=False)
    print("consultas de fluxo sem dado (bloqueadas):", dict(MISSING_FLOW_LOOKUPS))


if __name__ == "__main__":
    main()
