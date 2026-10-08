"""Spec 030 — tomar el control, contestar y devolver (Requisitos 9 y 10).

Lo que fija este archivo:

- tomar el control asigna a la persona, calla al agente y saca la conversación
  de «espera a una persona»; con una versión vieja, 412 con el estado real;
- devolver exige ser quien atiende y deja ``takeover_context`` para el agente;
- enviar exige atenderla (409 ``not_assigned_to_you``), la ventana de 24 h
  abierta (``window_closed``) y el número conectado (``channel_disconnected``);
- el mensaje es ``member`` con la membresía como ``actor_id`` y sale
  ``pending`` para el despachador de salida;
- la auditoría dice quién (``client:<correo>``) y nunca qué escribió.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Message,
)
from tests.conftest import add_client_member, make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _conv(db_session, conversation_id: uuid.UUID) -> Conversation:
    db_session.expire_all()
    return (
        await db_session.execute(sa.select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one()


async def _set(db_session, conversation_id: uuid.UUID, **values: Any) -> None:
    await db_session.execute(
        sa.update(Conversation).where(Conversation.id == conversation_id).values(**values)
    )
    await db_session.commit()


async def _take(client, inbox, conversation_id, *, version: int | None = None, headers=None):
    h = (headers or inbox["headers"])()
    if version is not None:
        h["If-Match"] = str(version)
    return await client.post(f"{BASE}/{conversation_id}/takeover", headers=h)


async def _audit(db_session, tenant_id, action: str) -> list[AuditLog]:
    return list(
        (
            await db_session.execute(
                sa.select(AuditLog).where(
                    AuditLog.tenant_id == tenant_id, AuditLog.action == action
                )
            )
        ).scalars()
    )


async def test_taking_over_assigns_and_silences(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    await _set(db_session, c0, status=ConversationStatus.ESCALATED, agent_active=False)
    version = (await _conv(db_session, c0)).agent_active_version

    r = await _take(client, inbox, c0, version=version)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "person"
    assert body["assignee"] == {"kind": "member", "name": "Valeria Ríos", "is_me": True}
    assert body["control_version"] == version + 1

    conv = await _conv(db_session, c0)
    assert conv.agent_active is False
    assert conv.assigned_user_id == inbox["member"]["user_id"]
    assert conv.status == ConversationStatus.OPEN
    events = (
        await db_session.execute(
            sa.select(ConversationEvent.kind, ConversationEvent.actor).where(
                ConversationEvent.conversation_id == c0
            )
        )
    ).all()
    assert ("takeover", f"client:{inbox['member']['user_id']}") in events
    (row,) = await _audit(db_session, w["tenant_id"], "inbox.takeover")
    assert row.actor.startswith("client:") and "@" in row.actor

    # Tomarla otra vez quien ya la tiene no cambia nada.
    again = await _take(client, inbox, c0)
    assert again.json()["control_version"] == version + 1


async def test_a_stale_version_gets_the_real_state(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    version = (await _conv(db_session, c0)).agent_active_version
    r = await _take(client, inbox, c0, version=version + 7)
    assert r.status_code == 412
    detail = r.json()["detail"]
    assert detail["error"] == "version_mismatch"
    assert detail["actual"] == version
    assert detail["conversation"]["state"] == "agent"
    bad = inbox["headers"]()
    bad["If-Match"] = "siete"
    assert (await client.post(f"{BASE}/{c0}/takeover", headers=bad)).status_code == 400


async def test_another_person_can_take_it_over(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    other = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    c0 = inbox["conversations"][0]
    assert (await _take(client, inbox, c0)).status_code == 200
    r = await _take(client, inbox, c0, headers=other["headers"])
    assert r.status_code == 200
    assert r.json()["assignee"]["is_me"] is True
    assert (await _conv(db_session, c0)).assigned_user_id == other["user_id"]


async def test_giving_back_needs_the_person_attending(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    other = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    c0 = inbox["conversations"][0]
    assert (await _take(client, inbox, c0)).status_code == 200

    theirs = await client.post(f"{BASE}/{c0}/release", headers=other["headers"]())
    assert theirs.status_code == 409
    assert theirs.json()["detail"]["code"] == "not_assigned_to_you"

    mine = await client.post(f"{BASE}/{c0}/release", headers=inbox["headers"]())
    assert mine.status_code == 200, mine.text
    assert mine.json()["state"] == "agent"
    conv = await _conv(db_session, c0)
    assert conv.agent_active is True
    assert conv.assigned_user_id is None
    assert conv.takeover_context is not None  # el despachador lo resume y lo limpia
    assert len(await _audit(db_session, w["tenant_id"], "inbox.released")) == 1


async def test_giving_back_a_waiting_conversation(client, db_session, console_world) -> None:
    """Una conversación que espera a una persona y nadie atiende se puede
    devolver al agente sin tomarla antes."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    await _set(db_session, c0, status=ConversationStatus.ESCALATED, agent_active=False)
    r = await client.post(f"{BASE}/{c0}/release", headers=inbox["headers"]())
    assert r.status_code == 200
    assert r.json()["state"] == "agent"


async def test_sending_needs_the_person_the_window_and_the_number(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    send = f"{BASE}/{c0}/messages"

    r = await client.post(send, headers=inbox["headers"](), json={"text": "Hola"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_assigned_to_you"

    assert (await _take(client, inbox, c0)).status_code == 200
    await _set(db_session, c0, last_inbound_at=datetime.now(UTC) - timedelta(hours=25))
    r = await client.post(send, headers=inbox["headers"](), json={"text": "Hola"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "window_closed"

    await _set(db_session, c0, last_inbound_at=datetime.now(UTC))
    await db_session.execute(
        sa.update(Channel)
        .where(Channel.id == inbox["channel_id"])
        .values(status=ChannelStatus.DISCONNECTED)
    )
    await db_session.commit()
    r = await client.post(send, headers=inbox["headers"](), json={"text": "Hola"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "channel_disconnected"

    blank = await client.post(send, headers=inbox["headers"](), json={"text": "   "})
    assert blank.status_code == 422


async def test_a_sent_message_is_the_members_and_the_audit_keeps_no_text(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    assert (await _take(client, inbox, c0)).status_code == 200
    text = "Hola, te escribe Valeria: mañana a las 10 te va bien"

    r = await client.post(f"{BASE}/{c0}/messages", headers=inbox["headers"](), json={"text": text})
    assert r.status_code == 201, r.text
    assert r.json()["delivery"] == "pending"

    msg = (
        await db_session.execute(sa.select(Message).where(Message.id == uuid.UUID(r.json()["id"])))
    ).scalar_one()
    assert msg.actor_kind == "member"
    assert msg.actor_id == inbox["member"]["membership_id"]
    assert msg.content == text
    assert msg.status.value == "pending"
    assert msg.direction.value == "outbound"

    (row,) = await _audit(db_session, w["tenant_id"], "inbox.message_sent")
    assert row.after_json == {"length": len(text)}
    assert "Valeria" not in str(row.after_json)

    thread = (await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"]())).json()
    last = thread["items"][-1]
    assert last["author"] == {"kind": "member", "name": "Valeria Ríos", "is_me": True}
    assert last["delivery"] == "pending"
    assert (await _conv(db_session, c0)).last_message_at is not None
