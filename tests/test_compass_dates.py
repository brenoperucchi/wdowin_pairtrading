"""Consulta de dias anteriores: as datas guardadas aparecem mesmo sem snapshot ao vivo (produtor parado)."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from cloud_saas.app import create_app
from tests.test_cloud_saas import _make_settings, _signed_push_request

PW = "StrongPassword!123"


def _days_ago(n: int) -> str:
    return (datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(days=n)).strftime("%Y-%m-%d")


class CompassDatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(os.path.join(self._tmp.name, "dates.db"))
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        key = {"X-Admin-Key": self.settings.admin_api_key}
        self.tokens = {}
        for plan in ("core", "pro"):
            email = f"{plan}@mw.com"
            r = self.client.post("/api/v1/admin/users", headers=key, json={
                "email": email, "password": PW, "full_name": "T", "plan": plan, "status": "active",
                "days": 30, "terms_version": self.settings.terms_version})
            self.assertEqual(r.status_code, 200, r.text)
            tok = self.client.post("/auth/login", json={"email": email, "password": PW, "device_fp": f"fp-{plan}"}).json()["access_token"]
            self.tokens[plan] = {"Authorization": f"Bearer {tok}"}

    def tearDown(self) -> None:
        self.app.state.db.close()
        self._tmp.cleanup()

    def _push_days(self, days: list[str], live: bool = False) -> None:
        core = {f"etapa1_day_{d}": {"ok": True, "tier": "core", "selected_date": d} for d in days}
        pro = {f"etapa1_day_{d}": {"ok": True, "tier": "pro", "selected_date": d} for d in days}
        if live:
            core["etapa1_lite"] = {"ok": True, "selected_date": days[0], "available_dates": days}
            pro["etapa1_lite"] = {"ok": True, "selected_date": days[0], "available_dates": days}
        r = _signed_push_request(self.client, self.settings.push_hmac_secret, {
            "producer_id": "vps-01", "producer_role": "primary", "snapshots": {"core": core, "pro": pro}})
        self.assertEqual(r.status_code, 200, r.text)

    def test_dates_listed_without_live_snapshot_newest_first(self) -> None:
        d1, d3, d5 = _days_ago(1), _days_ago(3), _days_ago(5)
        self._push_days([d5, d1, d3])
        # sem snapshot ao vivo, a rota principal segue indisponível...
        self.assertEqual(self.client.get("/api/compass/etapa1", headers=self.tokens["core"]).status_code, 503)
        # ...mas as datas guardadas continuam consultáveis
        r = self.client.get("/api/compass/dates", headers=self.tokens["core"])
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["dates"], [d1, d3, d5])
        self.assertFalse(body["live"])
        # e cada data listada abre o pregão correspondente
        day = self.client.get(f"/api/compass/etapa1?date_str={d3}&lite=1", headers=self.tokens["core"])
        self.assertEqual(day.status_code, 200)
        self.assertEqual(day.json()["selected_date"], d3)

    def test_dates_empty_when_nothing_stored(self) -> None:
        r = self.client.get("/api/compass/dates", headers=self.tokens["core"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["dates"], [])

    def test_dates_respect_tier_and_require_login(self) -> None:
        self._push_days([_days_ago(2)], live=True)
        self.assertEqual(self.client.get("/api/compass/dates").status_code, 401)
        self.assertTrue(self.client.get("/api/compass/dates", headers=self.tokens["pro"]).json()["live"])

    def test_old_day_snapshots_outlive_the_live_snapshot_ttl(self) -> None:
        self.assertGreater(self.settings.day_snapshot_ttl_sec, self.settings.snapshot_ttl_sec)


if __name__ == "__main__":
    unittest.main()
