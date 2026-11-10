"""
Análise de Aderência Estatística Um-a-Um: MT5 Strategy Tester (OHLC 1-Min) vs Python
====================================================================================
Reconstrói ciclos flat-to-flat no MT5 (para não duplicar contagem de pernas no SmartGrid),
alinha as séries diárias nos 127 pregões (2026-05-11 a 2026-11-06) e calcula:
  - Aderência de Ciclos (%) e Aderência de Lotes (%)
  - Correlação de Pearson da Curva de Capital (r_eq) e R² da Curva (R2_eq)
  - Correlação de PnL Diário (r_day)
  - Concordância Direcional Diária (% de pregões com mesmo sinal/direção)
  - Exatidão Diária (% de pregões com diferença <= R$ 15 no dia)
  - Teste t pareado (p-value: H0 = médias diárias MT5 e Python são estatisticamente iguais)
  - Score Composto de Aderência Estatística (0% a 100%)
"""
import os
import sys
import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from research.diagnostics.compare_mt5_ohlc_vs_python_11 import (
    ROBOS_11,
    REPORT_DIR,
    PY_TRADES_CSV,
    parse_htm_deals,
    compute_daily_dd,
)


def reconstruct_mt5_cycles(deals_df: pd.DataFrame, native_spread_per_lot: float, extra_cost_per_lot: float) -> pd.DataFrame:
    """
    Agrupa deals do MT5 em ciclos completos (flat -> posicionado -> flat).
    No modo Hedging, o SmartGrid (EST-13, 14, 15) abre Perna 1 (1 lote) e Perna 2 (2 lotes)
    e fecha ambos os tickets no mesmo segundo, gerando 2 deals 'out' para 1 único ciclo.
    """
    if deals_df.empty:
        return pd.DataFrame()

    cycles = []
    open_vol = 0.0
    cyc_lots_closed = 0.0
    cyc_profit_raw = 0.0
    cyc_in_time = None
    cyc_date = None

    for _, row in deals_df.iterrows():
        d_dir = str(row["direction"]).lower()
        vol = float(row["volume"])
        prof = float(row["profit"])
        dt_s = str(row["datetime"])
        dt_date = str(row["date"])

        if d_dir in ("in", "entrada"):
            if open_vol <= 1e-6:
                cyc_in_time = dt_s
                cyc_date = dt_date
                cyc_lots_closed = 0.0
                cyc_profit_raw = 0.0
            open_vol += vol
        elif d_dir in ("out", "in/out", "saída", "entrada/saída"):
            cyc_lots_closed += vol
            cyc_profit_raw += prof
            open_vol = max(0.0, open_vol - vol)
            if open_vol <= 1e-6:
                cycles.append({
                    "date": dt_date,
                    "entry_dt": cyc_in_time or dt_s,
                    "exit_dt": dt_s,
                    "lots": cyc_lots_closed,
                    "pnl_htm": cyc_profit_raw,
                    "pnl_nocost": cyc_profit_raw + cyc_lots_closed * native_spread_per_lot,
                    "pnl_cost": cyc_profit_raw - cyc_lots_closed * extra_cost_per_lot,
                })
                cyc_in_time = None
                cyc_lots_closed = 0.0
                cyc_profit_raw = 0.0

    return pd.DataFrame(cycles)


