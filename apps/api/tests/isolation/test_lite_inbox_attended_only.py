"""Spec 045 R1 y R2 — la Bandeja solo enseña lo que el agente atiende o atendió.

Garantía 1 (RLS) un nivel más estrecha: dentro del propio cliente, lo que el
agente no atendió —un número que la puerta de números permitidos silenció, un
envío del sistema que nadie contestó— **no existe** para la Bandeja. Barre:

- la lista con cada filtro y con la búsqueda (por nombre, teléfono y texto);
- los contadores de la página y ``/counts``;
- cada ruta de la Bandeja con id: 404 idéntico al de un id inventado;
- el hilo y la vista previa de una conversación visible: sin el mensaje
  silenciado que llegó después, y sin marcarla como no leída.

El test enumera las rutas montadas: una ruta nueva con ``{conversation_id}``
entra sola en el barrido.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import make_inbox
from tests.isolation.test_console_scope import _console_routes
from tests.isolation.test_lite_client_vs_client import _INBOX_WRITES

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

SILENCED_NAME = "Número Silenciado"
SILENCED_TEXT = "mensaje-de-un-numero-no-permitido"
SYSTEM_NAME = "Solo Recordatorio"
LATE_TEXT = "silenciado-despues"


async def _world(db_session: Any, console_world: dict[str, Any]) -> dict[str, Any]:
    w = console_world["a"]
    tid = w["tenant_id"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=tid)
    now = datetime.now(UTC)

    async def hidden(
        name: str, direction: MessageDirection, text: str, skipped: str | None
    ) -> uuid.UUID:
        cust = Customer(
            id=uuid.uuid4(),
            tenant_id=tid,
            identifier=f"+56988{uuid.uuid4().int % 10**6:06d}",
            name=name,
        )
        db_session.add(cust)
        await db_session.flush()
        conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=tid,
            channel_id=inbox["channel_id"],
            customer_id=cust.id,
            status=ConversationStatus.ESCALATED if skipped else ConversationStatus.OPEN,
            last_inbound_at=now if direction == MessageDirection.INBOUND else None,
            last_message_at=now,
        )
        db_session.add(conv)
        await db_session.flush()
        db_session.add(
            Message(
                tenant_id=tid,
                conversation_id=conv.id,
                direction=direction,
                status=MessageStatus.DELIVERED,
                content=text,
                skipped_reason=skipped,
                created_at=now,
            )
        )
        await db_session.flush()
        return conv.id

    silenced = await hidden(SILENCED_NAME, MessageDirection.INBOUND, SILENCED_TEXT, "not_admin")
    system_only = await hidden(SYSTEM_NAME, MessageDirection.OUTBOUND, "Te recordamos…", None)

    # Una conversación visible recibe después un mensaje silenciado: el
    # despachador mueve la ventana de WhatsApp y el orden, nada más.
    c0 = inbox["conversations"][0]
    db_session.add(
        Message(
            tenant_id=tid,
            conversation_id=c0,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            content=LATE_TEXT,
            skipped_reason="not_admin",
            created_at=now,
        )
    )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c0)
        .values(last_inbound_at=now, last_message_at=now)
    )
    await db_session.commit()
    return {
        **inbox,
        "hidden": [silenced, system_only],
        "c0": c0,
        "since": now - timedelta(hours=1),
    }


LIST = "/console/lite/inbox/conversations"


@pytest.mark.parametrize("flt", ["all", "unread", "waiting", "resolved"])
async def test_the_list_never_shows_what_the_agent_did_not_attend(
    flt: str, client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    resp = await client.get(LIST, params={"filter": flt}, headers=world["headers"]())
    assert resp.status_code == 200, resp.text
    ids = {i["id"] for i in resp.json()["items"]}
    assert not ids & {str(h) for h in world["hidden"]}
    assert SILENCED_NAME not in resp.text and SYSTEM_NAME not in resp.text


@pytest.mark.parametrize("q", [SILENCED_NAME, SILENCED_TEXT, LATE_TEXT, "+56988"])
async def test_search_never_finds_it(q: str, client, db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    resp = await client.get(LIST, params={"q": q}, headers=world["headers"]())
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_counters_count_only_what_the_list_shows(client, db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    page = (await client.get(LIST, headers=world["headers"]())).json()
    counts = (await client.get("/console/lite/inbox/counts", headers=world["headers"]())).json()
    # Las dos de la fixture, sin leer; la silenciada escalada no cuenta en «esperan».
    assert page["counts"] == counts == {"unread": 2, "waiting": 0}


async def test_a_late_silenced_message_is_not_shown_nor_unread(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    c0, headers = world["c0"], world["headers"]
    assert (await client.post(f"{LIST}/{c0}/read", headers=headers())).status_code == 204

    page = (await client.get(LIST, headers=headers())).json()
    row = next(i for i in page["items"] if i["id"] == str(c0))
    assert row["unread"] is False
    assert LATE_TEXT not in (row["last_message"] or {}).get("preview", "")

    thread = await client.get(f"{LIST}/{c0}/messages", headers=headers())
    assert thread.status_code == 200
    assert LATE_TEXT not in thread.text


def _conversation_routes() -> list[tuple[str, str]]:
    return sorted(
        (sorted(r.methods)[0], r.path)
        for r in _console_routes()
        if r.path.startswith("/console/lite/inbox/conversations/{conversation_id}")
        # Multipart: el 404 lo fija test_lite_inbox_replies_and_attachments.
        and not r.path.endswith("/attachments")
    )


_BODIES = {(m, p): b for m, p, b in _INBOX_WRITES}


@pytest.mark.parametrize(("method", "path"), _conversation_routes())
async def test_every_route_with_its_id_is_the_same_404(
    method: str, path: str, client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    body = _BODIES.get((method, path))
    for hidden in world["hidden"]:
        real = await client.request(
            method,
            path.replace("{conversation_id}", str(hidden)),
            headers=world["headers"](),
            json=body,
        )
        ghost = await client.request(
            method,
            path.replace("{conversation_id}", str(uuid.uuid4())),
            headers=world["headers"](),
            json=body,
        )
        assert real.status_code == ghost.status_code == 404, (path, real.status_code, real.text)
        assert real.content == ghost.content


async def test_media_of_what_the_inbox_does_not_show_is_the_same_404(
    client, db_session, console_world, monkeypatch
) -> None:
    """/cso CSO-002: la ruta del adjunto va por id de mensaje, no de
    conversación, y el id llega por el stream. Lo que la Bandeja no enseña (un
    número silenciado, un envío que nadie contestó, un mensaje silenciado en
    una conversación visible) no se descarga: el mismo 404 que un id inventado."""
    from nexus_api.services.media_storage import InMemoryMediaStorage

    store = InMemoryMediaStorage()
    monkeypatch.setattr("nexus_api.api.console.lite.inbox_media.get_media_storage", lambda: store)
    world = await _world(db_session, console_world)
    tid = console_world["a"]["tenant_id"]
    stored = await store.put_inbound(
        tenant_slug="cliente-a", wamid="wamid.x", content=b"\xff\xd8jpeg", content_type="image/jpeg"
    )

    async def with_media(conversation_id: uuid.UUID, skipped: str | None) -> uuid.UUID:
        mid = uuid.uuid4()
        db_session.add(
            Message(
                id=mid,
                tenant_id=tid,
                conversation_id=conversation_id,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="",
                media_kind="image",
                media_s3_key=stored.key,
                media_mime="image/jpeg",
                media_filename="foto.jpg",
                skipped_reason=skipped,
            )
        )
        await db_session.commit()
        return mid

    silenced_number = await with_media(world["hidden"][0], "not_admin")
    never_attended = await with_media(world["hidden"][1], None)
    late_silenced = await with_media(world["c0"], "not_admin")
    shown = await with_media(world["c0"], None)

    url = "/console/lite/inbox/messages/{}/media"
    headers = world["headers"]
    assert (await client.get(url.format(shown), headers=headers())).status_code == 200
    ghost = await client.get(url.format(uuid.uuid4()), headers=headers())
    for mid in (silenced_number, never_attended, late_silenced):
        r = await client.get(url.format(mid), headers=headers())
        assert r.status_code == ghost.status_code == 404, (mid, r.status_code)
        assert r.content == ghost.content
