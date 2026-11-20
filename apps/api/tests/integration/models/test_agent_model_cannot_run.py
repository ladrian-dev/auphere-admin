"""Spec 065, T054 (requisito 4.8): el modelo elegido deja de poder ejecutar el agente.

Un agente elige un modelo de OpenAI y después empieza a usar Skills de Anthropic, que OpenAI
no ejecuta. El turno responde con el siguiente origen que pueda (``resolve()``; el worker lo
prueba en ``apps/worker/tests/unit/test_respond_fallback_mid_turn.py``, con su reserva de
Anthropic), la elección se conserva y el ``GET`` de la consola lo avisa con
``notice = "chosen_model_cannot_run_agent"`` (contracts/api.md).
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
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TERRA = "openai/gpt-5.6-terra"
OPUS = "anthropic/claude-opus-5-5"
SONNET = "anthropic/claude-sonnet-5-5"


@pytest_asyncio.fixture(autouse=True)
async def _catalog() -> AsyncIterator[None]:
    async with get_sessionmaker()() as session:
        await respond_catalog.refresh_from_db(session)
    yield
    respond_catalog.reset()


async def _agent(tenant_id: uuid.UUID, *, version_model: str | None = None) -> uuid.UUID:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent = Agent(tenant_id=tenant_id, name="Recepción")
        session.add(agent)
        await session.flush()
        policies: dict[str, Any] = {}
        if version_model:
            policies["llm"] = {"respond_model": version_model}
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
                runtime_skills=[],
                created_by="test",
            )
        )
        await session.commit()
        return agent.id


async def _start_using_skills(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.update(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE)
            .values(runtime_skills=[{"skill_id": "pdf", "version": "1"}])
        )
        await session.commit()


def _url(ref: str, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{ref}/agents/{agent_id}/model"


async def _enable(model_id: str, on: bool) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET respond_enabled_at = CASE WHEN :on THEN now() END, "
                "respond_enabled_by = CASE WHEN :on THEN 'test' END WHERE model_id = :m"
            ),
            {"m": model_id, "on": on},
        )
    async with get_sessionmaker()() as session:
        await respond_catalog.refresh_from_db(session)


@pytest.mark.parametrize(
    ("version_model", "sonnet_enabled", "effective", "source"),
    [
        (None, True, SONNET, "platform"),
        # /cso 2026-11-20 (T093): sin Sonnet 5.5 habilitada en el entorno, el modelo por
        # defecto, como hoy, y no uno que no pasó la batería.
        (None, False, "openai/gpt-5.6-sol", "platform"),
        (OPUS, False, OPUS, "version"),
    ],
    ids=[
        "sin_version_reserva_habilitada",
        "sin_version_reserva_sin_habilitar",
        "la_version_de_anthropic",
    ],
)
async def test_a_choice_the_agent_can_no_longer_run_is_kept_and_said(
    client: Any,
    console_world: Any,
    version_model: str | None,
    sonnet_enabled: bool,
    effective: str,
    source: str,
) -> None:
    await _enable(SONNET, sonnet_enabled)
    a = console_world["a"]
    agent = await _agent(a["tenant_id"], version_model=version_model)
    chosen = await client.put(
        _url(a["ref"], agent), headers=a["headers"](), json={"model_id": TERRA}
    )
    assert chosen.status_code == 200, chosen.text
    before = (await client.get(_url(a["ref"], agent), headers=a["headers"]())).json()
    assert before["notice"] is None
    assert before["effective"]["model_id"] == TERRA

    await _start_using_skills(a["tenant_id"], agent)

    body = (await client.get(_url(a["ref"], agent), headers=a["headers"]())).json()
    assert body["notice"] == "chosen_model_cannot_run_agent"
    assert body["choice"]["model_id"] == TERRA, "la elección no se borra"
    assert body["effective"]["model_id"] == effective
    assert body["effective"]["source"] == source
    assert all(o["provider"] == "anthropic" for o in body["options"]), "OpenAI ni se ofrece"
    await _enable(SONNET, False)
