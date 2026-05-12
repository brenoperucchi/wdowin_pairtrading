import math
import os
import sqlite3
import sys
import time

import pytest

import scripts.backfill_bar_history_indicators as backfill
from core import bar_history_db as bhdb
from core.config import DI_SYMBOL, SYMBOL_A, SYMBOL_B, TIME_OFFSET
from server import init_bar_history, save_bar_history


TEST_DATE = "2026-05-08"


def _ts_for(i: int) -> int:
    base = int(time.mktime(time.strptime(f"{TEST_DATE} 09:00", "%Y-%m-%d %H:%M")))
    return base + i * 300


def _local_ts(date_str: str, bar_time: str) -> int:
    return int(time.mktime(time.strptime(f"{date_str} {bar_time}", "%Y-%m-%d %H:%M")))


def _mt5_ts(date_str: str, bar_time: str) -> int:
    return _local_ts(date_str, bar_time) - TIME_OFFSET


def _seed_rows(db_path: str, n: int = 95, *, missing_wdo_at: set[int] | None = None) -> None:
    missing_wdo_at = missing_wdo_at or set()
    for i in range(n):
        ts = _ts_for(i)
        hour = 9 + (i * 5) // 60
        minute = (i * 5) % 60
        save_bar_history(
            timestamp=ts,
            date_str=TEST_DATE,
            bar_time=f"{hour:02d}:{minute:02d}",
            win_price=130000.0 + i * 12.0,
            wdo_price=None if i in missing_wdo_at else 5500.0 + i * 0.7,
            di_price=12.5,
            spread_wdo=10.0,
            spread_di=1.0,
            z_wdo=0.1,
            z_di=0.2,
            nwe_center=130000.0,
            nwe_upper=130200.0,
            nwe_lower=129800.0,
            nwe_is_up=True,
            db_path=db_path,
        )


def _fake_mt5_fetcher(n_prev: int = 100, n_today: int = 95, *, wdo_shift: float = 0.0):
    data = {
        SYMBOL_A: [],
        SYMBOL_B: [],
        DI_SYMBOL: [],
    }
    for day, n in (("2026-05-07", n_prev), (TEST_DATE, n_today)):
        for i in range(n):
            hour = 9 + (i * 5) // 60
            minute = (i * 5) % 60
            ts = _mt5_ts(day, f"{hour:02d}:{minute:02d}")
            absolute_i = (0 if day == "2026-05-07" else n_prev) + i
            data[SYMBOL_A].append((ts, 129000.0 + absolute_i * 12.0))
            data[SYMBOL_B].append((ts, 5400.0 + absolute_i * 0.7 + wdo_shift))
            data[DI_SYMBOL].append((ts, 12.0 + absolute_i * 0.01))

    def fetcher(symbol: str, start_ts: int, end_ts: int):
        rows = [(ts, close) for ts, close in data[symbol] if start_ts <= ts < end_ts]
        return (
            [close for _ts, close in rows],
            [ts for ts, _close in rows],
        )

    return fetcher


