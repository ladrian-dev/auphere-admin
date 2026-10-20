"""Spec 031 · R8.2, R8.4, R8.5 — el outbox de avisos (T082).

Un aviso al teléfono nace como una fila de ``client_push_events`` escrita **en
la misma transacción que el hecho**. El worker solo ve lo confirmado, así que un
escalado que se deshace no avisa de nada (R8.5). Lo que fija este archivo:

- el escalado de una conversación de un cliente con Bandeja deja su evento, y
  un rollback no deja ninguno;
- sin Bandeja no hay evento: nadie atendería el aviso;
- la clave de deduplicación hace que un hecho sea un evento;
- el aviso de saldo del cliente (bajo o agotado) deja su evento junto a la fila
  de la campana, y uno deduplicado no deja ninguno;
- ningún evento lleva contenido: solo referencias.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import ClientPushEvent, Conversation
from nexus_api.services import inbox_lifecycle, push_events, wallet_alerts
from tests.conftest import make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _events(db_session, tenant_id: uuid.UUID) -> list[ClientPushEvent]:
    db_session.expire_all()
    return list(
        (
            await db_session.scalars(
                sa.select(ClientPushEvent).where(ClientPushEvent.tenant_id == tenant_id)
            )
        ).all()
    )


async def _escalate(scoped_session_factory, tenant_id, conversation_id, *, commit: bool) -> Any:
    session = await scoped_session_factory(tenant_id)
    try:
        conv = await session.get(Conversation, conversation_id)
        mark = await inbox_lifecycle.mark_waiting(
            session, conv, reason="Pide un reembolso", summary=None
        )
        if commit:
            await session.commit()
        else:
            await session.rollback()
    finally:
        await session.close()
    return mark


async def test_an_escalation_leaves_its_event_in_the_same_transaction(
    db_session, console_world, scoped_session_factory
) -> None:
    w = console_world["a"]
    box = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    conv = box["conversations"][0]

    mark = await _escalate(scoped_session_factory, w["tenant_id"], conv, commit=True)

    (event,) = await _events(db_session, w["tenant_id"])
    assert event.kind == "inbox.waiting"
    assert event.conversation_id == conv
    assert event.dedupe_key == f"inbox.waiting:{mark.event_id}"
    assert event.status == "pending"
    assert event.target_principal_id is None and event.notification_id is None


async def test_a_rolled_back_escalation_leaves_nothing(
    db_session, console_world, scoped_session_factory
) -> None:
    w = console_world["a"]
    box = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])

    await _escalate(scoped_session_factory, w["tenant_id"], box["conversations"][0], commit=False)

    assert await _events(db_session, w["tenant_id"]) == []


async def test_without_inbox_there_is_no_event(
    db_session, console_world, scoped_session_factory
) -> None:
    w = console_world["a"]
    box = await make_inbox(
        db_session,
        partner_id=w["partner_id"],
        tenant_id=w["tenant_id"],
        modules=("panel", "usage"),
    )

    await _escalate(scoped_session_factory, w["tenant_id"], box["conversations"][0], commit=True)

    assert await _events(db_session, w["tenant_id"]) == []


async def test_one_fact_is_one_event(db_session, console_world) -> None:
    w = console_world["a"]
    conv = uuid.uuid4()
    for _ in range(2):
        async with db_session.begin():
            await push_events.enqueue(
                db_session,
                tenant_id=w["tenant_id"],
                kind="inbox.waiting",
                conversation_id=conv,
                dedupe_key="inbox.waiting:mismo-hecho",
            )
    assert len(await _events(db_session, w["tenant_id"])) == 1


async def test_a_balance_notice_leaves_its_event_once(db_session, console_world) -> None:
    w = console_world["a"]
    async with db_session.begin():
        row = await wallet_alerts._emit_client_balance(
            db_session, w["partner_id"], w["tenant_id"], w["ref"], "balance_low", days_left=3.2
        )
        row_id = row.id if row is not None else None
    async with db_session.begin():
        again = await wallet_alerts._emit_client_balance(
            db_session, w["partner_id"], w["tenant_id"], w["ref"], "balance_low", days_left=3.2
        )

    assert row is not None and again is None
    (event,) = await _events(db_session, w["tenant_id"])
    assert event.kind == "client.balance"
    assert event.notification_id == row_id
    assert event.dedupe_key == f"client.balance:{row_id}"


def test_an_event_carries_references_not_content() -> None:
    columns = set(ClientPushEvent.__table__.columns.keys())
    assert columns.isdisjoint({"title", "body", "text", "contact", "reason", "phone", "content"})


async def test_a_message_where_a_person_handles_it_leaves_an_event(
    db_session, console_world, scoped_session_factory
) -> None:
    """R8.3 (T083): lo que llama el despachador del worker en la transacción del
    entrante. Solo si la atiende una persona; con el agente, nada."""
    w = console_world["a"]
    box = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    conv_id = box["conversations"][0]
    me = box["member"]["user_id"]
    inbound = uuid.uuid4()

    session = await scoped_session_factory(w["tenant_id"])
    try:
        conv = await session.get(Conversation, conv_id)
        assert conv is not None
        assert await push_events.enqueue_message_for_you(session, conv, inbound_id=inbound) is False
        conv.agent_active = False
        conv.assigned_user_id = me
        assert await push_events.enqueue_message_for_you(session, conv, inbound_id=inbound) is True
        # La misma burbuja (o un reintento del consumidor): un solo evento.
        await push_events.enqueue_message_for_you(session, conv, inbound_id=inbound)
        await session.commit()
    finally:
        await session.close()

    (event,) = await _events(db_session, w["tenant_id"])
    assert event.kind == "inbox.message_for_you"
    assert event.target_principal_id == me
    assert event.dedupe_key == f"inbox.message:{inbound}"
