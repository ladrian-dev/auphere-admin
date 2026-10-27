"""El router dentro del grafo compilado, contra la base de verdad (spec 047,
T140 y T145 · historia 13, requisitos 40.5 y 40.7).

``apps/worker/tests/unit/test_pipeline_router.py`` prueba la política del grafo
con un catálogo de mentira. Esto prueba lo mismo con **el catálogo que sembraron
las migraciones** (las filas de hoy, sin retención cero comprobada: research
D44), el grafo entero (clasificar → manejador → juez → formato → checkpoint) y
las tablas de verdad:

1. un agente de hoy responde con su modelo de hoy, byte a byte igual que con el
   router fuera de alcance, y no deja afinidad ni anomalías;
2. un agente con perfil, con ese catálogo, no saca nada de su residencia: la
   conversación va a la Bandeja con ``no_model`` y la anomalía queda en
   ``router_anomalies`` con la RLS de su cliente;
3. en cuanto un despliegue pasa el filtro y la batería de ``classify``, el
   clasificador de todos —también el de un agente de hoy— pasa a él (D24),
   y su respuesta sigue en su modelo de hoy.

Ningún proveedor real: ``InMemoryProvider``. El despliegue de prueba se borra al
acabar (``model_profiles`` es de plataforma y el ``conftest`` no lo vacía).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime import model_resolver
from nexus_worker.runtime import pipeline as graph
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import ROUTE_DECISION_EVENT, InMemoryProvider, LLMCall, LLMRouter
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id
from structlog.testing import capture_logs

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    Tenant,
    TenantPlan,
)

from ...isolation.conftest import (  # type: ignore[import-not-found]
    seed_active_agent_config,
    seed_channel,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CLASSIFIER = "c3t-eu/classifier"
AUTO = {"model_policy": {"kind": "profile", "profile": "auto"}}


@pytest_asyncio.fixture(autouse=True)
async def _fresh_catalog(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Cada prueba lee el catálogo de la base, no el de la anterior; y la hora
    del turno, fija, para comparar dos turnos byte a byte."""
    monkeypatch.setattr(graph, "_now_note", lambda _tz: "Hoy es sábado, 10:00.")
    model_resolver.invalidate_catalog()
    yield
    model_resolver.invalidate_catalog()
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c3t-%'"))
    respond_catalog.reset()


@pytest_asyncio.fixture
async def two_clients(db_session) -> dict[str, uuid.UUID]:
    ids = {"a": uuid.uuid4(), "b": uuid.uuid4()}
    db_session.add_all(
        [
            Tenant(id=t, name=f"C3 {k}", slug=f"c3-{k}-{t.hex[:6]}", plan=TenantPlan.PRO)
            for k, t in ids.items()
        ]
    )
    await db_session.commit()
    return ids


async def _conversation(db_session, tenant_id: uuid.UUID, channel: Any, who: str) -> Any:
    customer = Customer(tenant_id=tenant_id, identifier=who, preferences={})
    db_session.add(customer)
    await db_session.commit()
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        content="¿A qué hora abren el sábado?",
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()
    state = new_state(
        tenant_id=tenant_id,
        channel_id=channel.id,
        user_id=who,
        conversation_id=conv.id,
        customer_id=customer.id,
        inbound_message_id=inbound.id,
        user_message="¿A qué hora abren el sábado?",
    )
    return state, make_thread_id(tenant_id, channel.id, who)


def _provider() -> InMemoryProvider:
    provider = InMemoryProvider()

    def responder(call: LLMCall) -> str:
        if call.extra.get("task") == "classify":
            return json.dumps(
                {
                    "intent": "info",
                    "needs_tools": False,
                    "risk": "low",
                    "complexity": "low",
                    "language": "es",
                    "intents": 1,
                }
            )
        if call.role == "classify":
            return "info"
        return "Abrimos de 10 a 14."

    provider.responder = responder
    return provider


async def _run(state: dict[str, Any], thread: str, provider: InMemoryProvider) -> dict[str, Any]:
    llm = LLMRouter(
        provider=provider,
        classify_model="test/classify",
        respond_model="test/respond",
        fallback_model="test/fallback",
    )
    pipeline = build_pipeline(
        agent_loader=AgentLoader(), llm_router=llm, checkpointer=MemorySaver()
    )
    return dict(await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread}}))


def _wire(provider: InMemoryProvider) -> list[tuple[Any, ...]]:
    return [
        (c.role, c.model, json.dumps(c.messages, sort_keys=True, default=str), c.tools, c.extra)
        for c in provider.calls
    ]


