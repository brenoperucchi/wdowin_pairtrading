"""
Backtest das 11 estratégias da carteira com e sem os filtros de Fluxo/Janela do dashboard
=========================================================================================
Carteira (perfil Jumba_11_CARTEIRA_ALINHADA):
  WIN: EST-01, 04, 07, 13, 14, 15, 16     WDO: WDO-02, 07, 09, 10

- Simuladores alinhados ao MT5 (os mesmos validados trade a trade contra o Strategy Tester):
  optimize_existing_16_setups (EST-01/07), test_win_aligned_wdo_matrix (EST-04),
  sg_sim (EST-13..16, tick a tick M1) e wdo_mt5_sim (WDO).
- Filtros: os 6 filtros do dashboard (research/flow_window_asg/flow_filters.py) aplicados
  NA BARRA DE SINAL (b1) dentro do simulador (sinal bloqueado -> slot continua livre).
- Custos: R$ 2/contrato no WIN (10 pts) e R$ 5/contrato no WDO (0,5 pt).
- Período: 11/05/2026 a 04/11/2026, 1 lote base.
- Robustez: in-sample (IS) 11/05–31/08 e out-of-sample (OOS) 01/09–04/11. As escolhas de
  filtro/portfólio são feitas também só no IS e medidas no OOS.

Saídas: data/reports/flow_filters_11/*.csv  e  docs/BACKTEST_11_FLUXO_JANELA.md
"""
import os
import sys
import itertools
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
from research.flow_window_asg.flow_filters import load_flow_tables, make_sig_filter, FILTER_NAMES, FILTER_LABELS

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "flow_filters_11")
START, END = "2026-05-11", "2026-11-04"
IS_END = "2026-08-31"
WIN_COST_PTS, WDO_COST_PTS = 10.0, 0.5

