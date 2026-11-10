"""
COMPARATIVO COMPLETO DAS 11 ESTRATÉGIAS COM E SEM FILTROS NWE
=============================================================
Usa exatamente a mesma métrica e simuladores de `backtest_11_flow_filters.py`:
  WIN: EST-01, EST-04, EST-07, EST-13, EST-14, EST-15, EST-16
  WDO: WDO-02, WDO-07, WDO-09, WDO-10

Filtros NWE avaliados:
  0_BASE_ATUAL       : Sem filtro NWE extra (Baseline atual do MT5)
  1_NWE_SLOPE_FAVOR  : Slope da NWE50 a favor do trade (>0 compra, <0 venda)
  2_NWE_DUAL_SLOPE   : Slope da NWE30 e NWE50 ambos a favor
  3_NWE_ANTI_CRASH   : Não opera contra NWE acelerada (evita faca caindo)
  4_NWE_ROOM_70      : Exige espaço até a banda oposta (pos50 <= 0.70 / >= 0.30)
  5_NWE_VOL_MIN      : Exige largura mínima das bandas NWE50 (>= P20)
"""
import os
import sys
import functools
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
import research.optimizers.optimize_existing_16_setups as o16
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
import research.optimizers.sg_sim as sg_sim
import research.optimizers.wdo_mt5_sim as wsim

START, END = "2026-05-11", "2026-11-04"
WIN_COST_PTS, WDO_COST_PTS = 10.0, 0.5

