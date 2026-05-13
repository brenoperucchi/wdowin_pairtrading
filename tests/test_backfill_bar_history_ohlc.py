"""Tests for scripts/backfill_bar_history_ohlc.py — TASK-17.5 ACs.

Covers the 5 acceptance criteria of Slice A.4:

  AC#1 — dry-run reports what would change, writes nothing
  AC#2 — `--commit` populates OHLC on rows where columns are NULL
  AC#3 — idempotent (running twice with `--commit` is a no-op on the second run
         because cells are already populated)
  AC#4 — `--force-refresh` rewrites OHLC even when cells are already populated
  AC#5 — cell-level checksum proves no INTEGRITY_COLUMN was touched (catches a
         programming mistake that would broaden the update set beyond the 9 OHLC
         columns).

All tests are SQLite-only and inject a fake MT5 fetcher — no real MT5 needed.
"""
from __future__ import annotations

import sqlite3
import time

import numpy as np
import pytest

import scripts.backfill_bar_history_ohlc as backfill
from core import bar_history_db as bhdb
from core.config import DI_SYMBOL, SYMBOL_A, SYMBOL_B, TIME_OFFSET
from server import init_bar_history, save_bar_history


TEST_DATE = "2026-05-08"
N_BARS = 5


# Structured dtype that mirrors MT5's copy_rates_range return shape.
_RATES_DTYPE = [
    ("time", "i8"),
    ("open", "f8"),
    ("high", "f8"),
    ("low", "f8"),
    ("close", "f8"),
    ("tick_volume", "u8"),
    ("spread", "i4"),
    ("real_volume", "u8"),
]


def _local_ts(i: int) -> int:
    """Local epoch seconds for bar i on TEST_DATE, starting at 09:00."""
    base = int(time.mktime(time.strptime(f"{TEST_DATE} 09:00", "%Y-%m-%d %H:%M")))
    return base + i * 300


def _mt5_ts(i: int) -> int:
    """MT5-side timestamp (UTC offset by TIME_OFFSET vs. local)."""
    return _local_ts(i) - TIME_OFFSET


def _seed_rows(db_path: str, n: int = N_BARS) -> list[int]:
    """Insert n bars without OHLC. Returns timestamps."""
    timestamps: list[int] = []
    for i in range(n):
        ts = _local_ts(i)
        hour = 9 + (i * 5) // 60
        minute = (i * 5) % 60
        save_bar_history(
            timestamp=ts,
            date_str=TEST_DATE,
            bar_time=f"{hour:02d}:{minute:02d}",
            win_price=130000.0 + i * 12.0,
            wdo_price=5500.0 + i * 0.7,
            di_price=12.5 + i * 0.01,
            spread_wdo=10.0,
            spread_di=1.0,
            z_wdo=0.1 + i * 0.01,
            z_di=0.2 + i * 0.01,
            nwe_center=130000.0,
            nwe_upper=130200.0,
            nwe_lower=129800.0,
            nwe_is_up=True,
            eg_pvalue=0.05,
            rho=-0.62,
            rho_level=1,
            beta_value=0.85,
            beta_delta_pct=2.5,
            db_path=db_path,
        )
        timestamps.append(ts)
    return timestamps


def _make_fetcher(*, win_offset=0.0, missing: set[int] | None = None):
    """Return a fake fetcher matching `Mt5RatesFetcher` contract.

    Builds OHLC structured arrays. `missing` is the set of bar indices for
    which all symbols should return no rows (simulates a gap).
    """
    missing = missing or set()

    def fetcher(symbol: str, dt_start, dt_end):
        rows = []
        for i in range(N_BARS):
            if i in missing:
                continue
            ts = _mt5_ts(i)
            if symbol == SYMBOL_A:
                close = 130000.0 + i * 12.0
                o, h, lo = close - 5.0, close + 25.0 + win_offset, close - 15.0
            elif symbol == SYMBOL_B:
                close = 5500.0 + i * 0.7
                o, h, lo = close - 0.3, close + 1.2, close - 0.8
            else:  # DI_SYMBOL
                close = 12.5 + i * 0.01
                o, h, lo = close - 0.01, close + 0.04, close - 0.02
            rows.append((ts, o, h, lo, close, 0, 0, 0))
        if not rows:
            return None
        return np.array(rows, dtype=_RATES_DTYPE)

    return fetcher


