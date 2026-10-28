"""Un turno contra el mundo simulado — spec 047, T085 (requisitos 20.1 a 20.4).

El playground y las pruebas corren **el mismo grafo que atiende el canal**
(``build_pipeline``) con tres cambios, y ninguno más:

1. el cargador del agente va **fijado a la versión elegida** (el borrador o una
   versión del historial), con el paquete entero que vería el canal: zona
   horaria, asignaciones de modelo, banderas y agente (``agent_loader.bundle_of``);
2. el registro de herramientas es el **simulado** (``SimulatedRegistry``): la
   agenda y la hora no son las de verdad y nada sale fuera;
3. la **hora** es la simulada (``turn_clock.simulated_clock``).

La conversación es de verdad en la base, en el canal ``qa_playground`` del
cliente, que la Bandeja, el tráfico y Consumo ya excluyen; el grafo lee de ahí
el historial. Se borra al cerrar la sesión o al terminar la prueba.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.db.models.channel import QA_PLAYGROUND_PROVIDER

from nexus_worker.simulation.registry import SimulatedRegistry
from nexus_worker.simulation.world import World

log = structlog.get_logger(__name__)

TURN_TIMEOUT_S = 120.0

_router_override: Any | None = None


def set_simulation_router(router: Any | None) -> None:
    """Gancho de pruebas: un ``LLMRouter`` con ``InMemoryProvider``."""
    global _router_override
    _router_override = router


def default_router() -> Any:
    """El router del playground y de las pruebas. Con ``llm_use_inmemory``
    (local), un proveedor en memoria: el flujo se recorre sin claves."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import InMemoryProvider, LiteLLMProvider, LLMRouter

    if _router_override is not None:
        return _router_override
    settings = get_worker_settings()
    provider: Any = InMemoryProvider() if settings.llm_use_inmemory else LiteLLMProvider()
    model = os.environ.get("NEXUS_LLM_SIMULATION_MODEL") or settings.llm_respond_model
    return LLMRouter(
        provider=provider,
        classify_model=settings.llm_classify_model,
        respond_model=model,
        fallback_model="",
    )


@dataclass(frozen=True)
class SimConversation:
    channel_id: uuid.UUID
    conversation_id: uuid.UUID
    customer_id: uuid.UUID
    identifier: str


@dataclass
class TurnOutcome:
    """Lo que enseña el playground de un turno (20.3, 20.4)."""

    bubbles: list[str]
    actions: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    intent: str | None = None

    @property
    def several_bubbles(self) -> bool:
        return len(self.bubbles) > 1


async def _channel(session: Any, tenant_id: uuid.UUID) -> Channel:
    channel = (
        await session.scalars(
            sa.select(Channel).where(
                Channel.tenant_id == tenant_id,
                Channel.type == ChannelType.WEB,
                Channel.provider == QA_PLAYGROUND_PROVIDER,
            )
        )
    ).first()
    if channel is not None:
        return channel
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WEB,
        provider=QA_PLAYGROUND_PROVIDER,
        provider_identifier=f"{QA_PLAYGROUND_PROVIDER}:{tenant_id}",
        config={"qa_playground": True},
        status=ChannelStatus.ACTIVE,
    )
    session.add(channel)
    await session.flush()
    return channel


