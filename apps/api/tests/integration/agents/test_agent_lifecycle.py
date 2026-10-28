"""Spec 047, T118 a T121 — varios agentes con estado claro; pausar, reanudar,
archivar y restaurar (historias 19 y 20; requisitos 25 a 28).

- **Estados** (25): la vida guardada con su motivo; el estado visible derivado,
  el mismo en la cabecera y en las tarjetas; pausar no toca los canales.
- **Varios agentes** (26): las tarjetas abren la pestaña que toca; exactamente
  uno por defecto, con el cambio atómico; lo que no nombra agente usa el de por
  defecto; renombrar.
- **Pausar y reanudar** (27): los mensajes se guardan con su motivo; reanudar
  devuelve lo de antes; sin saldo se pausa y al volver se reanuda solo lo que el
  sistema pausó; quién (``agents:write``), desde dónde y por qué; confirmación si
  hay conversaciones en curso.
- **Archivar y restaurar** (28): el destino de cada número o en pausa; restaurar
  deja el agente en pausa; nunca se borra; el de por defecto pide elegir otro.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import process_inbound
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AuditLog, Channel, ChannelStatus, ChannelType
from nexus_api.services import agent_states
from nexus_api.services.agents import principal_agent_id
from tests.conftest import add_console_member

from .._turn_world import RecordingPipeline, conversation_of, inbound_rows, make_world
from ..builder._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft
from ..business._business_world import Biz, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


async def _agent(client: Any, biz: Biz, fake_redis: Any, name: str) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name=name)
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    return uuid.UUID(body["result"]["agent_id"])


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _row(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> Agent:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = await db_session.get(Agent, agent_id, populate_existing=True)
    assert agent is not None
    return agent


async def _channel(
    db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID, number: str
) -> uuid.UUID:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = Channel(
            tenant_id=biz.tenant_id,
            agent_id=agent_id,
            type=ChannelType.WHATSAPP,
            provider="whatsapp_meta",
            provider_identifier=number,
            config={},
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(channel)
        await db_session.flush()
        return channel.id


# ── T118: estados ──────────────────────────────────────────────────────────


async def test_the_stored_life_and_the_visible_state_say_the_same_everywhere(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    head = (await client.get(_url(biz, agent_id), headers=biz.headers())).json()
    assert (head["lifecycle"], head["visible_state"]["code"]) == ("draft", "draft")
    cards = (await client.get(f"/console/clients/{biz.ref}/agents", headers=biz.headers())).json()
    card = next(c for c in cards if c["id"] == str(agent_id))
    assert card["visible_state"] == head["visible_state"] and card["opens"] == "builder"

    channel_id = await _channel(db_session, biz, agent_id, "34600111001")
    paused = await client.post(f"{_url(biz, agent_id)}/pause", json={}, headers=biz.headers())
    assert paused.status_code == 200, paused.text
    assert paused.json()["visible_state"] == {"code": "paused", "tone": "warn", "reason": "manual"}
    # 25.4: pausar el agente no toca sus canales.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = await db_session.get(Channel, channel_id, populate_existing=True)
    assert channel is not None and channel.status is ChannelStatus.ACTIVE
    cards = (await client.get(f"/console/clients/{biz.ref}/agents", headers=biz.headers())).json()
    card = next(c for c in cards if c["id"] == str(agent_id))
    assert card["visible_state"]["code"] == "paused" and card["opens"] == "overview"


# ── T119: varios agentes y el de por defecto ───────────────────────────────


async def test_exactly_one_default_with_an_atomic_change_and_it_answers_by_default(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    first = await _agent(client, biz, fake_redis, "Recepción")
    second = await _agent(client, biz, fake_redis, "Ventas")
    assert (await _row(db_session, biz, first)).is_default is True
    assert (await _row(db_session, biz, second)).is_default is False
    moved = await client.put(
        f"/console/clients/{biz.ref}/default-agent",
        json={"agent_id": str(second)},
        headers=biz.headers(),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["is_default"] is True
    async with tenant_scoped_session(db_session, biz.tenant_id):
        defaults = (
            await db_session.scalars(sa.select(Agent.id).where(Agent.is_default.is_(True)))
        ).all()
        principal = await principal_agent_id(db_session)
    assert list(defaults) == [second]
    # 26.3: lo que no nombra agente (enlaces, API, rutas sin ?agent=) usa el de por defecto.
    assert principal == second
    renamed = await client.patch(
        _url(biz, second), json={"name": "Ventas mayoristas"}, headers=biz.headers()
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Ventas mayoristas"


# ── T120: pausar y reanudar ────────────────────────────────────────────────


async def test_a_paused_agent_keeps_the_messages_with_its_reason(db_session: AsyncSession) -> None:
    world = await make_world(db_session)
    async with tenant_scoped_session(db_session, world.tenant_id):
        agent = await db_session.get(Agent, world.agent_id)
        assert agent is not None
        agent.lifecycle = "published"
        await agent_states.pause(
            db_session, agent, by_kind="partner_member", by_id="u", origin="console", actor="test"
        )
    pipeline = RecordingPipeline()
    await process_inbound(world.event("hola"), pipeline=pipeline)
    assert pipeline.calls == [], "un agente en pausa no contesta"
    assert [r.content for r in await inbound_rows(world)] == ["hola"]
    assert (await conversation_of(world)).waiting_reason == "paused_agent"


async def test_an_agent_at_its_cap_keeps_the_messages_as_tope_del_agente(
    db_session: AsyncSession,
) -> None:
    """Quickstart, ola 7.3 (requisitos 44.2 y 27.2): al 100 % del tope el agente
    pasa a la Bandeja con «Tope del agente» (``agent_cap``), no con la pausa de
    una persona."""
    world = await make_world(db_session)
    async with tenant_scoped_session(db_session, world.tenant_id):
        agent = await db_session.get(Agent, world.agent_id)
        assert agent is not None
        agent.lifecycle = "published"
        await agent_states.pause(
            db_session,
            agent,
            reason="agent_cap",
            by_kind="system",
            by_id=None,
            origin="system",
            actor="system",
        )
    pipeline = RecordingPipeline()
    await process_inbound(world.event("hola"), pipeline=pipeline)
    assert pipeline.calls == [], "un agente en su tope no contesta"
    assert [r.content for r in await inbound_rows(world)] == ["hola"]
    assert (await conversation_of(world)).waiting_reason == "agent_cap"


async def test_resume_gives_back_what_it_was_and_the_system_only_undoes_its_own(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    mine = await _agent(client, biz, fake_redis, "Recepción")
    other = await _agent(client, biz, fake_redis, "Ventas")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        for agent_id in (mine, other):
            agent = await db_session.get(Agent, agent_id)
            assert agent is not None
            agent.lifecycle = "published"
    # Una persona pausa uno; luego la bolsa se vacía.
    assert (
        await client.post(f"{_url(biz, mine)}/pause", json={}, headers=biz.headers())
    ).status_code == 200
    async with tenant_scoped_session(db_session, biz.tenant_id):
        paused = await agent_states.pause_for_balance(db_session)
    assert paused == [other]
    assert (await _row(db_session, biz, other)).pause_reason == "no_balance"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        resumed = await agent_states.resume_after_balance(db_session)
    # 27.4: vuelve el saldo y se reanuda solo el que pausó el sistema.
    assert resumed == [other]
    assert (await _row(db_session, biz, other)).lifecycle == "published"
    assert (await _row(db_session, biz, mine)).lifecycle == "paused"
    back = await client.post(f"{_url(biz, mine)}/resume", headers=biz.headers())
    assert back.json()["lifecycle"] == "published"


async def test_who_from_where_and_why_and_the_confirmation_with_open_conversations(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    denied = await client.post(
        f"{_url(biz, agent_id)}/pause", json={}, headers=analyst["headers"]()
    )
    assert denied.status_code == 403
    channel_id = await _channel(db_session, biz, agent_id, "34600111002")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        from nexus_api.db.models import Conversation, ConversationStatus, Customer

        for n in range(2):
            customer = Customer(
                tenant_id=biz.tenant_id, identifier=f"+3460000000{n}", preferences={}
            )
            db_session.add(customer)
            await db_session.flush()
            db_session.add(
                Conversation(
                    tenant_id=biz.tenant_id,
                    channel_id=channel_id,
                    customer_id=customer.id,
                    status=ConversationStatus.OPEN,
                )
            )
    ask = await client.post(f"{_url(biz, agent_id)}/pause", json={}, headers=biz.headers())
    assert ask.status_code == 409
    assert ask.json()["detail"] == {"code": "confirm_required", "open_conversations": 2}
    done = await client.post(
        f"{_url(biz, agent_id)}/pause",
        json={"confirm": True, "note": "Vacaciones"},
        headers=biz.headers(),
    )
    assert done.status_code == 200
    assert (
        done.json()["paused_by_kind"] == "partner_member"
        and done.json()["paused_origin"] == "console"
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        audit = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "agent.paused")
        )
    assert audit is not None and audit.after_json["note"] == "Vacaciones"
    assert audit.after_json["origin"] == "console"


# ── T121: archivar y restaurar ─────────────────────────────────────────────


async def test_archive_asks_each_numbers_destination_restore_pauses_and_nothing_is_deleted(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    keep = await _agent(client, biz, fake_redis, "Recepción")
    leave = await _agent(client, biz, fake_redis, "Ventas")
    one = await _channel(db_session, biz, leave, "34600111003")
    two = await _channel(db_session, biz, leave, "34600111004")
    missing = await client.post(
        f"{_url(biz, leave)}/archive",
        json={"channels": [{"channel_id": str(one), "to": str(keep)}]},
        headers=biz.headers(),
    )
    assert (
        missing.status_code == 422
        and missing.json()["detail"]["code"] == "channel_destination_required"
    )
    archived = await client.post(
        f"{_url(biz, leave)}/archive",
        json={
            "channels": [
                {"channel_id": str(one), "to": str(keep)},
                {"channel_id": str(two), "to": "pause"},
            ]
        },
        headers=biz.headers(),
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["lifecycle"] == "archived" and archived.json()["allowed"] == ["restore"]
    async with tenant_scoped_session(db_session, biz.tenant_id):
        first = await db_session.get(Channel, one, populate_existing=True)
        second = await db_session.get(Channel, two, populate_existing=True)
        still_there = await db_session.get(Agent, leave, populate_existing=True)
    assert first is not None and first.agent_id == keep
    assert second is not None and second.status is ChannelStatus.PAUSED
    assert still_there is not None  # 28.3: nunca se borra
    # La pestaña lo encuentra para restaurarlo; la lista de siempre, no.
    base = f"/console/clients/{biz.ref}/agents"
    live = await client.get(base, headers=biz.headers())
    assert str(leave) not in [a["id"] for a in live.json()]
    every = await client.get(f"{base}?include_archived=true", headers=biz.headers())
    card = next(a for a in every.json() if a["id"] == str(leave))
    assert card["visible_state"]["code"] == "archived"
    restored = await client.post(f"{_url(biz, leave)}/restore", headers=biz.headers())
    assert restored.status_code == 200
    assert (restored.json()["lifecycle"], restored.json()["pause_reason"]) == ("paused", "manual")


async def test_the_default_agent_asks_to_choose_another_before_archiving(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    default = await _agent(client, biz, fake_redis, "Recepción")
    other = await _agent(client, biz, fake_redis, "Ventas")
    refused = await client.post(
        f"{_url(biz, default)}/archive", json={"channels": []}, headers=biz.headers()
    )
    assert (
        refused.status_code == 409 and refused.json()["detail"]["code"] == "default_agent_required"
    )
    await client.put(
        f"/console/clients/{biz.ref}/default-agent",
        json={"agent_id": str(other)},
        headers=biz.headers(),
    )
    ok = await client.post(
        f"{_url(biz, default)}/archive", json={"channels": []}, headers=biz.headers()
    )
    assert ok.status_code == 200
