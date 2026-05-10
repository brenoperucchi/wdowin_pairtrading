"""Tests for scripts/replay_execution_timeline.py.

Covers TASK-8.2 AC #9 (fixture-driven happy/missing paths) and AC #6 (no
MetaTrader5 import).
"""
import hashlib
import os
import sqlite3
import sys
import time

import pytest

from scripts.replay_execution_timeline import (
    REQUIRED_BAR_FIELDS,
    ReplayStats,
    _process_bar,
    run_replay,
)
from core.config import BUY_TP
from core.execution_timeline import record_event
from core.trade_engine import TradeEngine
from server import init_bar_history, save_bar_history


REPLAY_DATE = "2026-05-07"


def _seed_bar(
    db_path: str,
    *,
    bar_time: str,
    ts: int,
    win_price=130000.0,
    wdo_price=5500.0,
    di_price=12.5,
    z_wdo=0.4,
    z_di=-0.6,
    eg_pvalue=0.04,
    rho=-0.85,
    rho_level=0,
    beta_value=23.5,
    beta_delta_pct=2.0,
):
    save_bar_history(
        timestamp=ts,
        date_str=REPLAY_DATE,
        bar_time=bar_time,
        win_price=win_price,
        wdo_price=wdo_price,
        di_price=di_price,
        spread_wdo=42.0,
        spread_di=-3.1,
        z_wdo=z_wdo,
        z_di=z_di,
        nwe_center=130100.0,
        nwe_upper=130250.0,
        nwe_lower=129950.0,
        nwe_is_up=True,
        eg_pvalue=eg_pvalue,
        rho=rho,
        rho_level=rho_level,
        beta_value=beta_value,
        beta_delta_pct=beta_delta_pct,
        db_path=db_path,
    )


def _ts_for(bar_time: str) -> int:
    """Stable epoch for a HH:MM on REPLAY_DATE."""
    return int(time.mktime(time.strptime(f"{REPLAY_DATE} {bar_time}", "%Y-%m-%d %H:%M")))


def _events(replay_db: str, **filters) -> list[dict]:
    conn = sqlite3.connect(replay_db)
    conn.row_factory = sqlite3.Row
    where = []
    params: list = []
    for k, v in filters.items():
        where.append(f"{k} = ?")
        params.append(v)
    sql = "SELECT * FROM execution_timeline"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def source_db(tmp_path):
    p = tmp_path / "source.db"
    init_bar_history(str(p))
    return str(p)


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "replays"
    d.mkdir()
    return str(d)


# ─── Happy path ─────────────────────────────────────────────────────────────

def test_replay_valid_day_emits_full_funnel(source_db, out_dir):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"))
    _seed_bar(source_db, bar_time="10:05", ts=_ts_for("10:05"), z_wdo=-0.2)

    summary = run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")
    assert os.path.exists(replay_db)

    assert summary["bars_total"] == 2
    assert summary["bars_processed"] == 2
    assert summary["bars_skipped_missing"] == 0
    assert summary["missing_by_field"] == {}

    indicators = _events(replay_db, phase="INDICATORS", event="INDICATORS_OK")
    assert len(indicators) == 2

    # Each bar emits one INDICATORS_OK + one SIGNAL row per strategy
    # (3 strategies × WAIT or SKIPPED). At minimum we want 2*3 SIGNAL rows.
    signals = _events(replay_db, phase="SIGNAL")
    assert len(signals) >= 6

    # META event written at end
    meta = _events(replay_db, event="REPLAY_SUMMARY")
    assert len(meta) == 1
    assert meta[0]["timestamp"].startswith(f"{REPLAY_DATE}T10:05")

    assert [
        (r["phase"], r["event"], r["status"], r["strategy"])
        for r in _events(replay_db)
    ] == [
        ("INDICATORS", "INDICATORS_OK", "OK", None),
        ("SIGNAL", "WAIT", "INFO", "CONS_BASE"),
        ("SIGNAL", "WAIT", "INFO", "WDO_NWE"),
        ("SIGNAL", "WAIT", "INFO", "DI_NWE"),
        ("INDICATORS", "INDICATORS_OK", "OK", None),
        ("SIGNAL", "WAIT", "INFO", "CONS_BASE"),
        ("SIGNAL", "WAIT", "INFO", "WDO_NWE"),
        ("SIGNAL", "WAIT", "INFO", "DI_NWE"),
        ("EXIT", "REPLAY_SUMMARY", "OK", None),
    ]


def test_replay_uses_bar_clock_for_trades_and_pnl(source_db, out_dir):
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        z_wdo=-2.1,
        z_di=-1.5,
    )
    _seed_bar(
        source_db,
        bar_time="10:05",
        ts=_ts_for("10:05"),
        win_price=130000.0 + BUY_TP,
        z_wdo=0.0,
        z_di=0.0,
    )

    summary = run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")

    assert summary["trades_opened"] == 1
    assert summary["trades_closed"] == 1
    assert summary["pnl_paper_brl"] > 0

    conn = sqlite3.connect(replay_db)
    row = conn.execute(
        "SELECT timestamp_in, timestamp_out FROM matador_ops WHERE status='CLOSED'"
    ).fetchone()
    timeline_rows = conn.execute(
        "SELECT event, timestamp FROM execution_timeline "
        "WHERE event IN ('BUY_WIN', 'TARGET') ORDER BY id"
    ).fetchall()
    conn.close()
    assert row is not None
    assert row[0].startswith(f"{REPLAY_DATE}T10:00")
    assert row[1].startswith(f"{REPLAY_DATE}T10:05")
    assert {r[0] for r in timeline_rows} == {"BUY_WIN", "TARGET"}
    assert all(r[1].startswith(REPLAY_DATE) for r in timeline_rows)


def test_replay_counts_open_trade_once_while_holding(source_db, out_dir):
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        z_wdo=-2.1,
        z_di=-1.5,
    )
    _seed_bar(
        source_db,
        bar_time="10:05",
        ts=_ts_for("10:05"),
        z_wdo=0.0,
        z_di=0.0,
    )

    summary = run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")

    assert summary["trades_opened"] == 1
    assert summary["trades_closed"] == 0

    conn = sqlite3.connect(replay_db)
    n_open = conn.execute("SELECT COUNT(*) FROM matador_ops WHERE status='OPEN'").fetchone()[0]
    conn.close()
    assert n_open == 1


# ─── Missing-field paths ────────────────────────────────────────────────────

def test_replay_missing_di_price_emits_missing_event(source_db, out_dir):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"), di_price=None)

    summary = run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")

    assert summary["bars_processed"] == 0
    assert summary["bars_skipped_missing"] == 1
    assert summary["missing_by_field"].get("di_price") == 1

    miss = _events(replay_db, phase="DATA", event="MISSING_DI_PRICE")
    assert len(miss) == 1
    assert miss[0]["status"] == "FAILED"

    # No funnel for the skipped bar
    assert _events(replay_db, phase="INDICATORS") == []


def test_replay_missing_eg_pvalue_emits_missing_event(source_db, out_dir):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"), eg_pvalue=None)

    summary = run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")

    assert summary["bars_skipped_missing"] == 1
    assert summary["missing_by_field"].get("eg_pvalue") == 1

    miss = _events(replay_db, phase="DATA", event="MISSING_EG_PVALUE")
    assert len(miss) == 1


def test_replay_corrupt_timestamp_emits_missing_timestamp(tmp_path):
    replay_db = str(tmp_path / "replay.db")
    engine = TradeEngine(db_path=replay_db)
    stats = ReplayStats(bars_total=1)

    row = {
        "timestamp": "bad-ts",
        "date_str": REPLAY_DATE,
        "bar_time": "10:00",
        "win_price": 130000.0,
        "wdo_price": 5500.0,
        "di_price": 12.5,
        "z_wdo": 0.1,
        "z_di": 0.2,
        "nwe_upper": 130250.0,
        "nwe_lower": 129950.0,
        "nwe_is_up": 1,
        "eg_pvalue": 0.04,
        "rho": -0.85,
        "rho_level": 0,
        "beta_value": 23.5,
        "beta_delta_pct": 2.0,
    }

    _process_bar(row, engine=engine, replay_db=replay_db, stats=stats)

    assert stats.bars_processed == 0
    assert stats.bars_skipped_missing == 1
    assert stats.missing_by_field.get("timestamp") == 1

    miss = _events(replay_db, phase="DATA", event="MISSING_TIMESTAMP")
    assert len(miss) == 1
    assert miss[0]["timestamp"].startswith(f"{REPLAY_DATE}T10:00")
    assert miss[0]["closed_bar_ts"] is None


def test_replay_required_fields_match_ac(source_db):
    # Sanity check that AC #5's listed fields are exactly what the replay enforces.
    assert set(REQUIRED_BAR_FIELDS) == {
        "win_price", "wdo_price", "di_price",
        "eg_pvalue", "rho", "rho_level",
        "beta_value", "beta_delta_pct",
    }


# ─── No-MT5 guarantee ───────────────────────────────────────────────────────

def test_replay_does_not_import_metatrader5(source_db, out_dir, monkeypatch):
    """AC #6: replay must not invoke or import MetaTrader5.

    conftest.py pre-loads a stub. We tag the stub with a sentinel and then
    assert the sentinel survives the replay — proof that no real-module
    reload happened. (A real `import MetaTrader5` would replace the stub
    via the sys.modules cache only if the stub were popped; tagging is
    the more robust signal.)
    """
    mt5_stub = sys.modules.get("MetaTrader5")
    assert mt5_stub is not None, "conftest.py should have stubbed MetaTrader5"
    sentinel = "__replay_sentinel__"
    monkeypatch.setattr(mt5_stub, sentinel, "untouched", raising=False)

    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"))
    run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)

    after = sys.modules.get("MetaTrader5")
    assert after is mt5_stub, "MetaTrader5 module identity must not change during replay"
    assert getattr(after, sentinel, None) == "untouched"


def test_replay_never_calls_mt5_order_send(source_db, out_dir, monkeypatch):
    mt5_stub = sys.modules.get("MetaTrader5")
    assert mt5_stub is not None, "conftest.py should have stubbed MetaTrader5"
    calls = []

    def spy_order_send(request):
        calls.append(request)
        raise AssertionError("replay must not call mt5.order_send")

    monkeypatch.setattr(mt5_stub, "order_send", spy_order_send, raising=False)

    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        z_wdo=-2.1,
        z_di=-1.5,
    )
    run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)

    assert calls == []


# ─── Source-DB integrity ────────────────────────────────────────────────────

def test_replay_does_not_mutate_source_db(source_db, out_dir):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"))
    before_hash = _sha256(source_db)
    before_mtime = os.path.getmtime(source_db)
    before_size = os.path.getsize(source_db)

    run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)

    after_hash = _sha256(source_db)
    after_mtime = os.path.getmtime(source_db)
    after_size = os.path.getsize(source_db)
    assert after_hash == before_hash
    assert after_mtime == before_mtime
    assert after_size == before_size


def test_replay_three_consecutive_runs_keep_source_db_hash_intact(source_db, out_dir):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"))
    _seed_bar(source_db, bar_time="10:05", ts=_ts_for("10:05"), z_wdo=-0.2)
    before_hash = _sha256(source_db)
    before_mtime = os.path.getmtime(source_db)

    for _ in range(3):
        run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)

    assert _sha256(source_db) == before_hash
    assert os.path.getmtime(source_db) == before_mtime


def test_replay_rerun_recreates_output_db(source_db, out_dir):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"))
    run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")

    record_event(
        replay_db,
        dedupe_key="stale:event",
        phase="DATA",
        event="STALE_EVENT",
        status="FAILED",
    )
    assert _events(replay_db, event="STALE_EVENT")

    run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)
    assert _events(replay_db, event="STALE_EVENT") == []
