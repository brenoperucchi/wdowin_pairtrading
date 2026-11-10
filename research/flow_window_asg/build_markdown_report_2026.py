# -*- coding: utf-8 -*-
import os
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "bt_dashboard_flow_2026")
DOC_PATH = os.path.join(ROOT_DIR, "docs", "BACKTEST_DASHBOARD_FLUXO_2026_IS_OOS.md")

df_port = pd.read_csv(os.path.join(OUT_DIR, "portfolios_dashboard_flow_is_oos_2026.csv"))
df_ind = pd.read_csv(os.path.join(OUT_DIR, "individual_16_x_7filters_is_oos_2026.csv"))
df_mon = pd.read_csv(os.path.join(OUT_DIR, "monthly_portfolios_2026.csv"))
df_asg = pd.read_csv(os.path.join(OUT_DIR, "asg_pure_window_turn_is_oos_2026.csv"))

STRICT_ACTIVE_FLOW_MAP = {
    "EST-01": "6_COMBO_SMART",
    "EST-03": "4_FLUXO_ABSORCAO",
    "EST-04": "4_FLUXO_ABSORCAO",
    "EST-05": "4_FLUXO_ABSORCAO",
    "EST-07": "4_FLUXO_ABSORCAO",
    "EST-13": "4_FLUXO_ABSORCAO",
    "EST-14": "4_FLUXO_ABSORCAO",
    "EST-15": "4_FLUXO_ABSORCAO",
    "EST-16": "2_JANELA_S_EXPLOSAO",
    "WIN-E2": "6_COMBO_SMART",
    "WDO-01": "3_FLUXO_INST",
    "WDO-02": "4_FLUXO_ABSORCAO",
    "WDO-05": "1_JANELA_ASG",
    "WDO-07": "3_FLUXO_INST",
    "WDO-09": "1_JANELA_ASG",
    "WDO-10": "3_FLUXO_INST",
}

lines = []
lines.append("# Backtest de Longo Prazo 2026 (OOS vs IS vs TOTAL) — Estratégias de Fluxo nas Walls & Janela A.S.G (Dashboard)\n")
lines.append("- **Base de Dados:** 212 pregões completos de 2026 (`02/01/2026` a `06/11/2026`) com GEX B3 + Sessões Históricas de Fluxo Institucional/Varejo reconstruídas tick-a-tick (`.tkc` do MT5 `WIN$N` e `WDO$N`) em `data/processed/gex_historical_sessions_v1/`.")
lines.append("- **Divisão de Períodos:**")
lines.append("  1. **OUT-OF-SAMPLE (OOS):** `02/01/2026` a `06/05/2026` (**84 pregões** novos de backfill B3 + ticks MT5, 100% fora da amostra).")
lines.append("  2. **IN-SAMPLE (IS):** `07/05/2026` a `06/11/2026` (**128 pregões** originais).")
lines.append("  3. **PERÍODO TOTAL 2026:** `02/01/2026` a `06/11/2026` (**212 pregões**).")
lines.append("- **Custos Operacionais Incluídos:** `WIN = 10 pts/contrato (R$ 2,00/lote)` | `WDO = 0,5 pt/contrato (R$ 5,00/lote)`.\n")

