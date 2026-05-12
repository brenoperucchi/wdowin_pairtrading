# core/execution_timeline.py
"""Execution Timeline — funil operacional auditável persistido em SQLite.

Cada barra M5 fechada gera ~14-16 eventos (DATA→INDICATORS→ELIGIBILITY→RISK→
SIGNAL→ORDER→EXECUTION→EXIT). Eventos críticos (MT5 desconectado, order
falhou) também entram fora do contexto da barra.

Schema do evento em `_FIELDS` abaixo. `dedupe_key` é UNIQUE — `INSERT OR IGNORE`
faz a idempotência funcionar sob cache hit / retry.

Owners de emissão (Slices B/C):
- `server.py` emite DATA/INDICATORS/ELIGIBILITY/RISK e SIGNAL WAIT/SKIPPED
  por barra fechada.
- `core.trade_engine` emite SIGNAL real (BUY_WIN/SELL_WIN), ORDER_REQUEST,
  EXECUTION_FILLED/REJECTED e EXIT.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Iterable

# Ordem do funil — usada pela `current_bottleneck` para escolher o primeiro
# bloqueio por fase dentro da última barra fechada.
PHASE_ORDER = (
    "DATA",
    "INDICATORS",
    "ELIGIBILITY",
    "RISK",
    "SIGNAL",
    "ORDER",
    "EXECUTION",
    "EXIT",
)

_BLOCKING_STATUSES = ("BLOCKED", "FAILED")
_MAX_LOAD_LIMIT = 1000
_DEFAULT_LIVE_ISSUE_MAX_AGE_SECONDS = 300

_FIELDS = (
    "timestamp",
    "closed_bar_ts",
    "correlation_id",
    "attempt_id",
    "dedupe_key",
    "trade_id",
    "phase",
    "event",
    "status",
    "severity",
    "strategy",
    "symbol",
    "metric",
    "value",
    "threshold",
    "operator",
    "distance",
    "ratio_to_threshold",
    "message",
    "payload_json",
)


# ─── Schema ─────────────────────────────────────────────────────────────────

def init_timeline_table(db_path: str) -> None:
    """Create `execution_timeline` table + indexes if missing. Idempotent."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                closed_bar_ts INTEGER,
                correlation_id TEXT,
                attempt_id TEXT,
                dedupe_key TEXT NOT NULL,
                trade_id INTEGER,
                phase TEXT NOT NULL,
                event TEXT NOT NULL,
                status TEXT NOT NULL,
                severity TEXT,
                strategy TEXT,
                symbol TEXT,
                metric TEXT,
                value REAL,
                threshold REAL,
                operator TEXT,
                distance REAL,
                ratio_to_threshold REAL,
                message TEXT,
                payload_json TEXT
            )
            """
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_timeline_dedupe "
            "ON execution_timeline(dedupe_key)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS ix_timeline_ts "
            "ON execution_timeline(timestamp)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS ix_timeline_bar_phase "
            "ON execution_timeline(closed_bar_ts, phase, strategy)"
        )
        conn.commit()
    finally:
        conn.close()


# ─── Distance / ratio computation ───────────────────────────────────────────

def _compute_distance_ratio(
    value: float | None,
    threshold: float | None,
    operator: str | None,
) -> tuple[float | None, float | None]:
    """Return (distance, ratio_to_threshold) given value/threshold/operator.

    `operator` is the pass requirement. `distance` is signed around that
    requirement: positive means the value is still on the blocked side;
    negative means the value has margin on the passing side.

    Example: the EG gate requires `eg_pvalue < 0.10`. With value=0.64,
    threshold=0.10, operator="<", distance is +0.54: the pvalue is 0.54
    above the permitted ceiling. With value=0.04, distance is -0.06.

    `ratio_to_threshold` is `value / threshold` when threshold != 0. Useful
    to highlight "6.4× over the limit" type messages in the UI.
    """
    if value is None or threshold is None:
        return None, None
    op = operator or ""
    if op in ("<", "<="):
        distance = float(value) - float(threshold)
    elif op in (">", ">="):
        distance = float(threshold) - float(value)
    else:  # "==", or unknown — default to value-threshold
        distance = float(value) - float(threshold)
    if threshold == 0:
        ratio = None
    else:
        ratio = float(value) / float(threshold)
    return distance, ratio


# ─── Write API ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalise_event(fields: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults, compute distance/ratio, serialize payload_json."""
    if "phase" not in fields or "event" not in fields:
        raise ValueError("execution_timeline event requires phase and event")
    if "dedupe_key" not in fields or not fields["dedupe_key"]:
        raise ValueError("execution_timeline event requires non-empty dedupe_key")
    if "status" not in fields:
        raise ValueError("execution_timeline event requires status")

    payload = fields.get("payload_json")
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, default=str)

    distance, ratio = _compute_distance_ratio(
        fields.get("value"),
        fields.get("threshold"),
        fields.get("operator"),
    )

    out = {k: None for k in _FIELDS}
    out.update(
        {
            "timestamp": fields.get("timestamp") or _now_iso(),
            "closed_bar_ts": fields.get("closed_bar_ts"),
            "correlation_id": fields.get("correlation_id"),
            "attempt_id": fields.get("attempt_id"),
            "dedupe_key": fields["dedupe_key"],
            "trade_id": fields.get("trade_id"),
            "phase": fields["phase"],
            "event": fields["event"],
            "status": fields["status"],
            "severity": fields.get("severity"),
            "strategy": fields.get("strategy"),
            "symbol": fields.get("symbol"),
            "metric": fields.get("metric"),
            "value": fields.get("value"),
            "threshold": fields.get("threshold"),
            "operator": fields.get("operator"),
            "distance": fields.get("distance", distance),
            "ratio_to_threshold": fields.get("ratio_to_threshold", ratio),
            "message": fields.get("message"),
            "payload_json": payload,
        }
    )
    return out


