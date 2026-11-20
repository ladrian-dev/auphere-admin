"""Spec 065, T020: el partner elige el modelo de un agente desde la consola.

``GET/PUT /console/clients/{ref}/agents/{agent_id}/model`` (contracts/api.md):

- el ``GET`` dice qué modelo eligió el agente (o ninguno), con cuál responde y de dónde
  sale, y qué puede elegir: lo activo ∩ habilitado ∩ con perfil ∩ lista del partner, del
  más barato al más caro, sin los que el agente no pueda ejecutar;
- el ``PUT`` escribe la elección del agente (``set_by = 'partner'``), deja auditoría con el
  antes y el después y avisa al worker para ese agente; no publica versión ni lanza pruebas;
- lo que no está en la oferta es ``422 unknown_model``; lo que el agente no puede ejecutar,
  ``422 model_unavailable_for_agent``; sin ``agents:write``, ``403``.

Requisitos 1.2, 1.5, 2.3, 2.4, 2.5, 2.6, 2.7, 6.2 y 9.1.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, AuditLog, Job
from nexus_api.services.business.writes import drain_after_commit

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
SONNET = "anthropic/claude-sonnet-5-5"


@pytest_asyncio.fixture(autouse=True)
async def _catalog() -> AsyncIterator[None]:
    """El catálogo se lee de la base, como al arrancar; vuelve a la semilla al acabar."""
    async with get_sessionmaker()() as session:
        await respond_catalog.refresh_from_db(session)
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET respond_enabled_at = NULL, respond_enabled_by = NULL "
                "WHERE model_id LIKE 'anthropic/%'"
            )
        )
    respond_catalog.reset()


async def agent_of(
    tenant_id: uuid.UUID,
    name: str = "Recepción",
    *,
    skills: bool = False,
    respond_model: str | None = None,
) -> uuid.UUID:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent = Agent(tenant_id=tenant_id, name=name)
        session.add(agent)
        await session.flush()
        policies: dict[str, Any] = {}
        if respond_model:
            policies["llm"] = {"respond_model": respond_model}
        session.add(
            AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=int(uuid.uuid4().int % 100000) + 1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Eres la recepción.",
                channels=[],
                tools=["escalate.escalate_to_human"],
                policies=policies,
                runtime_skills=[{"skill_id": "pdf"}] if skills else [],
                created_by="test",
            )
        )
        await session.commit()
        return agent.id


async def choice_of(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> tuple[Any, ...]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                sa.text(
                    "SELECT p.model_id, a.respond_model_set_by, a.respond_model_set_at "
                    "FROM agents a LEFT JOIN model_profiles p "
                    "ON p.id = a.respond_model_profile_id WHERE a.id = :a"
                ),
                {"a": agent_id},
            )
        ).one()
        return tuple(row)


async def enable(model_id: str) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET respond_enabled_at = now(), "
                "respond_enabled_by = 'test' WHERE model_id = :m"
            ),
            {"m": model_id},
        )
    async with get_sessionmaker()() as session:
        await respond_catalog.refresh_from_db(session)


def url(ref: str, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{ref}/agents/{agent_id}/model"


async def test_an_agent_without_a_choice_answers_with_auphere_default(
    client, console_world
) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    resp = await client.get(url(a["ref"], agent), headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_id"] == str(agent)
    assert body["choice"] is None
    assert body["effective"]["model_id"] == SOL
    assert body["effective"]["source"] == "platform"
    assert body["effective"]["outside_offer"] is None
    assert body["effective"]["estimate"]["basis"] in {"agent_7d", "nominal"}
    assert body["notice"] is None
    assert body["can_change"] is True
    options = [o["model_id"] for o in body["options"]]
    assert set(options) == {SOL, TERRA, LUNA}, "Claude no se ofrece sin habilitar"
    prices = [o["estimate"]["amount_micros"] for o in body["options"]]
    assert prices == sorted(prices), "del más barato al más caro"
    for option in body["options"]:
        assert option["provider"] == "openai"
        assert option["line"] in {"max", "balanced", "economy"}


async def test_choosing_a_model_writes_the_agent_audits_and_tells_the_worker(
    client, console_world, fake_redis, monkeypatch
) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    other = await agent_of(a["tenant_id"], "Ventas")
    published: list[tuple[str, str]] = []
    real = fake_redis.publish

    async def spy(channel: str, message: str) -> Any:
        published.append((channel, message))
        return await real(channel, message)

    monkeypatch.setattr(fake_redis, "publish", spy)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        versions_before = await session.scalar(sa.select(sa.func.count()).select_from(AgentConfig))
        jobs_before = await session.scalar(sa.select(sa.func.count()).select_from(Job))

    resp = await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": TERRA})
    assert resp.status_code == 200, resp.text
    await drain_after_commit()
    body = resp.json()
    assert body["choice"]["model_id"] == TERRA
    assert body["choice"]["set_by"] == "partner"
    assert body["effective"] == {**body["effective"], "model_id": TERRA, "source": "agent"}

    model_id, set_by, set_at = await choice_of(a["tenant_id"], agent)
    assert (model_id, set_by) == (TERRA, "partner") and set_at is not None
    assert (await choice_of(a["tenant_id"], other))[0] is None, "los demás agentes no cambian"
    assert any(msg == f"{a['tenant_id']}:{agent}" for _, msg in published), published

    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        audit = (
            await session.execute(
                sa.select(AuditLog).where(AuditLog.action == "console.agent.model.update")
            )
        ).scalar_one()
        assert audit.target == f"agent:{agent}"
        assert audit.before_json == {"model_id": None}
        assert audit.after_json["model_id"] == TERRA
        assert await session.scalar(sa.select(sa.func.count()).select_from(AgentConfig)) == (
            versions_before
        ), "no publica versión"
        assert await session.scalar(sa.select(sa.func.count()).select_from(Job)) == jobs_before, (
            "no lanza pruebas"
        )


async def test_null_goes_back_to_the_default(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": LUNA})
    resp = await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["choice"] is None
    assert resp.json()["effective"]["model_id"] == SOL
    assert (await choice_of(a["tenant_id"], agent))[:2] == (None, None)


@pytest.mark.parametrize(
    "model_id",
    [SONNET, "anthropic/claude-sonnet-4-6", "openai/gpt-4o", "prov/no-existe"],
)
async def test_what_is_not_offered_is_unknown(client, console_world, model_id: str) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    resp = await client.put(
        url(a["ref"], agent), headers=a["headers"](), json={"model_id": model_id}
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_model"
    assert (await choice_of(a["tenant_id"], agent))[0] is None


async def test_a_model_outside_the_partners_list_is_unknown(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    put = await client.put(
        f"/admin/partners/{a['partner_id']}/models",
        headers=admin_headers,
        json={"model_ids": [SOL, LUNA]},
    )
    assert put.status_code == 200, put.text
    got = await client.get(url(a["ref"], agent), headers=a["headers"]())
    assert {o["model_id"] for o in got.json()["options"]} == {SOL, LUNA}
    resp = await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": TERRA})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "unknown_model"


async def test_an_enabled_claude_is_offered(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    await enable(SONNET)
    got = await client.get(url(a["ref"], agent), headers=a["headers"]())
    sonnet = next(o for o in got.json()["options"] if o["model_id"] == SONNET)
    assert sonnet["provider"] == "anthropic" and sonnet["line"] == "balanced"
    resp = await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": SONNET})
    assert resp.status_code == 200, resp.text


async def test_a_model_the_agent_cannot_run_is_not_offered_nor_accepted(
    client, console_world
) -> None:
    """Requisito 4.8: con Skills, solo Claude; los de OpenAI ni aparecen."""
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"], skills=True)
    await enable(SONNET)
    got = await client.get(url(a["ref"], agent), headers=a["headers"]())
    assert {o["model_id"] for o in got.json()["options"]} == {SONNET}
    resp = await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": TERRA})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "model_unavailable_for_agent"


async def test_the_version_override_is_the_second_step(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"], respond_model=LUNA)
    got = (await client.get(url(a["ref"], agent), headers=a["headers"]())).json()
    assert got["effective"]["model_id"] == LUNA
    assert got["effective"]["source"] == "version"


async def test_read_only_can_see_but_not_change(client, console_world, db_session) -> None:
    from tests.conftest import add_console_member

    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    got = await client.get(url(a["ref"], agent), headers=analyst["headers"]())
    assert got.status_code == 200, got.text
    assert got.json()["can_change"] is False
    resp = await client.put(
        url(a["ref"], agent), headers=analyst["headers"](), json={"model_id": TERRA}
    )
    assert resp.status_code == 403


async def test_a_model_disabled_after_the_cache_was_read_is_refused(client, console_world) -> None:
    """/cso 2026-11-20 (T093): un proceso que aún no refrescó su catálogo tras
    ``respond-disable`` no deja elegir ese modelo: la escritura mira la base."""
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET respond_enabled_at = NULL, respond_enabled_by = NULL, "
                "respond_enabled_note = NULL WHERE model_id = :m"
            ),
            {"m": LUNA},
        )
    try:
        assert LUNA in {m for m, _ in respond_catalog.RESPOND_MODELS}, "la caché aún lo ofrece"
        resp = await client.put(
            url(a["ref"], agent), headers=a["headers"](), json={"model_id": LUNA}
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "unknown_model"
        assert (await choice_of(a["tenant_id"], agent))[0] is None
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(
                sa.text(
                    "UPDATE model_profiles SET respond_enabled_at = now(), "
                    "respond_enabled_by = 'migration:0238' WHERE model_id = :m"
                ),
                {"m": LUNA},
            )
