"""Backend-agnostic wrapper for the bar_history table.

TASK-14 Slice 2. Adds the abstraction without touching any caller yet.

Backend is selected via the ``BAR_HISTORY_BACKEND`` env var:

* ``sqlite`` (default) — current behavior, reads/writes ``trades.db``.
* ``postgres`` — reads/writes the Postgres/TimescaleDB hypertable.
* ``dual`` — writes go to both backends; reads come from SQLite.

The dual mode is the migration cutover bridge (Slice 4/5): the live engine
stays sourced from SQLite while we accumulate parity in Postgres.

Schema and UPSERT semantics are kept byte-equivalent across backends, including
the SQLite ``z_di`` asymmetry (``z_di`` is the only column that overwrites the
existing value when the new row has a non-NULL — see
``docs/migration_bar_history_timescale.md`` §4.

psycopg is imported lazily so SQLite-only environments don't need it.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

DEFAULT_SQLITE_PATH = "trades.db"

BAR_COLUMNS: tuple[str, ...] = (
    "timestamp", "date_str", "bar_time",
    "win_price", "wdo_price", "di_price",
    "spread_wdo", "spread_di", "z_wdo", "z_di",
    "nwe_center", "nwe_upper", "nwe_lower", "nwe_is_up",
    "eg_pvalue", "rho", "rho_level", "beta_value", "beta_delta_pct",
)


# ── DDL ──────────────────────────────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS bar_history (
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

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS bar_history (
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

_POSTGRES_HYPERTABLE = """
SELECT create_hypertable(
    'bar_history',
    'timestamp',
    chunk_time_interval => 2592000,
    if_not_exists       => TRUE
)
"""

_POSTGRES_DATE_INDEX = "CREATE INDEX IF NOT EXISTS bar_history_date_idx ON bar_history (date_str)"


# ── Conflict-resolution clauses (identical except excluded vs EXCLUDED) ──────
# `wdo_price`, `di_price`, indicators → preserve existing value, fill NULLs.
# `z_di` (only) → overwrite if the new row supplies a non-NULL value.
# Matches server.py:save_bar_history exactly. Do NOT change without updating
# both backends + the test suite.

_CONFLICT_SQLITE = """
ON CONFLICT(timestamp) DO UPDATE SET
    wdo_price = COALESCE(bar_history.wdo_price, excluded.wdo_price),
    di_price = COALESCE(bar_history.di_price, excluded.di_price),
    z_di = COALESCE(excluded.z_di, bar_history.z_di),
    eg_pvalue = COALESCE(bar_history.eg_pvalue, excluded.eg_pvalue),
    rho = COALESCE(bar_history.rho, excluded.rho),
    rho_level = COALESCE(bar_history.rho_level, excluded.rho_level),
    beta_value = COALESCE(bar_history.beta_value, excluded.beta_value),
    beta_delta_pct = COALESCE(bar_history.beta_delta_pct, excluded.beta_delta_pct)
"""

_CONFLICT_POSTGRES = """
ON CONFLICT(timestamp) DO UPDATE SET
    wdo_price = COALESCE(bar_history.wdo_price, EXCLUDED.wdo_price),
    di_price = COALESCE(bar_history.di_price, EXCLUDED.di_price),
    z_di = COALESCE(EXCLUDED.z_di, bar_history.z_di),
    eg_pvalue = COALESCE(bar_history.eg_pvalue, EXCLUDED.eg_pvalue),
    rho = COALESCE(bar_history.rho, EXCLUDED.rho),
    rho_level = COALESCE(bar_history.rho_level, EXCLUDED.rho_level),
    beta_value = COALESCE(bar_history.beta_value, EXCLUDED.beta_value),
    beta_delta_pct = COALESCE(bar_history.beta_delta_pct, EXCLUDED.beta_delta_pct)