async def open_conversation(tenant_id: uuid.UUID) -> SimConversation:
    """Un cliente simulado y su conversación, en el canal del playground."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel = await _channel(session, tenant_id)
        identifier = f"sim::{uuid.uuid4().hex}"
        customer = Customer(tenant_id=tenant_id, identifier=identifier, preferences={})
        session.add(customer)
        await session.flush()
        conversation = Conversation(
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        session.add(conversation)
        await session.flush()
        return SimConversation(
            channel_id=channel.id,
            conversation_id=conversation.id,
            customer_id=customer.id,
            identifier=identifier,
        )


async def close_conversation(tenant_id: uuid.UUID, conv: SimConversation) -> None:
    """Borra la conversación simulada (los mensajes caen en cascada)."""
    sm = get_sessionmaker()
    try:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await session.execute(
                sa.delete(Conversation).where(Conversation.id == conv.conversation_id)
            )
            await session.execute(sa.delete(Customer).where(Customer.id == conv.customer_id))
    except Exception:  # limpiar no puede tumbar a quien llama
        log.warning("simulation.cleanup_failed", tenant_id=str(tenant_id), exc_info=True)


async def run_turn(
    *,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    world: World,
    conv: SimConversation,
    text: str,
    llm_router: Any | None = None,
    timeout_s: float = TURN_TIMEOUT_S,
    model_policy: dict[str, Any] | None = None,
) -> TurnOutcome:
    """Un mensaje del cliente simulado y lo que el agente hace con él. El mundo
    cambia en el sitio (agenda, hora, lo que habría hecho). ``model_policy``: la
    política de modelo con la que corre en lugar de la de la versión (la
    comprobación de calidad, 39.9)."""
    from langgraph.checkpoint.memory import MemorySaver
    from nexus_api.core.llm_proxy import (
        llm_proxy_partner_scope,
        partner_id_for_tenant_standalone,
    )

    from nexus_worker.runtime.agent_loader import AgentLoader, bundle_of
    from nexus_worker.runtime.pipeline import build_pipeline
    from nexus_worker.runtime.turn_clock import simulated_clock

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        cfg = await session.get(AgentConfig, version_id)
        if cfg is None:
            raise LookupError("unknown_version")
        bundle = await bundle_of(session, tenant_id, cfg)
        if model_policy:
            bundle = dataclasses.replace(
                bundle, policies={**bundle.policies, "model_policy": dict(model_policy)}
            )
        inbound = Message(
            tenant_id=tenant_id,
            conversation_id=conv.conversation_id,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.SENT,
            content=text,
            tool_calls=[],
            # La hora de la base es la de verdad: el historial se ordena por
            # ella y las respuestas las escribe el grafo con ``now()``.
            created_at=datetime.now(UTC),
        )
        session.add(inbound)
        await session.flush()
        inbound_id = inbound.id

    loader = AgentLoader()
    loader.prime(bundle)
    pipeline = build_pipeline(
        agent_loader=loader,
        llm_router=llm_router or default_router(),
        checkpointer=MemorySaver(),
        mcp_registry=SimulatedRegistry(world),
        use_ucm_formatter=False,
    )
    before = len(world.actions)
    world.bubbles = []
    state: dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(conv.channel_id),
        "channel_type": "web",
        "user_id": conv.identifier,
        "conversation_id": str(conv.conversation_id),
        "customer_id": str(conv.customer_id),
        "inbound_message_id": str(inbound_id),
        "user_message": text,
    }
    config = {"configurable": {"thread_id": f"sim:{conv.conversation_id}"}}
    # El proxy de modelos es fail-closed: cada salto lleva la clave virtual del
    # partner. Se abre aquí, en la misma tarea que crea ``wait_for``, porque los
    # que llaman (el playground, las pruebas, la calidad) no la abren.
    partner_id = await partner_id_for_tenant_standalone(tenant_id)
    scope = (
        llm_proxy_partner_scope(partner_id) if partner_id is not None else contextlib.nullcontext()
    )
    with tenant_context(tenant_id), simulated_clock(world.now_at), scope:
        final = await asyncio.wait_for(pipeline.ainvoke(state, config=config), timeout=timeout_s)
    final = final or {}
    response = str(final.get("response") or "").strip()
    bubbles = [b for b in [response, *world.bubbles] if b]
    # El reloj avanza un poco por turno, como en una conversación de verdad.
    world.set_now(world.now_at + timedelta(minutes=1))
    return TurnOutcome(
        bubbles=bubbles,
        actions=[{"tool": a.tool, "phrase": a.phrase} for a in world.actions[before:]],
        tool_calls=[
            {"name": e.get("tool"), "status": e.get("status")}
            for e in final.get("tool_calls") or []
        ],
        model=final.get("response_model"),
        intent=final.get("intent"),
    )


__all__ = [
    "SimConversation",
    "TurnOutcome",
    "close_conversation",
    "default_router",
    "open_conversation",
    "run_turn",
    "set_simulation_router",
]
