"""CLI: Simulação e otimização completa de Stop Diário Máximo para os 11 robôs Jumba.

Uso:
    python -m research.stop_diario.run_stop_simulation --all-presets
    python -m research.stop_diario.run_stop_simulation --portfolio proposta_b_11 --win-mult 1 --wdo-mult 1
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from research.stop_diario.data_loader import PORTFOLIO_PRESETS, load_m1_bars
from research.stop_diario.engine import run_full_analysis
from research.stop_diario.report_html import generate_html_report
from research.stop_diario.report_md import generate_markdown_report

OUT_DIR = ROOT_DIR / "data" / "reports" / "stop_diario"
HTML_PATH = OUT_DIR / "relatorio_stop_diario_11_robos.html"
JSON_PATH = OUT_DIR / "stop_diario_results.json"
MD_PATH = ROOT_DIR / "docs" / "STOP_DIARIO_11_ROBOS.md"


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _export_preset_csvs(pid: str, res: dict[str, Any], out_dir: Path) -> None:
    _write_csv(out_dir / f"sweep_global_{pid}.csv", res["sweeps"]["global_m1"])
    _write_csv(out_dir / f"sweep_win_{pid}.csv", res["sweeps"]["win_isolated"])
    _write_csv(out_dir / f"sweep_wdo_{pid}.csv", res["sweeps"]["wdo_isolated"])
    _write_csv(out_dir / f"combo_grid_{pid}.csv", res["combined"]["all_combos"])

    flat_robots = []
    for rb in res["robots"]:
        flat_robots.append({
            "id": rb["id"],
            "magic": rb["magic"],
            "asset": rb["asset"],
            "tf": rb["tf"],
            "desc": rb["desc"],
            "trades": rb["total_trades"],
            "lots": rb["total_lots"],
            "profit": rb["total_profit"],
            "win_rate": rb["win_rate"],
            "pf": rb["pf"],
            "payoff": rb["payoff"],
            "expectancy": rb["expectancy"],
            "mae_mean": rb["mae"]["mean"],
            "mae_p90": rb["mae"]["p90"],
            "mae_max": rb["mae"]["max"],
            "mfe_mean": rb["mfe"]["mean"],
            "mfe_eff": rb["mfe_eff"],
            "optimal_trade_stop": rb["optimal_trade_stop"],
            "daily_mean": rb["daily"]["mean"],
            "daily_worst": rb["daily"]["worst"],
            "suggested_daily_stop": rb["suggested_daily_stop"],
            "worst_15_pnl": rb["worst_15_pnl"],
            "worst_15_share_pct": rb["worst_15_share_pct"],
        })
    _write_csv(out_dir / f"robots_{pid}.csv", flat_robots)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulação de Stop Diário Máximo — 11 Robôs Jumba")
    parser.add_argument("--portfolio", default="proposta_b_11", choices=list(PORTFOLIO_PRESETS.keys()))
    parser.add_argument("--all-presets", action="store_true", help="Roda proposta_b_11, m5_11 e top_8")
    parser.add_argument("--win-mult", type=float, default=1.0, help="Multiplicador de contratos WIN")
    parser.add_argument("--wdo-mult", type=float, default=1.0, help="Multiplicador de contratos WDO")
    parser.add_argument("--cost-mode", default="net", choices=["net", "mt5_raw", "gross"])
    parser.add_argument("--slippage", type=float, default=0.0, help="Slippage por lote ao estopar (R$)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print("Carregando barras M1 reais (WIN + WDO)...")
    m1_cache = load_m1_bars()

    pids = list(PORTFOLIO_PRESETS.keys()) if args.all_presets else [args.portfolio]
    results: dict[str, dict[str, Any]] = {}

    for pid in pids:
        tp = time.time()
        print(f"Simulando '{pid}' (win_mult={args.win_mult}, wdo_mult={args.wdo_mult}, cost={args.cost_mode})...")
        res = run_full_analysis(
            portfolio_id=pid,
            win_mult=args.win_mult,
            wdo_mult=args.wdo_mult,
            cost_mode=args.cost_mode,
            slippage_per_lot=args.slippage,
            m1_cache=m1_cache,
        )
        results[pid] = res
        _export_preset_csvs(pid, res, OUT_DIR)
        b = res["baseline"]
        rs = res["robust_stops"]
        f1 = res["final_ret_dd"]
        f2 = res["final_profit"]
        fc = res["final_combo"]
        cb = rs.get("combo_best_ret_dd") or {}
        print(
            f"  [OK] {res['label']} ({time.time() - tp:.2f}s) | "
            f"Base: R${b['ret']:,.0f} DD R${b['max_dd']:,.0f} ({b['ret_dd']:.2f}x) | "
            f"Stop Ret/DD=R${rs['primary_used']} -> R${f1['ret']:,.0f} DD R${f1['max_dd']:,.0f} ({f1['ret_dd']:.2f}x, {f1['stopped']}d) | "
            f"MaxLucro=R${rs['global_profit']} -> R${f2['ret']:,.0f} ({f2['ret_dd']:.2f}x) | "
            f"Combo G={cb.get('stop_global',0)}/W={cb.get('stop_win',0)}/D={cb.get('stop_wdo',0)} -> "
            f"R${fc['ret']:,.0f} DD R${fc['max_dd']:,.0f} ({fc['ret_dd']:.2f}x, {fc['stopped']}d)"
        )

    JSON_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    generate_html_report(results, HTML_PATH, default_preset=pids[0])
    generate_markdown_report(results, MD_PATH)

    print(f"\nArtefatos gerados em {time.time() - t0:.2f}s:")
    print(f"  - JSON     : {JSON_PATH}")
    print(f"  - HTML     : {HTML_PATH}")
    print(f"  - Markdown : {MD_PATH}")


if __name__ == "__main__":
    main()
