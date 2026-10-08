"""Spec 030 T061 y T083 — lo que escribe una persona del cliente sale como lo
del agente.

La Bandeja deja los mensajes de la persona (``actor_kind = "member"``) como
filas salientes ``pending``; el despachador de salida no distingue quién
escribió. Lo que fija este archivo:

- un texto ``member`` sale por ``send_text`` y se mide como mensaje saliente
  (``record_channel_message``), igual que uno del agente;
- un adjunto ``member`` sale por enlace firmado (``send_image`` /
  ``send_document``) y se mide además como unidad de archivo;
- tras guardar el estado se publica ``message.status`` en el canal del
  cliente —sin cuerpo— para que la Bandeja pinte la entrega (T056);
- al devolver la conversación, el resumen para el agente incluye lo que
  escribió la persona desde que tomó el control (T065).

Vive en la suite de la API porque necesita la base; prueba código del worker.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from nexus_channels.base import SendResult, SendStatus
from nexus_worker.runtime.dispatcher import takeover_messages
from nexus_worker.streams import outbound
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Message, MessageDirection, MessageStatus
from nexus_api.services.inbox_stream import inbox_channel
from nexus_api.services.media_storage import InMemoryMediaStorage

from .conftest import FakeWhatsAppAdapter

pytestmark = pytest.mark.asyncio


@dataclass
class _MediaAdapter(FakeWhatsAppAdapter):
    media_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def _media(self, kind: str, kwargs: dict[str, Any]) -> SendResult:
        self.media_calls.append((kind, kwargs))
        return SendResult(
            provider_message_id=f"wamid.m.{len(self.media_calls)}", status=SendStatus.SENT
        )

    async def send_image(self, **kwargs: Any) -> SendResult:
        return await self._media("image", kwargs)

    async def send_document(self, **kwargs: Any) -> SendResult:
        return await self._media("document", kwargs)


async def _seed(info: dict[str, Any], **kw: Any) -> uuid.UUID:
    msg = Message(
        tenant_id=info["tenant_id"],
        conversation_id=info["conversation_id"],
        direction=MessageDirection.OUTBOUND,
        status=kw.pop("status", MessageStatus.PENDING),
        tool_calls=[],
        actor_kind="member",
        actor_id=uuid.uuid4(),
        **kw,
    )
    async with get_sessionmaker()() as s, tenant_scoped_session(s, info["tenant_id"]):
        s.add(msg)
        await s.flush()
        await s.refresh(msg)
        return msg.id


async def _read(info: dict[str, Any], message_id: uuid.UUID) -> Message:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, info["tenant_id"]):
        return (await s.execute(select(Message).where(Message.id == message_id))).scalar_one()


@pytest.fixture
def metered(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    calls: dict[str, list[dict[str, Any]]] = {"message": [], "media": []}

    async def _message(**kw: Any) -> None:
        calls["message"].append(kw)

    async def _media(**kw: Any) -> None:
        calls["media"].append(kw)

    monkeypatch.setattr(outbound, "record_channel_message", _message)
    monkeypatch.setattr(outbound, "record_media_unit", _media)
    return calls


async def test_a_member_text_goes_out_and_is_metered(
    two_tenants_with_channels, fake_adapter, metered, fake_redis
) -> None:
    info = two_tenants_with_channels["a"]
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(inbox_channel(info["tenant_id"]))
    mid = await _seed(info, content="Hola, te escribe Valeria")

    await outbound._drain_tenant(
        get_sessionmaker(), info["tenant_id"], {"meta": fake_adapter}, batch_size=10
    )

    assert (await _read(info, mid)).status is MessageStatus.SENT
    (call,) = fake_adapter.text_calls
    assert call["text"] == "Hola, te escribe Valeria"
    assert call["recipient"] == info["customer_identifier"]
    (measure,) = metered["message"]
    assert measure["conversation_id"] == info["conversation_id"]

    event = None
    for _ in range(3):
        event = event or await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert event is not None
    body = json.loads(event["data"])
    assert body == {
        "event": "message.status",
        "conversation_id": str(info["conversation_id"]),
        "message_id": str(mid),
        "status": "sent",
        "at": body["at"],
    }


async def test_a_member_attachment_goes_out_by_signed_link(
    two_tenants_with_channels, metered, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = two_tenants_with_channels["a"]
    store = InMemoryMediaStorage()
    monkeypatch.setattr(outbound, "get_media_storage", lambda: store)
    stored = await store.put_outbound(
        tenant_slug="f-a",
        content=b"%PDF-1.7",
        content_type="application/pdf",
        filename="carta.pdf",
    )
    mid = await _seed(
        info,
        content="Te mando la carta",
        media_kind="document",
        media_s3_key=stored.key,
        media_mime="application/pdf",
        media_filename="carta.pdf",
    )
    adapter = _MediaAdapter()

    await outbound._drain_tenant(
        get_sessionmaker(), info["tenant_id"], {"meta": adapter}, batch_size=10
    )

    assert (await _read(info, mid)).status is MessageStatus.SENT
    ((kind, kwargs),) = adapter.media_calls
    assert kind == "document"
    assert kwargs["filename"] == "carta.pdf"
    assert kwargs["caption"] == "Te mando la carta"
    assert kwargs["link"] == await store.presign_get(stored.key)
    assert len(metered["message"]) == 1
    assert metered["media"][0]["kind"] == "document"


async def test_the_briefing_counts_what_the_person_wrote(two_tenants_with_channels) -> None:
    info = two_tenants_with_channels["a"]
    started = datetime.now(UTC) - timedelta(minutes=5)
    await _seed(
        info,
        content="antes de tomarla",
        created_at=started - timedelta(minutes=1),
        status=MessageStatus.SENT,
    )
    await _seed(info, content="Te confirmo el lunes a las 10", status=MessageStatus.SENT)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, info["tenant_id"]):
        s.add(
            Message(
                tenant_id=info["tenant_id"],
                conversation_id=info["conversation_id"],
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.SENT,
                content="nota del operador",
                tool_calls=[],
                actor_kind="operator",
            )
        )
        await s.flush()
        texts = await takeover_messages(s, info["conversation_id"], started.isoformat())
    assert texts == ["Te confirmo el lunes a las 10", "nota del operador"]
