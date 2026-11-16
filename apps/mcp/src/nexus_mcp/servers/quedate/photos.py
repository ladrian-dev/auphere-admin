"""Las fotos que la persona del turno mandó en su conversación (spec 061, research D7).

Quédate no deja quitar una foto subida, y su KYC recibe la foto de un documento de
identidad. Por eso nada se sube sin que la persona lo elija: ``recent`` enumera las
imágenes de su última conversación (24 horas, como mucho 20), cada una con un
``photo_id``, y las herramientas de subida reciben esos ids.

El servidor comprueba que cada id está en esa lista, de la conversación de la
persona del turno. El modelo nunca ve URLs ni claves del almacén; los bytes los lee
el servidor del almacén de medios.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Conversation, Message, MessageDirection
from sqlalchemy import select

from nexus_mcp.base import ToolError

WINDOW = timedelta(hours=24)
MAX_PHOTOS = 20


@dataclass(frozen=True)
class Photo:
    photo_id: str
    sent_at: datetime
    key: str = field(repr=False)
    mime: str = "image/jpeg"


class PhotoSource(Protocol):
    async def recent(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Photo]: ...

    async def read(self, photo: Photo) -> tuple[bytes, str]: ...


class _DbPhotos:
    async def recent(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Photo]:
        since = datetime.now(UTC) - WINDOW
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            conv_id = await session.scalar(
                select(Conversation.id)
                .where(Conversation.customer_id == customer_id)
                .order_by(Conversation.last_message_at.desc().nulls_last())
                .limit(1)
            )
            if conv_id is None:
                return []
            rows = (
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conv_id,
                        Message.direction == MessageDirection.INBOUND,
                        Message.media_kind == "image",
                        Message.media_s3_key.is_not(None),
                        Message.created_at >= since,
                    )
                    .order_by(Message.created_at.desc())
                    .limit(MAX_PHOTOS)
                )
            ).all()
            return [
                Photo(
                    photo_id=str(m.id),
                    sent_at=m.created_at,
                    key=str(m.media_s3_key),
                    mime=m.media_mime or "image/jpeg",
                )
                for m in rows
            ]

    async def read(self, photo: Photo) -> tuple[bytes, str]:
        from nexus_api.services.media_storage.storage import get_media_storage

        data, content_type = await get_media_storage().get_object(photo.key)
        return data, content_type or photo.mime


_override: PhotoSource | None = None


def set_test_photos(source: PhotoSource | None) -> None:
    """Sustituye la base de datos y el almacén. Solo pruebas."""
    global _override
    _override = source


def source() -> PhotoSource:
    return _override if _override is not None else _DbPhotos()


async def chosen(
    tenant_id: uuid.UUID, customer_id: uuid.UUID, photo_ids: list[str]
) -> list[tuple[str, bytes, str]]:
    """Los bytes de las fotos elegidas, en el orden elegido. Un id que no está entre
    las fotos de la conversación de la persona se rechaza antes de leer nada."""
    if not photo_ids:
        raise ToolError("Elige al menos una foto de quedate.recent_photos.")
    if len(set(photo_ids)) != len(photo_ids):
        raise ToolError("Hay fotos repetidas en la elección.")
    src = source()
    available = {p.photo_id: p for p in await src.recent(tenant_id, customer_id)}
    unknown = [i for i in photo_ids if i not in available]
    if unknown:
        raise ToolError(
            "Alguna foto elegida no está entre las que la persona mandó en las últimas 24 "
            "horas. Vuelve a pedir la lista con quedate.recent_photos."
        )
    out: list[tuple[str, bytes, str]] = []
    for i, pid in enumerate(photo_ids, start=1):
        data, mime = await src.read(available[pid])
        ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
        out.append((f"foto-{i}.{ext}", data, mime))
    return out


__all__ = ["MAX_PHOTOS", "Photo", "PhotoSource", "chosen", "set_test_photos", "source"]
