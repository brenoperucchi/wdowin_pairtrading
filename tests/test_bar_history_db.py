"""Unit tests for core/bar_history_db.py (TASK-14 Slice 2).

The SQLite tests always run. The Postgres tests opt in via the
``PG_TEST_URI`` env var (e.g.
``postgresql://pairtrading:pairtrading_dev@127.0.0.1:5432/pairtrading_test``);
they are skipped cleanly when the var is absent so the default suite
remains portable on machines without Postgres/TimescaleDB.

Dual-mode tests require BOTH backends and skip if either is unavailable.
"""

from __future__ import annotations

import os
import time

import pytest

from core import bar_history_db as bhdb


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sqlite_env(tmp_path, monkeypatch):
    """Point BAR_HISTORY_SQLITE_PATH at a per-test temp DB and init schema."""
    db_path = tmp_path / "bar_history.db"
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "sqlite")
    monkeypatch.setenv("BAR_HISTORY_SQLITE_PATH", str(db_path))
    bhdb.init_schema()
    yield db_path


@pytest.fixture
def pg_uri():
    uri = os.environ.get("PG_TEST_URI")
    if not uri:
        pytest.skip("PG_TEST_URI not set; skipping Postgres integration tests")
    return uri


@pytest.fixture
def postgres_env(pg_uri, monkeypatch):
    """Clean Postgres bar_history schema and point PG_URI at the test DB."""
    monkeypatch.setenv("PG_URI", pg_uri)
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    # Drop & recreate so each test starts from an empty table.
    import psycopg

    with psycopg.connect(pg_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")
    bhdb.init_schema()
    yield pg_uri
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")


@pytest.fixture
def dual_env(tmp_path, pg_uri, monkeypatch):
    """Dual mode: both backends primed, env points at both."""
    db_path = tmp_path / "bar_history_dual.db"
    monkeypatch.setenv("BAR_HISTORY_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("PG_URI", pg_uri)
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "dual")
    import psycopg

    with psycopg.connect(pg_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")
    bhdb.init_schema()
    yield {"sqlite_path": str(db_path), "pg_uri": pg_uri}
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")


# ── Sample data ─────────────────────────────────────────────────────────────


def _bar(ts: int, **overrides) -> dict:
    base = dict(
        timestamp=ts,
        date_str="2026-05-12",
        bar_time="10:30",
        win_price=130_000.0,
        wdo_price=5_500.0,
        di_price=12.5,
        spread_wdo=42.0,
        spread_di=-3.1,
        z_wdo=0.5,
        z_di=-0.8,
        nwe_center=130_100.0,
        nwe_upper=130_250.0,
        nwe_lower=129_950.0,
        nwe_is_up=True,
        eg_pvalue=0.04,
        rho=-0.82,
        rho_level=0,
        beta_value=1.23,
        beta_delta_pct=4.7,
    )
    base.update(overrides)
    return base


_OHLC_KEYS = (
    "win_open", "win_high", "win_low",
    "wdo_open", "wdo_high", "wdo_low",
    "di_open", "di_high", "di_low",
)


def _bar_with_ohlc(ts: int, **overrides) -> dict:
    base = _bar(
        ts,
        win_open=130_010.0, win_high=130_180.0, win_low=129_870.0,
        wdo_open=5_505.0, wdo_high=5_520.0, wdo_low=5_490.0,
        di_open=12.55, di_high=12.62, di_low=12.48,
    )
    base.update(overrides)
    return base


# ── Backend resolution ──────────────────────────────────────────────────────


def test_get_backend_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("BAR_HISTORY_BACKEND", raising=False)
    assert bhdb.get_backend() == "sqlite"


def test_get_backend_reads_env(monkeypatch):
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "POSTGRES")
    assert bhdb.get_backend() == "postgres"


def test_read_backend_dual_reads_sqlite(monkeypatch):
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "dual")
    assert bhdb._read_backend(None) == "sqlite"


def test_pg_uri_missing_raises(monkeypatch):
    monkeypatch.delenv("PG_URI", raising=False)
    with pytest.raises(RuntimeError, match="PG_URI"):
        bhdb._pg_uri()


def test_update_columns_rejects_unknown_column(sqlite_env):
    with pytest.raises(ValueError, match="unknown bar_history column"):
        bhdb.update_columns(1_700_000_000, not_a_column=1.0)


# ── SQLite backend ──────────────────────────────────────────────────────────


