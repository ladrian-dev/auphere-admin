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
    MessageStatus,
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
    provider_message_id: str | None = None,
    media_kind: str | None = None,
    media_s3_key: str | None = None,
    media_mime: str | None = None,
    media_size_bytes: int | None = None,
    media_filename: str | None = None,
    reaction_emoji: str | None = None,
    reaction_target_wamid: str | None = None,
    context_message_id: str | None = None,
) -> Message:
    """Persist a customer-side message.

    Block N: additionally captures the WhatsApp-native fields
    propagated by the inbound webhook (wamid, media handle, reaction
    target, quoted context). The wamid is the durable dedupe key — the
    UNIQUE partial index on ``messages.provider_message_id`` protects
    against accidental re-ingestion downstream of the consumer.
    """
    require_current_tenant()
    msg = Message(
        tenant_id=require_current_tenant(),
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND,
        content=content,
        intent=intent,
        trace_id=trace_id,
        tool_calls=[],
        provider_message_id=provider_message_id,
        media_kind=media_kind,
        media_s3_key=media_s3_key,
        media_mime=media_mime,
        media_size_bytes=media_size_bytes,
        media_filename=media_filename,
        reaction_emoji=reaction_emoji,
        reaction_target_wamid=reaction_target_wamid,
        context_message_id=context_message_id,
        # Inbound messages don't carry a SENT/PENDING semantic — the
        # historical default of ``SENT`` works because the operator panel
        # only ever cares about "did the agent reply yet". Leave it.
        status=MessageStatus.SENT,
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
    status: MessageStatus = MessageStatus.PENDING,
    interactive_payload: dict[str, Any] | None = None,
) -> Message:
    """Persist the assistant's reply.

    Block C relied on the column default ``status='sent'`` because nothing
    drained outbound. Block F flips the default at the call site to
    ``PENDING`` so the new outbound dispatcher actually has work to do —
    the WhatsApp send happens *after* persistence. Callers (tests) can
    still pass ``status=MessageStatus.SENT`` to bypass the dispatcher.

    ``interactive_payload`` is set when this row represents a native
    WhatsApp interactive component (reply buttons / list / cta_url).
    The outbound dispatcher detects it and routes through
    ``adapter.send_interactive``. ``content`` should still be set to a
    sensible fallback text (typically the component's ``body``) so the
    operator panel and Langfuse traces have something human-readable.
    """
    require_current_tenant()
    msg = Message(
        tenant_id=require_current_tenant(),
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        status=status,
        content=content,
        intent=intent,
        model=model,
        tool_calls=list(tool_calls),
        trace_id=trace_id,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        interactive_payload=interactive_payload,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg
