"""Archivos de la Bandeja — spec 030 (R8.3, R10.3; plan D15, D16).

* ``GET …/messages/{id}/media`` sirve los bytes de un archivo recibido (o
  enviado) **por streaming**: la BFF los pasa al navegador, y ningún enlace
  firmado de S3 llega nunca a él. La RLS decide de quién es el mensaje.
* ``POST …/conversations/{id}/attachments`` sube una imagen o un PDF y lo deja
  como mensaje saliente ``member``: el despachador de salida lo envía por
  enlace firmado como los del agente. Mismas precondiciones que el texto.

Tipos y tamaños: un subconjunto de lo que WhatsApp admite —JPEG y PNG hasta
5 MB, PDF hasta 16 MB—, rechazado antes de subir con el límite dicho.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, UploadFile, status
from fastapi.responses import Response
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models import (
    AuditLog,
    Channel,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.services.inbox_stream import publish_inbox_event
from nexus_api.services.inbox_view import PLAYGROUND_PROVIDER
from nexus_api.services.media_storage.storage import MediaStorageError, get_media_storage

from .deps import LiteScope, lite_scope
from .inbox import SentOut, _can_send, _conversation

router = APIRouter(prefix="/inbox")

MB = 1024 * 1024

#: What a browser may show in place (``inline``): the media WhatsApp itself
#: carries and that cannot run code. The type comes from whoever SENT the file
#: (a contact can send a «document» declared ``text/html`` or SVG); anything
#: outside this list is served as a download of opaque bytes, never rendered
#: on the console's origin — whose CSP would be the only barrier otherwise.
INLINE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
        "audio/amr",
        "video/mp4",
        "video/3gpp",
        "application/pdf",
    }
)


def _disposition(kind: str, filename: str | None) -> str:
    """``inline|attachment; filename="ascii"; filename*=UTF-8''…`` (RFC 6266).
    A name with emoji or CJK would otherwise not even fit in the header
    (latin-1) and the download would fail with a 500."""
    name = (filename or "archivo").replace("\r", " ").replace("\n", " ")
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in name)
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


#: ``mime → (tipo de mensaje, tamaño máximo)``.
ALLOWED: dict[str, tuple[str, int]] = {
    "image/jpeg": ("image", 5 * MB),
    "image/png": ("image", 5 * MB),
    "application/pdf": ("document", 16 * MB),
}


@router.get("/messages/{message_id}/media")
async def read_media(
    message_id: uuid.UUID = Path(...),
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> Response:
    msg = (
        await scope.session.execute(
            sa.select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(Message.id == message_id, Channel.provider != PLAYGROUND_PROVIDER)
        )
    ).scalar_one_or_none()
    if msg is None or not msg.media_s3_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown media")
    try:
        body, content_type = await get_media_storage().get_object(msg.media_s3_key)
    except MediaStorageError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown media") from None
    declared = (msg.media_mime or content_type or "").split(";")[0].strip().lower()
    inline = declared in INLINE_TYPES
    return Response(
        content=body,
        media_type=declared if inline else "application/octet-stream",
        headers={
            "Content-Disposition": _disposition(
                "inline" if inline else "attachment", msg.media_filename
            ),
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=SentOut,
    status_code=status.HTTP_201_CREATED,
    responses={413: {"description": "Too large"}, 415: {"description": "Type not allowed"}},
)
async def send_attachment(
    conversation_id: uuid.UUID = Path(...),
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=1024),
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
) -> SentOut:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    rule = ALLOWED.get(content_type)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "type_not_allowed", "allowed": sorted(ALLOWED)},
        )
    kind, limit = rule
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "too_large", "limit_bytes": limit},
        )
    conv = await _conversation(scope, conversation_id)
    await _can_send(scope, conv)
    stored = await get_media_storage().put_outbound(
        tenant_slug=scope.tenant.slug,
        content=data,
        content_type=content_type,
        filename=file.filename,
    )
    now = datetime.now(UTC)
    msg = Message(
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=(caption or "").strip(),
        tool_calls=[],
        actor_kind="member",
        actor_id=scope.principal.membership.id,
        media_kind=kind,
        media_s3_key=stored.key,
        media_mime=content_type,
        media_size_bytes=len(data),
        media_filename=file.filename,
    )
    scope.session.add(msg)
    conv.last_message_at = now
    scope.session.add(
        AuditLog(
            tenant_id=conv.tenant_id,
            actor=scope.principal.actor,
            action="inbox.attachment_sent",
            target=f"conversation:{conv.id}",
            after_json={"kind": kind, "bytes": len(data)},
        )
    )
    await scope.session.flush()
    await scope.session.refresh(msg)
    await publish_inbox_event(
        redis,
        tenant_id=conv.tenant_id,
        event="message.new",
        conversation_id=conv.id,
        message_id=str(msg.id),
        direction="outbound",
    )
    return SentOut(id=msg.id, at=msg.created_at, delivery="pending")