def _make_symbol_gap_fetcher(missing_by_symbol: dict[str, set[int]]):
    """Fake fetcher with gaps scoped per MT5 symbol."""
    base = _make_fetcher()

    def fetcher(symbol: str, dt_start, dt_end):
        rows = []
        rates = base(symbol, dt_start, dt_end)
        if rates is None:
            return None
        missing = missing_by_symbol.get(symbol, set())
        for r in rates:
            # Convert back to fixture bar index from the MT5 timestamp.
            i = int((int(r["time"]) - _mt5_ts(0)) / 300)
            if i not in missing:
                rows.append(tuple(r))
        if not rows:
            return None
        return np.array(rows, dtype=_RATES_DTYPE)

    return fetcher


def _read_row(db_path: str, ts: int) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM bar_history WHERE timestamp = ?", (ts,)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "bars.db")
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "sqlite")
    monkeypatch.setenv("BAR_HISTORY_SQLITE_PATH", path)
    init_bar_history(path)
    return path


# ─── AC#1: dry-run ──────────────────────────────────────────────────────────

def test_dry_run_reports_plan_without_writing(db):
    timestamps = _seed_rows(db)

    summary = backfill.run_backfill(
        start=TEST_DATE,
        end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=False,
        force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )

    assert summary["rows_scanned"] == N_BARS
    assert summary["rows_updated"] == N_BARS
    assert summary["cells_updated"] == N_BARS * 9  # 9 OHLC cols × N bars
    assert summary["rows_missing_mt5_data"] == 0
    assert summary["commit"] is False
    assert summary["integrity_after_sha256"] is None  # no post-write checksum

    # Nothing actually written
    for ts in timestamps:
        row = _read_row(db, ts)
        for col in (
            "win_open", "win_high", "win_low",
            "wdo_open", "wdo_high", "wdo_low",
            "di_open", "di_high", "di_low",
        ):
            assert row[col] is None, f"dry-run wrote {col} on ts={ts}"


# ─── AC#2: commit populates NULL OHLC ───────────────────────────────────────

def test_commit_populates_null_ohlc(db):
    timestamps = _seed_rows(db)

    summary = backfill.run_backfill(
        start=TEST_DATE,
        end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True,
        force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )

    assert summary["rows_updated"] == N_BARS
    assert summary["cells_updated"] == N_BARS * 9
    assert summary["integrity_after_sha256"] is not None
    assert (
        summary["integrity_after_sha256"] == summary["integrity_before_sha256"]
    )

    # Bar 0 sanity: win_close=130000 → open=129995, high=130025, low=129985
    row0 = _read_row(db, timestamps[0])
    assert row0["win_open"] == pytest.approx(129995.0)
    assert row0["win_high"] == pytest.approx(130025.0)
    assert row0["win_low"] == pytest.approx(129985.0)
    assert row0["wdo_open"] == pytest.approx(5499.7)
    assert row0["wdo_high"] == pytest.approx(5501.2)
    assert row0["wdo_low"] == pytest.approx(5499.2)
    assert row0["di_open"] == pytest.approx(12.49)
    assert row0["di_high"] == pytest.approx(12.54)
    assert row0["di_low"] == pytest.approx(12.48)

    # Indicator/close cells preserved
    assert row0["win_price"] == pytest.approx(130000.0)
    assert row0["z_wdo"] == pytest.approx(0.1)
    assert row0["rho"] == pytest.approx(-0.62)


# ─── AC#3: idempotent (second run is a no-op) ───────────────────────────────

def test_idempotent_second_commit_is_noop(db):
    _seed_rows(db)

    first = backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True, force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )
    assert first["rows_updated"] == N_BARS

    second = backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True, force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )
    assert second["rows_updated"] == 0
    assert second["cells_updated"] == 0
    assert second["integrity_after_sha256"] == second["integrity_before_sha256"]


# ─── AC#4: --force-refresh overwrites populated cells ───────────────────────

