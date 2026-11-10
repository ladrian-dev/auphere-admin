"""Fallo ``el-playground-consulta-al-dueno-de-verdad`` — el playground y las pruebas
no salen del mundo simulado (requisito 20.1; C8).

Un agente con una integración en «Preguntar antes de escribir» y una conversación
del playground (``run_turn``, el mismo grafo que el canal con el registro
simulado) en la que el modelo lee de la integración y después quiere escribir:

- **ninguna consulta al dueño**: ni fila en ``owner_consultations`` ni plantilla;
  el turno cuenta «Lo que habría hecho: Preguntar al dueño antes de …» y sigue
  como si hubiera dicho que sí, para que la prueba compruebe el resto;
- **ninguna lectura de verdad**: la herramienta de lectura de la integración no
  se ejecuta; el agente recibe un resultado simulado y vacío.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from nexus_mcp import MCPRegistry
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_worker.runtime.llm import InMemoryProvider, LLMCall, LLMRouter, ToolCall
from nexus_worker.simulation import registry as sim_registry
from nexus_worker.simulation.runner import close_conversation, open_conversation, run_turn
from nexus_worker.simulation.world import seed_world
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConnectorActivation,
    OwnerConsultation,
    Partner,
)

from ..business._business_world import Biz, new_business, seed_agent
from ._activation_world import READ, SPEC, WRITE, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _In(InputModel):
    pass


class _Out(OutputModel):
    orders: list[str] = Field(default_factory=list)


class _ShopRead(ToolBase):
    """La lectura de la tienda del negocio: pedidos con nombre de sus clientes."""

    name: ClassVar[str] = READ
    description: ClassVar[str] = "Lista los pedidos"
    input_model: ClassVar[type[InputModel]] = _In
    output_model: ClassVar[type[OutputModel]] = _Out
    side_effects: ClassVar[tuple[str, ...]] = ()
    runs: ClassVar[int] = 0

    async def run(self, payload: InputModel) -> OutputModel:
        type(self).runs += 1
        return _Out(orders=["Lucía Pérez · 2 taladros"])


class _ShopWrite(_ShopRead):
    """La escritura: crearía un pedido de verdad en la tienda."""

    name: ClassVar[str] = WRITE
    description: ClassVar[str] = "Crea un pedido"
    side_effects: ClassVar[tuple[str, ...]] = ("external_api",)


class _Model:
    """El agente de mentira: lee los pedidos, quiere crear uno y contesta."""

    def __init__(self) -> None:
        self.provider = InMemoryProvider(responder=self._respond, tool_caller=self._tools)
        self.router = LLMRouter(
            provider=self.provider, classify_model="t/c", respond_model="t/r", fallback_model=""
        )
        self.rounds = 0

    def _respond(self, call: LLMCall) -> str:
        return "info" if call.role == "classify" else "Te lo dejo pedido."

    def _tools(self, call: LLMCall) -> list[ToolCall]:
        if call.role == "classify":
            return []
        self.rounds += 1
        if self.rounds > 1:
            return []
        return [
            ToolCall(id="r1", name=READ, arguments={}),
            ToolCall(id="w1", name=WRITE, arguments={"product": "taladro", "qty": 2}),
        ]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Tienda Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return biz


async def test_the_playground_never_asks_the_owner_nor_reads_the_shop(
    db_session: AsyncSession, biz: Biz, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    agent_id, version_id = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="Vende.", tools=[READ, WRITE]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.get(AgentConfig, version_id)
        assert cfg is not None
        cfg.spec = SPEC
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                connector_id=install_id,
                permission="ask_before_write",
                settings={},
            )
        )
    await db_session.commit()

    # La tienda existe en el registro (como la de WooCommerce): leerla devolvería
    # pedidos de verdad, y escribir crearía uno.
    def registry_with_the_shop() -> MCPRegistry:
        return MCPRegistry(tools=[_ShopRead(), _ShopWrite()])

    monkeypatch.setattr(sim_registry, "build_default_registry", registry_with_the_shop)
    _ShopRead.runs = _ShopWrite.runs = 0
    model = _Model()

    async with tenant_scoped_session(db_session, biz.tenant_id):
        world = await seed_world(db_session, agent_id)
    conv = await open_conversation(biz.tenant_id)
    try:
        outcome = await run_turn(
            tenant_id=biz.tenant_id,
            version_id=version_id,
            world=world,
            conv=conv,
            text="¿Me pides dos taladros?",
            llm_router=model.router,
        )
        async with tenant_scoped_session(db_session, biz.tenant_id):
            consultations = (
                await db_session.scalars(
                    sa.select(OwnerConsultation).where(
                        OwnerConsultation.conversation_id == conv.conversation_id
                    )
                )
            ).all()
    finally:
        await close_conversation(biz.tenant_id, conv)

    offered = {t["function"]["name"] for c in model.provider.calls for t in c.tools}
    assert {READ, WRITE} <= offered, "the agent's own activation applies in the playground"
    assert consultations == [], "the playground asked the real owner"
    assert _ShopRead.runs == 0, "the playground read the business's real shop"
    assert _ShopWrite.runs == 0
    phrases = [a["phrase"] for a in outcome.actions]
    assert f"Preguntar al dueño antes de usar {WRITE}" in phrases
    assert f"Usar {WRITE}" in phrases, "and goes on as if the owner said yes"
    assert f"Consultar {READ} (simulado, sin datos reales)" in phrases


async def test_the_channel_still_asks_the_owner(db_session: AsyncSession, biz: Biz) -> None:
    """Fuera del playground nada cambia: la escritura espera al dueño (35.5)."""
    from nexus_worker.runtime.pipeline import _approval_envelope

    from nexus_api.db.models import Channel, ChannelType, Conversation, ConversationStatus, Customer

    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id, _ = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="Vende.", tools=[READ, WRITE]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = Channel(
            tenant_id=biz.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3491{uuid.uuid4().int % 10**7:07d}",
            config={},
            agent_id=agent_id,
        )
        customer = Customer(tenant_id=biz.tenant_id, identifier="34600555222", preferences={})
        db_session.add_all([channel, customer])
        await db_session.flush()
        conversation = Conversation(
            tenant_id=biz.tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conversation)
        await db_session.flush()
        conv_id = conversation.id
    await db_session.commit()
    state: Any = {
        "tenant_id": str(biz.tenant_id),
        "conversation_id": str(conv_id),
        "agent_id": str(agent_id),
    }
    asked = await _approval_envelope(
        state, ToolCall(id="c1", name=WRITE, arguments={"qty": 1}), "info"
    )
    assert asked is not None and asked["status"] == "approval_requested"
