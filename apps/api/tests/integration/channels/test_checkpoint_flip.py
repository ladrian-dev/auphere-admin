"""Verifies block F's checkpoint-status flip.

Block C wrote outbound rows with the column default ``status='sent'``
because no dispatcher drained them. Block F:

- ``persist_outbound_message`` now defaults to ``MessageStatus.PENDING``.
- The pipeline ``checkpoint`` node uses that helper.

These tests assert the helper writes 'pending' by default, which is what
the outbound dispatcher expects to find.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.persistence.messages import persist_outbound_message

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Message,
    MessageDirection,
    MessageStatus,
)

pytestmark = pytest.mark.asyncio


async def _last_outbound(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Message:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.direction == MessageDirection.OUTBOUND,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one()


async def test_checkpoint_persists_outbound_as_pending(
    two_tenants_with_channels: dict[str, dict[str, Any]],
):
    info = two_tenants_with_channels["a"]
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        await persist_outbound_message(
            session,
            conversation_id=info["conversation_id"],
            content="hola desde el agente",
            intent="info",
            model="claude-sonnet-4-6",
            tool_calls=[],
        )

    msg = await _last_outbound(info["tenant_id"], info["conversation_id"])
    assert msg.status is MessageStatus.PENDING
    assert msg.intent == "info"
    assert msg.model == "claude-sonnet-4-6"


async def test_caller_can_force_status_sent_for_legacy_paths(
    two_tenants_with_channels: dict[str, dict[str, Any]],
):
    """Tests + legacy code can opt out of the dispatcher by passing
    ``status=SENT`` explicitly. Useful for fixtures that don't want a
    pending tail of outbound rows."""
    info = two_tenants_with_channels["b"]
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        await persist_outbound_message(
            session,
            conversation_id=info["conversation_id"],
            content="legacy path",
            intent=None,
            model=None,
            tool_calls=[],
            status=MessageStatus.SENT,
        )

    msg = await _last_outbound(info["tenant_id"], info["conversation_id"])
    assert msg.status is MessageStatus.SENT
