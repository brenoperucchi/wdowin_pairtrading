"""Migrate bar_history from SQLite to TimescaleDB/Postgres.

TASK-14 Slice 3. Idempotent bootstrap + import:

  1. Ensures Postgres schema (hypertable + date index) via core.bar_history_db.
  2. Enables columnar compression + policy (>= 90 days) on the hypertable.
  3. Streams rows from trades.db (read-only) into Postgres in batches.
     Default: ON CONFLICT(timestamp) DO NOTHING (idempotent reruns).
     With --force-refresh: ON CONFLICT(timestamp) DO UPDATE (overwrite drift).
  4. Verifies parity at the cell level — SHA-256 over every column of every
     row, grouped by date_str. Catches the case where timestamps match but
     z_di/rho/beta/price/etc. drifted (which DO NOTHING leaves stale).
     On mismatch suggests rerunning with --force-refresh.
  5. Prints a summary: rows, days covered, first/last timestamp, elapsed.

Usage:
    PG_URI=postgresql://pairtrading:pw@localhost:5432/pairtrading_test \\
    python3 scripts/migrate_bar_history_to_pg.py --source-db trades.db

Flags:
    --source-db PATH        SQLite source (default: <repo>/trades.db)
    --batch-size N          rows per executemany batch (default 5000)
    --dry-run               run DDL + verification only, no INSERTs
    --skip-compression      do not configure TimescaleDB compression
    --no-verify             skip post-import content-hash verification
    --force-refresh         overwrite PG rows on timestamp conflict
                            (use when verify reports drift)
"""

from __future__ import annotations

import argparse
import hashlib
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

# Default insert mode: DO NOTHING keeps reruns no-op when PG already matches
# SQLite. It does NOT repair drift — if a row in PG has stale values for the
# same timestamp, it stays. The content-hash verification below catches that
# case and exits non-zero; use --force-refresh to switch to DO UPDATE.
_PG_INSERT_DO_NOTHING = (
    f"INSERT INTO bar_history ({bhdb._COLS_SQL}) "
    f"VALUES ({bhdb._PG_PLACEHOLDERS}) "
    f"ON CONFLICT(timestamp) DO NOTHING"
)

