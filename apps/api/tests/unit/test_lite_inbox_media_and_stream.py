"""Spec 030 — archivos y tiempo real de la Bandeja (Requisitos 7.5 y 8.3).

- ``GET /console/lite/inbox/messages/{id}/media`` sirve los bytes con su tipo
  —ningún enlace de almacenamiento llega al navegador— y un mensaje de otro
  cliente no existe;
- ``GET /console/lite/inbox/stream`` solo reenvía lo que se publica en el canal
  del cliente de la sesión, solo los eventos del contrato, y late cuando no
  pasa nada.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from nexus_api.api.console.lite import inbox_stream as stream_route
from nexus_api.db.models import Message, MessageDirection, MessageStatus
from nexus_api.services.inbox_stream import inbox_channel, publish_inbox_event
from nexus_api.services.media_storage import InMemoryMediaStorage
from tests.conftest import add_client_member, make_client_access, make_inbox

pytestmark = pytest.mark.asyncio

MEDIA = "/console/lite/inbox/messages/{id}/media"
STREAM = "/console/lite/inbox/stream"


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> InMemoryMediaStorage:
    store = InMemoryMediaStorage()
    monkeypatch.setattr("nexus_api.api.console.lite.inbox_media.get_media_storage", lambda: store)
    return store


async def _media_message(
    db_session, inbox: dict[str, Any], tenant_id, key: str | None
) -> uuid.UUID:
    mid = uuid.uuid4()
    db_session.add(
        Message(
            id=mid,
            tenant_id=tenant_id,
            conversation_id=inbox["conversations"][0],
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            content="",
            media_kind="image" if key else None,
            media_s3_key=key,
            media_mime="image/jpeg" if key else None,
            media_filename="foto.jpg" if key else None,
        )
    )
    await db_session.commit()
    return mid


async def test_media_is_streamed_with_its_type(client, db_session, console_world, storage) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    stored = await storage.put_inbound(
        tenant_slug="cliente-a", wamid="wamid.1", content=b"\xff\xd8jpeg", content_type="image/jpeg"
    )
    mid = await _media_message(db_session, inbox, w["tenant_id"], stored.key)

    r = await client.get(MEDIA.format(id=mid), headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.content == b"\xff\xd8jpeg"
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.headers["cache-control"].startswith("private")
    assert 'filename="foto.jpg"' in r.headers["content-disposition"]

    plain = await _media_message(db_session, inbox, w["tenant_id"], None)
    assert (await client.get(MEDIA.format(id=plain), headers=inbox["headers"]())).status_code == 404


async def test_what_a_stranger_declares_is_never_rendered_in_place(
    client, db_session, console_world, storage
) -> None:
    """The type of a received file is whatever the SENDER declared: a contact
    can send a «document» as ``text/html`` or SVG. Only media that cannot run
    code is shown in place; the rest is a download of opaque bytes. A name
    with emoji does not break the header either."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    for mime, name in (("text/html", "factura 😀.html"), ("image/svg+xml", "logo.svg")):
        stored = await storage.put_inbound(
            tenant_slug="cliente-a",
            wamid=f"wamid.{name}",
            content=b"<script>x</script>",
            content_type=mime,
        )
        mid = uuid.uuid4()
        db_session.add(
            Message(
                id=mid,
                tenant_id=w["tenant_id"],
                conversation_id=inbox["conversations"][0],
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="",
                media_kind="document",
                media_s3_key=stored.key,
                media_mime=mime,
                media_filename=name,
            )
        )
        await db_session.commit()
        r = await client.get(MEDIA.format(id=mid), headers=inbox["headers"]())
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in r.headers["content-security-policy"]
        if name.startswith("factura"):
            assert (
                "filename*=UTF-8''factura%20%F0%9F%98%80.html" in r.headers["content-disposition"]
            )


async def test_media_of_another_client_does_not_exist(
    client, db_session, console_world, storage
) -> None:
    a, b = console_world["a"], console_world["b"]
    mine = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    theirs = await make_inbox(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    stored = await storage.put_inbound(
        tenant_slug="cliente-b", wamid="wamid.2", content=b"ajeno", content_type="image/jpeg"
    )
    foreign = await _media_message(db_session, theirs, b["tenant_id"], stored.key)
    r = await client.get(MEDIA.format(id=foreign), headers=mine["headers"]())
    assert r.status_code == 404
    assert b"ajeno" not in r.content


class _Request:
    """Una conexión que se cierra tras ``turns`` vueltas del bucle."""

    def __init__(self, turns: int) -> None:
        self.turns = turns

    async def is_disconnected(self) -> bool:
        self.turns -= 1
        return self.turns < 0


async def test_stream_relays_only_its_clients_channel(
    monkeypatch: pytest.MonkeyPatch, fake_redis
) -> None:
    monkeypatch.setattr(stream_route, "HEARTBEAT_SECONDS", 0.01)
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    conv, foreign = uuid.uuid4(), uuid.uuid4()
    response = await stream_route.stream(
        request=_Request(turns=5),  # type: ignore[arg-type]
        principal=SimpleNamespace(tenant_id=mine),  # type: ignore[arg-type]
        redis=fake_redis,
    )
    events = response.body_iterator.__aiter__()
    assert (await events.__anext__())["event"] == "ready"

    await publish_inbox_event(
        fake_redis, tenant_id=mine, event="message.new", conversation_id=conv, direction="inbound"
    )
    await publish_inbox_event(
        fake_redis, tenant_id=theirs, event="message.new", conversation_id=foreign
    )
    # Algo que no es del contrato no se reenvía aunque llegue al canal.
    await fake_redis.publish(inbox_channel(mine), json.dumps({"event": "body", "text": "hola"}))

    rest = [e async for e in events]
    named = [e for e in rest if e["event"] != "ping"]
    assert [e["event"] for e in named] == ["message.new"]
    data = json.loads(named[0]["data"])
    assert data["conversation_id"] == str(conv)
    assert "text" not in data
    assert str(foreign) not in json.dumps(rest)
    assert any(e["event"] == "ping" for e in rest)


async def test_stream_needs_the_inbox_module(client, db_session, console_world) -> None:
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=("panel",)
    )
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    assert (await client.get(STREAM, headers=member["headers"]())).status_code == 403
    assert (await client.get(STREAM, headers=w["headers"]())).status_code == 403
