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
from datetime import datetime
from typing import Any

import structlog
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.services import inbox_lifecycle
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


async def upsert_customer(
    session: AsyncSession,
    *,
    identifier: str,
    name: str | None = None,
    bsuid: str | None = None,
    phone: str | None = None,
    username: str | None = None,
) -> Customer:
    """Find or create the person behind an inbound (spec 050, D2).

    ``identifier`` keeps its meaning and is never rewritten: the phone when
    the person had one at creation, the BSUID otherwise. Resolution:

    1. by ``bsuid``;
    2. by phone (``phone`` column or a phone-shaped ``identifier``) — and,
       since Meta gave both together, the BSUID is attached to that row;
    3. by ``identifier`` (every channel that is not WhatsApp, and rows from
       before the BSUID existed);
    4. otherwise a new row.

    Two existing rows are never merged: if the BSUID and the phone point at
    different people, the BSUID's wins and the conflict is logged.
    """
    require_current_tenant()
    found: Customer | None = None
    phone_taken = False
    if bsuid:
        found = await session.scalar(select(Customer).where(Customer.bsuid == bsuid))
        if found is not None and phone and found.phone != phone:
            other = await session.scalar(
                select(Customer.id)
                .where((Customer.phone == phone) | (Customer.identifier == phone))
                .where(Customer.id != found.id)
                .limit(1)
            )
            if other is not None:
                # Two people Meta now describes as one: keep both untouched.
                phone_taken = True
                log.warning("customer.identity_conflict", reason="bsuid_and_phone_differ")
    if found is None and phone:
        found = await session.scalar(
            select(Customer)
            .where((Customer.phone == phone) | (Customer.identifier == phone))
            .order_by(Customer.created_at)
            .limit(1)
        )
    if found is None:
        found = await session.scalar(select(Customer).where(Customer.identifier == identifier))
    if found is not None:
        changed = False
        if bsuid and found.bsuid is None:
            found.bsuid, changed = bsuid, True
        if phone and found.phone is None and not phone_taken:
            found.phone, changed = phone, True
        if username and found.username != username:
            found.username, changed = username, True
        if changed:
            await session.flush()
        return found
    customer = Customer(
        tenant_id=require_current_tenant(),
        identifier=identifier,
        name=name,
        bsuid=bsuid,
        phone=phone,
        username=username,
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
    reopened_by: str = inbox_lifecycle.CONTACT,
) -> Conversation:
    """The conversation of this customer on this number (spec 030, D11).

    One row per contact and number: the **latest** row, whatever its status.
    ``ESCALATED`` keeps waiting in the same row (before D11 only ``OPEN`` was
    looked up, so the next message split a waiting conversation in two).
    ``CLOSED`` — resolved from the Inbox — reopens with the agent answering;
    ``reopened_by`` says who brought it back (the contact by default; a
    business-initiated send passes its own actor).
    """
    require_current_tenant()
    stmt = (
        select(Conversation)
        .where(
            Conversation.channel_id == channel_id,
            Conversation.customer_id == customer_id,
        )
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        if existing.status == ConversationStatus.CLOSED:
            await inbox_lifecycle.reopen(session, existing, actor=reopened_by)
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


async def _touch_last_message(
    session: AsyncSession, conversation_id: uuid.UUID, at: datetime
) -> None:
    """``conversations.last_message_at`` — what the Inbox sorts by (spec 030).
    Only moves forward: a late folded bubble never pulls it back."""
    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=func.greatest(func.coalesce(Conversation.last_message_at, at), at))
        .execution_options(synchronize_session=False)
    )


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
    await _touch_last_message(session, conversation_id, msg.created_at)
    return msg


#: Spec 047 (0176): ``messages.origin`` of a reply, from who wrote it.
_ORIGIN_BY_ACTOR: dict[str, str] = {
    "agent": "agent",
    "system": "system",
    "member": "business_person",
    "operator": "business_person",
}


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
    outcome_overall: str | None = None,
    outcome_retries: int | None = None,
    outcome_feedback: str | None = None,
    actor_kind: str = "agent",
    actor_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
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

    Spec 047 (T035, requisito 1.3): inside a channel turn the reply is an
    effect. Its ``turn_effects`` key and its row go in the caller's
    transaction together, so a retried turn that writes its answer again gets
    the row of the first attempt back instead of a second message to the
    contact. Outside a turn (operator sends, the Playground) nothing changes.
    """
    require_current_tenant()
    from nexus_worker.runtime.turn_effects import claim_reply, record_reply
    from nexus_worker.runtime.turns import current_turn

    reply = await claim_reply(session)
    if reply is not None and reply[1] is not None:
        prior = await session.get(Message, reply[1])
        if prior is not None:
            return prior
    turn = current_turn()
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
        outcome_overall=outcome_overall,
        outcome_retries=outcome_retries,
        outcome_feedback=outcome_feedback,
        actor_kind=actor_kind,
        actor_id=actor_id,
        # Spec 030: which of the client's agents wrote it.
        agent_id=agent_id,
        # Spec 047 (0176): who wrote it and the turn it answers.
        origin=_ORIGIN_BY_ACTOR.get(actor_kind),
        turn_id=turn.turn_id if turn is not None else None,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    if reply is not None:
        await record_reply(session, reply[0], msg.id)
    await _touch_last_message(session, conversation_id, msg.created_at)
    return msg