async def _anomalies(tenant_id: uuid.UUID) -> list[tuple[str, str]]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (await session.execute(sa.text("SELECT task, kind FROM router_anomalies"))).all()
    return sorted((str(t), str(k)) for t, k in rows)


async def test_an_agent_of_today_answers_on_its_model_with_the_real_catalog(
    db_session, two_clients, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = two_clients["a"]
    await seed_active_agent_config(db_session, tenant_id=a, system_prompt="Agente de hoy", tools=[])
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="c3-hoy")

    # El router fuera de alcance: lo que hacía el grafo antes de C3.
    async def unreachable(*, force: bool = False) -> Any:
        raise ConnectionError("sin catálogo")

    with monkeypatch.context() as m:
        m.setattr(graph, "get_catalog_snapshot", unreachable)
        before = _provider()
        state, thread = await _conversation(db_session, a, channel, "+56900000001")
        out_before = await _run(state, thread, before)

    after = _provider()
    state, thread = await _conversation(db_session, a, channel, "+56900000002")
    with capture_logs() as logs:
        out_after = await _run(state, thread, after)

    assert _wire(after) == _wire(before)
    assert [c.model for c in after.calls] == ["test/classify", "test/respond"]
    assert out_after["response"] == out_before["response"] == "Abrimos de 10 a 14."
    assert out_after["turn_failure"] is None
    assert not out_after.get("pinned_model")
    assert not [e for e in logs if e["event"] == ROUTE_DECISION_EVENT]
    assert await _anomalies(a) == []


async def test_a_profiled_agent_with_todays_catalog_does_not_leave_its_residency(
    db_session, two_clients
) -> None:
    a, b = two_clients["a"], two_clients["b"]
    await seed_active_agent_config(
        db_session, tenant_id=a, system_prompt="Agente nuevo", tools=[], policies=AUTO
    )
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="c3-auto")
    provider = _provider()
    state, thread = await _conversation(db_session, a, channel, "+56900000003")
    out = await _run(state, thread, provider)

    assert provider.calls == [], "sin despliegue con retención cero no sale nada (D44)"
    assert out["turn_failure"] == {"kind": "llm_failed", "reason": "no_model", "detail": None}
    assert await _anomalies(a) == [("answer", "no_model"), ("classify", "no_model")]
    assert await _anomalies(b) == [], "la anomalía es de su cliente: la RLS la guarda"


async def _certified_classifier() -> None:
    """Un despliegue que pasa el filtro duro y la batería de ``classify``."""
    caps = {"strict_structured_outputs": True, "structured_outputs": True, "tier": "basic"}
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name, route, family, residency, zero_retention,
                    retention_how, contract_dpa, subprocessor_listed, status, capabilities,
                    supports_tools, price_input_per_mtok, price_output_per_mtok,
                    quota_weight_input, quota_weight_cache_read, quota_weight_output
                ) VALUES (
                    'c3t', :key, 'Clasificador de prueba', :key, 'openai-gpt-oss', 'eu', true,
                    'store=false', true, true, 'active', CAST(:caps AS jsonb), false,
                    0.05, 0.2, 0.011, 0.0011, 0.044
                )
                """
            ),
            {"key": CLASSIFIER, "caps": json.dumps(caps)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, output, source_url) "
                "SELECT id, DATE '2026-10-01', 0.05, 0.2, 'https://example.invalid' "
                "FROM model_profiles WHERE model_id = :key"
            ),
            {"key": CLASSIFIER},
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "SELECT id, 'classify', 1, '{\"pass3\": 0.97}'::jsonb, 0.97, true "
                "FROM model_profiles WHERE model_id = :key"
            ),
            {"key": CLASSIFIER},
        )


async def test_the_classifier_moves_once_a_deployment_passes_the_battery(
    db_session, two_clients
) -> None:
    a = two_clients["a"]
    await seed_active_agent_config(db_session, tenant_id=a, system_prompt="Agente de hoy", tools=[])
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="c3-clasifica")
    await _certified_classifier()

    provider = _provider()
    state, thread = await _conversation(db_session, a, channel, "+56900000004")
    out = await _run(state, thread, provider)

    [classify, answer] = provider.calls
    assert classify.model == CLASSIFIER and classify.extra["task"] == "classify"
    assert classify.extra["deployment"] == CLASSIFIER
    assert answer.model == "test/respond" and "deployment" not in answer.extra
    assert out["classification"]["intent"] == "info"
    assert out["response"] == "Abrimos de 10 a 14."
    assert not out.get("pinned_model"), "el agente de hoy sigue fijado en su modelo de hoy"
