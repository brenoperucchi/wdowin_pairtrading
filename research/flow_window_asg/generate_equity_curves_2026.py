# -*- coding: utf-8 -*-
import os
import json
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_DIR = os.path.join(ROOT_DIR, "data", "reports", "bt_dashboard_flow_2026")
IMG_DIR = os.path.join(ROOT_DIR, "docs", "images")
ARTIFACT_DIR = r"C:\Users\ryzen\.gemini\antigravity\brain\6a2a15de-ce6b-416a-ac6a-2e7aefc25061"

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

OOS_END = "2026-05-06"
IS_START = "2026-05-07"

CHAMPION_FLOW_FILTER_MAP = {
    "EST-01": "6_COMBO_SMART",
    "EST-03": "4_FLUXO_ABSORCAO",
    "EST-04": "4_FLUXO_ABSORCAO",
    "EST-05": "4_FLUXO_ABSORCAO",
    "EST-07": "4_FLUXO_ABSORCAO",
    "EST-13": "4_FLUXO_ABSORCAO",
    "EST-14": "4_FLUXO_ABSORCAO",
    "EST-15": "0_BASE_MT5",
    "EST-16": "2_JANELA_S_EXPLOSAO",
    "WIN-E2": "6_COMBO_SMART",
    "WDO-01": "3_FLUXO_INST",
    "WDO-02": "0_BASE_MT5",
    "WDO-05": "1_JANELA_ASG",
    "WDO-07": "0_BASE_MT5",
    "WDO-09": "1_JANELA_ASG",
    "WDO-10": "3_FLUXO_INST",
}

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

STRAT_ORDER = [
    "EST-01", "EST-03", "EST-04", "EST-05",
    "EST-07", "EST-13", "EST-14", "EST-15",
    "EST-16", "WIN-E2", "WDO-01", "WDO-02",
    "WDO-05", "WDO-07", "WDO-09", "WDO-10",
]

WALLS_6 = ["EST-14", "EST-04", "EST-07", "WIN-E2", "WDO-07", "WDO-10"]
TOP_6 = ["EST-04", "EST-07", "EST-14", "WDO-02", "WDO-07", "WDO-10"]
ALL_11 = ["EST-01", "EST-04", "EST-07", "EST-13", "EST-14", "EST-15", "EST-16", "WDO-02", "WDO-07", "WDO-09", "WDO-10"]
ALL_15 = [s for s in STRAT_ORDER if s != "WIN-E2"]


