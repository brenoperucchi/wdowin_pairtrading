import asyncio
import copy
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


def _epoch(iso_ts: str) -> int:
    return int(datetime.fromisoformat(iso_ts).timestamp())


def _mt5_epoch(iso_ts: str) -> int:
    return _epoch(iso_ts) - server.TIME_OFFSET


def _replay_timeline_db(tmp_path, monkeypatch, date="2026-05-08"):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(server, "REPLAY_DIR", str(replay_dir))
    db = str(replay_dir / f"execution_timeline_{date}.db")
    init_timeline_table(db)
    return db, date


def _trade_result(action="WAIT", gate_reasons=None):
    """Mirror TradeEngine.evaluate output. ``gate_reasons`` is the per-strategy
    list (post EG-bypass filter); pass the same list for all 3 slots when EG
    bypass isn't being exercised."""
    reasons = list(gate_reasons) if gate_reasons else []
    return {
        "strategies": {
            "CONS_BASE": {"action": action, "gate_reasons": list(reasons)},
            "WDO_NWE": {"action": action, "gate_reasons": list(reasons)},
            "DI_NWE": {"action": action, "gate_reasons": list(reasons)},
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
        trade_result=_trade_result(
            gate_reasons=["EG_NOT_COINTEGRATED", "MAX_TRADES_REACHED"],
        ),
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
    assert "Bloqueado por Engle-Granger" in eg["message"]
    assert "0.64" in eg["message"]
    assert "0.1" in eg["message"]

    risk = events["MAX_TRADES_REACHED"]
    assert risk["phase"] == "RISK"
    assert risk["severity"] == "operational_block"
    assert "limite diario de trades" in risk["message"]

    skipped = [r for r in rows if r["phase"] == "SIGNAL" and r["event"] == "SKIPPED"]
    assert {r["strategy"] for r in skipped} == {"CONS_BASE", "WDO_NWE", "DI_NWE"}
    payload = json.loads(skipped[0]["payload_json"])
    assert payload["gate_reasons"] == ["EG_NOT_COINTEGRATED", "MAX_TRADES_REACHED"]


def test_emit_closed_bar_timeline_uses_per_strategy_gate_reasons(tmp_path, monkeypatch):
    """When EG bypass strips a reason for one slot, that slot must NOT show
    EG in its SIGNAL payload — even though the global gate had it."""
    db = _timeline_db(tmp_path, monkeypatch)

    trade_result = {
        "strategies": {
            "CONS_BASE": {"action": "WAIT", "gate_reasons": ["EG_NOT_COINTEGRATED"]},
            "WDO_NWE":   {"action": "WAIT", "gate_reasons": ["EG_NOT_COINTEGRATED"]},
            "DI_NWE":    {"action": "WAIT", "gate_reasons": []},  # bypassed EG
        }
    }
    emit_closed_bar_timeline(
        closed_bar_ts=1778245200,
        gate={"allowed": False, "reasons": ["EG_NOT_COINTEGRATED"]},
        trade_result=trade_result,
        z_wdo=0.5, z_di=-1.1, rho=-0.57, rho_level=1,
        beta_delta_pct=1.0, eg_pvalue=0.79, joh_open=False,
        mt5_connected=True, trades_today_count=0, daily_pnl_brl=0.0,
        minutes_since_last_loss=None,
        now_dt=datetime.fromisoformat("2026-05-08T10:00:00"),
        db_path=db,
    )

    rows = load_timeline(db, limit=20)
    by_strat = {r["strategy"]: r for r in rows if r["phase"] == "SIGNAL"}
    # CONS_BASE / WDO_NWE blocked by EG → SKIPPED
    assert by_strat["CONS_BASE"]["event"] == "SKIPPED"
    assert by_strat["WDO_NWE"]["event"] == "SKIPPED"
    # DI_NWE bypassed EG → WAIT (no gate reasons)
    assert by_strat["DI_NWE"]["event"] == "WAIT"
    di_payload = json.loads(by_strat["DI_NWE"]["payload_json"])
    assert di_payload["gate_reasons"] == []


def test_emit_closed_bar_timeline_uses_runtime_thresholds(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)

    emit_closed_bar_timeline(
        closed_bar_ts=1778245200,
        gate={
            "allowed": False,
            "reasons": [
                "EG_NOT_COINTEGRATED",
                "RHO_BREAKDOWN",
                "BETA_DRIFT",
                "Z_ANOMALY",
            ],
        },
        trade_result=_trade_result(gate_reasons=["BETA_DRIFT"]),
        z_wdo=3.7,
        z_di=0.2,
        rho=-0.44,
        rho_level=3,
        beta_delta_pct=20.0,
        eg_pvalue=0.12,
        joh_open=False,
        mt5_connected=True,
        trades_today_count=0,
        daily_pnl_brl=0.0,
        minutes_since_last_loss=None,
        now_dt=datetime.fromisoformat("2026-05-08T10:00:00"),
        db_path=db,
        eg_threshold=0.15,
        rho_breakdown_level=3,
        beta_delta_max=15.0,
        z_anomaly=3.5,
    )

    events = {r["event"]: r for r in load_timeline(db, limit=20)}
    assert events["EG_NOT_COINTEGRATED"]["threshold"] == 0.15
    assert events["RHO_BREAKDOWN"]["threshold"] == 3
    assert events["BETA_DRIFT"]["threshold"] == 15.0
    assert events["Z_ANOMALY"]["threshold"] == 3.5
    assert "15" in events["BETA_DRIFT"]["message"]


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
    response = client.get(
        "/api/execution-timeline",
        params={"phase": "ELIGIBILITY", "market_hours": "0"},
    )

    assert response.status_code == 200
    data = response.json()
    assert [e["phase"] for e in data["events"]] == ["ELIGIBILITY"]
    assert "Bloqueado por Engle-Granger" in data["events"][0]["message"]
    assert data["summary"]["current_bottleneck"]["event"] == "EG_NOT_COINTEGRATED"
    assert "0.64" in data["summary"]["current_bottleneck"]["message"]
    assert data["summary"]["current_live_issue"] is None

    alias_response = client.get(
        "/api/execution_timeline",
        params={"phase": "ELIGIBILITY", "market_hours": "0"},
    )
    assert alias_response.status_code == 200
    assert alias_response.json()["events"] == data["events"]


def test_execution_timeline_endpoint_defaults_to_market_hours(tmp_path, monkeypatch):
    db = _timeline_db(tmp_path, monkeypatch)
    record_event(
        db,
        dedupe_key="bar:1:GLOBAL:ELIGIBILITY:EG",
        closed_bar_ts=_mt5_epoch("2026-05-08T10:00:00"),
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
        timestamp="2026-05-08T19:30:00",
    )
    record_event(
        db,
        dedupe_key="bar:2:GLOBAL:ELIGIBILITY:OUT",
        closed_bar_ts=_mt5_epoch("2026-05-08T18:25:00"),
        phase="ELIGIBILITY",
        event="OUT_OF_SESSION",
        status="BLOCKED",
        timestamp="2026-05-08T18:25:00",
    )

    client = TestClient(server.app)
    default = client.get("/api/execution-timeline")
    all_hours = client.get("/api/execution-timeline", params={"market_hours": "0"})

    assert default.status_code == 200
    default_body = default.json()
    assert default_body["market_hours"] is True
    assert default_body["market_window"] == {"start": "08:50", "end": "18:20"}
    assert [e["event"] for e in default_body["events"]] == ["EG_NOT_COINTEGRATED"]
    assert default_body["summary"]["current_bottleneck"]["event"] == "EG_NOT_COINTEGRATED"

    assert all_hours.status_code == 200
    all_body = all_hours.json()
    assert all_body["market_hours"] is False
    assert all_body["market_window"] == {"start": None, "end": None}
    assert [e["event"] for e in all_body["events"]] == [
        "OUT_OF_SESSION",
        "EG_NOT_COINTEGRATED",
    ]
    assert all_body["summary"]["current_bottleneck"]["event"] == "OUT_OF_SESSION"


def test_execution_timeline_endpoint_reads_replay_db_and_summary(tmp_path, monkeypatch):
    live_db = _timeline_db(tmp_path, monkeypatch)
    replay_db, replay_date = _replay_timeline_db(tmp_path, monkeypatch)
    record_event(
        live_db,
        dedupe_key="bar:2:GLOBAL:RISK:MAX_TRADES",
        closed_bar_ts=2,
        phase="RISK",
        event="MAX_TRADES_REACHED",
        status="BLOCKED",
    )
    record_event(
        replay_db,
        dedupe_key="bar:1:GLOBAL:ELIGIBILITY:EG",
        closed_bar_ts=1,
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
    )
    record_event(
        replay_db,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        dedupe_key="crit:DATA:MT5_DISCONNECTED:test",
        phase="DATA",
        event="MT5_DISCONNECTED",
        status="FAILED",
    )

    client = TestClient(server.app)
    response = client.get(
        "/api/execution-timeline",
        params={
            "mode": "replay",
            "date": replay_date,
            "phase": "ELIGIBILITY",
            "market_hours": "0",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "replay"
    assert data["date"] == replay_date
    assert [e["event"] for e in data["events"]] == ["EG_NOT_COINTEGRATED"]
    assert data["summary"]["current_bottleneck"]["event"] == "EG_NOT_COINTEGRATED"
    assert data["summary"]["current_live_issue"]["event"] == "MT5_DISCONNECTED"


def test_execution_timeline_endpoint_replay_not_found_and_bad_date(tmp_path, monkeypatch):
    _timeline_db(tmp_path, monkeypatch)
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    monkeypatch.setattr(server, "REPLAY_DIR", str(replay_dir))
    client = TestClient(server.app)

    missing = client.get(
        "/api/execution-timeline",
        params={"mode": "replay", "date": "2099-01-01"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"] == "REPLAY_NOT_FOUND"

    bad = client.get(
        "/api/execution-timeline",
        params={"mode": "replay", "date": "../etc/passwd"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "INVALID_REPLAY_DATE"

    no_date = client.get("/api/execution-timeline", params={"mode": "replay"})
    assert no_date.status_code == 400
    assert no_date.json()["error"] == "INVALID_REPLAY_DATE"


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
    response = client.get("/execution-timeline", params={"market_hours": "0"})

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
            params={"phase": "ELIGIBILITY", "refresh": 0, "market_hours": "0"},
    )

    assert response.status_code == 200
    body = response.text
    assert "EG_NOT_COINTEGRATED" in body
    assert "MAX_TRADES_REACHED" not in body
    assert 'http-equiv="refresh"' not in body


def test_execution_timeline_html_replay_mode_renders_replay_db(tmp_path, monkeypatch):
    live_db = _timeline_db(tmp_path, monkeypatch)
    replay_db, replay_date = _replay_timeline_db(tmp_path, monkeypatch)
    record_event(
        live_db,
        dedupe_key="bar:2:GLOBAL:RISK:MAX_TRADES",
        closed_bar_ts=2,
        phase="RISK",
        event="MAX_TRADES_REACHED",
        status="BLOCKED",
    )
    record_event(
        replay_db,
        dedupe_key="bar:1:GLOBAL:ELIGIBILITY:EG",
        closed_bar_ts=1,
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
    )

    client = TestClient(server.app)
    response = client.get(
        "/execution-timeline",
        params={
            "mode": "replay",
            "date": replay_date,
            "refresh": 5,
            "market_hours": "0",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert f"Replay {replay_date}" in body
    assert "EG_NOT_COINTEGRATED" in body
    assert "MAX_TRADES_REACHED" not in body
    assert 'http-equiv="refresh"' not in body
    assert 'name="mode"' in body
    assert 'value="replay" selected' in body
    assert f'name="date" value="{replay_date}"' in body
    assert f"mode=replay&amp;date={replay_date}" in body


def test_execution_timeline_html_replay_missing_db_is_friendly(tmp_path, monkeypatch):
    _timeline_db(tmp_path, monkeypatch)
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    monkeypatch.setattr(server, "REPLAY_DIR", str(replay_dir))

    client = TestClient(server.app)
    response = client.get(
        "/execution-timeline",
        params={"mode": "replay", "date": "2099-01-01", "refresh": 5},
    )

    assert response.status_code == 200
    body = response.text
    assert "Sem replay para esta data" in body
    assert "2099-01-01" in body
    assert 'http-equiv="refresh"' not in body


def test_execution_timeline_html_replay_bad_date_is_friendly(tmp_path, monkeypatch):
    _timeline_db(tmp_path, monkeypatch)
    client = TestClient(server.app)

    response = client.get(
        "/execution-timeline",
        params={"mode": "replay", "date": "../etc/passwd"},
    )

    assert response.status_code == 200
    body = response.text
    assert "Data de replay inválida" in body
    assert 'http-equiv="refresh"' not in body


def test_execution_timeline_html_replay_empty_date_prompts_user(tmp_path, monkeypatch):
    """Switching to replay without a date should prompt the user, not yell."""
    _timeline_db(tmp_path, monkeypatch)
    client = TestClient(server.app)

    response = client.get("/execution-timeline", params={"mode": "replay"})

    assert response.status_code == 200
    body = response.text
    assert "Escolha uma data" in body
    assert "Data de replay inválida" not in body
    assert 'http-equiv="refresh"' not in body


def test_execution_timeline_html_form_auto_submits_on_change(tmp_path, monkeypatch):
    """The filters form must auto-submit so toggling mode/date doesn't need Apply."""
    _timeline_db(tmp_path, monkeypatch)
    client = TestClient(server.app)

    response = client.get("/execution-timeline")

    assert response.status_code == 200
    body = response.text
    assert "form.submit()" in body
    assert "select[name=\"mode\"]" in body
    assert "input[name=\"date\"]" in body


def test_execution_timeline_html_replay_mode_shows_generate_button(tmp_path, monkeypatch):
    """Replay mode renders the 'Gerar replay' button bound to the chosen date."""
    _timeline_db(tmp_path, monkeypatch)
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    monkeypatch.setattr(server, "REPLAY_DIR", str(replay_dir))
    client = TestClient(server.app)

    response = client.get(
        "/execution-timeline",
        params={"mode": "replay", "date": "2026-05-08"},
    )

    assert response.status_code == 200
    body = response.text
    assert 'id="generate-replay-btn"' in body
    assert "Gerar replay" in body
    # date is set, so button must NOT be disabled in initial render
    assert 'id="generate-replay-btn" class="generate" disabled' not in body


def test_execution_timeline_generate_endpoint_invokes_run_replay(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(server, "REPLAY_DIR", str(tmp_path / "replays"))
    monkeypatch.setattr(server, "DB_PATH", str(tmp_path / "trades.db"))
    captured = {}

    def fake_run_replay(*, date_str, source_db, out_dir):
        captured["date_str"] = date_str
        captured["source_db"] = source_db
        captured["out_dir"] = out_dir
        return {
            "replay_date": date_str,
            "bars_total": 5,
            "bars_processed": 5,
            "bars_skipped_missing": 0,
        }

    import scripts.replay_execution_timeline as replay_mod
    monkeypatch.setattr(replay_mod, "run_replay", fake_run_replay)

    client = TestClient(server.app)
    response = client.post(
        "/api/execution-timeline/generate",
        params={"date": "2026-05-08"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["date"] == "2026-05-08"
    assert body["summary"]["bars_processed"] == 5
    assert captured["date_str"] == "2026-05-08"
    assert captured["source_db"] == server.DB_PATH
    assert captured["out_dir"] == server.REPLAY_DIR


def test_execution_timeline_generate_endpoint_rejects_bad_date(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REPLAY_DIR", str(tmp_path / "replays"))
    client = TestClient(server.app)

    response = client.post(
        "/api/execution-timeline/generate",
        params={"date": "../etc/passwd"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_REPLAY_DATE"

    response_missing = client.post("/api/execution-timeline/generate")
    # date is required by FastAPI signature → 422
    assert response_missing.status_code == 422


def test_execution_timeline_generate_endpoint_handles_replay_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(server, "REPLAY_DIR", str(tmp_path / "replays"))
    monkeypatch.setattr(server, "DB_PATH", str(tmp_path / "trades.db"))

    def boom(**_):
        raise RuntimeError("source DB missing")

    import scripts.replay_execution_timeline as replay_mod
    monkeypatch.setattr(replay_mod, "run_replay", boom)

    client = TestClient(server.app)
    response = client.post(
        "/api/execution-timeline/generate",
        params={"date": "2026-05-08"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "REPLAY_FAILED"
    assert "source DB missing" in body["message"]
    # Lock must be released even on failure — second call must not 409
    assert "2026-05-08" not in server._replay_in_progress


def test_execution_timeline_generate_endpoint_409_on_concurrent(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(server, "REPLAY_DIR", str(tmp_path / "replays"))
    monkeypatch.setattr(server, "DB_PATH", str(tmp_path / "trades.db"))

    # Pre-mark the date as in-progress to simulate a concurrent run.
    server._replay_in_progress.add("2026-05-08")
    try:
        client = TestClient(server.app)
        response = client.post(
            "/api/execution-timeline/generate",
            params={"date": "2026-05-08"},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "REPLAY_IN_PROGRESS"
    finally:
        server._replay_in_progress.discard("2026-05-08")


def test_trades_endpoint_returns_trades_for_date(monkeypatch):
    captured = {}

    class _StubEngine:
        def get_trades_for_date(self, date_str):
            captured["date"] = date_str
            return [{"id": 1, "direction": "BUY", "strategy": "CONS_BASE"}]

    monkeypatch.setattr(server, "_trade_engine", _StubEngine())
    client = TestClient(server.app)
    response = client.get("/api/trades", params={"date": "2026-05-08"})

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-05-08"
    assert body["trades"] == [{"id": 1, "direction": "BUY", "strategy": "CONS_BASE"}]
    assert captured["date"] == "2026-05-08"


def test_trades_endpoint_rejects_invalid_date(monkeypatch):
    class _StubEngine:
        def get_trades_for_date(self, date_str):
            raise AssertionError("must not be called for invalid date")

    monkeypatch.setattr(server, "_trade_engine", _StubEngine())
    client = TestClient(server.app)
    response = client.get("/api/trades", params={"date": "not-a-date"})

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_DATE"


def test_runtime_config_get_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        server.runtime_config, "CONFIG_PATH", tmp_path / "missing.json"
    )
    client = TestClient(server.app)
    response = client.get("/api/runtime-config")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"live", "replay"}
    assert body["live"]["eg_threshold"] == 0.10
    assert body["replay"]["eg_recalc"] == "daily"


def test_runtime_config_post_persists_and_returns_normalised(tmp_path, monkeypatch):
    target = tmp_path / "runtime.json"
    monkeypatch.setattr(server.runtime_config, "CONFIG_PATH", target)

    payload = {
        "live": {
            "eg_threshold": 0.05,
            "eg_bars": 250,
            "eg_recalc": "bar",
            "eg_strategies": ["CONS_BASE", "WDO_NWE"],
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
            "z_anomaly": 4.0,
        },
        "replay": {
            "eg_threshold": 0.10,
            "eg_bars": 2240,
            "eg_recalc": "daily",
            "eg_strategies": ["CONS_BASE", "WDO_NWE"],
            "rho_breakdown_level": 2,
            "beta_delta_max": 30.0,
            "z_anomaly": 4.0,
        },
    }
    client = TestClient(server.app)
    response = client.post("/api/runtime-config", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["live"]["eg_threshold"] == 0.05
    assert body["replay"]["eg_bars"] == 2240
    assert target.exists()

    # GET should now return what we just saved.
    follow_up = client.get("/api/runtime-config").json()
    assert follow_up == body


def test_runtime_config_post_rejects_invalid_payload(tmp_path, monkeypatch):
    target = tmp_path / "runtime.json"
    monkeypatch.setattr(server.runtime_config, "CONFIG_PATH", target)

    bad = {
        "live": {
            "eg_threshold": 0.10,
            "eg_bars": 10,  # below floor
            "eg_recalc": "bar",
            "eg_strategies": ["CONS_BASE", "WDO_NWE"],
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
            "z_anomaly": 4.0,
        },
        "replay": {
            "eg_threshold": 0.10,
            "eg_bars": 500,
            "eg_recalc": "daily",
            "eg_strategies": ["CONS_BASE", "WDO_NWE"],
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
            "z_anomaly": 4.0,
        },
    }
    client = TestClient(server.app)
    response = client.post("/api/runtime-config", json=bad)

    assert response.status_code == 400
    assert response.json()["error"] == "VALIDATION"
    assert not target.exists()


def test_runtime_config_post_rejects_invalid_json(tmp_path, monkeypatch):
    target = tmp_path / "runtime.json"
    monkeypatch.setattr(server.runtime_config, "CONFIG_PATH", target)

    client = TestClient(server.app)
    response = client.post(
        "/api/runtime-config",
        data="not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_JSON"


# ─── Slice D: live engine hot-reload of runtime profile ─────────────────────


def _live_profile(eg_recalc="bar", eg_bars=2240, eg_threshold=0.10):
    return {
        "eg_threshold": eg_threshold,
        "eg_bars": eg_bars,
        "eg_recalc": eg_recalc,
        "rho_breakdown_level": 2,
        "beta_delta_max": 25.0,
        "eg_strategies": ["CONS_BASE", "WDO_NWE"],
        "z_anomaly": 4.0,
    }


def test_compute_live_eg_pvalue_bar_mode_calls_through(monkeypatch):
    """eg_recalc='bar' just delegates to compute_engle_granger_pvalue."""
    server.reset_live_eg_daily_cache()
    calls = []

    def fake_eg(win, wdo, ts):
        calls.append((len(win), len(wdo), ts))
        return 0.05

    monkeypatch.setattr(server, "compute_engle_granger_pvalue", fake_eg)

    win = list(range(500))
    wdo = list(range(500))
    pv = server._compute_live_eg_pvalue(
        live_profile=_live_profile(eg_recalc="bar", eg_bars=100),
        win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_000_000, date_str="2026-05-08",
    )
    assert pv == 0.05
    # eg_bars=100 must trim the inputs before calling
    assert calls == [(100, 100, 1_700_000_000)]


def test_compute_live_eg_pvalue_daily_caches_first_pvalue(monkeypatch):
    """eg_recalc='daily' computes once per date_str, then reuses."""
    server.reset_live_eg_daily_cache()
    call_count = {"n": 0}

    def fake_eg(win, wdo, ts):
        call_count["n"] += 1
        return 0.07

    monkeypatch.setattr(server, "compute_engle_granger_pvalue", fake_eg)

    win = [1.0] * 300
    wdo = [2.0] * 300
    profile = _live_profile(eg_recalc="daily", eg_bars=100)

    # First poll on 05-08 → computes
    pv1 = server._compute_live_eg_pvalue(
        live_profile=profile, win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_000_000, date_str="2026-05-08",
    )
    # Subsequent polls on the same date → cached, no recompute
    pv2 = server._compute_live_eg_pvalue(
        live_profile=profile, win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_000_300, date_str="2026-05-08",
    )
    pv3 = server._compute_live_eg_pvalue(
        live_profile=profile, win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_000_600, date_str="2026-05-08",
    )
    assert pv1 == pv2 == pv3 == 0.07
    assert call_count["n"] == 1

    # New date → recomputes
    server._compute_live_eg_pvalue(
        live_profile=profile, win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_086_400, date_str="2026-05-09",
    )
    assert call_count["n"] == 2


def test_compute_live_eg_pvalue_daily_invalidates_when_eg_bars_changes(monkeypatch):
    """Mid-day hot-reload of eg_bars must recompute, not serve the stale value.

    Cache key is (date_str, eg_bars) — so flipping the window via
    /api/runtime-config invalidates the cached pvalue on the next poll
    without waiting for the next session.
    """
    server.reset_live_eg_daily_cache()
    pvalues = iter([0.07, 0.40])  # different windows → different pvalues

    def fake_eg(win, wdo, ts):
        return next(pvalues)

    monkeypatch.setattr(server, "compute_engle_granger_pvalue", fake_eg)
    win = [1.0] * 1000
    wdo = [2.0] * 1000

    pv1 = server._compute_live_eg_pvalue(
        live_profile=_live_profile(eg_recalc="daily", eg_bars=250),
        win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_000_000, date_str="2026-05-08",
    )
    pv2 = server._compute_live_eg_pvalue(
        live_profile=_live_profile(eg_recalc="daily", eg_bars=2240),
        win_closes=win, wdo_closes=wdo,
        bar_ts=1_700_000_300, date_str="2026-05-08",
    )
    assert pv1 == 0.07
    assert pv2 == 0.40  # not 0.07 — the change in eg_bars triggered recompute


def test_compute_live_eg_pvalue_daily_does_not_cache_none(monkeypatch):
    """A None pvalue (insufficient history) must retry on the next bar."""
    server.reset_live_eg_daily_cache()
    results = iter([None, 0.02])

    def fake_eg(win, wdo, ts):
        return next(results)

    monkeypatch.setattr(server, "compute_engle_granger_pvalue", fake_eg)
    profile = _live_profile(eg_recalc="daily", eg_bars=100)

    pv1 = server._compute_live_eg_pvalue(
        live_profile=profile, win_closes=[1] * 50, wdo_closes=[2] * 50,
        bar_ts=1, date_str="2026-05-08",
    )
    assert pv1 is None
    pv2 = server._compute_live_eg_pvalue(
        live_profile=profile, win_closes=[1] * 200, wdo_closes=[2] * 200,
        bar_ts=2, date_str="2026-05-08",
    )
    assert pv2 == 0.02


def test_live_engine_falls_back_to_defaults_when_runtime_config_invalid(
    tmp_path, monkeypatch,
):
    """A malformed runtime.json must not 500 the live engine — it falls back
    to DEFAULTS so every runtime field stays defined for the gate."""
    target = tmp_path / "runtime.json"
    target.write_text("not json{", encoding="utf-8")
    monkeypatch.setattr(server.runtime_config, "CONFIG_PATH", target)

    # Sanity: get_profile raises on this file.
    with pytest.raises(ValueError):
        server.runtime_config.get_profile("live")

    # The fallback path used in regime_v2 must produce a complete profile.
    fallback = copy.deepcopy(server.runtime_config.DEFAULTS["live"])
    for field in server.runtime_config.FIELDS:
        assert field in fallback