def test_force_refresh_rewrites_existing_ohlc(db):
    timestamps = _seed_rows(db)

    # First pass populates OHLC.
    backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True, force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )
    before = _read_row(db, timestamps[0])
    assert before["win_high"] == pytest.approx(130025.0)

    # Second pass with a shifted fetcher (win_high differs by +100) AND
    # --force-refresh → must overwrite.
    summary = backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True, force_refresh=True,
        mt5_fetcher=_make_fetcher(win_offset=100.0),
    )
    assert summary["rows_updated"] == N_BARS
    after = _read_row(db, timestamps[0])
    assert after["win_high"] == pytest.approx(130125.0)
    # Indicator preserved
    assert after["win_price"] == before["win_price"]
    assert after["z_wdo"] == before["z_wdo"]
    assert after["rho"] == before["rho"]


# ─── AC#5: cell-level integrity guard (drift detector) ──────────────────────

def test_integrity_checksum_aborts_on_non_ohlc_drift(db, monkeypatch):
    """Force a hostile UPDATE during the commit pass — checksum must catch it.

    We patch `bhdb.update_columns` to also clobber `win_price` on every call.
    The post-commit re-read should drift, triggering the RuntimeError.
    """
    _seed_rows(db)

    real_update = bhdb.update_columns
    def hostile(ts, *, backend=None, **cols):
        cols["win_price"] = -1.0  # drift!
        real_update(ts, backend=backend, **cols)

    monkeypatch.setattr(bhdb, "update_columns", hostile)
    # The backfill script imported `bhdb` at module load — repatch the binding
    # the script actually uses.
    monkeypatch.setattr(backfill.bhdb, "update_columns", hostile)

    with pytest.raises(RuntimeError, match="non-OHLC cell drift"):
        backfill.run_backfill(
            start=TEST_DATE, end=TEST_DATE,
            symbols=("WIN", "WDO", "DI"),
            commit=True, force_refresh=False,
            mt5_fetcher=_make_fetcher(),
        )


def test_integrity_checksum_stable_when_only_ohlc_written(db):
    """Sanity: a clean commit run leaves the integrity checksum bit-exact."""
    _seed_rows(db)
    summary = backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True, force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )
    assert summary["integrity_before_sha256"] == summary["integrity_after_sha256"]
    assert len(summary["integrity_before_sha256"]) == 64  # SHA-256 hex


# ─── Symbol/gap handling ────────────────────────────────────────────────────

def test_symbols_subset_only_updates_requested_columns(db):
    timestamps = _seed_rows(db)

    summary = backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN",),
        commit=True, force_refresh=False,
        mt5_fetcher=_make_fetcher(),
    )
    assert summary["cells_updated"] == N_BARS * 3  # WIN only → 3 cols × N

    row = _read_row(db, timestamps[0])
    assert row["win_open"] is not None
    assert row["wdo_open"] is None
    assert row["di_open"] is None


def test_rows_with_no_mt5_data_are_counted_not_updated(db):
    _seed_rows(db)

    # Fetcher returns nothing for bar index 2 → that ts has no OHLC.
    summary = backfill.run_backfill(
        start=TEST_DATE, end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True, force_refresh=False,
        mt5_fetcher=_make_fetcher(missing={2}),
    )
    assert summary["rows_updated"] == N_BARS - 1
    assert summary["rows_missing_mt5_data"] == 1
    assert summary["rows_partial_mt5_data"] == 0
    assert summary["cells_missing_mt5_data"] == 9


def test_partial_symbol_gaps_are_reported(db):
    _seed_rows(db)

    summary = backfill.run_backfill(
        start=TEST_DATE,
        end=TEST_DATE,
        symbols=("WIN", "WDO", "DI"),
        commit=True,
        force_refresh=False,
        mt5_fetcher=_make_symbol_gap_fetcher({SYMBOL_B: {2}}),
    )

    assert summary["rows_updated"] == N_BARS
    assert summary["rows_missing_mt5_data"] == 0
    assert summary["rows_partial_mt5_data"] == 1
    assert summary["cells_missing_mt5_data"] == 3


def test_backend_override_is_reported(db):
    _seed_rows(db)

    summary = backfill.run_backfill(
        start=TEST_DATE,
        end=TEST_DATE,
        symbols=("WIN",),
        commit=False,
        force_refresh=False,
        mt5_fetcher=_make_fetcher(),
        backend="sqlite",
    )

    assert summary["backend"] == "sqlite"
