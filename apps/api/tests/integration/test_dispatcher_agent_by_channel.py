"""Spec 030 T091 — cada número contesta con su agente (R14.3).

El despachador real, con un cliente de dos agentes:

- un entrante en el número del agente B corre el turno **de B**: el estado del
  grafo lleva su ``agent_id`` y las políticas que miran las puertas son las de
  la versión activa de B;
- un número sin agente (los de antes de la spec 030, el Playground) corre el
  **principal**;
- promover el borrador de B no apaga a A (lo fija el repositorio en
  ``test_agent_versions_per_agent.py``; aquí, que el turno sigue yendo a A).

El pipeline es un sustituto que registra el estado: no se prueba el LLM, se
prueba qué agente decide el despachador.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _RecordingPipeline:
    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.states.append(state)
        return {"intent": "info", "response": "ok", "tool_calls": []}


async def _two_agents_two_numbers(tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            a = Agent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name="Agente principal",
                # One transaction → one now(): the principal is older on purpose.
                created_at=datetime.now(UTC) - timedelta(days=1),
            )
            s.add(a)
            await s.flush()
            b = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name="Ventas")
            s.add(b)
            await s.flush()
            for version, agent, prompt in (
                (1, a, "Eres el agente A."),
                (2, b, "Eres el agente B."),
            ):
                s.add(
                    AgentConfig(
                        tenant_id=tenant_id,
                        agent_id=agent.id,
                        version=version,
                        status=AgentConfigStatus.ACTIVE,
                        system_prompt_rendered=prompt,
                        tools=[],
                        channels=[],
                        policies={"marker": prompt},
                        created_by="test",
                    )
                )
            numbers = {}
            for name, agent_id in (("b_number", b.id), ("unassigned", None)):
                ch = Channel(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    type=ChannelType.WHATSAPP,
                    provider="meta",
                    provider_identifier=f"+3460{uuid.uuid4().int % 10**7:07d}",
                    config={"phone_number_id": "PN"},
                    status=ChannelStatus.ACTIVE,
                    agent_id=agent_id,
                )
                s.add(ch)
                numbers[name] = ch.id
            return {"a": a.id, "b": b.id, **numbers}


async def test_each_number_runs_its_agent(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    ids = await _two_agents_two_numbers(tenant_id)
    pipeline = _RecordingPipeline()

    for channel, user in (
        (ids["b_number"], "+5491100000101"),
        (ids["unassigned"], "+5491100000102"),
    ):
        await process_inbound(
            InboundEvent(tenant_id=tenant_id, channel_id=channel, user_id=user, content="hola"),
            pipeline=pipeline,
        )

    assert [s.get("agent_id") for s in pipeline.states] == [str(ids["b"]), str(ids["a"])]
