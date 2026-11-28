#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rascunhos automáticos de Instagram para a fila de Marketing.

Duas metades, de propósito separadas:
  coletar  navegador sem janela abre o app, escolhe a data e baixa o card e a legenda do botão "Card IG"
           (o código real do front: uma só fonte dos números, sem recalcular nada em Python);
  enviar   cria o rascunho na API de Marketing e anexa o card. Nunca aprova nem publica.

Conta de automação: o e-mail precisa estar em MW_MARKETING_BOT_EMAILS no servidor, o que a impede de
aprovar, publicar ou mexer na chave geral. Quem aprova é uma pessoa, na tela de Marketing.

Uso:
  marketing_drafts.py run     --date AAAA-MM-DD [--app-url URL] [--api-url URL]
  marketing_drafts.py coletar --date AAAA-MM-DD --out DIR
  marketing_drafts.py enviar  --date AAAA-MM-DD --out DIR
Credenciais: MW_BOT_EMAIL e MW_BOT_PASSWORD (ambiente; nunca na linha de comando).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional

ASSETS = ("WIN", "WDO")
DISCLAIMER = "Conteúdo educacional. Sem recomendação de investimento."
EXTRA_NOTICE = (
    "Este resumo mostra as entradas sinalizadas pelas Walls, não o resultado de uma conta ou de um robô. "
    "Os pontos positivos são o MÁXIMO que o preço andou a favor depois do sinal. "
    "Os stops aparecem com o valor que de fato saiu. Mostramos o dia inteiro."
)
PAST_NOTICE = "Resultado passado não garante resultado futuro."


class DraftError(Exception):
    """Falha que deve parar o rascunho daquele ativo (a mensagem vai para o log)."""


def build_caption(raw_legend: str, asset: str) -> str:
    """Legenda do botão Card IG + avisos fixos. Recusa legenda sem contagem de sinais."""
    text = (raw_legend or "").strip().replace("pagaram", "andaram a favor, ao menos,")
    text = re.sub(r"\n⚠️ Conteúdo educacional[^\n]*$", "", text).rstrip()
    if not re.search(r"\d+\s+sinais?", text, re.I):
        raise DraftError(f"{asset}: a legenda não traz a contagem de sinais; não gerei o rascunho.")
    return f"{text}\n\n{EXTRA_NOTICE}\n\n{DISCLAIMER} {PAST_NOTICE}\n#MagicWalls #{asset} #B3"


