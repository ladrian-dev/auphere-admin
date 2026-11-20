"""Garantía 1 sobre el modelo de cada agente — spec 065 (T010; requisitos 10.1 y 10.2).

La elección de modelo es un dato del cliente: vive en ``agents``, con RLS forzada, y solo se
lee y se escribe con el contexto del cliente que decide el servidor, nunca con un argumento
del llamante. Se prueba por sus costuras, intentando el cruce y mirando el dato del otro
lado:

- el partner A, con el ``ref`` de un cliente de B, recibe el 404 opaco, idéntico al de un
  ``ref`` que no existe, al leer y al cambiar el modelo de un agente de B, y en B no cambia
  nada ni queda auditoría;
- el partner A, con su propio ``ref`` y el ``agent_id`` de un agente de B, tampoco: el agente
  se busca dentro del cliente de la ruta;
- una sesión con la GUC de A no ve las columnas de modelo de los agentes de B;
- un cuerpo con ``tenant_id`` o ``agent_id`` no pasa (``extra="forbid"``).

El ``PUT`` del panel (solo toca agentes del ``tenant_id`` de la ruta) se prueba con su
endpoint, en ``test_agent_model_admin`` (T070).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AuditLog

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

TERRA = "openai/gpt-5.6-terra"


async def _agent(tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent = Agent(tenant_id=tenant_id, name=name)
        session.add(agent)
        await session.commit()
        return agent.id


async def _choice(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Any:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return (
            await session.execute(
                sa.select(Agent.respond_model_profile_id, Agent.respond_model_set_by).where(
                    Agent.id == agent_id
                )
            )
        ).one()


async def _audits(tenant_id: uuid.UUID) -> int:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "console.agent.model.update")
            )
            or 0
        )


def _url(ref: str, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{ref}/agents/{agent_id}/model"


async def test_another_partner_cannot_read_nor_change_an_agents_model(
    client, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    b_agent = await _agent(b["tenant_id"], "Recepción de B")
    before = await _choice(b["tenant_id"], b_agent)

    for method, payload in (("GET", None), ("PUT", {"model_id": TERRA})):
        foreign = await client.request(
            method, _url(b["ref"], b_agent), headers=a["headers"](), json=payload
        )
        missing = await client.request(
            method, _url("no-existe", b_agent), headers=a["headers"](), json=payload
        )
        assert foreign.status_code == 404, (method, foreign.text)
        assert foreign.json() == missing.json(), "el 404 no dice si el cliente existe"

    assert await _choice(b["tenant_id"], b_agent) == before
    assert await _audits(b["tenant_id"]) == 0


async def test_an_agent_of_another_client_is_not_found_inside_my_client(
    client, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    b_agent = await _agent(b["tenant_id"], "Recepción de B")
    for method, payload in (("GET", None), ("PUT", {"model_id": TERRA})):
        resp = await client.request(
            method, _url(a["ref"], b_agent), headers=a["headers"](), json=payload
        )
        assert resp.status_code == 404, (method, resp.text)
    assert (await _choice(b["tenant_id"], b_agent))[0] is None


async def test_the_body_cannot_carry_whose_agent_it_is(client, console_world) -> None:
    a = console_world["a"]
    a_agent = await _agent(a["tenant_id"], "Recepción de A")
    for extra in ({"tenant_id": str(uuid.uuid4())}, {"agent_id": str(uuid.uuid4())}):
        resp = await client.put(
            _url(a["ref"], a_agent), headers=a["headers"](), json={"model_id": TERRA, **extra}
        )
        assert resp.status_code == 422, resp.text


async def test_a_session_of_one_client_does_not_see_the_model_of_anothers_agents(
    console_world,
) -> None:
    a, b = console_world["a"], console_world["b"]
    b_agent = await _agent(b["tenant_id"], "Recepción de B")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        seen = (
            await session.execute(
                sa.select(Agent.id, Agent.respond_model_profile_id).where(Agent.id == b_agent)
            )
        ).all()
    assert seen == []
