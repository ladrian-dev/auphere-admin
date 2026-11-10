"""Spec 047, T026 — quién se entera cuando el agente no contesta, y cuántas veces.

Requisitos 2.4 y 2.5 (``contracts/events.md`` §3):

- **Sin saldo** avisa al partner (campana y correo) y a las personas del cliente
  (campana, correo y push), como mucho una vez por motivo, cliente y día. Son
  los avisos de hoy (``client.out_of_quota`` y ``client.balance_out``), que la
  consola nueva reemplaza al activarse por partner.
- **Con Bandeja**, la conversación espera a una persona y su gente recibe el
  aviso de la Bandeja (campana, correo y push), uno por espera.
- **Sin Bandeja**, avisa a los destinatarios de escalado del canal por la vía de
  hoy (la fila ``conversation.escalated`` que el alertador convierte en la
  plantilla al dueño) y, si el canal tiene mensaje de espera, lo manda como
  mucho una vez cada 6 h por conversación.

El tope del agente avisa igual que sin saldo; su puerta llega con la ola 7.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import process_inbound

from nexus_api.db.models import (
    AgentConfigStatus,
    AuditLog,
    ClientPushEvent,
    ConsoleNotification,
    ConversationStatus,
)

from ..conftest import add_client_member, make_client_access
from ._turn_world import (
    RecordingPipeline,
    conversation_of,
    make_world,
    outbound_rows,
    scalar,
    wallet_closed,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

WAIT = "Gracias por escribir. Te respondemos en cuanto podamos."


async def _client(db_session: Any, console_world: dict[str, Any], *, inbox: bool, **kw: Any) -> Any:
    a = console_world["a"]
    world = await make_world(db_session, tenant_id=a["tenant_id"], **kw)
    modules = ("panel", "inbox", "usage") if inbox else ("panel", "usage")
    await make_client_access(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"], modules=modules
    )
    await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    world.extra.update(partner_id=a["partner_id"], ref=a["ref"])
    return world


async def _notifications(db_session: Any, partner_id: Any, kind: str) -> list[ConsoleNotification]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == partner_id,
                    ConsoleNotification.kind == kind,
                )
            )
        )
        .scalars()
        .all()
    )


async def _pushes(world: Any, kind: str) -> int:
    return int(
        await scalar(
            world,
            sa.select(sa.func.count())
            .select_from(ClientPushEvent)
            .where(ClientPushEvent.kind == kind),
        )
    )


async def _escalation_rows(world: Any) -> list[dict[str, Any]]:
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        rows = (
            (
                await s.execute(
                    sa.select(AuditLog).where(AuditLog.action == "conversation.escalated")
                )
            )
            .scalars()
            .all()
        )
        return [dict(r.after_json or {}) for r in rows]


async def test_no_balance_tells_the_partner_and_the_client_once_a_day(
    db_session, console_world, monkeypatch
) -> None:
    world = await _client(db_session, console_world, inbox=True)
    wallet_closed(monkeypatch)
    pipeline = RecordingPipeline()

    await process_inbound(world.event("hola"), pipeline=pipeline)
    await process_inbound(world.event("¿hola?", user="+34600333444"), pipeline=pipeline)

    partner = world.extra["partner_id"]
    told_partner = await _notifications(db_session, partner, "client.out_of_quota")
    assert len(told_partner) == 1, "uno por motivo, cliente y día"
    assert told_partner[0].audience == "partner"
    told_client = await _notifications(db_session, partner, "client.balance_out")
    assert len(told_client) == 1
    assert told_client[0].audience == "client"
    assert await _pushes(world, "client.balance") == 1


async def test_with_the_inbox_the_people_hear_once_per_wait(
    db_session, console_world, monkeypatch
) -> None:
    world = await _client(db_session, console_world, inbox=True)
    wallet_closed(monkeypatch)
    pipeline = RecordingPipeline()

    await process_inbound(world.event("hola"), pipeline=pipeline)
    await process_inbound(world.event("¿hay alguien?"), pipeline=pipeline)

    conv = await conversation_of(world)
    assert conv.status == ConversationStatus.ESCALATED
    waiting = await _notifications(db_session, world.extra["partner_id"], "inbox.waiting")
    assert len(waiting) == 1, "una espera, un aviso — no uno por mensaje"
    assert waiting[0].audience == "client"
    assert waiting[0].payload.get("reason") == "no_balance"
    # Un aviso nunca lleva el cuerpo de un mensaje (§I, events.md §5).
    assert "hola" not in str(waiting[0].payload)
    assert await _pushes(world, "inbox.waiting") == 1
    assert await _escalation_rows(world) == [], "con Bandeja el aviso va por la Bandeja"


async def test_without_the_inbox_the_channel_recipients_hear_and_the_wait_message_goes_once(
    db_session, console_world
) -> None:
    world = await _client(
        db_session,
        console_world,
        inbox=False,
        agent_config=AgentConfigStatus.STAGED,
        channel_config={"phone_number_id": "PN", "wait_message": WAIT},
    )
    pipeline = RecordingPipeline()

    await process_inbound(world.event("hola"), pipeline=pipeline)
    await process_inbound(world.event("¿me lees?"), pipeline=pipeline)

    escalations = await _escalation_rows(world)
    assert len(escalations) == 1, "un aviso por espera"
    assert escalations[0]["reason"] == "agent_unpublished"
    sent = [m for m in await outbound_rows(world) if m.content == WAIT]
    assert len(sent) == 1, "el mensaje de espera, como mucho una vez cada 6 h"
    assert sent[0].actor_kind == "system"
    assert await _notifications(db_session, world.extra["partner_id"], "inbox.waiting") == []


async def test_a_channel_without_a_wait_message_sends_nothing(db_session, console_world) -> None:
    world = await _client(
        db_session, console_world, inbox=False, agent_config=AgentConfigStatus.STAGED
    )

    await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    assert await outbound_rows(world) == []
    assert len(await _escalation_rows(world)) == 1


async def test_with_the_inbox_no_wait_message_is_sent(db_session, console_world) -> None:
    world = await _client(
        db_session,
        console_world,
        inbox=True,
        agent_config=AgentConfigStatus.STAGED,
        channel_config={"phone_number_id": "PN", "wait_message": WAIT},
    )

    await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    assert await outbound_rows(world) == []


async def test_out_of_audience_tells_nobody(db_session, console_world) -> None:
    world = await _client(
        db_session,
        console_world,
        inbox=False,
        policies={"admin_access": {"admin_only": True, "admin_phones": ["+34999000111"]}},
        channel_config={"phone_number_id": "PN", "wait_message": WAIT},
    )

    await process_inbound(world.event("hola"), pipeline=RecordingPipeline())

    assert await _escalation_rows(world) == []
    assert await outbound_rows(world) == []
