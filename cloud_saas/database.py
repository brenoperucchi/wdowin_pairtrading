# -*- coding: utf-8 -*-
"""
Camada de persistência dual do Cloud SaaS MagicWalls:
- SupabaseRestDatabase: PostgreSQL / PostgREST via httpx (/rest/v1/) usando as 5+1 tabelas oficiais
  (profiles, subscriptions, active_sessions, terms_acceptance, audit_logs, producer_heartbeats).
- SQLiteDatabase: fallback local com o mesmo schema 5+1 para desenvolvimento e testes offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import secrets
import sqlite3
import threading
import time
from typing import Any, Optional, Sequence

import httpx

from cloud_saas.security import hash_password


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _clean_ip(ip: str) -> str:
    return (ip or "unknown").strip()[:64]


def _clean_fp(device_fp: str) -> str:
    return (device_fp or "unknown").strip()[:128]


def _clean_ua(user_agent: str) -> str:
    return (user_agent or "").strip()[:240]


def _resolve_mt5_token(
    plan: str,
    existing_token: Optional[str],
    mt5_license_token: Optional[str],
) -> str:
    if mt5_license_token is not None:
        return mt5_license_token
    if existing_token:
        return existing_token
    if plan in ("quant", "admin"):
        return secrets.token_urlsafe(18)
    return ""


def _compute_switch_stats(rows: Sequence[dict[str, Any]], max_switches: int) -> dict[str, Any]:
    switches = 0
    distinct_ips: set[str] = set()
    distinct_fps: set[str] = set()
    prev_pair: Optional[tuple[str, str]] = None
    for r in rows:
        ip = str(r.get("ip") or "")
        fp = str(r.get("device_fp") or "")
        distinct_ips.add(ip)
        distinct_fps.add(fp)
        pair = (ip, fp)
        if prev_pair is not None and pair != prev_pair:
            switches += 1
        prev_pair = pair
    return {
        "switches": switches,
        "distinct_ips": len(distinct_ips),
        "distinct_fps": len(distinct_fps),
        "blocked": switches > int(max_switches),
    }


def _compose_user_dict(
    profile: Optional[dict[str, Any]],
    sub: Optional[dict[str, Any]],
    latest_term: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    if not profile:
        return None
    is_blocked = bool(profile.get("is_blocked"))
    sub_data = sub or {}
    term_data = latest_term or {}
    sub_status = str(sub_data.get("status") or "suspended")
    effective_status = "blocked" if is_blocked else sub_status
    return {
        "id": int(profile["id"]),
        "email": profile["email"],
        "password_hash": profile["password_hash"],
        "full_name": profile.get("full_name") or "",
        "cpf_masked": profile.get("cpf_masked") or "",
        "role": profile.get("role") or "member",
        "is_blocked": is_blocked,
        "blocked_reason": profile.get("blocked_reason") or "",
        "plan": sub_data.get("plan") or "none",
        "status": effective_status,
        "expires_at": sub_data.get("expires_at"),
        "gateway": sub_data.get("gateway") or "",
        "external_sub_id": sub_data.get("external_sub_id") or "",
        "terms_version": term_data.get("terms_version") or "",
        "terms_accepted_at": term_data.get("accepted_at"),
        "terms_ip": term_data.get("ip") or "",
        "mt5_account_login": sub_data.get("mt5_account_login"),
        "mt5_license_token": sub_data.get("mt5_license_token") or "",
        "created_at": profile.get("created_at"),
        "last_login_at": profile.get("last_login_at"),
    }


def _build_abuse_flag_entry(row: dict[str, Any], email: str) -> dict[str, Any]:
    raw_details = row.get("details")
    if isinstance(raw_details, str):
        try:
            details = json.loads(raw_details) if raw_details else {}
        except Exception:
            details = {}
    elif isinstance(raw_details, dict):
        details = raw_details
    else:
        details = {}

    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "email": email,
        "trading_day": str(row.get("trading_day") or ""),
        "switch_count": int(details.get("switch_count") or 0),
        "distinct_ips": int(details.get("distinct_ips") or 0),
        "distinct_fps": int(details.get("distinct_fps") or 0),
        "action_taken": str(details.get("action_taken") or "blocked"),
        "resolved": bool(row.get("resolved")),
        "created_at": row.get("created_at"),
    }


class BaseDatabase:
    """Contrato comum para persistência SaaS (Supabase PostgREST ou SQLite local)."""

    backend_name = "base"

    def close(self) -> None:
        raise NotImplementedError

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def get_user_by_mt5_login_and_token(self, account_login: int, token: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def upsert_user(
        self,
        email: str,
        password: Optional[str] = None,
        full_name: str = "",
        cpf_masked: str = "",
        plan: str = "core",
        status: str = "active",
        expires_at: Optional[str] = None,
        mt5_account_login: Optional[int] = None,
        mt5_license_token: Optional[str] = None,
        terms_version: Optional[str] = None,
        gateway: str = "",
        external_sub_id: str = "",
    ) -> dict[str, Any]:
        raise NotImplementedError

    def update_user_status(self, user_id: int, status: str) -> None:
        raise NotImplementedError

    def accept_terms(self, user_id: int, terms_version: str, ip: str, user_agent: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def record_login_and_check_abuse(
        self,
        user_id: int,
        session_id: str,
        ip: str,
        device_fp: str,
        user_agent: str,
        max_switches: int,
        trading_day: Optional[str] = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def set_active_session(
        self,
        user_id: int,
        session_id: str,
        ip: str,
        device_fp: str,
        user_agent: str = "",
        trading_day: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    def clear_active_session(self, user_id: int, reason: str = "REVOKED") -> None:
        raise NotImplementedError

    def log_audit(
        self,
        user_id: Optional[int],
        event_type: str,
        ip: str = "",
        device_fp: str = "",
        user_agent: str = "",
        details: Optional[dict[str, Any]] = None,
        trading_day: Optional[str] = None,
        resolved: bool = False,
    ) -> None:
        raise NotImplementedError

    def unblock_user(self, user_id: int) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def update_producer_heartbeat(self, producer_id: str, role: str, payload_bytes: int, status: str) -> None:
        raise NotImplementedError

    def get_primary_heartbeat(self) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def get_latest_active_heartbeat(self) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def get_admin_overview(self) -> dict[str, Any]:
        raise NotImplementedError


class SQLiteDatabase(BaseDatabase):
    """Repositório SQLite local com schema espelho 5+1 do Supabase para dev/testes."""

    backend_name = "sqlite"

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    cpf_masked TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'member',
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    blocked_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    plan TEXT NOT NULL DEFAULT 'none',
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT,
                    gateway TEXT NOT NULL DEFAULT '',
                    external_sub_id TEXT NOT NULL DEFAULT '',
                    mt5_account_login INTEGER,
                    mt5_license_token TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_subscriptions_mt5_token
                    ON subscriptions(mt5_license_token);

                CREATE TABLE IF NOT EXISTS active_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    device_fp TEXT NOT NULL,
                    user_agent TEXT NOT NULL DEFAULT '',
                    trading_day TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    revoked_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_active_sessions_user_day
                    ON active_sessions(user_id, trading_day, id);

                CREATE INDEX IF NOT EXISTS idx_active_sessions_user_active
                    ON active_sessions(user_id, is_active);

                CREATE TABLE IF NOT EXISTS terms_acceptance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    terms_version TEXT NOT NULL,
                    ip TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    accepted_at TEXT NOT NULL,
                    UNIQUE (user_id, terms_version),
                    FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event_type TEXT NOT NULL,
                    ip TEXT NOT NULL DEFAULT '',
                    device_fp TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    trading_day TEXT,
                    details TEXT NOT NULL DEFAULT '{}',
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_logs_type_resolved
                    ON audit_logs(event_type, resolved, id DESC);

                CREATE TABLE IF NOT EXISTS producer_heartbeats (
                    producer_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    last_seen_ts REAL NOT NULL,
                    payload_bytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'online'
                );
                """
            )
            self._conn.commit()

    @staticmethod
    def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        return dict(row) if row is not None else None

    def _hydrate_user(self, profile_row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        profile = self._row_to_dict(profile_row)
        if not profile:
            return None
        uid = int(profile["id"])
        sub_row = self._conn.execute("SELECT * FROM subscriptions WHERE user_id = ? LIMIT 1", (uid,)).fetchone()
        term_row = self._conn.execute(
            "SELECT * FROM terms_acceptance WHERE user_id = ? ORDER BY accepted_at DESC, id DESC LIMIT 1",
            (uid,),
        ).fetchone()
        return _compose_user_dict(profile, self._row_to_dict(sub_row), self._row_to_dict(term_row))

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        clean = (email or "").strip().lower()
        if not clean:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM profiles WHERE email = ? LIMIT 1", (clean,)).fetchone()
            return self._hydrate_user(row)

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM profiles WHERE id = ? LIMIT 1", (int(user_id),)).fetchone()
            return self._hydrate_user(row)

    def get_user_by_mt5_login_and_token(self, account_login: int, token: str) -> Optional[dict[str, Any]]:
        clean_tok = (token or "").strip()
        if not clean_tok:
            return None
        with self._lock:
            sub = self._conn.execute(
                "SELECT user_id FROM subscriptions WHERE mt5_license_token = ? LIMIT 1",
                (clean_tok,),
            ).fetchone()
            if not sub:
                return None
            return self.get_user_by_id(int(sub["user_id"]))

    def upsert_user(
        self,
        email: str,
        password: Optional[str] = None,
        full_name: str = "",
        cpf_masked: str = "",
        plan: str = "core",
        status: str = "active",
        expires_at: Optional[str] = None,
        mt5_account_login: Optional[int] = None,
        mt5_license_token: Optional[str] = None,
        terms_version: Optional[str] = None,
        gateway: str = "",
        external_sub_id: str = "",
    ) -> dict[str, Any]:
        clean_email = email.strip().lower()
        now = utc_now_iso()
        role = "admin" if plan == "admin" else "member"
        is_blocked = 1 if status == "blocked" else 0
        blocked_reason = "ADMIN_BLOCK" if is_blocked else ""

        with self._lock:
            existing = self.get_user_by_email(clean_email)
            if existing is None:
                pw = password or secrets.token_urlsafe(12)
                tok = _resolve_mt5_token(plan, None, mt5_license_token)
                cur = self._conn.execute(
                    """
                    INSERT INTO profiles (
                        email, password_hash, full_name, cpf_masked, role, is_blocked,
                        blocked_reason, created_at, last_login_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (clean_email, hash_password(pw), full_name, cpf_masked, role, is_blocked, blocked_reason, now, None),
                )
                uid = int(cur.lastrowid)
                self._conn.execute(
                    """
                    INSERT INTO subscriptions (
                        user_id, plan, status, expires_at, gateway, external_sub_id,
                        mt5_account_login, mt5_license_token, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uid, plan, status, expires_at, gateway, external_sub_id, mt5_account_login, tok, now),
                )
                if terms_version:
                    self._conn.execute(
                        """
                        INSERT INTO terms_acceptance (user_id, terms_version, ip, user_agent, accepted_at)
                        VALUES (?, ?, 'admin-seed', 'admin-seed', ?)
                        """,
                        (uid, terms_version, now),
                    )
                self._conn.commit()
                return self.get_user_by_id(uid)  # type: ignore[return-value]

            uid = int(existing["id"])
            new_pw_hash = hash_password(password) if password else existing["password_hash"]
            new_tok = _resolve_mt5_token(plan, existing.get("mt5_license_token"), mt5_license_token)
            self._conn.execute(
                """
                UPDATE profiles SET
                    password_hash = ?,
                    full_name = CASE WHEN ? != '' THEN ? ELSE full_name END,
                    cpf_masked = CASE WHEN ? != '' THEN ? ELSE cpf_masked END,
                    role = ?,
                    is_blocked = ?,
                    blocked_reason = CASE WHEN ? = 1 THEN blocked_reason ELSE '' END
                WHERE id = ?
                """,
                (new_pw_hash, full_name, full_name, cpf_masked, cpf_masked, role, is_blocked, is_blocked, uid),
            )
            self._conn.execute(
                """
                UPDATE subscriptions SET
                    plan = ?,
                    status = ?,
                    expires_at = ?,
                    gateway = CASE WHEN ? != '' THEN ? ELSE gateway END,
                    external_sub_id = CASE WHEN ? != '' THEN ? ELSE external_sub_id END,
                    mt5_account_login = CASE WHEN ? IS NOT NULL THEN ? ELSE mt5_account_login END,
                    mt5_license_token = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    plan,
                    status,
                    expires_at,
                    gateway,
                    gateway,
                    external_sub_id,
                    external_sub_id,
                    mt5_account_login,
                    mt5_account_login,
                    new_tok,
                    now,
                    uid,
                ),
            )
            if terms_version:
                self._conn.execute(
                    """
                    INSERT INTO terms_acceptance (user_id, terms_version, ip, user_agent, accepted_at)
                    VALUES (?, ?, 'admin-seed', 'admin-seed', ?)
                    ON CONFLICT(user_id, terms_version) DO UPDATE SET accepted_at = excluded.accepted_at
                    """,
                    (uid, terms_version, now),
                )
            self._conn.commit()
            return self.get_user_by_id(uid)  # type: ignore[return-value]

    def update_user_status(self, user_id: int, status: str) -> None:
        now = utc_now_iso()
        is_blocked = 1 if status == "blocked" else 0
        with self._lock:
            self._conn.execute(
                "UPDATE profiles SET is_blocked = ? WHERE id = ?",
                (is_blocked, int(user_id)),
            )
            self._conn.execute(
                "UPDATE subscriptions SET status = ?, updated_at = ? WHERE user_id = ?",
                (status, now, int(user_id)),
            )
            self._conn.commit()

    def accept_terms(self, user_id: int, terms_version: str, ip: str, user_agent: str = "") -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO terms_acceptance (user_id, terms_version, ip, user_agent, accepted_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, terms_version) DO UPDATE SET
                    ip = excluded.ip,
                    user_agent = excluded.user_agent,
                    accepted_at = excluded.accepted_at
                """,
                (int(user_id), terms_version, (ip or "")[:64], _clean_ua(user_agent), now),
            )
            self._conn.commit()
            return self.get_user_by_id(user_id)  # type: ignore[return-value]

    def record_login_and_check_abuse(
        self,
        user_id: int,
        session_id: str,
        ip: str,
        device_fp: str,
        user_agent: str,
        max_switches: int,
        trading_day: Optional[str] = None,
    ) -> dict[str, Any]:
        day = trading_day or utc_today_str()
        now = utc_now_iso()
        clean_ip = _clean_ip(ip)
        clean_fp = _clean_fp(device_fp)
        clean_ua = _clean_ua(user_agent)
        uid = int(user_id)

        with self._lock:
            self._conn.execute("UPDATE profiles SET last_login_at = ? WHERE id = ?", (now, uid))
            self._conn.execute(
                """
                UPDATE active_sessions SET is_active = 0, revoked_reason = 'SESSION_REPLACED', revoked_at = ?
                WHERE user_id = ? AND is_active = 1
                """,
                (now, uid),
            )
            self._conn.execute(
                """
                INSERT INTO active_sessions (
                    user_id, session_id, ip, device_fp, user_agent, trading_day, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (uid, session_id, clean_ip, clean_fp, clean_ua, day, now),
            )
            rows = self._conn.execute(
                "SELECT ip, device_fp FROM active_sessions WHERE user_id = ? AND trading_day = ? ORDER BY id ASC",
                (uid, day),
            ).fetchall()
            stats = _compute_switch_stats([dict(r) for r in rows], max_switches)

            if stats["blocked"]:
                self._conn.execute(
                    "UPDATE profiles SET is_blocked = 1, blocked_reason = 'ABUSE_DEVICE_SWITCHES' WHERE id = ?",
                    (uid,),
                )
                self._conn.execute(
                    "UPDATE subscriptions SET status = 'blocked', updated_at = ? WHERE user_id = ?",
                    (now, uid),
                )
                self._conn.execute(
                    """
                    UPDATE active_sessions SET is_active = 0, revoked_reason = 'ABUSE_BLOCKED', revoked_at = ?
                    WHERE user_id = ? AND is_active = 1
                    """,
                    (now, uid),
                )
                details = json.dumps(
                    {
                        "switch_count": stats["switches"],
                        "distinct_ips": stats["distinct_ips"],
                        "distinct_fps": stats["distinct_fps"],
                        "action_taken": "blocked",
                    },
                    separators=(",", ":"),
                )
                self._conn.execute(
                    """
                    INSERT INTO audit_logs (
                        user_id, event_type, ip, device_fp, user_agent, trading_day, details, resolved, created_at
                    ) VALUES (?, 'ABUSE_BLOCKED', ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (uid, clean_ip, clean_fp, clean_ua, day, details, now),
                )

            self._conn.commit()
            return {"trading_day": day, **stats}

    def set_active_session(
        self,
        user_id: int,
        session_id: str,
        ip: str,
        device_fp: str,
        user_agent: str = "",
        trading_day: Optional[str] = None,
    ) -> None:
        uid = int(user_id)
        now = utc_now_iso()
        day = trading_day or utc_today_str()
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM active_sessions WHERE user_id = ? AND session_id = ? LIMIT 1",
                (uid, session_id),
            ).fetchone()
            self._conn.execute(
                """
                UPDATE active_sessions SET is_active = 0, revoked_reason = 'SESSION_REPLACED', revoked_at = ?
                WHERE user_id = ? AND is_active = 1 AND session_id != ?
                """,
                (now, uid, session_id),
            )
            if existing:
                self._conn.execute(
                    "UPDATE active_sessions SET is_active = 1, revoked_reason = '', revoked_at = NULL WHERE id = ?",
                    (existing["id"],),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO active_sessions (
                        user_id, session_id, ip, device_fp, user_agent, trading_day, is_active, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (uid, session_id, _clean_ip(ip), _clean_fp(device_fp), _clean_ua(user_agent), day, now),
                )
            self._conn.commit()

    def clear_active_session(self, user_id: int, reason: str = "REVOKED") -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE active_sessions SET is_active = 0, revoked_reason = ?, revoked_at = ?
                WHERE user_id = ? AND is_active = 1
                """,
                (reason[:64], now, int(user_id)),
            )
            self._conn.commit()

    def log_audit(
        self,
        user_id: Optional[int],
        event_type: str,
        ip: str = "",
        device_fp: str = "",
        user_agent: str = "",
        details: Optional[dict[str, Any]] = None,
        trading_day: Optional[str] = None,
        resolved: bool = False,
    ) -> None:
        now = utc_now_iso()
        payload = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_logs (
                    user_id, event_type, ip, device_fp, user_agent, trading_day, details, resolved, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id) if user_id is not None else None,
                    event_type,
                    (ip or "")[:64],
                    (device_fp or "")[:128],
                    _clean_ua(user_agent),
                    trading_day or utc_today_str(),
                    payload,
                    1 if resolved else 0,
                    now,
                ),
            )
            self._conn.commit()

    def unblock_user(self, user_id: int) -> Optional[dict[str, Any]]:
        uid = int(user_id)
        day = utc_today_str()
        now = utc_now_iso()
        with self._lock:
            existing = self.get_user_by_id(uid)
            if not existing:
                return None
            self._conn.execute(
                "UPDATE profiles SET is_blocked = 0, blocked_reason = '' WHERE id = ?",
                (uid,),
            )
            self._conn.execute(
                "UPDATE subscriptions SET status = 'active', updated_at = ? WHERE user_id = ?",
                (now, uid),
            )
            self._conn.execute(
                "UPDATE audit_logs SET resolved = 1 WHERE user_id = ? AND event_type = 'ABUSE_BLOCKED' AND resolved = 0",
                (uid,),
            )
            self._conn.execute(
                "DELETE FROM active_sessions WHERE user_id = ? AND trading_day = ?",
                (uid, day),
            )
            self._conn.execute(
                """
                INSERT INTO audit_logs (user_id, event_type, trading_day, details, resolved, created_at)
                VALUES (?, 'ADMIN_UNBLOCK', ?, '{"action":"unblocked"}', 1, ?)
                """,
                (uid, day, now),
            )
            self._conn.commit()
            return self.get_user_by_id(uid)

    def update_producer_heartbeat(self, producer_id: str, role: str, payload_bytes: int, status: str) -> None:
        now_ts = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO producer_heartbeats (producer_id, role, last_seen_ts, payload_bytes, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(producer_id) DO UPDATE SET
                    role = excluded.role,
                    last_seen_ts = excluded.last_seen_ts,
                    payload_bytes = excluded.payload_bytes,
                    status = excluded.status
                """,
                (producer_id, role, now_ts, int(payload_bytes), status),
            )
            self._conn.commit()

    def get_primary_heartbeat(self) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM producer_heartbeats WHERE role = 'primary' ORDER BY last_seen_ts DESC LIMIT 1"
            ).fetchone()
            return self._row_to_dict(row)

    def get_latest_active_heartbeat(self) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM producer_heartbeats WHERE status = 'active' ORDER BY last_seen_ts DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                return self._row_to_dict(row)
            row = self._conn.execute(
                "SELECT * FROM producer_heartbeats ORDER BY last_seen_ts DESC LIMIT 1"
            ).fetchone()
            return self._row_to_dict(row)

    def get_admin_overview(self) -> dict[str, Any]:
        with self._lock:
            plan_rows = self._conn.execute(
                """
                SELECT s.plan,
                       CASE WHEN p.is_blocked = 1 THEN 'blocked' ELSE s.status END AS status,
                       COUNT(*) AS cnt
                FROM subscriptions s
                JOIN profiles p ON p.id = s.user_id
                GROUP BY s.plan, CASE WHEN p.is_blocked = 1 THEN 'blocked' ELSE s.status END
                """
            ).fetchall()
            users_rows = self._conn.execute(
                """
                SELECT p.id, p.email, p.full_name, s.plan,
                       CASE WHEN p.is_blocked = 1 THEN 'blocked' ELSE s.status END AS status,
                       s.expires_at,
                       COALESCE((
                           SELECT t.terms_version FROM terms_acceptance t
                           WHERE t.user_id = p.id ORDER BY t.accepted_at DESC, t.id DESC LIMIT 1
                       ), '') AS terms_version,
                       s.mt5_account_login,
                       p.last_login_at
                FROM profiles p
                LEFT JOIN subscriptions s ON s.user_id = p.id
                ORDER BY p.id DESC LIMIT 100
                """
            ).fetchall()
            flags_rows = self._conn.execute(
                """
                SELECT a.*, p.email
                FROM audit_logs a
                LEFT JOIN profiles p ON p.id = a.user_id
                WHERE a.event_type = 'ABUSE_BLOCKED' AND a.resolved = 0
                ORDER BY a.id DESC LIMIT 50
                """
            ).fetchall()
            hb_rows = self._conn.execute(
                "SELECT * FROM producer_heartbeats ORDER BY last_seen_ts DESC"
            ).fetchall()

            return {
                "summary": [dict(r) for r in plan_rows],
                "users": [dict(r) for r in users_rows],
                "open_abuse_flags": [
                    _build_abuse_flag_entry(dict(r), str(r["email"] or "")) for r in flags_rows
                ],
                "producers": [dict(r) for r in hb_rows],
            }


