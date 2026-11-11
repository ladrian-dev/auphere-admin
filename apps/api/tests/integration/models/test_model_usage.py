"""Spec 059 (requisitos 1.1, 1.2 y 1.5; T007) — ¿está en uso un modelo?

Un modelo está en uso si la plataforma lo usa por defecto (el registro de
``nexus_worker.platform_models``), si responde con él algún agente activo o si algún
cliente lo tiene asignado en cualquier rol. Lo que usa el worker de verdad lo
publica su latido; si falta o no coincide, no se puede decir que algo no esté en
uso y la respuesta es «no verificado».
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.platform_models import default_models

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.services import model_usage

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
LUNA = "openai/gpt-5.6-luna"
GPT4O = "openai/gpt-4o"
HEARTBEAT = "nexus:health:nexus-worker:host-1"


async def _agent(tenant_id: uuid.UUID, policies: dict[str, Any], name: str = "Agente") -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent_id = uuid.uuid4()
        await session.execute(
            sa.text("INSERT INTO agents (id, tenant_id, name) VALUES (:a, :t, :n)"),
            {"a": agent_id, "t": tenant_id, "n": name},
        )
        version = (
            await session.execute(sa.select(sa.func.coalesce(sa.func.max(AgentConfig.version), 0)))
        ).scalar_one() + 1
        session.add(
            AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent_id,
                version=version,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="x",
                channels=[],
                tools=[],
                policies=policies,
                seed_template_ref=None,
            )
        )


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
async def redis() -> AsyncIterator[Any]:
    client = fakeredis.aioredis.FakeRedis()
    model_usage.invalidate()
    yield client
    model_usage.invalidate()
    await client.aclose()


async def _publish(redis: Any, models: dict[str, str] | None, *, key: str = HEARTBEAT) -> None:
    value = "1" if models is None else json.dumps({"v": 1, "models": models})
    await redis.set(key, value, ex=60)


# ── usos por defecto (1.1) ─────────────────────────────────────────────────


async def test_the_respond_model_is_in_use_by_default(redis) -> None:
    await _publish(redis, default_models())
    uses = await model_usage.uses_of(SOL, redis=redis)
    assert uses.verified and uses.problem is None
    assert {"respond", "respond_fallback", "companion"} <= set(uses.defaults)
    assert uses.in_use


async def test_a_model_nobody_uses_is_free(redis) -> None:
    await _publish(redis, default_models())
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert uses.defaults == () and uses.agents == 0 and uses.clients == ()
    assert uses.verified and not uses.in_use


# ── agentes y asignaciones (1.2) ───────────────────────────────────────────


async def test_an_agent_that_chose_the_model_puts_it_in_use(console_world, redis) -> None:
    await _publish(redis, default_models())
    await _agent(console_world["a"]["tenant_id"], {"llm": {"respond_model": LUNA}})
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert uses.agents == 1 and uses.clients == ("Client A One",)


async def test_a_respond_binding_moves_every_agent_of_the_client(console_world, redis) -> None:
    await _publish(redis, default_models())
    tenant = console_world["b"]["tenant_id"]
    await _agent(tenant, {}, "Reservas")
    await _agent(tenant, {}, "Ventas")
    await _bind(tenant, "respond", LUNA)
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert uses.agents == 2 and uses.clients == ("Client B One",)


async def test_a_binding_in_any_role_puts_the_model_in_use(console_world, redis) -> None:
    await _publish(redis, default_models())
    await _bind(console_world["a"]["tenant_id"], "classify", GPT4O)
    uses = await model_usage.uses_of(GPT4O, redis=redis)
    assert uses.clients == ("Client A One",) and uses.in_use


# ── lo que publica el worker (1.5) ─────────────────────────────────────────


async def test_without_a_heartbeat_nothing_is_verified(redis) -> None:
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert not uses.verified and uses.problem == "no_heartbeat"


async def test_an_old_worker_that_writes_1_is_unpublished(redis) -> None:
    await _publish(redis, default_models())
    await _publish(redis, None, key="nexus:health:nexus-worker:old-host")
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert not uses.verified and uses.problem == "unpublished"


async def test_a_worker_with_another_model_is_a_mismatch_and_still_protects_it(redis) -> None:
    published = {**default_models(), "respond": LUNA}
    await _publish(redis, published)
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert not uses.verified and uses.problem == "mismatch"
    assert "respond" in uses.defaults, "lo que publica el worker también protege"


async def test_unrelated_keys_are_not_heartbeats(redis) -> None:
    await _publish(redis, default_models())
    await redis.set("nexus:health-check:other", "x")
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert uses.verified


async def test_only_the_worker_keys_must_match(redis) -> None:
    """Research D2: el worker publica todo el registro, pero las claves que
    resuelve la API (companion, visión, evaluaciones…) las decide el entorno de la
    API. Que el worker las vea distintas no es un desacuerdo; lo publicado sigue
    protegiendo."""
    published = {**default_models(), "companion": LUNA, "vision": GPT4O}
    await _publish(redis, published)
    uses = await model_usage.uses_of(LUNA, redis=redis)
    assert uses.verified and uses.problem is None
    assert "companion" in uses.defaults, "lo publicado también protege"


async def test_two_workers_that_disagree_on_a_worker_key_are_a_mismatch(redis) -> None:
    await _publish(redis, default_models())
    await _publish(
        redis, {**default_models(), "classify": LUNA}, key="nexus:health:nexus-worker:host-2"
    )
    uses = await model_usage.uses_of(GPT4O, redis=redis)
    assert not uses.verified and uses.problem == "mismatch"
