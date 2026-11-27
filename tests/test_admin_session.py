"""Rotas administrativas aceitam a chave (scripts) ou um login com plano admin (painel). Usuário comum não entra."""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from cloud_saas.app import create_app
from tests.test_cloud_saas import _make_settings

PW = "StrongPassword!123"


class AdminSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(os.path.join(self._tmp.name, "admin_session.db"))
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.key = {"X-Admin-Key": self.settings.admin_api_key}
        self.admin = self._login("boss@mw.com", "admin")
        self.core = self._login("core@mw.com", "core")

    def tearDown(self) -> None:
        self.app.state.db.close()
        self._tmp.cleanup()

    def _login(self, email: str, plan: str) -> dict:
        r = self.client.post("/api/v1/admin/users", headers=self.key, json={
            "email": email, "password": PW, "full_name": "Teste", "plan": plan, "status": "active",
            "days": 30, "terms_version": self.settings.terms_version})
        self.assertEqual(r.status_code, 200, r.text)
        uid = r.json()["user"]["id"]
        tok = self.client.post("/auth/login", json={"email": email, "password": PW, "device_fp": f"fp-{email}"}).json()["access_token"]
        return {"id": uid, "headers": {"Authorization": f"Bearer {tok}"}}

    def test_admin_login_reads_and_acts_like_the_key(self) -> None:
        h = self.admin["headers"]
        self.assertEqual(self.client.get("/api/v1/admin/overview", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/trials", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/invites", headers=h).status_code, 200)
        inv = self.client.post("/api/v1/admin/invites", headers=h, json={"code": "AMIGOS", "label": "teste", "trial_days": 15})
        self.assertEqual(inv.status_code, 200, inv.text)
        cid = self.core["id"]
        self.assertEqual(self.client.post(f"/api/v1/admin/users/{cid}/extend", headers=h, json={"days": 5}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/v1/admin/users/{cid}/kick", headers=h).status_code, 200)
        self.assertEqual(self.client.post(f"/api/v1/admin/users/{cid}/unblock", headers=h).status_code, 200)

    def test_key_still_works(self) -> None:
        self.assertEqual(self.client.get("/api/v1/admin/overview", headers=self.key).status_code, 200)

    def test_regular_user_is_refused_everywhere(self) -> None:
        h = self.core["headers"]
        aid = self.admin["id"]
        calls = [
            self.client.get("/api/v1/admin/overview", headers=h),
            self.client.get("/api/v1/admin/trials", headers=h),
            self.client.get("/api/v1/admin/invites", headers=h),
            self.client.post("/api/v1/admin/invites", headers=h, json={"code": "XX", "label": "", "trial_days": 15}),
            self.client.post(f"/api/v1/admin/users/{aid}/extend", headers=h, json={"days": 5}),
            self.client.post(f"/api/v1/admin/users/{aid}/kick", headers=h),
            self.client.post(f"/api/v1/admin/users/{aid}/unblock", headers=h),
        ]
        for r in calls:
            self.assertEqual(r.status_code, 403, r.text)
            self.assertEqual(r.json()["code"], "PLAN_UPGRADE_REQUIRED")

    def test_anonymous_and_wrong_key_are_refused(self) -> None:
        self.assertEqual(self.client.get("/api/v1/admin/overview").status_code, 401)
        r = self.client.get("/api/v1/admin/overview", headers={"X-Admin-Key": "errada"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], "ADMIN_UNAUTHORIZED")

    def test_creating_users_with_password_stays_key_only(self) -> None:
        body = {"email": "novo@mw.com", "password": PW, "full_name": "N", "plan": "admin", "status": "active", "days": 30}
        r = self.client.post("/api/v1/admin/users", headers=self.admin["headers"], json=body)
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(self.client.get("/api/v1/admin/health", headers=self.admin["headers"]).status_code, 401)

    def test_overview_lists_users_for_the_panel(self) -> None:
        ov = self.client.get("/api/v1/admin/overview", headers=self.admin["headers"]).json()
        emails = {u["email"] for u in ov.get("users", [])}
        self.assertTrue({"boss@mw.com", "core@mw.com"} <= emails, ov.keys())


if __name__ == "__main__":
    unittest.main()
