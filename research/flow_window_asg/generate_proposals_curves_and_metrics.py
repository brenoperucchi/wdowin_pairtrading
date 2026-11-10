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

ALL_15 = [
    "EST-01", "EST-03", "EST-04", "EST-05", "EST-07",
    "EST-13", "EST-14", "EST-15", "EST-16",
    "WDO-01", "WDO-02", "WDO-05", "WDO-07", "WDO-09", "WDO-10"
]

PROPOSALS = {
    # 1. MT5
    "MT5_ATUAL_15": {
        "env": "MT5",
        "title": "MT5 Atual (15 Robôs)",
        "color": "#64748b",
        "ls": "--",
        "lw": 1.8,
        "items": [(s, "0_BASE_MT5") for s in ALL_15],
    },
    "MT5_PROP_A_14": {
        "env": "MT5",
        "title": "MT5 Proposta A (14 Robôs · Sem EST-16)",
        "color": "#60a5fa",
        "ls": "-.",
        "lw": 2.0,
        "items": [(s, "0_BASE_MT5") for s in ALL_15 if s != "EST-16"],
    },
    "MT5_PROP_B_11_OOS": {
        "env": "MT5",
        "title": "MT5 Proposta B ⭐ (11 Robôs · 8 WIN + 3 WDO OOS+)",
        "color": "#38bdf8",
        "ls": "-",
        "lw": 2.6,
        "items": [(s, "0_BASE_MT5") for s in [
            "EST-01", "EST-03", "EST-04", "EST-05", "EST-07", "EST-13", "EST-14", "EST-15",
            "WDO-01", "WDO-05", "WDO-07"
        ]],
    },
    "MT5_PROP_C_9_ELITE": {
        "env": "MT5",
        "title": "MT5 Proposta C (9 Robôs Elite · Ultra Baixo DD)",
        "color": "#22d3ee",
        "ls": "-",
        "lw": 2.2,
        "items": [(s, "0_BASE_MT5") for s in [
            "EST-03", "EST-04", "EST-05", "EST-13", "EST-14", "EST-15",
            "WDO-01", "WDO-05", "WDO-07"
        ]],
    },

    # 2. DASHBOARD 5174
    "D5174_ATUAL_TOP6": {
        "env": "5174",
        "title": "5174 Atual · Top 6 Sem Fluxo",
        "color": "#94a3b8",
        "ls": ":",
        "lw": 1.7,
        "items": [(s, "0_BASE_MT5") for s in ["EST-04", "EST-07", "EST-14", "WDO-02", "WDO-07", "WDO-10"]],
    },
    "D5174_ATUAL_11_FLOW": {
        "env": "5174",
        "title": "5174 Atual · 11 Estratégias c/ Fluxo",
        "color": "#cbd5e1",
        "ls": "--",
        "lw": 1.8,
        "items": [
            ("EST-01", "6_COMBO_SMART"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
            ("EST-13", "4_FLUXO_ABSORCAO"), ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "0_BASE_MT5"),
            ("EST-16", "2_JANELA_S_EXPLOSAO"), ("WDO-02", "0_BASE_MT5"), ("WDO-07", "0_BASE_MT5"),
            ("WDO-09", "1_JANELA_ASG"), ("WDO-10", "3_FLUXO_INST")
        ],
    },
    "D5174_PROP_A_TOP8_M5": {
        "env": "5174",
        "title": "5174 Proposta A ⭐ (Top 8 Elite M5 c/ Fluxo)",
        "color": "#f59e0b",
        "ls": "-",
        "lw": 2.6,
        "items": [
            ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
            ("EST-13", "4_FLUXO_ABSORCAO"), ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "4_FLUXO_ABSORCAO"),
            ("WDO-01", "3_FLUXO_INST"), ("WDO-05", "0_BASE_MT5"), ("WDO-07", "3_FLUXO_INST")
        ],
    },
    "D5174_PROP_B_14_HIBRIDA": {
        "env": "5174",
        "title": "5174 Proposta B 🏆 (14 Híbrida Completa s/ EST-16)",
        "color": "#a855f7",
        "ls": "-",
        "lw": 2.4,
        "items": [
            ("EST-01", "6_COMBO_SMART"), ("EST-03", "0_BASE_MT5"), ("EST-04", "4_FLUXO_ABSORCAO"),
            ("EST-05", "0_BASE_MT5"), ("EST-07", "4_FLUXO_ABSORCAO"), ("EST-13", "4_FLUXO_ABSORCAO"),
            ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-15", "4_FLUXO_ABSORCAO"),
            ("WDO-01", "3_FLUXO_INST"), ("WDO-02", "0_BASE_MT5"), ("WDO-05", "0_BASE_MT5"),
            ("WDO-07", "3_FLUXO_INST"), ("WDO-09", "0_BASE_MT5"), ("WDO-10", "4_FLUXO_ABSORCAO")
        ],
    },

    # 3. DASHBOARD 5176
    "D5176_ATUAL_WALLS6": {
        "env": "5176",
        "title": "5176 Atual · 6 Walls (WDO-07 s/ Filtro)",
        "color": "#f43f5e",
        "ls": "--",
        "lw": 1.8,
        "items": [
            ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
            ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "0_BASE_MT5"), ("WDO-10", "3_FLUXO_INST")
        ],
    },
    "D5176_PROP_A_WALLS6_STRICT": {
        "env": "5176",
        "title": "5176 Proposta A (6 Walls · WDO-07 c/ 3_FLUXO_INST)",
        "color": "#34d399",
        "ls": "-.",
        "lw": 2.1,
        "items": [
            ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
            ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "3_FLUXO_INST"), ("WDO-10", "3_FLUXO_INST")
        ],
    },
    "D5176_PROP_B_WALLS6_V2": {
        "env": "5176",
        "title": "5176 Proposta B ⭐ (6 Walls V2: WDO-01+07 · 11/11 M+)",
        "color": "#10b981",
        "ls": "-",
        "lw": 2.5,
        "items": [
            ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
            ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "3_FLUXO_INST"), ("WDO-01", "3_FLUXO_INST")
        ],
    },
    "D5176_PROP_C_WALLS7_V2": {
        "env": "5176",
        "title": "5176 Proposta C 🏆 (7 Walls V2: 4 WIN + 3 WDO · 11/11 M+)",
        "color": "#22c55e",
        "ls": "-",
        "lw": 2.7,
        "items": [
            ("EST-14", "4_FLUXO_ABSORCAO"), ("EST-04", "4_FLUXO_ABSORCAO"), ("EST-07", "4_FLUXO_ABSORCAO"),
            ("WIN-E2", "6_COMBO_SMART"), ("WDO-07", "3_FLUXO_INST"), ("WDO-01", "3_FLUXO_INST"),
            ("WDO-10", "4_FLUXO_ABSORCAO")
        ],
    },
}


