"""What counts as customer traffic for the partner console.

The Playground creates a ``web`` channel with ``provider="qa_playground"``
and conversations on it (``api/qa.py``). Those rows are real — the runs
need them — but they are not customers. Every console figure that claims
to describe customers (onboarding steps, home counters, the conversations
lane) filters through here so the three never disagree again.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from nexus_api.db.models import Channel, Conversation
from nexus_api.db.models.channel import QA_PLAYGROUND_PROVIDER


def customer_facing_channel() -> sa.ColumnElement[bool]:
    """Predicate on ``Channel``: anything that is not the Playground."""
    return Channel.provider != QA_PLAYGROUND_PROVIDER


def customer_conversation_ids() -> sa.Select[tuple[uuid.UUID]]:
    """Sub-select of conversation ids that live on a customer-facing channel."""
    return (
        sa.select(Conversation.id)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(customer_facing_channel())
    )


__all__ = ["QA_PLAYGROUND_PROVIDER", "customer_conversation_ids", "customer_facing_channel"]