"""

# `replace` mode (Slice 6) used by backfill scripts that own every column on
# conflict — overwrites all non-key columns from the incoming row. `timestamp`,
# `date_str`, `bar_time` are immutable in this contract (PK + bar identity).
_REPLACE_COLUMNS: tuple[str, ...] = tuple(
    c for c in BAR_COLUMNS if c not in ("timestamp", "date_str", "bar_time")
)

_CONFLICT_REPLACE_SQLITE = "ON CONFLICT(timestamp) DO UPDATE SET " + ", ".join(
    f"{c} = excluded.{c}" for c in _REPLACE_COLUMNS
)
_CONFLICT_REPLACE_POSTGRES = "ON CONFLICT(timestamp) DO UPDATE SET " + ", ".join(
    f"{c} = EXCLUDED.{c}" for c in _REPLACE_COLUMNS
)

_COLS_SQL = ", ".join(BAR_COLUMNS)
_SQLITE_PLACEHOLDERS = ", ".join("?" * len(BAR_COLUMNS))
_PG_PLACEHOLDERS = ", ".join(["%s"] * len(BAR_COLUMNS))

_UPSERT_SQLITE = f"INSERT INTO bar_history ({_COLS_SQL}) VALUES ({_SQLITE_PLACEHOLDERS}) {_CONFLICT_SQLITE}"
_UPSERT_POSTGRES = f"INSERT INTO bar_history ({_COLS_SQL}) VALUES ({_PG_PLACEHOLDERS}) {_CONFLICT_POSTGRES}"
_UPSERT_REPLACE_SQLITE = f"INSERT INTO bar_history ({_COLS_SQL}) VALUES ({_SQLITE_PLACEHOLDERS}) {_CONFLICT_REPLACE_SQLITE}"
_UPSERT_REPLACE_POSTGRES = f"INSERT INTO bar_history ({_COLS_SQL}) VALUES ({_PG_PLACEHOLDERS}) {_CONFLICT_REPLACE_POSTGRES}"


# ── Backend resolution ──────────────────────────────────────────────────────

def get_backend() -> str:
    return os.environ.get("BAR_HISTORY_BACKEND", "sqlite").lower()


def _read_backend(backend: str | None) -> str:
    """Return the backend to use for SELECT operations.

    In `dual` mode reads come from SQLite to preserve the baseline during
    cutover (Slice 4 → Slice 5 transition).
    """
    b = (backend or get_backend()).lower()
    return "sqlite" if b == "dual" else b


def sqlite_path() -> str:
    """Resolve the active SQLite path: ``BAR_HISTORY_SQLITE_PATH`` or default."""
    return os.environ.get("BAR_HISTORY_SQLITE_PATH", DEFAULT_SQLITE_PATH)


# Backwards-compatible private alias (internal callers).
_sqlite_path = sqlite_path


def _pg_uri() -> str:
    uri = os.environ.get("PG_URI")
    if not uri:
        raise RuntimeError(
            "PG_URI is not set; cannot use postgres/dual backend. "
            "Either export PG_URI or fall back to BAR_HISTORY_BACKEND=sqlite."
        )
    return uri


# ── Connection helpers ──────────────────────────────────────────────────────

@contextmanager
def _sqlite_conn(*, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    path = _sqlite_path()
    if readonly:
        uri = f"file:{os.path.abspath(path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    else:
        conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if not readonly:
            conn.commit()
    finally:
        conn.close()


@contextmanager
def _pg_conn():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for BAR_HISTORY_BACKEND in {postgres, dual}. "
            "Install with `pip install 'psycopg[binary]>=3.1'`."
        ) from exc
    conn = psycopg.connect(_pg_uri(), autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── DDL ──────────────────────────────────────────────────────────────────────

def init_schema(backend: str | None = None) -> None:
    """Idempotently create bar_history (and hypertable+index on Postgres)."""
    b = (backend or get_backend()).lower()
    if b in ("sqlite", "dual"):
        with _sqlite_conn() as conn:
            conn.execute(_SQLITE_SCHEMA)
    if b in ("postgres", "dual"):
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(_POSTGRES_SCHEMA)
                cur.execute(_POSTGRES_HYPERTABLE)
                cur.execute(_POSTGRES_DATE_INDEX)


# ── Writes ──────────────────────────────────────────────────────────────────

def _values_tuple(row: dict) -> tuple[Any, ...]:
    nwe = row.get("nwe_is_up")
    nwe_val = int(bool(nwe)) if nwe is not None else None
    rho_lvl = row.get("rho_level")
    rho_lvl_val = int(rho_lvl) if rho_lvl is not None else None
    return (
        int(row["timestamp"]),
        row["date_str"],
        row["bar_time"],
        row.get("win_price"),
        row.get("wdo_price"),
        row.get("di_price"),
        row.get("spread_wdo"),
        row.get("spread_di"),
        row.get("z_wdo"),
        row.get("z_di"),
        row.get("nwe_center"),
        row.get("nwe_upper"),
        row.get("nwe_lower"),
        nwe_val,
        row.get("eg_pvalue"),
        row.get("rho"),
        rho_lvl_val,
        row.get("beta_value"),
        row.get("beta_delta_pct"),
    )


def upsert_bar(row: dict, backend: str | None = None, *, mode: str = "merge") -> None:
    """Insert a bar, or update on conflict per `mode`.

    Required keys: timestamp, date_str, bar_time. All other columns optional.

    * ``mode="merge"`` (default) — production semantics from save_bar_history:
      COALESCE existing non-NULL fields, with `z_di` as the only column that
      overwrites when the new row supplies a non-NULL.
    * ``mode="replace"`` — backfill semantics (force=True): overwrite every
      non-key column with the incoming row. Used by scripts that just recomputed
      the whole bar from MT5 closes.
    """
    if mode not in ("merge", "replace"):
        raise ValueError(f"upsert_bar mode must be 'merge' or 'replace', got {mode!r}")
    b = (backend or get_backend()).lower()
    values = _values_tuple(row)
    sqlite_sql = _UPSERT_SQLITE if mode == "merge" else _UPSERT_REPLACE_SQLITE
    pg_sql = _UPSERT_POSTGRES if mode == "merge" else _UPSERT_REPLACE_POSTGRES
    if b in ("sqlite", "dual"):
        with _sqlite_conn() as conn:
            conn.execute(sqlite_sql, values)
    if b in ("postgres", "dual"):
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(pg_sql, values)


def upsert_bars_batch(
    rows: list[dict],
    *,
    mode: str = "merge",
    backend: str | None = None,
) -> None:
    """Bulk UPSERT — same semantics as `upsert_bar`, one transaction.

    Backfill scripts process thousands of bars per run; opening one connection
    per row over Postgres adds 30+ seconds for no reason. This issues a single
    executemany inside one connection.
    """
    if mode not in ("merge", "replace"):
        raise ValueError(f"upsert_bars_batch mode must be 'merge' or 'replace', got {mode!r}")
    if not rows:
        return
    b = (backend or get_backend()).lower()
    values_list = [_values_tuple(r) for r in rows]
    sqlite_sql = _UPSERT_SQLITE if mode == "merge" else _UPSERT_REPLACE_SQLITE
    pg_sql = _UPSERT_POSTGRES if mode == "merge" else _UPSERT_REPLACE_POSTGRES
    if b in ("sqlite", "dual"):
        with _sqlite_conn() as conn:
            conn.executemany(sqlite_sql, values_list)
    if b in ("postgres", "dual"):
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(pg_sql, values_list)


def update_columns(timestamp: int, *, backend: str | None = None, **cols: Any) -> None:
    """Partial UPDATE by timestamp PK. Used by indicator backfill scripts."""
    if not cols:
        return
    for k in cols:
        if k not in BAR_COLUMNS:
            raise ValueError(f"unknown bar_history column: {k}")
    b = (backend or get_backend()).lower()
    keys = list(cols.keys())
    values = [cols[k] for k in keys]
    if b in ("sqlite", "dual"):
        sql = f"UPDATE bar_history SET {', '.join(f'{k}=?' for k in keys)} WHERE timestamp=?"
        with _sqlite_conn() as conn:
            conn.execute(sql, [*values, int(timestamp)])
    if b in ("postgres", "dual"):
        sql = f"UPDATE bar_history SET {', '.join(f'{k}=%s' for k in keys)} WHERE timestamp=%s"
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [*values, int(timestamp)])


def update_columns_batch(
    column: str,
    updates: list[tuple[Any, int]],
    *,
    backend: str | None = None,
) -> None:
    """Bulk UPDATE of a single column by timestamp PK.

    `updates` is a list of (value, timestamp) tuples. Used by backfill scripts
    that rewrite a single indicator (e.g. z_di) across hundreds of rows: opening
    one connection per row is wasteful, especially against Postgres.
    """
    if column not in BAR_COLUMNS:
        raise ValueError(f"unknown bar_history column: {column}")
    if not updates:
        return
    b = (backend or get_backend()).lower()
    coerced = [(v, int(ts)) for v, ts in updates]
    if b in ("sqlite", "dual"):
        with _sqlite_conn() as conn:
            conn.executemany(
                f"UPDATE bar_history SET {column}=? WHERE timestamp=?",
                coerced,
            )
    if b in ("postgres", "dual"):
        with _pg_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    f"UPDATE bar_history SET {column}=%s WHERE timestamp=%s",
                    coerced,
                )


# ── Reads ───────────────────────────────────────────────────────────────────

def _pg_rows_as_dicts(cur) -> list[dict]:
    colnames = [d[0] for d in cur.description]
    return [dict(zip(colnames, r)) for r in cur.fetchall()]


def select_window(
    *,
    days: int | None = None,
    since_ts: int | None = None,
    backend: str | None = None,
) -> list[dict]:
    """Return rows with timestamp >= cutoff, ASC.

    Provide either ``days`` (relative to now) or ``since_ts`` (epoch seconds).
    """
    if days is not None:
        since_ts = int(time.time()) - days * 86400
    if since_ts is None:
        raise ValueError("select_window requires days= or since_ts=")
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            cur = conn.execute(
                "SELECT * FROM bar_history WHERE timestamp >= ? ORDER BY timestamp ASC",
                (int(since_ts),),
            )
            return [dict(r) for r in cur.fetchall()]
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bar_history WHERE timestamp >= %s ORDER BY timestamp ASC",
                (int(since_ts),),
            )
            return _pg_rows_as_dicts(cur)


def select_by_date(date_str: str, *, backend: str | None = None) -> list[dict]:
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            cur = conn.execute(
                "SELECT * FROM bar_history WHERE date_str = ? ORDER BY timestamp ASC",
                (date_str,),
            )
            return [dict(r) for r in cur.fetchall()]
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bar_history WHERE date_str = %s ORDER BY timestamp ASC",
                (date_str,),
            )
            return _pg_rows_as_dicts(cur)


def select_di_warmup(date_str: str, *, backend: str | None = None) -> list[dict]:
    """Rows with date_str <= cutoff and both win_price/di_price non-NULL.

    Used by `scripts/backfill_z_di.py` to rebuild the OLS window without
    leaking SQL across the wrapper.
    """
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            cur = conn.execute(
                """
                SELECT timestamp, win_price, di_price
                FROM bar_history
                WHERE date_str <= ?
                  AND win_price IS NOT NULL
                  AND di_price  IS NOT NULL
                ORDER BY timestamp ASC
                """,
                (date_str,),
            )
            return [dict(r) for r in cur.fetchall()]
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, win_price, di_price
                FROM bar_history
                WHERE date_str <= %s
                  AND win_price IS NOT NULL
                  AND di_price  IS NOT NULL
                ORDER BY timestamp ASC
                """,
                (date_str,),
            )
            return _pg_rows_as_dicts(cur)


