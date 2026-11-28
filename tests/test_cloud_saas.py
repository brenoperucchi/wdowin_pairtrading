# -*- coding: utf-8 -*-
"""Testes ponta a ponta da arquitetura SaaS Cloud MagicWalls (Push, Failover, Entitlements e Anti-Rateio)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

from cloud_saas.app import create_app
from cloud_saas.config import Settings
from cloud_saas.database import SupabaseRestDatabase, brt_today_str, create_database
from cloud_saas.security import (
    canonicalize_email,
    compute_push_signature,
    compute_webhook_signature,
    normalize_br_phone,
)
from cloud_saas.store import CachedResilientStore, MemoryTTLStore, UpstashRestStore
from scripts.cloud_publisher import CloudPublisher, HeartbeatMonitor, _attach_precomputed_divs
from scripts.verify_cloud_connections import check_supabase, check_upstash


def _make_settings(db_path: str) -> Settings:
    return Settings(
        env="test",
        jwt_secret="test-jwt-secret-key-0123456789abcdef",
        push_hmac_secret="test-push-hmac-secret-0123456789abcdef",
        admin_api_key="test-admin-api-key",
        billing_webhook_secret="test-webhook-secret",
        mt5_license_secret="test-mt5-license-secret",
        upstash_redis_rest_url="",
        upstash_redis_rest_token="",
        db_path=db_path,
        cors_origins=["*"],
        telegram_bot_token="",
        telegram_chat_id="",
        max_device_switches_per_day=4,
        primary_failover_sec=12,
        heartbeat_stale_sec=15,
        terms_version="2026.11",
        jwt_ttl_sec=3600,
        snapshot_ttl_sec=300,
    )


def _signed_push_request(client: TestClient, secret: str, payload: dict, producer_id="vps-01", role="primary", ts_offset=0):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw)
    ts_str = str(int(time.time()) + ts_offset)
    sig = compute_push_signature(secret, ts_str, producer_id, role, gz)
    return client.post(
        "/internal/v1/push/snapshot",
        content=gz,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "X-MW-Timestamp": ts_str,
            "X-MW-Producer-Id": producer_id,
            "X-MW-Producer-Role": role,
            "X-MW-Signature": sig,
        },
    )


class CloudSaasArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "saas_test.db")
        self.settings = _make_settings(self.db_path)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.admin_headers = {"X-Admin-Key": self.settings.admin_api_key}

    def tearDown(self) -> None:
        self.app.state.db.close()
        self._tmpdir.cleanup()

    def _seed_sample_push(self, producer_id="vps-01", role="primary", marker="primary_val"):
        payload = {
            "producer_id": producer_id,
            "producer_role": role,
            "snapshots": {
                "core": {
                    "etapa1_lite": {"ok": True, "tier": "core", "marker": marker, "WIN": {"current": 167470}},
                    "m1_series": {"ok": True, "WIN": {"m1_series": [{"time": "09:05"}]}},
                },
                "pro": {
                    "etapa1_lite": {
                        "ok": True,
                        "tier": "pro",
                        "marker": marker,
                        "portfolio_4_sistematicas": {"net": 12827},
                    },
                    "m1_series": {"ok": True, "WIN": {"m1_series": [{"time": "09:05"}]}},
                    "regime": {"ok": True, "z": 0.42},
                    "performance": {"ok": True, "total": 100},
                    "di_regime": {"ok": True, "di": 11.2},
                    "gex_walls": [{"type": "Wall", "price": 168424}],
                    "history": {"history": [{"date": "2026-11-20", "z": 0.1}]},
                },
                "admin": {
                    "morning_brief": {"ok": True, "win": {"symbol": "WINFUT"}, "wdo": {"symbol": "WDOFUT"}},
                },
            },
        }
        return _signed_push_request(self.client, self.settings.push_hmac_secret, payload, producer_id=producer_id, role=role)

    def _create_user(self, email: str, plan: str, accept_terms: bool = True, mt5_login: int | None = None) -> dict:
        body = {
            "email": email,
            "password": "StrongPassword!123",
            "full_name": "Trader Teste",
            "plan": plan,
            "status": "active",
            "days": 30,
            "mt5_account_login": mt5_login,
        }
        if accept_terms:
            body["terms_version"] = self.settings.terms_version
        resp = self.client.post("/api/v1/admin/users", json=body, headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_hmac_push_auth_and_gzip(self) -> None:
        # Assinatura inválida rejeitada
        r_bad = self.client.post(
            "/internal/v1/push/snapshot",
            content=b"{}",
            headers={"X-MW-Timestamp": str(int(time.time())), "X-MW-Producer-Id": "x", "X-MW-Producer-Role": "primary", "X-MW-Signature": "deadbeef"},
        )
        self.assertEqual(r_bad.status_code, 401)
        self.assertEqual(r_bad.json()["code"], "INVALID_PUSH_SIGNATURE")

        # Timestamp expirado (> 60s) rejeitado
        r_exp = _signed_push_request(self.client, self.settings.push_hmac_secret, {"snapshots": {}}, ts_offset=-120)
        self.assertEqual(r_exp.status_code, 401)

        # Push gzip válido aceito
        r_ok = self._seed_sample_push()
        self.assertEqual(r_ok.status_code, 200)
        self.assertTrue(r_ok.json()["accepted"])
        self.assertEqual(r_ok.json()["stored_count"], 10)

        st = self.client.get("/api/v1/feed/status").json()
        self.assertEqual(st["status"], "live")
        self.assertEqual(st["active_role"], "primary")

        h = self.client.get("/health").json()
        self.assertTrue(h["ok"])
        self.assertEqual(h["db_backend"], "sqlite")
        self.assertEqual(h["store_backend"], "memory")

    def test_primary_and_standby_failover(self) -> None:
        r_p = self._seed_sample_push(producer_id="vps-sp", role="primary", marker="from-primary")
        self.assertTrue(r_p.json()["accepted"])

        # Enquanto primary fresco, standby fica idle e não sobrescreve
        r_sb = self._seed_sample_push(producer_id="pc-local", role="standby", marker="from-standby")
        self.assertEqual(r_sb.status_code, 200)
        self.assertFalse(r_sb.json()["accepted"])
        self.assertEqual(r_sb.json()["mode"], "standby_idle")

        # Simula queda do primary (> 12s atrás)
        with self.app.state.db._lock:
            self.app.state.db._conn.execute(
                "UPDATE producer_heartbeats SET last_seen_ts = ? WHERE producer_id = 'vps-sp'",
                (time.time() - 25.0,),
            )
            self.app.state.db._conn.commit()

        r_sb2 = self._seed_sample_push(producer_id="pc-local", role="standby", marker="from-standby")
        self.assertEqual(r_sb2.status_code, 200)
        self.assertTrue(r_sb2.json()["accepted"])
        self.assertEqual(r_sb2.json()["active_role"], "standby")

    def test_server_side_entitlements_core_vs_pro(self) -> None:
        self._seed_sample_push()
        self._create_user("core@mw.com", "core")
        self._create_user("pro@mw.com", "pro")

        tok_core = self.client.post("/auth/login", json={"email": "core@mw.com", "password": "StrongPassword!123", "device_fp": "fp-core"}).json()["access_token"]
        tok_pro = self.client.post("/auth/login", json={"email": "pro@mw.com", "password": "StrongPassword!123", "device_fp": "fp-pro"}).json()["access_token"]

        # CORE recebe payload sanitizado e é bloqueado em endpoints PRO
        e1_core = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok_core}"})
        self.assertEqual(e1_core.status_code, 200)
        self.assertEqual(e1_core.json()["tier"], "core")
        self.assertNotIn("portfolio_4_sistematicas", e1_core.json())

        reg_core = self.client.get("/api/v2/regime", headers={"Authorization": f"Bearer {tok_core}"})
        self.assertEqual(reg_core.status_code, 403)
        self.assertEqual(reg_core.json()["code"], "PLAN_UPGRADE_REQUIRED")

        # PRO recebe payload completo e acessa endpoints PRO
        e1_pro = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok_pro}"})
        self.assertEqual(e1_pro.status_code, 200)
        self.assertEqual(e1_pro.json()["tier"], "pro")
        self.assertIn("portfolio_4_sistematicas", e1_pro.json())

        reg_pro = self.client.get("/api/v2/regime", headers={"Authorization": f"Bearer {tok_pro}"})
        self.assertEqual(reg_pro.status_code, 200)

    def test_single_active_session_replaced(self) -> None:
        self._seed_sample_push()
        self._create_user("single@mw.com", "pro")

        tok_dev_a = self.client.post("/auth/login", json={"email": "single@mw.com", "password": "StrongPassword!123", "device_fp": "pc-a"}).json()["access_token"]
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok_dev_a}"}).status_code, 200)

        # Novo login em outro dispositivo derruba imediatamente o dispositivo A
        tok_dev_b = self.client.post("/auth/login", json={"email": "single@mw.com", "password": "StrongPassword!123", "device_fp": "pc-b"}).json()["access_token"]
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok_dev_b}"}).status_code, 200)

        r_a = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok_dev_a}"})
        self.assertEqual(r_a.status_code, 401)
        self.assertEqual(r_a.json()["code"], "SESSION_REPLACED")

        # Verifica tabela normalizada active_sessions + audit_logs
        with self.app.state.db._lock:
            sess_rows = self.app.state.db._conn.execute(
                "SELECT session_id, is_active, revoked_reason FROM active_sessions ORDER BY id ASC"
            ).fetchall()
            audit_rows = self.app.state.db._conn.execute(
                "SELECT event_type FROM audit_logs ORDER BY id ASC"
            ).fetchall()
        self.assertEqual(len(sess_rows), 2)
        self.assertEqual(sess_rows[0]["is_active"], 0)
        self.assertEqual(sess_rows[0]["revoked_reason"], "SESSION_REPLACED")
        self.assertEqual(sess_rows[1]["is_active"], 1)
        events = [r["event_type"] for r in audit_rows]
        self.assertIn("LOGIN_OK", events)
        self.assertIn("SESSION_REPLACED", events)

    def test_abuse_detector_and_admin_unblock(self) -> None:
        created = self._create_user("abuse@mw.com", "pro")
        uid = created["user"]["id"]

        # Login inicial (0 trocas) + 4 trocas permitidas (total 5 devices)
        for idx in range(5):
            r = self.client.post("/auth/login", json={"email": "abuse@mw.com", "password": "StrongPassword!123", "device_fp": f"fp-{idx}"})
            self.assertEqual(r.status_code, 200, f"Falhou no idx={idx}: {r.text}")

        # 5ª troca (> 4) dispara bloqueio preventivo e flag no admin
        r_blk = self.client.post("/auth/login", json={"email": "abuse@mw.com", "password": "StrongPassword!123", "device_fp": "fp-5"})
        self.assertEqual(r_blk.status_code, 403)
        self.assertEqual(r_blk.json()["code"], "ACCOUNT_ABUSE_BLOCKED")

        ov = self.client.get("/api/v1/admin/overview", headers=self.admin_headers).json()
        self.assertEqual(len(ov["open_abuse_flags"]), 1)
        self.assertEqual(ov["open_abuse_flags"][0]["email"], "abuse@mw.com")

        # Admin desbloqueia e usuário volta a logar
        r_unb = self.client.post(f"/api/v1/admin/users/{uid}/unblock", headers=self.admin_headers)
        self.assertEqual(r_unb.status_code, 200)
        r_ok = self.client.post("/auth/login", json={"email": "abuse@mw.com", "password": "StrongPassword!123", "device_fp": "fp-clean"})
        self.assertEqual(r_ok.status_code, 200)

    def test_admin_exempt_from_device_switch_block(self) -> None:
        self._create_user("boss@mw.com", "admin")
        tokens = []
        for idx in range(8):
            r = self.client.post(
                "/auth/login",
                json={"email": "boss@mw.com", "password": "StrongPassword!123", "device_fp": f"adm-{idx}"},
            )
            self.assertEqual(r.status_code, 200, f"Admin bloqueado indevidamente em idx={idx}: {r.text}")
            tokens.append(r.json()["access_token"])

        ov = self.client.get("/api/v1/admin/overview", headers=self.admin_headers).json()
        self.assertEqual(ov["open_abuse_flags"], [])

        # Admin não tem sessão única: o login mais antigo continua valendo (limite de sessões em test_admin_multi_session.py).
        r_old = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tokens[0]}"})
        self.assertEqual(r_old.status_code, 200)

    def test_two_device_alternation_tolerance_and_cap(self) -> None:
        self._create_user("two@mw.com", "pro")
        devices = ["pc-home", "phone-4g"]
        # 2 aparelhos distintos toleram até max(4*2, 12) = 12 trocas (13 logins)
        for idx in range(13):
            r = self.client.post(
                "/auth/login",
                json={"email": "two@mw.com", "password": "StrongPassword!123", "device_fp": devices[idx % 2]},
            )
            self.assertEqual(r.status_code, 200, f"Alternância 2 aparelhos falhou no login idx={idx}: {r.text}")

        # 14º login (13ª troca > 12) dispara bloqueio
        r_blk = self.client.post(
            "/auth/login",
            json={"email": "two@mw.com", "password": "StrongPassword!123", "device_fp": devices[13 % 2]},
        )
        self.assertEqual(r_blk.status_code, 403)
        self.assertEqual(r_blk.json()["code"], "ACCOUNT_ABUSE_BLOCKED")

    def test_brt_trading_day_boundary(self) -> None:
        self.assertEqual(brt_today_str(datetime(2026, 11, 22, 1, 41, tzinfo=timezone.utc)), "2026-11-21")
        self.assertEqual(brt_today_str(datetime(2026, 11, 22, 14, 27, tzinfo=timezone.utc)), "2026-11-22")

    def test_clickwrap_terms_enforcement(self) -> None:
        self._seed_sample_push()
        self._create_user("terms@mw.com", "pro", accept_terms=False)

        tok = self.client.post("/auth/login", json={"email": "terms@mw.com", "password": "StrongPassword!123", "device_fp": "fp-1"}).json()["access_token"]
        r_blocked = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_blocked.status_code, 403)
        self.assertEqual(r_blocked.json()["code"], "TERMS_NOT_ACCEPTED")

        r_acc = self.client.post("/auth/accept-terms", json={"terms_version": self.settings.terms_version}, headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_acc.status_code, 200)
        self.assertTrue(r_acc.json()["user"]["terms_accepted"])

        r_ok = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_ok.status_code, 200)

    def test_billing_webhook_lifecycle(self) -> None:
        paid_body = json.dumps({"event": "paid", "email": "buyer@mw.com", "plan": "pro", "days": 30, "password": "Pass!123"}).encode("utf-8")
        bad = self.client.post("/webhooks/billing", content=paid_body, headers={"X-MW-Webhook-Signature": "wrong"})
        self.assertEqual(bad.status_code, 401)

        sig_paid = compute_webhook_signature(self.settings.billing_webhook_secret, paid_body)
        ok_paid = self.client.post("/webhooks/billing", content=paid_body, headers={"X-MW-Webhook-Signature": sig_paid, "Content-Type": "application/json"})
        self.assertEqual(ok_paid.status_code, 200)
        self.assertEqual(ok_paid.json()["action"], "activated")

        tok = self.client.post("/auth/login", json={"email": "buyer@mw.com", "password": "Pass!123", "device_fp": "fp-b"}).json()["access_token"]
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code, 200)

        # Refund suspende conta e revoga sessão ativa imediatamente
        ref_body = json.dumps({"event": "refunded", "email": "buyer@mw.com"}).encode("utf-8")
        sig_ref = compute_webhook_signature(self.settings.billing_webhook_secret, ref_body)
        ok_ref = self.client.post("/webhooks/billing", content=ref_body, headers={"X-MW-Webhook-Signature": sig_ref, "Content-Type": "application/json"})
        self.assertEqual(ok_ref.status_code, 200)
        self.assertEqual(ok_ref.json()["action"], "suspended_and_revoked")

        r_after = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        self.assertIn(r_after.status_code, (401, 403))

    def test_mt5_license_verify_camada4(self) -> None:
        q = self._create_user("quant@mw.com", "quant", mt5_login=2004051)
        q_tok = q["mt5_license_token"]

        c = self._create_user("core_mt5@mw.com", "core", mt5_login=999999)
        c_tok = c["mt5_license_token"] or "dummy"

        # Conta e plano corretos
        r_ok = self.client.get(f"/api/v1/mt5/verify?account_login=2004051&token={q_tok}&symbol=WIN$N").json()
        self.assertTrue(r_ok["authorized"])
        self.assertTrue(r_ok["sig"])

        # Conta MT5 diferente da contratada
        r_mismatch = self.client.get(f"/api/v1/mt5/verify?account_login=1111111&token={q_tok}&symbol=WIN$N").json()
        self.assertFalse(r_mismatch["authorized"])
        self.assertEqual(r_mismatch["reason"], "ACCOUNT_MISMATCH")

        # Plano inferior a QUANT
        r_plan = self.client.get(f"/api/v1/mt5/verify?account_login=999999&token={c_tok}").json()
        self.assertFalse(r_plan["authorized"])
        self.assertIn(r_plan["reason"], ("PLAN_NOT_QUANT", "INVALID_TOKEN"))

        # Assinatura vencida ontem
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
        self.client.post(
            "/api/v1/admin/users",
            json={"email": "quant@mw.com", "plan": "quant", "status": "active", "expires_at": yesterday, "mt5_account_login": 2004051, "mt5_license_token": q_tok},
            headers=self.admin_headers,
        )
        r_exp = self.client.get(f"/api/v1/mt5/verify?account_login=2004051&token={q_tok}").json()
        self.assertFalse(r_exp["authorized"])
        self.assertEqual(r_exp["reason"], "EXPIRED")

    @patch("scripts.cloud_publisher.notify_admin_telegram")
    def test_heartbeat_monitor_alerts_and_recovery(self, mock_tg) -> None:
        mon = HeartbeatMonitor(
            stale_sec=15.0,
            cooldown_sec=0.1,
            telegram_token="bot-tok",
            telegram_chat_id="12345",
            always_alert=True,
        )
        mon.last_ok_mono = time.monotonic() - 20.0
        mon.check("pc-prod", last_error="timeout")
        self.assertTrue(mon.in_alert)
        self.assertEqual(mock_tg.call_count, 1)
        self.assertIn("CRÍTICO", mock_tg.call_args[0][2])

        mon.mark_ok("pc-prod")
        self.assertFalse(mon.in_alert)
        self.assertEqual(mock_tg.call_count, 2)
        self.assertIn("RECUPERADO", mock_tg.call_args[0][2])

    def test_supabase_rest_database_requests(self) -> None:
        tables: dict[str, list[dict]] = {
            "profiles": [],
            "subscriptions": [],
            "active_sessions": [],
            "terms_acceptance": [],
            "audit_logs": [],
            "producer_heartbeats": [],
        }
        seq = {"id": 0}
        calls: list[tuple[str, str]] = []

        def _match_params(row: dict, params: dict[str, str]) -> bool:
            for k, v in params.items():
                if k in ("select", "order", "limit", "on_conflict"):
                    continue
                if "." not in v:
                    continue
                op, expected = v.split(".", 1)
                actual = row.get(k)
                if expected == "true":
                    exp_val = True
                elif expected == "false":
                    exp_val = False
                elif expected.lstrip("-").isdigit() and isinstance(actual, int):
                    exp_val = int(expected)
                else:
                    exp_val = expected
                if op == "eq" and actual != exp_val:
                    return False
                if op == "neq" and actual == exp_val:
                    return False
            return True

        def _handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers.get("apikey"), "srv-key-secret")
            self.assertEqual(request.headers.get("Authorization"), "Bearer srv-key-secret")
            parts = [p for p in request.url.path.split("/") if p]
            table = parts[-1]
            calls.append((request.method, table))
            params = dict(request.url.params)
            body = json.loads(request.content.decode("utf-8")) if request.content else None

            if request.method == "GET":
                rows = [dict(r) for r in tables[table] if _match_params(r, params)]
                if "order" in params and "desc" in params["order"] and rows and "id" in rows[0]:
                    rows = list(reversed(rows))
                if "limit" in params:
                    rows = rows[: int(params["limit"])]
                return httpx.Response(200, json=rows)

            if request.method == "POST":
                on_conf = params.get("on_conflict", "")
                if on_conf:
                    keys = [c.strip() for c in on_conf.split(",") if c.strip()]
                    for existing in tables[table]:
                        if all(existing.get(k) == body.get(k) for k in keys):
                            existing.update(body)
                            return httpx.Response(200, json=[dict(existing)])
                seq["id"] += 1
                row = dict(body)
                if table != "producer_heartbeats" and "id" not in row:
                    row["id"] = seq["id"]
                tables[table].append(row)
                return httpx.Response(201, json=[dict(row)])

            if request.method == "PATCH":
                updated = []
                for existing in tables[table]:
                    if _match_params(existing, params):
                        existing.update(body)
                        updated.append(dict(existing))
                return httpx.Response(200, json=updated)

            if request.method == "DELETE":
                tables[table] = [r for r in tables[table] if not _match_params(r, params)]
                return httpx.Response(204)

            return httpx.Response(405)

        mock_client = httpx.Client(transport=httpx.MockTransport(_handler))
        sb = SupabaseRestDatabase("https://demo.supabase.co", "srv-key-secret", client=mock_client)
        try:
            u = sb.upsert_user(
                email="SupaTrader@mw.com",
                password="Secret!123",
                full_name="Trader Cloud",
                plan="pro",
                status="active",
                terms_version="2026.11",
            )
            self.assertEqual(u["email"], "supatrader@mw.com")
            self.assertEqual(u["plan"], "pro")
            self.assertEqual(u["terms_version"], "2026.11")

            fetched = sb.get_user_by_email("supatrader@mw.com")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["id"], u["id"])

            # Excede max_switches=1 na 3ª troca para acionar bloqueio + audit_logs
            sb.record_login_and_check_abuse(u["id"], "s1", "1.1.1.1", "fp1", "ua", max_switches=1, trading_day="2026-11-21")
            sb.record_login_and_check_abuse(u["id"], "s2", "1.1.1.2", "fp2", "ua", max_switches=1, trading_day="2026-11-21")
            res3 = sb.record_login_and_check_abuse(u["id"], "s3", "1.1.1.3", "fp3", "ua", max_switches=1, trading_day="2026-11-21")
            self.assertTrue(res3["blocked"])

            sb.update_producer_heartbeat("vps-sp", "primary", 512, "active")
            ov = sb.get_admin_overview()
            self.assertEqual(len(ov["users"]), 1)
            self.assertEqual(ov["users"][0]["status"], "blocked")
            self.assertEqual(len(ov["open_abuse_flags"]), 1)
            self.assertEqual(len(ov["producers"]), 1)

            unb = sb.unblock_user(u["id"])
            self.assertEqual(unb["status"], "active")
            ov_after = sb.get_admin_overview()
            self.assertEqual(len(ov_after["open_abuse_flags"]), 0)

            sb.accept_terms(u["id"], "2026.12", "187.10.1.1", user_agent="Chrome")
            updated_u = sb.get_user_by_id(u["id"])
            self.assertEqual(updated_u["terms_version"], "2026.12")

            chk = check_supabase("https://demo.supabase.co", "srv-key-secret", client=mock_client)
            self.assertTrue(chk["ok"])
            self.assertEqual(len(chk["tables"]), 6)

            cfg_sb = Settings(
                env="test",
                jwt_secret="a",
                push_hmac_secret="b",
                admin_api_key="c",
                billing_webhook_secret="d",
                mt5_license_secret="e",
                upstash_redis_rest_url="",
                upstash_redis_rest_token="",
                db_path=self.db_path,
                cors_origins=["*"],
                telegram_bot_token="",
                telegram_chat_id="",
                max_device_switches_per_day=4,
                primary_failover_sec=12,
                heartbeat_stale_sec=15,
                terms_version="2026.11",
                jwt_ttl_sec=3600,
                snapshot_ttl_sec=300,
                supabase_url="https://demo.supabase.co",
                supabase_service_role_key="srv-key-secret",
            )
            created_db = create_database(cfg_sb)
            self.assertEqual(created_db.backend_name, "supabase")
            created_db.close()
        finally:
            mock_client.close()

    def test_upstash_rest_store_roundtrip(self) -> None:
        kv: dict[str, str] = {}

        def _upstash_handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers.get("Authorization"), "Bearer upstash-tok")
            cmd = json.loads(request.content.decode("utf-8"))
            op = cmd[0]
            if op == "SET":
                kv[cmd[1]] = cmd[2]
                return httpx.Response(200, json={"result": "OK"})
            if op == "GET":
                return httpx.Response(200, json={"result": kv.get(cmd[1])})
            if op == "DEL":
                removed = 1 if cmd[1] in kv else 0
                kv.pop(cmd[1], None)
                return httpx.Response(200, json={"result": removed})
            return httpx.Response(400, json={"error": f"unsupported cmd {op}"})

        mock_client = httpx.Client(transport=httpx.MockTransport(_upstash_handler))
        try:
            store = UpstashRestStore("https://demo.upstash.io", "upstash-tok", client=mock_client)

            store.set_json("snap:core:etapa1_lite", {"ok": True, "WIN": {"current": 167470}}, ttl_sec=60)
            got = store.get_json("snap:core:etapa1_lite")
            self.assertEqual(got["WIN"]["current"], 167470)

            store.delete("snap:core:etapa1_lite")
            self.assertIsNone(store.get_json("snap:core:etapa1_lite"))

            probe = check_upstash("https://demo.upstash.io", "upstash-tok", client=mock_client)
            self.assertTrue(probe["ok"])
        finally:
            mock_client.close()

    def test_supabase_sb_secret_key_omits_bearer_header(self) -> None:
        seen_headers: list[dict[str, str]] = []

        def _sb_secret_handler(request: httpx.Request) -> httpx.Response:
            seen_headers.append(dict(request.headers))
            self.assertEqual(request.headers.get("apikey"), "sb_secret_demo_2026")
            self.assertNotIn("authorization", {k.lower() for k in request.headers.keys()})
            parts = [p for p in request.url.path.split("/") if p]
            table = parts[-1]
            if table == "profiles" and request.method == "POST":
                return httpx.Response(201, json=[{"id": 1, "email": "newkey@mw.com", "password_hash": "h"}])
            return httpx.Response(200, json=[])

        mock_client = httpx.Client(transport=httpx.MockTransport(_sb_secret_handler))
        try:
            sb = SupabaseRestDatabase(
                "https://yvxxxpsexigaylmebwvz.supabase.co",
                "sb_secret_demo_2026",
                client=mock_client,
            )
            sb.upsert_user(email="newkey@mw.com", password="Secret!123", plan="pro", status="active")
            self.assertGreaterEqual(len(seen_headers), 2)

            chk = check_supabase(
                "https://yvxxxpsexigaylmebwvz.supabase.co",
                "sb_secret_demo_2026",
                client=mock_client,
            )
            self.assertTrue(chk["ok"])
            self.assertEqual(len(chk["tables"]), 6)
            self.assertTrue(all(info.get("ok") for info in chk["tables"].values()))
        finally:
            mock_client.close()

    def test_morning_brief_admin_only(self) -> None:
        self._seed_sample_push()
        self._create_user("core_mb@mw.com", "core")
        self._create_user("pro_mb@mw.com", "pro")
        self._create_user("admin_mb@mw.com", "admin")

        r_unauth = self.client.get("/api/morning-brief")
        self.assertEqual(r_unauth.status_code, 401)
        self.assertEqual(r_unauth.json()["code"], "UNAUTHENTICATED")

        tok_core = self.client.post("/auth/login", json={"email": "core_mb@mw.com", "password": "StrongPassword!123", "device_fp": "fp-core-mb"}).json()["access_token"]
        tok_pro = self.client.post("/auth/login", json={"email": "pro_mb@mw.com", "password": "StrongPassword!123", "device_fp": "fp-pro-mb"}).json()["access_token"]
        tok_admin = self.client.post("/auth/login", json={"email": "admin_mb@mw.com", "password": "StrongPassword!123", "device_fp": "fp-admin-mb"}).json()["access_token"]

        r_core = self.client.get("/api/morning-brief", headers={"Authorization": f"Bearer {tok_core}"})
        self.assertEqual(r_core.status_code, 403)
        self.assertEqual(r_core.json()["code"], "PLAN_UPGRADE_REQUIRED")

        r_pro = self.client.get("/api/morning-brief", headers={"Authorization": f"Bearer {tok_pro}"})
        self.assertEqual(r_pro.status_code, 403)
        self.assertEqual(r_pro.json()["code"], "PLAN_UPGRADE_REQUIRED")

        r_admin = self.client.get("/api/morning-brief", headers={"Authorization": f"Bearer {tok_admin}"})
        self.assertEqual(r_admin.status_code, 200)
        self.assertTrue(r_admin.json()["ok"])
        self.assertEqual(r_admin.json()["win"]["symbol"], "WINFUT")

    def test_etapa1_historical_date_str_served_from_cache(self) -> None:
        payload = {
            "producer_id": "vps-01",
            "producer_role": "primary",
            "snapshots": {
                "core": {
                    "etapa1_lite": {"ok": True, "tier": "core", "selected_date": "2026-11-21"},
                    "etapa1_day_2026-11-19": {"ok": True, "tier": "core", "selected_date": "2026-11-19"},
                },
                "pro": {
                    "etapa1_lite": {"ok": True, "tier": "pro", "selected_date": "2026-11-21"},
                    "etapa1_day_2026-11-19": {"ok": True, "tier": "pro", "selected_date": "2026-11-19"},
                },
            },
        }
        r_push = _signed_push_request(self.client, self.settings.push_hmac_secret, payload)
        self.assertEqual(r_push.status_code, 200)

        self._create_user("core_hist@mw.com", "core")
        self._create_user("pro_hist@mw.com", "pro")
        tok_core = self.client.post("/auth/login", json={"email": "core_hist@mw.com", "password": "StrongPassword!123", "device_fp": "fp-c"}).json()["access_token"]
        tok_pro = self.client.post("/auth/login", json={"email": "pro_hist@mw.com", "password": "StrongPassword!123", "device_fp": "fp-p"}).json()["access_token"]

        rc = self.client.get("/api/compass/etapa1?date_str=2026-11-19&lite=1", headers={"Authorization": f"Bearer {tok_core}"})
        self.assertEqual(rc.status_code, 200)
        self.assertEqual(rc.json()["selected_date"], "2026-11-19")
        self.assertEqual(rc.json()["tier"], "core")

        rp = self.client.get("/api/compass/etapa1?date_str=2026-11-19&lite=1", headers={"Authorization": f"Bearer {tok_pro}"})
        self.assertEqual(rp.status_code, 200)
        self.assertEqual(rp.json()["selected_date"], "2026-11-19")
        self.assertEqual(rp.json()["tier"], "pro")

    def test_etapa1_missing_date_does_not_leak_another_day(self) -> None:
        payload = {
            "producer_id": "vps-01",
            "producer_role": "primary",
            "snapshots": {
                "core": {
                    "etapa1_lite": {
                        "ok": True,
                        "selected_date": "2026-11-20",
                        "available_dates": ["2026-11-20", "2026-11-19"],
                        "WIN": {
                            "active_contract": "WINZ26",
                            "caminho_a": {"m5_dealer_vs_flow_series": [{"time": "09:05", "close": 167500}]},
                        },
                        "WDO": {
                            "active_contract": "WDOZ26",
                            "caminho_a": {"m5_dealer_vs_flow_series": [{"time": "09:05", "close": 5940}]},
                        },
                    },
                },
            },
        }
        r_push = _signed_push_request(self.client, self.settings.push_hmac_secret, payload)
        self.assertEqual(r_push.status_code, 200)

        self._create_user("core_miss@mw.com", "core")
        tok_core = self.client.post("/auth/login", json={"email": "core_miss@mw.com", "password": "StrongPassword!123", "device_fp": "fp-miss"}).json()["access_token"]

        r_miss = self.client.get("/api/compass/etapa1?date_str=2026-11-10&lite=1", headers={"Authorization": f"Bearer {tok_core}"})
        self.assertEqual(r_miss.status_code, 200)
        body = r_miss.json()
        self.assertEqual(body["selected_date"], "2026-11-10")
        self.assertTrue(body["is_historical"])
        self.assertEqual(body["WIN"]["caminho_a"]["m5_dealer_vs_flow_series"], [])
        self.assertEqual(body["WDO"]["caminho_a"]["m5_dealer_vs_flow_series"], [])

    def test_divergencias_motor_accessible_for_core_and_precompute_helper(self) -> None:
        # Constrói sequência sintética realista (>= 25 barras M5) com fundo duplo + divergência de fluxo + Wall próxima
        bars = []
        base_m = 9 * 60
        series_vals = [
            (168100, 168140, 168060, 168080, -10.0),
            (168080, 168100, 167980, 168000, -45.0),
            (168000, 168020, 167880, 167900, -120.0),
            (167900, 167920, 167760, 167780, -240.0),  # F1 px low=167760, wave=-240
            (167780, 167920, 167770, 167900, -80.0),
            (167900, 168060, 167890, 168040, 35.0),
            (168040, 168150, 168020, 168120, 90.0),
            (168120, 168140, 167990, 168010, 40.0),
            (168010, 168020, 167870, 167890, -25.0),
            (167890, 167900, 167750, 167770, -70.0),
            (167770, 167790, 167680, 167700, -95.0),   # F2 lower low=167680, milder wave=-95
            (167700, 167860, 167690, 167840, -15.0),
            (167840, 167980, 167830, 167950, 50.0),
            (167950, 168080, 167940, 168060, 110.0),
            (168060, 168120, 168030, 168100, 125.0),
        ]
        for idx, (op, hi, lo, cl, wv) in enumerate(series_vals):
            hh, mm = divmod(base_m + idx * 5, 60)
            bars.append({
                "time": f"{hh:02d}:{mm:02d}",
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "wave": wv,
                "smart_swing_wave": wv,
            })
        walls = [{"type": "Wall", "price": 167700.0}]

        self._create_user("core_div@mw.com", "core")
        tok_core = self.client.post("/auth/login", json={"email": "core_div@mw.com", "password": "StrongPassword!123", "device_fp": "fp-div"}).json()["access_token"]

        r_div = self.client.post(
            "/api/compass/divergencias_motor",
            json={"asset": "WIN", "engine": "v3.2", "bars": bars, "walls": walls, "trades": []},
            headers={"Authorization": f"Bearer {tok_core}"},
        )
        self.assertEqual(r_div.status_code, 200, r_div.text)
        div_body = r_div.json()
        self.assertTrue(div_body["ok"])
        self.assertGreater(len(div_body["divergences"]), 0)

        snap = {
            "WIN": {
                "all_walls": walls,
                "caminho_a": {
                    "m5_dealer_vs_flow_series": bars,
                    "signals_log": [],
                },
            }
        }
        enriched = _attach_precomputed_divs(snap, include_trades=False)
        self.assertGreater(len(enriched["WIN"]["caminho_a"]["engine_divs_v32"]), 0)

    def test_cached_resilient_store_survives_upstash_suspension(self) -> None:
        l2_calls = {"count": 0}

        def _suspended_upstash(_request: httpx.Request) -> httpx.Response:
            l2_calls["count"] += 1
            return httpx.Response(403, json={"error": "database suspended"})

        mock_client = httpx.Client(transport=httpx.MockTransport(_suspended_upstash))
        try:
            l1 = MemoryTTLStore()
            l2 = UpstashRestStore("https://demo.upstash.io", "upstash-tok", client=mock_client)
            store = CachedResilientStore(l1, l2, backoff_sec=60.0)

            big_payload = {"ok": True, "blob": "A" * 2500}
            store.set_json("snap:pro:etapa1_lite", big_payload, ttl_sec=120)
            self.assertEqual(l2_calls["count"], 1)

            # L1 RAM atende normalmente e cacheia backoff sem gerar HTTP 500
            got = store.get_json("snap:pro:etapa1_lite")
            self.assertEqual(got, big_payload)
            self.assertIsNone(store.get_json("snap:missing:key"))
            self.assertEqual(l2_calls["count"], 1)
        finally:
            mock_client.close()

    def test_session_rehydrates_from_db_after_ram_restart(self) -> None:
        self._seed_sample_push()
        self._create_user("rehydrate@mw.com", "pro")

        tok_a = self.client.post(
            "/auth/login",
            json={"email": "rehydrate@mw.com", "password": "StrongPassword!123", "device_fp": "pc-a"},
        ).json()["access_token"]
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok_a}"}).status_code, 200)

        # Simula restart do container limpando toda a RAM de store
        self.app.state.store._data.clear()

        # Sessão ativa é re-hidratada automaticamente a partir de active_sessions
        r_after = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok_a}"})
        self.assertEqual(r_after.status_code, 200, r_after.text)

        # Novo login em outro aparelho substitui a sessão no DB e derruba tok_a
        tok_b = self.client.post(
            "/auth/login",
            json={"email": "rehydrate@mw.com", "password": "StrongPassword!123", "device_fp": "pc-b"},
        ).json()["access_token"]
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok_b}"}).status_code, 200)
        r_old = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok_a}"})
        self.assertEqual(r_old.status_code, 401)
        self.assertEqual(r_old.json()["code"], "SESSION_REPLACED")

    def test_etag_304_not_modified_and_needs_backfill_signal(self) -> None:
        r_push = self._seed_sample_push(marker="v1")
        self.assertEqual(r_push.status_code, 200)
        self.assertTrue(r_push.json()["needs_backfill"])

        self._create_user("etag@mw.com", "pro")
        tok = self.client.post(
            "/auth/login",
            json={"email": "etag@mw.com", "password": "StrongPassword!123", "device_fp": "fp-etag"},
        ).json()["access_token"]

        r1 = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r1.status_code, 200)
        etag1 = r1.headers.get("etag")
        self.assertTrue(etag1)

        r304 = self.client.get(
            "/api/compass/etapa1?lite=1",
            headers={"Authorization": f"Bearer {tok}", "If-None-Match": etag1},
        )
        self.assertEqual(r304.status_code, 304)
        self.assertEqual(r304.content, b"")

        r_day = _signed_push_request(
            self.client,
            self.settings.push_hmac_secret,
            {
                "producer_id": "vps-01",
                "producer_role": "primary",
                "snapshots": {
                    "pro": {"etapa1_day_2026-11-19": {"ok": True, "selected_date": "2026-11-19"}}
                },
            },
        )
        self.assertEqual(r_day.status_code, 200)
        self.assertFalse(r_day.json()["needs_backfill"])

        self._seed_sample_push(marker="v2")
        r2 = self.client.get(
            "/api/compass/etapa1?lite=1",
            headers={"Authorization": f"Bearer {tok}", "If-None-Match": etag1},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertNotEqual(r2.headers.get("etag"), etag1)
        self.assertEqual(r2.json()["marker"], "v2")

    def test_user_cache_invalidation_on_admin_mutations(self) -> None:
        self._create_user("cacheinv@mw.com", "pro")
        tok = self.client.post(
            "/auth/login",
            json={"email": "cacheinv@mw.com", "password": "StrongPassword!123", "device_fp": "fp-c"},
        ).json()["access_token"]
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code, 200)

        r_susp = self.client.post(
            "/api/v1/admin/users",
            json={"email": "cacheinv@mw.com", "plan": "pro", "status": "suspended"},
            headers=self.admin_headers,
        )
        self.assertEqual(r_susp.status_code, 200)

        r_blocked = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_blocked.status_code, 403)
        self.assertEqual(r_blocked.json()["code"], "SUBSCRIPTION_INACTIVE")

        r_act = self.client.post(
            "/api/v1/admin/users",
            json={"email": "cacheinv@mw.com", "plan": "pro", "status": "active", "days": 30},
            headers=self.admin_headers,
        )
        self.assertEqual(r_act.status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code, 200)

    def test_heartbeat_only_keeps_feed_live_and_publisher_dedup(self) -> None:
        self._seed_sample_push(marker="live-snap")
        r_hb = _signed_push_request(
            self.client,
            self.settings.push_hmac_secret,
            {"producer_id": "vps-01", "producer_role": "primary", "heartbeat_only": True},
        )
        self.assertEqual(r_hb.status_code, 200)
        self.assertEqual(r_hb.json()["mode"], "heartbeat_only")
        self.assertTrue(r_hb.json()["needs_backfill"])
        self.assertEqual(self.client.get("/api/v1/feed/status").json()["status"], "live")

        posted: list[dict] = []
        pub = CloudPublisher("https://cloud.local", "http://127.0.0.1:8080", "sec", "pc-dedup")
        try:
            pub._last_backfill_mono = time.monotonic()
            sample_snap = {"core": {"etapa1_lite": {"ok": True, "t": 1}}, "pro": {"etapa1_lite": {"ok": True, "t": 1}}, "admin": {}}
            pub.build_snapshots = lambda force_all=False, include_days=True: sample_snap  # type: ignore[method-assign]

            def _fake_post(snapshots=None, heartbeat_only=False):
                posted.append({"hb": heartbeat_only, "snaps": snapshots})
                return True, {"ok": True, "needs_backfill": False}

            pub._post_snapshots_payload = _fake_post  # type: ignore[method-assign]
            ok1, _ = pub.push_once(force_all=False)
            ok2, _ = pub.push_once(force_all=False)
            self.assertTrue(ok1 and ok2)
            self.assertFalse(posted[0]["hb"])
            self.assertTrue(posted[1]["hb"])
        finally:
            pub.close()

    def _register_trial(self, client: TestClient, **overrides) -> httpx.Response:
        payload = {
            "full_name": "Trader Teste",
            "email": "trader1@gmail.com",
            "phone": "(11) 98765-4321",
            "password": "StrongPassword!123",
            "accept_terms": True,
            "terms_version": self.settings.terms_version,
            "device_fp": "fp-trial-1",
            "utm_source": "instagram",
        }
        payload.update(overrides)
        ip = overrides.pop("_ip", "200.10.10.1")
        payload.pop("_ip", None)
        return client.post("/auth/trial/register", json=payload, headers={"X-Forwarded-For": ip})

    def test_trial_registration_immediate_access_and_entitlements(self) -> None:
        self._seed_sample_push()
        cfg_resp = self.client.get("/api/v1/public/trial-config")
        self.assertEqual(cfg_resp.status_code, 200)
        cfg_body = cfg_resp.json()
        self.assertEqual(cfg_body["mode"], "open")
        self.assertEqual(cfg_body["trial_days"], 15)
        self.assertTrue(cfg_body["accepting_trials"])
        self.assertEqual(cfg_body["slots_remaining"], 50)

        r_reg = self._register_trial(self.client)
        self.assertEqual(r_reg.status_code, 200, r_reg.text)
        reg_json = r_reg.json()
        self.assertTrue(reg_json["ok"])
        tok = reg_json["access_token"]
        self.assertTrue(tok)
        self.assertEqual(reg_json["user"]["plan"], "trial")
        self.assertTrue(reg_json["user"]["is_trial"])
        self.assertEqual(reg_json["user"]["trial_days_left"], 15)
        self.assertEqual(reg_json["user"]["phone"], "5511987654321")
        self.assertTrue(reg_json["user"]["terms_accepted"])

        # Trial tem acesso CORE liberado na hora e PRO/ADMIN bloqueados
        r_core = self.client.get("/api/compass/etapa1?lite=1", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_core.status_code, 200)
        self.assertEqual(r_core.json()["tier"], "core")

        r_pro = self.client.get("/api/v2/regime", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_pro.status_code, 403)
        self.assertEqual(r_pro.json()["code"], "PLAN_UPGRADE_REQUIRED")

        r_adm = self.client.get("/api/morning-brief", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_adm.status_code, 403)
        self.assertEqual(r_adm.json()["code"], "PLAN_UPGRADE_REQUIRED")

        cfg_after = self.client.get("/api/v1/public/trial-config").json()
        self.assertEqual(cfg_after["active_trials"], 1)
        self.assertEqual(cfg_after["slots_remaining"], 49)

    def test_trial_anti_abuse_canonical_email_phone_disposable_and_rate_limit(self) -> None:
        self.assertEqual(canonicalize_email("J.Oao.Silva+promo@googlemail.com"), "joaosilva@gmail.com")
        self.assertEqual(normalize_br_phone("(11) 98765-4321"), "5511987654321")
        self.assertEqual(normalize_br_phone("+55 11 98765-4321"), "5511987654321")
        self.assertEqual(normalize_br_phone("11999999999"), "")
        self.assertEqual(normalize_br_phone("05987654321"), "")

        # E-mail descartável bloqueado
        r_disp = self._register_trial(self.client, email="fake@mailinator.com")
        self.assertEqual(r_disp.status_code, 400)
        self.assertEqual(r_disp.json()["code"], "DISPOSABLE_EMAIL_NOT_ALLOWED")

        # WhatsApp inválido bloqueado
        r_ph = self._register_trial(self.client, phone="11999999999")
        self.assertEqual(r_ph.status_code, 400)
        self.assertEqual(r_ph.json()["code"], "INVALID_PHONE")

        # 1º cadastro OK
        r1 = self._register_trial(
            self.client,
            email="joao.silva@gmail.com",
            phone="(11) 98765-4321",
            device_fp="fp-a",
            _ip="198.51.100.10",
        )
        self.assertEqual(r1.status_code, 200, r1.text)

        # Alias Gmail (+tag / pontos) bloqueado como duplicado
        r_alias = self._register_trial(
            self.client,
            email="joaosilva+teste2@gmail.com",
            phone="(21) 98888-7777",
            device_fp="fp-b",
            _ip="198.51.100.11",
        )
        self.assertEqual(r_alias.status_code, 409)
        self.assertEqual(r_alias.json()["code"], "TRIAL_ALREADY_USED")

        # Mesmo WhatsApp com e-mail diferente bloqueado
        r_same_phone = self._register_trial(
            self.client,
            email="outro.trader@outlook.com",
            phone="+55 (11) 98765-4321",
            device_fp="fp-c",
            _ip="198.51.100.12",
        )
        self.assertEqual(r_same_phone.status_code, 409)
        self.assertEqual(r_same_phone.json()["code"], "TRIAL_ALREADY_USED")

        # Rate limit por IP/device_fp sobrevive a reset de RAM (consulta audit_logs)
        r2 = self._register_trial(
            self.client,
            email="segundo@outlook.com",
            phone="(21) 98111-2222",
            device_fp="fp-a",
            _ip="198.51.100.10",
        )
        self.assertEqual(r2.status_code, 200, r2.text)

        self.app.state.store._data.clear()
        r3_rl = self._register_trial(
            self.client,
            email="terceiro@outlook.com",
            phone="(31) 98333-4444",
            device_fp="fp-a",
            _ip="198.51.100.10",
        )
        self.assertEqual(r3_rl.status_code, 429)
        self.assertEqual(r3_rl.json()["code"], "TRIAL_RATE_LIMITED")

    def test_trial_capacity_cap_and_waitlist_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_settings(os.path.join(td, "cap.db"))
            cfg.trial_max_active = 2
            app_cap = create_app(cfg)
            client_cap = TestClient(app_cap)
            try:
                r1 = self._register_trial(client_cap, email="c1@mw.com", phone="(11) 98111-1111", device_fp="fp1", _ip="10.0.0.1")
                r2 = self._register_trial(client_cap, email="c2@mw.com", phone="(11) 98222-2222", device_fp="fp2", _ip="10.0.0.2")
                self.assertEqual(r1.status_code, 200)
                self.assertEqual(r2.status_code, 200)

                pub = client_cap.get("/api/v1/public/trial-config").json()
                self.assertFalse(pub["accepting_trials"])
                self.assertEqual(pub["slots_remaining"], 0)

                r3 = self._register_trial(client_cap, email="c3@mw.com", phone="(11) 98333-3333", device_fp="fp3", _ip="10.0.0.3")
                self.assertEqual(r3.status_code, 409)
                self.assertEqual(r3.json()["code"], "TRIAL_CAPACITY_REACHED")

                rwl = client_cap.post(
                    "/api/v1/public/waitlist",
                    json={"full_name": "Lead Espera", "email": "c3@mw.com", "phone": "(11) 98333-3333", "utm_source": "ig"},
                )
                self.assertEqual(rwl.status_code, 200, rwl.text)
                self.assertTrue(rwl.json()["ok"])

                rep = client_cap.get("/api/v1/admin/trials", headers={"X-Admin-Key": cfg.admin_api_key}).json()
                self.assertEqual(rep["summary"]["active_trials"], 2)
                self.assertEqual(rep["summary"]["waitlist_count"], 1)
                self.assertEqual(rep["waitlist"][0]["email"], "c3@mw.com")
            finally:
                app_cap.state.db.close()

    def test_trial_invite_only_mode_and_max_uses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_settings(os.path.join(td, "inv.db"))
            cfg.trial_mode = "invite_only"
            app_inv = create_app(cfg)
            client_inv = TestClient(app_inv)
            adm_h = {"X-Admin-Key": cfg.admin_api_key}
            try:
                pub = client_inv.get("/api/v1/public/trial-config").json()
                self.assertTrue(pub["require_invite_code"])

                r_no = self._register_trial(client_inv, email="noinv@mw.com", phone="(11) 98444-4444", device_fp="f1", _ip="10.0.1.1")
                self.assertEqual(r_no.status_code, 400)
                self.assertEqual(r_no.json()["code"], "INVALID_INVITE_CODE")

                r_create_inv = client_inv.post(
                    "/api/v1/admin/invites",
                    json={"code": "vip21", "label": "Turma VIP", "trial_days": 21, "max_uses": 1},
                    headers=adm_h,
                )
                self.assertEqual(r_create_inv.status_code, 200)
                self.assertEqual(r_create_inv.json()["invite"]["code"], "VIP21")

                r_ok = self._register_trial(
                    client_inv,
                    email="vip1@mw.com",
                    phone="(11) 98555-5555",
                    invite_code="vip21",
                    device_fp="f2",
                    _ip="10.0.1.2",
                )
                self.assertEqual(r_ok.status_code, 200, r_ok.text)
                self.assertEqual(r_ok.json()["user"]["trial_days_left"], 21)

                r_exhausted = self._register_trial(
                    client_inv,
                    email="vip2@mw.com",
                    phone="(11) 98666-6666",
                    invite_code="VIP21",
                    device_fp="f3",
                    _ip="10.0.1.3",
                )
                self.assertEqual(r_exhausted.status_code, 400)
                self.assertEqual(r_exhausted.json()["code"], "INVALID_INVITE_CODE")
            finally:
                app_inv.state.db.close()

    @patch("cloud_saas.security.httpx.post")
    def test_trial_turnstile_verification(self, mock_post) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_settings(os.path.join(td, "ts.db"))
            cfg.turnstile_site_key = "0x4AAAAAAA_test_site"
            cfg.turnstile_secret_key = "0x4AAAAAAA_test_secret"
            app_ts = create_app(cfg)
            client_ts = TestClient(app_ts)
            try:
                r_empty = self._register_trial(client_ts, email="ts0@mw.com", phone="(11) 98100-0001", turnstile_token="")
                self.assertEqual(r_empty.status_code, 400)
                self.assertEqual(r_empty.json()["code"], "TURNSTILE_FAILED")

                mock_post.return_value = httpx.Response(200, json={"success": False, "error-codes": ["invalid-input-response"]})
                r_fail = self._register_trial(client_ts, email="ts1@mw.com", phone="(11) 98100-0002", turnstile_token="bad-tok")
                self.assertEqual(r_fail.status_code, 400)
                self.assertEqual(r_fail.json()["code"], "TURNSTILE_FAILED")

                mock_post.return_value = httpx.Response(200, json={"success": True})
                r_pass = self._register_trial(client_ts, email="ts2@mw.com", phone="(11) 98100-0003", turnstile_token="good-tok")
                self.assertEqual(r_pass.status_code, 200, r_pass.text)
            finally:
                app_ts.state.db.close()

    def test_trial_expired_conversion_intent_extend_and_billing_upgrade(self) -> None:
        r_reg = self._register_trial(self.client, email="exp@mw.com", phone="(11) 98777-8888", device_fp="fp-exp")
        self.assertEqual(r_reg.status_code, 200)
        uid = r_reg.json()["user"]["id"]
        tok = r_reg.json()["access_token"]

        # Simula expiração ontem
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
        with self.app.state.db._lock:
            self.app.state.db._conn.execute(
                "UPDATE subscriptions SET expires_at = ? WHERE user_id = ?",
                (yesterday, uid),
            )
            self.app.state.db._conn.commit()
        self.app.state.store.delete(f"user:{uid}")

        r_me_exp = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r_me_exp.status_code, 403)
        self.assertEqual(r_me_exp.json()["code"], "TRIAL_EXPIRED")

        r_login_exp = self.client.post("/auth/login", json={"email": "exp@mw.com", "password": "StrongPassword!123", "device_fp": "fp-exp"})
        self.assertEqual(r_login_exp.status_code, 403)
        self.assertEqual(r_login_exp.json()["code"], "TRIAL_EXPIRED")

        # Usuário registra intenção de pagamento usando o próprio JWT expirado ou e-mail
        r_ci = self.client.post(
            "/auth/trial/conversion-intent",
            json={"email": "exp@mw.com", "note": "Quero assinar PRO"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        self.assertEqual(r_ci.status_code, 200, r_ci.text)

        rep = self.client.get("/api/v1/admin/trials", headers=self.admin_headers).json()
        self.assertEqual(rep["summary"]["expired_trials"], 1)
        self.assertEqual(rep["summary"]["conversion_intents_count"], 1)

        # Admin estende por +10 dias e libera acesso novamente
        r_ext = self.client.post(f"/api/v1/admin/users/{uid}/extend", json={"days": 10}, headers=self.admin_headers)
        self.assertEqual(r_ext.status_code, 200)
        self.assertEqual(r_ext.json()["user"]["trial_days_left"], 10)
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code, 200)

        # Ponte futura: webhook de pagamento promove trial para PRO preservando user_id e senha
        paid_body = json.dumps({"event": "paid", "email": "exp@mw.com", "plan": "pro", "days": 30, "gateway": "asaas"}).encode("utf-8")
        sig = compute_webhook_signature(self.settings.billing_webhook_secret, paid_body)
        r_paid = self.client.post("/webhooks/billing", content=paid_body, headers={"X-MW-Webhook-Signature": sig, "Content-Type": "application/json"})
        self.assertEqual(r_paid.status_code, 200)
        self.assertEqual(r_paid.json()["user_id"], uid)
        self.assertEqual(r_paid.json()["plan"], "pro")

        r_login_pro = self.client.post("/auth/login", json={"email": "exp@mw.com", "password": "StrongPassword!123", "device_fp": "fp-exp"})
        self.assertEqual(r_login_pro.status_code, 200)
        self.assertEqual(r_login_pro.json()["user"]["plan"], "pro")
        self.assertFalse(r_login_pro.json()["user"]["is_trial"])

    def test_supabase_rest_trial_invite_waitlist_flow(self) -> None:
        tables: dict[str, list[dict]] = {
            "profiles": [],
            "subscriptions": [],
            "active_sessions": [],
            "terms_acceptance": [],
            "audit_logs": [],
            "producer_heartbeats": [],
            "trial_invites": [],
            "waitlist_leads": [],
        }
        seq = {"id": 0}

        def _match_params(row: dict, params: dict[str, str]) -> bool:
            for k, v in params.items():
                if k in ("select", "order", "limit", "on_conflict"):
                    continue
                if "." not in v:
                    continue
                op, expected = v.split(".", 1)
                actual = row.get(k)
                if expected == "true":
                    exp_val = True
                elif expected == "false":
                    exp_val = False
                elif expected.lstrip("-").isdigit() and isinstance(actual, int):
                    exp_val = int(expected)
                else:
                    exp_val = expected
                if op == "eq" and actual != exp_val:
                    return False
                if op == "neq" and actual == exp_val:
                    return False
            return True

        def _handler(request: httpx.Request) -> httpx.Response:
            parts = [p for p in request.url.path.split("/") if p]
            table = parts[-1]
            params = dict(request.url.params)
            body = json.loads(request.content.decode("utf-8")) if request.content else None

            if request.method == "GET":
                rows = [dict(r) for r in tables[table] if _match_params(r, params)]
                if "order" in params and "desc" in params["order"] and rows and "id" in rows[0]:
                    rows = list(reversed(rows))
                if "limit" in params:
                    rows = rows[: int(params["limit"])]
                return httpx.Response(200, json=rows)

            if request.method == "POST":
                on_conf = params.get("on_conflict", "")
                if on_conf:
                    keys = [c.strip() for c in on_conf.split(",") if c.strip()]
                    for existing in tables[table]:
                        if all(existing.get(k) == body.get(k) for k in keys):
                            existing.update(body)
                            return httpx.Response(200, json=[dict(existing)])
                seq["id"] += 1
                row = dict(body)
                if table not in ("producer_heartbeats", "trial_invites") and "id" not in row:
                    row["id"] = seq["id"]
                tables[table].append(row)
                return httpx.Response(201, json=[dict(row)])

            if request.method == "PATCH":
                updated = []
                for existing in tables[table]:
                    if _match_params(existing, params):
                        existing.update(body)
                        updated.append(dict(existing))
                return httpx.Response(200, json=updated)

            if request.method == "DELETE":
                tables[table] = [r for r in tables[table] if not _match_params(r, params)]
                return httpx.Response(204)

            return httpx.Response(405)

        mock_client = httpx.Client(transport=httpx.MockTransport(_handler))
        sb = SupabaseRestDatabase("https://demo.supabase.co", "srv-key-secret", client=mock_client)
        try:
            inv = sb.upsert_invite("IG15", label="Bio IG", trial_days=15, max_uses=5)
            self.assertEqual(inv["code"], "IG15")

            u = sb.create_trial_user(
                email="sb_trial@gmail.com",
                email_canonical="sbtrial@gmail.com",
                password="StrongPassword!123",
                full_name="Trader SB",
                phone="5511998765432",
                trial_days=15,
                terms_version="2026.11",
                ip="200.1.2.3",
                user_agent="pytest",
                acquisition_source="instagram",
                acquisition_meta={"invite_code": "IG15"},
            )
            self.assertEqual(u["plan"], "trial")
            self.assertEqual(u["phone"], "5511998765432")
            sb.increment_invite_usage("IG15")
            sb.log_audit(u["id"], "TRIAL_ACTIVATED", ip="200.1.2.3", device_fp="fp-sb")

            self.assertEqual(sb.count_active_trials(), 1)
            self.assertIsNotNone(sb.get_user_by_canonical_email("sbtrial@gmail.com"))
            self.assertIsNotNone(sb.get_user_by_phone("5511998765432"))
            rl = sb.count_recent_trial_registrations("200.1.2.3", "fp-sb")
            self.assertEqual(rl["ip_24h"], 1)
            self.assertEqual(rl["fp_30d"], 1)

            sb.upsert_waitlist_lead("lead@mw.com", full_name="Lead SB", phone="5511988881111", source="waitlist")
            ext = sb.extend_user_subscription(u["id"], 5)
            self.assertIsNotNone(ext)

            rep = sb.get_admin_trials_report()
            self.assertEqual(rep["summary"]["active_trials"], 1)
            self.assertEqual(rep["summary"]["waitlist_count"], 1)
            self.assertEqual(rep["invites"][0]["used_count"], 1)
        finally:
            mock_client.close()


class HealthEndpointsTests(unittest.TestCase):
    """/api/health e /api/v1/admin/health leem os arquivos do coletor de saúde (MW_HEALTH_DIR)."""

    def _write(self, directory: str, name: str, generated_at: datetime, with_detail: bool):
        comp = {"status": "ok", "summary": "ok", "since": "2026-11-25T14:00:00Z"}
        if with_detail:
            comp["detail"] = {"caminho": "/interno"}
        payload = {
            "schema": 1,
            "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "market_open": True,
            "status": "ok",
            "summary": "tudo funcionando",
            "components": {"mt5": comp},
        }
        with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def _client(self, directory: str):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))
        patcher = patch.dict(os.environ, {"MW_HEALTH_DIR": directory})
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(create_app(_make_settings(db_path)))

    def test_public_health_returns_file_without_detail(self):
        with tempfile.TemporaryDirectory() as d:
            now = datetime.now(timezone.utc)
            self._write(d, "health.json", now, with_detail=True)
            r = self._client(d).get("/api/health")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["status"], "ok")
            self.assertNotIn("detail", body["components"]["mt5"])
            self.assertEqual(r.headers.get("cache-control"), "no-store")

    def test_health_unknown_when_file_missing_or_stale(self):
        with tempfile.TemporaryDirectory() as d:
            client = self._client(d)
            r = client.get("/api/health")
            self.assertEqual(r.json()["status"], "unknown")
            self.assertEqual(r.json()["summary"], "coletor de saúde sem atualizar")
            self._write(d, "health.json", datetime.now(timezone.utc) - timedelta(seconds=300), with_detail=False)
            r = client.get("/api/health")
            self.assertEqual(r.json()["status"], "unknown")
            self.assertEqual(r.json()["components"], {})

    def test_admin_health_requires_key_and_keeps_detail(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "health-admin.json", datetime.now(timezone.utc), with_detail=True)
            client = self._client(d)
            self.assertEqual(client.get("/api/v1/admin/health").status_code, 401)
            r = client.get("/api/v1/admin/health", headers={"X-Admin-Key": "test-admin-api-key"})
            self.assertEqual(r.status_code, 200)
            self.assertIn("detail", r.json()["components"]["mt5"])

    def test_liveness_health_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            r = self._client(d).get("/health")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["ok"])


if __name__ == "__main__":
    unittest.main()
