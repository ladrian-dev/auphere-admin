"""El presupuesto está ENGANCHADO, no solo implementado (WP-20).

``test_budget_cutoff.py`` prueba la lógica: el veredicto sale bien y el
traspaso se escribe. Esto prueba lo otro, que es donde de verdad se
rompen estas cosas: que el dispatcher lo consulta antes de abrir el
turno y que el pipeline hace caso a la degradación.

Por qué merece un archivo propio: **un fallo de cableado aquí es
silencioso por construcción**. Si la llamada a ``evaluate`` desaparece en
un refactor, no hay excepción ni log raro — los turnos se responden con
normalidad y el presupuesto simplemente no existe. Se descubre en la
factura. Lo mismo con la degradación: sin ella el agente sigue
contestando igual de bien, solo que caro.

El pipeline es un doble que registra llamadas. Es el nivel de simulación
correcto para un test de compuerta: no se prueba el pipeline, se prueba
la reja que tiene delante.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.metering.budget import add_spend, invalidate_policies
from nexus_worker.runtime.budget_gate import HANDOFF_MESSAGE
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Tenant,
    TenantPlan,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _RecordingPipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(state)
        return {"intent": "info", "response": "ok", "tool_calls": []}


@pytest.fixture(autouse=True)
def _fresh_policy_cache():
    invalidate_policies()
    yield
    invalidate_policies()


async def _tenant_with_agent(db_session: Any) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Presupuesto",
            slug=f"wire-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Eres un asistente de prueba.",
            channels=[],
            tools=[],
            policies={},
            created_by="test",
        )
    )
    await db_session.commit()
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"wire-{tenant_id.hex[:8]}",
        status=ChannelStatus.ACTIVE,
        config={},
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return tenant_id, channel.id


async def _policy(scope_id: uuid.UUID, *, soft: str, hard: str, action: str = "both") -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text(
                "INSERT INTO budget_policies "
                "(scope, scope_id, meter, period, soft_limit, hard_limit, soft_action) "
                "VALUES ('tenant', :sid, 'cost_usd', 'day', :soft, :hard, :act)"
            ),
            {"sid": str(scope_id), "soft": soft, "hard": hard, "act": action},
        )
        await session.commit()
    invalidate_policies()


async def _outbound(tenant_id: uuid.UUID) -> list[str]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return list(
            (
                await session.execute(
                    sa.text(
                        "SELECT content FROM messages WHERE direction = 'outbound' "
                        "ORDER BY created_at"
                    )
                )
            )
            .scalars()
            .all()
        )


async def test_a_tenant_within_budget_runs_normally(db_session, fake_redis) -> None:
    """El control negativo. Sin él, un test que ve el pipeline sin invocar
    no distingue "lo cortó el presupuesto" de "está roto el arnés"."""
    tenant_id, channel_id = await _tenant_with_agent(db_session)
    await _policy(tenant_id, soft="10.0000", hard="50.0000")

    pipeline = _RecordingPipeline()
    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id, channel_id=channel_id, user_id="+34600000001", content="hola"
        ),
        pipeline=pipeline,
    )

    assert len(pipeline.calls) == 1
    assert result.get("skipped") is None


async def test_the_hard_limit_stops_the_pipeline_from_being_invoked(db_session, fake_redis) -> None:
    """Lo que el presupuesto viene a conseguir: no se gasta ni un token."""
    tenant_id, channel_id = await _tenant_with_agent(db_session)
    await _policy(tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("50"))

    pipeline = _RecordingPipeline()
    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id, channel_id=channel_id, user_id="+34600000002", content="hola"
        ),
        pipeline=pipeline,
    )

    assert pipeline.calls == [], "se abrió el turno con el presupuesto agotado"
    assert result["skipped"] == "budget_hard_limit"


async def test_the_cutoff_still_answers_the_customer(db_session, fake_redis) -> None:
    """La garantía que hace aceptable cortar, comprobada por el camino
    real del dispatcher y no llamando al gate a mano."""
    tenant_id, channel_id = await _tenant_with_agent(db_session)
    await _policy(tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("99"))

    await process_inbound(
        InboundEvent(
            tenant_id=tenant_id, channel_id=channel_id, user_id="+34600000003", content="hola"
        ),
        pipeline=_RecordingPipeline(),
    )

    assert await _outbound(tenant_id) == [HANDOFF_MESSAGE], (
        "el turno se cortó y el cliente final se quedó sin respuesta"
    )


async def test_the_soft_limit_reaches_the_graph_as_degradation(db_session, fake_redis) -> None:
    """El dispatcher tiene que PASAR la degradación al grafo.

    Si las banderas no llegan al estado, el pipeline no tiene forma de
    saber que hay que abaratar el turno — y la degradación existiría solo
    en el log.
    """
    tenant_id, channel_id = await _tenant_with_agent(db_session)
    await _policy(tenant_id, soft="10.0000", hard="50.0000", action="both")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("12"))

    pipeline = _RecordingPipeline()
    await process_inbound(
        InboundEvent(
            tenant_id=tenant_id, channel_id=channel_id, user_id="+34600000004", content="hola"
        ),
        pipeline=pipeline,
    )

    assert len(pipeline.calls) == 1, "el umbral blando NO puede cortar el turno"
    state = pipeline.calls[0]
    assert state.get("budget_degrade_model") is True
    assert state.get("budget_disable_grader") is True


async def test_each_soft_action_pulls_only_its_own_lever(db_session, fake_redis) -> None:
    """``downgrade`` no puede apagar el grader de rebote: son dos
    decisiones de coste distintas y el operador elige una."""
    tenant_id, channel_id = await _tenant_with_agent(db_session)
    await _policy(tenant_id, soft="10.0000", hard="50.0000", action="downgrade")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("12"))

    pipeline = _RecordingPipeline()
    await process_inbound(
        InboundEvent(
            tenant_id=tenant_id, channel_id=channel_id, user_id="+34600000005", content="hola"
        ),
        pipeline=pipeline,
    )

    state = pipeline.calls[0]
    assert state.get("budget_degrade_model") is True
    assert state.get("budget_disable_grader") is False
