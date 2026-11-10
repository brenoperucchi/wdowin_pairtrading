"""
BACKTEST COMPLETO 2026 (IS vs OOS vs TOTAL) - CARTEIRA OFICIAL JUMBA 15 ROBÔS (MT5)
===================================================================================
Avalia as 15 estratégias oficiais do MT5 (`Jumba_15_CARTEIRA_V2`):
  - 09 Estratégias WIN: EST-01, EST-03 (M15), EST-04, EST-05 (M15), EST-07, EST-13, EST-14, EST-15, EST-16
  - 06 Estratégias WDO: WDO-01, WDO-02, WDO-05, WDO-07, WDO-09, WDO-10

Divisão de Períodos:
  - OOS (Novo Backfill B3 2026): 02/01/2026 a 06/05/2026 (84 pregões)
  - IS  (Período Original):      07/05/2026 a 06/11/2026 (128 pregões)
  - TOTAL (Ano Completo 2026):   02/01/2026 a 06/11/2026 (212 pregões)

Custos operacionais incluídos (idêntico ao backtest validado):
  - WIN: 10 pts por contrato (R$ 2,00/contrato)
  - WDO: 0,5 pt por contrato (R$ 5,00/contrato)
"""

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
import research.optimizers.optimize_existing_16_setups as o16
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
import research.optimizers.sg_sim as sg_sim
import research.optimizers.wdo_mt5_sim as wsim
from research.discover_m15_deep_dive import run_experiment, load_tf_bars
from research.mt5_loader import load_gex_csv, HIST_WIN, HIST_WDO

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "bt_15_full_2026")
os.makedirs(OUT_DIR, exist_ok=True)

FULL_START = "2026-01-02"
OOS_END = "2026-05-06"
IS_START = "2026-05-07"
FULL_END = "2026-11-06"

WIN_COST_PTS = 10.0  # R$ 2,00 / contrato
WDO_COST_PTS = 0.5   # R$ 5,00 / contrato

STRAT_META = [
    ("EST-01", "WIN", "M5",  "WIN_PA_PINBAR_WALL (Scalper NY)"),
    ("EST-03", "WIN", "M15", "WIN_M15_FAKEOUT_TRAP (Fakeout Wall M15)"),
    ("EST-04", "WIN", "M5",  "WIN_PB_WDO_ALIGNED (Pullback Reteste Wall)"),
    ("EST-05", "WIN", "M15", "WIN_M15_MIDWALL_PULLBACK (MidWall Slope M15)"),
    ("EST-07", "WIN", "M5",  "WIN_OF_CLIMAX_WALL (Breakout/Absorcao NY)"),
    ("EST-13", "WIN", "M5",  "WIN_SG_SCALPER_3C (SmartGrid 1+2L)"),
    ("EST-14", "WIN", "M5",  "WIN_SG_MOMENTUM_3C (SmartGrid Vel 1+2L)"),
    ("EST-15", "WIN", "M5",  "WIN_SG_Z30_REV_WALL (SmartGrid Z30 Wall)"),
    ("EST-16", "WIN", "M5",  "WIN_SG_SPRING_Z30_WALL (SmartGrid Spring)"),
    ("WDO-01", "WDO", "M5",  "WDO_PA_WALL_SCALPER_NY (Scalper Hibrido NY)"),
    ("WDO-02", "WDO", "M5",  "WDO_PA_OUTSIDE_MID (Scalper Hibrido CORE)"),
    ("WDO-05", "WDO", "M5",  "WDO_PA_CLUSTER_NWE (Cluster NWE30+50)"),
    ("WDO-07", "WDO", "M5",  "WDO_OF_CLIMAX_WALL (Absorcao Mkt NY)"),
    ("WDO-09", "WDO", "M5",  "WDO_PB_WALL_PULLBACK (Cluster Limit Wall)"),
    ("WDO-10", "WDO", "M5",  "WDO_S2_MIDWALL_Z30 (Reversao NWE 12-14h30)"),
]


