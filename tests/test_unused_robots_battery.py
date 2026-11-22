"""Testes unitários e de integridade para a bateria de validação dos 24 robôs não utilizados."""

from __future__ import annotations

from pathlib import Path
import json

from research.unused_robots_battery.battery import (
    build_stage_a_grid,
    build_stage_b_grid,
    compute_is_selection_score,
    compute_trade_metrics,
    evaluate_5_gates,
)
from research.unused_robots_battery.catalog import (
    ACTIVE_8_ROBOTS,
    SPEC_BY_CODE,
    UNUSED_24_SPECS,
    count_changed_knobs,
    format_cfg_label,
)


def test_catalog_has_exact_24_unused_and_disjoint_from_active_8():
    codes = [s.code for s in UNUSED_24_SPECS]
    assert len(codes) == 24
    assert len(set(codes)) == 24
    assert set(codes).isdisjoint(set(ACTIVE_8_ROBOTS))
    assert sum(1 for s in UNUSED_24_SPECS if s.asset == "WIN") == 11
    assert sum(1 for s in UNUSED_24_SPECS if s.asset == "WDO") == 13


def test_stage_grids_include_baseline_and_dedup():
    for code in ("EST-01", "EST-03", "EST-16", "WDO-02"):
        spec = SPEC_BY_CODE[code]
        ga = build_stage_a_grid(spec)
        assert spec.baseline_cfg in ga
        assert len(ga) >= 6
        gb = build_stage_b_grid([spec.baseline_cfg])
        assert spec.baseline_cfg in gb
        assert len(gb) >= 10
        assert count_changed_knobs(spec, spec.baseline_cfg) == 0
        assert format_cfg_label(spec, spec.baseline_cfg) == "ORIGINAL (sem ajuste)"


def test_five_gates_verdict_logic():
    ok_is = {"trades": 60, "net": 1500.0, "pf": 1.35, "ret_dd": 3.0, "pos_months": 5, "total_months": 7}
    ok_oos = {"trades": 25, "net": 700.0, "pf": 1.28, "ret_dd": 1.8}
    ok_h1 = {"net": 900.0}
    ok_h2 = {"net": 1300.0}
    ok_full = {"net": 2200.0, "pos_months": 8, "total_months": 11}
    ok_stress = {"net": 1100.0, "pf": 1.15}

    res_ok = evaluate_5_gates(ok_is, ok_oos, ok_h1, ok_h2, ok_full, ok_stress)
    assert res_ok["verdict"] == "APROVADO"
    assert res_ok["gates_passed"] == 5

    # Falhar no OOS cego deve reprovar imediatamente (mesmo com IS forte)
    bad_oos = {"trades": 25, "net": -150.0, "pf": 0.92, "ret_dd": -0.3}
    res_bad = evaluate_5_gates(ok_is, bad_oos, ok_h1, ok_h2, ok_full, ok_stress)
    assert res_bad["verdict"] == "REPROVADO"

    # Passar OOS + Stress mas falhar em trades IS (ex: 32 trades) e meses (6/11) -> RESERVA
    low_is = {"trades": 32, "net": 800.0, "pf": 1.30, "ret_dd": 2.0, "pos_months": 4, "total_months": 7}
    low_m = {"net": 1500.0, "pos_months": 6, "total_months": 11}
    res_res = evaluate_5_gates(low_is, ok_oos, ok_h1, ok_h2, low_m, ok_stress)
    assert res_res["verdict"] == "RESERVA"


def test_compute_trade_metrics_consistency():
    trades = [
        {"date": "2026-01-05", "pnl": 100.0, "lots": 1.0},
        {"date": "2026-01-06", "pnl": -50.0, "lots": 1.0},
        {"date": "2026-02-02", "pnl": 200.0, "lots": 2.0},
    ]
    m = compute_trade_metrics(trades, all_days=["2026-01-05", "2026-01-06", "2026-02-02"])
    assert m["trades"] == 3
    assert m["lots"] == 4
    assert m["net"] == 250.0
    assert m["dd_day"] == 50.0
    assert m["ret_dd"] == 5.0
    assert m["pos_months"] == 2
    assert m["total_months"] == 2


def test_is_selection_score_parsimony():
    spec = SPEC_BY_CODE["EST-01"]
    m = {"trades": 80, "net": 1200.0, "pf": 1.30, "ret_dd": 3.0, "pos_months": 5, "total_months": 7}
    c_mod = dict(spec.baseline_cfg)
    c_mod["max_trades_day"] = 2
    assert compute_is_selection_score(spec, spec.baseline_cfg, m) > compute_is_selection_score(spec, c_mod, m)


def test_generated_artifacts_if_present():
    out_json = Path("data/reports/unused_robots_battery/battery_results.json")
    if out_json.exists():
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert len(data["battery"]) == 24
        assert "inclusion" in data
        assert len(data["inclusion"]["base_robots"]) == 8
