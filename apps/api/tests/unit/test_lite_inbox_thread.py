"""Spec 030 — el hilo de una conversación (Requisito 8).

``GET /console/lite/inbox/conversations/{id}`` y ``…/messages``. Lo que fija
este archivo:

- mensajes y eventos van intercalados en el orden en que pasaron, y se
  pagina hacia atrás sin repetir;
- de un archivo llegan su tipo, su nombre y su transcripción —nunca la clave
  de almacenamiento—, y se descarga por su ruta;
- un envío fallido dice que falló y por qué;
- una conversación de otro cliente o del Playground no existe.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Conversation,
    ConversationEvent,
    Message,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _first_message_at(db_session, conversation_id) -> datetime:
    return (
        await db_session.execute(
            sa.select(sa.func.min(Message.created_at)).where(
                Message.conversation_id == conversation_id
            )
        )
    ).scalar_one()


async def test_messages_and_events_interleave_in_order(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    at = await _first_message_at(db_session, c0)
    db_session.add(
        ConversationEvent(
            tenant_id=w["tenant_id"],
            conversation_id=c0,
            kind="escalated",
            actor="agent",
            payload={"reason": "Pide un reembolso", "customer_summary": "Cliente habitual"},
            created_at=at + timedelta(seconds=2),
        )
    )
    await db_session.commit()

    r = await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["type"], i["direction"] or i["kind"]) for i in items] == [
        ("message", "inbound"),
        ("event", "escalated"),
        ("message", "outbound"),
    ]
    assert items[0]["author"]["kind"] == "contact"
    assert items[1]["detail"] == "Pide un reembolso"
    assert items[1]["author"]["kind"] == "agent"
    assert items[2]["author"]["kind"] == "agent"
    assert items[2]["delivery"] == "sent"
    assert r.json()["next_before"] is None

    detail = (await client.get(f"{BASE}/{c0}", headers=inbox["headers"]())).json()
    assert detail["summary"] == "Cliente habitual"
    assert detail["activity"][0]["kind"] == "escalated"


async def test_pages_backwards_without_repeats(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    at = await _first_message_at(db_session, c0)
    for i in range(3):
        db_session.add(
            Message(
                tenant_id=w["tenant_id"],
                conversation_id=c0,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content=f"seguimiento {i}",
                created_at=at + timedelta(seconds=10 + i),
            )
        )
    await db_session.commit()

    seen: list[str] = []
    before: str | None = None
    for _ in range(6):
        params = {"limit": "2", **({"before": before} if before else {})}
        body = (
            await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"](), params=params)
        ).json()
        # Cada página sale en orden y va antes que la anterior.
        seen = [i["id"] for i in body["items"]] + seen
        before = body["next_before"]
        if before is None:
            break
    assert len(seen) == len(set(seen)) == 5
    texts = [
        i["text"]
        for i in (await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"]())).json()[
            "items"
        ]
    ]
    assert texts[-3:] == ["seguimiento 0", "seguimiento 1", "seguimiento 2"]


async def test_files_say_what_they_are_and_never_where_they_live(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    at = await _first_message_at(db_session, c0)
    key = f"tenants/{w['tenant_id']}/inbound/secreto-s3.jpg"
    db_session.add_all(
        [
            Message(
                tenant_id=w["tenant_id"],
                conversation_id=c0,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="",
                media_kind="image",
                media_s3_key=key,
                media_mime="image/jpeg",
                media_filename="foto.jpg",
                created_at=at + timedelta(seconds=20),
            ),
            Message(
                tenant_id=w["tenant_id"],
                conversation_id=c0,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="",
                media_kind="audio",
                media_s3_key=key.replace(".jpg", ".ogg"),
                media_mime="audio/ogg",
                media_transcript="Quería saber si abren el sábado",
                created_at=at + timedelta(seconds=21),
            ),
        ]
    )
    await db_session.commit()

    r = await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"]())
    assert "secreto-s3" not in r.text
    assert "s3" not in r.text.lower()
    image, audio = r.json()["items"][-2:]
    assert image["media"] == {"kind": "image", "filename": "foto.jpg", "transcript": None}
    assert audio["media"]["transcript"] == "Quería saber si abren el sábado"


async def test_a_failed_send_says_why(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    await db_session.execute(
        sa.update(Message)
        .where(Message.conversation_id == c0, Message.direction == MessageDirection.OUTBOUND)
        .values(status=MessageStatus.FAILED, last_error="Fuera de la ventana de 24 h")
    )
    await db_session.commit()
    items = (await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"]())).json()["items"]
    out = next(i for i in items if i["direction"] == "outbound")
    assert out["delivery"] == "failed"
    assert out["failure_reason"] == "Fuera de la ventana de 24 h"
    inbound = next(i for i in items if i["direction"] == "inbound")
    assert inbound["delivery"] is None


async def test_detail_tells_the_window_and_the_channel(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = inbox["conversations"]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c1)
        .values(last_inbound_at=datetime.now(UTC) - timedelta(hours=25))
    )
    await db_session.commit()

    open_ = (await client.get(f"{BASE}/{c0}", headers=inbox["headers"]())).json()
    assert open_["window"]["open"] is True
    assert open_["channel"] == {"kind": "whatsapp", "connected": True}
    assert open_["state"] == "agent"
    assert open_["summary"] is None
    assert open_["waiting_reason"] is None
    assert open_["contact"]["conversations"] == 1
    closed = (await client.get(f"{BASE}/{c1}", headers=inbox["headers"]())).json()
    assert closed["window"]["open"] is False


async def test_another_clients_or_playground_conversation_does_not_exist(
    client, db_session, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    mine = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    theirs = await make_inbox(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    foreign = theirs["conversations"][0]
    for path in (f"{BASE}/{foreign}", f"{BASE}/{foreign}/messages"):
        assert (await client.get(path, headers=mine["headers"]())).status_code == 404
    assert (
        await client.post(f"{BASE}/{foreign}/read", headers=mine["headers"]())
    ).status_code == 404
    pg = mine["playground_conversation"]
    assert (await client.get(f"{BASE}/{pg}", headers=mine["headers"]())).status_code == 404
