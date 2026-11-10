"""QA de staging del 2026-11-08: en un agente de instrucciones libres (``spec.mode ==
"instructions"``), los interruptores de Habilidades escribían ``draft.tools`` y no la spec.
La ficha y la revisión leían la spec («12 habilidades», «prometen cambiar o cancelar citas y
no tiene herramienta») y la siguiente edición de la spec, que manda ``spec.tools``, borraba
sin avisar lo que se había encendido."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus
from tests.conftest import make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SPEC: dict[str, Any] = {
    "schema_version": "1",
    "mode": "instructions",
    "identity": {"name": "Ana", "description": "Da citas por WhatsApp."},
    "instructions": {"legacy_text": "Da citas en la agenda del negocio."},
    "tools": ["reservas.services", "reservas.find_slots", "reservas.create"],
    "ai_disclosure": {"decided": False},
    "model_policy": {"kind": "profile", "profile": "auto"},
    "memory": {"scope": "shared"},
}


async def _agent(db_session: Any, w: dict[str, Any]) -> uuid.UUID:
    tenant_id = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tenant_id)
    agent = Agent(tenant_id=tenant_id, name="Ana")
    db_session.add(agent)
    await db_session.flush()
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Da citas en la agenda del negocio.",
            channels=[],
            tools=list(SPEC["tools"]),
            policies={},
            spec=SPEC,
            created_by="test",
        )
    )
    await db_session.commit()
    return agent.id


async def _switch_on(client: Any, w: dict[str, Any], agent_id: uuid.UUID, key: str) -> None:
    r = await client.put(
        f"/console/clients/{w['ref']}/capabilities?agent={agent_id}",
        headers=w["headers"](),
        json={"key": key, "kind": "tool", "enabled": True},
    )
    assert r.status_code == 200, r.text


async def test_a_switched_on_skill_is_in_the_spec_the_console_reads(
    client, console_world, db_session
) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w)
    await _switch_on(client, w, agent_id, "reservas.cancel")

    url = f"/console/clients/{w['ref']}/agents/{agent_id}/draft"
    got = await client.get(url, headers=w["headers"]())
    assert got.status_code == 200, got.text
    assert "reservas.cancel" in got.json()["spec"]["tools"]


async def test_editing_the_instructions_keeps_the_skills_switched_on(
    client, console_world, db_session
) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w)
    await _switch_on(client, w, agent_id, "reservas.cancel")

    url = f"/console/clients/{w['ref']}/agents/{agent_id}/draft"
    draft = (await client.get(url, headers=w["headers"]())).json()
    spec = draft["spec"]
    spec["instructions"] = {"legacy_text": "Da, mueve y cancela citas en la agenda."}
    saved = await client.patch(
        url,
        json={"spec": spec},
        headers={**w["headers"](), "If-Match": f'"{draft["revision"]}"'},
    )
    assert saved.status_code == 200, saved.text

    staged = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
        )
    )
    await db_session.refresh(staged)
    assert staged is not None
    assert "reservas.cancel" in (staged.tools or []), staged.tools