def compute_period_metrics(sub_df: pd.DataFrame, days: list) -> dict:
    if sub_df.empty:
        return {}
    s_sorted = sub_df.sort_values(["date", "seq"]).reset_index(drop=True)
    pnls = s_sorted["pnl"].values.astype(float)
    pnls_nc = s_sorted["pnl_nocost"].values.astype(float)
    n = len(pnls)
    lots = int(s_sorted["lots"].sum())

    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    wr = 100.0 * len(wins) / n if n > 0 else 0.0
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = gw / gl if gl > 1e-6 else 99.9

    gw_nc = float(pnls_nc[pnls_nc > 0].sum())
    gl_nc = float(-pnls_nc[pnls_nc < 0].sum())
    pf_nc = gw_nc / gl_nc if gl_nc > 1e-6 else 99.9

    net = float(pnls.sum())
    net_nc = float(pnls_nc.sum())

    # Trade-by-trade DD
    cum_tr = np.cumsum(pnls)
    pk_tr = np.maximum.accumulate(np.insert(cum_tr, 0, 0.0))[1:]
    dd_trade = float(np.max(pk_tr - cum_tr)) if len(cum_tr) else 0.0
    ret_dd_trade = net / dd_trade if dd_trade > 1e-6 else 99.9

    # Daily DD
    d_ser = s_sorted.groupby("date")["pnl"].sum().reindex(days, fill_value=0.0)
    cum_d = d_ser.cumsum().values
    pk_d = np.maximum.accumulate(np.insert(cum_d, 0, 0.0))[1:]
    dd_day = float(np.max(pk_d - cum_d)) if len(cum_d) else 0.0
    ret_dd_day = net / dd_day if dd_day > 1e-6 else 99.9

    std_d = float(d_ser.std(ddof=1)) if len(d_ser) > 1 else 0.0
    sharpe = (float(d_ser.mean()) / std_d * np.sqrt(252.0)) if std_d > 1e-9 else 0.0
    worst_day = float(d_ser.min())

    return {
        "trades": n,
        "lots": lots,
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "pf_nc": round(pf_nc, 2),
        "net": round(net, 0),
        "net_nc": round(net_nc, 0),
        "dd_day": round(dd_day, 0),
        "dd_trade": round(dd_trade, 0),
        "ret_dd_day": round(ret_dd_day, 2),
        "ret_dd_trade": round(ret_dd_trade, 2),
        "sharpe": round(sharpe, 2),
        "worst_day": round(worst_day, 0),
    }


