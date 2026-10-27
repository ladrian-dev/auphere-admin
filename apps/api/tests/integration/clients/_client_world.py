"""Lo común de las pruebas del cliente y de su ficha (spec 047, fase 7: de la T062 a la T072).

Un mundo pequeño sobre ``console_world``:

- partners con sitio para varios clientes y, si se pide, con la consola nueva;
- clientes creados por la ruta de verdad (``POST /console/clients``), así que
  nacen con su ficha;
- agentes con o sin versión publicada y con o sin canal, para que el estado
  visible salga de ``agent_lifecycle`` y no de una cifra puesta a mano;
- consumo en ``usage_ledger`` y la bolsa en ``partner_allocations``, que es de
  donde la lee la consola hasta la ola 7.

No es un test (empieza por ``_``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Partner,
    PartnerAllocation,
    PartnerTenant,
    UsageLedger,
)


async def roomy(
    db_session: AsyncSession, world: dict[str, Any], *, v2: tuple[str, ...] = ("a",)
) -> None:
    """Sitio para varios clientes; la consola nueva para los partners de ``v2``."""
    for label in ("a", "b"):
        partner = await db_session.get(Partner, world[label]["partner_id"])
        assert partner is not None
        partner.max_clients = 50
        if label in v2:
            partner.console_v2_enabled_at = datetime.now(UTC)
            partner.console_v2_enabled_by = "operator:tests@auphere.com"
    await db_session.commit()
    # El saldo recargado de la cuenta, que es lo que paga un turno (spec 033):
    # sin él todos los clientes saldrían «Sin saldo».
    from tests.conftest import give_recharged_balance

    for label in ("a", "b"):
        await give_recharged_balance(world[label]["partner_id"], 100_000_000)


async def new_client(client: Any, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    body.setdefault("niche", "Barbería de barrio")
    resp = await client.post("/console/clients", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def tenant_of(db_session: AsyncSession, partner_id: uuid.UUID, ref: str) -> uuid.UUID:
    async with db_session.begin():
        tenant_id = await db_session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == partner_id, PartnerTenant.external_client_ref == ref
            )
        )
    assert tenant_id is not None
    return tenant_id


def _number() -> str:
    return f"+3460{uuid.uuid4().int % 10**7:07d}"


async def add_agent(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    *,
    published: bool = True,
    channel: str | None = "active",
    created_at: datetime | None = None,
) -> dict[str, uuid.UUID | None]:
    """Un agente del cliente. ``published``: con versión activa. ``channel``:
    el estado de su WhatsApp (``None``, sin canal)."""
    async with tenant_scoped_session(db_session, tenant_id):
        agent = Agent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            status="active",
            created_at=created_at or datetime.now(UTC),
        )
        db_session.add(agent)
        await db_session.flush()
        if published:
            last = await db_session.scalar(sa.select(sa.func.max(AgentConfig.version)))
            db_session.add(
                AgentConfig(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    version=(last or 0) + 1,
                    status=AgentConfigStatus.ACTIVE,
                    system_prompt_rendered=f"Eres {name}.",
                    channels=[],
                    tools=[],
                    policies={},
                    created_by="tests",
                    promoted_at=datetime.now(UTC),
                    promoted_by="tests",
                )
            )
        channel_id: uuid.UUID | None = None
        if channel is not None:
            row = Channel(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=_number(),
                config={"phone_number_id": "TESTS"},
                status=ChannelStatus(channel),
                agent_id=agent.id,
            )
            db_session.add(row)
            channel_id = row.id
        await db_session.flush()
    return {"agent_id": agent.id, "channel_id": channel_id}


async def set_bag(
    db_session: AsyncSession,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    cap: int,
    remaining: int,
) -> None:
    """La bolsa en créditos (1 crédito = cien milésimas de US$)."""
    row = await db_session.scalar(
        sa.select(PartnerAllocation).where(
            PartnerAllocation.partner_id == partner_id, PartnerAllocation.tenant_id == tenant_id
        )
    )
    if row is None:
        db_session.add(
            PartnerAllocation(
                partner_id=partner_id, tenant_id=tenant_id, cap=cap, remaining=remaining
            )
        )
    else:
        row.cap = cap
        row.remaining = remaining
    await db_session.commit()


async def add_spend(
    db_session: AsyncSession,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    credits: int,
    *,
    agent_id: uuid.UUID | None = None,
    at: datetime | None = None,
) -> None:
    db_session.add(
        UsageLedger(
            partner_id=partner_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            qty=credits,
            bucket="purchased",
            kind="debit",
            idempotency_key=f"tests:{uuid.uuid4().hex}",
            created_at=at or datetime.now(UTC),
        )
    )
    await db_session.commit()


async def add_conversations(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    count: int,
    escalated: int = 0,
    at: datetime | None = None,
) -> None:
    """``count`` conversaciones de clientes finales en el canal; ``escalated``
    de ellas pasaron a una persona."""
    when = at or datetime.now(UTC) - timedelta(minutes=5)
    async with tenant_scoped_session(db_session, tenant_id):
        for i in range(count):
            customer = Customer(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                identifier=f"+5491100{uuid.uuid4().int % 10**6:06d}",
                name=f"Contacto {i}",
            )
            db_session.add(customer)
            await db_session.flush()
            db_session.add(
                Conversation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    customer_id=customer.id,
                    status=ConversationStatus.ESCALATED
                    if i < escalated
                    else ConversationStatus.CLOSED,
                    created_at=when,
                    last_inbound_at=when,
                )
            )
        await db_session.flush()


__all__ = [
    "add_agent",
    "add_conversations",
    "add_spend",
    "new_client",
    "roomy",
    "set_bag",
    "tenant_of",
]
