"""
Verificacao M1 exata + Stop Diario G950/W400/D0 dos melhores candidatos direcionais WDO da Tarde
(R4_AFTERNOON: 14:00 / 14:30 / 15:00) e comparacao com WDO-04 / WDO-16 nos 38 Dias de Furia.
"""
import os
import sys
import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.wdo_directional_battery.discover_wdo_trend_r2 import prepare_r2_data, sim_r2_strategy
from research.wdo_directional_battery.discover_wdo_trend import eval_trades_metrics
from research.stop_diario.data_loader import load_portfolio_trades, load_m1_bars, PORTFOLIO_PRESETS
from research.stop_diario.engine import build_intraday_days, simulate_combined_stops
from research.optimizers.wdo_mt5_sim import load_wdo_mt5_raw, simulate_wdo_core_slot


def main():
    data = prepare_r2_data()
    all_dates = data["all_dates"]
    fury = data["fury_dates"]
    win_m1, wdo_m1 = load_m1_bars()

    b3_dir = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_ohlc_2026_b3")
    base_trades = load_portfolio_trades(PORTFOLIO_PRESETS["top_10"]["robots"], htm_dir=b3_dir)
    wdo_d, port_d = {}, {}
    for t in base_trades:
        port_d[t["date"]] = port_d.get(t["date"], 0.0) + float(t["pnl"])
        if t["asset"] == "WDO":
            wdo_d[t["date"]] = wdo_d.get(t["date"], 0.0) + float(t["pnl"])

    base_days = build_intraday_days(base_trades, win_m1, wdo_m1, all_dates=all_dates)
    b_ns = simulate_combined_stops(base_days, 0, 0, 0)
    b_950 = simulate_combined_stops(base_days, 950, 400, 0)
    print(f"BASE B3 SemStop : Net=R$ {b_ns['ret']:,.0f} | DD=R$ {b_ns['max_dd']:,.0f} | Ret/DD={b_ns['ret_dd']:.2f}x | Sharpe={b_ns['sharpe']:.2f}")
    print(f"BASE B3 G950    : Net=R$ {b_950['ret']:,.0f} | DD=R$ {b_950['max_dd']:,.0f} | Ret/DD={b_950['ret_dd']:.2f}x | Sharpe={b_950['sharpe']:.2f}\n")

    cands = [
        ("PB_1400_T0_e65",   {"sl": 8.0, "tp": 0.0,  "be_trig": 7.0, "be_lock": 1.0, "tr_trig": 11.0, "tr_dist": 7.0, "mode": "PB_EMA9", "min_dmv": 15.0, "min_eff": 0.65, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 840, "max_tmin": 990}),
        ("PB_1400_T35_e65",  {"sl": 8.0, "tp": 35.0, "be_trig": 8.0, "be_lock": 1.0, "tr_trig": 12.0, "tr_dist": 7.0, "mode": "PB_EMA9", "min_dmv": 15.0, "min_eff": 0.65, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 840, "max_tmin": 990}),
        ("PB_1430_T0_e65",   {"sl": 8.0, "tp": 0.0,  "be_trig": 7.0, "be_lock": 1.0, "tr_trig": 11.0, "tr_dist": 7.0, "mode": "PB_EMA9", "min_dmv": 15.0, "min_eff": 0.65, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 870, "max_tmin": 990}),
        ("PB_1500_T0_e60",   {"sl": 8.0, "tp": 0.0,  "be_trig": 7.0, "be_lock": 1.0, "tr_trig": 11.0, "tr_dist": 7.0, "mode": "PB_EMA9", "min_dmv": 15.0, "min_eff": 0.60, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 900, "max_tmin": 990}),
        ("PB_1500_T0_e50",   {"sl": 8.0, "tp": 0.0,  "be_trig": 7.0, "be_lock": 1.0, "tr_trig": 11.0, "tr_dist": 7.0, "mode": "PB_EMA9", "min_dmv": 15.0, "min_eff": 0.50, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 900, "max_tmin": 990}),
        ("NDH_1400_T24_e65", {"sl": 6.0, "tp": 24.0, "be_trig": 6.0, "be_lock": 1.0, "tr_trig": 9.0,  "tr_dist": 5.0, "mode": "MKT_NDH", "min_dmv": 25.0, "min_eff": 0.65, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 840, "max_tmin": 990}),
        ("NDH_1430_T24_e60", {"sl": 6.0, "tp": 24.0, "be_trig": 6.0, "be_lock": 1.0, "tr_trig": 9.0,  "tr_dist": 5.0, "mode": "MKT_NDH", "min_dmv": 20.0, "min_eff": 0.60, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 870, "max_tmin": 990}),
        ("NDH_1500_T24_e55", {"sl": 6.0, "tp": 24.0, "be_trig": 6.0, "be_lock": 1.0, "tr_trig": 9.0,  "tr_dist": 5.0, "mode": "MKT_NDH", "min_dmv": 18.0, "min_eff": 0.55, "use_limit": False, "lim_bars": 2, "max_tr": 2, "min_tmin": 900, "max_tmin": 990}),
    ]

    print("=== VERIFICACAO M1 EXATA: R4_AFTERNOON (REVEZAMENTO DA TARDE) ===")
    for name, p in cands:
        tr05 = sim_r2_strategy(data, "R4_AFTERNOON", p, cost_pts=0.5, m1_dict=wdo_m1)
        tr10 = sim_r2_strategy(data, "R4_AFTERNOON", p, cost_pts=1.0, m1_dict=wdo_m1)
        m05 = eval_trades_metrics(tr05, all_dates, fury, wdo_d, port_d)
        m10 = eval_trades_metrics(tr10, all_dates, fury, wdo_d, port_d)
        extra = [{
            "strat": "WDO_TREND", "asset": "WDO", "tf": "M5", "magic": 89099, "side": t["dir"],
            "lots": 1.0, "date": t["date"], "date_in": t["date"], "min_in": t["entry_min"],
            "min_out": t["exit_min"], "sec_in": t["entry_min"] * 60, "sec_out": t["exit_min"] * 60,
            "px_in": t["entry_px"], "px_out": t["exit_px"], "pnl": t["pnl"], "cost_extra": 5.0,
        } for t in tr05]
        cdays = build_intraday_days(base_trades + extra, win_m1, wdo_m1, all_dates=all_dates)
        c_950 = simulate_combined_stops(cdays, 950, 400, 0)
        print(
            f"{name:<17} | N={m05['n']:>3} Net={m05['net']:>+5.0f} DD={m05['dd']:>4.0f} R/DD={m05['ret_dd']:>4.2f} PF={m05['pf']:.2f} | "
            f"IS={m05['is_net']:>+5.0f}({m05['is_pf']:.2f}) OOS={m05['oos_net']:>+4.0f}({m05['oos_pf']:.2f}) | "
            f"Fury={m05['fury_pnl']:>+5.0f} Mo={m05['pos_months']:>4} Str1p={m10['net']:>+5.0f} | "
            f"CombNS={m05['comb_ret_dd']:.2f}x Comb950={c_950['ret_dd']:.2f}x(Net={c_950['ret']:.0f},DD={c_950['max_dd']:.0f})"
        )

    # Also check WDO-04 and WDO-16 (5/5 approved earlier!) on Fury Days & Synergy with top_10 B3
    print("\n=== CHECAGEM EXTRA: WDO-04 e WDO-16 (JA APROVADOS 5/5) NOS 38 DIAS DE FURIA ===")
    from research.discover_gex_nwe_setups import compute_nwe_series
    from research.optimizers.wdo_mt5_sim import compute_rsi7_series
    df_raw, gex_raw = load_wdo_mt5_raw()
    rc = df_raw["close"].values.astype(float)
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(rc, 50, 5.0, 2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(rc, 30, 3.0, 1.6)
    rsi7 = compute_rsi7_series(rc)
    for sid, nm in [(4, "WDO-04"), (16, "WDO-16")]:
        raw_tr = simulate_wdo_core_slot(
            sid, df_raw, gex_raw, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7,
            start_date="2026-01-02", end_date="2026-11-06", cost_pts=0.5
        )
        tr_norm = [{
            "date": str(t["date"]), "entry_min": pd.Timestamp(t["entry_time"]).hour * 60 + pd.Timestamp(t["entry_time"]).minute,
            "exit_min": pd.Timestamp(t["exit_time"]).hour * 60 + pd.Timestamp(t["exit_time"]).minute,
            "dir": int(t["side"]), "entry_px": float(t["avg_px"]), "exit_px": float(t["exit_px"]),
            "pts": float(t["pnl_pts"]), "pnl": float(t["pnl_brl"]),
        } for t in raw_tr]
        m = eval_trades_metrics(tr_norm, all_dates, fury, wdo_d, port_d)
        extra = [{
            "strat": nm, "asset": "WDO", "tf": "M5", "magic": 89000 + sid, "side": t["dir"],
            "lots": 1.0, "date": t["date"], "date_in": t["date"], "min_in": t["entry_min"],
            "min_out": t["exit_min"], "sec_in": t["entry_min"] * 60, "sec_out": t["exit_min"] * 60,
            "px_in": t["entry_px"], "px_out": t["exit_px"], "pnl": t["pnl"], "cost_extra": 5.0,
        } for t in tr_norm]
        cdays = build_intraday_days(base_trades + extra, win_m1, wdo_m1, all_dates=all_dates)
        c_950 = simulate_combined_stops(cdays, 950, 400, 0)
        print(
            f"{nm:<17} | N={m['n']:>3} Net={m['net']:>+5.0f} DD={m['dd']:>4.0f} R/DD={m['ret_dd']:>4.2f} PF={m['pf']:.2f} | "
            f"IS={m['is_net']:>+5.0f}({m['is_pf']:.2f}) OOS={m['oos_net']:>+4.0f}({m['oos_pf']:.2f}) | "
            f"Fury={m['fury_pnl']:>+5.0f} Corr={m['corr_wdo']:+.2f} Mo={m['pos_months']:>4} | "
            f"CombNS={m['comb_ret_dd']:.2f}x Comb950={c_950['ret_dd']:.2f}x(Net={c_950['ret']:.0f},DD={c_950['max_dd']:.0f})"
        )


if __name__ == "__main__":
    import pandas as pd
    main()
