"""Outbound dispatcher: drains ``messages.status='pending'`` to the
the WhatsApp Meta adapter (faked here)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from nexus_worker.streams.outbound import (
    MAX_ATTEMPTS,
    _drain_tenant,
)
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Message,
    MessageDirection,
    MessageStatus,
)

pytestmark = pytest.mark.asyncio


async def _seed_pending_message(*, tenant_info: dict[str, Any], content: str) -> Any:
    """Insert a pending outbound message under a tenant-scoped session.

    ``tenant_scoped_session`` commits on clean exit; do not call commit
    inside the with-block, that closes the begun transaction prematurely.
    """
    sm = get_sessionmaker()
    msg = Message(
        tenant_id=tenant_info["tenant_id"],
        conversation_id=tenant_info["conversation_id"],
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[],
    )
    async with sm() as session, tenant_scoped_session(session, tenant_info["tenant_id"]):
        session.add(msg)
        await session.flush()
        await session.refresh(msg)
        msg_id = msg.id
    return msg_id


async def _read_message(tenant_id: Any, message_id: Any) -> Message:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one()


async def test_outbound_dispatcher_sends_pending_messages(
    two_tenants_with_channels,
    fake_adapter,
):
    info = two_tenants_with_channels["a"]
    msg_id = await _seed_pending_message(tenant_info=info, content="Hola desde Cultor")

    sm = get_sessionmaker()
    await _drain_tenant(sm, info["tenant_id"], {"meta": fake_adapter}, batch_size=10)

    msg = await _read_message(info["tenant_id"], msg_id)
    assert msg.status is MessageStatus.SENT
    assert msg.trace_id == "wamid.1"
    assert len(fake_adapter.text_calls) == 1
    call = fake_adapter.text_calls[0]
    assert call["from_phone"] == info["business_phone"]
    assert call["recipient"] == info["customer_identifier"]
    assert call["text"] == "Hola desde Cultor"


async def test_outbound_dispatcher_marks_failed_after_retries(
    two_tenants_with_channels,
    fake_adapter,
):
    info = two_tenants_with_channels["a"]
    fake_adapter.fail_text_with = MetaAPIError("Bad Gateway", status_code=502)
    msg_id = await _seed_pending_message(tenant_info=info, content="reintenta")

    sm = get_sessionmaker()
    for _ in range(MAX_ATTEMPTS + 1):
        await _drain_tenant(sm, info["tenant_id"], {"meta": fake_adapter}, batch_size=10)

    msg = await _read_message(info["tenant_id"], msg_id)
    assert msg.status is MessageStatus.FAILED
    assert msg.attempts == MAX_ATTEMPTS
    assert "MetaAPIError" in (msg.last_error or "")


async def test_outbound_dispatcher_isolation_two_tenants(
    two_tenants_with_channels,
    fake_adapter,
):
    info_a = two_tenants_with_channels["a"]
    info_b = two_tenants_with_channels["b"]
    a_msg = await _seed_pending_message(tenant_info=info_a, content="A says hi")
    b_msg = await _seed_pending_message(tenant_info=info_b, content="B says hi")

    sm = get_sessionmaker()
    await asyncio.gather(
        _drain_tenant(sm, info_a["tenant_id"], {"meta": fake_adapter}, batch_size=10),
        _drain_tenant(sm, info_b["tenant_id"], {"meta": fake_adapter}, batch_size=10),
    )

    msg_a = await _read_message(info_a["tenant_id"], a_msg)
    msg_b = await _read_message(info_b["tenant_id"], b_msg)
    assert msg_a.status is MessageStatus.SENT
    assert msg_b.status is MessageStatus.SENT

    # Two send_text calls. Each tenant only saw its own from_phone.
    by_recipient = {c["recipient"]: c["from_phone"] for c in fake_adapter.text_calls}
    assert by_recipient[info_a["customer_identifier"]] == info_a["business_phone"]
    assert by_recipient[info_b["customer_identifier"]] == info_b["business_phone"]
    assert (
        by_recipient[info_a["customer_identifier"]] != by_recipient[info_b["customer_identifier"]]
    )


async def test_outbound_dispatcher_skips_already_sent_messages(
    two_tenants_with_channels,
    fake_adapter,
):
    """A row whose status is already 'sent' must not be re-sent on next tick."""
    info = two_tenants_with_channels["a"]
    msg_id = await _seed_pending_message(tenant_info=info, content="once")

    sm = get_sessionmaker()
    # First tick sends; second tick should find no pending and not call adapter.
    await _drain_tenant(sm, info["tenant_id"], {"meta": fake_adapter}, batch_size=10)
    assert len(fake_adapter.text_calls) == 1
    await _drain_tenant(sm, info["tenant_id"], {"meta": fake_adapter}, batch_size=10)
    assert len(fake_adapter.text_calls) == 1  # unchanged

    msg = await _read_message(info["tenant_id"], msg_id)
    assert msg.status is MessageStatus.SENT
