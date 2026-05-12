from fastapi.testclient import TestClient
import json

import server


def test_comparative_page_renders():
    client = TestClient(server.app)

    res = client.get("/comparative")

    assert res.status_code == 200
    assert "Comparativo WDOWIN x Miqueias" in res.text
    assert "Comparativos intraday" in res.text
    assert "/api/comparative" in res.text


def test_comparative_api_returns_snapshot(monkeypatch):
    def fake_snapshot(*, ours, ref, tag, timeout):
        return {
            "schema": "wdowin.miqueias-live-compare.v1",
            "ours_base": ours,
            "ref_base": ref,
            "output_dir": "audits/live_compare/sample",
            "differences": [
                {"path": "strategy_actions.DI_NWE", "ours": "WAIT", "ref": "SELL"}
            ],
            "business": {
                "ours": {"strategy_actions": {"DI_NWE": "WAIT"}},
                "ref": {"strategy_actions": {"DI_NWE": "SELL"}},
            },
            "files": {"summary": "summary.json", "audit_jsonl": "audit.jsonl"},
        }

    monkeypatch.setattr(server, "_run_comparative_snapshot", fake_snapshot)
    client = TestClient(server.app)

    res = client.get(
        "/api/comparative",
        params={
            "ours": "http://127.0.0.1:8080",
            "ref": "http://127.0.0.1:8081",
            "tag": "test",
            "timeout": "1",
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["differences"][0]["path"] == "strategy_actions.DI_NWE"
    assert body["ours_base"] == "http://127.0.0.1:8080"


def test_comparative_history_compacts_intraday_rows(tmp_path, monkeypatch):
    out_dir = tmp_path / "live_compare"
    run_dir = out_dir / "20260511-100508-comparative-page"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(json.dumps({
        "timestamp": "2026-05-11T10:05:08",
        "output_dir": str(run_dir),
        "differences": [
            {"path": "strategy_actions.DI_NWE", "ours": "WAIT", "ref": "SELL"},
            {"path": "current_z_di", "ours": 1.1, "ref": 1.7},
        ],
        "decision": {
            "has_signal_mismatch": True,
            "indicator_diff_count": 1,
            "strategies": [
                {
                    "strategy": "DI_NWE",
                    "ours_action": "WAIT",
                    "ref_action": "SELL",
                    "matches": False,
                }
            ],
        },
        "business": {
            "ours": {
                "strategy_actions": {"DI_NWE": "WAIT"},
                "current_z_wdo": 0.2,
                "current_z_di": 1.1,
                "current_rho": -0.4,
                "eg_pvalue": 0.2,
                "risk_gate_reasons": ["RHO_BREAKDOWN"],
            },
            "ref": {
                "strategy_actions": {"DI_NWE": "SELL"},
                "current_z_wdo": 0.2,
                "current_z_di": 1.7,
                "current_rho": -0.4,
                "eg_pvalue": 0.2,
            },
        },
    }), encoding="utf-8")
    monkeypatch.setattr(server, "COMPARATIVE_OUT_DIR", str(out_dir))
    client = TestClient(server.app)

    res = client.get("/api/comparative/history", params={"date": "2026-05-11"})

    assert res.status_code == 200
    rows = res.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "20260511-100508-comparative-page"
    assert rows[0]["signal_mismatch"] is True
    assert rows[0]["actions"]["ours"]["DI_NWE"] == "WAIT"
    assert rows[0]["actions"]["ref"]["DI_NWE"] == "SELL"
    assert rows[0]["metrics"]["z_di"]["delta"] == -0.6
