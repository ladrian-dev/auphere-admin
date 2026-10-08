"""Spec 030 T073 — resolver, reabrir y marcar como no leída (Requisito 12).

- resolver pone ``CLOSED`` y ``closed_at``, deja de esperar, deja el agente
  listo para cuando el contacto vuelva a escribir, y es idempotente;
- reabrir la devuelve a la lista con el agente respondiendo y sin persona;
- cada acción deja su evento y su auditoría, una sola vez.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, Conversation, ConversationEvent, ConversationStatus
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _conv(db_session, conversation_id: uuid.UUID) -> Conversation:
    db_session.expire_all()
    return (
        await db_session.execute(sa.select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one()


async def _count(db_session, model, *where) -> int:
    return int(
        (
            await db_session.execute(sa.select(sa.func.count()).select_from(model).where(*where))
        ).scalar_one()
    )


async def test_resolving_closes_and_stops_waiting(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c0)
        .values(status=ConversationStatus.ESCALATED, agent_active=False)
    )
    await db_session.commit()

    r = await client.post(f"{BASE}/{c0}/resolve", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "resolved"
    conv = await _conv(db_session, c0)
    assert conv.status == ConversationStatus.CLOSED
    assert conv.closed_at is not None
    assert conv.agent_active is True  # si el contacto vuelve, responde el agente
    assert conv.assigned_user_id is None
    counts = (await client.get("/console/lite/inbox/counts", headers=inbox["headers"]())).json()
    assert counts["waiting"] == 0

    again = await client.post(f"{BASE}/{c0}/resolve", headers=inbox["headers"]())
    assert again.status_code == 200
    assert (
        await _count(
            db_session,
            ConversationEvent,
            ConversationEvent.conversation_id == c0,
            ConversationEvent.kind == "resolved",
        )
        == 1
    )
    assert (
        await _count(
            db_session,
            AuditLog,
            AuditLog.tenant_id == w["tenant_id"],
            AuditLog.action == "inbox.resolved",
        )
        == 1
    )


async def test_reopening_gives_it_to_the_agent(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    assert (
        await client.post(f"{BASE}/{c0}/takeover", headers=inbox["headers"]())
    ).status_code == 200
    assert (
        await client.post(f"{BASE}/{c0}/resolve", headers=inbox["headers"]())
    ).status_code == 200

    r = await client.post(f"{BASE}/{c0}/reopen", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "agent"
    assert r.json()["assignee"] is None
    conv = await _conv(db_session, c0)
    assert conv.status == ConversationStatus.OPEN
    assert conv.closed_at is None
    assert conv.agent_active is True

    assert (await client.post(f"{BASE}/{c0}/reopen", headers=inbox["headers"]())).status_code == 200
    kinds = [
        k
        for (k,) in (
            await db_session.execute(
                sa.select(ConversationEvent.kind)
                .where(ConversationEvent.conversation_id == c0)
                .order_by(ConversationEvent.created_at)
            )
        ).all()
    ]
    assert kinds == ["takeover", "resolved", "reopened"]
    listed = (await client.get(BASE, headers=inbox["headers"]())).json()["items"]
    assert str(c0) in [i["id"] for i in listed]