def test_sqlite_init_schema_idempotent(sqlite_env):
    bhdb.init_schema()
    bhdb.init_schema()  # second call must not raise
    # Sanity: table is queryable and empty.
    assert bhdb.count_rows() == 0


def test_sqlite_upsert_roundtrip(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts))
    rows = bhdb.select_by_date("2026-05-12")
    assert len(rows) == 1
    r = rows[0]
    assert r["timestamp"] == ts
    assert r["win_price"] == 130_000.0
    assert r["z_wdo"] == 0.5
    assert r["z_di"] == -0.8
    assert r["eg_pvalue"] == 0.04
    assert r["nwe_is_up"] == 1


def test_sqlite_upsert_preserves_existing_indicators(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts, eg_pvalue=0.04, rho=-0.82, beta_value=1.23))
    bhdb.upsert_bar(_bar(ts, eg_pvalue=None, rho=None, beta_value=None))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["eg_pvalue"] == 0.04
    assert r["rho"] == -0.82
    assert r["beta_value"] == 1.23


def test_sqlite_upsert_z_di_overwrites_when_new_value_present(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts, z_di=-0.8))
    bhdb.upsert_bar(_bar(ts, z_di=1.42))  # new non-NULL → must overwrite
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["z_di"] == 1.42


def test_sqlite_upsert_z_di_keeps_old_when_new_is_null(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts, z_di=-0.8))
    bhdb.upsert_bar(_bar(ts, z_di=None))  # NULL → keep -0.8
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["z_di"] == -0.8


def test_sqlite_upsert_fills_null_wdo_di(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts, wdo_price=None, di_price=None))
    bhdb.upsert_bar(_bar(ts, wdo_price=5_501.5, di_price=13.12))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["wdo_price"] == 5_501.5
    assert r["di_price"] == 13.12


def test_sqlite_select_window_by_days(sqlite_env):
    now = int(time.time())
    bhdb.upsert_bar(_bar(now - 10 * 86_400, date_str="2026-05-02", bar_time="09:00"))
    bhdb.upsert_bar(_bar(now, date_str="2026-05-12", bar_time="10:30"))
    recent = bhdb.select_window(days=1)
    assert len(recent) == 1
    assert recent[0]["bar_time"] == "10:30"
    all_rows = bhdb.select_window(days=30)
    assert len(all_rows) == 2


def test_sqlite_select_window_requires_arg(sqlite_env):
    with pytest.raises(ValueError):
        bhdb.select_window()


def test_sqlite_select_eg_warmup_inclusive(sqlite_env):
    bhdb.upsert_bar(_bar(1_700_000_000, date_str="2026-05-10", bar_time="09:00"))
    bhdb.upsert_bar(_bar(1_700_000_300, date_str="2026-05-12", bar_time="09:05"))
    bhdb.upsert_bar(_bar(1_700_000_600, date_str="2026-05-13", bar_time="09:10"))
    rows = bhdb.select_eg_warmup("2026-05-12")
    dates = [r["date_str"] for r in rows]
    assert dates == ["2026-05-10", "2026-05-12"]
    # Warmup query returns the trimmed projection only.
    assert set(rows[0].keys()) == {"timestamp", "date_str", "bar_time", "win_price", "wdo_price"}


def test_sqlite_count_rows_total_and_by_date(sqlite_env):
    bhdb.upsert_bar(_bar(1_700_000_000, date_str="2026-05-12", bar_time="09:00"))
    bhdb.upsert_bar(_bar(1_700_000_300, date_str="2026-05-12", bar_time="09:05"))
    bhdb.upsert_bar(_bar(1_700_000_600, date_str="2026-05-13", bar_time="09:00"))
    assert bhdb.count_rows() == 3
    assert bhdb.count_rows(date_str="2026-05-12") == 2
    assert bhdb.count_rows(date_str="2026-05-13") == 1
    assert bhdb.count_rows(date_str="2026-05-14") == 0


def test_sqlite_bar_time_range(sqlite_env):
    bhdb.upsert_bar(_bar(1_700_000_000, date_str="2026-05-12", bar_time="09:00"))
    bhdb.upsert_bar(_bar(1_700_000_300, date_str="2026-05-12", bar_time="17:50"))
    assert bhdb.bar_time_range("2026-05-12") == ("09:00", "17:50")
    assert bhdb.bar_time_range("2026-05-13") == (None, None)


