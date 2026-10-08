"""Spec 030 T092 — versiones por agente (iteración 3, R14.1).

Un cliente puede tener varios agentes; cada uno tiene **su** versión activa.
Lo que fija este archivo, sobre el repositorio real y la RLS del tenant:

- promover o revertir una versión de un agente **no toca** la activa de otro
  (hasta la spec 030 el «archivar la activa» era del tenant entero: publicar el
  agente B dejaba mudo al A);
- ``get_active()`` sin agente es la del **agente principal** (el activo más
  antiguo) — así los llamantes de hoy siguen viendo lo mismo;
- los números de versión siguen siendo únicos por cliente (decisión de
  data-model.md): las búsquedas por ``(tenant, versión)`` no se vuelven ambiguas;
- la base no admite dos versiones activas del mismo agente;
- una versión insertada sin agente (escritores de antes de la spec 030) cae en
  el agente principal, que se crea si no existe.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus
from nexus_api.repositories.agent_config import AgentConfigRepository

pytestmark = pytest.mark.asyncio


def _config(
    tenant_id: uuid.UUID, version: int, status: AgentConfigStatus, **kw: Any
) -> AgentConfig:
    return AgentConfig(
        tenant_id=tenant_id,
        version=version,
        status=status,
        system_prompt_rendered=f"prompt v{version}",
        tools=[],
        channels=[],
        policies={},
        created_by="test",
        **kw,
    )


async def _two_agents(tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Agente A (principal, v1 activa) y agente B (v2 activa, v3 en borrador)."""
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
            s.add_all(
                [
                    _config(tenant_id, 1, AgentConfigStatus.ACTIVE, agent_id=a.id),
                    _config(tenant_id, 2, AgentConfigStatus.ACTIVE, agent_id=b.id),
                    _config(tenant_id, 3, AgentConfigStatus.STAGED, agent_id=b.id),
                ]
            )
            return a.id, b.id


async def _status(tenant_id: uuid.UUID) -> dict[int, str]:
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            rows = (await s.execute(sa.select(AgentConfig.version, AgentConfig.status))).all()
            return {v: st.value for v, st in rows}


async def test_promoting_one_agent_leaves_the_other_alone(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    _a, b = await _two_agents(tenant_id)
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            promoted = await AgentConfigRepository(s).promote(3, promoted_by="test")
            assert promoted.agent_id == b
    assert await _status(tenant_id) == {1: "active", 2: "archived", 3: "active"}

    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            await AgentConfigRepository(s).rollback(2, promoted_by="test")
    assert await _status(tenant_id) == {1: "active", 2: "active", 3: "archived"}


async def test_without_an_agent_the_principal_answers(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    a, b = await _two_agents(tenant_id)
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            repo = AgentConfigRepository(s)
            assert (await repo.get_active()).version == 1
            assert (await repo.get_active(agent_id=b)).version == 2
            assert (await repo.principal_agent_id()) == a
            assert [c.version for c in await repo.list_all(agent_id=b)] == [3, 2]


async def test_versions_keep_counting_per_client(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    _a, b = await _two_agents(tenant_id)
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            draft = await AgentConfigRepository(s).create_staged(
                system_prompt_rendered="x",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by="test",
                agent_id=b,
            )
            assert draft.version == 4
            assert draft.agent_id == b


async def test_the_database_refuses_two_active_versions_of_one_agent(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    a, _b = await _two_agents(tenant_id)
    with pytest.raises(IntegrityError), tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            s.add(_config(tenant_id, 9, AgentConfigStatus.ACTIVE, agent_id=a))
            await s.flush()


async def test_a_version_written_without_an_agent_lands_on_the_principal(console_world) -> None:
    """The writers from before spec 030 (provisioning, scripts, tests) do not
    know about agents. The database gives their row the principal agent —
    creating it the first time — so no version is ever left without one."""
    tenant_id = console_world["b"]["tenant_id"]
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            s.add(_config(tenant_id, 1, AgentConfigStatus.ACTIVE))
            await s.flush()
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            agents = (await s.execute(sa.select(Agent))).scalars().all()
            assert [ag.name for ag in agents] == ["Agente principal"]
            (cfg,) = (await s.execute(sa.select(AgentConfig))).scalars().all()
            assert cfg.agent_id == agents[0].id
            # A second one joins the same principal, it does not create another.
            s.add(_config(tenant_id, 2, AgentConfigStatus.STAGED))
            await s.flush()
            assert len((await s.execute(sa.select(Agent))).scalars().all()) == 1
