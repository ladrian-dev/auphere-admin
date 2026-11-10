"""Spec 058, T006 — una espera que ya no es cierta sale de la Bandeja.

Requisitos 2.1 a 2.3. Una conversación esperaba a una persona por una pausa,
porque su contacto estaba en la audiencia o por el fallo que arregla la 058.
Ahora su contacto está fuera de la audiencia y vuelve a escribir. Su número no
le respondería ni con todo activo, así que nadie la espera: sale de la Bandeja
y su aviso queda atendido. Lo que una persona pidió o se asignó no se toca.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import process_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    ClientPushEvent,
    ConsoleNotification,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Tenant,
    TenantStatus,
)

from ..conftest import add_client_member, make_client_access
from ._turn_world import RecordingPipeline, conversation_of, make_world, outbound_rows, scalar

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CONTACT = "+34600111222"
TEAM = "+34999000111"


async def _waiting_paused_client(db_session: Any, console_world: dict[str, Any]) -> Any:
    """Un cliente en pausa con Bandeja. El contacto escribe estando en la
    audiencia (es admin de un agente solo para administradores), así que la
    conversación espera con «Cliente en pausa» y deja su aviso."""
    a = console_world["a"]
    world = await make_world(
        db_session,
        tenant_id=a["tenant_id"],
        policies={"admin_access": {"admin_only": True, "admin_phones": [CONTACT]}},
    )
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    await db_session.execute(
        sa.update(Tenant).where(Tenant.id == a["tenant_id"]).values(status=TenantStatus.PAUSED)
    )
    await db_session.commit()
    world.extra.update(partner_id=a["partner_id"])

    await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.waiting_reason == "paused_client"
    assert len(await _notices(db_session, world)) == 1
    return world


async def _in_tenant(world: Any, *statements: Any) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        for statement in statements:
            await s.execute(statement)
        await s.commit()


async def _leave_the_audience(world: Any) -> None:
    """La versión publicada pasa a responder solo a otro número."""
    await _in_tenant(
        world,
        sa.update(AgentConfig)
        .where(AgentConfig.agent_id == world.agent_id)
        .values(policies={"admin_access": {"admin_only": True, "admin_phones": [TEAM]}}),
    )


async def _notices(db_session: Any, world: Any) -> list[ConsoleNotification]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                sa.select(ConsoleNotification)
                .where(
                    ConsoleNotification.partner_id == world.extra["partner_id"],
                    ConsoleNotification.kind == "inbox.waiting",
                )
                .order_by(ConsoleNotification.created_at)
            )
        )
        .scalars()
        .all()
    )


async def _released_events(world: Any) -> list[dict[str, Any]]:
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
        return [dict(r.payload or {}) | {"actor": r.actor} for r in rows]


async def _pushes(world: Any) -> int:
    return int(
        await scalar(
            world,
            sa.select(sa.func.count())
            .select_from(ClientPushEvent)
            .where(ClientPushEvent.kind == "inbox.waiting"),
        )
    )


async def test_a_gate_wait_leaves_when_the_contact_is_out_of_the_audience(
    db_session, console_world
) -> None:
    """Requisitos 2.1 y 2.3."""
    world = await _waiting_paused_client(db_session, console_world)
    pushes_before = await _pushes(world)
    outbound_before = len(await outbound_rows(world))
    await _leave_the_audience(world)

    result = await process_inbound(world.event("¿sigue ahí?"), pipeline=RecordingPipeline())

    assert result["reason"] == "out_of_audience"
    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.OPEN, "ya no espera a nadie"
    assert conv.waiting_reason == "out_of_audience"
    assert await _released_events(world) == [
        {"why": "out_of_audience", "reason": "paused_client", "actor": "system"}
    ]
    notices = await _notices(db_session, world)
    assert len(notices) == 1, "ningún aviso nuevo"
    assert notices[0].handled_at is not None, "el aviso de la espera queda atendido"
    assert await _pushes(world) == pushes_before, "ningún push nuevo"
    assert len(await outbound_rows(world)) == outbound_before, "nada al contacto"


async def test_a_wait_that_is_not_a_gate_stays(db_session, console_world) -> None:
    """Requisito 2.2: si el contacto pidió una persona, la sigue esperando, y
    su motivo no se pisa."""
    world = await _waiting_paused_client(db_session, console_world)
    await _in_tenant(
        world,
        sa.update(Conversation)
        .where(Conversation.tenant_id == world.tenant_id)
        .values(waiting_reason="escalated"),
    )
    await _leave_the_audience(world)

    await process_inbound(world.event("¿sigue ahí?"), pipeline=RecordingPipeline())

    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.waiting_reason == "escalated"
    assert await _released_events(world) == []
    assert (await _notices(db_session, world))[0].handled_at is None


async def test_a_wait_a_person_took_stays(db_session, console_world) -> None:
    """Requisito 2.2: lo que una persona se asignó no se lo quita el sistema."""
    world = await _waiting_paused_client(db_session, console_world)
    await _in_tenant(
        world,
        sa.update(Conversation)
        .where(Conversation.tenant_id == world.tenant_id)
        .values(assigned_user_id="client_persona"),
    )
    await _leave_the_audience(world)

    await process_inbound(world.event("¿sigue ahí?"), pipeline=RecordingPipeline())

    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.waiting_reason == "paused_client"
    assert conv.assigned_user_id == "client_persona"
    assert await _released_events(world) == []
    assert (await _notices(db_session, world))[0].handled_at is None
