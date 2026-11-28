"""Conta admin pode ficar logada em vários navegadores ao mesmo tempo (painel, testes, celular).
Usuário comum segue com sessão única: um novo login derruba o anterior."""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from cloud_saas.app import create_app
from tests.test_cloud_saas import _make_settings

PW = "StrongPassword!123"


class AdminMultiSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(os.path.join(self._tmp.name, "multi_session.db"))
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.key = {"X-Admin-Key": self.settings.admin_api_key}
        for email, plan in (("boss@mw.com", "admin"), ("core@mw.com", "core")):
            r = self.client.post("/api/v1/admin/users", headers=self.key, json={
                "email": email, "password": PW, "full_name": "Teste", "plan": plan, "status": "active",
                "days": 30, "terms_version": self.settings.terms_version})
            self.assertEqual(r.status_code, 200, r.text)

    def tearDown(self) -> None:
        self.app.state.db.close()
        self._tmp.cleanup()

    def _login(self, email: str, fp: str) -> dict:
        r = self.client.post("/auth/login", json={"email": email, "password": PW, "device_fp": fp})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _me(self, headers: dict) -> int:
        return self.client.get("/auth/me", headers=headers).status_code

    def test_admin_keeps_every_browser_logged_in(self) -> None:
        a = self._login("boss@mw.com", "fp-painel")
        b = self._login("boss@mw.com", "fp-testes")
        c = self._login("boss@mw.com", "fp-celular")
        self.assertEqual([self._me(a), self._me(b), self._me(c)], [200, 200, 200])

    def test_regular_user_still_has_a_single_session(self) -> None:
        a = self._login("core@mw.com", "fp-1")
        b = self._login("core@mw.com", "fp-1")
        self.assertEqual(self._me(a), 401)
        self.assertEqual(self._me(b), 200)

    def test_admin_logout_ends_only_that_session(self) -> None:
        a = self._login("boss@mw.com", "fp-painel")
        b = self._login("boss@mw.com", "fp-testes")
        self.assertEqual(self.client.post("/auth/logout", headers=a).status_code, 200)
        self.assertEqual(self._me(a), 401, "o token que saiu não pode continuar valendo")
        self.assertEqual(self._me(b), 200, "o outro navegador segue logado")

    def test_admin_session_count_is_bounded(self) -> None:
        tokens = [self._login("boss@mw.com", f"fp-{i}") for i in range(12)]
        self.assertEqual(self._me(tokens[0]), 401, "a mais antiga sai quando passa do limite")
        self.assertEqual(self._me(tokens[-1]), 200)
        self.assertEqual(sum(self._me(t) == 200 for t in tokens), 10)

    def test_admin_kick_ends_all_admin_sessions(self) -> None:
        a = self._login("boss@mw.com", "fp-painel")
        b = self._login("boss@mw.com", "fp-testes")
        uid = self.client.get("/auth/me", headers=a).json()["user"]["id"]
        self.assertEqual(self.client.post(f"/api/v1/admin/users/{uid}/kick", headers=self.key).status_code, 200)
        self.assertEqual([self._me(a), self._me(b)], [401, 401])


if __name__ == "__main__":
    unittest.main()
