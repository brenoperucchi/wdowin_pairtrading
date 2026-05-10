import json
import sqlite3
from pathlib import Path

import scripts.wdowin_live_execution_smoke as smoke


def _args(tmp_path, *extra):
    return smoke._parse_args(
        [
            "--report-dir", str(tmp_path / "reports"),
            "--audit-dir", str(tmp_path / "audit"),
            *extra,
        ]
    )


def test_dry_run_uses_engine_path_and_writes_report(tmp_path):
    args = _args(tmp_path, "--dry-run", "--symbol", "WINM26", "--side", "BUY", "--volume", "1.0")

    code, report = smoke.run_smoke(args)

    assert code == 0
    assert report.classification == "dry_run_simulated"
    assert report.retcode == 10018
    assert report.retcode_name == "TRADE_RETCODE_MARKET_CLOSED"
    assert Path(report.report_file).exists()
    assert Path(report.audit_path).exists()
    assert report.order_payload == {
        "symbol": "WINM26",
        "action": "TRADE_ACTION_DEAL",
        "type": "ORDER_TYPE_BUY",
        "volume": 1.0,
        "price": 0.0,
        "deviation": 50,
        "magic": 770001,
        "comment": "CONS_BASE/CONSENSO",
        "type_time": "ORDER_TIME_GTC",
        "type_filling": "ORDER_FILLING_RETURN",
        "project_order_request": {
            "symbol": "WINM26",
            "side": "BUY",
            "volume": 1.0,
            "magic": 770001,
            "deviation": 50,
            "comment": "CONS_BASE/CONSENSO",
        },
    }

    assert [row["event"] for row in report.timeline_events] == [
        "BUY_WIN",
        "ORDER_REQUEST",
        "EXECUTION_REJECTED",
    ]
    conn = sqlite3.connect(report.audit_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM matador_ops").fetchone()[0] == 0
    finally:
        conn.close()

    saved = json.loads(Path(report.report_file).read_text(encoding="utf-8"))
    assert saved["schema"] == smoke.SCHEMA
    assert saved["classification"] == "dry_run_simulated"


def test_live_requires_ack_live_risk(tmp_path):
    args = _args(tmp_path, "--live", "--symbol", "WINM26")

    code, report = smoke.run_smoke(args)

    assert code == 2
    assert report.classification == "safety_abort"
    assert "--live requires --ack-live-risk" in report.notes
    assert Path(report.report_file).exists()


def test_live_market_closed_classification_through_engine(tmp_path, monkeypatch):
    args = _args(
        tmp_path,
        "--live",
        "--ack-live-risk",
        "--symbol",
        "WINM26",
        "--side",
        "SELL",
        "--volume",
        "1.0",
    )

    def fake_probe(_args, report):
        report.symbol_info = {
            "trade_mode": 4,
            "volume_min": 1.0,
            "volume_step": 1.0,
            "volume_max": 1000.0,
            "filling_mode": 2,
            "expiration_mode": 15,
        }
        report.symbol_tick = {"bid": 130000.0, "ask": 130005.0}
        report.mt5_last_error = [1, "Success"]
        return True, True, True

    def fake_send(symbol, side, volume, magic, deviation, comment):
        return {
            "ok": False,
            "ticket": None,
            "retcode": 10018,
            "message": "market closed",
            "price": None,
        }

    monkeypatch.setattr(smoke, "_connect_and_probe_mt5", fake_probe)
    monkeypatch.setattr(smoke.trade_engine_module, "send_market_order", fake_send)

    code, report = smoke.run_smoke(args)

    assert code == 0
    assert report.classification == "expected_market_closed"
    assert report.order_payload["type"] == "ORDER_TYPE_SELL"
    assert report.raw_response["retcode"] == 10018
    assert [row["event"] for row in report.timeline_events] == [
        "SELL_WIN",
        "ORDER_REQUEST",
        "EXECUTION_REJECTED",
    ]


def test_volume_validation_respects_min_max_and_step():
    info = {"volume_min": 1.0, "volume_step": 0.5, "volume_max": 10.0}

    assert smoke._volume_ok(1.0, info) is True
    assert smoke._volume_ok(1.5, info) is True
    assert smoke._volume_ok(0.5, info) is False
    assert smoke._volume_ok(1.25, info) is False
    assert smoke._volume_ok(11.0, info) is False
