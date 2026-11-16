"""Garantía 1 y 9 (tocadas) — el agente de un hilo del Playground es de su cliente.

Fallo ``playground-del-panel-sin-agente``. Desde el arreglo, ``POST /qa/threads``
acepta un ``agent_id`` que llega del navegador, y ``qa.threads.agent_id`` no tiene
FK. Un hilo de antes del arreglo (``agent_id`` NULL) resuelve el principal con
``principal_agent_id``, que no filtra por cliente: se apoya en la RLS.

1. Un hilo del cliente A con el agente del cliente B da 404 y no crea nada.
2. Un hilo sin agente del cliente A se sella con el principal de A, aunque el de
   B sea más antiguo: si la RLS no se aplicara al resolverlo, ganaría el de B.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, text, update

from nexus_api.db.models import Agent
from nexus_api.db.models.qa import QAThread

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


class _CapturingPipeline:
    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def astream_events(
        self, state: dict[str, Any], config: dict[str, Any], version: str = "v2"
    ) -> Any:
        self.states.append(dict(state))
        for _ in ():
            yield {}


async def _agent(db_session: Any, tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    agent_id = uuid.uuid4()
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        db_session.add(Agent(id=agent_id, tenant_id=tenant_id, name=name))
    return agent_id


def _headers(admin_headers: dict[str, str], operator: str) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": operator}


async def _threads_of(db_session: Any, tenant_id: uuid.UUID, operator: str) -> int:
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        await db_session.execute(
            text("SELECT set_config('app.operator_id', :o, true)"), {"o": operator}
        )
        return int(await db_session.scalar(select(func.count()).select_from(QAThread)) or 0)


async def test_a_thread_cannot_test_another_clients_agent(
    client: Any, admin_headers: dict[str, str], db_session: Any, tenants_ab: dict[str, uuid.UUID]
) -> None:
    operator = secrets.token_urlsafe(12)
    await _agent(db_session, tenants_ab["a"], "Recepción A")
    agent_b = await _agent(db_session, tenants_ab["b"], "Recepción B")

    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenants_ab["a"]), "agent_id": str(agent_b)},
        headers=_headers(admin_headers, operator),
    )

    assert r.status_code == 404, r.text
    assert await _threads_of(db_session, tenants_ab["a"], operator) == 0


async def test_a_thread_without_agent_seals_its_own_clients_principal(
    client: Any,
    admin_headers: dict[str, str],
    db_session: Any,
    tenants_ab: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _CapturingPipeline()
    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda *, live: fake)
    operator = secrets.token_urlsafe(12)
    # B primero: el más antiguo de los dos. Sin la RLS, sería «el principal».
    await _agent(db_session, tenants_ab["b"], "Recepción B")
    agent_a = await _agent(db_session, tenants_ab["a"], "Recepción A")

    created = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenants_ab["a"])},
        headers=_headers(admin_headers, operator),
    )
    assert created.status_code == 201, created.text
    thread_id = uuid.UUID(created.json()["id"])
    assert created.json()["agent_id"] == str(agent_a)
    # Como un hilo de antes del arreglo.
    async with db_session.begin():
        await set_tenant(db_session, tenants_ab["a"])
        await db_session.execute(
            text("SELECT set_config('app.operator_id', :o, true)"), {"o": operator}
        )
        await db_session.execute(
            update(QAThread).where(QAThread.id == thread_id).values(agent_id=None)
        )

    run = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "hola"},
        headers=_headers(admin_headers, operator),
    )
    assert run.status_code == 202, run.text
    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": run.json()["run_id"]},
        headers=_headers(admin_headers, operator),
    ) as stream:
        seen = ""
        async for chunk in stream.aiter_text():
            seen += chunk
            if "event: run.completed" in seen:
                break

    assert fake.states[0]["agent_id"] == str(agent_a)
    got = await client.get(f"/qa/threads/{thread_id}", headers=_headers(admin_headers, operator))
    assert got.json()["agent_id"] == str(agent_a)
