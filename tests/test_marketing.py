# -*- coding: utf-8 -*-
"""Testes do módulo de marketing: aprovação obrigatória, simulação por padrão, mídia, chave geral e canal Meta falso."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from cloud_saas.app import create_app
from cloud_saas.marketing import routes as mkt_routes
from cloud_saas.marketing.channels import ChannelError, InstagramChannel
from cloud_saas.marketing.routes import DISCLAIMER
from tests.test_cloud_saas import _make_settings

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
GOOD_CAPTION = f"Resumo do pregão.\n\n{DISCLAIMER}\n#MagicWalls"


class FakeChannel:
    name = "instagram"

    def __init__(self, configured=True, fail=None):
        self.configured = configured
        self.fail = fail
        self.calls = []

    def publish(self, *, media_url, media_type, caption):
        self.calls.append((media_url, media_type, caption))
        if self.fail:
            raise ChannelError("HTTP_400", self.fail)
        return "17900000000000001"

    def check_account(self):
        return {"account": {"id": "1", "username": "magicwallsb3"}, "limit": {"data": []}}


class MarketingBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = patch.dict(os.environ, {"MW_PUBLIC_BASE_URL": "https://api.example.test"})
        env.start()
        self.addCleanup(env.stop)
        self.channel = FakeChannel()
        factory = patch.object(
            mkt_routes, "InstagramChannel", lambda *a, **k: self.channel
        )
        factory.start()
        self.addCleanup(factory.stop)
        self.settings = _make_settings(os.path.join(self._tmp.name, "saas.db"))
        self.app = create_app(self.settings)
        self.addCleanup(self.app.state.db.close)
        self.client = TestClient(self.app)
        self.admin_key = {"X-Admin-Key": self.settings.admin_api_key}
        self.hdr = self._login("admin@test.local", "admin")

    def _login(self, email: str, plan: str) -> dict:
        r = self.client.post("/api/v1/admin/users", headers=self.admin_key, json={
            "email": email, "password": "StrongPassword!123", "full_name": "Teste", "plan": plan,
            "status": "active", "days": 30, "terms_version": self.settings.terms_version,
        })
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/auth/login", json={"email": email, "password": "StrongPassword!123"})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    API = "/api/v1/admin/marketing"

    def make_post(self, caption=GOOD_CAPTION, ref_date="2026-11-25", headers=None) -> str:
        r = self.client.post(f"{self.API}/posts", headers=headers or self.hdr, json={
            "channel": "instagram", "kind": "end_of_day", "asset": "wdo", "ref_date": ref_date,
            "caption": caption,
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["post"]["id"]

    def upload(self, post_id, data=PNG, ctype="image/png"):
        return self.client.post(f"{self.API}/posts/{post_id}/media", headers=dict(self.hdr, **{"Content-Type": ctype}),
                                content=data)

    def approved_post(self, ref_date="2026-11-25") -> str:
        pid = self.make_post(ref_date=ref_date)
        self.assertEqual(self.upload(pid).status_code, 200)
        self.assertEqual(self.client.post(f"{self.API}/posts/{pid}/approve", headers=self.hdr).status_code, 200)
        return pid


class AccessTests(MarketingBase):
    def test_requires_admin_plan(self):
        pro = self._login("pro@test.local", "pro")
        self.assertEqual(self.client.get(f"{self.API}/posts", headers=pro).status_code, 403)
        self.assertEqual(self.client.get(f"{self.API}/posts").status_code, 401)
        self.assertEqual(self.client.get(f"{self.API}/posts", headers=self.hdr).status_code, 200)

    def test_status_reports_dry_run_and_channel(self):
        body = self.client.get(f"{self.API}/status", headers=self.hdr).json()
        self.assertTrue(body["enabled"])
        self.assertFalse(body["live"])
        self.assertTrue(body["channels"]["instagram"]["configured"])


class ApprovalRulesTests(MarketingBase):
    def approve(self, pid):
        return self.client.post(f"{self.API}/posts/{pid}/approve", headers=self.hdr)

    def test_cannot_approve_without_media(self):
        r = self.approve(self.make_post())
        self.assertEqual((r.status_code, r.json()["code"]), (422, "MEDIA_REQUIRED"))

    def test_cannot_approve_without_disclaimer(self):
        pid = self.make_post(caption="Só texto, sem aviso.")
        self.upload(pid)
        r = self.approve(pid)
        self.assertEqual((r.status_code, r.json()["code"]), (422, "DISCLAIMER_REQUIRED"))

    def test_cannot_approve_too_many_hashtags(self):
        pid = self.make_post(caption=DISCLAIMER + " " + " ".join(f"#t{i}" for i in range(31)))
        self.upload(pid)
        self.assertEqual(self.approve(pid).json()["code"], "TOO_MANY_HASHTAGS")

    def test_editing_caption_or_media_resets_approval(self):
        pid = self.approved_post()
        r = self.client.patch(f"{self.API}/posts/{pid}", headers=self.hdr, json={"caption": GOOD_CAPTION + " v2"})
        self.assertEqual(r.json()["post"]["status"], "draft")
        self.assertEqual(self.approve(pid).status_code, 200)
        self.upload(pid, MP4, "video/mp4")
        got = self.client.get(f"{self.API}/posts/{pid}", headers=self.hdr).json()["post"]
        self.assertEqual(got["status"], "draft")

    def test_admin_can_preview_media_before_approval_but_public_link_stays_closed(self):
        pid = self.make_post()
        self.upload(pid)
        r = self.client.get(f"{self.API}/posts/{pid}/media", headers=self.hdr)
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "image/png"))
        self.assertEqual(self.client.get(f"{self.API}/posts/{pid}/media").status_code, 401)
        view = self.client.get(f"{self.API}/posts/{pid}", headers=self.hdr).json()["post"]
        self.assertEqual(view["media_url"], "")  # rascunho: sem link público

    def test_media_validation(self):
        pid = self.make_post()
        self.assertEqual(self.upload(pid, b"not a png", "image/png").json()["code"], "BAD_MEDIA_CONTENT")
        self.assertEqual(self.upload(pid, PNG, "text/html").json()["code"], "BAD_MEDIA_TYPE")
        self.assertEqual(self.upload(pid, b"", "image/png").json()["code"], "EMPTY_MEDIA")
        self.assertEqual(self.upload(pid, b"\x89PNG\r\n\x1a\n" + b"0" * (8 * 1024 * 1024), "image/png").json()["code"],
                         "MEDIA_TOO_LARGE")


class PublishTests(MarketingBase):
    def publish(self, pid, confirm=True):
        return self.client.post(f"{self.API}/posts/{pid}/publish", headers=self.hdr, json={"confirm": confirm})

    def go_live(self):
        env = patch.dict(os.environ, {"MW_MARKETING_LIVE": "1"})
        env.start()
        self.addCleanup(env.stop)

    def _live_client(self):
        """Recria o app com executor síncrono e modo real ligado."""
        self.go_live()
        sync = lambda fn: fn()  # noqa: E731
        patcher = patch.object(mkt_routes, "_default_runner", sync)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app.state.db.close()
        self.app = create_app(self.settings)
        self.addCleanup(self.app.state.db.close)
        self.client = TestClient(self.app)
        self.hdr = self._login("admin2@test.local", "admin")

    def test_unapproved_post_is_never_published(self):
        pid = self.make_post()
        self.upload(pid)
        r = self.publish(pid)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "NOT_APPROVED"))
        self.assertEqual(self.channel.calls, [])

    def test_confirm_is_required(self):
        pid = self.approved_post()
        self.assertEqual(self.publish(pid, confirm=False).json()["code"], "CONFIRM_REQUIRED")

    def test_default_mode_is_dry_run_and_does_not_call_meta(self):
        pid = self.approved_post()
        r = self.publish(pid)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["dry_run"])
        self.assertEqual(self.channel.calls, [])
        got = self.client.get(f"{self.API}/posts/{pid}", headers=self.hdr).json()
        self.assertEqual(got["post"]["status"], "approved")
        self.assertIn("dry_run_publish", [e["action"] for e in got["events"]])

    def test_live_publish_success_removes_media_and_closes_public_url(self):
        self._live_client()
        pid = self.approved_post()
        media_url = self.client.get(f"{self.API}/posts/{pid}", headers=self.hdr).json()["post"]["media_url"]
        token_path = media_url.replace("https://api.example.test", "")
        self.assertEqual(self.client.get(token_path).status_code, 200)  # a Meta consegue buscar enquanto aprovado
        r = self.publish(pid)
        self.assertEqual(r.status_code, 200, r.text)
        got = self.client.get(f"{self.API}/posts/{pid}", headers=self.hdr).json()["post"]
        self.assertEqual(got["status"], "published")
        self.assertEqual(got["external_id"], "17900000000000001")
        self.assertEqual(len(self.channel.calls), 1)
        self.assertEqual(self.channel.calls[0][1], "image")
        self.assertEqual(self.client.get(token_path).status_code, 404)  # URL pública fechada depois de publicar
        again = self.publish(pid)
        self.assertEqual(again.json()["code"], "NOT_APPROVED")  # nunca publica duas vezes

    def test_live_publish_failure_is_recorded_and_retryable(self):
        self._live_client()
        self.channel.fail = "token expirado"
        pid = self.approved_post()
        self.publish(pid)
        got = self.client.get(f"{self.API}/posts/{pid}", headers=self.hdr).json()["post"]
        self.assertEqual(got["status"], "failed")
        self.assertIn("token expirado", got["error"])
        self.assertEqual(self.client.post(f"{self.API}/posts/{pid}/retry", headers=self.hdr).json()["post"]["status"],
                         "draft")

    def test_kill_switch_blocks_publish(self):
        pid = self.approved_post()
        self.client.put(f"{self.API}/switch", headers=self.hdr, json={"enabled": False})
        self.assertEqual(self.publish(pid).json()["code"], "MARKETING_DISABLED")
        self.client.put(f"{self.API}/switch", headers=self.hdr, json={"enabled": True})
        self.assertEqual(self.publish(pid).status_code, 200)

    def test_unconfigured_channel_blocks_publish(self):
        pid = self.approved_post()
        self.channel.configured = False
        self.assertEqual(self.publish(pid).json()["code"], "CHANNEL_NOT_CONFIGURED")

    def test_daily_limit(self):
        self._live_client()
        with patch.dict(os.environ, {"MW_MARKETING_DAILY_LIMIT": "1"}):
            first = self.approved_post()
            self.assertEqual(self.publish(first).status_code, 200)
            second = self.approved_post(ref_date="2026-11-24")
            self.assertEqual(self.publish(second).json()["code"], "DAILY_LIMIT")

    def test_public_media_is_closed_for_unapproved_and_unknown(self):
        pid = self.make_post()
        self.upload(pid)
        self.assertEqual(self.client.get("/m/nao-existe").status_code, 404)


class AutomationTests(MarketingBase):
    def test_duplicate_active_post_is_refused_but_rejected_one_can_be_redone(self):
        first = self.make_post()
        r = self.client.post(f"{self.API}/posts", headers=self.hdr, json={
            "channel": "instagram", "kind": "end_of_day", "asset": "WDO", "ref_date": "2026-11-25", "caption": GOOD_CAPTION})
        self.assertEqual((r.status_code, r.json()["code"]), (409, "POST_EXISTS"))
        self.assertIn(first, r.json()["detail"])
        self.assertEqual(self.client.post(f"{self.API}/posts/{first}/reject", headers=self.hdr).status_code, 200)
        self.make_post()  # rejeitado libera um novo rascunho do mesmo caso

    def test_bot_account_drafts_and_uploads_but_cannot_approve_publish_or_switch(self):
        with patch.dict(os.environ, {"MW_MARKETING_BOT_EMAILS": "bot@test.local"}):
            bot = self._login("bot@test.local", "admin")
            pid = self.make_post(headers=bot)
            self.assertEqual(self.client.post(f"{self.API}/posts/{pid}/media", headers=dict(bot, **{"Content-Type": "image/png"}),
                                              content=PNG).status_code, 200)
            for path, method in ((f"/posts/{pid}/approve", "post"), (f"/posts/{pid}/reject", "post"),
                                 (f"/posts/{pid}/retry", "post"), (f"/posts/{pid}/publish", "post"),
                                 ("/channels/instagram/check", "get"), ("/switch", "put")):
                kw = {"json": {"confirm": True, "enabled": False}} if method != "get" else {}
                r = getattr(self.client, method)(f"{self.API}{path}", headers=bot, **kw)
                self.assertEqual((path, r.status_code, r.json().get("code")), (path, 403, "BOT_NOT_ALLOWED"))
            # a pessoa continua podendo aprovar o que o robô preparou
            self.assertEqual(self.client.post(f"{self.API}/posts/{pid}/approve", headers=self.hdr).status_code, 200)


class InstagramChannelTests(unittest.TestCase):
    def make(self, responses, **kw):
        calls = []

        def http(method, url, data):
            calls.append((method, url, data))
            return responses.pop(0)

        ch = InstagramChannel("111", "SECRET-TOKEN", http=http, sleep=lambda s: None, **kw)
        return ch, calls

    def test_image_flow_creates_container_waits_and_publishes(self):
        ch, calls = self.make([{"id": "C1"}, {"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}, {"id": "P1"}])
        self.assertEqual(ch.publish(media_url="https://x/y.png", media_type="image", caption="oi"), "P1")
        self.assertIn("image_url", calls[0][2])
        self.assertIn("media_publish", calls[3][1])

    def test_video_uses_reels(self):
        ch, calls = self.make([{"id": "C1"}, {"status_code": "FINISHED"}, {"id": "P1"}])
        ch.publish(media_url="https://x/y.mp4", media_type="video", caption="oi")
        self.assertEqual(calls[0][2]["media_type"], "REELS")

    def test_container_error_and_timeout_do_not_publish(self):
        ch, calls = self.make([{"id": "C1"}, {"status_code": "ERROR"}])
        with self.assertRaises(ChannelError):
            ch.publish(media_url="u", media_type="image", caption="c")
        self.assertFalse(any("media_publish" in c[1] for c in calls))
        ch2, calls2 = self.make([{"id": "C1"}] + [{"status_code": "IN_PROGRESS"}] * 3, max_polls=3)
        with self.assertRaises(ChannelError) as ctx:
            ch2.publish(media_url="u", media_type="image", caption="c")
        self.assertEqual(ctx.exception.code, "CONTAINER_TIMEOUT")
        self.assertFalse(any("media_publish" in c[1] for c in calls2))

    def test_token_never_leaks_in_errors(self):
        def http(method, url, data):
            raise ChannelError("HTTP_400", "bad token SECRET-TOKEN in message")

        ch = InstagramChannel("111", "SECRET-TOKEN", http=http)
        with self.assertRaises(ChannelError) as ctx:
            ch.check_account()
        self.assertNotIn("SECRET-TOKEN", str(ctx.exception))

    def test_unconfigured(self):
        self.assertFalse(InstagramChannel("", "").configured)
        with self.assertRaises(ChannelError):
            InstagramChannel("", "").check_account()


if __name__ == "__main__":
    unittest.main()