def test_sqlite_update_columns_partial(sqlite_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar(ts))
    bhdb.update_columns(ts, z_di=2.5, beta_value=1.99)
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["z_di"] == 2.5
    assert r["beta_value"] == 1.99
    # Untouched fields stay put.
    assert r["z_wdo"] == 0.5


# ── OHLC schema + migration ─────────────────────────────────────────────────


def _sqlite_columns(db_path) -> set[str]:
    import sqlite3 as sql
    with sql.connect(str(db_path)) as conn:
        cur = conn.execute("PRAGMA table_info(bar_history)")
        return {row[1] for row in cur.fetchall()}


def test_sqlite_ohlc_columns_present_after_fresh_init(sqlite_env):
    cols = _sqlite_columns(sqlite_env)
    for col in _OHLC_KEYS:
        assert col in cols, f"missing OHLC column after fresh init: {col}"


def test_sqlite_ohlc_migration_from_legacy_table(tmp_path, monkeypatch):
    """init_schema must ALTER an existing pre-OHLC table, not silently skip it."""
    import sqlite3 as sql

    db_path = tmp_path / "legacy.db"
    legacy_ddl = """
    CREATE TABLE bar_history (
        timestamp       INTEGER PRIMARY KEY,
        date_str        TEXT NOT NULL,
        bar_time        TEXT NOT NULL,
        win_price       REAL,
        wdo_price       REAL,
        di_price        REAL,
        spread_wdo      REAL,
        spread_di       REAL,
        z_wdo           REAL,
        z_di            REAL,
        nwe_center      REAL,
        nwe_upper       REAL,
        nwe_lower       REAL,
        nwe_is_up       INTEGER,
        eg_pvalue       REAL,
        rho             REAL,
        rho_level       INTEGER,
        beta_value      REAL,
        beta_delta_pct  REAL
    )
    """
    with sql.connect(str(db_path)) as conn:
        conn.execute(legacy_ddl)
        conn.execute(
            "INSERT INTO bar_history (timestamp, date_str, bar_time, win_price) "
            "VALUES (?, ?, ?, ?)",
            (1_700_000_000, "2026-05-12", "09:00", 130_000.0),
        )
        conn.commit()

    # Sanity: OHLC columns absent in the legacy table.
    pre_cols = _sqlite_columns(db_path)
    for col in _OHLC_KEYS:
        assert col not in pre_cols

    monkeypatch.setenv("BAR_HISTORY_BACKEND", "sqlite")
    monkeypatch.setenv("BAR_HISTORY_SQLITE_PATH", str(db_path))
    bhdb.init_schema()

    post_cols = _sqlite_columns(db_path)
    for col in _OHLC_KEYS:
        assert col in post_cols
    # Existing row preserved (migration is additive, not destructive).
    rows = bhdb.select_by_date("2026-05-12")
    assert len(rows) == 1
    assert rows[0]["win_price"] == 130_000.0
    assert rows[0]["win_open"] is None  # new column starts NULL


def test_sqlite_ohlc_migration_idempotent(sqlite_env):
    """Re-running init_schema on an already-migrated table is a no-op."""
    bhdb.init_schema()
    bhdb.init_schema()
    cols = _sqlite_columns(sqlite_env)
    for col in _OHLC_KEYS:
        assert col in cols


def test_sqlite_upsert_ohlc_roundtrip(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar_with_ohlc(ts))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_open"] == 130_010.0
    assert r["win_high"] == 130_180.0
    assert r["win_low"] == 129_870.0
    assert r["wdo_open"] == 5_505.0
    assert r["wdo_high"] == 5_520.0
    assert r["wdo_low"] == 5_490.0
    assert r["di_open"] == 12.55
    assert r["di_high"] == 12.62
    assert r["di_low"] == 12.48


def test_sqlite_upsert_merge_preserves_existing_ohlc(sqlite_env):
    """Merge mode: NULL OHLC in re-upsert must keep the prior non-NULL values."""
    ts = int(time.time())
    bhdb.upsert_bar(_bar_with_ohlc(ts))
    # Re-upsert with OHLC explicitly None — should NOT clobber.
    bhdb.upsert_bar(_bar(ts, **{k: None for k in _OHLC_KEYS}))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_open"] == 130_010.0
    assert r["wdo_high"] == 5_520.0
    assert r["di_low"] == 12.48


