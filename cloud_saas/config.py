# -*- coding: utf-8 -*-
"""Configuração 100% via variáveis de ambiente para a API Cloud SaaS MagicWalls."""

from dataclasses import dataclass
import os
import secrets


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_csv(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return list(default)
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class Settings:
    env: str
    jwt_secret: str
    push_hmac_secret: str
    admin_api_key: str
    billing_webhook_secret: str
    mt5_license_secret: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    db_path: str
    cors_origins: list[str]
    telegram_bot_token: str
    telegram_chat_id: str
    max_device_switches_per_day: int
    primary_failover_sec: int
    heartbeat_stale_sec: int
    terms_version: str
    jwt_ttl_sec: int
    snapshot_ttl_sec: int
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        env_name = os.environ.get("MW_ENV", "development").strip().lower() or "development"
        is_prod = env_name == "production"

        def _req_or_dev(var_name: str, dev_fallback: str) -> str:
            val = os.environ.get(var_name, "").strip()
            if val:
                return val
            if is_prod:
                raise RuntimeError(f"Variavel de ambiente obrigatoria ausente em producao: {var_name}")
            return dev_fallback

        # Nunca usa credenciais reais nem serviceAccountKey.json; em dev usa segredo efêmero por processo se omitido
        ephemeral = secrets.token_hex(16)
        return cls(
            env=env_name,
            jwt_secret=_req_or_dev("MW_JWT_SECRET", f"dev-jwt-{ephemeral}"),
            push_hmac_secret=_req_or_dev("MW_PUSH_HMAC_SECRET", f"dev-push-{ephemeral}"),
            admin_api_key=_req_or_dev("MW_ADMIN_API_KEY", f"dev-admin-{ephemeral}"),
            billing_webhook_secret=_req_or_dev("MW_BILLING_WEBHOOK_SECRET", f"dev-billing-{ephemeral}"),
            mt5_license_secret=_req_or_dev("MW_MT5_LICENSE_SECRET", f"dev-mt5-{ephemeral}"),
            upstash_redis_rest_url=os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/"),
            upstash_redis_rest_token=os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip(),
            db_path=os.environ.get("MW_DB_PATH", os.path.join("data", "saas_magicwalls.db")).strip(),
            cors_origins=_env_csv("MW_CORS_ORIGINS", ["*"]),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            max_device_switches_per_day=_env_int("MW_MAX_DEVICE_SWITCHES_PER_DAY", 8),
            primary_failover_sec=_env_int("MW_PRIMARY_FAILOVER_SEC", 12),
            heartbeat_stale_sec=_env_int("MW_HEARTBEAT_STALE_SEC", 15),
            terms_version=os.environ.get("MW_TERMS_VERSION", "2026.11").strip() or "2026.11",
            jwt_ttl_sec=_env_int("MW_JWT_TTL_SEC", 43200),
            snapshot_ttl_sec=_env_int("MW_SNAPSHOT_TTL_SEC", 604800),
            supabase_url=os.environ.get("SUPABASE_URL", "").strip().rstrip("/"),
            supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )
