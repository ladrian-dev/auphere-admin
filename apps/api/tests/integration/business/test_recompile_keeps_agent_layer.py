"""Bug «la ficha borra lo que sabe el agente» (2026-10-29; requisitos 8.4, 16.2 y 22).

Guardar algo en la ficha recompila la versión activa de cada agente. Con un
AgentSpec, el prompt es «cuerpo + ficha + capa del agente», y la recompilación
cortaba en la marca de la ficha: el agente perdía sus preguntas frecuentes
propias sin que nadie lo tocara. Ahora la versión se recompila desde su
AgentSpec, igual que al escribir el borrador.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AgentConfig
from nexus_api.services.agent_spec.compiler import compile_spec
from nexus_api.services.agent_spec.schema import AgentSpec
from nexus_api.services.business.compilation import compile_prompt, load_facts

from ._business_world import SPLIT_WEEK, Biz, active_prompt, biz, seed_agent, write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

__all__ = ["biz"]

SPEC: dict[str, Any] = {
    "schema_version": "1",
    "mode": "structured",
    "identity": {"name": "Ventas", "description": "Atiende pedidos mayoristas de la floristería."},
    "voice": {"languages": ["es"]},
    "instructions": {"sections": [{"title": "Qué haces", "body": "Prepara presupuestos."}]},
    "services": {"mode": "all", "faqs": [{"q": "¿Pedido mínimo?", "a": "50 ramos."}]},
    "escalation": {},
    "tools": [],
    "ai_disclosure": {"decided": False},
    "model_policy": {"kind": "pinned", "deployment": "nexus/current-binding"},
    "memory": {"scope": "shared"},
}


async def _structured_agent(db_session: AsyncSession, biz: Biz) -> Any:
    spec = AgentSpec.model_validate(SPEC)
    agent_id, cfg_id = await seed_agent(db_session, biz.tenant_id, name="Ventas", prompt="x")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = await db_session.get(Agent, agent_id)
        assert agent is not None
        cfg = await db_session.get(AgentConfig, cfg_id)
        assert cfg is not None
        cfg.spec = SPEC
        cfg.system_prompt_rendered = compile_spec(spec, await load_facts(db_session, agent))
        await db_session.flush()
    return agent_id, cfg_id


async def test_a_ficha_write_keeps_the_agent_own_faqs(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    _agent_id, cfg_id = await _structured_agent(db_session, biz)
    assert "Pedido mínimo" in await active_prompt(db_session, biz.tenant_id, cfg_id)

    await write(client, biz, "PUT", "/hours", {"layout": "blocks", "days": SPLIT_WEEK}, revision=0)

    after = await active_prompt(db_session, biz.tenant_id, cfg_id)
    assert "Pedido mínimo" in after, "the agent's own layer survives a ficha write"
    assert "09:00" in after, "and the ficha block did change"


async def test_the_recompiled_prompt_is_the_one_the_draft_writer_gives(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id, cfg_id = await _structured_agent(db_session, biz)

    await write(client, biz, "PUT", "/hours", {"layout": "blocks", "days": SPLIT_WEEK}, revision=0)

    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = await db_session.scalar(
            sa.select(Agent).where(Agent.id == agent_id).execution_options(populate_existing=True)
        )
        assert agent is not None
        expected = compile_spec(AgentSpec.model_validate(SPEC), await load_facts(db_session, agent))
    assert await active_prompt(db_session, biz.tenant_id, cfg_id) == expected


async def test_a_version_without_agent_spec_compiles_as_today(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    instructions = "Eres Sofía, de Barbería Cultor."
    agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt=instructions
    )

    await write(client, biz, "PUT", "/hours", {"layout": "blocks", "days": SPLIT_WEEK}, revision=0)

    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = await db_session.get(Agent, agent_id)
        assert agent is not None
        expected = compile_prompt(instructions, await load_facts(db_session, agent))
    assert await active_prompt(db_session, biz.tenant_id, cfg_id) == expected