def test_sqlite_upsert_merge_fills_null_ohlc_when_supplied(sqlite_env):
    """Merge mode: NULL → non-NULL fills the column (mirrors wdo_price/di_price)."""
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts))  # base has no OHLC
    bhdb.upsert_bar(_bar_with_ohlc(ts))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_open"] == 130_010.0
    assert r["di_high"] == 12.62


def test_sqlite_upsert_replace_overwrites_ohlc(sqlite_env):
    """Replace mode (backfill): every non-key column gets overwritten, OHLC included."""
    ts = int(time.time())
    bhdb.upsert_bar(_bar_with_ohlc(ts))
    bhdb.upsert_bar(
        _bar_with_ohlc(ts, win_open=999.0, win_high=999.0, win_low=999.0),
        mode="replace",
    )
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_open"] == 999.0
    assert r["win_high"] == 999.0
    assert r["win_low"] == 999.0


def test_sqlite_update_columns_accepts_ohlc(sqlite_env):
    ts = int(time.time())
    bhdb.upsert_bar(_bar(ts))
    bhdb.update_columns(ts, win_high=130_500.0, di_low=12.30)
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_high"] == 130_500.0
    assert r["di_low"] == 12.30


# ── Postgres backend (opt-in via PG_TEST_URI) ───────────────────────────────


def test_postgres_init_schema_idempotent(postgres_env):
    bhdb.init_schema()
    bhdb.init_schema()
    assert bhdb.count_rows() == 0


def test_postgres_upsert_roundtrip(postgres_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar(ts))
    rows = bhdb.select_by_date("2026-05-12")
    assert len(rows) == 1
    r = rows[0]
    assert r["timestamp"] == ts
    assert r["z_wdo"] == 0.5
    assert r["eg_pvalue"] == 0.04
    # SMALLINT for nwe_is_up.
    assert r["nwe_is_up"] == 1


def test_postgres_upsert_preserves_existing_indicators(postgres_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar(ts, eg_pvalue=0.04, rho=-0.82, beta_value=1.23))
    bhdb.upsert_bar(_bar(ts, eg_pvalue=None, rho=None, beta_value=None))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["eg_pvalue"] == 0.04
    assert r["rho"] == -0.82
    assert r["beta_value"] == 1.23


def test_postgres_upsert_z_di_asymmetry(postgres_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar(ts, z_di=-0.8))
    bhdb.upsert_bar(_bar(ts, z_di=1.42))  # overwrite
    assert bhdb.select_by_date("2026-05-12")[0]["z_di"] == 1.42
    bhdb.upsert_bar(_bar(ts, z_di=None))  # keep
    assert bhdb.select_by_date("2026-05-12")[0]["z_di"] == 1.42


def test_postgres_select_window_and_warmup(postgres_env):
    bhdb.upsert_bar(_bar(1_700_000_000, date_str="2026-05-10", bar_time="09:00"))
    bhdb.upsert_bar(_bar(1_700_000_300, date_str="2026-05-12", bar_time="09:05"))
    bhdb.upsert_bar(_bar(1_700_000_600, date_str="2026-05-13", bar_time="09:10"))
    assert bhdb.count_rows() == 3
    win = bhdb.select_window(since_ts=1_700_000_300)
    assert [r["timestamp"] for r in win] == [1_700_000_300, 1_700_000_600]
    warmup = bhdb.select_eg_warmup("2026-05-12")
    assert [r["date_str"] for r in warmup] == ["2026-05-10", "2026-05-12"]


def test_postgres_update_columns_partial(postgres_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar(ts))
    bhdb.update_columns(ts, z_di=2.5, beta_value=1.99)
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["z_di"] == 2.5
    assert r["beta_value"] == 1.99


def test_postgres_hypertable_created(postgres_env):
    """bar_history must be registered as a TimescaleDB hypertable."""
    import psycopg

    with psycopg.connect(postgres_env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = 'bar_history'"
            )
            (cnt,) = cur.fetchone()
            assert cnt == 1


# ── Postgres OHLC schema + migration ────────────────────────────────────────


def _postgres_columns(pg_uri: str) -> set[str]:
    import psycopg

    with psycopg.connect(pg_uri) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bar_history'"
            )
            return {row[0] for row in cur.fetchall()}


def test_postgres_ohlc_columns_present_after_fresh_init(postgres_env):
    cols = _postgres_columns(postgres_env)
    for col in _OHLC_KEYS:
        assert col in cols


