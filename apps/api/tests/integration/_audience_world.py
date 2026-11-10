"""Spec 058 — un cliente en pausa con esperas de contactos que acaban fuera de la
audiencia. Lo comparten la prueba de la limpieza y su prueba de aislamiento.

Las esperas se siembran como nacen de verdad. El número responde a todos
(«A todos»), el cliente está en pausa y cada contacto que escribe abre su espera
con «Cliente en pausa» y su aviso. Después el número pasa a «Solo mi equipo», y
esos contactos quedan fuera de la audiencia con la espera abierta: es lo que el
fallo dejó en producción.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import process_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelAudienceNumber,
    ConsoleNotification,
    ConversationEvent,
    ConversationStatus,
    Partner,
    Tenant,
    TenantStatus,
)

from ..conftest import add_client_member, make_client_access
from ._turn_world import RecordingPipeline, World, conversation_of, make_world

TEAM = "+34999000111"


async def in_tenant(world: World, *statements: Any) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        for statement in statements:
            await s.execute(statement)
        await s.commit()


async def paused_client(
    db_session: Any,
    side: dict[str, Any],
    *,
    console_v2: bool = True,
    policies: dict[str, Any] | None = None,
) -> World:
    """El cliente de ``console_world[side]``, en pausa y con Bandeja. Con
    ``console_v2`` su número decide su propia audiencia (``strict``) y empieza
    en «A todos»; sin ella, decide la política de la versión publicada."""
    world = await make_world(db_session, tenant_id=side["tenant_id"], policies=policies)
    await make_client_access(db_session, partner_id=side["partner_id"], tenant_id=side["tenant_id"])
    await add_client_member(db_session, partner_id=side["partner_id"], tenant_id=side["tenant_id"])
    await db_session.execute(
        sa.update(Tenant).where(Tenant.id == side["tenant_id"]).values(status=TenantStatus.PAUSED)
    )
    if console_v2:
        await db_session.execute(
            sa.update(Partner)
            .where(Partner.id == side["partner_id"])
            .values(console_v2_enabled_at=datetime.now(UTC))
        )
    await db_session.commit()
    if console_v2:
        await in_tenant(
            world,
            sa.update(Channel)
            .where(Channel.id == world.channel_id)
            .values(audience_mode="everyone"),
        )
    world.extra.update(partner_id=side["partner_id"], ref=side["ref"])
    return world


async def waiting(world: World, contact: str) -> uuid.UUID:
    """El contacto escribe y su conversación espera por la pausa."""
    await process_inbound(world.event("hola", user=contact), pipeline=RecordingPipeline())
    conv = await conversation_of(world, contact)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.waiting_reason == "paused_client"
    return conv.id


async def team_only(world: World, *test_numbers: str) -> None:
    """El número pasa a «Solo mi equipo»: el resto queda fuera de la audiencia."""
    statements: list[Any] = [
        sa.update(Channel).where(Channel.id == world.channel_id).values(audience_mode="team_only")
    ]
    for phone in test_numbers:
        statements.append(
            sa.insert(ChannelAudienceNumber).values(
                tenant_id=world.tenant_id,
                channel_id=world.channel_id,
                kind="test",
                phone_e164=phone,
            )
        )
    await in_tenant(world, *statements)


async def notices(db_session: Any, partner_id: uuid.UUID) -> dict[str, datetime | None]:
    """Los avisos «espera a una persona» del partner: conversación → ``handled_at``.

    Valores, no filas: una segunda llamada caduca la sesión, y leer una fila
    caducada fuera de su ``await`` revienta (``MissingGreenlet``)."""
    rows = (
        await db_session.execute(
            sa.select(
                ConsoleNotification.payload["conversation_id"].astext,
                ConsoleNotification.handled_at,
            ).where(
                ConsoleNotification.partner_id == partner_id,
                ConsoleNotification.kind == "inbox.waiting",
            )
        )
    ).all()
    return {str(conversation_id): handled_at for conversation_id, handled_at in rows}


async def conversation_state(world: World, conversation_id: uuid.UUID) -> tuple[str, str | None]:
    from nexus_api.db.models import Conversation

    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        row = (
            await s.execute(
                sa.select(Conversation.status, Conversation.waiting_reason).where(
                    Conversation.id == conversation_id
                )
            )
        ).one()
        status = row[0].value if hasattr(row[0], "value") else str(row[0])
        return status, row[1]


async def released(world: World) -> dict[str, dict[str, Any]]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        rows = (
            (
                await s.execute(
                    sa.select(ConversationEvent).where(ConversationEvent.kind == "released")
                )
            )
            .scalars()
            .all()
        )
        return {str(r.conversation_id): dict(r.payload or {}) | {"actor": r.actor} for r in rows}
