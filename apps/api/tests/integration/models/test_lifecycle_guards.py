"""Spec 059 (requisitos 1.1 a 1.8; T009, T011 y T013) — nadie deja mudos a los
agentes desde el panel.

- **Guardas**: «Retirar» y «No disponible» se rechazan sobre un modelo en uso o si
  no se puede verificar qué usa el worker, sin tocar el estado ni la auditoría.
- **Vuelta atrás**: «Cancelar retirada» y «Volver a disponible».
- **Retirada detenida**: si llega la fecha con agentes que no tienen a dónde ir, ni
  se retira el modelo ni se mueven a «Automático» (que hoy no tiene modelo).

Contra la base de verdad, con despliegues de prueba (prefijo ``c59-``) que se
borran al acabar. Ninguna llamada a un modelo.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.platform_models import default_models
from nexus_worker.runtime import model_resolver

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.services import model_lifecycle, model_usage

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
FREE = "c59-a/free"
USED = "c59-b/used"
ACTOR = "operator:luis@auphere.com"
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


async def _deployment(key: str, *, status: str = "active") -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_profiles (provider, model_id, display_name, route, status, "
                "capabilities, supports_tools, price_input_per_mtok, price_output_per_mtok, "
                "quota_weight_input, quota_weight_cache_read, quota_weight_output) VALUES "
                "('c59', :k, :k, :k, :s, CAST(:caps AS jsonb), true, 1, 5, 0.22, 0.022, 1.1)"
            ),
            {"k": key, "s": status, "caps": json.dumps({"tools": True, "tier": "basic"})},
        )


async def _status(key: str) -> tuple[str, str | None]:
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT status, status_before_unavailable FROM model_profiles "
                    "WHERE model_id = :k"
                ),
                {"k": key},
            )
        ).one()
        return str(row[0]), row[1]


async def _audit(action: str, key: str) -> list[dict[str, Any]]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            sa.text(
                "SELECT actor, before_json, after_json FROM audit_log "
                "WHERE action = :a AND target = :t "
                "ORDER BY created_at"
            ),
            {"a": action, "t": f"deployment:{key}"},
        )
        return [{"actor": a, "before": b, "after": c} for a, b, c in rows.all()]


async def _agent(tenant_id: uuid.UUID, name: str, policies: dict[str, Any]) -> uuid.UUID:
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
        return agent_id


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Any]:
    client = fakeredis.aioredis.FakeRedis()
    await client.set(
        "nexus:health:nexus-worker:host-1",
        json.dumps({"v": 1, "models": default_models()}),
        ex=60,
    )
    model_usage.invalidate()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def catalog() -> AsyncIterator[None]:
    await _deployment(FREE)
    await _deployment(USED)
    model_resolver.invalidate_catalog()
    try:
        yield
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c59-%'"))
        model_resolver.invalidate_catalog()
        respond_catalog.reset()
        model_usage.invalidate()


# ── guardas (1.1 a 1.4) ────────────────────────────────────────────────────


async def test_the_respond_model_cannot_be_made_unavailable(catalog, redis) -> None:
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.mark_unavailable(SOL, actor=ACTOR, reason="prueba", redis=redis)
    assert caught.value.code == "model_in_use"
    assert "respond" in caught.value.uses.defaults
    assert (await _status(SOL))[0] == "active"
    assert await _audit("deployment.unavailable", SOL) == []


async def test_the_respond_model_cannot_be_retired(catalog, redis) -> None:
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.announce_retirement(
            SOL, retire_after=NOW + timedelta(days=40), actor=ACTOR, now=NOW, redis=redis
        )
    assert caught.value.code == "model_in_use"
    assert (await _status(SOL))[0] == "active"


async def test_a_model_an_agent_responds_with_cannot_be_retired(
    console_world, catalog, redis
) -> None:
    await _agent(console_world["a"]["tenant_id"], "Ventas", {"llm": {"respond_model": USED}})
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.announce_retirement(
            USED, retire_after=NOW + timedelta(days=40), actor=ACTOR, now=NOW, redis=redis
        )
    assert caught.value.code == "model_in_use"
    assert caught.value.uses.agents == 1
    assert caught.value.uses.clients == ("Client A One",)
    assert (await _status(USED))[0] == "active"


async def test_without_verifying_the_worker_nothing_is_retired(catalog) -> None:
    empty = fakeredis.aioredis.FakeRedis()
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.mark_unavailable(FREE, actor=ACTOR, reason="prueba", redis=empty)
    assert caught.value.code == "defaults_unverified"
    assert caught.value.uses.problem == "no_heartbeat"
    assert (await _status(FREE))[0] == "active"


async def test_a_free_model_is_made_unavailable_and_remembers_its_status(catalog, redis) -> None:
    before = await model_lifecycle.mark_unavailable(
        FREE, actor=ACTOR, reason="contrato vencido", redis=redis
    )
    assert before == "active"
    assert await _status(FREE) == ("unavailable", "active")
    [row] = await _audit("deployment.unavailable", FREE)
    assert row["actor"] == ACTOR


async def test_a_free_model_is_retired_as_today(catalog, redis) -> None:
    proposals = await model_lifecycle.announce_retirement(
        FREE, retire_after=NOW + timedelta(days=40), actor=ACTOR, now=NOW, redis=redis
    )
    assert proposals == []
    assert (await _status(FREE))[0] == "retiring"


# ── vuelta atrás (1.6 y 1.7) ───────────────────────────────────────────────


async def test_cancelling_a_retirement_brings_it_back(catalog, redis) -> None:
    await model_lifecycle.announce_retirement(
        FREE, retire_after=NOW + timedelta(days=40), actor=ACTOR, now=NOW, redis=redis
    )
    await model_lifecycle.cancel_retirement(FREE, actor=ACTOR, reason="me equivoqué")
    async with get_sessionmaker()() as session:
        status, retire_after = (
            await session.execute(
                sa.text("SELECT status, retire_after FROM model_profiles WHERE model_id = :k"),
                {"k": FREE},
            )
        ).one()
    assert (status, retire_after) == ("active", None)
    [row] = await _audit("deployment.retirement_cancelled", FREE)
    assert row["actor"] == ACTOR and row["after"]["reason"] == "me equivoqué"


async def test_cancelling_needs_a_retiring_model(catalog) -> None:
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.cancel_retirement(FREE, actor=ACTOR, reason="x")
    assert caught.value.code == "not_retiring"


async def test_restoring_returns_to_the_status_it_had(catalog, redis) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text("UPDATE model_profiles SET status = 'draft' WHERE model_id = :k"), {"k": FREE}
        )
    await model_lifecycle.mark_unavailable(FREE, actor=ACTOR, reason="x", redis=redis)
    restored = await model_lifecycle.restore_available(FREE, actor=ACTOR, reason="ya vale")
    assert restored == "draft", "vuelve a borrador, no a activo"
    assert await _status(FREE) == ("draft", None)
    [row] = await _audit("deployment.restored", FREE)
    assert row["after"] == {"status": "draft", "reason": "ya vale"}


async def test_restoring_a_model_marked_before_this_spec_reads_the_audit(catalog) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text("UPDATE model_profiles SET status = 'unavailable' WHERE model_id = :k"),
            {"k": FREE},
        )
        await session.execute(
            sa.text(
                "INSERT INTO audit_log (actor, action, target, before_json, after_json) VALUES "
                "(:a, 'deployment.unavailable', :t, CAST(:b AS jsonb), CAST(:c AS jsonb))"
            ),
            {
                "a": ACTOR,
                "t": f"deployment:{FREE}",
                "b": json.dumps({"status": "active"}),
                "c": json.dumps({"status": "unavailable"}),
            },
        )
    assert await model_lifecycle.restore_available(FREE, actor=ACTOR, reason="x") == "active"


async def test_restoring_without_any_trace_goes_to_draft(catalog) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text("UPDATE model_profiles SET status = 'unavailable' WHERE model_id = :k"),
            {"k": USED},
        )
    assert await model_lifecycle.restore_available(USED, actor=ACTOR, reason="x") == "draft"


async def test_restoring_needs_an_unavailable_model(catalog) -> None:
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.restore_available(FREE, actor=ACTOR, reason="x")
    assert caught.value.code == "not_unavailable"


# ── retirada detenida (1.8) ────────────────────────────────────────────────


async def _retiring_since_before_this_spec(key: str) -> None:
    """Un modelo que ya estaba en retirada antes de las guardas, con la fecha pasada."""
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = 'retiring', retire_after = :d "
                "WHERE model_id = :k"
            ),
            {"k": key, "d": NOW - timedelta(hours=1)},
        )


async def test_a_retirement_with_trapped_agents_is_held(console_world, catalog) -> None:
    tenant = console_world["a"]["tenant_id"]
    agent = await _agent(tenant, "Ventas", {"llm": {"respond_model": USED}})
    await _retiring_since_before_this_spec(USED)

    report = await model_lifecycle.run_lifecycle(now=NOW)
    assert report.retired == [] and report.moved_agents == 0
    assert report.blocked == {USED: 1}
    assert (await _status(USED))[0] == "retiring", "ni se retira"
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant):
        versions = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(AgentConfig)
                .where(AgentConfig.agent_id == agent)
            )
        ).scalar_one()
    assert versions == 1, "ni se mueve el agente a «Automático»"
    [row] = await _audit("deployment.retirement_blocked", USED)
    assert row["after"]["agents"] == 1

    await model_lifecycle.run_lifecycle(now=NOW + timedelta(hours=1))
    assert len(await _audit("deployment.retirement_blocked", USED)) == 1, "una vez al día"
    await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=1))
    assert len(await _audit("deployment.retirement_blocked", USED)) == 2


async def test_the_blocked_count_reaches_the_catalog(console_world, catalog) -> None:
    await _agent(console_world["a"]["tenant_id"], "Ventas", {"llm": {"respond_model": USED}})
    await _retiring_since_before_this_spec(USED)
    assert await model_lifecycle.blocked_retirements(now=NOW) == {USED: 1}


async def test_a_retirement_without_agents_still_happens(catalog) -> None:
    await _retiring_since_before_this_spec(FREE)
    report = await model_lifecycle.run_lifecycle(now=NOW)
    assert report.retired == [FREE]
    assert (await _status(FREE))[0] == "retired"
