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
from cloud_saas.database import SupabaseRestDatabase, create_database
from cloud_saas.security import compute_push_signature, compute_webhook_signature
from cloud_saas.store import UpstashRestStore
from scripts.cloud_publisher import HeartbeatMonitor, _attach_precomputed_divs
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


if __name__ == "__main__":
    unittest.main()
