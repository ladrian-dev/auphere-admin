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
    AgentConfig,
    AgentConfigStatus,
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
    db_session: Any,
    status: TenantStatus,
    *,
    agent: AgentConfigStatus | None = AgentConfigStatus.ACTIVE,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Tenant + channel, with an agent_config in ``agent`` status.

    ``agent=None`` builds a **send-only** tenant: no agent_config row ever,
    the shape of a client that only uses the outbound template API.
    """
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

    if agent is not None:
        db_session.add(
            AgentConfig(
                tenant_id=tenant_id,
                version=1,
                status=agent,
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


async def test_send_only_tenant_skips_pipeline_without_erroring(
    db_session: Any,
) -> None:
    """A tenant that never had an agent_config uses the outbound template
    API only. Its customers' replies still arrive, and they must be a
    skip (acked) — NOT an IsolationViolation that leaves the Redis entry
    pending forever and floods the logs with ERROR."""
    tenant_id, channel_id = await _make_tenant_with_channel(
        db_session, TenantStatus.ACTIVE, agent=None
    )
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910005",
            content="gracias, ya pagué",
        ),
        pipeline=pipeline,
    )

    assert pipeline.calls == [], "a send-only tenant has nothing to run"
    assert result["skipped"] == "no_agent"
    # Still persisted: the operator panel shows the customer's reply.
    assert await _count_inbound(tenant_id) == 1


async def test_tenant_with_only_archived_agent_is_not_treated_as_send_only(
    db_session: Any,
) -> None:
    """Having versions but no ACTIVE one is a BROKEN agent, not a
    send-only client. It must keep reaching the pipeline, where the loader
    raises IsolationViolation and the consumer logs a real error (the
    sentinel pipeline here stands in for that path)."""
    tenant_id, channel_id = await _make_tenant_with_channel(
        db_session, TenantStatus.ACTIVE, agent=AgentConfigStatus.ARCHIVED
    )
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910006",
            content="hola?",
        ),
        pipeline=pipeline,
    )

    assert result.get("skipped") is None, "a broken agent must not be silenced"
    assert len(pipeline.calls) == 1


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


# ── Bloque C: resume-with-context briefing ──────────────────────────────────


async def _seed_conversation_with_takeover(
    db_session: Any,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    user_id: str,
    takeover_context: dict[str, Any],
    operator_messages: list[str],
) -> uuid.UUID:
    """Seed a conversation that the operator paused, sent N messages on,
    then resumed — the state the dispatcher should encounter on the
    first inbound after resume. ``agent_active=True`` to simulate the
    post-resume state; ``takeover_context`` is still set because the
    PATCH .../agent endpoint leaves it for the dispatcher to consume."""
    customer = Customer(tenant_id=tenant_id, identifier=user_id, preferences={})
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
        agent_active=True,
        takeover_context=takeover_context,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    from nexus_api.db.models import MessageStatus

    for content in operator_messages:
        db_session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.SENT,
                content=content,
                tool_calls=[],
                actor_kind="operator",
            )
        )
    await db_session.commit()
    return conv.id


async def test_takeover_context_prepended_to_user_message_on_resume(
    db_session: Any,
) -> None:
    """First turn after operator resumes: the briefing block lives at the
    top of ``user_message`` and the customer's text lives below it."""
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ACTIVE)
    from datetime import UTC, datetime, timedelta

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await _seed_conversation_with_takeover(
        db_session,
        tenant_id=tenant_id,
        channel_id=channel_id,
        user_id="+5699910100",
        takeover_context={
            "reason": "queja del cliente",
            "notes": "estaba enojado por la demora",
            "started_at": past,
            "operator_id": "luis1234",
        },
        operator_messages=[
            "Lamento la demora, ya estoy revisando",
            "Tu pedido sale hoy a las 18hs",
        ],
    )
    pipeline = _RecordingPipeline()

    result = await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910100",
            content="ok, gracias",
        ),
        pipeline=pipeline,
    )

    assert result.get("skipped") is None
    assert len(pipeline.calls) == 1
    state, _config = pipeline.calls[0]
    msg = state["user_message"]
    assert "[Contexto interno" in msg
    assert "queja del cliente" in msg
    assert "estaba enojado por la demora" in msg
    assert "Lamento la demora, ya estoy revisando" in msg
    assert "Tu pedido sale hoy a las 18hs" in msg
    assert "[Mensaje del cliente]" in msg
    assert "ok, gracias" in msg
    # Briefing must come BEFORE the customer's message.
    assert msg.index("[Contexto interno") < msg.index("[Mensaje del cliente]")


async def test_takeover_context_cleared_after_successful_pipeline_run(
    db_session: Any,
) -> None:
    """After the briefing has been delivered once, ``takeover_context``
    is set to NULL so the next turn doesn't replay it."""
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ACTIVE)
    from datetime import UTC, datetime, timedelta

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    conv_id = await _seed_conversation_with_takeover(
        db_session,
        tenant_id=tenant_id,
        channel_id=channel_id,
        user_id="+5699910101",
        takeover_context={
            "reason": "x",
            "started_at": past,
        },
        operator_messages=["hola"],
    )
    pipeline = _RecordingPipeline()

    await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910101",
            content="continuá",
        ),
        pipeline=pipeline,
    )

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        ctx = (
            await session.execute(
                sa.select(Conversation.takeover_context).where(Conversation.id == conv_id)
            )
        ).scalar_one()
    assert ctx is None


async def test_no_takeover_context_passes_user_message_untouched(
    db_session: Any,
) -> None:
    """Control case — when there is no takeover context, the user_message
    passed to the pipeline is exactly what the customer wrote (no
    briefing prepended)."""
    tenant_id, channel_id = await _make_tenant_with_channel(db_session, TenantStatus.ACTIVE)
    await _seed_conversation(
        db_session,
        tenant_id=tenant_id,
        channel_id=channel_id,
        user_id="+5699910102",
        agent_active=True,
    )
    pipeline = _RecordingPipeline()

    await process_inbound(
        InboundEvent(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id="+5699910102",
            content="hola normal",
        ),
        pipeline=pipeline,
    )

    state, _config = pipeline.calls[0]
    assert state["user_message"] == "hola normal"
    assert "[Contexto interno" not in state["user_message"]
