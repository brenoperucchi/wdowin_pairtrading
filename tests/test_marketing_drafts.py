# -*- coding: utf-8 -*-
"""Rascunhos automáticos: legenda com avisos, idempotência, conta de automação sem poder de aprovar."""

from __future__ import annotations

import os
import pathlib
import tempfile
from unittest.mock import patch

from scripts import marketing_drafts as md
from tests.test_marketing import GOOD_CAPTION, MarketingBase, PNG

RAW = "Pregão de 25/11 · WDO\n#1 09:35 COMPRA → STOP -3,0 pts\n2 sinais: 1 stop e 1 sem stop.\n⚠️ Conteúdo educacional. Sem recomendação."


class ClientApi(md.Api):
    """Mesmo cliente, mas o transporte é o TestClient do app (sem rede)."""

    def __init__(self, client, email, password):
        super().__init__("http://test", email, password)
        self.client = client

    def _call(self, method, path, body=None, raw=None, ctype="application/json"):
        headers = {"Content-Type": ctype}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        kw = {"content": raw} if raw is not None else ({"json": body} if body is not None else {})
        r = self.client.request(method, path, headers=headers, **kw)
        return r.status_code, r.json()


class CaptionTests(MarketingBase):
    def test_caption_gets_fixed_notices_and_drops_panel_disclaimer(self):
        cap = md.build_caption(RAW, "WDO")
        self.assertIn(md.EXTRA_NOTICE, cap)
        self.assertEqual(cap.count("Conteúdo educacional"), 1)  # o do painel saiu, ficou o nosso
        self.assertTrue(cap.rstrip().endswith("#MagicWalls #WDO #B3"))
        self.assertIn(md.DISCLAIMER, cap)

    def test_caption_without_signal_count_is_refused(self):
        with self.assertRaises(md.DraftError):
            md.build_caption("Pregão sem nada", "WIN")

    def test_generated_caption_passes_server_rules(self):
        pid = self.make_post(caption=md.build_caption(RAW, "WDO"))
        self.assertTrue(pid)


class SendTests(MarketingBase):
    def folder(self, assets=("WIN", "WDO")):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for a in assets:
            d = pathlib.Path(tmp.name) / a
            d.mkdir()
            (d / "card.png").write_bytes(PNG)
            (d / "legenda.txt").write_text(RAW.replace("WDO", a), encoding="utf-8")
        return pathlib.Path(tmp.name)

    def test_bot_creates_drafts_with_media_and_never_approves(self):
        with patch.dict(os.environ, {"MW_MARKETING_BOT_EMAILS": "bot@test.local"}):
            self._login("bot@test.local", "admin")
            api = ClientApi(self.client, "bot@test.local", "StrongPassword!123")
            lines = md.enviar(api, "2026-11-25", self.folder())
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("aguarda aprovação" in l for l in lines), lines)
        posts = self.client.get(f"{self.API}/posts", headers=self.hdr).json()["posts"]
        self.assertEqual({p["asset"] for p in posts}, {"WIN", "WDO"})
        self.assertTrue(all(p["status"] == "draft" and p["has_media"] for p in posts))

    def test_second_run_does_not_duplicate(self):
        with patch.dict(os.environ, {"MW_MARKETING_BOT_EMAILS": "bot@test.local"}):
            self._login("bot@test.local", "admin")
            api = ClientApi(self.client, "bot@test.local", "StrongPassword!123")
            folder = self.folder()
            md.enviar(api, "2026-11-25", folder)
            lines = md.enviar(api, "2026-11-25", folder)
        self.assertTrue(all("já existia" in l for l in lines), lines)
        self.assertEqual(len(self.client.get(f"{self.API}/posts", headers=self.hdr).json()["posts"]), 2)

    def test_missing_asset_is_skipped_and_wrong_password_stops(self):
        with patch.dict(os.environ, {"MW_MARKETING_BOT_EMAILS": "bot@test.local"}):
            self._login("bot@test.local", "admin")
            api = ClientApi(self.client, "bot@test.local", "StrongPassword!123")
            lines = md.enviar(api, "2026-11-25", self.folder(assets=("WIN",)))
            self.assertTrue(lines[0].startswith("WIN: rascunho") and "WDO: sem card" in lines[1], lines)
            with self.assertRaises(md.DraftError):
                md.enviar(ClientApi(self.client, "bot@test.local", "senha-errada"), "2026-11-25", self.folder())

    def test_bad_legend_for_one_asset_does_not_block_the_other(self):
        with patch.dict(os.environ, {"MW_MARKETING_BOT_EMAILS": "bot@test.local"}):
            self._login("bot@test.local", "admin")
            api = ClientApi(self.client, "bot@test.local", "StrongPassword!123")
            folder = self.folder()
            (folder / "WIN" / "legenda.txt").write_text("sem contagem", encoding="utf-8")
            lines = md.enviar(api, "2026-11-25", folder)
        self.assertIn("não traz a contagem", lines[0])
        self.assertIn("rascunho", lines[1])
