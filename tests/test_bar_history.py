"""Tests for bar_history migration and save/load roundtrip.

Covers TASK-3 AC #2: idempotent CREATE TABLE, INSERT OR IGNORE dedup,
and date-window filtering in load_bar_history.
"""
import sqlite3
import time

import pytest

from server import init_bar_history, save_bar_history, load_bar_history


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
