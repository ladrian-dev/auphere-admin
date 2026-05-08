"""Shared fixtures for MCP server integration tests.

Each test runs against the real Postgres test DB + fakeredis. Tools are
invoked via ``MCPRegistry.dispatch`` which is exactly what the worker
uses. Tenant context is established per-test so RLS policies apply.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from nexus_mcp import MCPRegistry, build_default_registry
from nexus_mcp.registry import reset_default_registry

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    KGNode,
    Tenant,
    TenantPlan,
)


@pytest_asyncio.fixture
async def mcp_registry() -> AsyncIterator[MCPRegistry]:
    reset_default_registry()
    yield build_default_registry()
    reset_default_registry()


@pytest_asyncio.fixture
async def two_tenants(db_session) -> dict[str, uuid.UUID]:
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    db_session.add_all(
        [
            Tenant(id=a_id, name="MCP A", slug=f"mcp-a-{a_id.hex[:6]}", plan=TenantPlan.PRO),
            Tenant(id=b_id, name="MCP B", slug=f"mcp-b-{b_id.hex[:6]}", plan=TenantPlan.PRO),
        ]
    )
    await db_session.commit()
    return {"a": a_id, "b": b_id}


async def seed_customer(db_session, *, tenant_id: uuid.UUID, identifier: str = "c1") -> Customer:
    cust = Customer(tenant_id=tenant_id, identifier=identifier, preferences={})
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)
    return cust


async def seed_channel_and_conversation(
    db_session,
    *,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    provider_identifier: str = "wa-1",
) -> tuple[Channel, Conversation]:
    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=provider_identifier,
        config={},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=ch.id,
        customer_id=customer_id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return ch, conv


async def seed_barber(
    db_session,
    *,
    tenant_id: uuid.UUID,
    name: str = "Luis",
    commission_pct: float = 0.4,
    model: str = "commission",
) -> KGNode:
    node = KGNode(
        tenant_id=tenant_id,
        label="Barber",
        properties={
            "name": name,
            "commission_model": model,
            "commission_pct": commission_pct,
        },
    )
    db_session.add(node)
    await db_session.commit()
    await db_session.refresh(node)
    return node


def all_whitelist() -> list[str]:
    """Returns the 21 tool names — handy when a test doesn't care about
    whitelist filtering and wants every tool dispatchable."""
    from nexus_mcp.servers.booking.tools import BOOKING_TOOLS
    from nexus_mcp.servers.client.tools import CLIENT_TOOLS
    from nexus_mcp.servers.commission.tools import COMMISSION_TOOLS
    from nexus_mcp.servers.escalate.tools import ESCALATE_TOOLS
    from nexus_mcp.servers.notification.tools import NOTIFICATION_TOOLS
    from nexus_mcp.servers.queue.tools import QUEUE_TOOLS

    return [
        *(t.name for t in ESCALATE_TOOLS),
        *(t.name for t in CLIENT_TOOLS),
        *(t.name for t in BOOKING_TOOLS),
        *(t.name for t in QUEUE_TOOLS),
        *(t.name for t in COMMISSION_TOOLS),
        *(t.name for t in NOTIFICATION_TOOLS),
    ]


# Re-exported for tests that need to enter tenant_context manually.
__all__ = [
    "all_whitelist",
    "seed_barber",
    "seed_channel_and_conversation",
    "seed_customer",
    "tenant_context",
]
