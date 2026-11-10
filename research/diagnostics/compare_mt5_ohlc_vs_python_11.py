"""
Compara os resultados do MT5 Strategy Tester em Model=1 (1-Minute OHLC)
para os 11 robôs da Proposta B ⭐ contra o Backtest Python no mesmo período.
"""
import os
import re
import sys
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

REPORT_DIR = os.path.join(ROOT, "data", "reports", "mt5_tester_ohlc_2026")
PY_TRADES_CSV = os.path.join(ROOT, "data", "reports", "bt_15_full_2026", "trades_15_strategies_2026.csv")

ROBOS_11 = [
    ("EST01", "EST-01", "WIN", "M5",  2.0, "Breakout GEX Wall C/V"),
    ("EST03", "EST-03", "WIN", "M15", 2.0, "GEX Fade + NWE 30/50"),
    ("EST04", "EST-04", "WIN", "M5",  2.0, "Fade Extremos + Flip"),
    ("EST05", "EST-05", "WIN", "M15", 2.0, "Reversão Gamma Flip"),
    ("EST07", "EST-07", "WIN", "M5",  2.0, "Breakout Momentum NY"),
    ("EST13", "EST-13", "WIN", "M5",  2.0, "SmartGrid 1+2L RSI+BE"),
    ("EST14", "EST-14", "WIN", "M5",  2.0, "SmartGrid 1+2L Instit."),
    ("EST15", "EST-15", "WIN", "M5",  2.0, "SmartGrid 1+2L EOD"),
    ("WDO01", "WDO-01", "WDO", "M5",  5.0, "Scalper Híbrido NY"),
    ("WDO05", "WDO-05", "WDO", "M5",  5.0, "Cluster NWE 30+50"),
    ("WDO07", "WDO-07", "WDO", "M5",  5.0, "Absorção Abertura NY"),
]


