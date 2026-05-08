import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import server
from core.execution_timeline import init_timeline_table, load_timeline, record_event


def _timeline_db(tmp_path, monkeypatch):
    db = str(tmp_path / "timeline_server.db")
    init_timeline_table(db)
    monkeypatch.setattr(server, "DB_PATH", db)
    for attr in ("_last_emitted_bar_ts", "_timeline_data_failed"):
        if hasattr(server.regime_v2, attr):
            delattr(server.regime_v2, attr)
    return db


def _trade_result(action="WAIT"):
    return {
        "strategies": {
            "CONS_BASE": {"action": action},
            "WDO_NWE": {"action": action},
            "DI_NWE": {"action": action},
        }
    }


def test_record_timeline_data_failure_dedupes_by_minute(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)
    now = datetime.fromisoformat("2026-05-08T10:00:10")

    first = server._record_timeline_data_failure(
        "MT5_DISCONNECTED",
        message="down",
        now_dt=now,
        db_path=db,
    )
    second = server._record_timeline_data_failure(
        "MT5_DISCONNECTED",
        message="still down",
        now_dt=now.replace(second=40),
        db_path=db,
    )

    assert first is not None
    assert second is None
    rows = load_timeline(db, limit=10)
    assert len(rows) == 1
    assert rows[0]["event"] == "MT5_DISCONNECTED"


def test_emit_closed_bar_timeline_records_gate_reasons_and_skips_bar_not_closed(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)

    inserted = server._emit_closed_bar_timeline(
        closed_bar_ts=1778243100,
        gate={
            "allowed": False,
            "reasons": ["BAR_NOT_CLOSED", "EG_NOT_COINTEGRATED", "MAX_TRADES_REACHED"],
        },
        trade_result=_trade_result(),
        z_wdo=1.5,
        z_di=1.2,
        rho=-0.93,
        rho_level=0,
        beta_delta_pct=0.3,
        eg_pvalue=0.64,
        joh_open=False,
        mt5_connected=True,
        trades_today_count=4,
        daily_pnl_brl=0.0,
        minutes_since_last_loss=None,
        now_dt=datetime.fromisoformat("2026-05-08T10:05:00"),
        db_path=db,
    )

    assert inserted == 6  # INDICATORS + EG + MAX_TRADES + 3 strategy SKIPPED
    rows = load_timeline(db, limit=20)
    events = {r["event"]: r for r in rows}
    assert "BAR_NOT_CLOSED" not in events
    assert events["INDICATORS_OK"]["phase"] == "INDICATORS"

    eg = events["EG_NOT_COINTEGRATED"]
    assert eg["phase"] == "ELIGIBILITY"
    assert eg["metric"] == "eg_pvalue"
    assert eg["operator"] == "<"
    assert eg["distance"] == pytest.approx(0.54)
    assert eg["ratio_to_threshold"] == pytest.approx(6.4)

    risk = events["MAX_TRADES_REACHED"]
    assert risk["phase"] == "RISK"
    assert risk["severity"] == "operational_block"

    skipped = [r for r in rows if r["phase"] == "SIGNAL" and r["event"] == "SKIPPED"]
    assert {r["strategy"] for r in skipped} == {"CONS_BASE", "WDO_NWE", "DI_NWE"}
    payload = json.loads(skipped[0]["payload_json"])
    assert payload["gate_reasons"] == ["EG_NOT_COINTEGRATED", "MAX_TRADES_REACHED"]


def test_emit_closed_bar_timeline_dedupes_same_closed_bar(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)
    kwargs = dict(
        closed_bar_ts=1778243100,
        gate={"allowed": True, "reasons": []},
        trade_result=_trade_result(),
        z_wdo=0.2,
        z_di=0.1,
        rho=-0.9,
        rho_level=0,
        beta_delta_pct=0.2,
        eg_pvalue=0.04,
        joh_open=True,
        mt5_connected=True,
        trades_today_count=0,
        daily_pnl_brl=0.0,
        minutes_since_last_loss=None,
        now_dt=datetime.fromisoformat("2026-05-08T10:05:00"),
        db_path=db,
    )

    assert server._emit_closed_bar_timeline(**kwargs) == 4
    assert server._emit_closed_bar_timeline(**kwargs) == 0
    rows = load_timeline(db, limit=20)
    assert len(rows) == 4  # INDICATORS + 3 WAIT signals


def test_execution_timeline_endpoint_returns_events_summary_and_filters(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)
    record_event(
        db,
        dedupe_key="bar:1:GLOBAL:ELIGIBILITY:EG",
        closed_bar_ts=1,
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
        metric="eg_pvalue",
        value=0.64,
        threshold=0.10,
        operator="<",
    )
    record_event(
        db,
        dedupe_key="bar:1:CONS_BASE:SIGNAL:SKIPPED",
        closed_bar_ts=1,
        phase="SIGNAL",
        event="SKIPPED",
        status="SKIPPED",
        strategy="CONS_BASE",
    )

    client = TestClient(server.app)
    response = client.get("/api/execution-timeline", params={"phase": "ELIGIBILITY"})

    assert response.status_code == 200
    data = response.json()
    assert [e["phase"] for e in data["events"]] == ["ELIGIBILITY"]
    assert data["summary"]["current_bottleneck"]["event"] == "EG_NOT_COINTEGRATED"
    assert data["summary"]["current_live_issue"] is None

    alias_response = client.get("/api/execution_timeline", params={"phase": "ELIGIBILITY"})
    assert alias_response.status_code == 200
    assert alias_response.json()["events"] == data["events"]
