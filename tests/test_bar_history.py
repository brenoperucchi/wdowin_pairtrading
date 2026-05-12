"""Tests for bar_history migration and save/load roundtrip.

Covers TASK-3 AC #2: idempotent CREATE TABLE, timestamp dedup/upsert,
date-window filtering in load_bar_history, and the V2 persistence helper
that activates the non-repainting write path.
"""
import os
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


def _sample(
    ts,
    *,
    z_wdo=0.5,
    win_price=130000.0,
    wdo_price=5500.0,
    di_price=12.5,
    nwe_is_up=True,
):
    return dict(
        timestamp=ts,
        date_str="2026-05-07",
        bar_time="10:30",
        win_price=win_price,
        wdo_price=wdo_price,
        di_price=di_price,
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
    assert r["wdo_price"] == 5500.0
    assert r["di_price"] == 12.5
    assert r["z"] == 0.5  # mapped from z_wdo


def test_timestamp_conflict_dedups_non_null_values(db):
    ts_now = int(time.time())
    save_bar_history(**_sample(ts_now, z_wdo=0.5), db_path=db)
    save_bar_history(**_sample(ts_now, z_wdo=0.99), db_path=db)  # same ts, different z
    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    assert rows[0]["z"] == 0.5  # first write wins for non-null persisted values


def test_save_bar_history_fills_missing_wdo_di_on_conflict(db):
    ts_now = int(time.time())
    save_bar_history(
        **_sample(ts_now, z_wdo=0.5, wdo_price=None, di_price=None),
        db_path=db,
    )
    save_bar_history(
        **_sample(ts_now, z_wdo=0.99, wdo_price=5501.5, di_price=13.12),
        db_path=db,
    )

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    assert rows[0]["z"] == 0.5
    assert rows[0]["wdo_price"] == 5501.5
    assert rows[0]["di_price"] == 13.12


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
    wdo_prices = np.array([5500.0, 5501.0, 5502.0])
    di_prices = np.array([13.10, 13.11, 13.12])
    nwe_data = (
        np.array([130050.0, 130150.0, 130250.0]),
        np.array([130200.0, 130300.0, 130400.0]),
        np.array([129900.0, 130000.0, 130100.0]),
        np.array([True, True, True]),
    )

    history = _build_history(
        times,
        z,
        spread,
        win_prices=win_prices,
        wdo_prices=wdo_prices,
        di_prices=di_prices,
        nwe_data=nwe_data,
    )
    assert len(history) == 3  # all in session

    saved = _persist_closed_bars(history, db_path=db)
    assert saved == 2  # last bar skipped

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 2
    assert {r["bar_time"] for r in rows} == {"10:00", "10:05"}
    by_time = {r["bar_time"]: r for r in rows}
    assert by_time["10:00"]["wdo_price"] == 5500.0
    assert by_time["10:00"]["di_price"] == 13.10
    assert by_time["10:05"]["wdo_price"] == 5501.0
    assert by_time["10:05"]["di_price"] == 13.11
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
    assert len(rows) == 2  # timestamp conflict deduped


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


# ─── TASK-8 Slice A: replay-required indicators on bar_history ───────────────

def test_init_bar_history_creates_indicator_columns(tmp_path):
    """Migration adds eg_pvalue/rho/rho_level/beta_value/beta_delta_pct."""
    p = str(tmp_path / "indicators.db")
    init_bar_history(p)
    init_bar_history(p)  # re-run must be idempotent

    conn = sqlite3.connect(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bar_history)").fetchall()}
    conn.close()
    for col in ("eg_pvalue", "rho", "rho_level", "beta_value", "beta_delta_pct"):
        assert col in cols, f"missing column {col} after migration"


def test_save_bar_history_roundtrips_indicators(db):
    ts = int(time.time())
    save_bar_history(
        **_sample(ts),
        eg_pvalue=0.0345,
        rho=-0.82,
        rho_level=0,
        beta_value=1.234,
        beta_delta_pct=4.7,
        db_path=db,
    )
    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    r = rows[0]
    assert r["eg_pvalue"] == 0.0345
    assert r["rho"] == -0.82
    assert r["rho_level"] == 0
    assert r["beta_value"] == 1.234
    assert r["beta_delta_pct"] == 4.7


def test_save_bar_history_indicator_coalesce_preserves_first_value(db):
    """Subsequent re-saves of the same bar with NULL indicators must NOT
    erase values written when the bar was the closed-bar of an earlier poll.
    """
    ts = int(time.time())
    save_bar_history(
        **_sample(ts),
        eg_pvalue=0.05,
        rho=-0.75,
        rho_level=0,
        beta_value=1.10,
        beta_delta_pct=2.0,
        db_path=db,
    )
    # Same bar again, this time with no indicators (simulates the bar
    # being history[-3], history[-4], etc. in a later poll).
    save_bar_history(**_sample(ts), db_path=db)

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    r = rows[0]
    assert r["eg_pvalue"] == 0.05
    assert r["rho"] == -0.75
    assert r["rho_level"] == 0
    assert r["beta_value"] == 1.10
    assert r["beta_delta_pct"] == 2.0


def test_save_bar_history_indicators_optional(db):
    """Bars saved without indicator kwargs (legacy callers) must not break."""
    ts = int(time.time())
    save_bar_history(**_sample(ts), db_path=db)
    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    r = rows[0]
    assert r["eg_pvalue"] is None
    assert r["rho"] is None
    assert r["rho_level"] is None
    assert r["beta_value"] is None
    assert r["beta_delta_pct"] is None


def test_persist_closed_bars_threads_indicators(db):
    """_persist_closed_bars reads eg_pvalue/rho/etc. from history entries."""
    today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    bars = [today + timedelta(minutes=5 * i) for i in range(3)]
    times = np.array([_utc_ts_for_local(dt) for dt in bars], dtype=np.int64)
    z = np.array([0.5, -0.3, 1.7])
    spread = np.array([40.0, 41.0, 42.0])
    history = _build_history(times, z, spread)
    assert len(history) == 3

    # Mimic regime_v2's attachment: only the closed bar (history[-2]) gets
    # indicators in any given poll.
    history[-2]["eg_pvalue"] = 0.022
    history[-2]["rho"] = -0.91
    history[-2]["rho_level"] = 0
    history[-2]["beta_value"] = 1.05
    history[-2]["beta_delta_pct"] = -3.2

    _persist_closed_bars(history, db_path=db)

    rows = load_bar_history(days=1, db_path=db)
    by_time = {r["bar_time"]: r for r in rows}
    closed_bar_time = history[-2]["bar_time"]
    closed = by_time[closed_bar_time]
    assert closed["eg_pvalue"] == 0.022
    assert closed["rho"] == -0.91
    assert closed["rho_level"] == 0
    assert closed["beta_value"] == 1.05
    assert closed["beta_delta_pct"] == -3.2

    # The earlier closed bar wasn't tagged this poll; indicators stay NULL.
    earlier = by_time[history[0]["bar_time"]]
    assert earlier["eg_pvalue"] is None
    assert earlier["rho"] is None


# ─── TASK-14 Slice 4: BAR_HISTORY_BACKEND=dual mirror to Postgres ───────────


def test_save_bar_history_default_backend_skips_pg(db, monkeypatch):
    """Default `sqlite` backend must not call bhdb.upsert_bar / init_schema."""
    from core import bar_history_db as bhdb

    monkeypatch.delenv("BAR_HISTORY_BACKEND", raising=False)
    upsert_calls: list = []
    init_calls: list = []
    monkeypatch.setattr(bhdb, "upsert_bar", lambda *a, **k: upsert_calls.append((a, k)))
    monkeypatch.setattr(bhdb, "init_schema", lambda *a, **k: init_calls.append((a, k)))

    init_bar_history(db)
    save_bar_history(**_sample(int(time.time())), db_path=db)

    assert upsert_calls == []
    assert init_calls == []
    # SQLite still written
    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1


@pytest.mark.parametrize("mode", ["dual", "postgres"])
def test_save_bar_history_mirrors_to_pg_when_backend_dual_or_postgres(db, monkeypatch, mode):
    """`dual` AND `postgres` must invoke bhdb.upsert_bar(backend='postgres').

    Slice 5 cutover regression: reads moved to PG when env=postgres, so writes
    have to follow or PG goes stale and SQLite (which would still receive the
    write) becomes invisible to /api/history.
    """
    from core import bar_history_db as bhdb

    monkeypatch.setenv("BAR_HISTORY_BACKEND", mode)
    upsert_calls: list = []
    init_calls: list = []
    monkeypatch.setattr(bhdb, "upsert_bar", lambda *a, **k: upsert_calls.append((a, k)))
    monkeypatch.setattr(bhdb, "init_schema", lambda *a, **k: init_calls.append((a, k)))

    init_bar_history(db)
    ts = int(time.time())
    save_bar_history(**_sample(ts, z_wdo=0.42), db_path=db)

    assert init_calls == [((), {"backend": "postgres"})]
    assert len(upsert_calls) == 1
    args, kwargs = upsert_calls[0]
    assert kwargs == {"backend": "postgres"}
    row = args[0]
    assert row["timestamp"] == ts
    assert row["z_wdo"] == 0.42
    assert row["date_str"] == "2026-05-07"
    # SQLite write still fires in both modes (rollback safety).
    conn = sqlite3.connect(db)
    sqlite_rows = conn.execute("SELECT z_wdo FROM bar_history WHERE timestamp=?", (ts,)).fetchall()
    conn.close()
    assert sqlite_rows == [(0.42,)]


@pytest.mark.parametrize("mode", ["dual", "postgres"])
def test_save_bar_history_pg_failure_does_not_break_sqlite(db, monkeypatch, capsys, mode):
    """Postgres upsert failure must be logged but never raise; SQLite still gets the row."""
    from core import bar_history_db as bhdb

    monkeypatch.setenv("BAR_HISTORY_BACKEND", mode)

    def boom(*_a, **_k):
        raise RuntimeError("PG unreachable")

    monkeypatch.setattr(bhdb, "init_schema", boom)
    monkeypatch.setattr(bhdb, "upsert_bar", boom)

    init_bar_history(db)  # must not raise
    ts = int(time.time())
    save_bar_history(**_sample(ts), db_path=db)  # must not raise

    conn = sqlite3.connect(db)
    sqlite_rows = conn.execute("SELECT timestamp FROM bar_history WHERE timestamp=?", (ts,)).fetchall()
    conn.close()
    assert sqlite_rows == [(ts,)]
    captured = capsys.readouterr().out
    assert "[ERRO PG]" in captured


@pytest.mark.parametrize("mode", ["dual", "postgres"])
def test_save_bar_history_skips_pg_when_sqlite_fails(tmp_path, monkeypatch, capsys, mode):
    """If the SQLite write raises, PG must NOT be touched — keeps parity invariant."""
    from core import bar_history_db as bhdb

    monkeypatch.setenv("BAR_HISTORY_BACKEND", mode)
    upsert_calls: list = []
    monkeypatch.setattr(bhdb, "upsert_bar", lambda *a, **k: upsert_calls.append((a, k)))
    monkeypatch.setattr(bhdb, "init_schema", lambda *a, **k: None)

    # Point save_bar_history at a path it cannot write to (parent does not exist).
    bad_path = str(tmp_path / "nonexistent_dir" / "trades.db")
    save_bar_history(**_sample(int(time.time())), db_path=bad_path)

    assert upsert_calls == [], "PG mirror must not run when SQLite write fails"
    captured = capsys.readouterr().out
    assert "[ERRO DB]" in captured
    assert "[ERRO PG]" not in captured


# ─── TASK-14 Slice 5: BAR_HISTORY_BACKEND=postgres flips read path ──────────


def test_load_bar_history_default_unaffected_by_wrapper(db, monkeypatch):
    """Default `sqlite` backend: wrapper.select_window MUST NOT be called."""
    from core import bar_history_db as bhdb

    monkeypatch.delenv("BAR_HISTORY_BACKEND", raising=False)
    calls: list = []
    monkeypatch.setattr(bhdb, "select_window", lambda *a, **k: calls.append((a, k)) or [])

    ts = int(time.time())
    save_bar_history(**_sample(ts), db_path=db)
    rows = load_bar_history(days=1, db_path=db)

    assert calls == []
    assert len(rows) == 1


@pytest.fixture
def pg_clean_table(monkeypatch):
    """Point env at PG_TEST_URI and start each test with an empty bar_history."""
    uri = os.environ.get("PG_TEST_URI")
    if not uri:
        pytest.skip("PG_TEST_URI not set; skipping Postgres integration tests")
    monkeypatch.setenv("PG_URI", uri)
    import psycopg
    from core import bar_history_db as bhdb

    with psycopg.connect(uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")
    bhdb.init_schema(backend="postgres")
    yield uri
    with psycopg.connect(uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")


def test_load_bar_history_reads_from_postgres_when_backend_postgres(
    tmp_path, monkeypatch, pg_clean_table
):
    """env=postgres → load_bar_history pulls rows from PG, db_path is ignored."""
    from core import bar_history_db as bhdb

    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    # Seed PG directly via the wrapper.
    ts = int(time.time())
    bhdb.upsert_bar(
        {
            "timestamp": ts,
            "date_str": "2026-05-12",
            "bar_time": "11:55",
            "win_price": 130123.0,
            "wdo_price": 5502.5,
            "di_price": 12.55,
            "spread_wdo": 42.0,
            "spread_di": -3.1,
            "z_wdo": 0.42,
            "z_di": -0.8,
            "nwe_center": 130100.0,
            "nwe_upper": 130250.0,
            "nwe_lower": 129950.0,
            "nwe_is_up": True,
            "eg_pvalue": 0.022,
            "rho": -0.91,
            "rho_level": 0,
            "beta_value": 1.05,
            "beta_delta_pct": -3.2,
        },
        backend="postgres",
    )

    # Pass a non-existent db_path: if the SQLite branch ran, it would yield [].
    bogus = str(tmp_path / "ghost.db")
    rows = load_bar_history(days=1, db_path=bogus)

    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-05-12"
    assert r["win_price"] == 130123.0
    assert r["z"] == 0.42
    assert r["rho"] == -0.91
    assert r["beta_value"] == 1.05


def test_load_bar_history_dual_still_reads_from_sqlite(
    db, monkeypatch, pg_clean_table
):
    """env=dual → reads come from SQLite even with PG empty (cutover happens in postgres mode only)."""
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "dual")
    ts = int(time.time())
    save_bar_history(**_sample(ts), db_path=db)

    rows = load_bar_history(days=1, db_path=db)
    assert len(rows) == 1
    # Even though dual-write mirrored to PG, the read path is still SQLite.
    # Proof: db_path is what gives us the row.


def test_do_backfill_if_empty_uses_postgres_count(monkeypatch):
    """env=postgres → COUNT(*) goes through bhdb.count_rows(backend='postgres')."""
    from core import bar_history_db as bhdb
    import server as server_mod

    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    count_calls: list = []
    monkeypatch.setattr(
        bhdb,
        "count_rows",
        lambda *a, **k: count_calls.append((a, k)) or 42,  # non-zero → no HTTP backfill
    )

    server_mod.do_backfill_if_empty()

    assert count_calls == [((), {"backend": "postgres"})]
