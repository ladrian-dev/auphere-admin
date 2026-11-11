"""Garantía 1 (RLS), rozada por la spec 059 (requisito 1.2; T004).

Para saber si un modelo está en uso, la plataforma recorre los agentes y las
asignaciones de **todos** los clientes. Ese barrido es de plataforma, pero cada
cliente se lee bajo su propio GUC, como cualquier lectura de sus tablas: nunca con
``row_security = off``. Y de él solo salen un recuento y los nombres de los
clientes, ni ids de agentes, ni políticas, ni prompts.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.services import model_usage

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.isolation]

ONLY_A = "openai/gpt-5.6-luna"
ONLY_B = "openai/gpt-4o"


async def _agent(tenant_id: uuid.UUID, name: str, policies: dict[str, Any]) -> uuid.UUID:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent_id = uuid.uuid4()
        await session.execute(
            sa.text("INSERT INTO agents (id, tenant_id, name) VALUES (:a, :t, :n)"),
            {"a": agent_id, "t": tenant_id, "n": name},
        )
        session.add(
            AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent_id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=f"Prompt secreto de {name}",
                channels=[],
                tools=[],
                policies=policies,
                seed_template_ref=None,
            )
        )
        return agent_id


async def _bind(tenant_id: uuid.UUID, role: str, model_id: str) -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(
                "INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id) "
                "SELECT :t, :r, id FROM model_profiles WHERE model_id = :m"
            ),
            {"t": tenant_id, "r": role, "m": model_id},
        )


@pytest_asyncio.fixture
async def world(console_world) -> AsyncIterator[dict[str, Any]]:
    a, b = console_world["a"], console_world["b"]
    agent_a = await _agent(a["tenant_id"], "Agente A", {"llm": {"respond_model": ONLY_A}})
    await _bind(b["tenant_id"], "classify", ONLY_B)
    model_usage.invalidate()
    yield {"a": a, "b": b, "agent_a": agent_a}
    model_usage.invalidate()


async def test_each_client_is_read_under_its_own_guc(world, monkeypatch) -> None:
    scoped: list[uuid.UUID] = []
    real = tenant_scoped_session

    @asynccontextmanager
    async def spy(session, tenant_id, *args, **kwargs):  # type: ignore[no-untyped-def]
        scoped.append(uuid.UUID(str(tenant_id)))
        async with real(session, tenant_id, *args, **kwargs) as inner:
            yield inner

    monkeypatch.setattr(model_usage, "tenant_scoped_session", spy)
    usage = await model_usage.scan_usage()
    assert {world["a"]["tenant_id"], world["b"]["tenant_id"]} <= set(scoped), (
        "cada cliente se lee bajo su GUC"
    )
    assert usage.get(ONLY_A) is not None and usage.get(ONLY_B) is not None


async def test_usage_is_attributed_to_its_own_client(world) -> None:
    usage = await model_usage.scan_usage()
    a_name, b_name = "Client A One", "Client B One"
    assert usage[ONLY_A].agents == 1
    assert usage[ONLY_A].clients == (a_name,), "el agente de A no aparece en B"
    assert usage[ONLY_B].agents == 0, "una asignación no es un agente"
    assert usage[ONLY_B].clients == (b_name,), "la asignación de B no aparece en A"


async def test_nothing_but_counts_and_client_names_leaves_the_scan(world) -> None:
    usage = await model_usage.scan_usage()
    fields = {f.name for f in dataclasses.fields(usage[ONLY_A])}
    assert fields == {"agents", "clients"}
    dumped = repr(usage)
    assert str(world["agent_a"]) not in dumped, "ni ids de agente"
    assert "Prompt secreto" not in dumped, "ni prompts"
    assert "respond_model" not in dumped, "ni políticas"
