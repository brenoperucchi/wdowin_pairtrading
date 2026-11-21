# -*- coding: utf-8 -*-
"""Camada de cache em memória ultra-rápida: Upstash Redis REST em produção, MemoryTTLStore em dev/testes."""

from __future__ import annotations

import base64
import json
import threading
import time
from typing import Any, Optional

import httpx


class BaseCacheStore:
    """Interface comum para armazenamento chave-valor com TTL."""

    backend_name = "base"

    def get_json(self, key: str) -> Optional[Any]:
        raw = self.get_bytes(key)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_sec: Optional[int] = None) -> None:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.set_bytes(key, raw, ttl_sec=ttl_sec)

    def get_bytes(self, key: str) -> Optional[bytes]:
        raise NotImplementedError

    def set_bytes(self, key: str, data: bytes, ttl_sec: Optional[int] = None) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class MemoryTTLStore(BaseCacheStore):
    """Store em memória thread-safe com TTL para desenvolvimento e testes locais."""

    backend_name = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, tuple[bytes, Optional[float]]] = {}

    def get_bytes(self, key: str) -> Optional[bytes]:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            payload, exp = item
            if exp is not None and now >= exp:
                self._data.pop(key, None)
                return None
            return payload

    def set_bytes(self, key: str, data: bytes, ttl_sec: Optional[int] = None) -> None:
        exp = (time.monotonic() + ttl_sec) if (ttl_sec and ttl_sec > 0) else None
        with self._lock:
            self._data[key] = (bytes(data), exp)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class UpstashRestStore(BaseCacheStore):
    """Cliente REST síncrono/thread-safe para Upstash Redis."""

    backend_name = "upstash_redis"

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 4.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, headers=self._headers)

    def _cmd(self, args: list[Any]) -> Any:
        resp = self._client.post(self.base_url, json=args, headers=self._headers)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict) and body.get("error"):
            raise RuntimeError(f"Upstash error: {body['error']}")
        return body.get("result") if isinstance(body, dict) else None

    def get_bytes(self, key: str) -> Optional[bytes]:
        val = self._cmd(["GET", key])
        if val is None:
            return None
        if isinstance(val, str) and val.startswith("b64:"):
            return base64.b64decode(val[4:].encode("ascii"))
        return str(val).encode("utf-8")

    def set_bytes(self, key: str, data: bytes, ttl_sec: Optional[int] = None) -> None:
        encoded = "b64:" + base64.b64encode(data).decode("ascii")
        if ttl_sec and ttl_sec > 0:
            self._cmd(["SET", key, encoded, "EX", int(ttl_sec)])
        else:
            self._cmd(["SET", key, encoded])

    def delete(self, key: str) -> None:
        self._cmd(["DEL", key])


def create_store(settings) -> BaseCacheStore:
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        return UpstashRestStore(
            base_url=settings.upstash_redis_rest_url,
            token=settings.upstash_redis_rest_token,
        )
    return MemoryTTLStore()