def _indicator_counts(db_path: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT COUNT(*), SUM(
                eg_pvalue IS NOT NULL
                AND rho IS NOT NULL
                AND rho_level IS NOT NULL
                AND beta_value IS NOT NULL
                AND beta_delta_pct IS NOT NULL
            )
            FROM bar_history
            """
        ).fetchone()
    finally:
        conn.close()


def test_backfill_updates_missing_indicators(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db)
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(source_db=db, date=TEST_DATE, backup=False)

    assert summary["rows_total"] == 95
    assert summary["rows_in_scope"] == 95
    assert summary["rows_computed"] == 5
    assert summary["rows_updated"] == 5
    assert _indicator_counts(db) == (95, 5)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM bar_history WHERE eg_pvalue IS NOT NULL ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["eg_pvalue"] == 0.04
    assert math.isfinite(row["rho"])
    assert row["rho_level"] in {0, 1, 2, 3}
    assert math.isfinite(row["beta_value"])
    assert math.isfinite(row["beta_delta_pct"])


def test_backfill_dry_run_does_not_write(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db)
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(source_db=db, date=TEST_DATE, dry_run=True, backup=False)

    assert summary["rows_computed"] == 5
    assert summary["rows_updated"] == 0
    assert _indicator_counts(db) == (95, 0)


def test_backfill_preserves_existing_values_without_overwrite(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db)
    ts = _ts_for(94)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE bar_history SET eg_pvalue = 0.99 WHERE timestamp = ?", (ts,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(source_db=db, date=TEST_DATE, backup=False)

    assert summary["rows_updated"] == 5
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT eg_pvalue, rho FROM bar_history WHERE timestamp = ?",
        (ts,),
    ).fetchone()
    conn.close()
    assert row[0] == 0.99
    assert row[1] is not None


def test_backfill_can_overwrite_existing_values(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db)
    ts = _ts_for(94)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE bar_history SET eg_pvalue = 0.99 WHERE timestamp = ?", (ts,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    backfill.run_backfill(source_db=db, date=TEST_DATE, overwrite=True, backup=False)

    conn = sqlite3.connect(db)
    value = conn.execute(
        "SELECT eg_pvalue FROM bar_history WHERE timestamp = ?",
        (ts,),
    ).fetchone()[0]
    conn.close()
    assert value == 0.04


def test_backfill_skips_rows_missing_pair_prices(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db, missing_wdo_at={94})
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(source_db=db, date=TEST_DATE, backup=False)

    assert summary["rows_missing_pair_prices"] == 1
    assert summary["rows_computed"] == 4
    assert _indicator_counts(db) == (95, 4)


def test_fetch_mt5_price_rows_maps_symbols_and_warmup_window():
    rows = backfill.fetch_mt5_price_rows(
        date=TEST_DATE,
        warmup_days=1,
        mt5_fetcher=_fake_mt5_fetcher(n_prev=2, n_today=2),
    )

    assert [r["date_str"] for r in rows] == ["2026-05-07", "2026-05-07", TEST_DATE, TEST_DATE]
    assert rows[0]["bar_time"] == "09:00"
    assert rows[0]["win_price"] is not None
    assert rows[0]["wdo_price"] is not None
    assert rows[0]["di_price"] is not None


def test_backfill_fetch_mt5_fills_prices_and_computes_indicators(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db, missing_wdo_at={94})
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(
        source_db=db,
        date=TEST_DATE,
        fetch_mt5=True,
        mt5_warmup_days=1,
        mt5_fetcher=_fake_mt5_fetcher(),
        backup=False,
    )

    assert summary["fetch_mt5"] is True
    assert summary["mt5_price_rows"] == 195
    assert summary["price_rows_inserted"] == 100
    assert summary["price_rows_updated"] == 1
    assert summary["rows_in_scope"] == 95
    assert summary["rows_computed"] == 95
    assert summary["rows_updated"] == 95

    conn = sqlite3.connect(db)
    fixed_wdo = conn.execute(
        "SELECT wdo_price FROM bar_history WHERE timestamp = ?",
        (_ts_for(94),),
    ).fetchone()[0]
    prev_rows = conn.execute(
        "SELECT COUNT(*) FROM bar_history WHERE date_str = '2026-05-07'"
    ).fetchone()[0]
    conn.close()
    assert fixed_wdo is not None
    assert prev_rows == 100
    assert _indicator_counts(db) == (195, 95)


def test_backfill_fetch_mt5_dry_run_does_not_write_prices_or_indicators(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db, missing_wdo_at={94})
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(
        source_db=db,
        date=TEST_DATE,
        fetch_mt5=True,
        mt5_warmup_days=1,
        mt5_fetcher=_fake_mt5_fetcher(),
        dry_run=True,
        backup=False,
    )

    assert summary["price_rows_inserted"] == 100
    assert summary["price_rows_updated"] == 1
    assert summary["rows_computed"] == 95
    assert summary["rows_updated"] == 0

    conn = sqlite3.connect(db)
    fixed_wdo = conn.execute(
        "SELECT wdo_price FROM bar_history WHERE timestamp = ?",
        (_ts_for(94),),
    ).fetchone()[0]
    prev_rows = conn.execute(
        "SELECT COUNT(*) FROM bar_history WHERE date_str = '2026-05-07'"
    ).fetchone()[0]
    conn.close()
    assert fixed_wdo is None
    assert prev_rows == 0
    assert _indicator_counts(db) == (95, 0)


def test_backfill_fetch_mt5_preserves_existing_prices_without_overwrite(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db)
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)
    original = sqlite3.connect(db).execute(
        "SELECT wdo_price FROM bar_history WHERE timestamp = ?",
        (_ts_for(94),),
    ).fetchone()[0]

    backfill.run_backfill(
        source_db=db,
        date=TEST_DATE,
        fetch_mt5=True,
        mt5_warmup_days=1,
        mt5_fetcher=_fake_mt5_fetcher(wdo_shift=999.0),
        backup=False,
    )

    conn = sqlite3.connect(db)
    value = conn.execute(
        "SELECT wdo_price FROM bar_history WHERE timestamp = ?",
        (_ts_for(94),),
    ).fetchone()[0]
    conn.close()
    assert value == original


def test_backfill_fetch_mt5_can_overwrite_existing_prices(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db)
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    backfill.run_backfill(
        source_db=db,
        date=TEST_DATE,
        fetch_mt5=True,
        mt5_warmup_days=1,
        mt5_fetcher=_fake_mt5_fetcher(wdo_shift=999.0),
        overwrite=True,
        backup=False,
    )

    conn = sqlite3.connect(db)
    value = conn.execute(
        "SELECT wdo_price FROM bar_history WHERE timestamp = ?",
        (_ts_for(94),),
    ).fetchone()[0]
    conn.close()
    assert value > 6000.0


# ── TASK-14 Slice 7: backend-aware behavior ─────────────────────────────────


def test_run_backfill_skips_source_existence_check_under_postgres(monkeypatch):
    """Postgres-only runs must not require a local SQLite trades.db."""
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    monkeypatch.delenv("BAR_HISTORY_SQLITE_PATH", raising=False)
    captured: dict = {}

    def fake_load_rows(*, backend=None):
        captured["backend"] = backend
        captured["sqlite_path_env"] = os.environ.get("BAR_HISTORY_SQLITE_PATH")
        return []

    monkeypatch.setattr(backfill, "load_rows", fake_load_rows)
    summary = backfill.run_backfill(
        source_db="/nonexistent/should-not-be-checked.db",
        date=TEST_DATE,
        dry_run=True,
        backup=False,
    )
    assert captured["backend"] == "postgres"
    # The env override only fires for sqlite/dual; postgres leaves it untouched.
    assert captured["sqlite_path_env"] is None
    assert summary["source_db"].startswith("<postgres:")
    assert summary["backup_path"] is None


def test_run_backfill_still_requires_source_db_under_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "sqlite")
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(FileNotFoundError):
        backfill.run_backfill(source_db=str(missing), date=TEST_DATE, backup=False)


def test_create_backup_skips_under_postgres(monkeypatch, tmp_path):
    """Postgres backend has no file-level snapshot → backup must return None."""
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    # Path doesn't even exist; shouldn't matter.
    assert backfill.create_backup(str(tmp_path / "irrelevant.db")) is None


def test_ensure_indicator_columns_is_noop_under_postgres(monkeypatch):
    """Postgres schema already has indicator columns — function must short-circuit."""
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    # If it tried to open SQLite, it would raise (env points nowhere meaningful).
    monkeypatch.delenv("BAR_HISTORY_SQLITE_PATH", raising=False)
    backfill.ensure_indicator_columns()  # must not raise


@pytest.fixture
def pg_clean_table(monkeypatch):
    """Drop+recreate Postgres bar_history. Skips when PG_TEST_URI is unset."""
    uri = os.environ.get("PG_TEST_URI")
    if not uri:
        pytest.skip("PG_TEST_URI not set; skipping Postgres integration tests")
    monkeypatch.setenv("PG_URI", uri)
    import psycopg

    with psycopg.connect(uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")
    bhdb.init_schema(backend="postgres")
    yield uri
    with psycopg.connect(uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS bar_history CASCADE")


def _seed_rows_pg(n: int = 95, *, missing_wdo_at: set[int] | None = None) -> None:
    missing_wdo_at = missing_wdo_at or set()
    rows = []
    for i in range(n):
        ts = _ts_for(i)
        hour = 9 + (i * 5) // 60
        minute = (i * 5) % 60
        rows.append(
            {
                "timestamp": ts,
                "date_str": TEST_DATE,
                "bar_time": f"{hour:02d}:{minute:02d}",
                "win_price": 130000.0 + i * 12.0,
                "wdo_price": None if i in missing_wdo_at else 5500.0 + i * 0.7,
                "di_price": 12.5,
                "spread_wdo": 10.0,
                "spread_di": 1.0,
                "z_wdo": 0.1,
                "z_di": 0.2,
                "nwe_center": 130000.0,
                "nwe_upper": 130200.0,
                "nwe_lower": 129800.0,
                "nwe_is_up": True,
            }
        )
    bhdb.upsert_bars_batch(rows, mode="merge", backend="postgres")


def test_backfill_updates_missing_indicators_postgres(monkeypatch, pg_clean_table):
    """Mirror of test_backfill_updates_missing_indicators against Postgres."""
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    _seed_rows_pg()
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(
        source_db="<unused-under-pg>",
        date=TEST_DATE,
        backup=False,
    )
    assert summary["rows_total"] == 95
    assert summary["rows_in_scope"] == 95
    assert summary["rows_computed"] == 5
    assert summary["rows_updated"] == 5

    import psycopg
    with psycopg.connect(pg_clean_table) as conn:
        cur = conn.execute(
            "SELECT eg_pvalue, rho, rho_level, beta_value, beta_delta_pct "
            "FROM bar_history WHERE eg_pvalue IS NOT NULL "
            "ORDER BY timestamp DESC LIMIT 1"
        )
        row = cur.fetchone()
    assert row[0] == 0.04
    assert math.isfinite(row[1])
    assert row[2] in {0, 1, 2, 3}
    assert math.isfinite(row[3])
    assert math.isfinite(row[4])


def test_backfill_preserves_existing_values_postgres(monkeypatch, pg_clean_table):
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")
    _seed_rows_pg()
    target_ts = _ts_for(94)
    bhdb.update_columns(target_ts, eg_pvalue=0.99, backend="postgres")
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    summary = backfill.run_backfill(
        source_db="<unused-under-pg>",
        date=TEST_DATE,
        backup=False,
    )
    assert summary["rows_updated"] == 5

    import psycopg
    with psycopg.connect(pg_clean_table) as conn:
        cur = conn.execute(
            "SELECT eg_pvalue, rho FROM bar_history WHERE timestamp = %s",
            (target_ts,),
        )
        eg, rho = cur.fetchone()
    assert eg == 0.99
    assert rho is not None


def test_backfill_fetch_mt5_never_calls_order_send(tmp_path, monkeypatch):
    db = str(tmp_path / "bars.db")
    init_bar_history(db)
    _seed_rows(db, missing_wdo_at={94})
    monkeypatch.setattr(backfill, "compute_engle_granger_pvalue", lambda *_args: 0.04)

    mt5_stub = sys.modules.get("MetaTrader5")
    assert mt5_stub is not None
    calls = []

    def spy_order_send(request):
        calls.append(request)
        raise AssertionError("backfill must not send MT5 orders")

    monkeypatch.setattr(mt5_stub, "order_send", spy_order_send, raising=False)

    backfill.run_backfill(
        source_db=db,
        date=TEST_DATE,
        fetch_mt5=True,
        mt5_warmup_days=1,
        mt5_fetcher=_fake_mt5_fetcher(),
        backup=False,
    )

    assert calls == []
