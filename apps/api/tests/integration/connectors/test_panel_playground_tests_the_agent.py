"""Fallo ``playground-del-panel-sin-agente`` — el Playground del panel prueba el
agente con sus conectores.

En la consola nueva, sin ``agent_id`` en el estado del turno, la política de
activaciones de la spec 047 no encuentra la del agente y cierra todas las
herramientas de conector (``tool_policy(tenant, None)``). El panel no lo pasaba:
en staging, las 27 herramientas de Quédate bloqueadas en el Playground.

Por los endpoints del panel (``/qa/threads``, ``/runs`` y ``/send``), con el grafo
sustituido por uno que guarda el estado que recibe, y la política real calculada
con ese estado:

- un hilo nuevo prueba el principal, con su activación;
- un hilo de antes del arreglo (``agent_id`` NULL) prueba el principal y queda
  sellado con él;
- un hilo creado para otro agente del cliente prueba ese agente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.pipeline import _agent_uuid, _load_tool_policy
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AgentConnectorActivation, Partner
from nexus_api.db.models.qa import QAThread

from ..business._business_world import Biz, new_business
from ._activation_world import READ, WRITE, agent_with_spec, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

OPERATOR = "op-playground-agente"


class _CapturingPipeline:
    """El grafo de mentira: guarda el estado de cada turno y no hace nada más."""

    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.states.append(dict(state))
        return {"response": "ok"}

    async def astream_events(
        self, state: dict[str, Any], config: dict[str, Any], version: str = "v2"
    ) -> Any:
        self.states.append(dict(state))
        for _ in ():
            yield {}


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> _CapturingPipeline:
    fake = _CapturingPipeline()
    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda *, live: fake)
    return fake


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    """Un cliente de un partner con la consola nueva: sin activación, nada."""
    biz = await new_business(client, db_session, console_world, name="Prueba Quédate")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return biz


async def _activated_agent(
    db_session: AsyncSession, biz: Biz, name: str, *, principal: bool
) -> uuid.UUID:
    """Un agente con la integración conectada y activada para él."""
    connector = await seed_integration(db_session)
    # Si ya existía, ``seed_integration`` lo leyó y dejó la transacción abierta.
    await db_session.commit()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        install_id = await db_session.scalar(
            sa.text("SELECT id FROM tenant_connectors WHERE connector_id = :c"),
            {"c": connector.id},
        )
    await db_session.commit()
    if install_id is None:
        install_id = await connect(db_session, biz, connector)
    agent_id = await agent_with_spec(db_session, biz, name)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        if principal:
            await db_session.execute(sa.update(Agent).values(is_default=False))
            await db_session.execute(
                sa.update(Agent).where(Agent.id == agent_id).values(is_default=True)
            )
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                connector_id=install_id,
                permission="read_write",
                settings={},
            )
        )
    await db_session.commit()
    return agent_id


def _headers(admin_headers: dict[str, str]) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": OPERATOR}


async def _new_thread(
    client: Any, admin_headers: dict[str, str], biz: Biz, agent_id: uuid.UUID | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"tenant_id": str(biz.tenant_id), "title": "conector"}
    if agent_id is not None:
        body["agent_id"] = str(agent_id)
    r = await client.post("/qa/threads", json=body, headers=_headers(admin_headers))
    assert r.status_code == 201, r.text
    thread: dict[str, Any] = r.json()
    return thread


async def _run(client: Any, admin_headers: dict[str, str], thread_id: str) -> None:
    """Un turno por ``/runs`` (el que usa el panel), hasta ``run.completed``."""
    r = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "¿Qué tenéis?"},
        headers=_headers(admin_headers),
    )
    assert r.status_code == 202, r.text
    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": r.json()["run_id"]},
        headers=_headers(admin_headers),
    ) as stream:
        seen = ""
        async for chunk in stream.aiter_text():
            seen += chunk
            if "event: run.completed" in seen:
                break


async def _send(client: Any, admin_headers: dict[str, str], thread_id: str) -> None:
    r = await client.post(
        f"/qa/threads/{thread_id}/send",
        json={"message": "¿Qué tenéis?"},
        headers=_headers(admin_headers),
    )
    assert r.status_code == 200, r.text


async def _blocked_by(state: dict[str, Any], biz: Biz) -> set[str]:
    """Lo que el turno de ese estado no podría ofrecer: la política del worker."""
    policy = await _load_tool_policy(biz.tenant_id, _agent_uuid(state))  # type: ignore[arg-type]
    return {n for n in (READ, WRITE) if n in policy.blocked or policy.closed}


async def test_a_new_thread_tests_the_principal_with_its_connector(
    client: Any,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    biz: Biz,
    pipeline: _CapturingPipeline,
) -> None:
    principal = await _activated_agent(db_session, biz, "Recepción", principal=True)
    thread = await _new_thread(client, admin_headers, biz)

    await _run(client, admin_headers, thread["id"])
    await _send(client, admin_headers, thread["id"])

    assert len(pipeline.states) == 2
    for state in pipeline.states:
        # Lo que se vio en staging: sin agente en el estado, todo bloqueado.
        assert await _blocked_by(state, biz) == set(), "con su activación, nada bloqueado"
        assert state.get("agent_id") == str(principal), "el turno dice qué agente prueba"
    assert thread["agent_id"] == str(principal), "el hilo nace con el principal"


async def test_a_thread_from_before_tests_the_principal_and_keeps_it(
    client: Any,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    biz: Biz,
    pipeline: _CapturingPipeline,
) -> None:
    # Los hilos del panel de hasta hoy nacieron sin agente.
    principal = await _activated_agent(db_session, biz, "Recepción", principal=True)
    thread = await _new_thread(client, admin_headers, biz)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.text("SELECT set_config('app.operator_id', :o, true)"), {"o": OPERATOR}
        )
        await db_session.execute(
            sa.update(QAThread).where(QAThread.id == uuid.UUID(thread["id"])).values(agent_id=None)
        )
    await db_session.commit()

    await _run(client, admin_headers, thread["id"])

    assert pipeline.states[0].get("agent_id") == str(principal)
    assert await _blocked_by(pipeline.states[0], biz) == set()
    # Sellado: si mañana el principal es otro, esta conversación no cambia de agente.
    got = await client.get(f"/qa/threads/{thread['id']}", headers=_headers(admin_headers))
    assert got.status_code == 200, got.text
    assert got.json()["agent_id"] == str(principal)


async def test_a_thread_for_another_agent_tests_that_agent(
    client: Any,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    biz: Biz,
    pipeline: _CapturingPipeline,
) -> None:
    await _activated_agent(db_session, biz, "Recepción", principal=True)
    ventas = await _activated_agent(db_session, biz, "Ventas", principal=False)
    thread = await _new_thread(client, admin_headers, biz, agent_id=ventas)
    assert thread["agent_id"] == str(ventas)

    await _run(client, admin_headers, thread["id"])

    assert pipeline.states[0].get("agent_id") == str(ventas)
    assert await _blocked_by(pipeline.states[0], biz) == set()


async def test_an_archived_agent_cannot_open_a_thread(
    client: Any,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    biz: Biz,
) -> None:
    await _activated_agent(db_session, biz, "Recepción", principal=True)
    ventas = await _activated_agent(db_session, biz, "Ventas", principal=False)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(Agent).where(Agent.id == ventas).values(status="archived")
        )
    await db_session.commit()
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(biz.tenant_id), "agent_id": str(ventas)},
        headers=_headers(admin_headers),
    )
    assert r.status_code == 404, r.text


async def test_the_real_qa_graph_offers_the_agents_connector_tools(
    client: Any,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    biz: Biz,
    seeded_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lo que se vio en staging, de punta a punta en local: el grafo de QA de verdad
    (dry run, sin modelo de verdad) recibe por ``/send`` el estado del panel y la
    herramienta de Quédate del agente llega a la llamada del modelo."""
    from langgraph.checkpoint.memory import MemorySaver
    from nexus_worker.runtime.agent_loader import AgentLoader
    from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
    from nexus_worker.runtime.qa_pipeline import build_qa_pipeline

    from nexus_api.db.models import Connector, ConnectorPartnerAccess, TenantConnector

    from ..business._business_world import seed_agent

    tool = "quedate.search_listings"
    await db_session.merge(
        ConnectorPartnerAccess(
            connector_slug="quedate",
            partner_id=biz.partner_id,
            enabled=True,
            reason="t",
            set_by="t",
        )
    )
    quedate = await db_session.scalar(sa.select(Connector).where(Connector.slug == "quedate"))
    assert quedate is not None, "la semilla de Quédate no está en el catálogo"
    await db_session.commit()
    agent_id, _cfg = await seed_agent(
        db_session, biz.tenant_id, name="Reservas", prompt="Busca alojamientos.", tools=[tool]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.update(Agent).values(is_default=False))
        await db_session.execute(
            sa.update(Agent).where(Agent.id == agent_id).values(is_default=True)
        )
        install = TenantConnector(
            tenant_id=biz.tenant_id,
            connector_id=quedate.id,
            status="connected",
            credentials_ref={},
            connected_at=datetime.now(UTC),
        )
        db_session.add(install)
        await db_session.flush()
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                connector_id=install.id,
                permission="read",
                settings={},
            )
        )
    await db_session.commit()

    provider = InMemoryProvider()
    provider.responder = lambda call: "info" if call.role == "classify" else "Tenemos sitio."
    graph = build_qa_pipeline(
        agent_loader=AgentLoader(),
        llm_router=LLMRouter(
            provider=provider,
            classify_model="test/classify",
            respond_model="test/respond",
            fallback_model="test/fallback",
        ),
        checkpointer=MemorySaver(),
        dry_run=True,
    )
    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda *, live: graph)

    thread = await _new_thread(client, admin_headers, biz)
    await _send(client, admin_headers, thread["id"])

    offered = {
        td.get("function", {}).get("name", td.get("name", ""))
        for call in provider.calls
        if call.role != "classify"
        for td in (call.tools or [])
    }
    assert tool in offered, f"el modelo no recibió {tool}: {sorted(offered)}"
