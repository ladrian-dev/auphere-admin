"""Customer / conversation / message persistence used by the pipeline.

All functions assume the caller has already entered ``tenant_scoped_session``
on ``session`` — they do not call ``apply_tenant_to_session`` themselves.
RLS guarantees the rows we write/read are scoped to ``tenant_id``.

Block B gotcha #3: after mutating ORM attributes (status, promoted_at,
updated_at) we ``await session.refresh(obj)`` so subsequent serialisation
doesn't trip MissingGreenlet on a lazy load.
"""

from __future__ import annotations

import uuid
from typing import Any

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_customer(
    session: AsyncSession,
    *,
    identifier: str,
    name: str | None = None,
) -> Customer:
    require_current_tenant()
    stmt = select(Customer).where(Customer.identifier == identifier)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    customer = Customer(
        tenant_id=require_current_tenant(),
        identifier=identifier,
        name=name,
        preferences={},
    )
    session.add(customer)
    await session.flush()
    await session.refresh(customer)
    return customer


async def upsert_conversation_for_customer(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    customer_id: uuid.UUID,
) -> Conversation:
    """Return the open conversation for this customer/channel, opening one if needed."""
    require_current_tenant()
    stmt = (
        select(Conversation)
        .where(
            Conversation.channel_id == channel_id,
            Conversation.customer_id == customer_id,
            Conversation.status == ConversationStatus.OPEN,
        )
        .limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    conv = Conversation(
        tenant_id=require_current_tenant(),
        channel_id=channel_id,
        customer_id=customer_id,
        status=ConversationStatus.OPEN,
    )
    session.add(conv)
    await session.flush()
    await session.refresh(conv)
    return conv


async def persist_inbound_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    content: str,
    intent: str | None = None,
    trace_id: str | None = None,
) -> Message:
    require_current_tenant()
    msg = Message(
        tenant_id=require_current_tenant(),
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND,
        content=content,
        intent=intent,
        trace_id=trace_id,
        tool_calls=[],
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg


async def persist_outbound_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    content: str,
    intent: str | None,
    model: str | None,
    tool_calls: list[dict[str, Any]],
    trace_id: str | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
) -> Message:
    require_current_tenant()
    msg = Message(
        tenant_id=require_current_tenant(),
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        content=content,
        intent=intent,
        model=model,
        tool_calls=list(tool_calls),
        trace_id=trace_id,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg
