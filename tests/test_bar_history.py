"""Tests for bar_history migration and save/load roundtrip.

Covers TASK-3 AC #2: idempotent CREATE TABLE, INSERT OR IGNORE dedup,
date-window filtering in load_bar_history, and the V2 persistence helper
that activates the non-repainting write path.
"""
import sqlite3
import time
from datetime import datetime, timedelta

import numpy as np
import pytest

from core.config import TIME_OFFSET
from server import (
    _build_history,
    _persist_closed_bars,
    init_bar_history,
    load_bar_history,
    save_bar_history,
)


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "test_bar_history.db"
    init_bar_history(str(p))
    return str(p)


def _sample(ts, *, z_wdo=0.5, win_price=130000.0, nwe_is_up=True):
    return dict(
        timestamp=ts,
        date_str="2026-05-07",
        bar_time="10:30",
        win_price=win_price,
        wdo_price=5500.0,
        di_price=12.5,
        spread_wdo=42.0,
        spread_di=-3.1,
        z_wdo=z_wdo,
        z_di=-0.8,
        nwe_center=130100.0,
        nwe_upper=130250.0,
        nwe_lower=129950.0,
        nwe_is_up=nwe_is_up,
    )


def test_init_bar_history_idempotent(tmp_path):
    p = str(tmp_path / "idemp.db")
    init_bar_history(p)
    init_bar_history(p)  # second call must not raise

    conn = sqlite3.connect(p)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bar_history)").fetchall()]
    conn.close()
    assert "timestamp" in cols
    assert "z_wdo" in cols
    assert "nwe_is_up" in cols


def test_save_load_roundtrip(db):
    ts_now = int(time.time())
    save_bar_history(**_sample(ts_now), db_path=db)
    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    r = rows[0]
    assert r["bar_time"] == "10:30"
    assert r["date"] == "2026-05-07"
    assert r["win_price"] == 130000.0
    assert r["z"] == 0.5  # mapped from z_wdo


def test_insert_or_ignore_dedups_on_timestamp(db):
    ts_now = int(time.time())
    save_bar_history(**_sample(ts_now, z_wdo=0.5), db_path=db)
    save_bar_history(**_sample(ts_now, z_wdo=0.99), db_path=db)  # same ts, different z
    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    assert rows[0]["z"] == 0.5  # first write wins (INSERT OR IGNORE)


def test_load_filters_by_days_window(db):
    now = int(time.time())
    old_ts = now - 5 * 86400  # 5 days ago
    save_bar_history(**{**_sample(old_ts), "bar_time": "09:00"}, db_path=db)
    save_bar_history(**{**_sample(now), "bar_time": "10:30"}, db_path=db)

    recent = load_bar_history(days=1, db_path=db)
    assert len(recent) == 1
    assert recent[0]["bar_time"] == "10:30"

    all_rows = load_bar_history(days=10, db_path=db)
    assert len(all_rows) == 2


def test_nwe_blocking_in_load_zeros_buy_when_nwe_up(db):
    """When nwe_is_up is True, negative z_wdo (buy signal) gets zeroed by load filter."""
    ts = int(time.time())
    # nwe_is_up=True → isBuyBlocked=True → negative z_wdo should be zeroed in sig_wdo
    save_bar_history(**_sample(ts, z_wdo=-2.0, nwe_is_up=True), db_path=db)
    rows = load_bar_history(days=1, db_path=db)
    assert rows[0]["sig_wdo"] == 0  # buy direction blocked
    assert rows[0]["z_raw_wdo"] == 0  # z zeroed too
    # Original value preserved in z_unfiltered_wdo
    assert rows[0]["z_unfiltered_wdo"] == -2.0


# ─── V2 persistence wiring (closes codex-flagged gap) ───────────────────────

def _utc_ts_for_local(dt: datetime) -> int:
    return int(dt.timestamp()) - TIME_OFFSET


def test_persist_closed_bars_skips_open_bar(db):
    """The last entry is the still-forming bar — must NOT be persisted."""
    today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    bars = [today + timedelta(minutes=5 * i) for i in range(3)]  # closed, closed, OPEN
    times = np.array([_utc_ts_for_local(dt) for dt in bars], dtype=np.int64)
    z = np.array([0.5, -0.3, 1.7])
    spread = np.array([40.0, 41.0, 42.0])
    win_prices = np.array([130000.0, 130100.0, 130200.0])
    nwe_data = (
        np.array([130050.0, 130150.0, 130250.0]),
        np.array([130200.0, 130300.0, 130400.0]),
        np.array([129900.0, 130000.0, 130100.0]),
        np.array([True, True, True]),
    )

    history = _build_history(times, z, spread, win_prices=win_prices, nwe_data=nwe_data)
    assert len(history) == 3  # all in session

    saved = _persist_closed_bars(history, db_path=db)
    assert saved == 2  # last bar skipped

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 2
    assert {r["bar_time"] for r in rows} == {"10:00", "10:05"}
    # Open bar at 10:10 must not be present
    assert "10:10" not in {r["bar_time"] for r in rows}


