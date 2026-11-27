# -*- coding: utf-8 -*-
"""Rotas administrativas do módulo de marketing (somente plano admin) e rota pública da mídia.

Regras que o servidor impõe, independentemente do navegador:
- nada é publicado sem aprovação explícita do post e sem `confirm: true` na chamada de publicar;
- por padrão a publicação é simulada (MW_MARKETING_LIVE != "1"): registra o evento e não chama a Meta;
- chave geral liga/desliga e limite de publicações por 24 h por canal;
- legenda precisa do aviso fixo; mídia é validada por tipo, tamanho e assinatura do arquivo.
"""

from __future__ import annotations

import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cloud_saas.marketing.channels import ChannelError, InstagramChannel
from cloud_saas.marketing.store import MarketingStore

DISCLAIMER = "Conteúdo educacional. Sem recomendação de investimento."
CHANNELS = ("instagram",)
KINDS = ("morning", "end_of_day", "other")
CAPTION_MAX = 2200
HASHTAGS_MAX = 30
MEDIA_RULES = {
    "image/png": ("image", "png", 8 * 1024 * 1024),
    "image/jpeg": ("image", "jpg", 8 * 1024 * 1024),
    "video/mp4": ("video", "mp4", 100 * 1024 * 1024),
}
EDITABLE = ("draft", "approved", "rejected", "failed")


class CreatePostBody(BaseModel):
    channel: str = "instagram"
    kind: str = "other"
    asset: str = ""
    ref_date: str = ""
    caption: str = ""


class EditPostBody(BaseModel):
    caption: str


class PublishBody(BaseModel):
    confirm: bool = False


class SwitchBody(BaseModel):
    enabled: bool


def _problem(status: int, code: str, detail: str):
    from cloud_saas.app import ApiRuleError  # import tardio: evita ciclo com app.py

    raise ApiRuleError(status, code, detail)


def _magic_ok(media_type: str, data: bytes) -> bool:
    if media_type == "image/png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if media_type == "image/jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if media_type == "video/mp4":
        return data[4:8] == b"ftyp"
    return False