def max_loss_streak(pnls: np.ndarray) -> int:
    max_s = 0
    cur_s = 0
    for p in pnls:
        if p < 0:
            cur_s += 1
            if cur_s > max_s:
                max_s = cur_s
        elif p > 0:
            cur_s = 0
    return int(max_s)


def compute_detailed_metrics(df_tr: pd.DataFrame, all_trading_days: list) -> dict:
    if df_tr.empty:
        return {
            "trades": 0, "lots": 0, "wr": 0.0, "pf": 0.0, "pf_nocost": 0.0,
            "net": 0.0, "net_nocost": 0.0, "dd_day": 0.0, "dd_trade": 0.0,
            "ret_dd": 0.0, "payoff": 0.0, "avg_trade": 0.0, "sharpe": 0.0,
            "pos_days_pct": 0.0, "active_days": 0, "worst_day": 0.0, "best_day": 0.0,
            "max_streak": 0
        }

    df_sorted = df_tr.sort_values(["date", "seq"]).reset_index(drop=True)
    pnls = df_sorted["pnl"].values.astype(float)
    pnls_nc = df_sorted["pnl_nocost"].values.astype(float)
    lots = int(df_sorted["lots"].sum())
    n = len(pnls)

    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = 100.0 * len(wins) / n if n > 0 else 0.0
    gw = float(wins.sum()) if len(wins) > 0 else 0.0
    gl = float(-losses.sum()) if len(losses) > 0 else 0.0
    pf = gw / gl if gl > 1e-6 else (99.9 if gw > 0 else 0.0)

    gw_nc = float(pnls_nc[pnls_nc > 0].sum())
    gl_nc = float(-pnls_nc[pnls_nc < 0].sum())
    pf_nc = gw_nc / gl_nc if gl_nc > 1e-6 else (99.9 if gw_nc > 0 else 0.0)

    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(-losses.mean()) if len(losses) > 0 else 0.0
    payoff = avg_win / avg_loss if avg_loss > 1e-6 else 0.0

    net = float(pnls.sum())
    net_nc = float(pnls_nc.sum())
    avg_tr = net / n if n > 0 else 0.0

    # Max DD Trade-a-Trade
    cum_tr = np.cumsum(pnls)
    pk_tr = np.maximum.accumulate(np.insert(cum_tr, 0, 0.0))[1:]
    dd_trade = float(np.max(pk_tr - cum_tr)) if len(cum_tr) > 0 else 0.0

    # Série diária nos pregões do período
    daily_active = df_sorted.groupby("date")["pnl"].sum()
    daily_full = daily_active.reindex(all_trading_days, fill_value=0.0)
    cum_day = daily_full.cumsum().values
    pk_day = np.maximum.accumulate(np.insert(cum_day, 0, 0.0))[1:]
    dd_day = float(np.max(pk_day - cum_day)) if len(cum_day) > 0 else 0.0

    ret_dd = net / dd_day if dd_day > 1e-6 else (99.9 if net > 0 else 0.0)

    std_d = float(daily_full.std(ddof=1)) if len(daily_full) > 1 else 0.0
    sharpe = (float(daily_full.mean()) / std_d * np.sqrt(252.0)) if std_d > 1e-9 else 0.0

    active_days = int(len(daily_active))
    pos_days = int((daily_active > 0).sum())
    pos_days_pct = 100.0 * pos_days / active_days if active_days > 0 else 0.0

    worst_day = float(daily_full.min()) if len(daily_full) > 0 else 0.0
    best_day = float(daily_full.max()) if len(daily_full) > 0 else 0.0
    streak = max_loss_streak(pnls)

    return {
        "trades": n,
        "lots": lots,
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "pf_nocost": round(pf_nc, 2),
        "net": round(net, 2),
        "net_nocost": round(net_nc, 2),
        "dd_day": round(dd_day, 2),
        "dd_trade": round(dd_trade, 2),
        "ret_dd": round(ret_dd, 2),
        "payoff": round(payoff, 2),
        "avg_trade": round(avg_tr, 2),
        "sharpe": round(sharpe, 2),
        "pos_days_pct": round(pos_days_pct, 1),
        "active_days": active_days,
        "worst_day": round(worst_day, 2),
        "best_day": round(best_day, 2),
        "max_streak": streak,
    }