def _insert_row(cursor: sqlite3.Cursor, row: dict[str, Any]) -> int | None:
    placeholders = ", ".join(["?"] * len(_FIELDS))
    cols = ", ".join(_FIELDS)
    cursor.execute(
        f"INSERT OR IGNORE INTO execution_timeline ({cols}) VALUES ({placeholders})",
        tuple(row[k] for k in _FIELDS),
    )
    return cursor.lastrowid if cursor.rowcount > 0 else None


def record_event(db_path: str, **fields: Any) -> int | None:
    """Insert one event. Returns the new row id, or None if dedupe_key collided."""
    row = _normalise_event(fields)
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        rowid = _insert_row(c, row)
        conn.commit()
        return rowid
    finally:
        conn.close()


def bulk_record_events(db_path: str, events: Iterable[dict[str, Any]]) -> list[int | None]:
    """Insert many events in a single transaction. Rolls back on any error.

    Returns list of row ids parallel to the input (None where dedupe_key collided).
    """
    rows = [_normalise_event(e) for e in events]
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        ids: list[int | None] = []
        try:
            for row in rows:
                ids.append(_insert_row(c, row))
            conn.commit()
            return ids
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


# ─── Read API ───────────────────────────────────────────────────────────────

def _row_to_dict(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _clamp_limit(limit: int) -> int:
    try:
        out = int(limit)
    except (TypeError, ValueError):
        out = 200
    return max(1, min(out, _MAX_LOAD_LIMIT))


def _market_time_expr(closed_bar_offset_seconds: int = 0) -> str:
    offset = int(closed_bar_offset_seconds or 0)
    closed_bar_expr = (
        f"closed_bar_ts + ({offset})"
        if offset
        else "closed_bar_ts"
    )
    return (
        "COALESCE("
        f"strftime('%H:%M', {closed_bar_expr}, 'unixepoch', 'localtime'), "
        "substr(replace(timestamp, ' ', 'T'), 12, 5)"
        ")"
    )


def load_timeline(
    db_path: str,
    *,
    limit: int = 200,
    phase: str | None = None,
    status: str | None = None,
    strategy: str | None = None,
    event: str | None = None,
    since: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    closed_bar_offset_seconds: int = 0,
) -> list[dict[str, Any]]:
    """Return events newest-first, with optional filters."""
    bounded_limit = _clamp_limit(limit)
    where: list[str] = []
    params: list[Any] = []
    if phase:
        where.append("phase = ?")
        params.append(phase)
    if status:
        where.append("status = ?")
        params.append(status)
    if strategy:
        where.append("strategy = ?")
        params.append(strategy)
    if event:
        where.append("event = ?")
        params.append(event)
    if since:
        where.append("timestamp >= ?")
        params.append(since)
    if time_start and time_end:
        where.append(
            f"{_market_time_expr(closed_bar_offset_seconds)} BETWEEN ? AND ?"
        )
        params.extend([time_start, time_end])

    sql = "SELECT * FROM execution_timeline"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(bounded_limit)

    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        c.execute(sql, params)
        rows = c.fetchall()
        return [_row_to_dict(c, r) for r in rows]
    finally:
        conn.close()


def current_bottleneck(
    db_path: str,
    *,
    time_start: str | None = None,
    time_end: str | None = None,
    closed_bar_offset_seconds: int = 0,
) -> dict[str, Any] | None:
    """First BLOCKED/FAILED event of the most recent closed bar, by funnel order.

    Returns None if the latest closed bar has no blocking events (funnel passed)
    or if no closed-bar events exist yet.
    """
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        where = ["closed_bar_ts IS NOT NULL"]
        params: list[Any] = []
        if time_start and time_end:
            where.append(
                f"{_market_time_expr(closed_bar_offset_seconds)} BETWEEN ? AND ?"
            )
            params.extend([time_start, time_end])
        c.execute(
            "SELECT MAX(closed_bar_ts) FROM execution_timeline "
            "WHERE " + " AND ".join(where),
            params,
        )
        row = c.fetchone()
        latest = row[0] if row else None
        if latest is None:
            return None

        placeholders = ", ".join(["?"] * len(_BLOCKING_STATUSES))
        candidate_where = [f"closed_bar_ts = ? AND status IN ({placeholders})"]
        candidate_params: list[Any] = [latest, *_BLOCKING_STATUSES]
        if time_start and time_end:
            candidate_where.append(
                f"{_market_time_expr(closed_bar_offset_seconds)} BETWEEN ? AND ?"
            )
            candidate_params.extend([time_start, time_end])
        c.execute(
            "SELECT * FROM execution_timeline WHERE " + " AND ".join(candidate_where),
            candidate_params,
        )
        candidates = [_row_to_dict(c, r) for r in c.fetchall()]
        if not candidates:
            return None

        phase_rank = {p: i for i, p in enumerate(PHASE_ORDER)}
        candidates.sort(
            key=lambda e: (
                phase_rank.get(e.get("phase"), len(PHASE_ORDER)),
                e.get("id", 0),
            )
        )
        return candidates[0]
    finally:
        conn.close()


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def current_live_issue(
    db_path: str,
    *,
    max_age_seconds: int | None = _DEFAULT_LIVE_ISSUE_MAX_AGE_SECONDS,
    now: datetime | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    closed_bar_offset_seconds: int = 0,
) -> dict[str, Any] | None:
    """Most recent unresolved DATA failure with no closed_bar_ts.

    Only recent DATA failures should keep the dashboard red. A later DATA
    recovery event (status != FAILED) clears the issue, and old failures expire
    by `max_age_seconds` so a transient outage does not remain "current"
    forever.
    """
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        where = ["closed_bar_ts IS NULL", "phase = 'DATA'"]
        params: list[Any] = []
        if time_start and time_end:
            where.append(
                f"{_market_time_expr(closed_bar_offset_seconds)} BETWEEN ? AND ?"
            )
            params.extend([time_start, time_end])
        c.execute(
            "SELECT * FROM execution_timeline "
            "WHERE " + " AND ".join(where) + " ORDER BY id DESC LIMIT 1",
            params,
        )
        row = c.fetchone()
        if not row:
            return None
        event = _row_to_dict(c, row)
        if event.get("status") != "FAILED":
            return None
        if max_age_seconds is not None:
            ts = _parse_iso_timestamp(event.get("timestamp"))
            if ts is not None:
                ref = now or datetime.now()
                if ts < ref - timedelta(seconds=max_age_seconds):
                    return None
        return event
    finally:
        conn.close()