# Force-refresh insert mode: overwrites every non-PK column with the SQLite
# snapshot. Explicit column list (vs `EXCLUDED.*`) so adding a column later
# fails loudly here instead of silently dropping it from the overwrite set.
_OVERWRITE_ASSIGNMENTS = ", ".join(
    f"{c} = EXCLUDED.{c}" for c in bhdb.BAR_COLUMNS if c != "timestamp"
)
_PG_INSERT_OVERWRITE = (
    f"INSERT INTO bar_history ({bhdb._COLS_SQL}) "
    f"VALUES ({bhdb._PG_PLACEHOLDERS}) "
    f"ON CONFLICT(timestamp) DO UPDATE SET {_OVERWRITE_ASSIGNMENTS}"
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


def _row_signature(row: dict) -> bytes:
    """Stable byte representation of one bar_history row.

    Uses `repr()` on Python natives — both SQLite and psycopg map our
    columns to (int|float|str|None), so the repr is identical on both
    sides byte-for-byte. We pin the column order to `bhdb.BAR_COLUMNS`
    so that schema column-order drift is detected too.
    """
    parts: list[str] = []
    for col in bhdb.BAR_COLUMNS:
        v = row.get(col)
        parts.append("∅" if v is None else repr(v))
    return "|".join(parts).encode("utf-8")


def _content_hash_by_date_sqlite(conn: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    cur = conn.execute(
        f"SELECT {bhdb._COLS_SQL} FROM bar_history ORDER BY date_str, timestamp"
    )
    return _accumulate_hashes(dict(r) for r in cur)


def _content_hash_by_date_pg(pg_cur) -> dict[str, tuple[int, str]]:
    pg_cur.execute(
        f"SELECT {bhdb._COLS_SQL} FROM bar_history ORDER BY date_str, timestamp"
    )
    colnames = [d[0] for d in pg_cur.description]
    return _accumulate_hashes(dict(zip(colnames, r)) for r in pg_cur)


def _accumulate_hashes(rows: Iterator[dict]) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    current_date: str | None = None
    current_hash: hashlib._Hash | None = None
    current_count = 0
    for r in rows:
        d = r["date_str"]
        if d != current_date:
            if current_date is not None and current_hash is not None:
                result[current_date] = (current_count, current_hash.hexdigest())
            current_date = d
            current_hash = hashlib.sha256()
            current_count = 0
        assert current_hash is not None
        current_hash.update(_row_signature(r))
        current_count += 1
    if current_date is not None and current_hash is not None:
        result[current_date] = (current_count, current_hash.hexdigest())
    return result


def _verify(sqlite_conn: sqlite3.Connection, pg_cur) -> tuple[bool, list[str]]:
    """Verify SQLite ≡ Postgres at the cell level.

    Computes a SHA-256 over every column of every row, grouped by date_str.
    Catches the case where a row's `timestamp` matches but its `z_di`,
    `rho`, price columns, etc. drift — which `ON CONFLICT DO NOTHING`
    will silently keep stale on rerun. Suggest --force-refresh on failure.
    """
    src_total = sqlite_conn.execute("SELECT COUNT(*) FROM bar_history").fetchone()[0]
    pg_cur.execute("SELECT COUNT(*) FROM bar_history")
    pg_total = int(pg_cur.fetchone()[0])

    src_by_date = _content_hash_by_date_sqlite(sqlite_conn)
    pg_by_date = _content_hash_by_date_pg(pg_cur)

    issues: list[str] = []
    if src_total != pg_total:
        issues.append(f"row count: sqlite={src_total} pg={pg_total}")
    for d in sorted(set(src_by_date) | set(pg_by_date)):
        s = src_by_date.get(d)
        p = pg_by_date.get(d)
        if s == p:
            continue
        if s is None:
            issues.append(f"date {d}: missing in sqlite, pg has {p[0]} rows")
        elif p is None:
            issues.append(f"date {d}: missing in pg, sqlite has {s[0]} rows")
        elif s[0] != p[0]:
            issues.append(f"date {d}: row count sqlite={s[0]} pg={p[0]}")
        else:
            issues.append(
                f"date {d}: content hash differs (rows={s[0]}, "
                f"sqlite={s[1][:12]}.. pg={p[1][:12]}..)"
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
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Overwrite every column on conflicting timestamps (ON CONFLICT "
             "DO UPDATE). Default is DO NOTHING, which leaves drift in place. "
             "Use this when content-hash verification fails.",
    )
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
                    insert_sql = (
                        _PG_INSERT_OVERWRITE if args.force_refresh
                        else _PG_INSERT_DO_NOTHING
                    )
                    mode_label = (
                        "ON CONFLICT DO UPDATE (force-refresh)"
                        if args.force_refresh else "ON CONFLICT DO NOTHING"
                    )
                    print(f"[import] batch_size={args.batch_size} ({mode_label})")
                    imported = 0
                    next_log = max(args.batch_size, 10_000)
                    for batch in _iter_batches(src, args.batch_size):
                        values = [bhdb._values_tuple(dict(r)) for r in batch]
                        cur.executemany(insert_sql, values)
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
                    print("[verify] counts + per-date SHA-256 over all columns")
                    ok, issues = _verify(src, cur)
                    if not ok:
                        print(f"  MISMATCH ({len(issues)}):")
                        for line in issues[:20]:
                            print(f"    {line}")
                        if len(issues) > 20:
                            print(f"    ... and {len(issues) - 20} more")
                        if not args.force_refresh:
                            print(
                                "  HINT: rerun with --force-refresh to overwrite "
                                "PG rows with SQLite values."
                            )
                    else:
                        print("  OK — every cell in every row matches SQLite")

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
