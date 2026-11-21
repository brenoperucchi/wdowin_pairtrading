# -*- coding: utf-8 -*-
"""Segurança: hash de senha PBKDF2, JWT HS256, HMAC-SHA256 de Push/Webhook/MT5 e alerta Telegram."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any, Optional

import httpx
import jwt


def hash_password(password: str, iterations: int = 260_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or not stored_hash:
        return False
    try:
        algo, iters_str, salt_hex, hash_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed, expected)
    except Exception:
        return False


def create_access_token(
    jwt_secret: str,
    user_id: int,
    email: str,
    plan: str,
    session_id: str,
    ttl_sec: int = 43200,
) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "plan": plan,
        "sid": session_id,
        "iat": now,
        "exp": now + int(ttl_sec),
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_access_token(jwt_secret: str, token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    try:
        return jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except Exception:
        return None


def compute_push_signature(
    secret: str,
    timestamp_str: str,
    producer_id: str,
    producer_role: str,
    body_bytes: bytes,
) -> str:
    prefix = f"{timestamp_str}.{producer_id}.{producer_role}.".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), prefix + body_bytes, hashlib.sha256).hexdigest()


def verify_push_signature(
    secret: str,
    timestamp_str: str,
    producer_id: str,
    producer_role: str,
    body_bytes: bytes,
    signature: str,
    max_skew_sec: int = 60,
) -> tuple[bool, str]:
    if not timestamp_str or not producer_id or not signature:
        return False, "HEADERS_INCOMPLETE"
    try:
        ts = int(float(timestamp_str))
    except ValueError:
        return False, "INVALID_TIMESTAMP"
    if abs(int(time.time()) - ts) > max_skew_sec:
        return False, "TIMESTAMP_EXPIRED"
    expected = compute_push_signature(secret, timestamp_str, producer_id, producer_role, body_bytes)
    if not hmac.compare_digest(expected, signature.strip().lower()):
        return False, "INVALID_SIGNATURE"
    return True, "OK"


def compute_webhook_signature(secret: str, body_bytes: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


def verify_webhook_signature(secret: str, body_bytes: bytes, signature: str) -> bool:
    if not secret or not signature:
        return False
    expected = compute_webhook_signature(secret, body_bytes)
    return hmac.compare_digest(expected, signature.strip().lower())


def sign_mt5_license(secret: str, account_login: int, valid_until: str, plan: str) -> str:
    msg = f"{account_login}:{valid_until}:{plan}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def notify_admin_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id or not text:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False
