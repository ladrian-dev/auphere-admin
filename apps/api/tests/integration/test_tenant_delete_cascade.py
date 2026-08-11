"""Borrar de verdad — la cadena de CASCADE que sostiene el claim de GDPR.

``DELETE /admin/tenants/{id}`` no borra fila a fila: se apoya en el CASCADE
de la base. La cadena es

    tenants ──CASCADE──> conversations ──CASCADE──> messages

y el eslabón de la derecha estuvo ROTO entre 0063 y 0070: la tabla
particionada se creó con ``LIKE`` sin ``INCLUDING CONSTRAINTS``, así que
perdió su clave foránea sin que nada fallara. Borrar un tenant eliminaba
sus conversaciones y dejaba sus mensajes para siempre — que es justo lo
contrario de lo que promete el DPA.

Se prueba la cadena entera, no la constraint: un test que solo mirase
``pg_constraint`` seguiría verde si alguien cambiase el CASCADE por un
RESTRICT o un SET NULL.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
)

pytestmark = pytest.mark.asyncio


async def _seed_tenant_with_messages(session, tenant_id: uuid.UUID, *, messages: int) -> None:
    # ``tenants`` es la única tabla sin tenant_id (ES el tenant), así que
    # su alta va fuera del scoping.
    session.add(
        Tenant(
            id=tenant_id,
            name="Borrable",
            slug=f"borrable-{tenant_id.hex[:8]}",
            plan=TenantPlan.ESSENTIAL,
        )
    )
    await session.commit()

    async with tenant_scoped_session(session, tenant_id):
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+569{uuid.uuid4().hex[:8]}",
            status=ChannelStatus.ACTIVE,
            config={},
        )
        session.add(channel)
        await session.flush()
        customer = Customer(tenant_id=tenant_id, identifier=f"569{uuid.uuid4().hex[:8]}")
        session.add(customer)
        await session.flush()
        conversation = Conversation(
            tenant_id=tenant_id, channel_id=channel.id, customer_id=customer.id
        )
        session.add(conversation)
        await session.flush()
        for i in range(messages):
            session.add(
                Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    direction=MessageDirection.INBOUND,
                    status=MessageStatus.SENT,
                    content=f"mensaje {i}",
                )
            )
        # El commit lo hace el propio ``tenant_scoped_session`` al salir.


async def test_deleting_a_tenant_leaves_no_messages_behind(db_session) -> None:
    """El criterio de aceptación del WP de GDPR, literal: cero filas con su
    ``tenant_id`` después del borrado."""
    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_tenant_with_messages(session, tenant_id, messages=5)

    async with sm() as session:
        before = await session.scalar(
            sa.select(sa.func.count())
            .select_from(Message.__table__)
            .where(Message.__table__.c.tenant_id == tenant_id)
        )
        assert before == 5

        # Lo que hace el endpoint de admin: borra el tenant y deja que la
        # base arrastre el resto.
        await session.execute(sa.delete(Tenant.__table__).where(Tenant.__table__.c.id == tenant_id))
        await session.commit()

    async with sm() as session:
        for table in (Message.__table__, Conversation.__table__):
            left = await session.scalar(
                sa.select(sa.func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
            )
            assert left == 0, f"{table.name} sobrevivió al borrado del tenant"


async def test_deleting_a_conversation_takes_its_messages(db_session) -> None:
    """El eslabón concreto que 0063 rompió y 0070 devuelve."""
    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_tenant_with_messages(session, tenant_id, messages=3)

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        conversation_id = await session.scalar(
            sa.select(Conversation.__table__.c.id).where(
                Conversation.__table__.c.tenant_id == tenant_id
            )
        )
        await session.execute(
            sa.delete(Conversation.__table__).where(Conversation.__table__.c.id == conversation_id)
        )

    async with sm() as session:
        orphans = await session.scalar(
            sa.select(sa.func.count())
            .select_from(Message.__table__)
            .where(Message.__table__.c.conversation_id == conversation_id)
        )
        assert orphans == 0

    # Limpieza: el tenant sigue ahí porque solo se borró la conversación.
    async with sm() as session:
        await session.execute(sa.delete(Tenant.__table__).where(Tenant.__table__.c.id == tenant_id))
        await session.commit()
