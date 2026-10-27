"""El mundo de las pruebas del turno — spec 047, ola 1 (T025 a T030).

Un cliente con un número y un agente publicado, en el estado que pida cada
prueba: el cliente en pausa, el canal en pausa o con problemas, el agente sin
publicar, solo administradores… Las pruebas mandan mensajes por el despachador
de verdad (``accept_inbound`` / ``run_turn`` / ``process_inbound``) contra la
base de verdad; lo único de mentira es el grafo, que aquí es un
``RecordingPipeline`` que apunta lo que recibe y puede bloquearse o fallar.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import InboundEvent

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Message,
    MessageDirection,
    Tenant,
    TenantPlan,
    TenantStatus,
)


class RecordingPipeline:
    """El grafo de mentira. Apunta cada estado; ``block`` lo deja esperando
    hasta que la prueba lo suelte (un turno largo) y ``fail_times`` lo hace
    fallar las primeras veces (un turno que se reintenta)."""

    def __init__(self, *, block: asyncio.Event | None = None, fail_times: int = 0) -> None:
        self.calls: list[dict[str, Any]] = []
        self.started = asyncio.Event()
        self.block = block
        self.fail_times = fail_times

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(dict(state))
        self.started.set()
        if self.block is not None:
            await self.block.wait()
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("el proveedor se cayó a mitad del turno")
        return {"intent": "info", "response": "ok", "tool_calls": []}


@dataclass
class World:
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    agent_id: uuid.UUID
    provider_identifier: str
    extra: dict[str, Any] = field(default_factory=dict)

    def event(
        self, content: str = "hola", *, user: str = "+34600111222", **kw: Any
    ) -> InboundEvent:
        return InboundEvent(
            tenant_id=self.tenant_id,
            channel_id=self.channel_id,
            user_id=user,
            content=content,
            provider_message_id=kw.pop("wamid", f"wamid.{uuid.uuid4().hex}"),
            **kw,
        )


async def make_world(
    db_session: Any,
    *,
    tenant_status: TenantStatus = TenantStatus.ACTIVE,
    channel_status: ChannelStatus = ChannelStatus.ACTIVE,
    channel_config: dict[str, Any] | None = None,
    agent_config: AgentConfigStatus | None = AgentConfigStatus.ACTIVE,
    policies: dict[str, Any] | None = None,
    tenant_id: uuid.UUID | None = None,
) -> World:
    """Un cliente (o el que se pase) con un número que contesta su agente.

    ``agent_config=None`` deja el agente sin ninguna versión (borrador);
    ``STAGED`` o ``ARCHIVED`` lo dejan con versiones pero ninguna publicada.
    """
    if tenant_id is None:
        tenant_id = uuid.uuid4()
        db_session.add(
            Tenant(
                id=tenant_id,
                name="Barbería Cultor",
                slug=f"cultor-{tenant_id.hex[:8]}",
                plan=TenantPlan.PRO,
                status=tenant_status,
            )
        )
        await db_session.commit()
    sm = get_sessionmaker()
    identifier = f"+3460{uuid.uuid4().int % 10**7:07d}"
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        agent = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name="Recepción")
        s.add(agent)
        await s.flush()
        if agent_config is not None:
            s.add(
                AgentConfig(
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    version=1,
                    status=agent_config,
                    system_prompt_rendered="Eres la recepción de la barbería.",
                    tools=[],
                    channels=[],
                    policies=dict(policies or {}),
                    created_by="test",
                )
            )
        channel = Channel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=identifier,
            config=dict(channel_config or {"phone_number_id": "PN"}),
            status=channel_status,
            agent_id=agent.id,
        )
        s.add(channel)
        await s.commit()
        return World(
            tenant_id=tenant_id,
            channel_id=channel.id,
            agent_id=agent.id,
            provider_identifier=identifier,
        )


async def conversation_of(world: World, user: str = "+34600111222") -> Conversation:
    from nexus_api.db.models import Customer

    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        row = (
            await s.execute(
                sa.select(Conversation)
                .join(Customer, Customer.id == Conversation.customer_id)
                .where(Conversation.channel_id == world.channel_id, Customer.identifier == user)
            )
        ).scalar_one()
        s.expunge(row)
        return row


async def inbound_rows(world: World) -> list[Message]:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        rows = list(
            (
                await s.execute(
                    sa.select(Message)
                    .where(Message.direction == MessageDirection.INBOUND)
                    .order_by(Message.created_at, Message.id)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            s.expunge(row)
        return rows


async def outbound_rows(world: World) -> list[Message]:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        rows = list(
            (
                await s.execute(
                    sa.select(Message)
                    .where(Message.direction == MessageDirection.OUTBOUND)
                    .order_by(Message.created_at, Message.id)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            s.expunge(row)
        return rows


async def scalar(world: World, statement: Any, params: dict[str, Any] | None = None) -> Any:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        return await s.scalar(statement, params or {})


def wallet_closed(monkeypatch: Any, *, closed: bool = True) -> None:
    """La bolsa del cliente a cero: la puerta de saldo cierra."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "nexus_api.metering.wallet.allow_channel_turn", AsyncMock(return_value=not closed)
    )
