"""CLI principal da Bateria de Validação & Inclusão dos 24 Robôs Não Utilizados.

Uso:
    python -m research.unused_robots_battery.run_battery
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from research.stop_diario.data_loader import DATE_END_2026, DATE_START_2026, load_m1_bars
from research.unused_robots_battery.battery import run_all_24_battery
from research.unused_robots_battery.portfolio_inclusion import run_portfolio_inclusion_study
from research.unused_robots_battery.report_html import generate_html_report
from research.unused_robots_battery.report_md import generate_markdown_report

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT_DIR / "data" / "reports" / "unused_robots_battery"
MD_PATH = ROOT_DIR / "docs" / "BATERIA_ROBOS_NAO_USADOS.md"


def _strip_trades(bat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = []
    for r in bat:
        c = {k: v for k, v in r.items() if k not in ("baseline_trades", "best_trades")}
        clean.append(c)
    return clean


def main():
    parser = argparse.ArgumentParser(description="Bateria de validação e inclusão dos 24 robôs não utilizados.")
    parser.add_argument("--workers", type=int, default=min(12, os.cpu_count() or 4), help="Processos paralelos")
    args = parser.parse_args()

    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Carregando barras M1 reais de 2026 (WIN + WDO)...", flush=True)
    win_m1, wdo_m1 = load_m1_bars()
    all_days = sorted(d for d in (set(win_m1.keys()) | set(wdo_m1.keys())) if DATE_START_2026 <= d <= DATE_END_2026)
    print(f"      {len(all_days)} pregões ({all_days[0]} .. {all_days[-1]}) em {time.time() - t0:.1f}s", flush=True)

    print(f"\n[2/4] Rodando bateria anti-overfitting (24 robôs não utilizados, {args.workers} workers)...", flush=True)
    t1 = time.time()
    battery_results = run_all_24_battery(all_days, max_workers=args.workers)
    print(f"      Bateria concluída em {time.time() - t1:.1f}s", flush=True)

    print("\n[3/4] Rodando estudo de inclusão no portfólio Top 8 (M1 intraday + Stop Live G850/W400/D550)...", flush=True)
    t2 = time.time()
    inclusion = run_portfolio_inclusion_study(battery_results, win_m1, wdo_m1, all_days)
    print(f"      Inclusão concluída em {time.time() - t2:.1f}s (pool elegível: {inclusion['pool_size']} robôs)", flush=True)

    print("\n[4/4] Exportando CSVs, JSON, Markdown e HTML interativo...", flush=True)
    # CSV resumo da bateria
    bat_rows = []
    for r in battery_results:
        b = r["baseline"]
        o = r["best_is"]
        bat_rows.append({
            "code": r["code"],
            "asset": r["asset"],
            "tf": r["tf"],
            "in_proposta_b": r["in_proposta_b"],
            "base_verdict": b["verdict"],
            "base_gates": b["gates_passed"],
            "base_net": b["full"]["net"],
            "base_dd": b["full"]["dd_day"],
            "base_ret_dd": b["full"]["ret_dd"],
            "base_pf": b["full"]["pf"],
            "base_trades": b["full"]["trades"],
            "base_oos_net": b["oos"]["net"],
            "adj_label": o["label"],
            "adj_n_changed": o["n_changed"],
            "adj_verdict": o["verdict"],
            "adj_gates": o["gates_passed"],
            "adj_net": o["full"]["net"],
            "adj_dd": o["full"]["dd_day"],
            "adj_ret_dd": o["full"]["ret_dd"],
            "adj_pf": o["full"]["pf"],
            "adj_trades": o["full"]["trades"],
            "adj_is_ret_dd": o["is"]["ret_dd"],
            "adj_oos_net": o["oos"]["net"],
            "adj_oos_pf": o["oos"]["pf"],
            "adj_oos_ret_dd": o["oos"]["ret_dd"],
            "adj_h1_net": o["h1"]["net"],
            "adj_h2_net": o["h2"]["net"],
            "adj_stress_pf": o["stress"]["pf"],
            "adj_pos_months": f"{o['full']['pos_months']}/{o['full']['total_months']}",
            "plateau_pct": r["plateau_pct"],
            "configs_tested": r["configs_tested"],
        })
    pd.DataFrame(bat_rows).to_csv(OUT_DIR / "battery_24_summary.csv", index=False)

    # CSV inclusão marginal 1-a-1
    marg_rows = []
    for m in inclusion["marginal"]:
        sl = m["stop_live_850"]
        ns = m["no_stop"]
        si = m["stop_indep_0"]
        marg_rows.append({
            "key": m["key"],
            "code": m["code"],
            "asset": m["asset"],
            "verdict": m["verdict"],
            "label": m["label"],
            "corr_all": m["corr_all"],
            "corr_asset": m["corr_asset"],
            "pnl_worst15": m["pnl_on_top8_worst15"],
            "nostop_ret": ns["ret"],
            "nostop_dd": ns["max_dd"],
            "nostop_ret_dd": ns["ret_dd"],
            "nostop_d_ret_dd": ns["d_ret_dd"],
            "stop850_ret": sl["ret"],
            "stop850_d_ret": sl["d_ret"],
            "stop850_dd": sl["max_dd"],
            "stop850_d_dd": sl["d_dd"],
            "stop850_ret_dd": sl["ret_dd"],
            "stop850_d_ret_dd": sl["d_ret_dd"],
            "stop850_oos_ret_dd": sl["oos_ret_dd"],
            "stop850_d_oos_ret_dd": sl["d_oos_ret_dd"],
            "stop0_ret_dd": si["ret_dd"],
            "stop0_d_ret_dd": si["d_ret_dd"],
        })
    pd.DataFrame(marg_rows).to_csv(OUT_DIR / "portfolio_inclusion_1by1.csv", index=False)

    payload = {
        "total_days": len(all_days),
        "period_start": all_days[0],
        "period_end": all_days[-1],
        "battery": _strip_trades(battery_results),
        "inclusion": inclusion,
    }
    (OUT_DIR / "battery_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    generate_markdown_report(payload, MD_PATH)
    generate_html_report(payload, OUT_DIR / "relatorio_bateria_robos_nao_usados.html")

    print(f"\n[CONCLUIDO] Tempo total: {time.time() - t0:.1f}s")
    print(f"  - Markdown : {MD_PATH}")
    print(f"  - HTML     : {OUT_DIR / 'relatorio_bateria_robos_nao_usados.html'}")
    print(f"  - CSVs     : {OUT_DIR / 'battery_24_summary.csv'} | {OUT_DIR / 'portfolio_inclusion_1by1.csv'}")


if __name__ == "__main__":
    main()
