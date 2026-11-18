"""Spec 063, requisito 2 — llegar a la configuración de un número.

- El resumen de canales trae la audiencia de cada número (2.3): «No responde a
  nadie» sale de ``audience_mode == "unset"``.
- Un número sin agente asignado lo atiende el principal del cliente: el marcado
  por defecto o, si ninguno lo está, el activo más antiguo, que es la regla del
  turno (``services/agents.agent_for_channel``). La pestaña Canales de cada
  agente, su tarjeta en Agentes y la página del número dicen el mismo (2.4).
- A dónde lleva la tarjeta de un agente que espera un número (2.7) lo fija la
  consola (``life-model.test.ts``).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, Channel, ChannelStatus, ChannelType

from .business._business_world import Biz, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Estética Lumen")


async def _agent(db: AsyncSession, biz: Biz, name: str, *, default: bool) -> uuid.UUID:
    async with tenant_scoped_session(db, biz.tenant_id):
        agent = Agent(id=uuid.uuid4(), tenant_id=biz.tenant_id, name=name, is_default=default)
        db.add(agent)
    await db.commit()
    return agent.id


async def _number(db: AsyncSession, biz: Biz, *, agent_id: uuid.UUID | None = None) -> uuid.UUID:
    async with tenant_scoped_session(db, biz.tenant_id):
        channel = Channel(
            id=uuid.uuid4(),
            tenant_id=biz.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3460017{uuid.uuid4().int % 10000:04d}",
            config={},
            status=ChannelStatus.ACTIVE,
            agent_id=agent_id,
        )
        db.add(channel)
    await db.commit()
    return channel.id


async def _tab(client: Any, biz: Biz, agent_id: uuid.UUID) -> set[str]:
    resp = await client.get(
        f"/console/clients/{biz.ref}/agents/{agent_id}/channels", headers=biz.headers()
    )
    assert resp.status_code == 200, resp.text
    return {c["id"] for c in resp.json()["channels"]}


async def _page_agent(client: Any, biz: Biz, channel_id: uuid.UUID) -> str | None:
    resp = await client.get(
        f"/console/clients/{biz.ref}/channels/{channel_id}", headers=biz.headers()
    )
    assert resp.status_code == 200, resp.text
    agent = resp.json()["agent"]
    return None if agent is None else str(agent["id"])


async def _cards(client: Any, biz: Biz) -> dict[str, dict[str, Any]]:
    resp = await client.get(f"/console/clients/{biz.ref}/agents", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    return {a["id"]: a for a in resp.json()}


async def _same_agent_everywhere(
    client: Any, biz: Biz, channel_id: uuid.UUID, expected: uuid.UUID, other: uuid.UUID
) -> None:
    assert str(channel_id) in await _tab(client, biz, expected)
    assert str(channel_id) not in await _tab(client, biz, other)
    assert await _page_agent(client, biz, channel_id) == str(expected)
    cards = await _cards(client, biz)
    assert str(channel_id) in {c["id"] for c in cards[str(expected)]["channels"]}
    assert str(channel_id) not in {c["id"] for c in cards[str(other)]["channels"]}


async def test_the_overview_says_who_each_number_answers(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    await _agent(db_session, biz, "Ana", default=True)
    channel_id = await _number(db_session, biz)
    resp = await client.get(f"/console/clients/{biz.ref}/channels/overview", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    row = next(c for c in resp.json()["channels"] if c["id"] == str(channel_id))
    assert row["audience_mode"] == "unset"


async def test_an_unassigned_number_belongs_to_the_default_agent_everywhere(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    older = await _agent(db_session, biz, "Recepción", default=False)
    default = await _agent(db_session, biz, "Ana", default=True)
    channel_id = await _number(db_session, biz)
    await _same_agent_everywhere(client, biz, channel_id, expected=default, other=older)


async def test_without_a_marked_default_it_is_the_oldest_active_one(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    older = await _agent(db_session, biz, "Recepción", default=False)
    newer = await _agent(db_session, biz, "Ana", default=False)
    channel_id = await _number(db_session, biz)
    await _same_agent_everywhere(client, biz, channel_id, expected=older, other=newer)


async def test_an_assigned_number_stays_with_its_agent(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    default = await _agent(db_session, biz, "Ana", default=True)
    other = await _agent(db_session, biz, "Recepción", default=False)
    channel_id = await _number(db_session, biz, agent_id=other)
    await _same_agent_everywhere(client, biz, channel_id, expected=other, other=default)


async def test_the_playground_channel_is_on_no_card(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """El canal interno del probador nace sin agente, como en prod (Ana, 2026-11-18):
    no es un número del cliente."""
    ana = await _agent(db_session, biz, "Ana", default=True)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        playground = Channel(
            id=uuid.uuid4(),
            tenant_id=biz.tenant_id,
            type=ChannelType.WEB,
            provider="qa_playground",
            provider_identifier=f"qa:{uuid.uuid4()}",
            config={},
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(playground)
    await db_session.commit()
    card = (await _cards(client, biz))[str(ana)]
    assert str(playground.id) not in {c["id"] for c in card["channels"]}
    assert str(playground.id) not in await _tab(client, biz, ana)


async def test_a_channel_that_does_not_decide_reads_its_agents_audience(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Instagram, Messenger o un número que no es estricto llevan ``unset`` guardado
    y responden con la audiencia del agente publicado (``channel_audience``). No
    pueden salir «No responde a nadie»: la tarjeta diría algo falso (§V)."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    ana = await _agent(db_session, biz, "Ana", default=True)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            AgentConfig(
                tenant_id=biz.tenant_id,
                agent_id=ana,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Eres Ana.",
                tools=[],
                channels=[],
                policies={},
            )
        )
        instagram = Channel(
            id=uuid.uuid4(),
            tenant_id=biz.tenant_id,
            type=ChannelType.INSTAGRAM,
            provider="meta_instagram",
            provider_identifier=f"ig:{uuid.uuid4().int % 10**8}",
            config={},
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(instagram)
    await db_session.commit()
    resp = await client.get(f"/console/clients/{biz.ref}/channels/overview", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    row = next(c for c in resp.json()["channels"] if c["id"] == str(instagram.id))
    assert row["audience_mode"] != "unset"