WIN_CFG = {
    1: ("3p", "CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
    4: ("wdo", "ALIGNED", "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL"),
    7: ("3p", "CURRENT", "BE_WALL_SHIELD", 15.0, "TP_CURRENT"),
}
WIN_SG = (13, 14, 15, 16)
WDO_SLOTS = (2, 7, 9, 10)

NWE_FILTERS = [
    "0_BASE_ATUAL",
    "1_NWE_SLOPE_FAVOR",
    "2_NWE_DUAL_SLOPE",
    "3_NWE_ANTI_CRASH",
    "4_NWE_ROOM_70",
    "5_NWE_VOL_MIN",
]


def build_nwe_lut(dates, t_mins, closes, n50_u, n50_l, n50_s, n30_s, is_win=True):
    bw50 = np.maximum(1.0 if is_win else 0.5, n50_u - n50_l)
    pos50 = (closes - n50_l) / bw50
    p20 = np.percentile(bw50, 20)
    crash_thr = 7.0 if is_win else 0.30

    luts = {}
    for mode in NWE_FILTERS:
        if mode == "0_BASE_ATUAL":
            luts[mode] = None
            continue
        elif mode == "1_NWE_SLOPE_FAVOR":
            mb = n50_s > 0.0
            ms = n50_s < 0.0
        elif mode == "2_NWE_DUAL_SLOPE":
            mb = (n50_s > 0.0) & (n30_s > 0.0)
            ms = (n50_s < 0.0) & (n30_s < 0.0)
        elif mode == "3_NWE_ANTI_CRASH":
            mb = n50_s > -crash_thr
            ms = n50_s < crash_thr
        elif mode == "4_NWE_ROOM_70":
            mb = pos50 <= 0.70
            ms = pos50 >= 0.30
        elif mode == "5_NWE_VOL_MIN":
            mb = bw50 >= p20
            ms = bw50 >= p20

        lb = {(str(dates[i]), int(t_mins[i])): bool(mb[i]) for i in range(len(dates))}
        ls = {(str(dates[i]), int(t_mins[i])): bool(ms[i]) for i in range(len(dates))}

        def make_f(b_map, s_map):
            def _f(d_str, tm, s_dir):
                return b_map.get((str(d_str), int(tm)), True) if s_dir == 1 else s_map.get((str(d_str), int(tm)), True)
            return _f

        luts[mode] = make_f(lb, ls)
    return luts


def daily_series(tr: pd.DataFrame, key="pnl"):
    return tr.groupby("date")[key].sum().sort_index()


def metrics(tr: pd.DataFrame, key="pnl"):
    if tr.empty:
        return dict(trades=0, wr=0.0, pf=0.0, net=0, dd=0, ret_dd=0.0)
    p = tr[key]
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    d = daily_series(tr, key)
    cum = d.cumsum()
    dd = float((cum.cummax().clip(lower=0) - cum).max())
    net = float(p.sum())
    return dict(
        trades=int(len(tr)),
        wr=round(100.0 * (p > 0).mean(), 1),
        pf=round(gw / gl, 2) if gl > 0 else 99.0,
        net=int(round(net)),
        dd=int(round(dd)),
        ret_dd=round(net / dd, 2) if dd > 0 else 99.0,
    )


def main():
    # 1. Carrega WIN
    df, gex = o16.load_win_and_wdo_aligned()
    c = df["close"].values
    n50 = disc.compute_nwe_series(c, lookback=50, bw=5.0, mult=2.0)
    n30 = disc.compute_nwe_series(c, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(c).diff()
    rsi7 = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values
    A = (df, gex, n50[0], n50[1], n50[2], n50[4], n30[0], n30[1], n30[2], n30[4], rsi7)

    win_luts = build_nwe_lut(df["session_date"].values, df["t_min"].values, c, n50[1], n50[2], n50[4], n30[4], is_win=True)

    # SmartGrids M1 cache
    sg_sim.load_m5_m1_wdo_gex = functools.lru_cache(maxsize=1)(sg_sim.load_m5_m1_wdo_gex)

    # 2. Carrega WDO
    wdf, wgex = wsim.load_wdo_mt5_raw()
    wc = wdf["close"].values
    w50 = wsim.compute_nwe_series(wc, lookback=50, bw=5.0, mult=2.0)
    w30 = wsim.compute_nwe_series(wc, lookback=30, bw=3.0, mult=1.6)
    wrsi = wsim.compute_rsi7_series(wc)

    wdo_luts = build_nwe_lut(wdf["session_date"].values, wdf["t_min"].values, wc, w50[1], w50[2], w50[4], w30[4], is_win=False)

    rows = []
    for fn in NWE_FILTERS:
        f_win = win_luts[fn]
        f_wdo = wdo_luts[fn]
        print(f"Simulando {fn}...", flush=True)

        for k, (eng, ent, be, buf, tp) in WIN_CFG.items():
            if eng == "3p":
                tr, _ = o16.simulate_single_est_slot(k, *A, entry_override=ent, be_mode=be, wall_shield_buf=buf,
                                                      tp_mode=tp, cost_pts=WIN_COST_PTS, sig_filter=f_win)
            else:
                tr, _ = simulate_aligned_win_wdo_slot(k, *A, be_mode=be, wall_shield_buf=buf, tp_mode=tp,
                                                      entry_override=ent, cost_pts=WIN_COST_PTS, sig_filter=f_win)
            for t in tr:
                if START <= t["date"] <= END:
                    rows.append(dict(filter=fn, strat=f"EST-{k:02d}", date=t["date"], pnl=float(t["pnl_brl"])))

        sg = sg_sim.run(slots=WIN_SG, start=START, cost_pts=WIN_COST_PTS, sig_filter=f_win)
        for _, t in sg.iterrows():
            d = pd.Timestamp(t["t_in"]).strftime("%Y-%m-%d")
            if START <= d <= END:
                rows.append(dict(filter=fn, strat=f"EST-{int(t['k']):02d}", date=d, pnl=float(t["brl"])))

        for sid in WDO_SLOTS:
            tr = wsim.simulate_wdo_core_slot(sid, wdf, wgex, w50[0], w50[1], w50[2], w50[4], w30[0], w30[1], w30[2], w30[4],
                                             wrsi, start_date=START, end_date=END, cost_pts=WDO_COST_PTS, sig_filter=f_wdo)
            for t in tr:
                rows.append(dict(filter=fn, strat=f"WDO-{sid:02d}", date=t["date"], pnl=float(t["pnl_brl"])))

    df_all = pd.DataFrame(rows)
    out_dir = os.path.join(ROOT_DIR, "data", "reports", "tp_sl_be_optimization")
    os.makedirs(out_dir, exist_ok=True)

    summary_rows = []
    all_strats = ["EST-01", "EST-04", "EST-07", "EST-13", "EST-14", "EST-15", "EST-16", "WDO-02", "WDO-07", "WDO-09", "WDO-10"]
    for st in all_strats:
        for fn in NWE_FILTERS:
            sub = df_all[(df_all["strat"] == st) & (df_all["filter"] == fn)]
            m = metrics(sub)
            summary_rows.append(dict(strat=st, filter=fn, **m))

    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(os.path.join(out_dir, "all_11_nwe_filters_summary.csv"), index=False)
    print("\n=== TABELA RESUMO SALVA ===")
    print(df_sum.to_string(index=False))


if __name__ == "__main__":
    main()

