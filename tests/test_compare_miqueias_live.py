import json
from datetime import datetime

from scripts import compare_miqueias_live as cmp


def _v2(*, z=-0.5, rho=-0.8, action="WAIT", explicit_gate=True):
    out = {
        "current_z": z,
        "current_rho": rho,
        "beta_delta_pct": 3.0,
        "beta_unstable": False,
        "meta": {"version": "v2_kalman", "symbol_a": "WIN$N", "symbol_b": "WDO$N"},
        "regime_health": {"safe_to_trade": True},
        "trade_engine": {
            "action": action,
            "strategies": {
                "CONS_BASE": {"action": action},
                "WDO_NWE": {"action": "WAIT"},
                "DI_NWE": {"action": "WAIT"},
            },
        },
    }
    if explicit_gate:
        out["risk_gate"] = {
            "allowed": True,
            "reasons": [],
            "informational": {"eg_pvalue": 0.03},
        }
    else:
        out["coint_eg"] = {"pvalue": 0.03}
    return out


def _di(z=1.2):
    return {
        "current_z": z,
        "current_rho": -0.7,
        "beta_delta_pct": 2.0,
        "beta_unstable": False,
        "regime_health": {"safe_to_trade": True},
        "coint_eg": {"pvalue": 0.04},
    }


def test_business_snapshot_extracts_explicit_and_reference_gate_shapes():
    ours = cmp.business_snapshot(_v2(explicit_gate=True), _di())
    ref = cmp.business_snapshot(_v2(explicit_gate=False), _di())

    assert ours["risk_gate_allowed"] is True
    assert ours["eg_pvalue"] == 0.03
    assert ref["risk_gate_allowed"] is None
    assert ref["safe_to_trade"] is True
    assert ref["eg_pvalue"] == 0.03
    assert ref["strategy_actions"]["CONS_BASE"] == "WAIT"


def test_compare_business_reports_strategy_and_indicator_mismatches():
    ours = cmp.business_snapshot(_v2(z=1.0, action="SELL_WIN"), _di(z=2.0))
    ref = cmp.business_snapshot(_v2(z=-1.0, action="WAIT"), _di(z=-2.0))

    diffs = cmp.compare_business(ours, ref)
    paths = {d["path"] for d in diffs}

    assert "current_z_wdo" in paths
    assert "current_z_di" in paths
    assert "strategy_actions.CONS_BASE" in paths


def test_decision_summary_separates_signal_mismatch_from_indicator_noise():
    ours = cmp.business_snapshot(_v2(z=1.0, action="SELL_WIN"), _di(z=2.0))
    ref = cmp.business_snapshot(_v2(z=-1.0, action="WAIT"), _di(z=-2.0))

    decision = cmp.decision_summary(ours, ref)

    assert decision["has_signal_mismatch"] is True
    assert decision["engine"]["ours_action"] == "SELL_WIN"
    assert decision["engine"]["ref_action"] == "WAIT"
    assert decision["signal_mismatches"] == [{
        "strategy": "CONS_BASE",
        "ours_action": "SELL_WIN",
        "ref_action": "WAIT",
        "matches": False,
    }]


def test_compare_fetch_health_reports_failed_endpoints():
    diffs = cmp.compare_fetch_health({
        "ours": {
            "v2": {
                "ok": False,
                "error": "Connection refused",
                "status_code": None,
                "url": "http://ours/api/v2/regime",
            }
        },
        "ref": {
            "v2": {
                "ok": True,
                "error": None,
                "status_code": 200,
                "url": "http://ref/api/v2/regime",
            }
        },
    })

    assert diffs == [{
        "path": "fetch.ours.v2",
        "ours": "Connection refused",
        "ref": None,
        "status_code": None,
        "url": "http://ours/api/v2/regime",
    }]


def test_run_compare_writes_raw_json_summary_and_audit(tmp_path, monkeypatch):
    def fake_fetch(url, *, timeout):
        if "ours" in url and "/api/v2/regime" in url:
            return cmp.FetchResult(ok=True, url=url, status_code=200, data=_v2(action="SELL_WIN"))
        if "ours" in url and "/api/di-regime" in url:
            return cmp.FetchResult(ok=True, url=url, status_code=200, data=_di(z=1.5))
        if "ref" in url and "/api/v2/regime" in url:
            return cmp.FetchResult(ok=True, url=url, status_code=200, data=_v2(action="WAIT", explicit_gate=False))
        if "ref" in url and "/api/di-regime" in url:
            return cmp.FetchResult(ok=True, url=url, status_code=200, data=_di(z=1.5))
        return cmp.FetchResult(ok=True, url=url, status_code=200, data={"status": "ok"})

    monkeypatch.setattr(cmp, "fetch_json", fake_fetch)

    run = cmp.run_compare(
        ours_base="http://ours",
        ref_base="http://ref",
        out_dir=tmp_path / "audit",
        timeout=1.0,
    )

    summary_path = tmp_path / "audit" / "summary.json"
    audit_path = tmp_path / "audit" / "audit.jsonl"
    assert summary_path.exists()
    assert audit_path.exists()
    assert (tmp_path / "audit" / "ours_v2.json").exists()
    assert (tmp_path / "audit" / "ref_v2.json").exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["differences"]
    assert run.files["audit_jsonl"] == str(audit_path)

    audit_lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(e["phase"] == "DATA" and e["event"] == "FETCH_V2" for e in audit_lines)
    assert any(e["phase"] == "COMPARE" and e["event"] == "MISMATCH" for e in audit_lines)


def test_seconds_until_next_m5_respects_boundary_delay():
    assert cmp._seconds_until_next_m5(
        datetime(2026, 5, 11, 13, 52, 30),
        delay_seconds=8,
    ) == 158
    assert cmp._seconds_until_next_m5(
        datetime(2026, 5, 11, 13, 55, 3),
        delay_seconds=8,
    ) == 5
    assert cmp._seconds_until_next_m5(
        datetime(2026, 5, 11, 13, 55, 9),
        delay_seconds=8,
    ) == 299


def test_append_loop_index_writes_one_line_summary(tmp_path):
    run = cmp.CompareRun(
        timestamp="2026-05-11T13:55:08",
        output_dir=str(tmp_path / "sample"),
        differences=[{"path": "strategy_actions.DI_NWE", "ours": "WAIT", "ref": "SELL"}],
        business={
            "ours": {
                "trade_engine_action": "WAIT",
                "strategy_actions": {"DI_NWE": "WAIT"},
                "current_z_wdo": 0.1,
                "current_z_di": 1.1,
                "risk_gate_reasons": ["RHO_BREAKDOWN"],
            },
            "ref": {
                "trade_engine_action": "SELL",
                "strategy_actions": {"DI_NWE": "SELL"},
                "current_z_wdo": 0.1,
                "current_z_di": 1.8,
                "risk_gate_reasons": None,
            },
        },
    )

    cmp._append_loop_index(str(tmp_path), run, run_number=1, tag="test-loop")

    lines = (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["run_number"] == 1
    assert row["diff_count"] == 1
    assert row["decision"] == {}
    assert row["ours"]["strategy_actions"]["DI_NWE"] == "WAIT"
    assert row["ref"]["strategy_actions"]["DI_NWE"] == "SELL"