def build_supabase_headers(api_key: str) -> dict[str, str]:
    """Monta headers PostgREST compatíveis com chaves novas (sb_secret_*) e JWT legado (service_role)."""
    clean = (api_key or "").strip()
    headers = {
        "apikey": clean,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # Chaves novas do Supabase (sb_secret_... / sb_publishable_...) são opacas (não-JWT)
    # e devem ir apenas no header `apikey`; chaves legadas JWT (service_role) aceitam Bearer.
    if clean and not clean.startswith("sb_"):
        headers["Authorization"] = f"Bearer {clean}"
    return headers


class SupabaseRestDatabase(BaseDatabase):
    """Cliente PostgreSQL/PostgREST para Supabase via HTTPS (sem driver nativo compilado)."""

    backend_name = "supabase"

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        timeout: float = 8.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.rest_base = f"{supabase_url.rstrip('/')}/rest/v1"
        self._headers = build_supabase_headers(service_role_key)
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, headers=self._headers)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(
        self,
        method: str,
        table: str,
        params: Optional[dict[str, str]] = None,
        json_body: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        url = f"{self.rest_base}/{table.lstrip('/')}"
        resp = self._client.request(method, url, params=params, json=json_body, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase PostgREST {method} {table} -> HTTP {resp.status_code}: {resp.text[:300]}")
        if not resp.content:
            return []
        try:
            return resp.json()
        except Exception:
            return []

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        data = self._request("GET", table, params=params)
        return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])

    def _post(
        self,
        table: str,
        payload: dict[str, Any],
        params: Optional[dict[str, str]] = None,
        prefer: str = "return=representation",
    ) -> list[dict[str, Any]]:
        data = self._request("POST", table, params=params, json_body=payload, prefer=prefer)
        return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])

    def _patch(self, table: str, params: dict[str, str], payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._request("PATCH", table, params=params, json_body=payload, prefer="return=representation")
        return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])

    def _delete(self, table: str, params: dict[str, str]) -> None:
        self._request("DELETE", table, params=params, prefer="return=minimal")

    def _hydrate_profile(self, profile: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not profile:
            return None
        uid = int(profile["id"])
        subs = self._get("subscriptions", {"user_id": f"eq.{uid}", "limit": "1"})
        terms = self._get("terms_acceptance", {"user_id": f"eq.{uid}", "order": "accepted_at.desc,id.desc", "limit": "1"})
        return _compose_user_dict(profile, subs[0] if subs else None, terms[0] if terms else None)

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        clean = (email or "").strip().lower()
        if not clean:
            return None
        rows = self._get("profiles", {"email": f"eq.{clean}", "limit": "1"})
        return self._hydrate_profile(rows[0] if rows else None)

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        rows = self._get("profiles", {"id": f"eq.{int(user_id)}", "limit": "1"})
        return self._hydrate_profile(rows[0] if rows else None)

    def get_user_by_mt5_login_and_token(self, account_login: int, token: str) -> Optional[dict[str, Any]]:
        clean_tok = (token or "").strip()
        if not clean_tok:
            return None
        subs = self._get("subscriptions", {"mt5_license_token": f"eq.{clean_tok}", "limit": "1"})
        if not subs:
            return None
        return self.get_user_by_id(int(subs[0]["user_id"]))

    def upsert_user(
        self,
        email: str,
        password: Optional[str] = None,
        full_name: str = "",
        cpf_masked: str = "",
        plan: str = "core",
        status: str = "active",
        expires_at: Optional[str] = None,
        mt5_account_login: Optional[int] = None,
        mt5_license_token: Optional[str] = None,
        terms_version: Optional[str] = None,
        gateway: str = "",
        external_sub_id: str = "",
    ) -> dict[str, Any]:
        clean_email = email.strip().lower()
        now = utc_now_iso()
        role = "admin" if plan == "admin" else "member"
        is_blocked = status == "blocked"
        existing = self.get_user_by_email(clean_email)

        if existing is None:
            pw = password or secrets.token_urlsafe(12)
            tok = _resolve_mt5_token(plan, None, mt5_license_token)
            prof_rows = self._post(
                "profiles",
                {
                    "email": clean_email,
                    "password_hash": hash_password(pw),
                    "full_name": full_name,
                    "cpf_masked": cpf_masked,
                    "role": role,
                    "is_blocked": is_blocked,
                    "blocked_reason": "ADMIN_BLOCK" if is_blocked else "",
                    "created_at": now,
                },
            )
            uid = int(prof_rows[0]["id"])
            self._post(
                "subscriptions",
                {
                    "user_id": uid,
                    "plan": plan,
                    "status": status,
                    "expires_at": expires_at,
                    "gateway": gateway,
                    "external_sub_id": external_sub_id,
                    "mt5_account_login": mt5_account_login,
                    "mt5_license_token": tok,
                    "updated_at": now,
                },
                params={"on_conflict": "user_id"},
                prefer="resolution=merge-duplicates,return=representation",
            )
        else:
            uid = int(existing["id"])
            new_pw_hash = hash_password(password) if password else existing["password_hash"]
            new_tok = _resolve_mt5_token(plan, existing.get("mt5_license_token"), mt5_license_token)
            prof_patch: dict[str, Any] = {
                "password_hash": new_pw_hash,
                "role": role,
                "is_blocked": is_blocked,
            }
            if full_name:
                prof_patch["full_name"] = full_name
            if cpf_masked:
                prof_patch["cpf_masked"] = cpf_masked
            if not is_blocked:
                prof_patch["blocked_reason"] = ""
            self._patch("profiles", {"id": f"eq.{uid}"}, prof_patch)

            sub_patch: dict[str, Any] = {
                "user_id": uid,
                "plan": plan,
                "status": status,
                "expires_at": expires_at,
                "mt5_license_token": new_tok,
                "updated_at": now,
                "gateway": gateway or existing.get("gateway") or "",
                "external_sub_id": external_sub_id or existing.get("external_sub_id") or "",
                "mt5_account_login": (
                    mt5_account_login if mt5_account_login is not None else existing.get("mt5_account_login")
                ),
            }
            self._post(
                "subscriptions",
                sub_patch,
                params={"on_conflict": "user_id"},
                prefer="resolution=merge-duplicates,return=representation",
            )

        if terms_version:
            self._post(
                "terms_acceptance",
                {
                    "user_id": uid,
                    "terms_version": terms_version,
                    "ip": "admin-seed",
                    "user_agent": "admin-seed",
                    "accepted_at": now,
                },
                params={"on_conflict": "user_id,terms_version"},
                prefer="resolution=merge-duplicates,return=representation",
            )

        return self.get_user_by_id(uid)  # type: ignore[return-value]

    def update_user_status(self, user_id: int, status: str) -> None:
        uid = int(user_id)
        now = utc_now_iso()
        self._patch("profiles", {"id": f"eq.{uid}"}, {"is_blocked": status == "blocked"})
        self._patch("subscriptions", {"user_id": f"eq.{uid}"}, {"status": status, "updated_at": now})

    def accept_terms(self, user_id: int, terms_version: str, ip: str, user_agent: str = "") -> dict[str, Any]:
        uid = int(user_id)
        now = utc_now_iso()
        self._post(
            "terms_acceptance",
            {
                "user_id": uid,
                "terms_version": terms_version,
                "ip": (ip or "")[:64],
                "user_agent": _clean_ua(user_agent),
                "accepted_at": now,
            },
            params={"on_conflict": "user_id,terms_version"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        return self.get_user_by_id(uid)  # type: ignore[return-value]

    def record_login_and_check_abuse(
        self,
        user_id: int,
        session_id: str,
        ip: str,
        device_fp: str,
        user_agent: str,
        max_switches: int,
        trading_day: Optional[str] = None,
    ) -> dict[str, Any]:
        uid = int(user_id)
        day = trading_day or utc_today_str()
        now = utc_now_iso()
        clean_ip = _clean_ip(ip)
        clean_fp = _clean_fp(device_fp)
        clean_ua = _clean_ua(user_agent)

        self._patch("profiles", {"id": f"eq.{uid}"}, {"last_login_at": now})
        self._patch(
            "active_sessions",
            {"user_id": f"eq.{uid}", "is_active": "eq.true"},
            {"is_active": False, "revoked_reason": "SESSION_REPLACED", "revoked_at": now},
        )
        self._post(
            "active_sessions",
            {
                "user_id": uid,
                "session_id": session_id,
                "ip": clean_ip,
                "device_fp": clean_fp,
                "user_agent": clean_ua,
                "trading_day": day,
                "is_active": True,
                "created_at": now,
            },
        )
        rows = self._get(
            "active_sessions",
            {
                "select": "ip,device_fp",
                "user_id": f"eq.{uid}",
                "trading_day": f"eq.{day}",
                "order": "id.asc",
            },
        )
        stats = _compute_switch_stats(rows, max_switches)
        if stats["blocked"]:
            self._patch(
                "profiles",
                {"id": f"eq.{uid}"},
                {"is_blocked": True, "blocked_reason": "ABUSE_DEVICE_SWITCHES"},
            )
            self._patch(
                "subscriptions",
                {"user_id": f"eq.{uid}"},
                {"status": "blocked", "updated_at": now},
            )
            self._patch(
                "active_sessions",
                {"user_id": f"eq.{uid}", "is_active": "eq.true"},
                {"is_active": False, "revoked_reason": "ABUSE_BLOCKED", "revoked_at": now},
            )
            self.log_audit(
                user_id=uid,
                event_type="ABUSE_BLOCKED",
                ip=clean_ip,
                device_fp=clean_fp,
                user_agent=clean_ua,
                trading_day=day,
                resolved=False,
                details={
                    "switch_count": stats["switches"],
                    "distinct_ips": stats["distinct_ips"],
                    "distinct_fps": stats["distinct_fps"],
                    "action_taken": "blocked",
                },
            )
        return {"trading_day": day, **stats}

    def set_active_session(
        self,
        user_id: int,
        session_id: str,
        ip: str,
        device_fp: str,
        user_agent: str = "",
        trading_day: Optional[str] = None,
    ) -> None:
        uid = int(user_id)
        now = utc_now_iso()
        day = trading_day or utc_today_str()
        self._patch(
            "active_sessions",
            {"user_id": f"eq.{uid}", "is_active": "eq.true", "session_id": f"neq.{session_id}"},
            {"is_active": False, "revoked_reason": "SESSION_REPLACED", "revoked_at": now},
        )
        existing = self._get(
            "active_sessions",
            {"select": "id", "user_id": f"eq.{uid}", "session_id": f"eq.{session_id}", "limit": "1"},
        )
        if existing:
            self._patch(
                "active_sessions",
                {"id": f"eq.{existing[0]['id']}"},
                {"is_active": True, "revoked_reason": "", "revoked_at": None},
            )
        else:
            self._post(
                "active_sessions",
                {
                    "user_id": uid,
                    "session_id": session_id,
                    "ip": _clean_ip(ip),
                    "device_fp": _clean_fp(device_fp),
                    "user_agent": _clean_ua(user_agent),
                    "trading_day": day,
                    "is_active": True,
                    "created_at": now,
                },
            )

    def clear_active_session(self, user_id: int, reason: str = "REVOKED") -> None:
        now = utc_now_iso()
        self._patch(
            "active_sessions",
            {"user_id": f"eq.{int(user_id)}", "is_active": "eq.true"},
            {"is_active": False, "revoked_reason": reason[:64], "revoked_at": now},
        )

    def log_audit(
        self,
        user_id: Optional[int],
        event_type: str,
        ip: str = "",
        device_fp: str = "",
        user_agent: str = "",
        details: Optional[dict[str, Any]] = None,
        trading_day: Optional[str] = None,
        resolved: bool = False,
    ) -> None:
        self._post(
            "audit_logs",
            {
                "user_id": int(user_id) if user_id is not None else None,
                "event_type": event_type,
                "ip": (ip or "")[:64],
                "device_fp": (device_fp or "")[:128],
                "user_agent": _clean_ua(user_agent),
                "trading_day": trading_day or utc_today_str(),
                "details": details or {},
                "resolved": bool(resolved),
                "created_at": utc_now_iso(),
            },
            prefer="return=minimal",
        )

    def unblock_user(self, user_id: int) -> Optional[dict[str, Any]]:
        uid = int(user_id)
        existing = self.get_user_by_id(uid)
        if not existing:
            return None
        day = utc_today_str()
        now = utc_now_iso()
        self._patch("profiles", {"id": f"eq.{uid}"}, {"is_blocked": False, "blocked_reason": ""})
        self._patch("subscriptions", {"user_id": f"eq.{uid}"}, {"status": "active", "updated_at": now})
        self._patch(
            "audit_logs",
            {"user_id": f"eq.{uid}", "event_type": "eq.ABUSE_BLOCKED", "resolved": "eq.false"},
            {"resolved": True},
        )
        self._delete("active_sessions", {"user_id": f"eq.{uid}", "trading_day": f"eq.{day}"})
        self.log_audit(uid, "ADMIN_UNBLOCK", trading_day=day, resolved=True, details={"action": "unblocked"})
        return self.get_user_by_id(uid)

    def update_producer_heartbeat(self, producer_id: str, role: str, payload_bytes: int, status: str) -> None:
        self._post(
            "producer_heartbeats",
            {
                "producer_id": producer_id,
                "role": role,
                "last_seen_ts": time.time(),
                "payload_bytes": int(payload_bytes),
                "status": status,
            },
            params={"on_conflict": "producer_id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def get_primary_heartbeat(self) -> Optional[dict[str, Any]]:
        rows = self._get(
            "producer_heartbeats",
            {"role": "eq.primary", "order": "last_seen_ts.desc", "limit": "1"},
        )
        return rows[0] if rows else None

    def get_latest_active_heartbeat(self) -> Optional[dict[str, Any]]:
        rows = self._get(
            "producer_heartbeats",
            {"status": "eq.active", "order": "last_seen_ts.desc", "limit": "1"},
        )
        if rows:
            return rows[0]
        rows = self._get("producer_heartbeats", {"order": "last_seen_ts.desc", "limit": "1"})
        return rows[0] if rows else None

    def get_admin_overview(self) -> dict[str, Any]:
        profiles = self._get(
            "profiles",
            {"select": "id,email,full_name,is_blocked,created_at,last_login_at", "order": "id.desc", "limit": "100"},
        )
        subs = self._get("subscriptions", {"select": "user_id,plan,status,expires_at,mt5_account_login"})
        terms = self._get(
            "terms_acceptance",
            {"select": "user_id,terms_version,accepted_at", "order": "accepted_at.desc,id.desc"},
        )
        flags = self._get(
            "audit_logs",
            {"event_type": "eq.ABUSE_BLOCKED", "resolved": "eq.false", "order": "id.desc", "limit": "50"},
        )
        hbs = self._get("producer_heartbeats", {"order": "last_seen_ts.desc"})

        sub_by_uid = {int(s["user_id"]): s for s in subs if s.get("user_id") is not None}
        term_by_uid: dict[int, dict[str, Any]] = {}
        for t in terms:
            uid = t.get("user_id")
            if uid is not None and int(uid) not in term_by_uid:
                term_by_uid[int(uid)] = t
        email_by_uid = {int(p["id"]): str(p.get("email") or "") for p in profiles if p.get("id") is not None}

        summary_counts: dict[tuple[str, str], int] = {}
        users_out: list[dict[str, Any]] = []
        for p in profiles:
            uid = int(p["id"])
            s = sub_by_uid.get(uid, {})
            t = term_by_uid.get(uid, {})
            plan = str(s.get("plan") or "none")
            status = "blocked" if p.get("is_blocked") else str(s.get("status") or "suspended")
            summary_counts[(plan, status)] = summary_counts.get((plan, status), 0) + 1
            users_out.append(
                {
                    "id": uid,
                    "email": p["email"],
                    "full_name": p.get("full_name") or "",
                    "plan": plan,
                    "status": status,
                    "expires_at": s.get("expires_at"),
                    "terms_version": t.get("terms_version") or "",
                    "mt5_account_login": s.get("mt5_account_login"),
                    "last_login_at": p.get("last_login_at"),
                }
            )

        summary_out = [{"plan": k[0], "status": k[1], "cnt": v} for k, v in summary_counts.items()]
        flags_out = [
            _build_abuse_flag_entry(f, email_by_uid.get(int(f["user_id"]), "") if f.get("user_id") else "")
            for f in flags
        ]
        return {
            "summary": summary_out,
            "users": users_out,
            "open_abuse_flags": flags_out,
            "producers": hbs,
        }


Database = SQLiteDatabase


def create_database(settings) -> BaseDatabase:
    if getattr(settings, "supabase_url", "") and getattr(settings, "supabase_service_role_key", ""):
        return SupabaseRestDatabase(
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
        )
    return SQLiteDatabase(settings.db_path)