WIN_CFG = {  # mesma configuração validada em verify_mt5_alignment.py (EST-07 atualizado p/ TP_MIDWALL)
    1: ("3p", "CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
    4: ("wdo", "ALIGNED", "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL"),
    7: ("3p", "CURRENT", "BE_WALL_SHIELD", 15.0, "TP_MIDWALL"),
}
WIN_SG = (13, 14, 15, 16)
WDO_SLOTS = (2, 7, 9, 10)
NAMES = {
    "EST-01": "Quebra/Absorção Mkt Wall", "EST-04": "Pullback Tendência WDO-Alinhado",
    "EST-07": "Absorção Mkt Wall NY", "EST-13": "SmartGrid GEX+NWE", "EST-14": "SmartGrid Vel 1+2L",
    "EST-15": "SmartGrid MainWall Z30", "EST-16": "SmartGrid MidWall",
    "WDO-02": "Scalper Híbrido CORE", "WDO-07": "Absorção Mkt Wall NY",
    "WDO-09": "Cluster NWE30+50 Limit Wall", "WDO-10": "Reversão NWE 12h-14h30",
}


# ──────────────────────────────────────────────────────────────────────────────
# Simulação
# ──────────────────────────────────────────────────────────────────────────────
def run_all_sims(flow):
    rows = []

    # WIN M5 (EST-01/04/07)
    df, gex = o16.load_win_and_wdo_aligned()
    c = df["close"].values
    n50 = disc.compute_nwe_series(c, lookback=50, bw=5.0, mult=2.0)
    n30 = disc.compute_nwe_series(c, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(c).diff()
    rsi7 = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values
    A = (df, gex, n50[0], n50[1], n50[2], n50[4], n30[0], n30[1], n30[2], n30[4], rsi7)

    # SmartGrids: carrega M1/M5 uma vez só
    sg_sim.load_m5_m1_wdo_gex = functools.lru_cache(maxsize=1)(sg_sim.load_m5_m1_wdo_gex)

    # WDO
    wdf, wgex = wsim.load_wdo_mt5_raw()
    wc = wdf["close"].values
    w50 = wsim.compute_nwe_series(wc, lookback=50, bw=5.0, mult=2.0)
    w30 = wsim.compute_nwe_series(wc, lookback=30, bw=3.0, mult=1.6)
    wrsi = wsim.compute_rsi7_series(wc)

    for fn in FILTER_NAMES:
        f_win = make_sig_filter(flow, "WIN", fn)
        f_wdo = make_sig_filter(flow, "WDO", fn)
        print(f"  simulando filtro {fn} ...", flush=True)

        for k, (eng, ent, be, buf, tp) in WIN_CFG.items():
            if eng == "3p":
                tr, _ = o16.simulate_single_est_slot(k, *A, entry_override=ent, be_mode=be, wall_shield_buf=buf,
                                                      tp_mode=tp, cost_pts=WIN_COST_PTS, sig_filter=f_win)
            else:
                tr, _ = simulate_aligned_win_wdo_slot(k, *A, be_mode=be, wall_shield_buf=buf, tp_mode=tp,
                                                      entry_override=ent, cost_pts=WIN_COST_PTS, sig_filter=f_win)
            for t in tr:
                if START <= t["date"] <= END:
                    lots = float(t["contracts"])
                    rows.append(dict(filter=fn, strat=f"EST-{k:02d}", asset="WIN", date=t["date"], lots=lots,
                                     pnl=float(t["pnl_brl"]), pnl_nocost=float(t["pnl_brl"]) + 2.0 * lots))

        sg = sg_sim.run(slots=WIN_SG, start=START, cost_pts=WIN_COST_PTS, sig_filter=f_win)
        for _, t in sg.iterrows():
            d = pd.Timestamp(t["t_in"]).strftime("%Y-%m-%d")
            if START <= d <= END:
                lots = float(t["lots"])
                rows.append(dict(filter=fn, strat=f"EST-{int(t['k']):02d}", asset="WIN", date=d, lots=lots,
                                 pnl=float(t["brl"]), pnl_nocost=float(t["brl"]) + 2.0 * lots))

        for sid in WDO_SLOTS:
            tr = wsim.simulate_wdo_core_slot(sid, wdf, wgex, w50[0], w50[1], w50[2], w50[4], w30[0], w30[1], w30[2], w30[4],
                                             wrsi, start_date=START, end_date=END, cost_pts=WDO_COST_PTS, sig_filter=f_wdo)
            for t in tr:
                rows.append(dict(filter=fn, strat=f"WDO-{sid:02d}", asset="WDO", date=t["date"], lots=float(t["contracts"]),
                                 pnl=float(t["pnl_brl"]), pnl_nocost=float(t["pnl_brl_nocost"])))
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Métricas
# ──────────────────────────────────────────────────────────────────────────────
def daily_series(tr: pd.DataFrame, key="pnl"):
    return tr.groupby("date")[key].sum().sort_index()


def metrics(tr: pd.DataFrame, key="pnl"):
    if tr.empty:
        return dict(trades=0, lots=0, wr=0.0, pf=0.0, net=0.0, dd=0.0, ret_dd=0.0, worst=0.0, pos_days=0.0)
    p = tr[key]
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    d = daily_series(tr, key)
    cum = d.cumsum()
    dd = float((cum.cummax().clip(lower=0) - cum).max())
    net = float(p.sum())
    return dict(trades=int(len(tr)), lots=int(tr["lots"].sum()), wr=round(100.0 * (p > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl > 0 else 99.0, net=round(net), dd=round(dd),
                ret_dd=round(net / dd, 2) if dd > 0 else 99.0, worst=round(float(d.min())),
                pos_days=round(100.0 * (d > 0).mean(), 1))


def port_metrics_from_daily(d: pd.Series):
    cum = d.cumsum()
    dd = float((cum.cummax().clip(lower=0) - cum).max())
    net = float(d.sum())
    return net, dd, (net / dd if dd > 0 else 99.0), float(d.min())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    flow, sess = load_flow_tables()
    print(f"Fluxo carregado: {len(sess)} sessões ({sess[0]} a {sess[-1]})")

    cache = os.path.join(OUT_DIR, "trades_all_filters.csv")
    if os.path.exists(cache) and os.environ.get("REUSE_TRADES") == "1":
        T = pd.read_csv(cache)
    else:
        T = run_all_sims(flow)
        T.to_csv(cache, index=False)
    T["date"] = T["date"].astype(str)
    all_days = sorted(T["date"].unique())

    # 1) Métricas individuais (estratégia x filtro), período completo + IS + OOS
    rows = []
    for (s, fn), g in T.groupby(["strat", "filter"]):
        m = metrics(g)
        m_nc = metrics(g, "pnl_nocost")
        mi = metrics(g[g["date"] <= IS_END])
        mo = metrics(g[g["date"] > IS_END])
        rows.append(dict(strat=s, asset=g["asset"].iloc[0], filter=fn, **m,
                         pf_nocost=m_nc["pf"], net_nocost=m_nc["net"],
                         is_net=mi["net"], is_pf=mi["pf"], is_ret_dd=mi["ret_dd"], is_trades=mi["trades"],
                         oos_net=mo["net"], oos_pf=mo["pf"], oos_ret_dd=mo["ret_dd"], oos_trades=mo["trades"]))
    IND = pd.DataFrame(rows).sort_values(["asset", "strat", "filter"])
    IND.to_csv(os.path.join(OUT_DIR, "individual_strategy_x_filter.csv"), index=False)

    # Melhor filtro por estratégia (completo e escolhido só no IS)
    best_rows = []
    for s, g in IND.groupby("strat"):
        base = g[g["filter"] == "0_BASE_MT5"].iloc[0]
        cand = g[g["trades"] >= 0.5 * base["trades"]]          # não aceita filtro que mate a estratégia
        b_full = cand.sort_values("ret_dd", ascending=False).iloc[0]
        b_is = cand.sort_values("is_ret_dd", ascending=False).iloc[0]
        best_rows.append(dict(strat=s, asset=base["asset"], base_trades=base["trades"], base_net=base["net"], base_pf=base["pf"],
                              base_dd=base["dd"], base_ret_dd=base["ret_dd"], base_oos_net=base["oos_net"],
                              best_filter=b_full["filter"], best_trades=b_full["trades"], best_net=b_full["net"],
                              best_pf=b_full["pf"], best_dd=b_full["dd"], best_ret_dd=b_full["ret_dd"],
                              is_choice=b_is["filter"], is_choice_oos_net=b_is["oos_net"], is_choice_oos_pf=b_is["oos_pf"]))
    BEST = pd.DataFrame(best_rows).sort_values(["asset", "strat"])
    BEST.to_csv(os.path.join(OUT_DIR, "best_filter_per_strategy.csv"), index=False)

    # 2) Carteira atual (11) sem filtro x mesmo filtro p/ todas x melhor filtro por estratégia
    daily = {}
    for (s, fn), g in T.groupby(["strat", "filter"]):
        daily[(s, fn)] = daily_series(g).reindex(all_days, fill_value=0.0)
    nTr = T.groupby(["strat", "filter"]).size().to_dict()

    def portfolio(items, days=None):
        d = sum(daily[it] for it in items)
        if days is not None:
            d = d[d.index.isin(days)] if isinstance(days, list) else d[days(d.index)]
        return d

    port_rows = []
    for asset, strats in (("WIN", [s for s in NAMES if s.startswith("EST")]), ("WDO", [s for s in NAMES if s.startswith("WDO")]),
                          ("WIN+WDO", list(NAMES))):
        for fn in FILTER_NAMES:
            d = portfolio([(s, fn) for s in strats])
            net, dd, rdd, worst = port_metrics_from_daily(d)
            port_rows.append(dict(carteira=f"{asset} todas ({len(strats)})", filtro=fn, trades=sum(nTr.get((s, fn), 0) for s in strats),
                                  net=round(net), dd=round(dd), ret_dd=round(rdd, 2), worst=round(worst)))
        bf = BEST.set_index("strat")["best_filter"].to_dict()
        d = portfolio([(s, bf[s]) for s in strats])
        net, dd, rdd, worst = port_metrics_from_daily(d)
        port_rows.append(dict(carteira=f"{asset} todas ({len(strats)})", filtro="MELHOR_POR_ESTRATEGIA",
                              trades=sum(nTr.get((s, bf[s]), 0) for s in strats), net=round(net), dd=round(dd), ret_dd=round(rdd, 2), worst=round(worst)))
    PORT = pd.DataFrame(port_rows)
    PORT.to_csv(os.path.join(OUT_DIR, "portfolio_by_filter.csv"), index=False)

    # 3) Melhor portfólio de até 3 estratégias por ativo (cada estratégia com seu filtro, inclusive "sem filtro")
    is_mask = lambda idx: np.array([x <= IS_END for x in idx])
    oos_mask = lambda idx: np.array([x > IS_END for x in idx])
    combo_rows = []
    for asset in ("WIN", "WDO"):
        strats = [s for s in NAMES if s.startswith("EST" if asset == "WIN" else "WDO")]
        for r in (1, 2, 3):
            for ss in itertools.combinations(strats, r):
                for fs in itertools.product(FILTER_NAMES, repeat=r):
                    items = list(zip(ss, fs))
                    d = portfolio(items)
                    net, dd, rdd, worst = port_metrics_from_daily(d)
                    di, do = d[is_mask(d.index)], d[oos_mask(d.index)]
                    ni, ddi, rdi, _ = port_metrics_from_daily(di)
                    no, ddo, rdo, _ = port_metrics_from_daily(do)
                    combo_rows.append(dict(
                        asset=asset, n=r, combo=" + ".join(f"{s}[{f.split('_', 1)[0]}]" for s, f in items),
                        strats=" + ".join(ss), filters=" + ".join(fs), all_base=all(f == "0_BASE_MT5" for f in fs),
                        trades=sum(nTr.get(it, 0) for it in items), net=round(net), dd=round(dd), ret_dd=round(rdd, 2),
                        worst=round(worst), is_net=round(ni), is_ret_dd=round(rdi, 2), oos_net=round(no), oos_dd=round(ddo),
                        oos_ret_dd=round(rdo, 2)))
    COMBOS = pd.DataFrame(combo_rows)
    COMBOS = COMBOS[COMBOS["trades"] >= 80]
    COMBOS.sort_values("ret_dd", ascending=False).to_csv(os.path.join(OUT_DIR, "combos_ate_3_por_ativo.csv"), index=False)

    # Impressão resumida
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print("\n=== MELHOR FILTRO POR ESTRATÉGIA ===")
    print(BEST.to_string(index=False))
    print("\n=== CARTEIRA POR FILTRO ===")
    print(PORT.to_string(index=False))
    for asset in ("WIN", "WDO"):
        A_ = COMBOS[COMBOS["asset"] == asset]
        print(f"\n=== {asset}: TOP 10 combos (até 3) por Ret/DD — período completo ===")
        print(A_.sort_values("ret_dd", ascending=False).head(10).to_string(index=False))
        print(f"\n=== {asset}: TOP 10 combos SEM FILTRO ===")
        print(A_[A_["all_base"]].sort_values("ret_dd", ascending=False).head(10).to_string(index=False))
        print(f"\n=== {asset}: TOP 10 escolhidos no IS -> resultado OOS ===")
        print(A_.sort_values("is_ret_dd", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()

