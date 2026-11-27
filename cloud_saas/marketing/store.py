# -*- coding: utf-8 -*-
"""Persistência SQLite do módulo de marketing: posts, trilha de eventos e chave geral de liga/desliga.

Arquivo próprio (marketing.db, ao lado do banco da API) para não depender dos dois backends de usuários.
Estados do post: draft -> approved -> publishing -> published | failed; draft/approved -> rejected.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

STATUSES = ("draft", "approved", "publishing", "published", "failed", "rejected")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MarketingStore:
    def __init__(self, path: str) -> None:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    asset TEXT NOT NULL DEFAULT '',
                    ref_date TEXT NOT NULL DEFAULT '',
                    caption TEXT NOT NULL DEFAULT '',
                    media_path TEXT NOT NULL DEFAULT '',
                    media_type TEXT NOT NULL DEFAULT '',
                    media_token TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    approved_by TEXT NOT NULL DEFAULT '',
                    approved_at TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL DEFAULT '',
                    external_id TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, created_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_events_post ON events(post_id);
                CREATE TABLE IF NOT EXISTS switches (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    # ── posts ──────────────────────────────────────────────────────────────
    def create_post(self, *, channel: str, kind: str, asset: str, ref_date: str, caption: str, actor: str) -> dict:
        post_id = secrets.token_hex(8)
        with self._lock:
            self._conn.execute(
                "INSERT INTO posts (id, channel, kind, asset, ref_date, caption, created_by, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (post_id, channel, kind, asset, ref_date, caption, actor, _now()),
            )
            self._conn.commit()
        self.add_event(post_id, actor, "created", {"channel": channel, "kind": kind})
        return self.get_post(post_id)  # type: ignore[return-value]

    def get_post(self, post_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(row) if row else None

    def get_post_by_token(self, token: str) -> Optional[dict]:
        if not token:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM posts WHERE media_token=?", (token,)).fetchone()
        return dict(row) if row else None

    def find_active(self, *, channel: str, kind: str, asset: str, ref_date: str) -> Optional[dict]:
        """Post ainda vivo (não rejeitado nem falho) para o mesmo canal, tipo, ativo e data."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM posts WHERE channel=? AND kind=? AND asset=? AND ref_date=?"
                " AND status NOT IN ('rejected','failed') ORDER BY created_at LIMIT 1",
                (channel, kind, asset, ref_date),
            ).fetchone()
        return dict(row) if row else None

    def list_posts(self, *, status: str = "", channel: str = "", limit: int = 100) -> list[dict]:
        sql, args = "SELECT * FROM posts WHERE 1=1", []
        if status:
            sql += " AND status=?"
            args.append(status)
        if channel:
            sql += " AND channel=?"
            args.append(channel)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def update_post(self, post_id: str, **fields: Any) -> dict:
        allowed = {
            "caption", "media_path", "media_type", "media_token", "status", "approved_by", "approved_at",
            "published_at", "external_id", "error",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"campos não permitidos: {sorted(bad)}")
        if fields.get("status") and fields["status"] not in STATUSES:
            raise ValueError(f"status inválido: {fields['status']}")
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            with self._lock:
                self._conn.execute(f"UPDATE posts SET {sets} WHERE id=?", (*fields.values(), post_id))
                self._conn.commit()
        return self.get_post(post_id)  # type: ignore[return-value]

    def claim_for_publishing(self, post_id: str) -> bool:
        """Transição atômica approved -> publishing; impede duas publicações simultâneas do mesmo post."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE posts SET status='publishing', error='' WHERE id=? AND status='approved'", (post_id,)
            )
            self._conn.commit()
            return cur.rowcount == 1

    def count_published_since(self, channel: str, since_iso: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM posts WHERE channel=? AND status='published' AND published_at>=?",
                (channel, since_iso),
            ).fetchone()
        return int(row[0])

    def counts_by_status(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) FROM posts GROUP BY status").fetchall()
        return {r[0]: int(r[1]) for r in rows}

    # ── eventos e chave geral ──────────────────────────────────────────────
    def add_event(self, post_id: str, actor: str, action: str, detail: Optional[dict] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (post_id, at, actor, action, detail) VALUES (?,?,?,?,?)",
                (post_id, _now(), actor, action, json.dumps(detail or {}, ensure_ascii=False)),
            )
            self._conn.commit()

    def list_events(self, post_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM events WHERE post_id=? ORDER BY id", (post_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_switch(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM switches WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_switch(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO switches (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()
