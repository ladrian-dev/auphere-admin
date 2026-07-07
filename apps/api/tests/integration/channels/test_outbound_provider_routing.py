"""Outbound dispatcher provider routing.

The dispatcher resolves the adapter from ``channels.provider``. Meta is the
only registered provider now; these tests assert that a Meta channel
dispatches through the Meta adapter and that a channel whose provider has
no registered adapter is parked failed instead of being sent through the
wrong transport.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from nexus_channels.base import SendResult, SendStatus
from nexus_worker.streams.outbound import _drain_tenant
from sqlalchemy import select

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
    MessageStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


@dataclass
class RecordingAdapter:
    """Provider-agnostic recording adapter — same send surface as both real
    adapters. ``provider`` is informational; the registry key is what routes."""

    provider: str = "meta"
    channel_type: str = "whatsapp"
    text_calls: list[dict[str, Any]] = field(default_factory=list)

    async def send_text(self, **kwargs: Any) -> SendResult:
        self.text_calls.append(kwargs)
        return SendResult(provider_message_id="wamid.x", status=SendStatus.SENT)


@dataclass
class TokenInvalidatedAdapter:
    """Meta adapter that simulates a dead BISUAT (OAuthException 190)."""

    provider: str = "meta"
    channel_type: str = "whatsapp"

    async def send_text(self, **kwargs: Any) -> SendResult:
        from nexus_channels.whatsapp_meta.exceptions import TokenInvalidatedError

        raise TokenInvalidatedError("token invalidated", status_code=401, code=190)


@pytest_asyncio.fixture
async def meta_tenant(db_session) -> dict[str, Any]:
    """A tenant whose only active WhatsApp channel is provider='meta'."""
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Meta Routing",
            slug=f"meta-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            owner_phone="+56999990003",
        )
    )
    await db_session.commit()
    channel = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier="+34632719028",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    customer = Customer(tenant_id=tid, identifier="+56911112223", preferences={})
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    conv = Conversation(
        tenant_id=tid,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return {
        "tenant_id": tid,
        "channel_id": channel.id,
        "business_phone": "+34632719028",
        "customer_identifier": "+56911112223",
        "conversation_id": conv.id,
    }


async def _seed_pending(info: dict[str, Any], content: str) -> uuid.UUID:
    sm = get_sessionmaker()
    msg = Message(
        tenant_id=info["tenant_id"],
        conversation_id=info["conversation_id"],
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[],
    )
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(msg)
        await session.flush()
        await session.refresh(msg)
        return msg.id


async def _read(tenant_id: uuid.UUID, message_id: uuid.UUID) -> Message:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one()


async def test_meta_channel_routes_to_meta_adapter(meta_tenant):
    """A provider='meta' channel sends through the Meta adapter, never any
    other registry entry."""
    meta = RecordingAdapter(provider="meta")
    other = RecordingAdapter(provider="other")
    msg_id = await _seed_pending(meta_tenant, "hola por Meta")

    sm = get_sessionmaker()
    await _drain_tenant(sm, meta_tenant["tenant_id"], {"other": other, "meta": meta}, batch_size=10)

    msg = await _read(meta_tenant["tenant_id"], msg_id)
    assert msg.status is MessageStatus.SENT
    assert len(meta.text_calls) == 1
    assert len(other.text_calls) == 0
    assert meta.text_calls[0]["text"] == "hola por Meta"
    assert meta.text_calls[0]["from_phone"] == meta_tenant["business_phone"]


async def test_unsupported_provider_parks_failed(meta_tenant):
    """A channel whose provider has no registered adapter must not be sent
    through the wrong transport — it's parked failed, no retry."""
    other = RecordingAdapter(provider="other")
    msg_id = await _seed_pending(meta_tenant, "sin adapter")

    sm = get_sessionmaker()
    # Registry intentionally omits "meta".
    await _drain_tenant(sm, meta_tenant["tenant_id"], {"other": other}, batch_size=10)

    msg = await _read(meta_tenant["tenant_id"], msg_id)
    assert msg.status is MessageStatus.FAILED
    assert msg.failure_code == "unsupported_provider"
    assert len(other.text_calls) == 0


async def test_meta_token_invalidation_flags_needs_reauth(meta_tenant):
    """A dead BISUAT (OAuthException 190) parks the send failed AND flips the
    tenant's Meta credentials to ``needs_reauth`` so the operator knows to
    re-run Embedded Signup instead of failing silently forever."""
    from nexus_channels.whatsapp_meta.credentials import (
        INTEGRATION_KEY,
        MetaCredentials,
        MetaCredentialsRepository,
    )

    from nexus_api.db.models import TenantCredentials

    tid = meta_tenant["tenant_id"]
    sm = get_sessionmaker()

    # Seed a Meta credentials row so there is something to flag.
    async with sm() as session, tenant_scoped_session(session, tid):
        await MetaCredentialsRepository(session).upsert(
            MetaCredentials(
                bisuat="EAAdead",
                waba_id="100",
                phone_number_id="200",
                business_id="300",
                display_phone_number="+34632719028",
                verify_token="x" * 32,
            )
        )
        await session.commit()

    msg_id = await _seed_pending(meta_tenant, "se cayó el token")
    await _drain_tenant(sm, tid, {"meta": TokenInvalidatedAdapter()}, batch_size=10)

    msg = await _read(tid, msg_id)
    assert msg.status is MessageStatus.FAILED

    async with sm() as session, tenant_scoped_session(session, tid):
        row = (
            await session.execute(
                select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
            )
        ).scalar_one()
        assert row.needs_reauth is True