for p_code, p_title in [
    ("OOS_JAN_MAI", "1. OUT-OF-SAMPLE (OOS: 02/01/2026 a 06/05/2026 — 84 Pregões)"),
    ("IS_MAI_NOV", "2. IN-SAMPLE (IS: 07/05/2026 a 06/11/2026 — 128 Pregões)"),
    ("TOTAL_2026", "3. PERÍODO TOTAL 2026 (02/01/2026 a 06/11/2026 — 212 Pregões)"),
]:
    lines.append(f"## {p_title}\n")
    lines.append("### A) Carteiras do Dashboard (Sem Filtro vs. Com Filtro de Fluxo)\n")
    lines.append("| Carteira | Descrição | Trades | Lotes | WR (%) | PF Líq. | PF Bruto | Lucro Líq. (R$) | Lucro Bruto (R$) | Max DD Dia (R$) | Max DD Trade (R$) | Ret/DD | Payoff | Méd/Trade (R$) | Sharpe | % Dias + | Pior Dia (R$) | Melhor Dia (R$) | Max Streak |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    sub_p = df_port[df_port["period"] == p_code]
    for _, r in sub_p.iterrows():
        lines.append(
            f"| **{r['portfolio_id']}** | {r['description']} | {int(r['trades'])} | {int(r['lots'])} | {r['wr']:.1f}% | **{r['pf']:.2f}** | {r['pf_nocost']:.2f} | **R$ {r['net']:+,.0f}** | R$ {r['net_nocost']:+,.0f} | R$ {r['dd_day']:,.0f} | R$ {r['dd_trade']:,.0f} | **{r['ret_dd']:.2f}x** | {r['payoff']:.2f} | R$ {r['avg_trade']:+.2f} | **{r['sharpe']:.2f}** | {r['pos_days_pct']:.1f}% | R$ {r['worst_day']:+,.0f} | R$ {r['best_day']:+,.0f} | {int(r['max_streak'])} |"
        )
    lines.append("\n### B) Comparação por Estratégia (Sem Filtro `0_BASE_MT5` vs. Filtro de Fluxo Ativo)\n")
    lines.append("| Estratégia | Ativo | TF | Filtro Ativo Aplicado | Tr (Sem -> C/Fluxo) | WR% (Sem -> C/Fluxo) | PF Líq. (Sem -> C/Fluxo) | Lucro Líq. R$ (Sem -> C/Fluxo) | Max DD Dia R$ (Sem -> C/Fluxo) | Ret/DD (Sem -> C/Fluxo) | Sharpe (Sem -> C/Fluxo) |")
    lines.append("| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    sub_i = df_ind[df_ind["period"] == p_code]
    for sid in STRICT_ACTIVE_FLOW_MAP:
        fn = STRICT_ACTIVE_FLOW_MAP[sid]
        b = sub_i[(sub_i["strat"] == sid) & (sub_i["filter"] == "0_BASE_MT5")].iloc[0]
        f = sub_i[(sub_i["strat"] == sid) & (sub_i["filter"] == fn)].iloc[0]
        lines.append(
            f"| **{sid}** | {b['asset']} | {b['tf']} | `{fn}` | {int(b['trades'])} -> **{int(f['trades'])}** | {b['wr']:.1f}% -> **{f['wr']:.1f}%** | {b['pf']:.2f} -> **{f['pf']:.2f}** | R$ {b['net']:+,.0f} -> **R$ {f['net']:+,.0f}** | R$ {b['dd_day']:,.0f} -> **R$ {f['dd_day']:,.0f}** | {b['ret_dd']:.2f}x -> **{f['ret_dd']:.2f}x** | {b['sharpe']:.2f} -> **{f['sharpe']:.2f}** |"
        )
    lines.append("\n")

lines.append("## 4. Evolução Mensal 2026 das Carteiras (Líquido em R$)\n")
cols = list(df_mon.columns)
header = "| Carteira | " + " | ".join(cols[1:]) + " |"
sep = "| :--- | " + " | ".join([":---:" for _ in cols[1:]]) + " |"
lines.append(header)
lines.append(sep)
for _, r in df_mon.iterrows():
    vals = [f"R$ {r[c]:+,.0f}" for c in cols[1:]]
    lines.append(f"| **{r['portfolio_id']}** | " + " | ".join(vals) + " |")
lines.append("\n")

lines.append("## 5. Operação Pura da Virada da Janela A.S.G (`Stop & Reverse` 09:15–17:00)\n")
lines.append("| Período | Setup Janela A.S.G | Trades | WR (%) | PF Líq. | PF Bruto | Lucro Líq. (R$) | Max DD Dia (R$) | Ret/DD | Sharpe |")
lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
for _, r in df_asg.iterrows():
    lines.append(
        f"| **{r['period']}** | {r['strat']} | {int(r['trades'])} | {r['wr']:.1f}% | {r['pf']:.2f} | {r['pf_nocost']:.2f} | R$ {r['net']:+,.0f} | R$ {r['dd_day']:,.0f} | {r['ret_dd']:.2f}x | {r['sharpe']:.2f} |"
    )

with open(DOC_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Saved report to {DOC_PATH}")