class Api:
    """Cliente mínimo (stdlib) da API de Marketing."""

    def __init__(self, base_url: str, email: str, password: str):
        self.base = base_url.rstrip("/")
        self.email, self._password = email, password
        self.token: Optional[str] = None

    def _call(self, method: str, path: str, body=None, raw: Optional[bytes] = None, ctype: str = "application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"Content-Type": ctype, "X-Device-FP": "mw-marketing-bot"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.load(exc)
            except Exception:  # noqa: BLE001
                return exc.code, {"detail": f"HTTP {exc.code}"}

    def login(self) -> str:
        status, body = self._call("POST", "/auth/login", {"email": self.email, "password": self._password})
        if status != 200 or "access_token" not in body:
            raise DraftError(f"login recusado ({status}): {body.get('code') or body.get('detail')}")
        self.token = body["access_token"]
        return self.token

    def create_draft(self, asset: str, ref_date: str, caption: str) -> Dict:
        status, body = self._call("POST", "/api/v1/admin/marketing/posts", {
            "channel": "instagram", "kind": "end_of_day", "asset": asset, "ref_date": ref_date, "caption": caption})
        if status == 409 and body.get("code") == "POST_EXISTS":
            return {"skipped": True, "detail": body.get("detail", "")}
        if status != 200:
            raise DraftError(f"{asset}: criar rascunho falhou ({status}): {body.get('code') or body.get('detail')}")
        return body["post"]

    def upload_media(self, post_id: str, png: bytes) -> None:
        status, body = self._call("POST", f"/api/v1/admin/marketing/posts/{post_id}/media", raw=png, ctype="image/png")
        if status != 200:
            raise DraftError(f"envio do card falhou ({status}): {body.get('code') or body.get('detail')}")


def enviar(api: Api, ref_date: str, folder: pathlib.Path) -> List[str]:
    """Cria um rascunho por ativo a partir de folder/<ATIVO>/{card.png, legenda.txt}. Devolve linhas de relato."""
    api.login()
    report: List[str] = []
    for asset in ASSETS:
        base = folder / asset
        card, legend = base / "card.png", base / "legenda.txt"
        if not card.exists() or not legend.exists():
            report.append(f"{asset}: sem card/legenda em {base}, pulei")
            continue
        try:
            caption = build_caption(legend.read_text(encoding="utf-8"), asset)
            post = api.create_draft(asset, ref_date, caption)
            if post.get("skipped"):
                report.append(f"{asset}: já existia ({post['detail']}), não dupliquei")
                continue
            api.upload_media(post["id"], card.read_bytes())
            report.append(f"{asset}: rascunho {post['id']} criado com card; aguarda aprovação")
        except DraftError as exc:
            report.append(str(exc))
    return report


def coletar(app_url: str, api: Api, ref_date: str, folder: pathlib.Path, fmt: str = "Feed") -> List[str]:
    """Baixa card e legenda pelo botão Card IG (Playwright). Só lê o app; não escreve nada nele."""
    from playwright.sync_api import sync_playwright  # importação tardia: só esta metade precisa dele

    api.login()
    auth = json.dumps({"access_token": api.token, "user": {"plan": "admin", "email": api.email}})
    y, m, d = ref_date.split("-")
    label = f"{d}/{m}/{y}"
    report: List[str] = []
    exe = os.environ.get("MW_CHROMIUM", "/usr/bin/chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1500, "height": 950}, accept_downloads=True)
        ctx.add_init_script(f"window.localStorage.setItem('mw_saas_auth_v1', {json.dumps(auth)})")
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=app_url.rstrip("/"))
        page = ctx.new_page()
        page.goto(app_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)
        select, target = None, None
        for idx in range(page.locator("select").count()):
            candidate = page.locator("select").nth(idx)
            options = candidate.locator("option").evaluate_all("o => o.map(x => [x.value, x.textContent])")
            target = next((v for v, t in options if v == ref_date or label in t), None)
            if target:
                select = candidate
                break
        if select is None:
            browser.close()
            raise DraftError(f"a data {ref_date} não existe em nenhum seletor do app (dia sem pregão?)")
        select.select_option(target)
        page.wait_for_timeout(15000)
        buttons = page.get_by_text("Card IG")
        if buttons.count() < len(ASSETS):
            browser.close()
            raise DraftError(f"o botão Card IG não apareceu para {ref_date} (sem sinais ou feed fora do ar)")
        for i, asset in enumerate(ASSETS):
            buttons.nth(i).click()
            page.wait_for_timeout(1500)
            title = page.locator("text=Gerador de Card Instagram").first.inner_text()
            if asset not in title:
                browser.close()
                raise DraftError(f"modal inesperado: {title}")
            page.get_by_role("button", name=re.compile(fmt, re.I)).first.click()
            page.wait_for_timeout(800)
            out = folder / asset
            out.mkdir(parents=True, exist_ok=True)
            with page.expect_download(timeout=60000) as dl:
                page.get_by_role("button", name=re.compile("Baixar", re.I)).click()
            dl.value.save_as(str(out / "card.png"))
            page.get_by_role("button", name=re.compile("Copiar Legenda", re.I)).click()
            page.wait_for_timeout(800)
            (out / "legenda.txt").write_text(page.evaluate("navigator.clipboard.readText()"), encoding="utf-8")
            report.append(f"{asset}: card e legenda baixados em {out}")
            page.get_by_role("button", name=re.compile("Fechar", re.I)).first.click()
            page.wait_for_timeout(800)
        browser.close()
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("run", "coletar", "enviar"))
    ap.add_argument("--date", required=True, help="AAAA-MM-DD")
    ap.add_argument("--out", help="pasta de trabalho (padrão: ~/marketing-drafts/<data>)")
    ap.add_argument("--app-url", default=os.environ.get("MW_APP_URL", "https://www.magicwalls.com.br"))
    ap.add_argument("--api-url", default=os.environ.get("MW_API_URL", "https://api.magicwalls.com.br"))
    args = ap.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        ap.error("--date precisa ser AAAA-MM-DD")
    email, password = os.environ.get("MW_BOT_EMAIL", ""), os.environ.get("MW_BOT_PASSWORD", "")
    if not email or not password:
        print("faltam MW_BOT_EMAIL e MW_BOT_PASSWORD no ambiente", file=sys.stderr)
        return 2
    folder = pathlib.Path(args.out or pathlib.Path.home() / "marketing-drafts" / args.date)
    api = Api(args.api_url, email, password)
    lines: List[str] = []
    try:
        if args.action in ("run", "coletar"):
            lines += coletar(args.app_url, api, args.date, folder)
        if args.action in ("run", "enviar"):
            lines += enviar(api, args.date, folder)
    except DraftError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