def main():
    df = pd.read_csv(os.path.join(REPORT_DIR, "trades_16_strategies_all_filters_2026.csv"))
    df["date"] = df["date"].astype(str)
    all_days = sorted(df["date"].unique())
    oos_days = [d for d in all_days if d <= OOS_END]
    dt_index = pd.to_datetime(all_days)
    dt_oos = pd.to_datetime(oos_days)
    split_dt = pd.to_datetime(OOS_END)

    def daily_pnl_for_portfolio(strats, fmap, days=all_days):
        parts = []
        for s in strats:
            fn = fmap[s] if isinstance(fmap, dict) else fmap
            sub = df[(df["strat"] == s) & (df["filter"] == fn)]
            parts.append(sub)
        cat = pd.concat(parts, ignore_index=True)
        s_day = cat.groupby("date")["pnl"].sum().reindex(days, fill_value=0.0)
        return s_day.values.astype(float)

    def eq_and_dd(daily_arr):
        eq = np.cumsum(daily_arr)
        pk = np.maximum.accumulate(np.insert(eq, 0, 0.0))[1:]
        dd = eq - pk  # negative or zero
        return np.round(eq, 1), np.round(dd, 1)

    port_series = {
        "15_MT5_BASE": {
            "label": "15 Robôs MT5 (Sem Filtro)",
            "color": "#38bdf8",
            "daily": daily_pnl_for_portfolio(ALL_15, "0_BASE_MT5"),
        },
        "15_MT5_FLOW": {
            "label": "15 Robôs MT5 (C/ Fluxo Campeão)",
            "color": "#818cf8",
            "daily": daily_pnl_for_portfolio(ALL_15, CHAMPION_FLOW_FILTER_MAP),
        },
        "15_MT5_STRICT": {
            "label": "15 Robôs MT5 (C/ Fluxo Ativo 100%)",
            "color": "#a855f7",
            "daily": daily_pnl_for_portfolio(ALL_15, STRICT_ACTIVE_FLOW_MAP),
        },
        "15_MT5_INST": {
            "label": "15 Robôs MT5 (Filtro 3_FLUXO_INST Único)",
            "color": "#22c55e",
            "daily": daily_pnl_for_portfolio(ALL_15, "3_FLUXO_INST"),
        },
        "11_DASH_BASE": {
            "label": "11 Estratégias Dashboard (Sem Filtro)",
            "color": "#94a3b8",
            "daily": daily_pnl_for_portfolio(ALL_11, "0_BASE_MT5"),
        },
        "11_DASH_FLOW": {
            "label": "11 Estratégias Dashboard (C/ Fluxo Campeão)",
            "color": "#f59e0b",
            "daily": daily_pnl_for_portfolio(ALL_11, CHAMPION_FLOW_FILTER_MAP),
        },
        "11_DASH_STRICT": {
            "label": "11 Estratégias Dashboard (C/ Fluxo Ativo 100%)",
            "color": "#fb923c",
            "daily": daily_pnl_for_portfolio(ALL_11, STRICT_ACTIVE_FLOW_MAP),
        },
        "WALLS_6_BASE": {
            "label": "Localhost 2 · 6 Walls (Sem Filtro)",
            "color": "#f43f5e",
            "daily": daily_pnl_for_portfolio(WALLS_6, "0_BASE_MT5"),
        },
        "WALLS_6_FLOW": {
            "label": "Localhost 2 · 6 Walls (C/ Fluxo Padrão)",
            "color": "#ec4899",
            "daily": daily_pnl_for_portfolio(WALLS_6, CHAMPION_FLOW_FILTER_MAP),
        },
        "WALLS_6_STRICT": {
            "label": "Localhost 2 · 6 Walls (C/ Fluxo Ativo 100%)",
            "color": "#10b981",
            "daily": daily_pnl_for_portfolio(WALLS_6, STRICT_ACTIVE_FLOW_MAP),
        },
    }

    for k, v in port_series.items():
        eq, dd = eq_and_dd(v["daily"])
        v["eq"] = eq
        v["dd"] = dd
        eq_oos, dd_oos = eq_and_dd(v["daily"][:len(oos_days)])
        v["eq_oos"] = eq_oos
        v["dd_oos"] = dd_oos

    # Individual strategies (Base vs Active Flow)
    strat_series = {}
    for s in STRAT_ORDER:
        fn = STRICT_ACTIVE_FLOW_MAP[s]
        d_base = daily_pnl_for_portfolio([s], "0_BASE_MT5")
        d_flow = daily_pnl_for_portfolio([s], fn)
        eq_b, dd_b = eq_and_dd(d_base)
        eq_f, dd_f = eq_and_dd(d_flow)
        strat_series[s] = {
            "filter": fn,
            "daily_base": d_base,
            "daily_flow": d_flow,
            "eq_base": eq_b,
            "dd_base": dd_b,
            "eq_flow": eq_f,
            "dd_flow": dd_f,
        }

    # =========================================================================
    # CHART 1: Curvas de Capital Completas 2026 (OOS + IS) + Zoom OOS + Drawdown
    # =========================================================================
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(18, 13), dpi=140, facecolor="#0b0f19")
    gs = fig.add_gridspec(3, 2, height_ratios=[1.35, 1.0, 0.85], hspace=0.34, wspace=0.18)

    # 1A: Ano Completo 2026 (Todas as Carteiras Principais)
    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor("#111827")
    ax1.axvspan(dt_index[0], split_dt, color="#1e293b", alpha=0.45, label="Período OOS (02/01 a 06/05 — 84 pregões)")
    ax1.axvline(split_dt, color="#fbbf24", linestyle="--", linewidth=1.8, label="Divisão OOS / IS (06/05/2026)")

    plot_keys_main = [
        ("15_MT5_BASE", "-", 2.3),
        ("15_MT5_FLOW", "--", 2.0),
        ("15_MT5_INST", "-", 2.3),
        ("11_DASH_FLOW", "-", 2.0),
        ("WALLS_6_BASE", ":", 1.8),
        ("WALLS_6_STRICT", "-", 2.5),
    ]
    for k, ls, lw in plot_keys_main:
        p = port_series[k]
        tot = p["eq"][-1]
        mdd = abs(np.min(p["dd"]))
        rdd = tot / mdd if mdd > 0 else 99.9
        ax1.plot(
            dt_index, p["eq"], linestyle=ls, linewidth=lw, color=p["color"],
            label=f"{p['label']}  [Net: R$ {tot:+,.0f} | DD: R$ {mdd:,.0f} | Ret/DD: {rdd:.2f}x]"
        )

    ax1.axhline(0, color="#475569", linewidth=1.0)
    ax1.set_title("CURVAS DE CAPITAL 2026 COMPLETO (212 PREGÕES: OOS Jan–Mai + IS Mai–Nov) — LÍQUIDO DE CUSTOS (R$)", fontsize=13, fontweight="bold", color="#f8fafc", pad=10)
    ax1.set_ylabel("Lucro Líquido Acumulado (R$)", fontsize=10, color="#cbd5e1")
    ax1.grid(True, linestyle=":", alpha=0.25, color="#64748b")
    ax1.legend(loc="upper left", fontsize=8.8, framealpha=0.85, facecolor="#0f172a", edgecolor="#334155", ncol=2)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    # 1B: Zoom no OOS (02/01/2026 a 06/05/2026) — Carteira 15 Robôs MT5
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.set_facecolor("#111827")
    for k, ls, lw in [("15_MT5_BASE", "-", 2.0), ("15_MT5_FLOW", "--", 1.8), ("15_MT5_STRICT", "-.", 2.0), ("15_MT5_INST", "-", 2.4)]:
        p = port_series[k]
        tot_o = p["eq_oos"][-1]
        mdd_o = abs(np.min(p["dd_oos"]))
        rdd_o = tot_o / mdd_o if mdd_o > 0 else 0.0
        ax2.plot(
            dt_oos, p["eq_oos"], linestyle=ls, linewidth=lw, color=p["color"],
            label=f"{p['label']} (OOS: R$ {tot_o:+,.0f} | DD R$ {mdd_o:,.0f} | {rdd_o:.2f}x)"
        )
    ax2.axhline(0, color="#475569", linewidth=1.0)
    ax2.set_title("ZOOM OOS (02/01 a 06/05) — CARTEIRA 15 ROBÔS MT5", fontsize=11, fontweight="bold", color="#38bdf8")
    ax2.set_ylabel("Lucro OOS (R$)", fontsize=9.5, color="#cbd5e1")
    ax2.grid(True, linestyle=":", alpha=0.25, color="#64748b")
    ax2.legend(loc="upper left", fontsize=8.0, framealpha=0.85, facecolor="#0f172a")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))

    # 1C: Zoom no OOS (02/01/2026 a 06/05/2026) — Carteira Localhost 2 (6 Walls) & 11 Dashboard
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.set_facecolor("#111827")
    for k, ls, lw in [("WALLS_6_BASE", ":", 1.8), ("WALLS_6_FLOW", "--", 2.0), ("WALLS_6_STRICT", "-", 2.5), ("11_DASH_BASE", ":", 1.6), ("11_DASH_STRICT", "-.", 1.9)]:
        p = port_series[k]
        tot_o = p["eq_oos"][-1]
        mdd_o = abs(np.min(p["dd_oos"]))
        rdd_o = tot_o / mdd_o if mdd_o > 0 else 0.0
        ax3.plot(
            dt_oos, p["eq_oos"], linestyle=ls, linewidth=lw, color=p["color"],
            label=f"{p['label']} (OOS: R$ {tot_o:+,.0f} | DD R$ {mdd_o:,.0f} | {rdd_o:.2f}x)"
        )
    ax3.axhline(0, color="#475569", linewidth=1.0)
    ax3.set_title("ZOOM OOS (02/01 a 06/05) — CARTEIRA 6 WALLS & 11 DASHBOARD", fontsize=11, fontweight="bold", color="#10b981")
    ax3.set_ylabel("Lucro OOS (R$)", fontsize=9.5, color="#cbd5e1")
    ax3.grid(True, linestyle=":", alpha=0.25, color="#64748b")
    ax3.legend(loc="upper left", fontsize=8.0, framealpha=0.85, facecolor="#0f172a")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))

    # 1D: Curva de Drawdown Diário (Underwater Plot) — Ano Completo 2026
    ax4 = fig.add_subplot(gs[2, :])
    ax4.set_facecolor("#111827")
    ax4.axvspan(dt_index[0], split_dt, color="#1e293b", alpha=0.45)
    ax4.axvline(split_dt, color="#fbbf24", linestyle="--", linewidth=1.6)
    for k, ls, lw in [("15_MT5_BASE", "-", 1.7), ("15_MT5_INST", "-", 2.1), ("WALLS_6_BASE", ":", 1.7), ("WALLS_6_STRICT", "-", 2.2)]:
        p = port_series[k]
        ax4.plot(dt_index, p["dd"], linestyle=ls, linewidth=lw, color=p["color"], label=f"{p['label']} (Max DD: R$ {abs(np.min(p['dd'])):,.0f})")
        ax4.fill_between(dt_index, p["dd"], 0, color=p["color"], alpha=0.08)
    ax4.axhline(0, color="#475569", linewidth=1.0)
    ax4.set_title("CURVA DE DRAWDOWN DIÁRIO (UNDERWATER PLOT 2026) — REDUÇÃO DE RISCO PELOS FILTROS DE FLUXO", fontsize=11, fontweight="bold", color="#f8fafc")
    ax4.set_ylabel("Drawdown Diário (R$)", fontsize=9.5, color="#cbd5e1")
    ax4.grid(True, linestyle=":", alpha=0.25, color="#64748b")
    ax4.legend(loc="lower right", fontsize=8.5, framealpha=0.85, facecolor="#0f172a", ncol=2)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    p1_path = os.path.join(IMG_DIR, "equity_portfolios_2026_full_and_oos.png")
    fig.savefig(p1_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    shutil.copy2(p1_path, os.path.join(ARTIFACT_DIR, "equity_portfolios_2026_full_and_oos.png"))

    # =========================================================================
    # CHART 2: Grid 4x4 das 16 Estratégias Individuais (Sem Filtro vs C/ Fluxo)
    # =========================================================================
    fig2, axes = plt.subplots(4, 4, figsize=(20, 14), dpi=135, facecolor="#0b0f19")
    fig2.suptitle(
        "CURVAS DE CAPITAL INDIVIDUAIS (2026 COMPLETO: OOS Jan–Mai | IS Mai–Nov) — SEM FILTRO ( tracejado ) vs C/ FILTRO DE FLUXO ATIVO ( sólido )",
        fontsize=14, fontweight="bold", color="#f8fafc", y=0.98
    )

    for idx, s in enumerate(STRAT_ORDER):
        r, c = divmod(idx, 4)
        ax = axes[r, c]
        ax.set_facecolor("#111827")
        st = strat_series[s]
        ax.axvspan(dt_index[0], split_dt, color="#1e293b", alpha=0.42)
        ax.axvline(split_dt, color="#fbbf24", linestyle="--", linewidth=1.1, alpha=0.85)
        ax.axhline(0, color="#475569", linewidth=0.8)

        tot_b = st["eq_base"][-1]
        dd_b = abs(np.min(st["dd_base"]))
        tot_f = st["eq_flow"][-1]
        dd_f = abs(np.min(st["dd_flow"]))

        col_main = "#38bdf8" if (s.startswith("EST") or s.startswith("WIN")) else "#10b981"
        ax.plot(dt_index, st["eq_base"], linestyle="--", linewidth=1.4, color="#94a3b8", alpha=0.85, label=f"Sem Filtro: R$ {tot_b:+,.0f} (DD {dd_b:,.0f})")
        ax.plot(dt_index, st["eq_flow"], linestyle="-", linewidth=2.0, color=col_main, label=f"{st['filter'][:12]}: R$ {tot_f:+,.0f} (DD {dd_f:,.0f})")

        ax.set_title(f"{s}  ({st['filter']})", fontsize=9.5, fontweight="bold", color="#f1f5f9")
        ax.grid(True, linestyle=":", alpha=0.22, color="#64748b")
        ax.legend(loc="upper left", fontsize=7.3, framealpha=0.82, facecolor="#0f172a")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
        ax.tick_params(axis="both", labelsize=7.5)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    p2_path = os.path.join(IMG_DIR, "equity_16_individual_strategies_2026.png")
    fig2.savefig(p2_path, bbox_inches="tight", facecolor=fig2.get_facecolor())
    plt.close(fig2)
    shutil.copy2(p2_path, os.path.join(ARTIFACT_DIR, "equity_16_individual_strategies_2026.png"))

    # =========================================================================
    # INTERACTIVE HTML WIDGET (Generative UI) in ARTIFACT_DIR
    # =========================================================================
    widget_data = {
        "dates": all_days,
        "oos_end_idx": len(oos_days) - 1,
        "oos_end_date": OOS_END,
        "portfolios": {
            k: {
                "label": v["label"],
                "color": v["color"],
                "eq": v["eq"].tolist(),
                "dd": v["dd"].tolist(),
                "eq_oos": v["eq_oos"].tolist(),
            }
            for k, v in port_series.items()
        },
        "strategies": {
            s: {
                "filter": strat_series[s]["filter"],
                "eq_base": strat_series[s]["eq_base"].tolist(),
                "eq_flow": strat_series[s]["eq_flow"].tolist(),
                "dd_base": strat_series[s]["dd_base"].tolist(),
                "dd_flow": strat_series[s]["dd_flow"].tolist(),
            }
            for s in STRAT_ORDER
        },
    }

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-2">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
      <div>
        <h2 class="text-[var(--foreground)] font-semibold text-base">Curvas de Capital 2026 — OOS (02/01–06/05) vs IS (07/05–06/11)</h2>
        <p class="text-[var(--muted-foreground)] text-xs">212 pregões · Custos B3 incluídos · Linha tracejada amarela separa OOS (84d) e IS (128d)</p>
      </div>
      <div class="flex flex-wrap items-center gap-1.5">
        <button onclick="setMode('main')" id="btn-main" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--primary)] text-[var(--primary-foreground)]">Carteiras 2026</button>
        <button onclick="setMode('oos')" id="btn-oos" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">Zoom OOS (Jan–Mai)</button>
        <button onclick="setMode('dd')" id="btn-dd" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">Drawdown Diário</button>
        <select id="strat-select" onchange="setMode('strat')" class="px-2 py-1 rounded text-xs border border-[var(--border)] bg-[var(--secondary)] text-[var(--foreground)]">
          <option value="">Estratégia Individual...</option>
          {"".join(f'<option value="{s}">{s} ({strat_series[s]["filter"]})</option>' for s in STRAT_ORDER)}
        </select>
      </div>
    </div>

    <div class="relative w-full" style="height: 295px;">
      <canvas id="eqCanvas" class="w-full h-full cursor-crosshair"></canvas>
      <div id="tooltip" class="hidden absolute pointer-events-none bg-[var(--background)] border border-[var(--border)] rounded-lg px-2.5 py-1.5 text-xs shadow-md z-10"></div>
    </div>

    <div id="legend-box" class="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2.5 pt-2 border-t border-[var(--border)] text-xs"></div>
  </div>

  <script>
    const DATA = {json.dumps(widget_data)};
    let currentMode = 'main';
    const canvas = document.getElementById('eqCanvas');
    const ctx = canvas.getContext('2d');
    const tooltip = document.getElementById('tooltip');
    const legendBox = document.getElementById('legend-box');

    function getActiveSeries() {{
      const P = DATA.portfolios;
      if (currentMode === 'main') {{
        return {{
          dates: DATA.dates,
          showSplit: true,
          isDD: false,
          lines: [
            {{ name: '15 Robôs MT5 Sem Filtro', color: '#38bdf8', data: P['15_MT5_BASE'].eq, dash: [] }},
            {{ name: '15 Robôs C/ Fluxo Ativo', color: '#a855f7', data: P['15_MT5_STRICT'].eq, dash: [5,3] }},
            {{ name: '15 Robôs C/ 3_FLUXO_INST (DD R$ 2.357)', color: '#22c55e', data: P['15_MT5_INST'].eq, dash: [] }},
            {{ name: '11 Dashboard C/ Fluxo', color: '#f59e0b', data: P['11_DASH_FLOW'].eq, dash: [] }},
            {{ name: '6 Walls Localhost 2 Sem Fluxo', color: '#f43f5e', data: P['WALLS_6_BASE'].eq, dash: [3,3] }},
            {{ name: '6 Walls C/ Fluxo 100% (Ret/DD 18,4x)', color: '#10b981', data: P['WALLS_6_STRICT'].eq, dash: [] }}
          ]
        }};
      }} else if (currentMode === 'oos') {{
        const oosDates = DATA.dates.slice(0, DATA.oos_end_idx + 1);
        return {{
          dates: oosDates,
          showSplit: false,
          isDD: false,
          lines: [
            {{ name: '15 Robôs Sem Filtro (OOS +R$ 7.812 | DD 6.217)', color: '#38bdf8', data: P['15_MT5_BASE'].eq_oos, dash: [4,3] }},
            {{ name: '15 Robôs C/ 3_FLUXO_INST (OOS +R$ 6.149 | DD 2.196)', color: '#22c55e', data: P['15_MT5_INST'].eq_oos, dash: [] }},
            {{ name: '15 Robôs C/ Fluxo Ativo (OOS +R$ 5.122 | DD 3.623)', color: '#a855f7', data: P['15_MT5_STRICT'].eq_oos, dash: [] }},
            {{ name: '6 Walls C/ Fluxo 100% (OOS +R$ 1.800 | DD 825)', color: '#10b981', data: P['WALLS_6_STRICT'].eq_oos, dash: [] }},
            {{ name: '6 Walls Sem Fluxo (OOS +R$ 541 | DD 1.755)', color: '#f43f5e', data: P['WALLS_6_BASE'].eq_oos, dash: [3,3] }}
          ]
        }};
      }} else if (currentMode === 'dd') {{
        return {{
          dates: DATA.dates,
          showSplit: true,
          isDD: true,
          lines: [
            {{ name: '15 Robôs Sem Filtro (Max DD -R$ 6.217)', color: '#38bdf8', data: P['15_MT5_BASE'].dd, dash: [4,3] }},
            {{ name: '15 Robôs C/ 3_FLUXO_INST (Max DD -R$ 2.357)', color: '#22c55e', data: P['15_MT5_INST'].dd, dash: [] }},
            {{ name: '6 Walls Sem Fluxo (Max DD -R$ 1.755)', color: '#f43f5e', data: P['WALLS_6_BASE'].dd, dash: [3,3] }},
            {{ name: '6 Walls C/ Fluxo 100% (Max DD -R$ 825)', color: '#10b981', data: P['WALLS_6_STRICT'].dd, dash: [] }}
          ]
        }};
      }} else {{
        const sel = document.getElementById('strat-select').value || 'EST-14';
        const st = DATA.strategies[sel];
        return {{
          dates: DATA.dates,
          showSplit: true,
          isDD: false,
          lines: [
            {{ name: sel + ' Sem Filtro (0_BASE_MT5)', color: '#94a3b8', data: st.eq_base, dash: [4,3] }},
            {{ name: sel + ' C/ Fluxo (' + st.filter + ')', color: '#10b981', data: st.eq_flow, dash: [] }}
          ]
        }};
      }}
    }}

    function setMode(m) {{
      currentMode = m;
      ['main', 'oos', 'dd'].forEach(k => {{
        const b = document.getElementById('btn-' + k);
        if (k === m) {{
          b.className = 'px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--primary)] text-[var(--primary-foreground)]';
        }} else {{
          b.className = 'px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]';
        }}
      }});
      if (m !== 'strat') {{
        document.getElementById('strat-select').value = '';
      }}
      drawChart();
    }}

    function drawChart(hoverIdx = null) {{
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);

      const W = rect.width;
      const H = rect.height;
      const padL = 62, padR = 16, padT = 14, padB = 26;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;

      const cfg = getActiveSeries();
      const dates = cfg.dates;
      const N = dates.length;

      let minV = 0, maxV = 0;
      cfg.lines.forEach(l => {{
        l.data.forEach(v => {{
          if (v < minV) minV = v;
          if (v > maxV) maxV = v;
        }});
      }});
      const span = Math.max(maxV - minV, 500);
      minV -= span * 0.06;
      maxV += span * 0.06;

      const xOf = i => padL + (i / Math.max(1, N - 1)) * plotW;
      const yOf = v => padT + (1 - (v - minV) / (maxV - minV)) * plotH;

      ctx.clearRect(0, 0, W, H);

      // OOS Shading
      if (cfg.showSplit) {{
        const splitX = xOf(DATA.oos_end_idx);
        ctx.fillStyle = 'rgba(148, 163, 184, 0.08)';
        ctx.fillRect(padL, padT, splitX - padL, plotH);

        ctx.save();
        ctx.strokeStyle = '#fbbf24';
        ctx.lineWidth = 1.4;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(splitX, padT);
        ctx.lineTo(splitX, padT + plotH);
        ctx.stroke();
        ctx.fillStyle = '#fbbf24';
        ctx.font = '12px sans-serif';
        ctx.fillText('← OOS | IS →', splitX - 36, padT + 14);
        ctx.restore();
      }}

      // Horizontal Grid & Zero line
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)';
      ctx.lineWidth = 1;
      ctx.font = '12px sans-serif';
      ctx.fillStyle = 'rgba(148, 163, 184, 0.85)';
      const steps = 5;
      for (let s = 0; s <= steps; s++) {{
        const val = minV + (s / steps) * (maxV - minV);
        const y = yOf(val);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(W - padR, y);
        ctx.stroke();
        const lbl = 'R$ ' + Math.round(val).toLocaleString('pt-BR');
        ctx.fillText(lbl, 4, y + 4);
      }}

      if (minV < 0 && maxV > 0) {{
        const y0 = yOf(0);
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.55)';
        ctx.beginPath();
        ctx.moveTo(padL, y0);
        ctx.lineTo(W - padR, y0);
        ctx.stroke();
      }}

      // X-axis date labels
      const xTicks = 6;
      for (let t = 0; t <= xTicks; t++) {{
        const idx = Math.round((t / xTicks) * (N - 1));
        const x = xOf(idx);
        const dStr = dates[idx].slice(8, 10) + '/' + dates[idx].slice(5, 7);
        ctx.fillText(dStr, x - 16, H - 6);
      }}

      // Plot Lines
      cfg.lines.forEach(line => {{
        ctx.save();
        ctx.strokeStyle = line.color;
        ctx.lineWidth = 2.1;
        ctx.setLineDash(line.dash || []);
        ctx.beginPath();
        for (let i = 0; i < N; i++) {{
          const x = xOf(i);
          const y = yOf(line.data[i]);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }}
        ctx.stroke();
        ctx.restore();
      }});

      // Hover Crosshair
      if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < N) {{
        const hx = xOf(hoverIdx);
        ctx.save();
        ctx.strokeStyle = 'rgba(226, 232, 240, 0.5)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hx, padT);
        ctx.lineTo(hx, padT + plotH);
        ctx.stroke();
        cfg.lines.forEach(line => {{
          const hy = yOf(line.data[hoverIdx]);
          ctx.fillStyle = line.color;
          ctx.beginPath();
          ctx.arc(hx, hy, 3.5, 0, Math.PI * 2);
          ctx.fill();
        }});
        ctx.restore();
      }}

      // Update Legend
      legendBox.innerHTML = cfg.lines.map(l => {{
        const lastVal = l.data[l.data.length - 1];
        const sign = lastVal >= 0 ? '+' : '';
        return `<div class="flex items-center gap-1.5">
          <span class="inline-block w-3 h-2.5 rounded-sm" style="background:${{l.color}}"></span>
          <span class="text-[var(--foreground)] font-medium">${{l.name}}:</span>
          <span class="text-[var(--muted-foreground)] font-semibold">${{sign}}R$ ${{Math.round(lastVal).toLocaleString('pt-BR')}}</span>
        </div>`;
      }}).join('');
    }}

    canvas.addEventListener('mousemove', e => {{
      const rect = canvas.getBoundingClientRect();
      const padL = 62, padR = 16;
      const plotW = rect.width - padL - padR;
      const cfg = getActiveSeries();
      const N = cfg.dates.length;
      const relX = e.clientX - rect.left - padL;
      const idx = Math.max(0, Math.min(N - 1, Math.round((relX / plotW) * (N - 1))));
      drawChart(idx);

      const dStr = cfg.dates[idx];
      const phase = dStr <= DATA.oos_end_date ? 'OOS' : 'IS';
      let html = `<div class="font-semibold mb-1">${{dStr}} (${{phase}})</div>`;
      cfg.lines.forEach(l => {{
        const v = l.data[idx];
        const s = v >= 0 ? '+' : '';
        html += `<div class="flex items-center justify-between gap-3">
          <span style="color:${{l.color}}">● ${{l.name.split(' (')[0]}}</span>
          <span class="font-mono font-semibold">${{s}}R$ ${{Math.round(v).toLocaleString('pt-BR')}}</span>
        </div>`;
      }});
      tooltip.innerHTML = html;
      tooltip.classList.remove('hidden');
      const leftPos = Math.min(rect.width - 230, Math.max(65, e.clientX - rect.left + 12));
      tooltip.style.left = leftPos + 'px';
      tooltip.style.top = '18px';
    }});

    canvas.addEventListener('mouseleave', () => {{
      tooltip.classList.add('hidden');
      drawChart(null);
    }});

    window.addEventListener('resize', () => drawChart(null));
    drawChart(null);
  </script>
</body>
</html>
"""
    widget_path = os.path.join(ARTIFACT_DIR, "curvas_capital_2026.html")
    with open(widget_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("Saved PNG charts and HTML widget successfully!")


if __name__ == "__main__":
    main()