def _default_runner(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def register_marketing(
    app: FastAPI,
    cfg: Any,
    auth_admin: Callable[..., dict],
    *,
    store: Optional[MarketingStore] = None,
    channel_factory: Optional[Callable[[], dict]] = None,
    runner: Optional[Callable[[Callable[[], None]], None]] = None,
) -> MarketingStore:
    runner = runner or _default_runner  # resolvido na hora do registro (permite trocar o executor nos testes)
    base_dir = os.path.dirname(cfg.db_path) or "."
    store = store or MarketingStore(os.path.join(base_dir, "marketing.db"))
    media_dir = os.environ.get("MW_MARKETING_DIR", os.path.join(base_dir, "marketing-media"))
    os.makedirs(media_dir, exist_ok=True)

    def _channels() -> dict:
        if channel_factory is not None:
            return channel_factory()
        return {
            "instagram": InstagramChannel(
                os.environ.get("MW_META_IG_USER_ID", ""),
                os.environ.get("MW_META_IG_TOKEN", ""),
                os.environ.get("MW_META_GRAPH_VERSION", "v26.0"),
            )
        }

    def _live() -> bool:
        return os.environ.get("MW_MARKETING_LIVE", "0").strip() == "1"

    def _public_base() -> str:
        return os.environ.get("MW_PUBLIC_BASE_URL", "https://api.magicwalls.com.br").rstrip("/")

    def _daily_limit() -> int:
        try:
            return int(os.environ.get("MW_MARKETING_DAILY_LIMIT", "20"))
        except ValueError:
            return 20

    def _view(post: dict) -> dict:
        out = {k: v for k, v in post.items() if k not in ("media_path", "media_token")}
        out["has_media"] = bool(post.get("media_path"))
        out["media_url"] = (
            f"{_public_base()}/m/{post['media_token']}"
            if post.get("media_token") and post["status"] in ("approved", "publishing")
            else ""
        )
        return out

    def _need(post_id: str) -> dict:
        post = store.get_post(post_id)
        if not post:
            _problem(404, "POST_NOT_FOUND", "Post não encontrado.")
        return post  # type: ignore[return-value]

    def _actor(user: dict) -> str:
        return str(user.get("email") or user.get("id") or "admin")

    def _remove_file(path: str) -> None:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _bot_emails() -> set:
        raw = os.environ.get("MW_MARKETING_BOT_EMAILS", "")
        return {e.strip().lower() for e in raw.split(",") if e.strip()}

    def human_admin(user: dict = Depends(auth_admin)) -> dict:
        """Contas de automação (MW_MARKETING_BOT_EMAILS) só criam rascunho e enviam mídia; quem aprova e publica é gente."""
        if str(user.get("email") or "").strip().lower() in _bot_emails():
            _problem(403, "BOT_NOT_ALLOWED", "Conta de automação não pode aprovar, publicar nem mudar chaves.")
        return user

    router = APIRouter(prefix="/api/v1/admin/marketing", tags=["marketing"])

    @router.get("/status")
    def status(_user: dict = Depends(auth_admin)):
        return {
            "ok": True,
            "enabled": store.get_switch("enabled", "1") == "1",
            "live": _live(),
            "daily_limit": _daily_limit(),
            "channels": {name: {"configured": ch.configured} for name, ch in _channels().items()},
            "counts": store.counts_by_status(),
        }

    @router.put("/switch")
    def switch(body: SwitchBody, user: dict = Depends(human_admin)):
        store.set_switch("enabled", "1" if body.enabled else "0")
        store.add_event("-", _actor(user), "switch", {"enabled": body.enabled})
        return {"ok": True, "enabled": body.enabled}

    @router.get("/channels/{channel}/check")
    def check_channel(channel: str, _user: dict = Depends(human_admin)):
        ch = _channels().get(channel)
        if ch is None:
            _problem(404, "CHANNEL_NOT_FOUND", "Canal desconhecido.")
        try:
            return {"ok": True, **ch.check_account()}
        except ChannelError as exc:
            _problem(502, "CHANNEL_ERROR", str(exc))

    @router.get("/posts")
    def list_posts(status: str = "", channel: str = "", limit: int = 100, _user: dict = Depends(auth_admin)):
        return {"ok": True, "posts": [_view(p) for p in store.list_posts(status=status, channel=channel, limit=limit)]}

    @router.post("/posts")
    def create_post(body: CreatePostBody, user: dict = Depends(auth_admin)):
        if body.channel not in CHANNELS:
            _problem(400, "BAD_CHANNEL", "Canal não suportado.")
        if body.kind not in KINDS:
            _problem(400, "BAD_KIND", "Tipo de post inválido.")
        asset, ref_date = body.asset.upper()[:8], body.ref_date[:10]
        if body.kind != "other" and asset and ref_date:
            existing = store.find_active(channel=body.channel, kind=body.kind, asset=asset, ref_date=ref_date)
            if existing:
                _problem(409, "POST_EXISTS", f"Já existe um post ativo para este caso: {existing['id']}")
        post = store.create_post(
            channel=body.channel, kind=body.kind, asset=asset, ref_date=ref_date,
            caption=body.caption, actor=_actor(user),
        )
        return {"ok": True, "post": _view(post)}

    @router.get("/posts/{post_id}")
    def get_post(post_id: str, _user: dict = Depends(auth_admin)):
        return {"ok": True, "post": _view(_need(post_id)), "events": store.list_events(post_id)}

    def _reopen_if_approved(post: dict, actor: str, why: str) -> dict:
        if post["status"] == "approved":
            post = store.update_post(post["id"], status="draft", approved_by="", approved_at="")
            store.add_event(post["id"], actor, "approval_reset", {"why": why})
        return post

    @router.patch("/posts/{post_id}")
    def edit_post(post_id: str, body: EditPostBody, user: dict = Depends(auth_admin)):
        post = _need(post_id)
        if post["status"] not in EDITABLE:
            _problem(409, "NOT_EDITABLE", "Post em publicação ou já publicado não pode ser editado.")
        if body.caption == post["caption"]:
            return {"ok": True, "post": _view(post), "changed": False}
        post = store.update_post(post_id, caption=body.caption)
        store.add_event(post_id, _actor(user), "caption_edited", {"length": len(body.caption)})
        post = _reopen_if_approved(post, _actor(user), "caption_edited")
        return {"ok": True, "post": _view(post), "changed": True}

    @router.post("/posts/{post_id}/media")
    async def upload_media(post_id: str, request: Request, user: dict = Depends(auth_admin)):
        post = _need(post_id)
        if post["status"] not in EDITABLE:
            _problem(409, "NOT_EDITABLE", "Post em publicação ou já publicado não pode receber mídia.")
        ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        rule = MEDIA_RULES.get(ctype)
        if rule is None:
            _problem(415, "BAD_MEDIA_TYPE", "Use image/png, image/jpeg ou video/mp4.")
        media_kind, ext, max_bytes = rule
        data = await request.body()
        if not data:
            _problem(400, "EMPTY_MEDIA", "Arquivo vazio.")
        if len(data) > max_bytes:
            _problem(413, "MEDIA_TOO_LARGE", f"Limite de {max_bytes // (1024 * 1024)} MB para este tipo.")
        if not _magic_ok(ctype, data):
            _problem(400, "BAD_MEDIA_CONTENT", "O conteúdo do arquivo não corresponde ao tipo informado.")
        token = secrets.token_urlsafe(24)
        path = os.path.join(media_dir, f"{token}.{ext}")
        with open(path, "wb") as fh:
            fh.write(data)
        _remove_file(post["media_path"])
        post = store.update_post(post_id, media_path=path, media_type=media_kind, media_token=token)
        store.add_event(post_id, _actor(user), "media_uploaded", {"type": ctype, "bytes": len(data)})
        post = _reopen_if_approved(post, _actor(user), "media_replaced")
        return {"ok": True, "post": _view(post)}

    @router.get("/posts/{post_id}/media")
    def preview_media(post_id: str, _user: dict = Depends(auth_admin)):
        post = _need(post_id)
        if not post["media_path"] or not os.path.exists(post["media_path"]):
            _problem(404, "MEDIA_NOT_FOUND", "O post não tem mídia.")
        ext = post["media_path"].rsplit(".", 1)[-1]
        ctype = {"png": "image/png", "jpg": "image/jpeg", "mp4": "video/mp4"}[ext]
        return FileResponse(post["media_path"], media_type=ctype, headers={"Cache-Control": "no-store"})

    @router.post("/posts/{post_id}/approve")
    def approve(post_id: str, user: dict = Depends(human_admin)):
        post = _need(post_id)
        if post["status"] != "draft":
            _problem(409, "NOT_DRAFT", "Só rascunho pode ser aprovado.")
        caption = post["caption"].strip()
        if not caption:
            _problem(422, "CAPTION_REQUIRED", "A legenda está vazia.")
        if DISCLAIMER.lower() not in caption.lower():
            _problem(422, "DISCLAIMER_REQUIRED", f'A legenda precisa conter: "{DISCLAIMER}"')
        if len(caption) > CAPTION_MAX:
            _problem(422, "CAPTION_TOO_LONG", f"Máximo de {CAPTION_MAX} caracteres.")
        if caption.count("#") > HASHTAGS_MAX:
            _problem(422, "TOO_MANY_HASHTAGS", f"Máximo de {HASHTAGS_MAX} hashtags.")
        if not post["media_path"] or not os.path.exists(post["media_path"]):
            _problem(422, "MEDIA_REQUIRED", "O post não tem mídia.")
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        post = store.update_post(post_id, status="approved", approved_by=_actor(user), approved_at=now)
        store.add_event(post_id, _actor(user), "approved")
        return {"ok": True, "post": _view(post)}

    @router.post("/posts/{post_id}/reject")
    def reject(post_id: str, user: dict = Depends(human_admin)):
        post = _need(post_id)
        if post["status"] not in ("draft", "approved", "failed"):
            _problem(409, "CANNOT_REJECT", "Este post não pode ser rejeitado agora.")
        post = store.update_post(post_id, status="rejected", approved_by="", approved_at="")
        store.add_event(post_id, _actor(user), "rejected")
        return {"ok": True, "post": _view(post)}

    @router.post("/posts/{post_id}/retry")
    def retry(post_id: str, user: dict = Depends(human_admin)):
        post = _need(post_id)
        if post["status"] != "failed":
            _problem(409, "NOT_FAILED", "Só post com falha pode ser reenviado.")
        post = store.update_post(post_id, status="draft", error="")
        store.add_event(post_id, _actor(user), "retry_requested")
        return {"ok": True, "post": _view(post)}

    def _publish_job(post_id: str, actor: str) -> None:
        post = store.get_post(post_id)
        if not post:
            return
        channel = _channels().get(post["channel"])
        try:
            if channel is None:
                raise ChannelError("CHANNEL_NOT_FOUND", "canal desconhecido")
            external = channel.publish(
                media_url=f"{_public_base()}/m/{post['media_token']}",
                media_type=post["media_type"],
                caption=post["caption"],
            )
        except ChannelError as exc:
            store.update_post(post_id, status="failed", error=str(exc)[:400])
            store.add_event(post_id, actor, "publish_failed", {"code": exc.code, "error": str(exc)[:400]})
            return
        except Exception as exc:  # falha inesperada nunca deixa o post preso em "publishing"
            store.update_post(post_id, status="failed", error=f"{type(exc).__name__}")
            store.add_event(post_id, actor, "publish_failed", {"code": "UNEXPECTED", "error": type(exc).__name__})
            return
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        store.update_post(post_id, status="published", external_id=external, published_at=now, error="")
        store.add_event(post_id, actor, "published", {"external_id": external})
        _remove_file(post["media_path"])

    @router.post("/posts/{post_id}/publish")
    def publish(post_id: str, body: PublishBody, user: dict = Depends(human_admin)):
        post = _need(post_id)
        actor = _actor(user)
        if store.get_switch("enabled", "1") != "1":
            _problem(409, "MARKETING_DISABLED", "As publicações estão desligadas pela chave geral.")
        if not body.confirm:
            _problem(400, "CONFIRM_REQUIRED", "Confirme a publicação com confirm=true.")
        if post["status"] != "approved":
            _problem(409, "NOT_APPROVED", "O post precisa estar aprovado.")
        channel = _channels().get(post["channel"])
        if channel is None or not channel.configured:
            _problem(409, "CHANNEL_NOT_CONFIGURED", "O canal não está configurado no servidor.")
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
        if store.count_published_since(post["channel"], since) >= _daily_limit():
            _problem(429, "DAILY_LIMIT", "Limite diário de publicações atingido.")
        if not _live():
            store.add_event(post_id, actor, "dry_run_publish", {"channel": post["channel"]})
            return {"ok": True, "dry_run": True, "post": _view(post)}
        if not store.claim_for_publishing(post_id):
            _problem(409, "ALREADY_PUBLISHING", "Este post já está sendo publicado.")
        store.add_event(post_id, actor, "publish_started")
        runner(lambda: _publish_job(post_id, actor))
        return {"ok": True, "dry_run": False, "post": _view(store.get_post(post_id))}

    app.include_router(router)

    @app.get("/m/{token}", include_in_schema=False)
    def public_media(token: str):
        """Rota pública para a Meta buscar a mídia. Só responde enquanto o post está aprovado ou em publicação."""
        from fastapi import HTTPException

        post = store.get_post_by_token(token)
        if not post or post["status"] not in ("approved", "publishing") or not os.path.exists(post["media_path"]):
            raise HTTPException(status_code=404)
        ctype = {"png": "image/png", "jpg": "image/jpeg", "mp4": "video/mp4"}[post["media_path"].rsplit(".", 1)[-1]]
        return FileResponse(post["media_path"], media_type=ctype, headers={"Cache-Control": "no-store"})

    return store
