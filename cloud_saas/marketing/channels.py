# -*- coding: utf-8 -*-
"""Adaptadores de canal do módulo de marketing. Hoje: Instagram pela API Graph da Meta.

O token nunca é registrado em log nem devolvido: toda mensagem de erro passa por `_scrub`.
O acesso HTTP é injetável (`http`), para testar sem rede.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

HttpFn = Callable[[str, str, Optional[dict]], dict]


class ChannelError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _default_http(method: str, url: str, data: Optional[dict]) -> dict:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            err = json.load(exc).get("error", {})
        except Exception:
            err = {}
        raise ChannelError(
            f"HTTP_{exc.code}",
            f"{err.get('type', 'erro')} {err.get('code', '')}: {err.get('message', 'sem detalhe')}",
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ChannelError("NETWORK", f"falha de rede: {type(exc).__name__}") from None


class InstagramChannel:
    name = "instagram"

    def __init__(
        self,
        user_id: str,
        token: str,
        graph_version: str = "v26.0",
        http: Optional[HttpFn] = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_sec: float = 15.0,
        max_polls: int = 20,
    ) -> None:
        self._uid = (user_id or "").strip()
        self._token = (token or "").strip()
        self._base = f"https://graph.facebook.com/{graph_version}"
        self._http = http or _default_http
        self._sleep = sleep
        self._poll_sec = poll_sec
        self._max_polls = max_polls

    @property
    def configured(self) -> bool:
        return bool(self._uid and self._token)

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _call(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        url = f"{self._base}/{path}"
        payload = dict(data or {}, access_token=self._token)
        try:
            if method == "GET":
                return self._http("GET", url + "?" + urllib.parse.urlencode(payload), None)
            return self._http("POST", url, payload)
        except ChannelError as exc:
            raise ChannelError(exc.code, self._scrub(str(exc))) from None

    def check_account(self) -> dict:
        """Somente leitura: confirma que o token enxerga a conta e devolve o uso da cota de publicação."""
        if not self.configured:
            raise ChannelError("NOT_CONFIGURED", "token ou id da conta ausentes")
        acct = self._call("GET", self._uid, {"fields": "id,username"})
        limit = self._call("GET", f"{self._uid}/content_publishing_limit", {"fields": "quota_usage,config"})
        return {"account": acct, "limit": limit}

    def publish(self, *, media_url: str, media_type: str, caption: str) -> str:
        if not self.configured:
            raise ChannelError("NOT_CONFIGURED", "token ou id da conta ausentes")
        if media_type == "image":
            fields = {"image_url": media_url, "caption": caption}
        elif media_type == "video":
            fields = {"media_type": "REELS", "video_url": media_url, "caption": caption, "share_to_feed": "true"}
        else:
            raise ChannelError("BAD_MEDIA", f"tipo de mídia não suportado: {media_type}")
        container = self._call("POST", f"{self._uid}/media", fields).get("id")
        if not container:
            raise ChannelError("NO_CONTAINER", "a Meta não devolveu o id do container")
        for _ in range(self._max_polls):
            status = self._call("GET", str(container), {"fields": "status_code"}).get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise ChannelError("CONTAINER_" + str(status), f"container falhou: {status}")
            self._sleep(self._poll_sec)
        else:
            raise ChannelError("CONTAINER_TIMEOUT", "container não ficou pronto a tempo; nada foi publicado")
        published = self._call("POST", f"{self._uid}/media_publish", {"creation_id": container}).get("id")
        if not published:
            raise ChannelError("NO_PUBLISH_ID", "a Meta não devolveu o id da publicação")
        return str(published)