def select_timestamps_by_date(date_str: str, *, backend: str | None = None) -> list[int]:
    """Return the `timestamp` PKs for a given session date, ASC."""
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            cur = conn.execute(
                "SELECT timestamp FROM bar_history WHERE date_str = ? ORDER BY timestamp",
                (date_str,),
            )
            return [int(r[0]) for r in cur.fetchall()]
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT timestamp FROM bar_history WHERE date_str = %s ORDER BY timestamp",
                (date_str,),
            )
            return [int(r[0]) for r in cur.fetchall()]


def select_eg_warmup(date_str: str, *, backend: str | None = None) -> list[dict]:
    """Rows with date_str <= cutoff. Used by replay EG recomputation warmup."""
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            cur = conn.execute(
                """
                SELECT timestamp, date_str, bar_time, win_price, wdo_price
                FROM bar_history
                WHERE date_str <= ?
                ORDER BY timestamp ASC
                """,
                (date_str,),
            )
            return [dict(r) for r in cur.fetchall()]
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, date_str, bar_time, win_price, wdo_price
                FROM bar_history
                WHERE date_str <= %s
                ORDER BY timestamp ASC
                """,
                (date_str,),
            )
            return _pg_rows_as_dicts(cur)


def count_rows(*, date_str: str | None = None, backend: str | None = None) -> int:
    """Total row count, or count for a single date if `date_str` provided."""
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            if date_str is None:
                row = conn.execute("SELECT COUNT(*) FROM bar_history").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM bar_history WHERE date_str = ?",
                    (date_str,),
                ).fetchone()
            return int(row[0])
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            if date_str is None:
                cur.execute("SELECT COUNT(*) FROM bar_history")
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM bar_history WHERE date_str = %s",
                    (date_str,),
                )
            return int(cur.fetchone()[0])


def bar_time_range(
    date_str: str, *, backend: str | None = None
) -> tuple[str | None, str | None]:
    """Return (MIN(bar_time), MAX(bar_time)) for a given date."""
    b = _read_backend(backend)
    if b == "sqlite":
        with _sqlite_conn(readonly=True) as conn:
            row = conn.execute(
                "SELECT MIN(bar_time), MAX(bar_time) FROM bar_history WHERE date_str = ?",
                (date_str,),
            ).fetchone()
            return (row[0], row[1])
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MIN(bar_time), MAX(bar_time) FROM bar_history WHERE date_str = %s",
                (date_str,),
            )
            row = cur.fetchone()
            return (row[0], row[1])
