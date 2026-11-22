# -*- coding: utf-8 -*-
"""
API Cloud SaaS da MagicWalls (FastAPI).

Responsável por:
- Ingestão Push autenticada por HMAC-SHA256 (com failover Primary -> Hot Standby)
- Entrega de snapshots sanitizados diretamente do cache em memória / Upstash Redis
- Server-Side Entitlements (trial/core < pro < quant < admin)
- Anti-Rateio em 4 Camadas (Sessão Única 401 SESSION_REPLACED, Detector de Abuso,
  dados de Watermark Forense, Verificação de Licença MT5 Tier QUANT)
- Webhooks de Billing e Backoffice Admin
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import hmac
import json
import secrets
import time
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cloud_saas.config import Settings
from cloud_saas.database import create_database, utc_today_str
from cloud_saas.security import (
    create_access_token,
    decode_access_token,
    notify_admin_telegram,
    sign_mt5_license,
    verify_password,
    verify_push_signature,
    verify_webhook_signature,
)
from cloud_saas.store import create_store

PLAN_RANK = {
    "none": 0,
    "trial": 1,
    "core": 1,
    "pro": 2,
    "quant": 3,
    "admin": 4,
}


class ApiRuleError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


class LoginRequest(BaseModel):
    email: str
    password: str
    device_fp: str = "browser-default"


class AcceptTermsRequest(BaseModel):
    terms_version: str = ""


class AdminUpsertUserRequest(BaseModel):
    email: str
    password: Optional[str] = None
    full_name: str = ""
    cpf_masked: str = ""
    plan: str = "core"
    status: str = "active"
    days: Optional[int] = 30
    expires_at: Optional[str] = None
    mt5_account_login: Optional[int] = None
    mt5_license_token: Optional[str] = None
    terms_version: Optional[str] = None


def _parse_iso_utc(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sanitize_user_public(user: dict[str, Any], terms_version_req: str) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name") or "",
        "plan": user.get("plan") or "none",
        "status": user.get("status") or "suspended",
        "expires_at": user.get("expires_at"),
        "terms_version": user.get("terms_version") or "",
        "terms_accepted": bool(user.get("terms_version") == terms_version_req and user.get("terms_accepted_at")),
        "required_terms_version": terms_version_req,
        "watermark_label": f"{user['email']} · UID:{user['id']}",
        "mt5_account_login": user.get("mt5_account_login"),
    }


def _check_subscription_access(user: dict[str, Any]) -> None:
    status = (user.get("status") or "suspended").lower()
    plan = (user.get("plan") or "none").lower()
    if status == "blocked":
        raise ApiRuleError(403, "ACCOUNT_ABUSE_BLOCKED", "Conta bloqueada preventivamente por excesso de trocas de dispositivo.")
    if status not in ("active", "past_due") or plan == "none":
        raise ApiRuleError(403, "SUBSCRIPTION_INACTIVE", "Assinatura inativa ou suspensa.")
    exp = _parse_iso_utc(user.get("expires_at"))
    if exp is not None and datetime.now(timezone.utc) > exp:
        raise ApiRuleError(403, "SUBSCRIPTION_INACTIVE", "Assinatura expirada.")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    db = create_database(cfg)
    store = create_store(cfg)

    app = FastAPI(title="MagicWalls SaaS Cloud API", version="1.0.0")
    app.state.settings = cfg
    app.state.db = db
    app.state.store = store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiRuleError)
    async def api_rule_error_handler(_request: Request, exc: ApiRuleError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "code": exc.code, "detail": exc.detail},
        )

    def _require_admin(x_admin_key: str = Header(default="", alias="X-Admin-Key")):
        if not x_admin_key or not hmac.compare_digest(x_admin_key, cfg.admin_api_key):
            raise ApiRuleError(401, "ADMIN_UNAUTHORIZED", "Chave administrativa inválida.")

    def _make_auth_dep(min_plan: Optional[str] = None, require_terms: bool = True):
        def _dep(
            request: Request,
            authorization: str = Header(default=""),
        ) -> dict[str, Any]:
            if not authorization.lower().startswith("bearer "):
                raise ApiRuleError(401, "UNAUTHENTICATED", "Token de autenticação ausente.")
            token = authorization[7:].strip()
            payload = decode_access_token(cfg.jwt_secret, token)
            if not payload or not payload.get("sub") or not payload.get("sid"):
                raise ApiRuleError(401, "UNAUTHENTICATED", "Token inválido ou expirado.")

            try:
                user_id = int(payload["sub"])
            except ValueError:
                raise ApiRuleError(401, "UNAUTHENTICATED", "Token malformado.")

            user = db.get_user_by_id(user_id)
            if not user:
                raise ApiRuleError(401, "UNAUTHENTICATED", "Usuário não encontrado.")

            # Anti-Rateio Camada 1: Sessão Única no Redis/Store
            active_sess = store.get_json(f"sess:{user_id}")
            if not active_sess or active_sess.get("sid") != payload["sid"]:
                raise ApiRuleError(401, "SESSION_REPLACED", "Acesso iniciado em outro dispositivo.")

            _check_subscription_access(user)

            if require_terms and user.get("terms_version") != cfg.terms_version:
                raise ApiRuleError(403, "TERMS_NOT_ACCEPTED", "É obrigatório aceitar os Termos de Uso CVM/LGPD.")

            if min_plan:
                u_rank = PLAN_RANK.get((user.get("plan") or "none").lower(), 0)
                req_rank = PLAN_RANK.get(min_plan.lower(), 99)
                if u_rank < req_rank:
                    raise ApiRuleError(
                        403,
                        "PLAN_UPGRADE_REQUIRED",
                        f"Recurso exclusivo do plano {min_plan.upper()} ou superior.",
                    )

            request.state.session_id = payload["sid"]
            return user

        return _dep

    auth_any_no_terms = _make_auth_dep(min_plan=None, require_terms=False)
    auth_core = _make_auth_dep(min_plan="core", require_terms=True)
    auth_pro = _make_auth_dep(min_plan="pro", require_terms=True)
    auth_admin = _make_auth_dep(min_plan="admin", require_terms=True)

    # ── Health & Feed Status ──────────────────────────────────────────────────

    @app.get("/health")
    def health():
        meta = store.get_json("snap:meta") or {}
        pushed_at = meta.get("pushed_at")
        age = round(time.time() - pushed_at, 2) if isinstance(pushed_at, (int, float)) else None
        return {
            "ok": True,
            "service": "magicwalls_cloud_saas",
            "db_backend": db.backend_name,
            "store_backend": store.backend_name,
            "feed_age_sec": age,
        }

    @app.get("/api/v1/feed/status")
    def feed_status():
        meta = store.get_json("snap:meta") or {}
        hb = db.get_latest_active_heartbeat()
        now = time.time()
        pushed_at = meta.get("pushed_at")
        age_sec = round(now - pushed_at, 2) if isinstance(pushed_at, (int, float)) else None
        if age_sec is None:
            status = "offline"
        elif age_sec > cfg.heartbeat_stale_sec:
            status = "stale"
        else:
            status = "live"
        return {
            "ok": True,
            "status": status,
            "active_producer_id": meta.get("producer_id") or (hb["producer_id"] if hb else None),
            "active_role": meta.get("producer_role") or (hb["role"] if hb else None),
            "age_sec": age_sec,
            "primary_failover_sec": cfg.primary_failover_sec,
            "server_time": int(now),
        }

    # ── Push Ingestion (Produtor Local / VPS -> Nuvem) ────────────────────────

    @app.post("/internal/v1/push/snapshot")
    async def push_snapshot(
        request: Request,
        x_mw_timestamp: str = Header(default="", alias="X-MW-Timestamp"),
        x_mw_producer_id: str = Header(default="", alias="X-MW-Producer-Id"),
        x_mw_producer_role: str = Header(default="primary", alias="X-MW-Producer-Role"),
        x_mw_signature: str = Header(default="", alias="X-MW-Signature"),
    ):
        raw_body = await request.body()
        ok_sig, reason = verify_push_signature(
            cfg.push_hmac_secret,
            x_mw_timestamp,
            x_mw_producer_id,
            x_mw_producer_role,
            raw_body,
            x_mw_signature,
        )
        if not ok_sig:
            raise ApiRuleError(401, "INVALID_PUSH_SIGNATURE", f"Falha HMAC do produtor: {reason}")

        content_enc = (request.headers.get("content-encoding") or "").lower()
        body_bytes = raw_body
        if "gzip" in content_enc or raw_body[:2] == b"\x1f\x8b":
            try:
                body_bytes = gzip.decompress(raw_body)
            except Exception:
                raise ApiRuleError(400, "INVALID_GZIP", "Corpo gzip inválido.")

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            raise ApiRuleError(400, "INVALID_JSON", "JSON inválido no push.")

        producer_id = str(payload.get("producer_id") or x_mw_producer_id).strip()
        role = str(payload.get("producer_role") or x_mw_producer_role or "primary").strip().lower()
        if role not in ("primary", "standby"):
            role = "primary"

        # Failover Primary -> Hot Standby
        if role == "standby":
            primary_hb = db.get_primary_heartbeat()
            if primary_hb and (time.time() - float(primary_hb["last_seen_ts"])) < cfg.primary_failover_sec:
                db.update_producer_heartbeat(producer_id, "standby", len(raw_body), "standby_idle")
                return {
                    "ok": True,
                    "accepted": False,
                    "mode": "standby_idle",
                    "active_role": "primary",
                }

        db.update_producer_heartbeat(producer_id, role, len(raw_body), "active")

        if payload.get("heartbeat_only"):
            return {"ok": True, "accepted": False, "mode": "heartbeat_only", "active_role": role}

        snapshots = payload.get("snapshots") or {}
        ttl = cfg.snapshot_ttl_sec
        stored_keys = []
        for tier in ("core", "pro", "admin"):
            tier_map = snapshots.get(tier)
            if not isinstance(tier_map, dict):
                continue
            for ep_name, ep_val in tier_map.items():
                if ep_val is None:
                    continue
                store.set_json(f"snap:{tier}:{ep_name}", ep_val, ttl_sec=ttl)
                stored_keys.append(f"{tier}:{ep_name}")

        store.set_json(
            "snap:meta",
            {
                "producer_id": producer_id,
                "producer_role": role,
                "pushed_at": time.time(),
                "stored_keys": stored_keys,
            },
            ttl_sec=ttl,
        )
        return {
            "ok": True,
            "accepted": True,
            "mode": "active",
            "active_role": role,
            "stored_count": len(stored_keys),
        }

    # ── Auth & Anti-Rateio (Sessão Única + Detector de Abuso + Termos) ────────

    @app.post("/auth/login")
    def login(req: LoginRequest, request: Request):
        user = db.get_user_by_email(req.email)
        if not user or not verify_password(req.password, user["password_hash"]):
            raise ApiRuleError(401, "INVALID_CREDENTIALS", "E-mail ou senha inválidos.")

        _check_subscription_access(user)

        sid = secrets.token_urlsafe(24)
        client_ip = _extract_client_ip(request)
        ua = request.headers.get("user-agent", "")
        prev_sess = store.get_json(f"sess:{user['id']}")
        abuse = db.record_login_and_check_abuse(
            user_id=user["id"],
            session_id=sid,
            ip=client_ip,
            device_fp=req.device_fp,
            user_agent=ua,
            max_switches=cfg.max_device_switches_per_day,
        )
        if abuse["blocked"]:
            store.delete(f"sess:{user['id']}")
            notify_admin_telegram(
                cfg.telegram_bot_token,
                cfg.telegram_chat_id,
                f"[ANTI-RATEIO BLOQUEIO] Conta {user['email']} bloqueada por {abuse['switches']} trocas de dispositivo/IP em {abuse['trading_day']}.",
            )
            raise ApiRuleError(
                403,
                "ACCOUNT_ABUSE_BLOCKED",
                "Conta bloqueada preventivamente por excesso de trocas de dispositivo/IP no mesmo pregão.",
            )

        if prev_sess and prev_sess.get("sid") and prev_sess.get("sid") != sid:
            db.log_audit(
                user_id=user["id"],
                event_type="SESSION_REPLACED",
                ip=client_ip,
                device_fp=req.device_fp,
                user_agent=ua,
                details={
                    "previous_session_id": prev_sess.get("sid"),
                    "new_session_id": sid,
                },
            )
        db.log_audit(
            user_id=user["id"],
            event_type="LOGIN_OK",
            ip=client_ip,
            device_fp=req.device_fp,
            user_agent=ua,
            details={"session_id": sid, "switches_today": abuse["switches"]},
        )

        store.set_json(
            f"sess:{user['id']}",
            {
                "sid": sid,
                "ip": client_ip,
                "device_fp": req.device_fp,
                "created_at": int(time.time()),
            },
            ttl_sec=cfg.jwt_ttl_sec,
        )

        token = create_access_token(
            jwt_secret=cfg.jwt_secret,
            user_id=user["id"],
            email=user["email"],
            plan=user["plan"],
            session_id=sid,
            ttl_sec=cfg.jwt_ttl_sec,
        )
        return {
            "ok": True,
            "access_token": token,
            "token_type": "bearer",
            "session_id": sid,
            "user": _sanitize_user_public(user, cfg.terms_version),
        }

    @app.post("/auth/accept-terms")
    def accept_terms(req: AcceptTermsRequest, request: Request, user: dict = Depends(auth_any_no_terms)):
        version = (req.terms_version or cfg.terms_version).strip()
        if version != cfg.terms_version:
            raise ApiRuleError(400, "TERMS_VERSION_MISMATCH", f"Versão de termos exigida: {cfg.terms_version}")
        client_ip = _extract_client_ip(request)
        ua = request.headers.get("user-agent", "")
        updated = db.accept_terms(user["id"], version, client_ip, user_agent=ua)
        db.log_audit(
            user_id=user["id"],
            event_type="TERMS_ACCEPTED",
            ip=client_ip,
            user_agent=ua,
            details={"terms_version": version},
        )
        return {
            "ok": True,
            "user": _sanitize_user_public(updated, cfg.terms_version),
        }

    @app.get("/auth/me")
    def auth_me(user: dict = Depends(auth_any_no_terms)):
        return {
            "ok": True,
            "user": _sanitize_user_public(user, cfg.terms_version),
        }

    @app.post("/auth/logout")
    def logout(request: Request, user: dict = Depends(auth_any_no_terms)):
        store.delete(f"sess:{user['id']}")
        db.clear_active_session(user["id"], reason="USER_LOGOUT")
        db.log_audit(
            user_id=user["id"],
            event_type="LOGOUT",
            ip=_extract_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            details={"session_id": getattr(request.state, "session_id", "")},
        )
        return {"ok": True}

    # ── Rotas do Terminal Web (Servidas do Cache + Server-Side Entitlements) ──

    @app.get("/api/compass/etapa1")
    def get_etapa1(
        lite: str = Query(default="0"),
        date_str: Optional[str] = Query(default=None),
        user: dict = Depends(auth_core),
    ):
        tier = "pro" if PLAN_RANK.get(user["plan"].lower(), 0) >= PLAN_RANK["pro"] else "core"
        clean_date = (date_str or "").strip()
        is_valid_date = (
            len(clean_date) == 10
            and clean_date[4] == "-"
            and clean_date[7] == "-"
            and clean_date[:4].isdigit()
            and clean_date[5:7].isdigit()
            and clean_date[8:].isdigit()
        )
        if is_valid_date:
            day_data = store.get_json(f"snap:{tier}:etapa1_day_{clean_date}")
            if day_data is not None:
                return day_data
        want_lite = lite in ("1", "true", "True")
        primary_key = f"snap:{tier}:etapa1_lite" if want_lite else f"snap:{tier}:etapa1_full"
        fallback_key = f"snap:{tier}:etapa1_full" if want_lite else f"snap:{tier}:etapa1_lite"
        data = store.get_json(primary_key) or store.get_json(fallback_key)
        if data is None:
            raise ApiRuleError(503, "FEED_UNAVAILABLE", "Dados ao vivo ainda não publicados pelo produtor.")
        if is_valid_date:
            live_date = str(data.get("selected_date") or "").strip()
            if live_date != clean_date:
                # Nunca devolver barras de outro pregão quando o usuário pediu uma data histórica não armazenada
                avail = data.get("available_dates") or []
                empty_assets = {}
                for sym in ("WIN", "WDO"):
                    src_asset = data.get(sym) if isinstance(data.get(sym), dict) else {}
                    empty_assets[sym] = {
                        "asset": sym,
                        "active_contract": src_asset.get("active_contract") or sym,
                        "session_date": clean_date,
                        "last_price": 0,
                        "open_price": 0,
                        "vwap": 0,
                        "all_walls": [],
                        "walls_radar": {},
                        "session_totals": {},
                        "caminho_a": {
                            "ref_date": clean_date,
                            "m5_dealer_vs_flow_series": [],
                            "flow_windows": [],
                            "asg_hud": {},
                            "signals_log": [],
                            "engine_divs_v32": [],
                        },
                    }
                return {
                    "ok": True,
                    "is_historical": True,
                    "selected_date": clean_date,
                    "available_dates": avail,
                    "WIN": empty_assets["WIN"],
                    "WDO": empty_assets["WDO"],
                }
        return data

    @app.get("/api/compass/m1_series")
    def get_m1_series(
        date_str: Optional[str] = Query(default=None),
        user: dict = Depends(auth_core),
    ):
        tier = "pro" if PLAN_RANK.get(user["plan"].lower(), 0) >= PLAN_RANK["pro"] else "core"
        clean_date = (date_str or "").strip()
        if (
            len(clean_date) == 10
            and clean_date[4] == "-"
            and clean_date[7] == "-"
            and clean_date[:4].isdigit()
            and clean_date[5:7].isdigit()
            and clean_date[8:].isdigit()
        ):
            day_m1 = store.get_json(f"snap:{tier}:m1_series_day_{clean_date}") or store.get_json(f"snap:core:m1_series_day_{clean_date}")
            if day_m1 is not None:
                return day_m1
        data = store.get_json(f"snap:{tier}:m1_series") or store.get_json("snap:core:m1_series")
        if data is None:
            raise ApiRuleError(503, "FEED_UNAVAILABLE", "Série M1 ainda não disponível.")
        return data

    def _serve_pro_snapshot(snapshot_key: str):
        data = store.get_json(f"snap:pro:{snapshot_key}")
        if data is None:
            raise ApiRuleError(503, "FEED_UNAVAILABLE", f"Snapshot {snapshot_key} ainda não disponível.")
        return data

    @app.get("/api/v2/regime")
    def get_v2_regime(_user: dict = Depends(auth_pro)):
        return _serve_pro_snapshot("regime")

    @app.get("/api/performance")
    def get_performance(_user: dict = Depends(auth_pro)):
        return _serve_pro_snapshot("performance")

    @app.get("/api/di-regime")
    def get_di_regime(_user: dict = Depends(auth_pro)):
        return _serve_pro_snapshot("di_regime")

    @app.get("/api/history")
    def get_history(_user: dict = Depends(auth_pro)):
        return _serve_pro_snapshot("history")

    @app.get("/api/gex-walls")
    def get_gex_walls(_user: dict = Depends(auth_pro)):
        return _serve_pro_snapshot("gex_walls")

    @app.get("/api/morning-brief")
    def get_morning_brief(_user: dict = Depends(auth_admin)):
        data = store.get_json("snap:admin:morning_brief")
        if data is None:
            raise ApiRuleError(503, "FEED_UNAVAILABLE", "Morning brief ainda não publicado pelo produtor.")
        return data

    @app.post("/api/compass/divergencias_motor")
    async def post_divergencias_motor(request: Request, _user: dict = Depends(auth_core)):
        try:
            body = await request.json()
        except Exception:
            raise ApiRuleError(400, "INVALID_JSON", "Corpo JSON inválido.")
        asset = str(body.get("asset", "WIN")).upper()
        engine = str(body.get("engine", "v3.2"))
        try:
            from core.div_engines_view import detect
            divs = detect(
                asset,
                body.get("bars") or [],
                body.get("walls") or [],
                engine,
                trades=body.get("trades") or [],
            )
        except ImportError:
            divs = []
        return {"ok": True, "asset": asset, "engine": engine, "divergences": divs}

    # ── Camada 4 Anti-Rateio: Verificação de Licença MT5 (Tier QUANT) ─────────

    @app.get("/api/v1/mt5/verify")
    def verify_mt5_license(
        account_login: int = Query(...),
        token: str = Query(default=""),
        symbol: str = Query(default=""),
    ):
        user = db.get_user_by_mt5_login_and_token(account_login, token)
        if not user:
            return {"authorized": False, "reason": "INVALID_TOKEN"}

        if (user.get("status") or "").lower() not in ("active", "past_due"):
            return {"authorized": False, "reason": "SUSPENDED"}

        plan = (user.get("plan") or "none").lower()
        if PLAN_RANK.get(plan, 0) < PLAN_RANK["quant"]:
            return {"authorized": False, "reason": "PLAN_NOT_QUANT"}

        bound_login = user.get("mt5_account_login")
        if bound_login is None or int(bound_login) != int(account_login):
            return {"authorized": False, "reason": "ACCOUNT_MISMATCH"}

        exp = _parse_iso_utc(user.get("expires_at"))
        if exp is not None and datetime.now(timezone.utc) > exp:
            return {"authorized": False, "reason": "EXPIRED"}

        valid_until = exp.strftime("%Y-%m-%d") if exp else (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        sig = sign_mt5_license(cfg.mt5_license_secret, int(account_login), valid_until, plan)
        return {
            "authorized": True,
            "account_login": int(account_login),
            "symbol": symbol,
            "plan": plan,
            "valid_until": valid_until,
            "sig": sig,
        }

    # ── Webhooks de Pagamento (Kiwify / Asaas / Pagar.me / Stripe) ───────────

    @app.post("/webhooks/billing")
    async def billing_webhook(
        request: Request,
        x_mw_webhook_signature: str = Header(default="", alias="X-MW-Webhook-Signature"),
    ):
        raw_body = await request.body()
        if not verify_webhook_signature(cfg.billing_webhook_secret, raw_body, x_mw_webhook_signature):
            raise ApiRuleError(401, "INVALID_WEBHOOK_SIGNATURE", "Assinatura de webhook inválida.")

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise ApiRuleError(400, "INVALID_JSON", "Payload JSON inválido.")

        event = str(body.get("event") or "").strip().lower()
        email = str(body.get("email") or "").strip().lower()
        if not email:
            raise ApiRuleError(400, "EMAIL_REQUIRED", "E-mail obrigatório no webhook.")

        plan = str(body.get("plan") or "pro").strip().lower()
        if plan not in PLAN_RANK:
            plan = "pro"
        days = int(body.get("days") or 30)

        gateway = str(body.get("gateway") or "").strip()[:64]
        external_sub_id = str(body.get("external_sub_id") or body.get("subscription_id") or "").strip()[:128]

        if event in ("paid", "renewed", "subscription.active"):
            expires_at = body.get("expires_at") or (
                datetime.now(timezone.utc) + timedelta(days=days)
            ).replace(microsecond=0).isoformat()
            user = db.upsert_user(
                email=email,
                password=body.get("password"),
                full_name=str(body.get("full_name") or ""),
                cpf_masked=str(body.get("cpf_masked") or ""),
                plan=plan,
                status="active",
                expires_at=expires_at,
                mt5_account_login=body.get("mt5_account_login"),
                gateway=gateway,
                external_sub_id=external_sub_id,
            )
            db.log_audit(
                user_id=user["id"],
                event_type="BILLING_EVENT",
                details={"event": event, "action": "activated", "plan": user["plan"], "gateway": gateway, "external_sub_id": external_sub_id},
            )
            return {"ok": True, "action": "activated", "user_id": user["id"], "plan": user["plan"]}

        existing = db.get_user_by_email(email)
        if not existing:
            return {"ok": True, "action": "ignored_unknown_user"}

        if event in ("past_due", "payment_failed"):
            grace_exp = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()
            db.upsert_user(
                email=email,
                plan=existing["plan"],
                status="past_due",
                expires_at=grace_exp,
                gateway=gateway,
                external_sub_id=external_sub_id,
            )
            db.log_audit(
                user_id=existing["id"],
                event_type="BILLING_EVENT",
                details={"event": event, "action": "grace_3d", "gateway": gateway, "external_sub_id": external_sub_id},
            )
            return {"ok": True, "action": "grace_3d", "user_id": existing["id"]}

        if event in ("canceled", "refunded", "chargeback", "subscription.canceled"):
            db.update_user_status(existing["id"], "suspended")
            store.delete(f"sess:{existing['id']}")
            db.clear_active_session(existing["id"], reason=f"BILLING_{event.upper()}")
            db.log_audit(
                user_id=existing["id"],
                event_type="BILLING_EVENT",
                details={"event": event, "action": "suspended_and_revoked", "gateway": gateway, "external_sub_id": external_sub_id},
            )
            return {"ok": True, "action": "suspended_and_revoked", "user_id": existing["id"]}

        return {"ok": True, "action": "ignored_event", "event": event}

    # ── Backoffice Admin ──────────────────────────────────────────────────────

    @app.get("/api/v1/admin/overview", dependencies=[Depends(_require_admin)])
    def admin_overview():
        ov = db.get_admin_overview()
        ov["ok"] = True
        ov["feed"] = feed_status()
        return ov

    @app.post("/api/v1/admin/users", dependencies=[Depends(_require_admin)])
    def admin_upsert_user(req: AdminUpsertUserRequest):
        expires_at = req.expires_at
        if not expires_at and req.days is not None:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=int(req.days))).replace(microsecond=0).isoformat()
        user = db.upsert_user(
            email=req.email,
            password=req.password,
            full_name=req.full_name,
            cpf_masked=req.cpf_masked,
            plan=req.plan.lower(),
            status=req.status.lower(),
            expires_at=expires_at,
            mt5_account_login=req.mt5_account_login,
            mt5_license_token=req.mt5_license_token,
            terms_version=req.terms_version,
        )
        return {
            "ok": True,
            "user": _sanitize_user_public(user, cfg.terms_version),
            "mt5_license_token": user.get("mt5_license_token") or "",
        }

    @app.post("/api/v1/admin/users/{user_id}/kick", dependencies=[Depends(_require_admin)])
    def admin_kick_user(user_id: int):
        store.delete(f"sess:{int(user_id)}")
        db.clear_active_session(int(user_id), reason="ADMIN_KICK")
        db.log_audit(user_id=int(user_id), event_type="ADMIN_KICK", details={"kicked_by": "admin_api"})
        return {"ok": True, "kicked_user_id": int(user_id)}

    @app.post("/api/v1/admin/users/{user_id}/unblock", dependencies=[Depends(_require_admin)])
    def admin_unblock_user(user_id: int):
        updated = db.unblock_user(user_id)
        if not updated:
            raise ApiRuleError(404, "USER_NOT_FOUND", "Usuário não encontrado.")
        return {"ok": True, "user": _sanitize_user_public(updated, cfg.terms_version)}

    return app


app = create_app()
