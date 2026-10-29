"""Erase what Instagram and Messenger brought in — spec 049, requirements 5.3 and 5.6.

Meta's Platform Terms and Auphere's privacy policy («Cómo pedir que borremos
tus datos»): when a business disconnects the channel, or removes the app,
the messages and profile data received through it are deleted or
anonymised within 30 days; a person who asks gets the same, for them.

**Anonymised, not deleted.** Conversations, customers and messages are
referenced from appointments, queues, sales and the audit trail with
``RESTRICT`` foreign keys; deleting the rows would either fail or take
legitimate business records (an appointment that happened) with them. So
what identifies or quotes the person is emptied, and the rows stay as
shapes: «[borrado]» where the text was, ``erased:<uuid>`` where the IGSID /
PSID was. Agent memories and contact notes about the person are deleted
outright — they exist only to describe them.

Runs inside a tenant-scoped session (RLS decides what is visible).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Channel, Conversation, Customer, Message

RETENTION_AFTER_DISCONNECT = timedelta(days=30)
ERASED_TEXT = "[borrado]"


async def erase_customer_in_channel(
    session: AsyncSession, *, channel_id: uuid.UUID, customer_id: uuid.UUID
) -> int:
    """Anonymise one person's data received through one channel. Returns the
    number of messages emptied."""
    require_current_tenant()
    conversation_ids = (
        await session.scalars(
            sa.select(Conversation.id).where(
                Conversation.channel_id == channel_id, Conversation.customer_id == customer_id
            )
        )
    ).all()
    emptied = 0
    if conversation_ids:
        result = await session.execute(
            sa.update(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .values(
                content=ERASED_TEXT,
                media_transcript=None,
                media_s3_key=None,
                media_filename=None,
                interactive_payload=None,
                tool_calls=[],
            )
            .execution_options(synchronize_session=False)
        )
        emptied = int(getattr(result, "rowcount", 0) or 0)
        await session.execute(
            sa.update(Conversation)
            .where(Conversation.id.in_(conversation_ids))
            .values(takeover_context=None)
            .execution_options(synchronize_session=False)
        )

    # The person exists only through this channel when no other channel has
    # a conversation with them: then their identity goes too.
    elsewhere = await session.scalar(
        sa.select(sa.func.count())
        .select_from(Conversation)
        .where(Conversation.customer_id == customer_id, Conversation.channel_id != channel_id)
    )
    if not elsewhere:
        await session.execute(
            sa.text("DELETE FROM agent_memories WHERE customer_id = :c"), {"c": str(customer_id)}
        )
        await session.execute(
            sa.text("DELETE FROM contact_notes WHERE customer_id = :c"), {"c": str(customer_id)}
        )
        await session.execute(
            sa.update(Customer)
            .where(Customer.id == customer_id)
            .values(identifier=f"erased:{customer_id}", name=None, preferences={})
            .execution_options(synchronize_session=False)
        )
    await session.flush()
    return emptied


async def purge_channel(session: AsyncSession, channel: Channel) -> int:
    """Anonymise every person of a disconnected channel. Returns how many."""
    require_current_tenant()
    customer_ids = (
        await session.scalars(
            sa.select(Conversation.customer_id)
            .where(Conversation.channel_id == channel.id)
            .distinct()
        )
    ).all()
    for customer_id in customer_ids:
        await erase_customer_in_channel(session, channel_id=channel.id, customer_id=customer_id)
    channel.config = {**(channel.config or {}), "purged_at": datetime.now(UTC).isoformat()}
    channel.config_encrypted = None
    await session.flush()
    return len(customer_ids)


def due_for_purge(channel: Channel, *, now: datetime) -> bool:
    cfg = channel.config or {}
    if cfg.get("purged_at") or not cfg.get("disconnected_at"):
        return False
    try:
        disconnected_at = datetime.fromisoformat(str(cfg["disconnected_at"]))
    except ValueError:
        return False
    return now - disconnected_at >= RETENTION_AFTER_DISCONNECT
