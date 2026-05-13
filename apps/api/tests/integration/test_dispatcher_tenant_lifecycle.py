"""Block M.1 — runtime enforcement of TenantStatus on inbound dispatch.

The dispatcher persists every inbound for audit but mutes the agent for
``PAUSED`` and ``ARCHIVED`` tenants. These tests verify both halves of the
contract:

- inbound is persisted regardless of status (panel surfaces the message);
- the LangGraph pipeline is invoked ONLY for ``ACTIVE`` tenants.

The fixture builds a real channel + conversation row so the persistence
side runs against the actual schema. The pipeline is a sentinel — it
records calls and refuses to run side effects. This is the right unit
of mocking for a dispatcher test: we are not testing the pipeline, we
are testing the *gate* in front of it.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _RecordingPipeline:
    """A pipeline stand-in. ``ainvoke`` would fail loudly if the dispatcher
    forgets the gate — we use ``called`` as the assertion surface."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append((state, config or {}))
        # The real pipeline returns a dict-like result; the dispatcher only
        # reads ``intent``/``response``/``tool_calls`` from it. Empty is fine.
        return {"intent": "info", "response": "ok", "tool_calls": []}


async def _make_tenant_with_channel(
    db_session: Any, status: TenantStatus
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"M1-{status.value}",
            slug=f"m1-{status.value}-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
            status=status,
        )
    )
    await db_session.commit()

    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=f"m1-{tenant_id.hex[:6]}",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return tenant_id, channel.id


async def _count_inbound(tenant_id: uuid.UUID) -> int:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(
                Message.direction == MessageDirection.INBOUND,
            )
        )
        return int(result.scalar_one())


async def test_active_tenant_invokes_pipeline(db_session: Any) -> None:
    """Control case — happy path is preserved."""
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ACTIVE)
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910001",
            content="hola",
        ),
        pipeline=pipeline,
    )

    assert len(pipeline.calls) == 1, "active tenants must drive the pipeline"
    assert result.get("skipped") is None
    assert await _count_inbound(tenant_id) == 1


async def test_paused_tenant_persists_inbound_but_skips_pipeline(
    db_session: Any,
) -> None:
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.PAUSED)
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910002",
            content="estamos abiertos?",
        ),
        pipeline=pipeline,
    )

    assert pipeline.calls == [], "paused tenants must NOT run the pipeline"
    assert result["skipped"] == "tenant_inactive"
    assert result["tenant_status"] == "paused"
    # Inbound is captured for audit + panel surfaces the message.
    assert await _count_inbound(tenant_id) == 1


async def test_archived_tenant_persists_inbound_but_skips_pipeline(
    db_session: Any,
) -> None:
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ARCHIVED)
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910003",
            content="hello?",
        ),
        pipeline=pipeline,
    )

    assert pipeline.calls == [], "archived tenants must NOT run the pipeline"
    assert result["skipped"] == "tenant_inactive"
    assert result["tenant_status"] == "archived"
    assert await _count_inbound(tenant_id) == 1


async def test_unknown_tenant_returns_skipped_without_raising(
    db_session: Any,
) -> None:
    """A stale Redis entry for a tenant that no longer exists must NOT
    crash the consumer loop — log + skip + ack is the desired path."""
    pipeline = _RecordingPipeline()
    # No tenant row created. The channel UUID is also synthetic.
    result = await process_inbound(
        InboundEvent(
            tenant_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            user_id="+5699910004",
            content="ghost",
        ),
        pipeline=pipeline,
    )
    assert pipeline.calls == []
    assert result == {"skipped": "tenant_unknown"}


# ── Block M.3: per-conversation human takeover ──────────────────────────────


async def _seed_conversation(
    db_session: Any,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    user_id: str,
    agent_active: bool,
) -> uuid.UUID:
    """Pre-create the conversation row with the takeover flag set, then
    feed an inbound from the same user_id so the dispatcher's
    ``upsert_conversation_for_customer`` returns this row instead of
    opening a new one."""
    customer = Customer(tenant_id=tenant_id, identifier=user_id, preferences={})
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
        agent_active=agent_active,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv.id


async def test_conversation_with_agent_inactive_skips_pipeline(
    db_session: Any,
) -> None:
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ACTIVE)
    conv_id = await _seed_conversation(
        db_session,
        tenant_id=tenant_id,
        channel_id=channel_id,
        user_id="+5699910005",
        agent_active=False,
    )
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910005",
            content="el operador me responde",
        ),
        pipeline=pipeline,
    )

    assert pipeline.calls == [], "human-takeover conversations must NOT drive the pipeline"
    assert result["skipped"] == "human_takeover"
    assert result["conversation_id"] == str(conv_id)
    # Inbound persisted for audit + panel surface.
    assert await _count_inbound(tenant_id) == 1


async def test_conversation_with_agent_active_still_invokes_pipeline(
    db_session: Any,
) -> None:
    """Control case: a conversation where the agent is on (default) still
    runs through the pipeline even though the M.3 check is now in place."""
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ACTIVE)
    await _seed_conversation(
        db_session,
        tenant_id=tenant_id,
        channel_id=channel_id,
        user_id="+5699910006",
        agent_active=True,
    )
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910006",
            content="hola de vuelta",
        ),
        pipeline=pipeline,
    )

    assert len(pipeline.calls) == 1
    assert result.get("skipped") is None
