"""Spec 030 T067 — lo que espera a una persona (Requisito 11 y 15.3).

``inbox_lifecycle.mark_waiting`` corre dentro de la transacción de la
herramienta de escalado; ``announce_waiting`` avisa después del commit. Lo que
fija este archivo:

- **con Bandeja**: ``ESCALATED``, el agente callado (``takeover_context.reason
  = "escalated"``), el evento con el motivo y el resumen, el aviso en la
  campana **solo para el cliente** (``audience = 'client'``), el correo a sus
  personas activas —nunca a miembros del partner— y el evento de tiempo real;
  todo una vez por escalado;
- **sin Bandeja**: estado y evento, y el agente sigue respondiendo (nadie la
  atendería);
- quitar la Bandeja o apagar el acceso devuelve al agente las conversaciones
  calladas por un escalado, con evento; las que una persona tomó se respetan.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    ConsoleNotification,
    Conversation,
    ConversationEvent,
    ConversationStatus,
)
from nexus_api.services import inbox_lifecycle
from nexus_api.services.inbox_stream import inbox_channel
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _send(**kw: Any) -> None:
        sent.append(kw)

    monkeypatch.setattr("nexus_api.services.console_notifications.send_email", _send)
    return sent


async def _escalate(scoped_session_factory, tenant_id, conversation_id, **kw: Any):
    session = await scoped_session_factory(tenant_id)
    try:
        conv = await session.get(Conversation, conversation_id)
        mark = await inbox_lifecycle.mark_waiting(
            session,
            conv,
            reason=kw.get("reason", "Pide un reembolso"),
            summary=kw.get("summary", "Cliente habitual, compró el lunes"),
        )
        await session.commit()
    finally:
        await session.close()
    return mark


async def _conv(db_session, conversation_id) -> Conversation:
    db_session.expire_all()
    return (
        await db_session.execute(sa.select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one()


async def _events(db_session, conversation_id) -> list[ConversationEvent]:
    return list(
        (
            await db_session.execute(
                sa.select(ConversationEvent)
                .where(ConversationEvent.conversation_id == conversation_id)
                .order_by(ConversationEvent.created_at)
            )
        ).scalars()
    )


async def _notifications(db_session, partner_id) -> list[ConsoleNotification]:
    return list(
        (
            await db_session.execute(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == partner_id,
                    ConsoleNotification.kind == "inbox.waiting",
                )
            )
        ).scalars()
    )


async def test_with_inbox_the_agent_goes_quiet_and_the_client_is_told(
    db_session, console_world, scoped_session_factory, fake_redis, mails
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(inbox_channel(w["tenant_id"]))

    mark = await _escalate(scoped_session_factory, w["tenant_id"], c0)
    assert mark.inbox is True
    conv = await _conv(db_session, c0)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.agent_active is False
    assert conv.assigned_user_id is None
    assert conv.takeover_context["reason"] == "escalated"
    (event,) = await _events(db_session, c0)
    assert event.kind == "escalated" and event.actor == "agent"
    assert event.payload == {
        "reason": "Pide un reembolso",
        "customer_summary": "Cliente habitual, compró el lunes",
    }
    # Nada se avisa antes del commit del escalado.
    assert await _notifications(db_session, w["partner_id"]) == []
    assert mails == []

    await inbox_lifecycle.announce_waiting(mark, redis=fake_redis)
    (row,) = await _notifications(db_session, w["partner_id"])
    assert row.audience == "client"
    assert row.external_client_ref == w["ref"]
    assert row.payload == {"conversation_id": str(c0), "contact": "Contacto 0"}
    (mail,) = mails
    member_email = (
        await db_session.execute(
            sa.text("SELECT email FROM client_memberships WHERE id = :id"),
            {"id": inbox["member"]["membership_id"]},
        )
    ).scalar_one()
    assert mail["to"] == [member_email]
    assert f"/inbox?c={c0}" in mail["html"]
    assert "Pide un reembolso" not in mail["html"]

    # La primera lectura puede ser la confirmación de la suscripción (None).
    published = None
    for _ in range(3):
        published = published or await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert published is not None
    assert json.loads(published["data"])["event"] == "conversation.updated"

    # Una vez por escalado: repetir el aviso no duplica ni la campana ni el correo.
    await inbox_lifecycle.announce_waiting(mark, redis=fake_redis)
    assert len(await _notifications(db_session, w["partner_id"])) == 1
    assert len(mails) == 1


async def test_without_inbox_the_agent_keeps_answering(
    db_session, console_world, scoped_session_factory, fake_redis, mails
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session,
        partner_id=w["partner_id"],
        tenant_id=w["tenant_id"],
        modules=("panel", "usage"),
    )
    c0 = inbox["conversations"][0]
    mark = await _escalate(scoped_session_factory, w["tenant_id"], c0)
    await inbox_lifecycle.announce_waiting(mark, redis=fake_redis)

    assert mark.inbox is False
    conv = await _conv(db_session, c0)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.agent_active is True
    assert [e.kind for e in await _events(db_session, c0)] == ["escalated"]
    assert await _notifications(db_session, w["partner_id"]) == []
    assert mails == []


async def _operator_headers(db_session, admin_headers) -> dict[str, str]:
    from nexus_api.services import operator_identity

    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": True, "modules": ["panel", "usage"]},
        {"enabled": False, "modules": ["panel", "inbox", "usage"]},
    ],
    ids=["inbox-removed", "access-off"],
)
async def test_removing_the_inbox_gives_the_quiet_ones_back(
    client,
    db_session,
    console_world,
    scoped_session_factory,
    admin_headers,
    mails,
    change: dict[str, Any],
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    quiet, taken = inbox["conversations"]
    await _escalate(scoped_session_factory, w["tenant_id"], quiet)
    await _escalate(scoped_session_factory, w["tenant_id"], taken)
    # Una persona tomó la segunda: esa se respeta.
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == taken)
        .values(assigned_user_id=inbox["member"]["user_id"])
    )
    await db_session.commit()

    headers = await _operator_headers(db_session, admin_headers)
    r = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access", headers=headers, json=change
    )
    assert r.status_code == 200, r.text

    back = await _conv(db_session, quiet)
    assert back.agent_active is True
    released = (await _events(db_session, quiet))[-1]
    assert released.kind == "released"
    assert released.payload == {"why": "inbox_removed"}
    still = await _conv(db_session, taken)
    assert still.agent_active is False
    assert still.assigned_user_id == inbox["member"]["user_id"]