def run_all_15_strategies() -> pd.DataFrame:
    rows = []
    seq_counter = 0

    print("1/4 Carregando WIN M5 + WDO M5 e calculando NWE/RSI...")
    df_win_m5, gex_win = o16.load_win_and_wdo_aligned()
    c_m5 = df_win_m5["close"].values
    n50 = disc.compute_nwe_series(c_m5, lookback=50, bw=5.0, mult=2.0)
    n30 = disc.compute_nwe_series(c_m5, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(c_m5).diff()
    rsi7 = (
        100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))
    ).fillna(50.0).values
    A_win_m5 = (df_win_m5, gex_win, n50[0], n50[1], n50[2], n50[4], n30[0], n30[1], n30[2], n30[4], rsi7)

    # EST-01, EST-04, EST-07
    win_m5_cfg = {
        1: ("3p", "CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
        4: ("wdo", "ALIGNED", "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL"),
        7: ("3p", "CURRENT", "BE_WALL_SHIELD", 15.0, "TP_MIDWALL"),
    }
    for k, (eng, ent, be, buf, tp) in win_m5_cfg.items():
        if eng == "3p":
            tr, _ = o16.simulate_single_est_slot(
                k, *A_win_m5, entry_override=ent, be_mode=be, wall_shield_buf=buf,
                tp_mode=tp, cost_pts=WIN_COST_PTS, start_date=FULL_START
            )
        else:
            tr, _ = simulate_aligned_win_wdo_slot(
                k, *A_win_m5, be_mode=be, wall_shield_buf=buf, tp_mode=tp,
                entry_override=ent, cost_pts=WIN_COST_PTS, start_date=FULL_START
            )
        for t in tr:
            d = str(t["date"])
            if FULL_START <= d <= FULL_END:
                seq_counter += 1
                lots = float(t.get("contracts", 1))
                pnl = float(t["pnl_brl"])
                rows.append({
                    "seq": seq_counter,
                    "strat": f"EST-{k:02d}",
                    "asset": "WIN",
                    "tf": "M5",
                    "date": d,
                    "lots": lots,
                    "pnl": pnl,
                    "pnl_nocost": pnl + 2.0 * lots,
                })

    print("2/4 Rodando WIN M15 (EST-03 e EST-05)...")
    df_win_m15 = load_tf_bars("WIN", "M15", start_date="2025-12-15", end_date=FULL_END)
    c_m15 = df_win_m15["close"].values
    c15, u15, l15, _, s15 = disc.compute_nwe_series(c_m15, lookback=30, bw=4.0, mult=1.8)
    nwe_win_m15 = {"center": c15, "upper": u15, "lower": l15, "slope": s15}

    tr_est03 = run_experiment(
        df_win_m15, gex_win, "WIN", "M15", "M15_FAKEOUT_TRAP", "MARKET", nwe_win_m15,
        wall_buf=30.0, min_tp_dist=220.0, front_run=20.0, be_ratio=0.50, be_lock_pts=25.0
    )
    for t in tr_est03:
        d = str(t["date"])
        if FULL_START <= d <= FULL_END:
            seq_counter += 1
            pnl = float(t["brl"])
            rows.append({
                "seq": seq_counter,
                "strat": "EST-03",
                "asset": "WIN",
                "tf": "M15",
                "date": d,
                "lots": 1.0,
                "pnl": pnl,
                "pnl_nocost": pnl + 2.0,
            })

    tr_est05 = run_experiment(
        df_win_m15, gex_win, "WIN", "M15", "M15_MIDWALL_PULLBACK", "MARKET", nwe_win_m15,
        wall_buf=35.0, min_tp_dist=250.0, front_run=20.0, be_ratio=0.50, be_lock_pts=25.0,
        use_nwe_slope=True, nwe_slope_thresh=4.0, min_nwe_bw=300.0
    )
    for t in tr_est05:
        d = str(t["date"])
        if FULL_START <= d <= FULL_END:
            seq_counter += 1
            pnl = float(t["brl"])
            rows.append({
                "seq": seq_counter,
                "strat": "EST-05",
                "asset": "WIN",
                "tf": "M15",
                "date": d,
                "lots": 1.0,
                "pnl": pnl,
                "pnl_nocost": pnl + 2.0,
            })

    print("3/4 Rodando WIN SmartGrids M5+M1 Tick-a-Tick (EST-13, EST-14, EST-15, EST-16)...")
    sg_df = sg_sim.run(slots=(13, 14, 15, 16), start=FULL_START, cost_pts=WIN_COST_PTS)
    for _, t in sg_df.iterrows():
        d = pd.Timestamp(t["t_in"]).strftime("%Y-%m-%d")
        if FULL_START <= d <= FULL_END:
            seq_counter += 1
            lots = float(t["lots"])
            pnl = float(t["brl"])
            rows.append({
                "seq": seq_counter,
                "strat": f"EST-{int(t['k']):02d}",
                "asset": "WIN",
                "tf": "M5",
                "date": d,
                "lots": lots,
                "pnl": pnl,
                "pnl_nocost": float(t.get("brl_nocost", pnl + 2.0 * lots)),
            })

    print("4/4 Rodando WDO M5 (WDO-01, WDO-02, WDO-05, WDO-07, WDO-09, WDO-10)...")
    wdf, wgex = wsim.load_wdo_mt5_raw()
    wc = wdf["close"].values
    w50 = wsim.compute_nwe_series(wc, lookback=50, bw=5.0, mult=2.0)
    w30 = wsim.compute_nwe_series(wc, lookback=30, bw=3.0, mult=1.6)
    wrsi = wsim.compute_rsi7_series(wc)

    for sid in (1, 2, 5, 7, 9, 10):
        tr = wsim.simulate_wdo_core_slot(
            sid, wdf, wgex, w50[0], w50[1], w50[2], w50[4], w30[0], w30[1], w30[2], w30[4],
            wrsi, start_date=FULL_START, end_date=FULL_END, cost_pts=WDO_COST_PTS
        )
        for t in tr:
            d = str(t["date"])
            if FULL_START <= d <= FULL_END:
                seq_counter += 1
                lots = float(t.get("contracts", 1))
                rows.append({
                    "seq": seq_counter,
                    "strat": f"WDO-{sid:02d}",
                    "asset": "WDO",
                    "tf": "M5",
                    "date": d,
                    "lots": lots,
                    "pnl": float(t["pnl_brl"]),
                    "pnl_nocost": float(t["pnl_brl_nocost"]),
                })

    return pd.DataFrame(rows)


def main():
    df_trades = run_all_15_strategies()
    df_trades.to_csv(os.path.join(OUT_DIR, "trades_15_strategies_2026.csv"), index=False)

    # Lista oficial de pregões com GEX em cada janela
    gex_win = load_gex_csv(HIST_WIN)
    all_gex_days = sorted([d for d in gex_win.keys() if FULL_START <= d <= FULL_END])
    oos_days = [d for d in all_gex_days if d <= OOS_END]
    is_days = [d for d in all_gex_days if d >= IS_START]

    print(f"\nPregões Totais: {len(all_gex_days)} | OOS (02/01..06/05): {len(oos_days)} | IS (07/05..06/11): {len(is_days)}")

    periods = [
        ("OOS_JAN_MAI", oos_days, lambda d: d <= OOS_END),
        ("IS_MAI_NOV",  is_days,  lambda d: d >= IS_START),
        ("TOTAL_2026",  all_gex_days, lambda d: (FULL_START <= d <= FULL_END)),
    ]

    summary_rows = []
    for code, asset, tf, desc in STRAT_META:
        sub = df_trades[df_trades["strat"] == code]
        row_dict = {"strat": code, "asset": asset, "tf": tf, "desc": desc}
        for p_name, p_days, p_fn in periods:
            p_tr = sub[sub["date"].map(p_fn)]
            m = compute_detailed_metrics(p_tr, p_days)
            for k, v in m.items():
                row_dict[f"{p_name}_{k}"] = v
        summary_rows.append(row_dict)

    # Subtotais: WIN 09, WDO 06, TOTAL 15
    for grp_code, grp_asset, grp_tf, grp_desc, cond_fn in [
        ("WIN 09",   "WIN",     "M5/M15", "SUBTOTAL INDICE (09 ROBOS)", lambda df: df["asset"] == "WIN"),
        ("WDO 06",   "WDO",     "M5",     "SUBTOTAL DOLAR (06 ROBOS)",  lambda df: df["asset"] == "WDO"),
        ("TOTAL 15", "WIN+WDO", "ALL",    "CARTEIRA COMPLETA (15 ROBOS)", lambda df: df["asset"].isin(["WIN", "WDO"])),
    ]:
        sub = df_trades[cond_fn(df_trades)]
        row_dict = {"strat": grp_code, "asset": grp_asset, "tf": grp_tf, "desc": grp_desc}
        for p_name, p_days, p_fn in periods:
            p_tr = sub[sub["date"].map(p_fn)]
            m = compute_detailed_metrics(p_tr, p_days)
            for k, v in m.items():
                row_dict[f"{p_name}_{k}"] = v
        summary_rows.append(row_dict)

    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(os.path.join(OUT_DIR, "summary_15_is_oos_total_2026.csv"), index=False)

    # Breakdown Mensal
    df_trades["month"] = df_trades["date"].str.slice(0, 7)
    months = sorted(df_trades["month"].unique())
    m_rows = []
    for code, asset, tf, desc in STRAT_META:
        sub = df_trades[df_trades["strat"] == code]
        r = {"strat": code, "asset": asset}
        for m in months:
            r[m] = round(float(sub[sub["month"] == m]["pnl"].sum()), 2)
        r["TOTAL"] = round(float(sub["pnl"].sum()), 2)
        m_rows.append(r)
    for grp_code, cond_fn in [
        ("WIN 09", lambda df: df["asset"] == "WIN"),
        ("WDO 06", lambda df: df["asset"] == "WDO"),
        ("TOTAL 15", lambda df: df["asset"].isin(["WIN", "WDO"])),
    ]:
        sub = df_trades[cond_fn(df_trades)]
        r = {"strat": grp_code, "asset": "PORT"}
        for m in months:
            r[m] = round(float(sub[sub["month"] == m]["pnl"].sum()), 2)
        r["TOTAL"] = round(float(sub["pnl"].sum()), 2)
        m_rows.append(r)

    df_monthly = pd.DataFrame(m_rows)
    df_monthly.to_csv(os.path.join(OUT_DIR, "monthly_15_strategies_2026.csv"), index=False)

    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 60)
    print("\n" + "=" * 145)
    print("  RESUMO COMPARATIVO: OOS (02/01..06/05) vs IS (07/05..06/11) vs TOTAL 2026 (02/01..06/11)")
    print("=" * 145)
    cols_view = [
        "strat", "tf",
        "OOS_JAN_MAI_trades", "OOS_JAN_MAI_wr", "OOS_JAN_MAI_pf", "OOS_JAN_MAI_net", "OOS_JAN_MAI_dd_day", "OOS_JAN_MAI_ret_dd",
        "IS_MAI_NOV_trades",  "IS_MAI_NOV_wr",  "IS_MAI_NOV_pf",  "IS_MAI_NOV_net",  "IS_MAI_NOV_dd_day",  "IS_MAI_NOV_ret_dd",
        "TOTAL_2026_trades",  "TOTAL_2026_wr",  "TOTAL_2026_pf",  "TOTAL_2026_net",  "TOTAL_2026_dd_day",  "TOTAL_2026_ret_dd",
        "TOTAL_2026_sharpe",  "TOTAL_2026_max_streak"
    ]
    print(df_sum[cols_view].to_string(index=False))

    print("\n" + "=" * 145)
    print("  RESULTADO MENSAL (R$ LÍQUIDO APÓS CUSTOS) - JAN/2026 A NOV/2026")
    print("=" * 145)
    print(df_monthly.to_string(index=False))


if __name__ == "__main__":
    main()