def main():
    df = pd.read_csv(os.path.join(REPORT_DIR, "trades_16_strategies_all_filters_2026.csv"))
    df["date"] = df["date"].astype(str)
    all_days = sorted(df["date"].unique())
    oos_days = [d for d in all_days if d <= OOS_END]
    is_days = [d for d in all_days if d >= IS_START]
    months = sorted(list({d[:7] for d in all_days}))

    dt_all = pd.to_datetime(all_days)
    dt_oos = pd.to_datetime(oos_days)
    split_dt = pd.to_datetime(OOS_END)

    summary_rows = []
    curves = {}

    for key, spec in PROPOSALS.items():
        parts = [df[(df["strat"] == s) & (df["filter"] == f)] for s, f in spec["items"]]
        cat = pd.concat(parts, ignore_index=True)

        d_all = cat.groupby("date")["pnl"].sum().reindex(all_days, fill_value=0.0).values.astype(float)
        eq_all = np.round(np.cumsum(d_all), 1)
        pk_all = np.maximum.accumulate(np.insert(eq_all, 0, 0.0))[1:]
        dd_all = np.round(eq_all - pk_all, 1)

        d_oos = d_all[:len(oos_days)]
        eq_oos = np.round(np.cumsum(d_oos), 1)
        pk_oos = np.maximum.accumulate(np.insert(eq_oos, 0, 0.0))[1:]
        dd_oos = np.round(eq_oos - pk_oos, 1)

        m_oos = compute_period_metrics(cat[cat["date"].isin(oos_days)], oos_days)
        m_is = compute_period_metrics(cat[cat["date"].isin(is_days)], is_days)
        m_tot = compute_period_metrics(cat, all_days)

        cat["m"] = cat["date"].str.slice(0, 7)
        m_ser = cat.groupby("m")["pnl"].sum().reindex(months, fill_value=0.0)
        pos_m = int((m_ser > 0).sum())

        curves[key] = {
            **spec,
            "eq": eq_all,
            "dd": dd_all,
            "eq_oos": eq_oos,
            "dd_oos": dd_oos,
            "oos": m_oos,
            "is": m_is,
            "tot": m_tot,
            "pos_months": pos_m,
            "total_months": len(months),
            "monthly": {m: round(float(m_ser[m]), 0) for m in months},
        }

        summary_rows.append({
            "key": key,
            "env": spec["env"],
            "title": spec["title"],
            "oos_tr": m_oos["trades"],
            "oos_pf": m_oos["pf"],
            "oos_net": m_oos["net"],
            "oos_dd_day": m_oos["dd_day"],
            "oos_dd_tr": m_oos["dd_trade"],
            "oos_ret_dd_day": m_oos["ret_dd_day"],
            "oos_ret_dd_tr": m_oos["ret_dd_trade"],
            "oos_sharpe": m_oos["sharpe"],
            "is_pf": m_is["pf"],
            "is_net": m_is["net"],
            "is_dd_day": m_is["dd_day"],
            "is_ret_dd_day": m_is["ret_dd_day"],
            "is_sharpe": m_is["sharpe"],
            "tot_tr": m_tot["trades"],
            "tot_wr": m_tot["wr"],
            "tot_pf": m_tot["pf"],
            "tot_pf_nc": m_tot["pf_nc"],
            "tot_net": m_tot["net"],
            "tot_dd_day": m_tot["dd_day"],
            "tot_dd_tr": m_tot["dd_trade"],
            "tot_ret_dd_day": m_tot["ret_dd_day"],
            "tot_ret_dd_tr": m_tot["ret_dd_trade"],
            "tot_sharpe": m_tot["sharpe"],
            "worst_day": m_tot["worst_day"],
            "pos_months": f"{pos_m}/{len(months)}",
        })

    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(os.path.join(REPORT_DIR, "proposals_mt5_5174_5176_summary_2026.csv"), index=False)

    # =========================================================================
    # MULTI-PANEL PNG CHART: 3 Ambientes (MT5, 5174, 5176) + Underwater DD
    # =========================================================================
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(19, 14), dpi=140, facecolor="#0b0f19")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.05, 1.0], hspace=0.30, wspace=0.16)

    panels = [
        (gs[0, 0], "MT5", "1. METATRADER 5 (100% Automatizado s/ Fluxo) — ATUAL vs SUGESTÕES", "#38bdf8"),
        (gs[0, 1], "5174", "2. DASHBOARD 5174 (Híbrido MT5 + Fluxo) — ATUAL vs SUGESTÕES", "#f59e0b"),
        (gs[1, 0], "5176", "3. DASHBOARD 5176 (Fluxo nas Walls) — ATUAL vs SUGESTÕES (11/11 Meses +)", "#10b981"),
    ]

    for subplot_spec, env_code, title, title_col in panels:
        ax = fig.add_subplot(subplot_spec)
        ax.set_facecolor("#111827")
        ax.axvspan(dt_all[0], split_dt, color="#1e293b", alpha=0.45)
        ax.axvline(split_dt, color="#fbbf24", linestyle="--", linewidth=1.4, alpha=0.9)
        ax.axhline(0, color="#475569", linewidth=0.9)

        for k, c in curves.items():
            if c["env"] != env_code:
                continue
            o = c["oos"]
            t = c["tot"]
            lbl = (
                f"{c['title']}\n"
                f"   OOS: R$ {o['net']:+,.0f} (DD {o['dd_day']:,.0f} | Ret/DD {o['ret_dd_day']:.2f}x)  •  "
                f"2026: R$ {t['net']:+,.0f} (DD {t['dd_day']:,.0f} | Ret/DD {t['ret_dd_day']:.2f}x | Sh {t['sharpe']:.2f})"
            )
            ax.plot(dt_all, c["eq"], linestyle=c["ls"], linewidth=c["lw"], color=c["color"], label=lbl)

        ax.set_title(title, fontsize=11, fontweight="bold", color=title_col, pad=8)
        ax.set_ylabel("Lucro Líquido Acumulado (R$)", fontsize=9.5, color="#cbd5e1")
        ax.grid(True, linestyle=":", alpha=0.25, color="#64748b")
        ax.legend(loc="upper left", fontsize=7.6, framealpha=0.88, facecolor="#0f172a", edgecolor="#334155")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    # Panel 4: Comparativo Direto das 3 Campeãs (MT5 Prop B vs 5174 Prop A/B vs 5176 Prop C) + Drawdown
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#111827")
    ax4.axvspan(dt_all[0], split_dt, color="#1e293b", alpha=0.45, label="OOS (02/01 a 06/05 — 84 pregões)")
    ax4.axvline(split_dt, color="#fbbf24", linestyle="--", linewidth=1.4, label="Divisão OOS / IS (06/05/2026)")
    ax4.axhline(0, color="#475569", linewidth=0.9)

    champ_keys = ["MT5_PROP_B_11_OOS", "MT5_PROP_C_9_ELITE", "D5174_PROP_B_14_HIBRIDA", "D5174_PROP_A_TOP8_M5", "D5176_PROP_C_WALLS7_V2"]
    for k in champ_keys:
        c = curves[k]
        o = c["oos"]
        t = c["tot"]
        lbl = (
            f"{c['title']} [{c['pos_months']} m+]\n"
            f"   OOS Ret/DD: {o['ret_dd_day']:.2f}x (R$ {o['net']:+,.0f} / DD {o['dd_day']:,.0f}) | "
            f"2026 Ret/DD: {t['ret_dd_day']:.2f}x (R$ {t['net']:+,.0f} / DD {t['dd_day']:,.0f})"
        )
        ax4.plot(dt_all, c["eq"], linestyle=c["ls"], linewidth=c["lw"], color=c["color"], label=lbl)

    ax4.set_title("4. COMPARATIVO FINAL DAS PROPOSTAS CAMPEÃS (MT5 vs 5174 vs 5176)", fontsize=11, fontweight="bold", color="#f8fafc", pad=8)
    ax4.set_ylabel("Lucro Líquido Acumulado (R$)", fontsize=9.5, color="#cbd5e1")
    ax4.grid(True, linestyle=":", alpha=0.25, color="#64748b")
    ax4.legend(loc="upper left", fontsize=7.5, framealpha=0.88, facecolor="#0f172a", edgecolor="#334155")
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    fig.suptitle(
        "CURVAS DE CAPITAL E MÉTRICAS DE RET/DD — ATUAL vs SUGESTÕES OTIMIZADAS (212 PREGÕES DE 2026: OOS + IS)",
        fontsize=14, fontweight="bold", color="#f8fafc", y=0.98
    )

    out_png = os.path.join(IMG_DIR, "equity_propostas_mt5_5174_5176_2026.png")
    fig.savefig(out_png, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    shutil.copy2(out_png, os.path.join(ARTIFACT_DIR, "equity_propostas_mt5_5174_5176_2026.png"))

    # =========================================================================
    # INTERACTIVE HTML WIDGET (Generative UI) in ARTIFACT_DIR
    # =========================================================================
    js_payload = {
        "dates": all_days,
        "oos_end_idx": len(oos_days) - 1,
        "oos_end_date": OOS_END,
        "curves": {
            k: {
                "env": v["env"],
                "title": v["title"],
                "color": v["color"],
                "dash": [5, 4] if v["ls"] == "--" else ([2, 3] if v["ls"] == ":" else ([6, 3, 2, 3] if v["ls"] == "-." else [])),
                "eq": v["eq"].tolist(),
                "dd": v["dd"].tolist(),
                "eq_oos": v["eq_oos"].tolist(),
                "oos": v["oos"],
                "is": v["is"],
                "tot": v["tot"],
                "pos_months": v["pos_months"],
            }
            for k, v in curves.items()
        }
    }

    html_widget = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-2">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-3.5 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-2.5">
      <div>
        <h2 class="text-[var(--foreground)] font-semibold text-sm">Curvas de Capital & Ret/DD — Atual vs. Sugestões (MT5 · 5174 · 5176)</h2>
        <p class="text-[var(--muted-foreground)] text-xs">Clique nas abas para comparar Antes vs. Depois em cada ambiente ou dar Zoom no OOS (Jan–Mai)</p>
      </div>
      <div class="flex flex-wrap items-center gap-1">
        <button onclick="setTab('champs')" id="tab-champs" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--primary)] text-[var(--primary-foreground)]">🏆 Campeãs</button>
        <button onclick="setTab('mt5')" id="tab-mt5" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">1. MT5</button>
        <button onclick="setTab('5174')" id="tab-5174" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">2. Dash 5174</button>
        <button onclick="setTab('5176')" id="tab-5176" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">3. Dash 5176</button>
        <button onclick="setTab('oos')" id="tab-oos" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">🔍 Zoom OOS</button>
        <button onclick="setTab('dd')" id="tab-dd" class="px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]">📉 Drawdown</button>
      </div>
    </div>

    <div class="relative w-full" style="height: 255px;">
      <canvas id="propCanvas" class="w-full h-full cursor-crosshair"></canvas>
      <div id="propTooltip" class="hidden absolute pointer-events-none bg-[var(--background)] border border-[var(--border)] rounded-lg px-2.5 py-1.5 text-xs shadow-md z-10"></div>
    </div>

    <div id="kpiTable" class="mt-2 pt-2 border-t border-[var(--border)] overflow-x-auto"></div>
  </div>

  <script>
    const D = {json.dumps(js_payload)};
    let activeTab = 'champs';
    const canvas = document.getElementById('propCanvas');
    const ctx = canvas.getContext('2d');
    const tooltip = document.getElementById('propTooltip');
    const kpiTable = document.getElementById('kpiTable');

    const TAB_KEYS = {{
      'champs': ['MT5_PROP_B_11_OOS', 'D5174_PROP_B_14_HIBRIDA', 'D5174_PROP_A_TOP8_M5', 'D5176_PROP_C_WALLS7_V2', 'D5176_PROP_B_WALLS6_V2'],
      'mt5': ['MT5_ATUAL_15', 'MT5_PROP_A_14', 'MT5_PROP_B_11_OOS', 'MT5_PROP_C_9_ELITE'],
      '5174': ['D5174_ATUAL_TOP6', 'D5174_ATUAL_11_FLOW', 'D5174_PROP_A_TOP8_M5', 'D5174_PROP_B_14_HIBRIDA'],
      '5176': ['D5176_ATUAL_WALLS6', 'D5176_PROP_A_WALLS6_STRICT', 'D5176_PROP_B_WALLS6_V2', 'D5176_PROP_C_WALLS7_V2'],
      'oos': ['MT5_ATUAL_15', 'MT5_PROP_B_11_OOS', 'D5174_ATUAL_11_FLOW', 'D5174_PROP_A_TOP8_M5', 'D5176_ATUAL_WALLS6', 'D5176_PROP_C_WALLS7_V2'],
      'dd': ['MT5_ATUAL_15', 'MT5_PROP_B_11_OOS', 'D5174_PROP_A_TOP8_M5', 'D5176_ATUAL_WALLS6', 'D5176_PROP_C_WALLS7_V2']
    }};

    function setTab(t) {{
      activeTab = t;
      ['champs', 'mt5', '5174', '5176', 'oos', 'dd'].forEach(k => {{
        const btn = document.getElementById('tab-' + k);
        if (k === t) {{
          btn.className = 'px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--primary)] text-[var(--primary-foreground)]';
        }} else {{
          btn.className = 'px-2.5 py-1 rounded text-xs font-medium border border-[var(--border)] bg-[var(--secondary)] text-[var(--secondary-foreground)]';
        }}
      }});
      render();
    }}

    function render(hoverIdx = null) {{
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);

      const W = rect.width, H = rect.height;
      const padL = 62, padR = 14, padT = 12, padB = 22;
      const plotW = W - padL - padR, plotH = H - padT - padB;

      const keys = TAB_KEYS[activeTab];
      const isOOS = (activeTab === 'oos');
      const isDD = (activeTab === 'dd');
      const dates = isOOS ? D.dates.slice(0, D.oos_end_idx + 1) : D.dates;
      const N = dates.length;

      const series = keys.map(k => {{
        const c = D.curves[k];
        return {{
          key: k,
          title: c.title,
          color: c.color,
          dash: c.dash,
          data: isOOS ? c.eq_oos : (isDD ? c.dd : c.eq),
          oos: c.oos,
          is: c.is,
          tot: c.tot,
          pos_months: c.pos_months
        }};
      }});

      let minV = 0, maxV = 0;
      series.forEach(s => s.data.forEach(v => {{
        if (v < minV) minV = v;
        if (v > maxV) maxV = v;
      }}));
      const span = Math.max(maxV - minV, 500);
      minV -= span * 0.06;
      maxV += span * 0.06;

      const xOf = i => padL + (i / Math.max(1, N - 1)) * plotW;
      const yOf = v => padT + (1 - (v - minV) / (maxV - minV)) * plotH;

      ctx.clearRect(0, 0, W, H);

      if (!isOOS) {{
        const splitX = xOf(D.oos_end_idx);
        ctx.fillStyle = 'rgba(148, 163, 184, 0.08)';
        ctx.fillRect(padL, padT, splitX - padL, plotH);
        ctx.save();
        ctx.strokeStyle = '#fbbf24';
        ctx.lineWidth = 1.3;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(splitX, padT);
        ctx.lineTo(splitX, padT + plotH);
        ctx.stroke();
        ctx.fillStyle = '#fbbf24';
        ctx.font = '12px sans-serif';
        ctx.fillText('← OOS | IS →', splitX - 36, padT + 13);
        ctx.restore();
      }}

      ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)';
      ctx.lineWidth = 1;
      ctx.font = '12px sans-serif';
      ctx.fillStyle = 'rgba(148, 163, 184, 0.85)';
      for (let s = 0; s <= 4; s++) {{
        const val = minV + (s / 4) * (maxV - minV);
        const y = yOf(val);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(W - padR, y);
        ctx.stroke();
        ctx.fillText('R$ ' + Math.round(val).toLocaleString('pt-BR'), 4, y + 4);
      }}

      if (minV < 0 && maxV > 0) {{
        const y0 = yOf(0);
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.5)';
        ctx.beginPath();
        ctx.moveTo(padL, y0);
        ctx.lineTo(W - padR, y0);
        ctx.stroke();
      }}

      for (let t = 0; t <= 6; t++) {{
        const idx = Math.round((t / 6) * (N - 1));
        const x = xOf(idx);
        const dStr = dates[idx].slice(8, 10) + '/' + dates[idx].slice(5, 7);
        ctx.fillText(dStr, x - 16, H - 5);
      }}

      series.forEach(s => {{
        ctx.save();
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.dash.length ? 1.8 : 2.4;
        ctx.setLineDash(s.dash);
        ctx.beginPath();
        for (let i = 0; i < N; i++) {{
          const x = xOf(i), y = yOf(s.data[i]);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }}
        ctx.stroke();
        ctx.restore();
      }});

      if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < N) {{
        const hx = xOf(hoverIdx);
        ctx.save();
        ctx.strokeStyle = 'rgba(226, 232, 240, 0.5)';
        ctx.beginPath();
        ctx.moveTo(hx, padT);
        ctx.lineTo(hx, padT + plotH);
        ctx.stroke();
        series.forEach(s => {{
          const hy = yOf(s.data[hoverIdx]);
          ctx.fillStyle = s.color;
          ctx.beginPath();
          ctx.arc(hx, hy, 3.5, 0, Math.PI * 2);
          ctx.fill();
        }});
        ctx.restore();
      }}

      // Render compact KPI summary table for active curves
      let rowsHtml = series.map(s => {{
        const o = s.oos, t = s.tot;
        const oSign = o.net >= 0 ? '+' : '';
        const tSign = t.net >= 0 ? '+' : '';
        return `<tr class="border-t border-[var(--border)]">
          <td class="py-1 pr-2 font-medium flex items-center gap-1.5">
            <span class="inline-block w-2.5 h-2.5 rounded-sm" style="background:${{s.color}}"></span>
            <span>${{s.title}}</span>
          </td>
          <td class="py-1 px-2 text-right font-mono">${{oSign}}R$ ${{o.net.toLocaleString('pt-BR')}}</td>
          <td class="py-1 px-2 text-right font-mono">R$ ${{o.dd_day.toLocaleString('pt-BR')}}</td>
          <td class="py-1 px-2 text-right font-mono font-semibold">${{o.ret_dd_day.toFixed(2)}}x</td>
          <td class="py-1 px-2 text-right font-mono">${{tSign}}R$ ${{t.net.toLocaleString('pt-BR')}}</td>
          <td class="py-1 px-2 text-right font-mono">R$ ${{t.dd_day.toLocaleString('pt-BR')}}</td>
          <td class="py-1 px-2 text-right font-mono font-bold text-[var(--primary)]">${{t.ret_dd_day.toFixed(2)}}x</td>
          <td class="py-1 px-2 text-right font-mono">${{t.pf.toFixed(2)}}</td>
          <td class="py-1 pl-2 text-right font-mono">${{s.pos_months}}/11</td>
        </tr>`;
      }}).join('');

      kpiTable.innerHTML = `<table class="w-full text-xs">
        <thead>
          <tr class="text-[var(--muted-foreground)]">
            <th class="text-left pb-1">Configuração</th>
            <th class="text-right pb-1 px-2">OOS Net</th>
            <th class="text-right pb-1 px-2">OOS DD</th>
            <th class="text-right pb-1 px-2">OOS Ret/DD</th>
            <th class="text-right pb-1 px-2">2026 Net</th>
            <th class="text-right pb-1 px-2">2026 DD</th>
            <th class="text-right pb-1 px-2">2026 Ret/DD</th>
            <th class="text-right pb-1 px-2">PF 2026</th>
            <th class="text-right pb-1 pl-2">Meses+</th>
          </tr>
        </thead>
        <tbody>${{rowsHtml}}</tbody>
      </table>`;
    }}

    canvas.addEventListener('mousemove', e => {{
      const rect = canvas.getBoundingClientRect();
      const padL = 62, padR = 14;
      const plotW = rect.width - padL - padR;
      const isOOS = (activeTab === 'oos');
      const dates = isOOS ? D.dates.slice(0, D.oos_end_idx + 1) : D.dates;
      const N = dates.length;
      const idx = Math.max(0, Math.min(N - 1, Math.round(((e.clientX - rect.left - padL) / plotW) * (N - 1))));
      render(idx);

      const dStr = dates[idx];
      const phase = dStr <= D.oos_end_date ? 'OOS' : 'IS';
      const keys = TAB_KEYS[activeTab];
      const isDD = (activeTab === 'dd');
      let html = `<div class="font-semibold mb-1">${{dStr}} (${{phase}})</div>`;
      keys.forEach(k => {{
        const c = D.curves[k];
        const arr = isOOS ? c.eq_oos : (isDD ? c.dd : c.eq);
        const v = arr[idx];
        const s = v >= 0 ? '+' : '';
        html += `<div class="flex items-center justify-between gap-3">
          <span style="color:${{c.color}}">● ${{c.title}}</span>
          <span class="font-mono font-semibold">${{s}}R$ ${{Math.round(v).toLocaleString('pt-BR')}}</span>
        </div>`;
      }});
      tooltip.innerHTML = html;
      tooltip.classList.remove('hidden');
      tooltip.style.left = Math.min(rect.width - 260, Math.max(65, e.clientX - rect.left + 12)) + 'px';
      tooltip.style.top = '12px';
    }});

    canvas.addEventListener('mouseleave', () => {{
      tooltip.classList.add('hidden');
      render(null);
    }});

    window.addEventListener('resize', () => render(null));
    render(null);
  </script>
</body>
</html>
"""
    widget_path = os.path.join(ARTIFACT_DIR, "curvas_sugestoes_mt5_5174_5176.html")
    with open(widget_path, "w", encoding="utf-8") as f:
        f.write(html_widget)

    print(df_sum.to_string(index=False))


if __name__ == "__main__":
    main()

