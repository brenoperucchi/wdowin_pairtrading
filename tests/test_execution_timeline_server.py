import asyncio
import json
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import server
from core.execution_timeline import init_timeline_table, load_timeline, record_event
from core.timeline_emit import emit_closed_bar_timeline


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


def test_lifespan_starts_trade_eval_loop_without_firebase(monkeypatch):
    started = {"value": False}

    async def fake_trade_eval_loop():
        started["value"] = True
        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    monkeypatch.setattr(server, "firebase_initialized", False)
    monkeypatch.setattr(server, "trade_eval_loop", fake_trade_eval_loop)
    monkeypatch.setattr(server, "do_backfill_if_empty", lambda: None)

    with TestClient(server.app):
        assert started["value"] is True


def test_trade_eval_loop_runs_regime_without_firebase(monkeypatch):
    calls = {"count": 0}

    def fake_run_regime():
        calls["count"] += 1
        return {"error": None, "trade_engine": {"action": "WAIT"}}

    async def stop_after_first_cycle(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(server, "firebase_initialized", False)
    monkeypatch.setattr(server, "_run_regime_v2_from_loop", fake_run_regime)
    monkeypatch.setattr(server.asyncio, "sleep", stop_after_first_cycle)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(server.trade_eval_loop())

    assert calls["count"] == 1
    assert server._get_eval_state()["loop_running"] is False


def test_serialized_regime_call_records_loop_source_and_snapshot(monkeypatch):
    monkeypatch.setattr(server, "_latest_regime_snapshot", None)
    wrapped = server._serialized_regime_call(lambda: {"error": None, "ok": True})

    token = server._eval_source.set("loop")
    try:
        result = wrapped()
    finally:
        server._eval_source.reset(token)

    state = server._get_eval_state()
    assert result == {"error": None, "ok": True}
    assert state["last_source"] == "loop"
    assert state["last_completed_at"] is not None
    assert state["last_duration_ms"] >= 0
    assert state["last_error"] is None
    assert state["last_result_error"] is None
    assert server._latest_regime_snapshot == result


def test_health_reports_trade_eval_loop_state(monkeypatch):
    monkeypatch.setattr(server, "connect_mt5", lambda: False)
    monkeypatch.setattr(server, "_latest_regime_snapshot", {"ok": True})
    server._set_eval_state(
        loop_running=True,
        in_progress=False,
        last_completed_at="2026-05-09T10:00:00",
        last_completed_epoch=time.time() - 4,
        last_source="loop",
        last_duration_ms=12.3,
        last_error=None,
        last_error_at=None,
        last_result_error=None,
    )

    out = server.health()

    assert out["trade_eval_loop"]["running"] is True
    assert out["trade_eval_loop"]["last_source"] == "loop"
    assert out["trade_eval_loop"]["last_completed_age_sec"] >= 4
    assert out["trade_eval_loop"]["has_snapshot"] is True


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

    inserted = emit_closed_bar_timeline(
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

    assert emit_closed_bar_timeline(**kwargs) == 4
    assert emit_closed_bar_timeline(**kwargs) == 0
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


def test_execution_timeline_html_page_renders_summary_and_rows(tmp_path, monkeypatch):
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
        dedupe_key="bar:1:CONS_BASE:SIGNAL:WAIT",
        closed_bar_ts=1,
        phase="SIGNAL",
        event="WAIT",
        status="SKIPPED",
        strategy="CONS_BASE",
    )

    client = TestClient(server.app)
    response = client.get("/execution-timeline")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "Execution Timeline" in body
    assert "Gargalo atual" in body
    assert "EG_NOT_COINTEGRATED" in body
    assert "ELIGIBILITY" in body
    assert "WAIT" in body
    assert 'http-equiv="refresh"' in body  # default refresh=5


def test_execution_timeline_html_filters_by_phase_and_disables_refresh(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)
    record_event(
        db,
        dedupe_key="bar:1:GLOBAL:ELIGIBILITY:EG",
        closed_bar_ts=1,
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
    )
    record_event(
        db,
        dedupe_key="bar:1:GLOBAL:RISK:MAX_TRADES",
        closed_bar_ts=1,
        phase="RISK",
        event="MAX_TRADES_REACHED",
        status="BLOCKED",
    )

    client = TestClient(server.app)
    response = client.get(
        "/execution-timeline",
        params={"phase": "ELIGIBILITY", "refresh": 0},
    )

    assert response.status_code == 200
    body = response.text
    assert "EG_NOT_COINTEGRATED" in body
    assert "MAX_TRADES_REACHED" not in body
    assert 'http-equiv="refresh"' not in body
