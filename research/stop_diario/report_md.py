"""Gerador de relatório Markdown (`docs/STOP_DIARIO_11_ROBOS.md`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _brl(v: float, dec: int = 0) -> str:
    sign = "-" if v < -1e-6 else ("+" if v > 1e-6 else "")
    s = f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}R\\$ {s}"


def _brl_abs(v: float, dec: int = 0) -> str:
    s = f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R\\$ {s}"


def _int_pt(v: int) -> str:
    return f"{int(v):,}".replace(",", ".")


def _pct(v: float, dec: int = 1) -> str:
    return f"{v:.{dec}f}%".replace(".", ",")


def _num(v: float, dec: int = 2) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def generate_markdown_report(results_by_preset: dict[str, dict[str, Any]], out_path: str | Path) -> Path:
    """Gera documentação completa em Markdown comparando todas as carteiras e cenários."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    primary = results_by_preset.get("proposta_b_11") or next(iter(results_by_preset.values()))
    lines: list[str] = []

    lines.append("# Sistema de Simulação e Gerência de Stop Diário Máximo — 11 Robôs Jumba")
    lines.append("")
    lines.append(f"- **Carteira Padrão:** {primary['label']} ({primary['subtitle']})")
    lines.append(
        f"- **Base Auditada:** Deals reais do MT5 Strategy Tester (`OHLC 1-Min`, `data/reports/mt5_tester_ohlc_2026/*_P1.htm`) "
        f"+ séries M1 reais de WIN e WDO ({primary['period_start']} a {primary['period_end']}, **{primary['total_days']} pregões**)."
    )
    lines.append(
        f"- **Divisão OOS / IS:** **OOS cego** (`02/01`–`06/05/2026`, {primary['oos_days']} pregões) · "
        f"**IS** (`07/05`–`06/11/2026`, {primary['is_days']} pregões)."
    )
    lines.append("- **Custos B3 embutidos:** WIN `R\\$ 2,00/contrato` (`-R\\$ 1,00/lote` adicional sobre o spread MT5) · WDO `R\\$ 5,00/contrato`.")
    lines.append("- **Motor Live MT5:** `Jumba_Portfolio_Live_Monitor.mq5` (v4.00) + `Jumba_SafetyGuard.mqh` + `Jumba_GEX_NWE_Core.mqh` + `Jumba_WDO_GEX_NWE_Core.mqh`.")
    lines.append("")

    # 1. Resumo Comparativo dos 3 Presets
    lines.append("## 1. Resumo Executivo das Carteiras")
    lines.append("")
    lines.append("| Carteira | Robôs | Trades | Sem Stop (Lucro / DD / Ret/DD) | Stop Ret/DD Ótimo | Resultado c/ Stop Ret/DD | Stop Max Lucro | Combo (Global / WIN / WDO) |")
    lines.append("| :--- | :---: | :---: | :--- | :---: | :--- | :---: | :--- |")
    for pid, res in results_by_preset.items():
        b = res["baseline"]
        f1 = res["final_ret_dd"]
        f2 = res["final_profit"]
        fc = res["final_combo"]
        rs = res["robust_stops"]
        cb = rs.get("combo_best_ret_dd") or {}
        stop_lbl = _brl_abs(rs["global_ret_dd"]) if rs["global_ret_dd"] > 0 else f"N/Rec (Cauda {_brl_abs(rs['global_tail_guard'])})"
        prof_lbl = _brl_abs(rs["global_profit"]) if rs["global_profit"] > 0 else "—"
        cb_lbl = (
            f"G {_brl_abs(cb.get('stop_global', 0))} / W {_brl_abs(cb.get('stop_win', 0))} / D {_brl_abs(cb.get('stop_wdo', 0))} "
            f"→ {_brl(fc['ret'])} (DD {_brl_abs(fc['max_dd'])}, **{_num(fc['ret_dd'])}x**)"
        )
        lines.append(
            f"| **{res['label']}** | {res['portfolio']['total_robots']} | {_int_pt(res['portfolio']['total_trades'])} | "
            f"{_brl(b['ret'])} / {_brl_abs(b['max_dd'])} / **{_num(b['ret_dd'])}x** | {stop_lbl} | "
            f"{_brl(f1['ret'])} / {_brl_abs(f1['max_dd'])} / **{_num(f1['ret_dd'])}x** ({f1['stopped']}d) | "
            f"{prof_lbl} ({_num(f2['ret_dd'])}x) | {cb_lbl} |"
        )
    lines.append("")

    # 2. Detalhamento por Carteira
    for pid, res in results_by_preset.items():
        b = res["baseline"]
        f1 = res["final_ret_dd"]
        f2 = res["final_profit"]
        fc = res["final_combo"]
        rs = res["robust_stops"]
        cb = rs.get("combo_best_ret_dd") or {}
        mae_g = res["portfolio"]["mae_daily_m1"]
        mae_c = res["portfolio"]["mae_daily_closed"]
        mae_w = res["portfolio"]["mae_win_m1"]
        mae_d = res["portfolio"]["mae_wdo_m1"]

        lines.append(f"---")
        lines.append("")
        lines.append(f"## 2. Análise Detalhada — {res['label']}")
        lines.append("")
        lines.append(f"> {res['subtitle']}")
        lines.append("")

        if not res["stop_recommended"]:
            lines.append(
                f"> **Nota Metodológica:** Nenhum stop diário único superou o Ret/DD do baseline ({_num(b['ret_dd'])}x) "
                f"acima do piso de 80% do MAE médio. O valor `{_brl(rs['primary_used'])}` exibido abaixo representa a "
                f"**proteção de cauda** (redução de pior dia preservando ≥92% do lucro)."
            )
            lines.append("")

        lines.append("### 2.1. Perfil de Excursão Adversa Diária (MAE M1 vs Trades Fechados)")
        lines.append("")
        lines.append("| Escopo | MAE Médio | σ | P50 | P75 | P90 | P95 | MAE Máximo |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        lines.append(f"| **Global Intraday (M1)** | {_brl_abs(mae_g['mean'])} | {_brl_abs(mae_g['std'])} | {_brl_abs(mae_g['p50'])} | {_brl_abs(mae_g['p75'])} | {_brl_abs(mae_g['p90'])} | {_brl_abs(mae_g['p95'])} | {_brl_abs(mae_g['max'])} |")
        lines.append(f"| **Global Fechado (Trades)** | {_brl_abs(mae_c['mean'])} | — | — | {_brl_abs(mae_c['p75'])} | {_brl_abs(mae_c['p90'])} | — | {_brl_abs(mae_c['max'])} |")
        lines.append(f"| **WIN Isolado (M1)** | {_brl_abs(mae_w['mean'])} | — | — | {_brl_abs(mae_w['p75'])} | {_brl_abs(mae_w['p90'])} | — | {_brl_abs(mae_w['max'])} |")
        lines.append(f"| **WDO Isolado (M1)** | {_brl_abs(mae_d['mean'])} | — | — | {_brl_abs(mae_d['p75'])} | {_brl_abs(mae_d['p90'])} | — | {_brl_abs(mae_d['max'])} |")
        lines.append("")

        lines.append("### 2.2. Comparativo Baseline vs Stops (Total 2026 · OOS · IS)")
        lines.append("")
        lines.append("| Cenário | Config Stop | Lucro Total | Max DD Diário | Max DD M1 Intra | Ret/DD | Sharpe | Pior Dia | Dias Parados | OOS (Jan-Mai) | IS (Mai-Nov) |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for title, cfg_lbl, sim in [
            ("Sem Stop (Baseline)", "—", b),
            ("Stop Global Ret/DD ★", _brl_abs(rs["primary_used"]), f1),
            ("Stop Global Máx Lucro 💰", _brl_abs(rs["global_profit"] or rs["primary_used"]), f2),
            (
                "Combo Multi-Escopo ⚡",
                f"G {_brl_abs(cb.get('stop_global', 0))} · W {_brl_abs(cb.get('stop_win', 0))} · D {_brl_abs(cb.get('stop_wdo', 0))}",
                fc,
            ),
        ]:
            lines.append(
                f"| **{title}** | {cfg_lbl} | {_brl(sim['ret'])} | {_brl_abs(sim['max_dd'])} | {_brl_abs(sim['max_dd_intraday'])} | "
                f"**{_num(sim['ret_dd'])}x** | {_num(sim['sharpe'])} | {_brl(sim['worst_day'])} | "
                f"{sim['stopped']}d ({_pct(sim['stopped_pct'])}) | "
                f"{_brl(sim['oos']['ret'])} ({_num(sim['oos']['ret_dd'])}x) | "
                f"{_brl(sim['is']['ret'])} ({_num(sim['is']['ret_dd'])}x) |"
            )
        lines.append("")

        # WFA e MC
        wfa = res["walk_forward"]
        pos_f = sum(1 for f in wfa["folds"] if f["improvement"] > 0)
        mc_i = res["monte_carlo"]["iid"]
        mc_b = res["monte_carlo"]["block_5d"]
        lines.append("### 2.3. Robustez Estatística (Walk-Forward & Monte Carlo)")
        lines.append("")
        lines.append(
            f"- **Walk-Forward Rolling ({wfa['train_window']}d treino → {wfa['test_window']}d teste):** "
            f"{pos_f}/{len(wfa['folds'])} folds melhoraram Ret/DD OOS · Stop Mediano = **{_brl_abs(wfa['robust_stop_ret_dd'])}**."
        )
        for sp in wfa["canonical_splits"]:
            lines.append(
                f"- **{sp['label']}:** Stop calibrado `{_brl_abs(sp['stop_calibrated'])}` → "
                f"Base {_brl(sp['base_ret'])} ({_num(sp['base_ret_dd'])}x) vs Stop {_brl(sp['stop_ret'])} ({_num(sp['stop_ret_dd'])}x, {sp['stopped']}d)."
            )
        lines.append(
            f"- **Monte Carlo IID (2.000 sims, stop {_brl_abs(rs['primary_used'])}):** "
            f"Vence em Ret/DD **{_pct(mc_i['wins_rdd'] / mc_i['n'] * 100)}** · Reduz MaxDD **{_pct(mc_i['wins_dd'] / mc_i['n'] * 100)}** · "
            f"MaxDD P95 {_brl_abs(mc_i['p95_dd_no'])} → **{_brl_abs(mc_i['p95_dd_stop'])}**."
        )
        lines.append(
            f"- **Monte Carlo Block Bootstrap 5d (2.000 sims):** "
            f"Vence em Ret/DD **{_pct(mc_b['wins_rdd'] / mc_b['n'] * 100)}** · Reduz MaxDD **{_pct(mc_b['wins_dd'] / mc_b['n'] * 100)}** · "
            f"MaxDD P95 {_brl_abs(mc_b['p95_dd_no'])} → **{_brl_abs(mc_b['p95_dd_stop'])}**."
        )
        lines.append("")

        # Tabela por Robô
        lines.append("### 2.4. Análise Individual por Robô (MAE/MFE Real M1)")
        lines.append("")
        lines.append("| Robô | Ativo | TF | Magic | Trades | Lucro Líq. | WR% | PF | Payoff | MAE P90 | MFE Méd | Eff% | Stop/Trade Sug. | Pior Dia | Stop/Dia Sug. | % Piores 15d |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for rb in res["robots"]:
            lines.append(
                f"| **{rb['id']}** | {rb['asset']} | {rb['tf']} | `{rb['magic']}` | {rb['total_trades']} | "
                f"{_brl(rb['total_profit'])} | {_pct(rb['win_rate'])} | {_num(rb['pf'])} | {_num(rb['payoff'])} | "
                f"{_brl_abs(rb['mae']['p90'])} | {_brl_abs(rb['mfe']['mean'])} | {_pct(rb['mfe_eff'])} | "
                f"{_brl_abs(rb['optimal_trade_stop'])} | {_brl(rb['daily']['worst'])} | {_brl_abs(rb['suggested_daily_stop'])} | "
                f"{_pct(rb['worst_15_share_pct'])} |"
            )
        lines.append("")

    # 3. Guia de Integração MT5
    rs0 = primary["robust_stops"]
    cb0 = rs0.get("combo_best_ret_dd") or {}
    lines.append("---")
    lines.append("")
    lines.append("## 3. Integração no MT5 (`Jumba_Portfolio_Live_Monitor` v4.00)")
    lines.append("")
    lines.append("O gerenciador em tempo real roda dentro do próprio gráfico do **`Jumba_Portfolio_Live_Monitor.mq5`** (timer de **1 segundo** + `OnTradeTransaction`), somando o P&L fechado do dia + flutuante em aberto e gravando as travas baseadas em data (`YYYYMMDD`) nas GlobalVariables do terminal:")
    lines.append("")
    lines.append("- `JUMBA_DAILY_STOP_GLOBAL`: trava todos os robôs `WIN` (`88000..88016`) e `WDO` (`89000..89016`).")
    lines.append("- `JUMBA_DAILY_STOP_WIN`: trava apenas os robôs `WIN` mantendo o `WDO` operando normalmente.")
    lines.append("- `JUMBA_DAILY_STOP_WDO`: trava apenas os robôs `WDO` mantendo o `WIN` operando normalmente.")
    lines.append("- **Reset automático:** na virada do pregão (`YYYYMMDD` diferente), a `Jumba_SafetyGuard.mqh` limpa as variáveis do dia anterior e libera as entradas automaticamente.")
    lines.append("")
    lines.append("### Presets Recomendados de Input no Monitor (`Proposta B · 11 Robôs`)")
    lines.append("")
    lines.append("| Perfil de Risco | `InpMaxDailyLossGlobal` | `InpMaxDailyLossWin` | `InpMaxDailyLossWdo` |")
    lines.append("| :--- | :---: | :---: | :---: |")
    lines.append(f"| **Conservador (Global Ret/DD ★)** | `{rs0['primary_used']:.1f}` | `0.0` | `0.0` |")
    lines.append(f"| **Máx Lucro Global 💰** | `{(rs0['global_profit'] or rs0['primary_used']):.1f}` | `0.0` | `0.0` |")
    lines.append(
        f"| **Combo Multi-Escopo ⚡** | `{float(cb0.get('stop_global', 0)):.1f}` | "
        f"`{float(cb0.get('stop_win', 0)):.1f}` | `{float(cb0.get('stop_wdo', 0)):.1f}` |"
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
