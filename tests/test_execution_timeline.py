"""Tests for core/execution_timeline.py — TASK-4.1 (Slice A).

Schema is idempotent, distance/ratio compute correctly, dedupe is enforced
via UNIQUE INDEX + INSERT OR IGNORE, filtering works, and bottleneck/live-issue
selectors honour the funnel order.
"""
import json
import sqlite3

import pytest

from core import execution_timeline as et
from core.trade_engine import TradeEngine


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "timeline.db")
    et.init_timeline_table(path)
    return path


# ─── schema ──────────────────────────────────────────────────────────────────

def test_init_timeline_table_is_idempotent(tmp_path):
    path = str(tmp_path / "t.db")
    et.init_timeline_table(path)
    et.init_timeline_table(path)  # must not raise
    conn = sqlite3.connect(path)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='execution_timeline'"
        ).fetchall()}
    finally:
        conn.close()
    assert "ux_timeline_dedupe" in names
    assert "ix_timeline_ts" in names
    assert "ix_timeline_bar_phase" in names


def test_trade_engine_init_db_enables_wal(tmp_path):
    """TradeEngine._init_db must set journal_mode=WAL."""
    path = str(tmp_path / "trades.db")
    TradeEngine(path)
    conn = sqlite3.connect(path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


# ─── distance / ratio ────────────────────────────────────────────────────────

def test_record_event_computes_distance_and_ratio_for_gt_operator(db):
    rowid = et.record_event(
        db,
        closed_bar_ts=1778243100,
        correlation_id="bar:1778243100:CONS_BASE",
        dedupe_key="bar:1778243100:CONS_BASE:ELIGIBILITY:EG_NOT_COINTEGRATED",
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
        severity="structural_block",
        strategy="CONS_BASE",
        metric="eg_pvalue",
        value=0.64,
        threshold=0.10,
        operator=">",
    )
    assert rowid is not None
    rows = et.load_timeline(db, limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["distance"] == pytest.approx(0.54)
    assert row["ratio_to_threshold"] == pytest.approx(6.4)


def test_record_event_distance_for_lt_operator_is_inverted(db):
    et.record_event(
        db,
        dedupe_key="bar:1:CONS_BASE:RISK:RHO_BREAKDOWN",
        phase="RISK",
        event="RHO_BREAKDOWN",
        status="BLOCKED",
        metric="rho",
        value=-0.30,
        threshold=-0.40,
        operator="<",
    )
    rows = et.load_timeline(db, limit=1)
    # gate is "block when rho > -0.40"; with operator "<" interpreted as
    # "open while value < threshold", value -0.30 vs threshold -0.40 →
    # threshold - value = -0.40 - (-0.30) = -0.10  (closed/blocked side)
    assert rows[0]["distance"] == pytest.approx(-0.10)


# ─── dedupe ──────────────────────────────────────────────────────────────────

def test_record_event_dedupe_key_collision_returns_none(db):
    key = "bar:1:CONS_BASE:ELIGIBILITY:EG_NOT_COINTEGRATED"
    first = et.record_event(
        db,
        dedupe_key=key,
        closed_bar_ts=1,
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
        strategy="CONS_BASE",
    )
    second = et.record_event(
        db,
        dedupe_key=key,
        closed_bar_ts=1,
        phase="ELIGIBILITY",
        event="EG_NOT_COINTEGRATED",
        status="BLOCKED",
        strategy="CONS_BASE",
    )
    assert first is not None
    assert second is None
    rows = et.load_timeline(db, limit=10)
    assert len(rows) == 1


# ─── bulk + payload_json ─────────────────────────────────────────────────────

def test_bulk_record_events_in_single_transaction(db):
    events = [
        {
            "dedupe_key": f"bar:1:CONS_BASE:ELIGIBILITY:E{i}",
            "closed_bar_ts": 1,
            "phase": "ELIGIBILITY",
            "event": f"E{i}",
            "status": "BLOCKED",
            "strategy": "CONS_BASE",
        }
        for i in range(3)
    ]
    ids = et.bulk_record_events(db, events)
    assert all(i is not None for i in ids)
    assert len(et.load_timeline(db, limit=10)) == 3


def test_bulk_record_events_payload_dict_serialised_as_json(db):
    payload = {"ticket": 111222, "price": 130000.0, "retcode": 10009}
    et.bulk_record_events(
        db,
        [
            {
                "dedupe_key": "trade:7:EXECUTION:EXECUTION_FILLED:abc",
                "trade_id": 7,
                "phase": "EXECUTION",
                "event": "EXECUTION_FILLED",
                "status": "OK",
                "payload_json": payload,
            }
        ],
    )
    rows = et.load_timeline(db, limit=1)
    assert json.loads(rows[0]["payload_json"]) == payload


# ─── load_timeline filters ───────────────────────────────────────────────────

def test_load_timeline_filters(db):
    base = [
        ("bar:1:CONS_BASE:ELIGIBILITY:EG", "ELIGIBILITY", "EG_NOT_COINTEGRATED",
         "BLOCKED", "CONS_BASE", 1, "2026-05-08T10:00:00"),
        ("bar:1:WDO_NWE:RISK:MAX_TRADES", "RISK", "MAX_TRADES_REACHED",
         "BLOCKED", "WDO_NWE", 1, "2026-05-08T10:01:00"),
        ("bar:2:CONS_BASE:INDICATORS:OK", "INDICATORS", "INDICATORS_OK",
         "OK", "CONS_BASE", 2, "2026-05-08T10:05:00"),
    ]
    et.bulk_record_events(
        db,
        [
            {
                "dedupe_key": k, "phase": p, "event": e, "status": s,
                "strategy": strat, "closed_bar_ts": bar, "timestamp": ts,
            }
            for k, p, e, s, strat, bar, ts in base
        ],
    )

    by_phase = et.load_timeline(db, phase="ELIGIBILITY")
    assert [r["event"] for r in by_phase] == ["EG_NOT_COINTEGRATED"]

    by_status = et.load_timeline(db, status="BLOCKED")
    assert {r["event"] for r in by_status} == {"EG_NOT_COINTEGRATED", "MAX_TRADES_REACHED"}

    by_strategy = et.load_timeline(db, strategy="WDO_NWE")
    assert [r["event"] for r in by_strategy] == ["MAX_TRADES_REACHED"]

    by_event = et.load_timeline(db, event="INDICATORS_OK")
    assert len(by_event) == 1

    since = et.load_timeline(db, since="2026-05-08T10:04:00")
    assert {r["event"] for r in since} == {"INDICATORS_OK"}

    limited = et.load_timeline(db, limit=1)
    assert len(limited) == 1
    # newest-first ordering
    assert limited[0]["event"] == "INDICATORS_OK"


# ─── current_bottleneck ──────────────────────────────────────────────────────

def test_current_bottleneck_picks_first_blocked_in_funnel_order(db):
    # bar 1: SIGNAL blocked AND ELIGIBILITY blocked — funnel says ELIGIBILITY
    # comes first.
    events = [
        {
            "dedupe_key": "bar:1:CONS_BASE:SIGNAL:HMM_BLOCKED",
            "closed_bar_ts": 1,
            "phase": "SIGNAL",
            "event": "HMM_BLOCKED",
            "status": "BLOCKED",
            "strategy": "CONS_BASE",
        },
        {
            "dedupe_key": "bar:1:CONS_BASE:ELIGIBILITY:EG",
            "closed_bar_ts": 1,
            "phase": "ELIGIBILITY",
            "event": "EG_NOT_COINTEGRATED",
            "status": "BLOCKED",
            "strategy": "CONS_BASE",
        },
    ]
    et.bulk_record_events(db, events)
    bot = et.current_bottleneck(db)
    assert bot is not None
    assert bot["phase"] == "ELIGIBILITY"
    assert bot["event"] == "EG_NOT_COINTEGRATED"


def test_current_bottleneck_uses_latest_bar_only(db):
    # Old bar 1 has a block; new bar 2 has only OK events.
    et.bulk_record_events(
        db,
        [
            {
                "dedupe_key": "bar:1:CONS_BASE:ELIGIBILITY:EG",
                "closed_bar_ts": 1,
                "phase": "ELIGIBILITY",
                "event": "EG_NOT_COINTEGRATED",
                "status": "BLOCKED",
                "strategy": "CONS_BASE",
            },
            {
                "dedupe_key": "bar:2:CONS_BASE:INDICATORS:OK",
                "closed_bar_ts": 2,
                "phase": "INDICATORS",
                "event": "INDICATORS_OK",
                "status": "OK",
                "strategy": "CONS_BASE",
            },
        ],
    )
    assert et.current_bottleneck(db) is None  # latest bar passed clean


def test_current_bottleneck_none_when_no_closed_bar_events(db):
    # only a critical live event (closed_bar_ts NULL)
    et.record_event(
        db,
        dedupe_key="crit:DATA:MT5_DISCONNECTED:202605081200",
        phase="DATA",
        event="MT5_DISCONNECTED",
        status="FAILED",
        severity="error",
    )
    assert et.current_bottleneck(db) is None


# ─── current_live_issue ──────────────────────────────────────────────────────

def test_current_live_issue_returns_latest_failed_without_bar(db):
    et.bulk_record_events(
        db,
        [
            {
                "dedupe_key": "crit:DATA:MT5_DISCONNECTED:1",
                "phase": "DATA",
                "event": "MT5_DISCONNECTED",
                "status": "FAILED",
                "timestamp": "2026-05-08T10:00:00",
            },
            {
                "dedupe_key": "crit:DATA:BARS_FETCH_FAILED:1",
                "phase": "DATA",
                "event": "BARS_FETCH_FAILED",
                "status": "FAILED",
                "timestamp": "2026-05-08T10:05:00",
            },
            # Closed-bar event should not surface here
            {
                "dedupe_key": "bar:1:CONS_BASE:ELIGIBILITY:EG",
                "closed_bar_ts": 1,
                "phase": "ELIGIBILITY",
                "event": "EG_NOT_COINTEGRATED",
                "status": "BLOCKED",
            },
        ],
    )
    issue = et.current_live_issue(db)
    assert issue is not None
    assert issue["event"] == "BARS_FETCH_FAILED"


def test_current_live_issue_none_when_no_critical_failures(db):
    et.record_event(
        db,
        dedupe_key="bar:1:CONS_BASE:INDICATORS:OK",
        closed_bar_ts=1,
        phase="INDICATORS",
        event="INDICATORS_OK",
        status="OK",
    )
    assert et.current_live_issue(db) is None


# ─── validation ──────────────────────────────────────────────────────────────

def test_record_event_requires_dedupe_key(db):
    with pytest.raises(ValueError):
        et.record_event(db, phase="ELIGIBILITY", event="X", status="BLOCKED")


def test_record_event_requires_phase_event_status(db):
    with pytest.raises(ValueError):
        et.record_event(db, dedupe_key="k1", event="X", status="OK")
    with pytest.raises(ValueError):
        et.record_event(db, dedupe_key="k2", phase="DATA", status="OK")
    with pytest.raises(ValueError):
        et.record_event(db, dedupe_key="k3", phase="DATA", event="X")
