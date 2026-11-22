"""Testes unitários e de integração do sistema de Stop Diário Máximo (11 Robôs)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from research.stop_diario.data_loader import (
    DEFAULT_HTM_DIR,
    PORTFOLIO_PRESETS,
    ROBOT_METADATA,
    enrich_trades_with_m1_mae_mfe,
    load_m1_bars,
    parse_mt5_htm_trades,
)
from research.stop_diario.engine import (
    analyze_robots,
    build_intraday_days,
    compute_recovery_bands,
    run_full_analysis,
    run_monte_carlo,
    run_param_sweep,
    run_walk_forward,
    simulate_combined_stops,
    simulate_single_scope,
)
from research.stop_diario.report_html import generate_html_report
from research.stop_diario.report_md import generate_markdown_report


def test_parse_htm_exact_smartgrid_matching() -> None:
    """SmartGrid multi-leg (EST-13) deve parear 100% dos deals com erro 0,00."""
    spec = ROBOT_METADATA["EST-13"]
    trades = parse_mt5_htm_trades(DEFAULT_HTM_DIR / "EST13_P1.htm", "EST-13", cost_mode="net")
    assert len(trades) == 681
    for t in trades:
        expected_raw = t["side"] * (t["px_out"] - t["px_in"]) * spec.pt_val * t["lots"]
        assert abs(t["pnl_mt5_raw"] - expected_raw) < 0.05
        assert abs(t["pnl"] - (t["pnl_mt5_raw"] - t["cost_extra"])) < 0.05


def test_m1_hedge_and_exit_clamp() -> None:
    """Posições opostas simultâneas no mesmo ativo devem fazer hedge intrabar M1."""
    # 1 pregão sintético com 3 barras M1 (09:30, 09:31, 09:32)
    win_bars = {
        "2026-06-01": {
            "mins": np.array([570, 571, 572], dtype=np.int32),
            "open": np.array([100000.0, 100000.0, 100000.0]),
            "high": np.array([100050.0, 100200.0, 100010.0]),
            "low": np.array([99950.0, 99500.0, 99990.0]),
            "close": np.array([100000.0, 100000.0, 100000.0]),
            "min_to_idx": {570: 0, 571: 1, 572: 2},
        }
    }
    wdo_bars = {}

    # Trade BUY 1L + Trade SELL 1L abertos 09:30 e fechados 09:32 exatamente no 0x0
    tr_buy = {
        "strat": "EST-01", "asset": "WIN", "tf": "M5", "magic": 88001,
        "side": 1, "lots": 1.0, "t_in": "2026-06-01 09:30:00", "t_out": "2026-06-01 09:32:00",
        "date": "2026-06-01", "date_in": "2026-06-01",
        "min_in": 570, "min_out": 572, "sec_in": 570 * 60, "sec_out": 572 * 60,
        "px_in": 100000.0, "px_out": 100000.0,
        "pnl": -1.0, "pnl_mt5_raw": 0.0, "pnl_gross": 1.0, "cost_extra": 1.0, "cost_total": 2.0, "comment": "",
    }
    tr_sell = {
        "strat": "EST-04", "asset": "WIN", "tf": "M5", "magic": 88004,
        "side": -1, "lots": 1.0, "t_in": "2026-06-01 09:30:00", "t_out": "2026-06-01 09:32:00",
        "date": "2026-06-01", "date_in": "2026-06-01",
        "min_in": 570, "min_out": 572, "sec_in": 570 * 60, "sec_out": 572 * 60,
        "px_in": 100000.0, "px_out": 100000.0,
        "pnl": -1.0, "pnl_mt5_raw": 0.0, "pnl_gross": 1.0, "cost_extra": 1.0, "cost_total": 2.0, "comment": "",
    }
    days = build_intraday_days([tr_buy, tr_sell], win_bars, wdo_bars, all_dates=["2026-06-01"])
    # Na barra 09:31 (low 99500 = -500 pts para buy e +500 pts para sell), soma líquida = -R$2 de custo apenas!
    assert days[0]["mae_intraday"] == 2.0
    assert days[0]["mae_win"] == 2.0


def test_combined_stops_independent_asset_locking() -> None:
    """Stop WIN deve travar só WIN e manter WDO operando normalmente no mesmo dia."""
    win_bars = {
        "2026-06-01": {
            "mins": np.array([570, 580, 600, 610], dtype=np.int32),
            "open": np.array([100000.0, 99000.0, 99000.0, 99000.0]),
            "high": np.array([100000.0, 99000.0, 99000.0, 99000.0]),
            "low": np.array([100000.0, 97500.0, 97500.0, 97500.0]),
            "close": np.array([100000.0, 97500.0, 97500.0, 97500.0]),
            "min_to_idx": {570: 0, 580: 1, 600: 2, 610: 3},
        }
    }
    wdo_bars = {
        "2026-06-01": {
            "mins": np.array([570, 580, 600, 610], dtype=np.int32),
            "open": np.array([5000.0, 5000.0, 5000.0, 5020.0]),
            "high": np.array([5000.0, 5000.0, 5000.0, 5020.0]),
            "low": np.array([5000.0, 5000.0, 5000.0, 5000.0]),
            "close": np.array([5000.0, 5000.0, 5000.0, 5020.0]),
            "min_to_idx": {570: 0, 580: 1, 600: 2, 610: 3},
        }
    }
    # WIN perde -500 BRL às 09:40 (580); WDO abre depois às 10:00 (600) e ganha +200 BRL às 10:10 (610)
    tr_win = {
        "strat": "EST-01", "asset": "WIN", "tf": "M5", "magic": 88001,
        "side": 1, "lots": 1.0, "t_in": "2026-06-01 09:30:00", "t_out": "2026-06-01 09:40:00",
        "date": "2026-06-01", "date_in": "2026-06-01",
        "min_in": 570, "min_out": 580, "sec_in": 570 * 60, "sec_out": 580 * 60,
        "px_in": 100000.0, "px_out": 97500.0,
        "pnl": -501.0, "pnl_mt5_raw": -500.0, "pnl_gross": -499.0, "cost_extra": 1.0, "cost_total": 2.0, "comment": "",
    }
    tr_wdo = {
        "strat": "WDO-01", "asset": "WDO", "tf": "M5", "magic": 89001,
        "side": 1, "lots": 1.0, "t_in": "2026-06-01 10:00:00", "t_out": "2026-06-01 10:10:00",
        "date": "2026-06-01", "date_in": "2026-06-01",
        "min_in": 600, "min_out": 610, "sec_in": 600 * 60, "sec_out": 610 * 60,
        "px_in": 5000.0, "px_out": 5020.0,
        "pnl": 200.0, "pnl_mt5_raw": 200.0, "pnl_gross": 205.0, "cost_extra": 0.0, "cost_total": 5.0, "comment": "",
    }
    days = build_intraday_days([tr_win, tr_wdo], win_bars, wdo_bars, all_dates=["2026-06-01"])

    # Apenas Stop WIN=300: WIN trava em -300, WDO soma +200 -> resultado do dia = -100
    sim_win_only = simulate_combined_stops(days, stop_global=0.0, stop_win=300.0, stop_wdo=0.0)
    assert sim_win_only["ret"] == -100.0
    assert sim_win_only["stopped_win"] == 1
    assert sim_win_only["stopped_wdo"] == 0
    assert sim_win_only["stopped_global"] == 0

    # Stop Global=300: dispara em 09:40 quando WIN chega em -300 e fecha tudo -> dia trava em -300
    sim_glob = simulate_combined_stops(days, stop_global=300.0, stop_win=0.0, stop_wdo=0.0)
    assert sim_glob["ret"] == -300.0
    assert sim_glob["stopped_global"] == 1


def test_full_proposta_b_pipeline_and_reports(tmp_path: Path) -> None:
    """Executa análise completa Proposta B (11 robôs) e valida WFA, MC, Robôs, HTML e MD."""
    m1_cache = load_m1_bars()
    res = run_full_analysis("proposta_b_11", m1_cache=m1_cache)

    assert res["portfolio"]["total_robots"] == 11
    assert res["total_days"] == 212
    assert res["oos_days"] == 84
    assert res["is_days"] == 128

    # WFA rolling deve gerar >= 5 folds (em 212 pregões com 60d/20d gera 7 folds)
    folds = res["walk_forward"]["folds"]
    assert len(folds) >= 5
    assert len(res["walk_forward"]["canonical_splits"]) == 2

    # Monte Carlo determinístico
    mc1 = run_monte_carlo(build_intraday_days(
        [], m1_cache[0], m1_cache[1], all_dates=sorted(m1_cache[0].keys())[:10]
    ), 500.0, n_sims=50, seed=42)
    assert mc1["n"] == 50

    mc_a = res["monte_carlo"]["iid"]
    assert mc_a["n"] == 2000
    assert 0 <= mc_a["wins_rdd"] <= 2000

    # Recovery e Robôs
    assert len(res["recovery"]["global"]) > 0
    assert len(res["robots"]) == 11
    assert {r["id"] for r in res["robots"]} == set(PORTFOLIO_PRESETS["proposta_b_11"]["robots"])

    # Relatórios HTML e MD
    html_p = generate_html_report({"proposta_b_11": res}, tmp_path / "stop_report.html")
    md_p = generate_markdown_report({"proposta_b_11": res}, tmp_path / "STOP_REPORT.md")
    assert html_p.exists() and html_p.stat().st_size > 15_000
    assert md_p.exists() and "Proposta B" in md_p.read_text(encoding="utf-8")
