"""Spec 030 T049 — una conversación por contacto y número (D11).

``nexus_worker.persistence.messages`` es quien da de alta las conversaciones.
Hasta la spec 030 buscaba solo una fila ``OPEN``: una conversación que
esperaba a una persona (``ESCALATED``) se partía en dos al siguiente mensaje
del contacto, y nadie escribía ``CLOSED``. Lo que fija este archivo:

- el alta toma **la última fila** del contacto en ese número, sea cual sea su
  estado;
- ``ESCALATED`` sigue en la misma fila (sigue esperando);
- ``CLOSED`` se reabre a ``OPEN`` con el agente respondiendo, sin persona, y
  con un evento ``reopened`` del contacto; quien envía (un recordatorio) puede
  decir que no fue el contacto;
- ``last_message_at`` sube con entrantes y salientes y nunca baja.

Vive en la suite de la API porque necesita la base; prueba código del worker.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.persistence.messages import (
    persist_inbound_message,
    persist_outbound_message,
    upsert_conversation_for_customer,
)

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Customer,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _world(db_session, tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    channel = Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
        config={"phone_number_id": "PN"},
        status=ChannelStatus.ACTIVE,
    )
    customer = Customer(id=uuid.uuid4(), tenant_id=tenant_id, identifier="+5491100000001")
    db_session.add_all([channel, customer])
    await db_session.commit()
    return channel.id, customer.id


async def _upsert(tenant_id, channel_id, customer_id, **kw: Any) -> uuid.UUID:
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            conv = await upsert_conversation_for_customer(
                s, channel_id=channel_id, customer_id=customer_id, **kw
            )
            return conv.id


async def _row(db_session, conversation_id) -> Conversation:
    db_session.expire_all()
    return (
        await db_session.execute(sa.select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one()


async def _set(db_session, conversation_id, **values: Any) -> None:
    await db_session.execute(
        sa.update(Conversation).where(Conversation.id == conversation_id).values(**values)
    )
    await db_session.commit()


async def test_waiting_stays_in_the_same_row(db_session, console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    channel_id, customer_id = await _world(db_session, tenant_id)
    first = await _upsert(tenant_id, channel_id, customer_id)
    await _set(db_session, first, status=ConversationStatus.ESCALATED, agent_active=False)

    again = await _upsert(tenant_id, channel_id, customer_id)
    assert again == first
    row = await _row(db_session, first)
    assert row.status == ConversationStatus.ESCALATED
    assert row.agent_active is False


async def test_a_resolved_one_reopens_with_the_agent(db_session, console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    channel_id, customer_id = await _world(db_session, tenant_id)
    first = await _upsert(tenant_id, channel_id, customer_id)
    await _set(
        db_session,
        first,
        status=ConversationStatus.CLOSED,
        closed_at=datetime.now(UTC),
        agent_active=False,
        assigned_user_id="usr_valeria",
    )
    version = (await _row(db_session, first)).agent_active_version

    again = await _upsert(tenant_id, channel_id, customer_id)
    assert again == first
    row = await _row(db_session, first)
    assert row.status == ConversationStatus.OPEN
    assert row.closed_at is None
    assert row.agent_active is True
    assert row.assigned_user_id is None
    assert row.agent_active_version == version + 1
    events = (
        await db_session.execute(
            sa.select(ConversationEvent.kind, ConversationEvent.actor).where(
                ConversationEvent.conversation_id == first
            )
        )
    ).all()
    assert events == [("reopened", "contact")]


async def test_who_reopens_can_be_someone_else(db_session, console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    channel_id, customer_id = await _world(db_session, tenant_id)
    first = await _upsert(tenant_id, channel_id, customer_id)
    await _set(db_session, first, status=ConversationStatus.CLOSED)
    await _upsert(tenant_id, channel_id, customer_id, reopened_by="system")
    (actor,) = (
        await db_session.execute(
            sa.select(ConversationEvent.actor).where(ConversationEvent.conversation_id == first)
        )
    ).scalars()
    assert actor == "system"


async def test_the_latest_row_wins(db_session, console_world) -> None:
    """Filas de antes de D11: si hay varias, se sigue en la más reciente."""
    tenant_id = console_world["a"]["tenant_id"]
    channel_id, customer_id = await _world(db_session, tenant_id)
    old = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        channel_id=channel_id,
        customer_id=customer_id,
        status=ConversationStatus.OPEN,
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    new = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        channel_id=channel_id,
        customer_id=customer_id,
        status=ConversationStatus.ESCALATED,
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add_all([old, new])
    await db_session.commit()
    assert await _upsert(tenant_id, channel_id, customer_id) == new.id


async def test_last_message_at_follows_both_directions(db_session, console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    channel_id, customer_id = await _world(db_session, tenant_id)
    conv_id = await _upsert(tenant_id, channel_id, customer_id)
    assert (await _row(db_session, conv_id)).last_message_at is None

    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            inbound = await persist_inbound_message(s, conversation_id=conv_id, content="hola")
    after_in = (await _row(db_session, conv_id)).last_message_at
    assert after_in == inbound.created_at

    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            outbound = await persist_outbound_message(
                s,
                conversation_id=conv_id,
                content="¿En qué te ayudo?",
                intent=None,
                model=None,
                tool_calls=[],
            )
    after_out = (await _row(db_session, conv_id)).last_message_at
    assert after_out == outbound.created_at
    assert after_out >= after_in

    # Nunca baja: una fila más vieja (un pliegue tardío) no la retrasa.
    await _set(db_session, conv_id, last_message_at=datetime.now(UTC) + timedelta(hours=1))
    future = (await _row(db_session, conv_id)).last_message_at
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            await persist_inbound_message(s, conversation_id=conv_id, content="otra")
    assert (await _row(db_session, conv_id)).last_message_at == future