def parse_htm_summary(htm_path: str) -> dict:
    with open(htm_path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-16", errors="ignore")

    def extract_val(labels):
        for lbl in labels:
            pat = rf"{re.escape(lbl)}\s*</td>\s*<td[^>]*><b>([^<]+)</b>"
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                s = m.group(1).strip().replace(" ", "").replace("\xa0", "")
                m_num = re.search(r"[-+]?\d+(?:[\.,]\d+)?", s)
                if m_num:
                    return float(m_num.group(0).replace(",", "."))
        return np.nan

    return {
        "net_profit": extract_val(["Lucro Líquido Total:", "Total Net Profit:"]),
        "gross_profit": extract_val(["Lucro Bruto:", "Gross Profit:"]),
        "gross_loss": extract_val(["Perda Bruta:", "Gross Loss:"]),
        "profit_factor": extract_val(["Fator de Lucro:", "Profit Factor:"]),
        "max_dd_abs": extract_val([
            "Rebaixamento Máximo do Saldo:",
            "Balance Drawdown Maximal:",
            "Rebaixamento Máximo do Capital Líquido:",
            "Equity Drawdown Maximal:",
        ]),
        "total_trades": extract_val(["Total de Negociações:", "Total Trades:"]),
        "win_trades": extract_val(["Negociações com Lucro (% do total):", "Profit Trades (% of total):"]),
        "bars": extract_val(["Barras:", "Bars:"]),
        "ticks": extract_val(["Ticks:", "Ticks:"]),
    }


def parse_htm_deals(htm_path: str) -> pd.DataFrame:
    """Extrai os deals da tabela de Ofertas/Deals do relatório HTML do MT5."""
    with open(htm_path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-16", errors="ignore")

    # Procura linhas de deals: Data/Hora | Oferta | Ativo | Tipo | Direção | Volume | Preço | Ordem | Comissão | Swap | Lucro | Saldo | Comentário
    row_pat = re.compile(
        r"<tr[^>]*>\s*"
        r"<td[^>]*>(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})</td>\s*"
        r"<td[^>]*>(\d+)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>\s*"
        r"<td[^>]*>([^<]*)</td>",
        flags=re.IGNORECASE,
    )
    deals = []
    for m in row_pat.finditer(text):
        dt_str, deal_id, sym, dtype, direction, vol_s, price_s, order_s, comm_s, swap_s, profit_s, bal_s, comment = m.groups()
        dtype_l = dtype.strip().lower()
        if dtype_l not in ("buy", "sell", "compra", "venda"):
            continue
        vol_clean = vol_s.strip().replace(" ", "").replace("\xa0", "").split("/")[0].replace(",", ".")
        prof_clean = profit_s.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
        price_clean = price_s.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            vol = float(vol_clean) if vol_clean else 0.0
        except ValueError:
            vol = 0.0
        try:
            prof = float(prof_clean) if prof_clean else 0.0
        except ValueError:
            prof = 0.0
        try:
            price = float(price_clean) if price_clean else 0.0
        except ValueError:
            price = 0.0
        deals.append({
            "datetime": dt_str.strip(),
            "date": dt_str.strip()[:10].replace(".", "-"),
            "deal": int(deal_id),
            "symbol": sym.strip(),
            "type": dtype_l,
            "direction": direction.strip().lower(),
            "volume": vol,
            "price": price,
            "profit": prof,
            "comment": comment.strip(),
        })
    return pd.DataFrame(deals)


def compute_daily_dd(daily_series: pd.Series) -> float:
    if daily_series.empty:
        return 0.0
    eq = daily_series.cumsum()
    dd = (eq.cummax() - eq).max()
    return float(dd)


def main():
    df_py_all = pd.read_csv(PY_TRADES_CSV)

    # Primeiro vamos inspecionar as datas reais presentes nos relatórios MT5
    all_mt5_deals = {}
    summaries = {}
    min_dates, max_dates = [], []

    for code, strat, asset, tf, cost_per_lot, desc in ROBOS_11:
        htm_path = os.path.join(REPORT_DIR, f"{code}_P1.htm")
        s = parse_htm_summary(htm_path)
        deals_df = parse_htm_deals(htm_path)
        summaries[strat] = s
        all_mt5_deals[strat] = deals_df
        if not deals_df.empty:
            min_dates.append(deals_df["date"].min())
            max_dates.append(deals_df["date"].max())

    mt5_start = min(min_dates) if min_dates else "2026-05-11"
    mt5_end = max(max_dates) if max_dates else "2026-11-06"
    print(f"Janela detectada nos deals MT5 Strategy Tester: {mt5_start} a {mt5_end}")

    # Para cada robô, reconstruir os trades fechados no MT5 (deals 'out' ou 'in/out')
    # No caso de SmartGrid (EST-13, 14, 15), 1 ciclo pode ter múltiplos 'in' (1 + 2 lotes) e 1 'out' de 3 lotes (ou BE).
    # O custo operacional por lote girado (round-turn) é R$ 2.00/contrato no WIN e R$ 5.00/contrato no WDO.
    # No MT5 deals: cada deal 'out' fecha 'volume' contratos (ou cada 'in' abre 'volume' contratos).
    rows = []
    mt5_daily_nocost_by_strat = {}
    mt5_daily_cost_by_strat = {}
    py_daily_nocost_by_strat = {}
    py_daily_cost_by_strat = {}

    for code, strat, asset, tf, cost_per_lot, desc in ROBOS_11:
        s = summaries[strat]
        deals = all_mt5_deals[strat]

        # Filtrar deals dentro de [2026-05-11, mt5_end]
        if not deals.empty:
            out_deals = deals[deals["direction"].isin(["out", "in/out", "saída", "entrada/saída"])].copy()
            in_deals = deals[deals["direction"].isin(["in", "entrada"])].copy()
        else:
            out_deals = pd.DataFrame()
            in_deals = pd.DataFrame()

        # No MT5 Tester (Model=1), o próprio testador já desconta 1 tick de spread Bid-Ask
        # em cada operação:
        #   - No WDO$N: 1 tick de spread = 0,5 pt = R$ 5,00/lote (100% do custo de 0,5 pt do backtest Python!)
        #   - No WIN$N: 1 tick de spread = 5,0 pts = R$ 1,00/lote (metade do custo de 10 pts = R$ 2,00/lote do Python!)
        # Portanto:
        #   - Para comparar SEM CUSTOS (Bruto puro): somamos de volta o spread nativo do MT5 (+R$ 1/lote WIN, +R$ 5/lote WDO)
        #   - Para comparar COM CUSTOS (R$ 2/lote WIN e R$ 5/lote WDO): descontamos apenas o residual B3 (+R$ 1/lote no WIN e R$ 0/lote no WDO)
        mt5_native_spread_per_lot = 1.0 if asset == "WIN" else 5.0
        extra_cost_per_lot = max(0.0, cost_per_lot - mt5_native_spread_per_lot)

        mt5_cycles = len(out_deals)
        mt5_lots_closed = float(out_deals["volume"].sum()) if not out_deals.empty else 0.0
        mt5_raw_htm_profit = float(out_deals["profit"].sum()) if not out_deals.empty else 0.0
        mt5_net_nocost = mt5_raw_htm_profit + mt5_lots_closed * mt5_native_spread_per_lot
        mt5_net_with_cost = mt5_raw_htm_profit - mt5_lots_closed * extra_cost_per_lot

        if not out_deals.empty:
            out_deals["profit_nocost"] = out_deals["profit"] + out_deals["volume"] * mt5_native_spread_per_lot
            out_deals["profit_with_cost"] = out_deals["profit"] - out_deals["volume"] * extra_cost_per_lot
            mt5_wr_nocost = float((out_deals["profit_nocost"] > 0).mean() * 100.0)
            mt5_wr_cost = float((out_deals["profit_with_cost"] > 0).mean() * 100.0)
            gp_nc = float(out_deals.loc[out_deals["profit_nocost"] > 0, "profit_nocost"].sum())
            gl_nc = float(-out_deals.loc[out_deals["profit_nocost"] < 0, "profit_nocost"].sum())
            mt5_pf_nocost = gp_nc / gl_nc if gl_nc > 0 else 99.9
            gp_c = float(out_deals.loc[out_deals["profit_with_cost"] > 0, "profit_with_cost"].sum())
            gl_c = float(-out_deals.loc[out_deals["profit_with_cost"] < 0, "profit_with_cost"].sum())
            mt5_pf_cost = gp_c / gl_c if gl_c > 0 else 99.9

            d_nc = out_deals.groupby("date")["profit_nocost"].sum()
            d_c = out_deals.groupby("date")["profit_with_cost"].sum()
        else:
            mt5_wr_nocost = mt5_wr_cost = mt5_pf_nocost = mt5_pf_cost = 0.0
            d_nc = pd.Series(dtype=float)
            d_c = pd.Series(dtype=float)

        mt5_daily_nocost_by_strat[strat] = d_nc
        mt5_daily_cost_by_strat[strat] = d_c
        mt5_dd_nc = compute_daily_dd(d_nc)
        mt5_dd_c = compute_daily_dd(d_c)

        # Agora Python no mesmo período [2026-05-11, mt5_end]
        py_sub = df_py_all[
            (df_py_all["strat"] == strat)
            & (df_py_all["date"] >= "2026-05-11")
            & (df_py_all["date"] <= mt5_end)
        ].copy()

        py_cycles = len(py_sub)
        py_lots = float(py_sub["lots"].sum()) if not py_sub.empty else 0.0
        py_net_nocost = float(py_sub["pnl_nocost"].sum()) if not py_sub.empty else 0.0
        py_net_cost = float(py_sub["pnl"].sum()) if not py_sub.empty else 0.0
        py_wr_nocost = float((py_sub["pnl_nocost"] > 0).mean() * 100.0) if not py_sub.empty else 0.0
        py_wr_cost = float((py_sub["pnl"] > 0).mean() * 100.0) if not py_sub.empty else 0.0

        py_gp_nc = float(py_sub.loc[py_sub["pnl_nocost"] > 0, "pnl_nocost"].sum()) if not py_sub.empty else 0.0
        py_gl_nc = float(-py_sub.loc[py_sub["pnl_nocost"] < 0, "pnl_nocost"].sum()) if not py_sub.empty else 0.0
        py_pf_nc = py_gp_nc / py_gl_nc if py_gl_nc > 0 else 99.9

        py_gp_c = float(py_sub.loc[py_sub["pnl"] > 0, "pnl"].sum()) if not py_sub.empty else 0.0
        py_gl_c = float(-py_sub.loc[py_sub["pnl"] < 0, "pnl"].sum()) if not py_sub.empty else 0.0
        py_pf_c = py_gp_c / py_gl_c if py_gl_c > 0 else 99.9

        py_d_nc = py_sub.groupby("date")["pnl_nocost"].sum() if not py_sub.empty else pd.Series(dtype=float)
        py_d_c = py_sub.groupby("date")["pnl"].sum() if not py_sub.empty else pd.Series(dtype=float)
        py_daily_nocost_by_strat[strat] = py_d_nc
        py_daily_cost_by_strat[strat] = py_d_c
        py_dd_nc = compute_daily_dd(py_d_nc)
        py_dd_c = compute_daily_dd(py_d_c)

        # Correlação diária / dias idênticos
        all_days = sorted(set(d_nc.index).union(set(py_d_nc.index)))
        if all_days:
            v_mt5 = np.array([d_nc.get(d, 0.0) for d in all_days])
            v_py = np.array([py_d_nc.get(d, 0.0) for d in all_days])
            same_day_pct = float((np.abs(v_mt5 - v_py) <= 10.0).mean() * 100.0)
        else:
            same_day_pct = 100.0

        rows.append({
            "strat": strat,
            "asset": asset,
            "tf": tf,
            "desc": desc,
            "mt5_trades": mt5_cycles,
            "py_trades": py_cycles,
            "diff_trades": mt5_cycles - py_cycles,
            "mt5_lots": int(mt5_lots_closed),
            "py_lots": int(py_lots),
            "mt5_wr_nc": round(mt5_wr_nocost, 1),
            "py_wr_nc": round(py_wr_nocost, 1),
            "mt5_pf_nc": round(mt5_pf_nocost, 2),
            "py_pf_nc": round(py_pf_nc, 2),
            "mt5_net_nc": round(mt5_net_nocost, 2),
            "py_net_nc": round(py_net_nocost, 2),
            "diff_net_nc": round(mt5_net_nocost - py_net_nocost, 2),
            "mt5_net_c": round(mt5_net_with_cost, 2),
            "py_net_c": round(py_net_cost, 2),
            "diff_net_c": round(mt5_net_with_cost - py_net_cost, 2),
            "mt5_dd_c": round(mt5_dd_c, 2),
            "py_dd_c": round(py_dd_c, 2),
            "mt5_htm_dd": round(float(s["max_dd_abs"]), 2),
            "day_match_pct": round(same_day_pct, 1),
        })

    df_res = pd.DataFrame(rows)

    # Adicionar linhas consolidadas: WIN 06 (M5), WIN 08 (M5+M15), WDO 03, TOTAL 09 (M5 Puro), TOTAL 11 (Proposta B ⭐)
    win_m5_strats = [r[1] for r in ROBOS_11 if r[2] == "WIN" and r[3] == "M5"]
    wdo_m5_strats = [r[1] for r in ROBOS_11 if r[2] == "WDO"]
    for grp_name, grp_asset, grp_tf, grp_desc, strats_list in [
        ("WIN 06 M5", "WIN",     "M5",     "Subtotal Índice M5 (Sem M15)",   win_m5_strats),
        ("WIN 08",    "WIN",     "M5/M15", "Subtotal Índice (8 Robôs)",      [r[1] for r in ROBOS_11 if r[2] == "WIN"]),
        ("WDO 03",    "WDO",     "M5",     "Subtotal Dólar (3 Robôs)",       wdo_m5_strats),
        ("TOTAL 09",  "WIN+WDO", "M5",     "Carteira 9 Robôs M5 (6WIN+3WDO)", win_m5_strats + wdo_m5_strats),
        ("TOTAL 11",  "WIN+WDO", "ALL",    "MT5 Proposta B ⭐ (11 Robôs)",    [r[1] for r in ROBOS_11]),
    ]:
        sub_r = df_res[df_res["strat"].isin(strats_list)]
        # Somar séries diárias para calcular DD consolidado real
        all_d = sorted(set().union(*[mt5_daily_nocost_by_strat[s].index for s in strats_list],
                                   *[py_daily_nocost_by_strat[s].index for s in strats_list]))
        mt5_port_nc = pd.Series([sum(mt5_daily_nocost_by_strat[s].get(d, 0.0) for s in strats_list) for d in all_d], index=all_d)
        mt5_port_c = pd.Series([sum(mt5_daily_cost_by_strat[s].get(d, 0.0) for s in strats_list) for d in all_d], index=all_d)
        py_port_nc = pd.Series([sum(py_daily_nocost_by_strat[s].get(d, 0.0) for s in strats_list) for d in all_d], index=all_d)
        py_port_c = pd.Series([sum(py_daily_cost_by_strat[s].get(d, 0.0) for s in strats_list) for d in all_d], index=all_d)

        mt5_dd_c = compute_daily_dd(mt5_port_c)
        py_dd_c = compute_daily_dd(py_port_c)

        # WR e PF do grupo
        mt5_tr = int(sub_r["mt5_trades"].sum())
        py_tr = int(sub_r["py_trades"].sum())
        mt5_lots = int(sub_r["mt5_lots"].sum())
        py_lots = int(sub_r["py_lots"].sum())
        mt5_net_nc = float(sub_r["mt5_net_nc"].sum())
        py_net_nc = float(sub_r["py_net_nc"].sum())
        mt5_net_c = float(sub_r["mt5_net_c"].sum())
        py_net_c = float(sub_r["py_net_c"].sum())

        grp_row = {
            "strat": grp_name,
            "asset": grp_asset,
            "tf": grp_tf,
            "desc": grp_desc,
            "mt5_trades": mt5_tr,
            "py_trades": py_tr,
            "diff_trades": mt5_tr - py_tr,
            "mt5_lots": mt5_lots,
            "py_lots": py_lots,
            "mt5_wr_nc": round(float(sub_r["mt5_wr_nc"].mean()), 1),
            "py_wr_nc": round(float(sub_r["py_wr_nc"].mean()), 1),
            "mt5_pf_nc": round(float(sub_r["mt5_pf_nc"].mean()), 2),
            "py_pf_nc": round(float(sub_r["py_pf_nc"].mean()), 2),
            "mt5_net_nc": round(mt5_net_nc, 2),
            "py_net_nc": round(py_net_nc, 2),
            "diff_net_nc": round(mt5_net_nc - py_net_nc, 2),
            "mt5_net_c": round(mt5_net_c, 2),
            "py_net_c": round(py_net_c, 2),
            "diff_net_c": round(mt5_net_c - py_net_c, 2),
            "mt5_dd_c": round(mt5_dd_c, 2),
            "py_dd_c": round(py_dd_c, 2),
            "mt5_htm_dd": round(compute_daily_dd(mt5_port_nc), 2),
            "day_match_pct": round(float(sub_r["day_match_pct"].mean()), 1),
        }
        df_res = pd.concat([df_res, pd.DataFrame([grp_row])], ignore_index=True)

    df_res["mt5_ret_dd_c"] = (df_res["mt5_net_c"] / df_res["mt5_dd_c"].replace(0, np.nan)).round(2)
    df_res["py_ret_dd_c"] = (df_res["py_net_c"] / df_res["py_dd_c"].replace(0, np.nan)).round(2)

    out_csv = os.path.join(REPORT_DIR, "parity_mt5_ohlc_vs_python_11_2026.csv")
    df_res.to_csv(out_csv, index=False)

    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    print("\n" + "=" * 150)
    print(f"  PARIDADE MT5 STRATEGY TESTER (MODEL=1 OHLC 1-MIN) vs PYTHON | PERÍODO: 2026-05-11 A {mt5_end}")
    print("=" * 150)
    print(df_res.to_string(index=False))


if __name__ == "__main__":
    main()