def test_persist_closed_bars_idempotent_across_polls(db):
    """Two consecutive polls (V2 fires every 2.5s) must not duplicate rows."""
    today = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
    bars = [today + timedelta(minutes=5 * i) for i in range(3)]
    times = np.array([_utc_ts_for_local(dt) for dt in bars], dtype=np.int64)
    z = np.array([0.1, 0.2, 0.3])
    spread = np.array([40.0, 41.0, 42.0])

    history = _build_history(times, z, spread)
    _persist_closed_bars(history, db_path=db)
    _persist_closed_bars(history, db_path=db)  # second poll, same bars

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 2  # INSERT OR IGNORE deduped


def test_persist_closed_bars_writes_unfiltered_z(db):
    """Persisted z_wdo must be the unfiltered value so load's NWE re-application
    is the single source of truth (avoid double-filtering)."""
    today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    bars = [today + timedelta(minutes=5 * i) for i in range(2)]
    times = np.array([_utc_ts_for_local(dt) for dt in bars], dtype=np.int64)
    z = np.array([-2.0, 0.0])  # first bar is a buy signal
    spread = np.array([42.0, 43.0])
    win_prices = np.array([130000.0, 130000.0])
    nwe_data = (
        np.array([130100.0, 130100.0]),
        np.array([130250.0, 130250.0]),
        np.array([129950.0, 129950.0]),
        np.array([True, True]),  # is_up → buy blocked in _build_history output
    )

    history = _build_history(times, z, spread, win_prices=win_prices, nwe_data=nwe_data)
    # In live history, the closed bar's filtered z is 0 but z_unfiltered_wdo is -2.0
    assert history[0]["z_raw_wdo"] == 0
    assert history[0]["z_unfiltered_wdo"] == -2.0

    _persist_closed_bars(history, db_path=db)

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    # load_bar_history re-applies NWE block; if we'd written 0, z_unfiltered would be 0 too.
    assert rows[0]["z_unfiltered_wdo"] == -2.0  # unfiltered preserved
    assert rows[0]["sig_wdo"] == 0  # filter still applied on read


def test_persist_closed_bars_handles_short_history(db):
    """Single-element history (only the open bar) must not write anything."""
    today = datetime.now().replace(hour=10, minute=30, second=0, microsecond=0)
    times = np.array([_utc_ts_for_local(today)], dtype=np.int64)
    z = np.array([0.5])
    spread = np.array([40.0])

    history = _build_history(times, z, spread)
    saved = _persist_closed_bars(history, db_path=db)
    assert saved == 0
    assert load_bar_history(days=1, db_path=db) == []


def test_midday_coldstart_does_not_shrink_history(db):
    """Reproduce codex round-2 finding: cold-start midday with empty DB.

    Before the fix, V2 fallback returned full history but persisted only
    live_history's 20-bar slice, so the next poll's merge branch shrank the
    dashboard. After the fix, persisting from the full `history` keeps the
    session intact across polls.

    This test exercises the V2 control flow inline (load_bar_history →
    _build_history fallback → persist → re-load → re-merge).
    """
    # 30 closed bars from 10:00 to 12:25 (5-min cadence) + 1 open bar at 12:30.
    today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    bars = [today + timedelta(minutes=5 * i) for i in range(31)]
    times = np.array([_utc_ts_for_local(dt) for dt in bars], dtype=np.int64)
    z = np.linspace(-1.0, 1.0, 31)
    spread = np.linspace(40.0, 50.0, 31)

    # Poll 1: cold start, DB empty.
    db_hist = load_bar_history(days=2, db_path=db)
    assert db_hist == []  # cold start
    live_history = _build_history(times[-20:], z[-20:], spread[-20:])
    history_poll1 = _build_history(times, z, spread)  # fallback branch
    assert len(history_poll1) == 31
    # NEW behavior: persist the FULL history, not just live_history.
    _persist_closed_bars(history_poll1, db_path=db)

    # Poll 2: same bar arrays (no new bar yet). DB now populated.
    db_hist2 = load_bar_history(days=2, db_path=db)
    today_str = today.strftime("%Y-%m-%d")
    db_hist2 = [h for h in db_hist2 if h.get("date") == today_str]
    assert len(db_hist2) == 30  # 30 closed bars persisted, open bar skipped

    live_history2 = _build_history(times[-20:], z[-20:], spread[-20:])
    # Merge logic from V2:
    last_db_ts = db_hist2[-1]["date"] + " " + db_hist2[-1]["bar_time"]
    for lh in live_history2:
        lh_ts = lh["date"] + " " + lh["bar_time"]
        if lh_ts > last_db_ts:
            db_hist2.append(lh)
    history_poll2 = db_hist2

    # Regression assertion: dashboard must NOT shrink.
    assert len(history_poll2) == 31, (
        f"history shrank from 31 to {len(history_poll2)} between polls"
    )
    assert history_poll2[0]["bar_time"] == "10:00"
    assert history_poll2[-1]["bar_time"] == "12:30"
