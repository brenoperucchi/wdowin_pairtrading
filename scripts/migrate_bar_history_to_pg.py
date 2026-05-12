"""Migrate bar_history from SQLite to TimescaleDB/Postgres.

TASK-14 Slice 3. Idempotent bootstrap + import:

  1. Ensures Postgres schema (hypertable + date index) via core.bar_history_db.
  2. Enables columnar compression + policy (>= 90 days) on the hypertable.
  3. Streams rows from trades.db (read-only) into Postgres in batches with
     INSERT ... ON CONFLICT(timestamp) DO NOTHING so reruns are no-ops.
  4. Verifies parity: row totals and per-date COUNT + SUM(timestamp) checksum.
  5. Prints a summary: rows, days covered, first/last timestamp, elapsed.

Usage:
    PG_URI=postgresql://pairtrading:pw@localhost:5432/pairtrading_test \\
    python3 scripts/migrate_bar_history_to_pg.py --source-db trades.db

Flags:
    --source-db PATH        SQLite source (default: <repo>/trades.db)
    --batch-size N          rows per executemany batch (default 5000)
    --dry-run               run DDL + verification only, no INSERTs
    --skip-compression      do not configure TimescaleDB compression
    --no-verify             skip post-import counts/checksum
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core import bar_history_db as bhdb  # noqa: E402


_COMPRESSION_ENABLE = """
ALTER TABLE bar_history SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'date_str',
    timescaledb.compress_orderby   = 'timestamp'
)
"""
# Hypertable time column is BIGINT (epoch seconds); compress_after must
# therefore be an integer duration in seconds, not an INTERVAL.
# 7_776_000 = 90 * 86_400.
_COMPRESSION_POLICY = (
    "SELECT add_compression_policy('bar_history', BIGINT '7776000', "
    "if_not_exists => TRUE)"
)
_COMPRESSION_CHECK = (
    "SELECT compression_enabled FROM timescaledb_information.hypertables "
    "WHERE hypertable_name = 'bar_history'"
)

# Migration uses DO NOTHING (not the wrapper's DO UPDATE) so reruns leave
# existing rows untouched — strict snapshot copy of the SQLite source.
_PG_INSERT_NO_MERGE = (
    f"INSERT INTO bar_history ({bhdb._COLS_SQL}) "
    f"VALUES ({bhdb._PG_PLACEHOLDERS}) "
    f"ON CONFLICT(timestamp) DO NOTHING"
)


def _sqlite_ro(path: str) -> sqlite3.Connection:
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"SQLite source not found: {abs_path}")
    conn = sqlite3.connect(f"file:{abs_path}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _iter_batches(conn: sqlite3.Connection, batch_size: int) -> Iterator[list[sqlite3.Row]]:
    cur = conn.execute(
        f"SELECT {bhdb._COLS_SQL} FROM bar_history ORDER BY timestamp ASC"
    )
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            return
        yield rows


def _enable_compression(pg_cur) -> None:
    pg_cur.execute(_COMPRESSION_CHECK)
    row = pg_cur.fetchone()
    already_enabled = bool(row and row[0])
    if not already_enabled:
        pg_cur.execute(_COMPRESSION_ENABLE)
    pg_cur.execute(_COMPRESSION_POLICY)


def _per_date_checksum_sqlite(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    cur = conn.execute(
        "SELECT date_str, COUNT(*), COALESCE(SUM(timestamp), 0) "
        "FROM bar_history GROUP BY date_str"
    )
    return {d: (int(c), int(s)) for d, c, s in cur.fetchall()}


def _per_date_checksum_pg(pg_cur) -> dict[str, tuple[int, int]]:
    pg_cur.execute(
        "SELECT date_str, COUNT(*), COALESCE(SUM(timestamp), 0) "
        "FROM bar_history GROUP BY date_str"
    )
    return {d: (int(c), int(s)) for d, c, s in pg_cur.fetchall()}


def _verify(sqlite_conn: sqlite3.Connection, pg_cur) -> tuple[bool, list[str]]:
    src_total = sqlite_conn.execute("SELECT COUNT(*) FROM bar_history").fetchone()[0]
    pg_cur.execute("SELECT COUNT(*) FROM bar_history")
    pg_total = int(pg_cur.fetchone()[0])

    src_by_date = _per_date_checksum_sqlite(sqlite_conn)
    pg_by_date = _per_date_checksum_pg(pg_cur)

    issues: list[str] = []
    if src_total != pg_total:
        issues.append(f"row count: sqlite={src_total} pg={pg_total}")
    all_dates = sorted(set(src_by_date) | set(pg_by_date))
    for d in all_dates:
        if src_by_date.get(d) != pg_by_date.get(d):
            issues.append(
                f"date {d}: sqlite={src_by_date.get(d)} pg={pg_by_date.get(d)}"
            )
    print(
        f"  sqlite total={src_total} dates={len(src_by_date)} | "
        f"pg total={pg_total} dates={len(pg_by_date)}"
    )
    return (len(issues) == 0), issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", default=str(REPO_ROOT / "trades.db"))
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-compression", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args(argv)

    if not os.environ.get("PG_URI"):
        print("ERROR: PG_URI not set", file=sys.stderr)
        return 2

    print(f"[bootstrap] init_schema(backend=postgres)")
    bhdb.init_schema(backend="postgres")

    t0 = time.time()
    src = _sqlite_ro(args.source_db)
    try:
        src_total = src.execute("SELECT COUNT(*) FROM bar_history").fetchone()[0]
        print(f"[source] {args.source_db}: {src_total} rows")

        with bhdb._pg_conn() as pg_conn:
            with pg_conn.cursor() as cur:
                if args.skip_compression:
                    print("[bootstrap] skip-compression: not configuring policy")
                else:
                    print("[bootstrap] enable compression + policy >= 90 days")
                    _enable_compression(cur)

                if args.dry_run:
                    print("[dry-run] skipping INSERTs")
                else:
                    print(
                        f"[import] batch_size={args.batch_size} "
                        f"(ON CONFLICT DO NOTHING)"
                    )
                    imported = 0
                    next_log = max(args.batch_size, 10_000)
                    for batch in _iter_batches(src, args.batch_size):
                        values = [bhdb._values_tuple(dict(r)) for r in batch]
                        cur.executemany(_PG_INSERT_NO_MERGE, values)
                        imported += len(values)
                        if imported >= next_log or imported == src_total:
                            print(f"  ... {imported}/{src_total}")
                            next_log = imported + 10_000
                    print(f"[import] processed {imported} rows from source")

                ok = True
                issues: list[str] = []
                if args.no_verify:
                    print("[verify] skipped (--no-verify)")
                else:
                    print("[verify] counts + per-date checksum")
                    ok, issues = _verify(src, cur)
                    if not ok:
                        print(f"  MISMATCH ({len(issues)}):")
                        for line in issues:
                            print(f"    {line}")
                    else:
                        print("  OK — totals + per-date checksums match")

                cur.execute(
                    "SELECT MIN(timestamp), MAX(timestamp), "
                    "COUNT(DISTINCT date_str) FROM bar_history"
                )
                pg_min, pg_max, pg_days = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM bar_history")
                pg_total = int(cur.fetchone()[0])
                print(
                    f"[summary] pg rows={pg_total} days={pg_days} "
                    f"first_ts={pg_min} last_ts={pg_max}"
                )
    finally:
        src.close()

    elapsed = time.time() - t0
    print(f"[done] elapsed={elapsed:.1f}s")
    return 0 if (args.no_verify or ok) else 1


if __name__ == "__main__":
    sys.exit(main())