def test_postgres_ohlc_migration_from_legacy_table(pg_uri, monkeypatch):
    """ADD COLUMN IF NOT EXISTS must populate the new OHLC columns on a legacy PG table."""
    import psycopg

    legacy_ddl = """
    CREATE TABLE bar_history (
        timestamp       BIGINT NOT NULL,
        date_str        TEXT NOT NULL,
        bar_time        TEXT NOT NULL,
        win_price       DOUBLE PRECISION,
        wdo_price       DOUBLE PRECISION,
        di_price        DOUBLE PRECISION,
        spread_wdo      DOUBLE PRECISION,
        spread_di       DOUBLE PRECISION,
        z_wdo           DOUBLE PRECISION,
        z_di            DOUBLE PRECISION,
        nwe_center      DOUBLE PRECISION,
        nwe_upper       DOUBLE PRECISION,
        nwe_lower       DOUBLE PRECISION,
        nwe_is_up       SMALLINT,
        eg_pvalue       DOUBLE PRECISION,
        rho             DOUBLE PRECISION,
        rho_level       SMALLINT,
        beta_value      DOUBLE PRECISION,
        beta_delta_pct  DOUBLE PRECISION,
        PRIMARY KEY (timestamp)
    )
    """
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")
            cur.execute(legacy_ddl)
            cur.execute(
                "INSERT INTO bar_history (timestamp, date_str, bar_time, win_price) "
                "VALUES (%s, %s, %s, %s)",
                (1_700_000_000, "2026-05-12", "09:00", 130_000.0),
            )

    pre_cols = _postgres_columns(pg_uri)
    for col in _OHLC_KEYS:
        assert col not in pre_cols

    monkeypatch.setenv("PG_URI", pg_uri)
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    bhdb.init_schema()

    post_cols = _postgres_columns(pg_uri)
    for col in _OHLC_KEYS:
        assert col in post_cols
    rows = bhdb.select_by_date("2026-05-12")
    assert len(rows) == 1
    assert rows[0]["win_open"] is None

    # Cleanup so the next test fixture starts from a clean slate.
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")


def test_postgres_ohlc_migration_idempotent(postgres_env):
    bhdb.init_schema()
    bhdb.init_schema()
    cols = _postgres_columns(postgres_env)
    for col in _OHLC_KEYS:
        assert col in cols


def test_postgres_upsert_ohlc_roundtrip(postgres_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar_with_ohlc(ts))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_open"] == 130_010.0
    assert r["wdo_high"] == 5_520.0
    assert r["di_low"] == 12.48


def test_postgres_upsert_merge_preserves_existing_ohlc(postgres_env):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar_with_ohlc(ts))
    bhdb.upsert_bar(_bar(ts, **{k: None for k in _OHLC_KEYS}))
    r = bhdb.select_by_date("2026-05-12")[0]
    assert r["win_open"] == 130_010.0
    assert r["di_high"] == 12.62


# ── Dual mode (requires both backends) ──────────────────────────────────────


def test_dual_write_lands_in_both_backends(dual_env, monkeypatch):
    ts = 1_700_000_000
    bhdb.upsert_bar(_bar(ts))
    # Read each backend explicitly to bypass the dual→sqlite read shortcut.
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "sqlite")
    sqlite_rows = bhdb.select_by_date("2026-05-12")
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    pg_rows = bhdb.select_by_date("2026-05-12")
    assert len(sqlite_rows) == 1
    assert len(pg_rows) == 1
    assert sqlite_rows[0]["timestamp"] == pg_rows[0]["timestamp"]
    assert sqlite_rows[0]["z_wdo"] == pg_rows[0]["z_wdo"]


def test_dual_read_uses_sqlite_baseline(dual_env, monkeypatch):
    """In dual mode reads MUST come from SQLite to preserve the live baseline."""
    ts = 1_700_000_000
    # Write through dual so both have the row.
    bhdb.upsert_bar(_bar(ts, z_wdo=0.5))
    # Now mutate Postgres only — sqlite stays at 0.5.
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    bhdb.update_columns(ts, z_wdo=9.99)
    # Back to dual: reads should ignore the PG mutation.
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "dual")
    rows = bhdb.select_by_date("2026-05-12")
    assert rows[0]["z_wdo"] == 0.5  # sqlite baseline wins on read
