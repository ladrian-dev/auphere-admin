"""Spec 058, T004 — un contacto fuera de la audiencia no espera a nadie, ni en pausa.

Requisitos 1.2 a 1.6. En producción (2026-11-10), Flor y Encanto estaba en
pausa y su número respondía solo a su equipo. Cada cliente final que escribía
abría «Espera a una persona» y le llegaba un correo a la persona del cliente,
porque la puerta de pausa iba antes que la de audiencia. Con el cliente activo,
esos mismos mensajes se guardaban en silencio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import process_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfigStatus,
    AuditLog,
    Channel,
    ChannelAudienceNumber,
    ChannelStatus,
    ClientPushEvent,
    ConsoleNotification,
    ConversationStatus,
    Partner,
    Tenant,
    TenantStatus,
)

from ..conftest import add_client_member, make_client_access
from ._turn_world import (
    RecordingPipeline,
    conversation_of,
    inbound_rows,
    make_world,
    outbound_rows,
    scalar,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CONTACT = "+34600111222"
TEAM = "+34999000111"
ADMIN_ONLY = {"admin_access": {"admin_only": True, "admin_phones": [TEAM]}}
WAIT = "Gracias por escribir. Te respondemos en cuanto podamos."


async def _client(
    db_session: Any,
    console_world: dict[str, Any],
    *,
    inbox: bool = True,
    tenant_status: TenantStatus = TenantStatus.ACTIVE,
    **kw: Any,
) -> Any:
    a = console_world["a"]
    world = await make_world(db_session, tenant_id=a["tenant_id"], **kw)
    modules = ("panel", "inbox", "usage") if inbox else ("panel", "usage")
    await make_client_access(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"], modules=modules
    )
    await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    if tenant_status != TenantStatus.ACTIVE:
        await db_session.execute(
            sa.update(Tenant).where(Tenant.id == a["tenant_id"]).values(status=tenant_status)
        )
        await db_session.commit()
    world.extra.update(partner_id=a["partner_id"], ref=a["ref"])
    return world


async def _in_tenant(world: Any, *statements: Any) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        for statement in statements:
            await s.execute(statement)
        await s.commit()


async def _pause_agent(world: Any, reason: str) -> None:
    await _in_tenant(
        world,
        sa.update(Agent)
        .where(Agent.id == world.agent_id)
        .values(lifecycle="paused", pause_reason=reason),
    )


async def _strict_audience(
    db_session: Any, world: Any, mode: str, numbers: dict[str, list[str]] | None = None
) -> None:
    """Un número que decide su propia audiencia: WhatsApp de un partner con la
    consola nueva (``channel_config.gate_audience`` → ``strict``)."""
    await db_session.execute(
        sa.update(Partner)
        .where(Partner.id == world.extra["partner_id"])
        .values(console_v2_enabled_at=datetime.now(UTC))
    )
    await db_session.commit()
    statements: list[Any] = [
        sa.update(Channel).where(Channel.id == world.channel_id).values(audience_mode=mode)
    ]
    for kind, phones in (numbers or {}).items():
        for phone in phones:
            statements.append(
                sa.insert(ChannelAudienceNumber).values(
                    tenant_id=world.tenant_id,
                    channel_id=world.channel_id,
                    kind=kind,
                    phone_e164=phone,
                )
            )
    await _in_tenant(world, *statements)


async def _waiting_notices(db_session: Any, world: Any) -> list[ConsoleNotification]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == world.extra["partner_id"],
                    ConsoleNotification.kind == "inbox.waiting",
                )
            )
        )
        .scalars()
        .all()
    )


async def _waiting_pushes(world: Any) -> int:
    return int(
        await scalar(
            world,
            sa.select(sa.func.count())
            .select_from(ClientPushEvent)
            .where(ClientPushEvent.kind == "inbox.waiting"),
        )
    )


async def _escalation_rows(world: Any) -> int:
    return int(
        await scalar(
            world,
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "conversation.escalated"),
        )
    )


async def _assert_kept_in_silence(db_session: Any, world: Any, user: str = CONTACT) -> None:
    """Lo mismo que con el cliente activo: guardado, «número no permitido»,
    sin espera y sin ningún aviso (requisitos 1.2, 1.3 y 1.5)."""
    rows = await inbound_rows(world)
    assert rows, "el entrante tiene que estar guardado (047, 2.1)"
    assert rows[-1].skipped_reason == "not_admin", "Conversaciones: «número no permitido»"
    conv = await conversation_of(world, user)
    assert conv.waiting_reason == "out_of_audience"
    assert conv.status == ConversationStatus.OPEN, "no espera a nadie"
    assert conv.attended_at is None, "la Bandeja no la enseña"
    assert await _waiting_notices(db_session, world) == [], "ni campana ni correo"
    assert await _waiting_pushes(world) == 0, "ni push"


@pytest.mark.parametrize(
    "state",
    ["paused_client", "archived_client", "paused_channel", "agent_paused_no_balance"],
)
async def test_out_of_audience_is_kept_in_silence_whatever_is_paused(
    db_session, console_world, state
) -> None:
    """Requisitos 1.2, 1.3 y 1.6: un número sin audiencia propia (el partner
    sin la consola nueva) decide con la política de la versión publicada, aunque
    el agente esté en pausa."""
    kw: dict[str, Any] = {"policies": ADMIN_ONLY}
    if state == "paused_client":
        kw["tenant_status"] = TenantStatus.PAUSED
    elif state == "archived_client":
        kw["tenant_status"] = TenantStatus.ARCHIVED
    elif state == "paused_channel":
        kw["channel_status"] = ChannelStatus.PAUSED
    world = await _client(db_session, console_world, **kw)
    if state == "agent_paused_no_balance":
        await _pause_agent(world, "no_balance")
    pipeline = RecordingPipeline()

    result = await process_inbound(world.event("hola"), pipeline=pipeline)

    assert result["skipped"] == "not_admin"
    assert result["reason"] == "out_of_audience"
    assert pipeline.calls == []
    await _assert_kept_in_silence(db_session, world)


async def test_the_flor_y_encanto_shape_tells_nobody(db_session, console_world) -> None:
    """El caso de producción: cliente en pausa, número «Solo mi equipo» de un
    partner con la consola nueva, y un cliente final que no es número de prueba."""
    world = await _client(db_session, console_world, tenant_status=TenantStatus.PAUSED)
    await _strict_audience(db_session, world, "team_only", {"test": [TEAM]})

    result = await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    assert result["reason"] == "out_of_audience"
    await _assert_kept_in_silence(db_session, world)


async def test_a_test_number_still_waits_for_the_pause(db_session, console_world) -> None:
    """Requisito 1.4: dentro de la audiencia nada cambia. Espera con su motivo
    y un aviso, uno solo."""
    world = await _client(db_session, console_world, tenant_status=TenantStatus.PAUSED)
    await _strict_audience(db_session, world, "team_only", {"test": [CONTACT]})

    await process_inbound(world.event("hola"), pipeline=RecordingPipeline())
    await process_inbound(world.event("¿hay alguien?"), pipeline=RecordingPipeline())

    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.waiting_reason == "paused_client"
    notices = await _waiting_notices(db_session, world)
    assert len(notices) == 1, "una espera, un aviso"
    assert notices[0].payload.get("reason") == "paused_client"
    assert await _waiting_pushes(world) == 1


async def test_everyone_with_exceptions_and_no_balance(db_session, console_world) -> None:
    """Historia 1, escenario 3: «A todos», el remitente en las excepciones y el
    agente pausado por saldo. La excepción no espera; otro contacto, sí."""
    world = await _client(db_session, console_world)
    await _strict_audience(db_session, world, "everyone", {"exception": [CONTACT]})
    await _pause_agent(world, "no_balance")

    result = await process_inbound(world.event("hola"), pipeline=RecordingPipeline())
    assert result["reason"] == "out_of_audience"
    await _assert_kept_in_silence(db_session, world)

    other = "+34600333444"
    result = await process_inbound(world.event("hola", user=other), pipeline=RecordingPipeline())
    assert result["reason"] == "no_balance"
    conv = await conversation_of(world, other)
    assert conv.status == ConversationStatus.ESCALATED
    assert len(await _waiting_notices(db_session, world)) == 1


async def test_an_unset_number_on_a_paused_client_tells_nobody(db_session, console_world) -> None:
    """Caso límite: «Sin configurar» no responde a nadie (047, 32.9). En pausa,
    igual que activo: nadie espera."""
    world = await _client(db_session, console_world, tenant_status=TenantStatus.PAUSED)
    await _strict_audience(db_session, world, "unset")

    result = await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    assert result["reason"] == "out_of_audience"
    await _assert_kept_in_silence(db_session, world)


async def test_without_the_inbox_no_recipient_and_no_wait_message(
    db_session, console_world
) -> None:
    """Requisito 1.3: sin módulo de Bandeja tampoco se avisa a los destinatarios
    de escalado ni se manda el mensaje de espera. Agente sin publicar: hoy, con
    un contacto de la audiencia, haría las dos cosas."""
    world = await _client(
        db_session,
        console_world,
        inbox=False,
        agent_config=AgentConfigStatus.STAGED,
        channel_config={"phone_number_id": "PN", "wait_message": WAIT},
    )
    await _strict_audience(db_session, world, "team_only", {"test": [TEAM]})

    result = await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    assert result["reason"] == "out_of_audience"
    assert await _escalation_rows(world) == 0
    assert await outbound_rows(world) == []
    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.OPEN
