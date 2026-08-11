"""La degradación por presupuesto llega hasta el modelo (WP-20 + WP-19/21).

``test_budget_wiring.py`` comprueba que el dispatcher pone las banderas en
el estado. Esto comprueba la otra mitad: que el grafo **les hace caso**.

Es la mitad que más fácil se rompe sin ruido. Si el nodo del handler deja
de leer ``budget_degrade_model``, el agente sigue contestando igual de
bien — solo que con el modelo caro, que es justo lo que el presupuesto
venía a evitar. No hay excepción, no hay log raro, no hay test de negocio
que lo note.

Se corre sobre el pipeline compilado de verdad, con un proveedor en
memoria que registra con qué modelo se le llamó. El modelo barato no está
escrito a mano en el test: sale del catálogo de WP-19, que es de donde lo
saca el runtime.
"""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.metering.pricing import cheapest_model
from nexus_worker.metering.pricing import invalidate as invalidate_pricing
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    Tenant,
    TenantPlan,
)

from ..isolation.conftest import (  # type: ignore[import-not-found]
    seed_active_agent_config,
    seed_channel,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

EXPENSIVE = "t/expensive-respond"


@pytest.fixture(autouse=True)
def _fresh_pricing_cache():
    invalidate_pricing()
    yield
    invalidate_pricing()


async def _seed(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Degradado",
            slug=f"degr-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()
    await seed_active_agent_config(
        db_session, tenant_id=tenant_id, system_prompt="Eres un asistente de prueba.", tools=[]
    )
    channel = await seed_channel(
        db_session, tenant_id=tenant_id, provider_identifier=f"degr-{tenant_id.hex[:6]}"
    )
    customer = Customer(tenant_id=tenant_id, identifier="+34600000009", name="cliente")
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        content="¿a qué hora abren?",
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()
    await db_session.refresh(inbound)

    state = new_state(
        tenant_id=tenant_id,
        channel_id=channel.id,
        user_id=customer.identifier,
        conversation_id=conv.id,
        customer_id=customer.id,
        inbound_message_id=inbound.id,
        user_message="¿a qué hora abren?",
    )
    return tenant_id, channel, state


def _pipeline() -> tuple[InMemoryProvider, object]:
    provider = InMemoryProvider()
    provider.responder = lambda call: "info" if call.role == "classify" else "Abrimos de 9 a 18."
    provider.tool_caller = lambda call: []
    router = LLMRouter(
        provider=provider,
        classify_model="t/classify",
        respond_model=EXPENSIVE,
        fallback_model="t/fallback",
    )
    return provider, build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
    )


def _respond_models(provider: InMemoryProvider) -> list[str]:
    return [c.model for c in provider.calls if c.role != "classify"]


async def test_without_degradation_the_normal_model_is_used(db_session) -> None:
    """Control negativo: sin él, un test que ve el modelo barato no
    distingue "degradó" de "nunca usó el caro"."""
    tenant_id, channel, state = await _seed(db_session)
    provider, pipeline = _pipeline()

    await pipeline.ainvoke(
        state,
        config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "no-degr")}},
    )
    assert _respond_models(provider) == [EXPENSIVE]


async def test_a_degraded_turn_runs_on_the_cheapest_model_in_the_catalog(db_session) -> None:
    tenant_id, channel, state = await _seed(db_session)
    state["budget_degrade_model"] = True
    provider, pipeline = _pipeline()

    await pipeline.ainvoke(
        state,
        config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "degr")}},
    )

    # El modelo esperado NO está escrito a mano: se pregunta al mismo
    # catálogo del que lo saca el runtime. Si mañana entra un modelo más
    # barato, este test sigue diciendo la verdad.
    barato = await cheapest_model()
    assert barato is not None, "el catálogo (0072) no tiene ningún modelo con precio"
    assert _respond_models(provider) == [barato]
    assert EXPENSIVE not in _respond_models(provider)


class _RecordingGrader:
    """Gradúa siempre ``pass`` y cuenta las veces. Lo que importa no es el
    veredicto, es SI se llamó."""

    def __init__(self) -> None:
        self.calls = 0

    async def grade(self, **kwargs):
        from nexus_worker.guardrails.outcome_grader import GraderVerdict

        self.calls += 1
        return GraderVerdict(overall="pass", criteria={}, feedback="")


async def _enable_grader(db_session, tenant_id) -> None:
    import sqlalchemy as sa

    await db_session.execute(
        sa.text(
            "UPDATE agent_configs SET runtime_outcome_grader = true, grader_mode = 'sync' "
            "WHERE tenant_id = :t"
        ),
        {"t": str(tenant_id)},
    )
    await db_session.commit()


def _pipeline_with_grader(grader) -> tuple[InMemoryProvider, object]:
    provider = InMemoryProvider()
    provider.responder = lambda call: "info" if call.role == "classify" else "Abrimos de 9 a 18."
    provider.tool_caller = lambda call: []
    router = LLMRouter(
        provider=provider,
        classify_model="t/classify",
        respond_model=EXPENSIVE,
        fallback_model="t/fallback",
    )
    return provider, build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
        outcome_grader=grader,
    )


async def test_a_grader_enabled_agent_grades_when_there_is_budget(db_session) -> None:
    """Control negativo del test siguiente.

    Sin esto, afirmar "no graduó" no prueba nada: con el grader apagado
    en el config —o sin grader construido— tampoco graduaría, y el test
    pasaría verde midiendo la nada.
    """
    tenant_id, channel, state = await _seed(db_session)
    await _enable_grader(db_session, tenant_id)
    grader = _RecordingGrader()
    _provider, pipeline = _pipeline_with_grader(grader)

    await pipeline.ainvoke(
        state,
        config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "grade-on")}},
    )
    assert grader.calls == 1


async def test_the_soft_limit_silences_the_grader(db_session) -> None:
    """La segunda palanca de coste: mismo agente, mismo grader, pero con
    el presupuesto blando puesto no se gradúa."""
    tenant_id, channel, state = await _seed(db_session)
    await _enable_grader(db_session, tenant_id)
    state["budget_disable_grader"] = True
    grader = _RecordingGrader()
    _provider, pipeline = _pipeline_with_grader(grader)

    final = await pipeline.ainvoke(
        state,
        config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "grade-off")}},
    )
    assert grader.calls == 0, "se gastó una llamada de grader con el presupuesto en blando"
    assert final.get("outcome_overall") == "skipped"
