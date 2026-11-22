"""Geração do relatório Markdown da Bateria de Validação e Inclusão dos 24 Robôs Não Utilizados."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _brl(v: float, signed: bool = False) -> str:
    sign = "+" if signed and v > 0 else ("-" if v < 0 else "")
    s = f"{abs(v):,.0f}".replace(",", ".")
    return f"{sign}R\\$ {s}"


def _delta(v: float, suffix: str = "") -> str:
    s = f"{v:+.2f}".replace(".", ",")
    return f"{s}{suffix}"


def _gate_str(gates: dict[str, bool]) -> str:
    tags = [
        ("IS", gates["G1_IS"]),
        ("OOS", gates["G2_OOS_BLIND"]),
        ("2Sem", gates["G3_BOTH_HALVES"]),
        ("Mes", gates["G4_MONTHLY"]),
        ("Str", gates["G5_COST_STRESS"]),
    ]
    return " ".join(f"{'✅' if ok else '❌'}{t}" for t, ok in tags)


def generate_markdown_report(payload: dict[str, Any], out_path: Path) -> Path:
    bat: list[dict[str, Any]] = payload["battery"]
    inc: dict[str, Any] = payload["inclusion"]

    n_aprov = sum(1 for r in bat if r["best_is"]["verdict"] == "APROVADO")
    n_res = sum(1 for r in bat if r["best_is"]["verdict"] == "RESERVA")
    n_rep = sum(1 for r in bat if r["best_is"]["verdict"] == "REPROVADO")
    n_base_aprov = sum(1 for r in bat if r["baseline"]["verdict"] == "APROVADO")

    lines: list[str] = [
        "# Bateria de Validação & Inclusão — 24 Robôs Não Utilizados (vs Top 8 da 2004051)",
        "",
        f"> **Período:** `2026-01-02` a `2026-11-06` (`{payload['total_days']}` pregões) · **Treino (IS):** `Jan–Jul` (`145d`) · **Validação Cega (OOS):** `Ago–Nov` (`67d`) · **Custos B3 reais:** `R\\$ 2/lote` WIN · `R\\$ 5/lote` WDO",
        "",
        "## 1. Resumo Executivo",
        "",
        f"- **Robôs analisados:** `24` não ativos na conta `2004051` (`11 WIN` + `13 WDO`).",
        f"- **Antes dos ajustes (Baseline atual do EA):** `{n_base_aprov}` aprovados nos 5 gates.",
        f"- **Após ajustes controlados (selecionados 100% no IS `Jan–Jul` e testados às cegas no OOS `Ago–Nov`):**",
        f"  - **`{n_aprov}` APROVADOS** (passam nos **5/5 gates**: Qualidade IS + OOS Cego + Ambos Semestres + `>=7/11` Meses + Stress `+50%` custo)",
        f"  - **`{n_res}` RESERVAS** (passam no OOS Cego e Stress `+50%`, com 3–4/5 gates)",
        f"  - **`{n_rep}` REPROVADOS** (não sustentam OOS cego ou stress de custo mesmo após ajustes)",
        "",
        "### Portfólio Base Atual (`2004051` — Top 8: `EST-04, 07, 13, 14, 15 + WDO-01, 05, 07`)",
        "",
        "| Regime de Stop | Retorno 2026 | Max DD | Ret/DD | Sharpe | IS Ret/DD | OOS Cego Ret/DD | Pior Dia | Dias Cortados |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for m_key, m_lbl in [
        ("no_stop", "Sem Stop"),
        ("stop_live_850", "Stop Atual (`G 850 + WIN 400 + WDO 550`)"),
        ("stop_indep_0", "Stop Indep (`WIN 400 + WDO 550`, `G=0`)"),
    ]:
        bm = inc["base_eval"][m_key]
        lines.append(
            f"| {m_lbl} | {_brl(bm['ret'], True)} | {_brl(bm['max_dd'])} | **{bm['ret_dd']:.2f}x** | "
            f"{bm['sharpe']:.2f} | {bm['is_chron']['ret_dd']:.2f}x | **{bm['oos_chron']['ret_dd']:.2f}x** | "
            f"{_brl(bm['worst_day'], True)} | {bm['stopped']} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 2. Resultado da Bateria nos 24 Robôs (Original vs Ajustado IS → OOS Cego)",
        "",
        "| Robô | Ativo | Veredito | Gates | Ajuste Escolhido (100% IS) | Base Ret/DD | Ajust. Ret/DD | Líq. 2026 | PF | Trades | OOS Cego (Ago–Nov) | Stress +50% PF | Platô IS |",
        "| :--- | :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    order_map = {"APROVADO": 0, "RESERVA": 1, "REPROVADO": 2}
    bat_sorted = sorted(
        bat,
        key=lambda r: (order_map[r["best_is"]["verdict"]], -r["best_is"]["gates_passed"], -r["best_is"]["full"]["ret_dd"]),
    )
    for r in bat_sorted:
        b = r["baseline"]
        o = r["best_is"]
        badge = {"APROVADO": "🟢 **APROVADO**", "RESERVA": "🟡 RESERVA", "REPROVADO": "🔴 REPROVADO"}[o["verdict"]]
        lines.append(
            f"| **{r['code']}** | {r['asset']} {r['tf']} | {badge} | {_gate_str(o['gates'])} | `{o['label']}` | "
            f"{b['full']['ret_dd']:.2f}x | **{o['full']['ret_dd']:.2f}x** | {_brl(o['full']['net'], True)} | "
            f"{o['full']['pf']:.2f} | {o['full']['trades']} | {_brl(o['oos']['net'], True)} (PF {o['oos']['pf']:.2f}) | "
            f"{o['stress']['pf']:.2f} | {r['plateau_pct']:.0f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## 3. Teste de Inclusão 1-a-1 no Portfólio Atual (`Top 8 + 1 Candidato`)",
        "",
        "Avaliado com o motor M1 intraday real (`G 850 + WIN 400 + WDO 550` e `Sem Stop`).",
        "",
        "| Candidato | Veredito | Ajuste | Corr. Top8 | Corr. Ativo | PnL Piores 15d | ΔRet (Stop Live) | ΔDD (Stop Live) | Ret/DD (Stop Live) | ΔOOS Ret/DD | Ret/DD (Sem Stop) |",
        "| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for m in inc["marginal"]:
        sl = m["stop_live_850"]
        ns = m["no_stop"]
        lines.append(
            f"| **{m['key']}** ({m['asset']}) | {m['verdict']} | `{m['label']}` | {m['corr_all']:+.2f} | {m['corr_asset']:+.2f} | "
            f"{_brl(m['pnl_on_top8_worst15'], True)} | {_brl(sl['d_ret'], True)} | {_brl(sl['d_dd'], True)} | "
            f"**{sl['ret_dd']:.2f}x** ({_delta(sl['d_ret_dd'], 'x')}) | {_delta(sl['d_oos_ret_dd'], 'x')} | "
            f"{ns['ret_dd']:.2f}x ({_delta(ns['d_ret_dd'], 'x')}) |"
        )

    lines += [
        "",
        "---",
        "",
        "## 4. Expansão Forward Stepwise (Guiada 100% no IS → Validada no OOS Cego)",
        "",
        "### 4.1 Apenas Candidatos `APROVADO` — Com Stop Atual (`G 850 + WIN 400 + WDO 550`)",
        "",
        "| Passo | Robôs | Adicionado | Ajuste | Retorno 2026 | Max DD | Ret/DD | Sharpe | IS Ret/DD | OOS Cego Ret/DD | OOS Cego Líq. | Dias Cortados |",
        "| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in inc["greedy_approved_stop"]:
        sl = s["stop_live_850"]
        lines.append(
            f"| {s['step']} | **{s['n_robots']}** | {s['added']} | `{s['added_label']}` | {_brl(sl['ret'], True)} | "
            f"{_brl(sl['max_dd'])} | **{sl['ret_dd']:.2f}x** | {sl['sharpe']:.2f} | {sl['is_chron']['ret_dd']:.2f}x | "
            f"**{sl['oos_chron']['ret_dd']:.2f}x** | {_brl(sl['oos_chron']['ret'], True)} | {sl['stopped']} |"
        )

    lines += [
        "",
        "### 4.2 Apenas Candidatos `APROVADO` — Sem Stop Diário",
        "",
        "| Passo | Robôs | Adicionado | Retorno 2026 | Max DD | Ret/DD | Sharpe | IS Ret/DD | OOS Cego Ret/DD | OOS Cego Líq. |",
        "| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in inc["greedy_approved_nostop"]:
        ns = s["no_stop"]
        lines.append(
            f"| {s['step']} | **{s['n_robots']}** | {s['added']} | {_brl(ns['ret'], True)} | "
            f"{_brl(ns['max_dd'])} | **{ns['ret_dd']:.2f}x** | {ns['sharpe']:.2f} | {ns['is_chron']['ret_dd']:.2f}x | "
            f"**{ns['oos_chron']['ret_dd']:.2f}x** | {_brl(ns['oos_chron']['ret'], True)} |"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