def main():
    df_py_all = pd.read_csv(PY_TRADES_CSV)
    df_py_window = df_py_all[
        (df_py_all["date"] >= "2026-05-11") & (df_py_all["date"] <= "2026-11-06")
    ].copy()

    all_trading_days = sorted(df_py_window["date"].unique())
    print(f"Total de pregões analisados: {len(all_trading_days)} (2026-05-11 a 2026-11-06)\n")

    results = []
    mt5_daily_c_dict = {}
    py_daily_c_dict = {}
    mt5_daily_nc_dict = {}
    py_daily_nc_dict = {}

    for code, strat, asset, tf, cost_per_lot, desc in ROBOS_11:
        htm_path = os.path.join(REPORT_DIR, f"{code}_P1.htm")
        deals = parse_htm_deals(htm_path)
        native_spread = 1.0 if asset == "WIN" else 5.0
        extra_cost = max(0.0, cost_per_lot - native_spread)

        cyc_mt5 = reconstruct_mt5_cycles(deals, native_spread, extra_cost)
        py_sub = df_py_window[df_py_window["strat"] == strat].copy()

        n_cyc_mt5 = len(cyc_mt5)
        n_cyc_py = len(py_sub)
        lots_mt5 = int(cyc_mt5["lots"].sum()) if not cyc_mt5.empty else 0
        lots_py = int(py_sub["lots"].sum()) if not py_sub.empty else 0

        # Aderência de contagem de ciclos e de lotes
        adh_cycles = 100.0 * (1.0 - abs(n_cyc_mt5 - n_cyc_py) / max(1, n_cyc_mt5, n_cyc_py))
        adh_lots = 100.0 * (1.0 - abs(lots_mt5 - lots_py) / max(1, lots_mt5, lots_py))

        # Métricas por ciclo (COM CUSTOS operacionais padrão: R$ 2 WIN, R$ 5 WDO)
        wr_mt5_c = float((cyc_mt5["pnl_cost"] > 0).mean() * 100.0) if not cyc_mt5.empty else 0.0
        wr_py_c = float((py_sub["pnl"] > 0).mean() * 100.0) if not py_sub.empty else 0.0

        gp_mt5 = float(cyc_mt5.loc[cyc_mt5["pnl_cost"] > 0, "pnl_cost"].sum()) if not cyc_mt5.empty else 0.0
        gl_mt5 = float(-cyc_mt5.loc[cyc_mt5["pnl_cost"] < 0, "pnl_cost"].sum()) if not cyc_mt5.empty else 0.0
        pf_mt5_c = gp_mt5 / gl_mt5 if gl_mt5 > 0 else 99.9

        gp_py = float(py_sub.loc[py_sub["pnl"] > 0, "pnl"].sum()) if not py_sub.empty else 0.0
        gl_py = float(-py_sub.loc[py_sub["pnl"] < 0, "pnl"].sum()) if not py_sub.empty else 0.0
        pf_py_c = gp_py / gl_py if gl_py > 0 else 99.9

        net_mt5_c = float(cyc_mt5["pnl_cost"].sum()) if not cyc_mt5.empty else 0.0
        net_py_c = float(py_sub["pnl"].sum()) if not py_sub.empty else 0.0
        net_mt5_nc = float(cyc_mt5["pnl_nocost"].sum()) if not cyc_mt5.empty else 0.0
        net_py_nc = float(py_sub["pnl_nocost"].sum()) if not py_sub.empty else 0.0

        # Séries diárias alinhadas nos 127 pregões
        s_mt5_c = (cyc_mt5.groupby("date")["pnl_cost"].sum() if not cyc_mt5.empty else pd.Series(dtype=float)).reindex(all_trading_days, fill_value=0.0)
        s_py_c = (py_sub.groupby("date")["pnl"].sum() if not py_sub.empty else pd.Series(dtype=float)).reindex(all_trading_days, fill_value=0.0)
        s_mt5_nc = (cyc_mt5.groupby("date")["pnl_nocost"].sum() if not cyc_mt5.empty else pd.Series(dtype=float)).reindex(all_trading_days, fill_value=0.0)
        s_py_nc = (py_sub.groupby("date")["pnl_nocost"].sum() if not py_sub.empty else pd.Series(dtype=float)).reindex(all_trading_days, fill_value=0.0)

        mt5_daily_c_dict[strat] = s_mt5_c
        py_daily_c_dict[strat] = s_py_c
        mt5_daily_nc_dict[strat] = s_mt5_nc
        py_daily_nc_dict[strat] = s_py_nc

        dd_mt5_c = compute_daily_dd(s_mt5_c)
        dd_py_c = compute_daily_dd(s_py_c)
        retdd_mt5 = net_mt5_c / dd_mt5_c if dd_mt5_c > 0 else 0.0
        retdd_py = net_py_c / dd_py_c if dd_py_c > 0 else 0.0

        # Correlação diária e da curva de capital acumulada
        v_mt5 = s_mt5_c.values
        v_py = s_py_c.values
        eq_mt5 = np.cumsum(v_mt5)
        eq_py = np.cumsum(v_py)

        r_day = float(np.corrcoef(v_mt5, v_py)[0, 1]) if (np.std(v_mt5) > 0 and np.std(v_py) > 0) else 0.0
        r_eq = float(np.corrcoef(eq_mt5, eq_py)[0, 1]) if (np.std(eq_mt5) > 0 and np.std(eq_py) > 0) else 0.0
        r2_eq = (r_eq ** 2) * 100.0 if r_eq > 0 else 0.0

        # Concordância direcional nos pregões (ambos >0, ambos <0 ou ambos ==0, ou |diff| <= R$ 15)
        sign_match = (np.sign(v_mt5) == np.sign(v_py)) | (np.abs(v_mt5 - v_py) <= 15.0)
        dir_agree_pct = float(sign_match.mean() * 100.0)

        # Teste t pareado nas séries diárias (p-value)
        diff_d = v_mt5 - v_py
        if np.std(diff_d) > 1e-9:
            _, p_val = stats.ttest_rel(v_mt5, v_py)
        else:
            p_val = 1.0

        mae_day = float(np.mean(np.abs(diff_d)))

        # Aderência de PnL Líquido (%)
        if max(abs(net_mt5_c), abs(net_py_c)) > 0 and (net_mt5_c * net_py_c > 0):
            adh_pnl = 100.0 * (1.0 - abs(net_mt5_c - net_py_c) / max(abs(net_mt5_c), abs(net_py_c)))
        else:
            adh_pnl = 0.0

        # Score Composto de Aderência Estatística:
        # 25% Aderência Lotes + 25% Correlação Diária (max(0,r_day)*100) + 25% R² Equity + 25% Aderência PnL
        score_adh = 0.25 * adh_lots + 0.25 * (max(0.0, r_day) * 100.0) + 0.25 * r2_eq + 0.25 * adh_pnl

        results.append({
            "strat": strat,
            "asset": asset,
            "tf": tf,
            "desc": desc,
            "cyc_mt5": n_cyc_mt5,
            "cyc_py": n_cyc_py,
            "adh_cyc_pct": round(adh_cycles, 1),
            "lots_mt5": lots_mt5,
            "lots_py": lots_py,
            "adh_lots_pct": round(adh_lots, 1),
            "wr_mt5": round(wr_mt5_c, 1),
            "wr_py": round(wr_py_c, 1),
            "pf_mt5": round(pf_mt5_c, 2),
            "pf_py": round(pf_py_c, 2),
            "net_mt5_c": round(net_mt5_c, 0),
            "net_py_c": round(net_py_c, 0),
            "adh_pnl_pct": round(adh_pnl, 1),
            "dd_mt5_c": round(dd_mt5_c, 0),
            "dd_py_c": round(dd_py_c, 0),
            "retdd_mt5": round(retdd_mt5, 2),
            "retdd_py": round(retdd_py, 2),
            "r_day_pct": round(r_day * 100.0, 1),
            "r_eq_pct": round(r_eq * 100.0, 1),
            "r2_eq_pct": round(r2_eq, 1),
            "dir_agree_pct": round(dir_agree_pct, 1),
            "mae_day": round(mae_day, 1),
            "p_value": round(float(p_val), 3),
            "score_adh": round(score_adh, 1),
        })

    # Adicionar subtotais de carteira com as mesmas métricas estatísticas
    cyc_mt5_by_strat = {r["strat"]: r["cyc_mt5"] for r in results}
    cyc_py_by_strat = {r["strat"]: r["cyc_py"] for r in results}
    lots_mt5_by_strat = {r["strat"]: r["lots_mt5"] for r in results}
    lots_py_by_strat = {r["strat"]: r["lots_py"] for r in results}
    wr_mt5_by_strat = {r["strat"]: r["wr_mt5"] for r in results}
    wr_py_by_strat = {r["strat"]: r["wr_py"] for r in results}
    pf_mt5_by_strat = {r["strat"]: r["pf_mt5"] for r in results}
    pf_py_by_strat = {r["strat"]: r["pf_py"] for r in results}

    for g_name, g_asset, g_tf, g_desc, s_list in [
        ("WDO 03 (M5)",   "WDO",     "M5",     "Subtotal Dólar M5 (3 Robôs)",     ["WDO-01", "WDO-05", "WDO-07"]),
        ("WIN 06 (M5)",   "WIN",     "M5",     "Subtotal Índice M5 (6 Robôs)",    ["EST-01", "EST-04", "EST-07", "EST-13", "EST-14", "EST-15"]),
        ("TOTAL 09 (M5)", "WIN+WDO", "M5",     "Carteira 9 Robôs M5 (6WIN+3WDO)", ["EST-01", "EST-04", "EST-07", "EST-13", "EST-14", "EST-15", "WDO-01", "WDO-05", "WDO-07"]),
        ("TOTAL 11",      "WIN+WDO", "M5/M15", "MT5 Proposta B ⭐ (11 Robôs)",    [r[1] for r in ROBOS_11]),
    ]:
        s_m = sum(mt5_daily_c_dict[s] for s in s_list)
        s_p = sum(py_daily_c_dict[s] for s in s_list)
        vm, vp = s_m.values, s_p.values
        eq_m, eq_p = np.cumsum(vm), np.cumsum(vp)
        cm = sum(cyc_mt5_by_strat[s] for s in s_list)
        cp = sum(cyc_py_by_strat[s] for s in s_list)
        lm = sum(lots_mt5_by_strat[s] for s in s_list)
        lp = sum(lots_py_by_strat[s] for s in s_list)
        adh_c = 100.0 * (1.0 - abs(cm - cp) / max(1, cm, cp))
        adh_l = 100.0 * (1.0 - abs(lm - lp) / max(1, lm, lp))
        nm, np_ = float(vm.sum()), float(vp.sum())
        adh_p = 100.0 * (1.0 - abs(nm - np_) / max(abs(nm), abs(np_))) if max(abs(nm), abs(np_)) > 0 else 0.0
        dd_m = compute_daily_dd(s_m)
        dd_p = compute_daily_dd(s_p)
        r_d = float(np.corrcoef(vm, vp)[0, 1])
        r_e = float(np.corrcoef(eq_m, eq_p)[0, 1])
        r2_e = (r_e ** 2) * 100.0 if r_e > 0 else 0.0
        da = float(((np.sign(vm) == np.sign(vp)) | (np.abs(vm - vp) <= 15.0)).mean() * 100.0)
        _, pv = stats.ttest_rel(vm, vp)
        mae_d = float(np.mean(np.abs(vm - vp)))
        sc = 0.25 * adh_l + 0.25 * (max(0.0, r_d) * 100.0) + 0.25 * r2_e + 0.25 * adh_p
        results.append({
            "strat": g_name,
            "asset": g_asset,
            "tf": g_tf,
            "desc": g_desc,
            "cyc_mt5": cm,
            "cyc_py": cp,
            "adh_cyc_pct": round(adh_c, 1),
            "lots_mt5": lm,
            "lots_py": lp,
            "adh_lots_pct": round(adh_l, 1),
            "wr_mt5": round(float(np.mean([wr_mt5_by_strat[s] for s in s_list])), 1),
            "wr_py": round(float(np.mean([wr_py_by_strat[s] for s in s_list])), 1),
            "pf_mt5": round(float(np.mean([pf_mt5_by_strat[s] for s in s_list])), 2),
            "pf_py": round(float(np.mean([pf_py_by_strat[s] for s in s_list])), 2),
            "net_mt5_c": round(nm, 0),
            "net_py_c": round(np_, 0),
            "adh_pnl_pct": round(adh_p, 1),
            "dd_mt5_c": round(dd_m, 0),
            "dd_py_c": round(dd_p, 0),
            "retdd_mt5": round(nm / dd_m if dd_m > 0 else 0.0, 2),
            "retdd_py": round(np_ / dd_p if dd_p > 0 else 0.0, 2),
            "r_day_pct": round(r_d * 100.0, 1),
            "r_eq_pct": round(r_e * 100.0, 1),
            "r2_eq_pct": round(r2_e, 1),
            "dir_agree_pct": round(da, 1),
            "mae_day": round(mae_d, 1),
            "p_value": round(float(pv), 3),
            "score_adh": round(sc, 1),
        })

    df_out = pd.DataFrame(results)
    out_path = os.path.join(REPORT_DIR, "statistical_adherence_11_robots_2026.csv")
    df_out.to_csv(out_path, index=False)

    pd.set_option("display.width", 320)
    pd.set_option("display.max_columns", 35)
    print("=" * 165)
    print("  ADERÊNCIA ESTATÍSTICA UM A UM (MT5 OHLC 1-MIN vs PYTHON) - 127 PREGÕES (2026-05-11 A 2026-11-06)")
    print("=" * 165)
    print(df_out.to_string(index=False))


if __name__ == "__main__":
    main()
