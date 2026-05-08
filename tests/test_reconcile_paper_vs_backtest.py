import sqlite3
from datetime import date

from scripts.reconcile_paper_vs_backtest import (
    aggregate_backtest_window,
    business_days_ago,
    load_paper_trades,
)


def _db(tmp_path):
    path = tmp_path / "paper.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE matador_ops (
            timestamp_out TEXT,
            status TEXT,
            pnl_brl REAL,
            z_source TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    return path


def _insert(path, timestamp_out, pnl, z_source="V2_KALMAN", status="CLOSED"):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO matador_ops VALUES (?, ?, ?, ?)",
        (timestamp_out, status, pnl, z_source),
    )
    conn.commit()
    conn.close()


def test_business_days_ago_inclusive_of_today():
    assert business_days_ago(date(2026, 5, 7), 1) == date(2026, 5, 7)
    assert business_days_ago(date(2026, 5, 7), 2) == date(2026, 5, 6)
    assert business_days_ago(date(2026, 5, 4), 2) == date(2026, 5, 1)
    assert business_days_ago(date(2026, 5, 9), 1) == date(2026, 5, 8)


def test_load_paper_trades_applies_inclusive_window_and_upper_bound(tmp_path):
    path = _db(tmp_path)
    _insert(path, "2026-05-06 10:00:00", 100.0)
    _insert(path, "2026-05-07 10:00:00", 200.0)
    _insert(path, "2026-05-08 10:00:00", 999.0)

    rows = load_paper_trades(path, date(2026, 5, 6), date(2026, 5, 7))

    assert rows == [
        ("2026-05-06 10:00:00", 100.0),
        ("2026-05-07 10:00:00", 200.0),
    ]


def test_load_paper_trades_excludes_replay_rows(tmp_path):
    path = _db(tmp_path)
    _insert(path, "2026-05-07 10:00:00", 100.0, z_source="V2_KALMAN")
    _insert(path, "2026-05-07 10:05:00", -120.0, z_source="REPLAY_DI_JOHANSEN")
    _insert(path, "2026-05-07 10:10:00", 80.0, z_source=None)

    rows = load_paper_trades(path, date(2026, 5, 7), date(2026, 5, 7))

    assert rows == [
        ("2026-05-07 10:00:00", 100.0),
        ("2026-05-07 10:10:00", 80.0),
    ]


def test_aggregate_backtest_window_applies_same_bounds():
    daily = [
        {"date": "2026-05-05", "trades": 1, "pnl_brl_net": 10.0, "pnl_brl_gross": 16.0},
        {"date": "2026-05-06", "trades": 2, "pnl_brl_net": 20.0, "pnl_brl_gross": 32.0},
        {"date": "2026-05-07", "trades": 3, "pnl_brl_net": 30.0, "pnl_brl_gross": 48.0},
        {"date": "2026-05-08", "trades": 99, "pnl_brl_net": 999.0, "pnl_brl_gross": 999.0},
    ]

    out = aggregate_backtest_window(daily, date(2026, 5, 6), date(2026, 5, 7))

    assert out == {
        "trades": 5,
        "pnl_brl_gross": 80.0,
        "pnl_brl_net": 50.0,
    }
