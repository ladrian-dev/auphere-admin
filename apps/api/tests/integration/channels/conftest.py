"""Shared fixtures for block F worker stream tests.

The tests here drive the outbound dispatcher / operator alerter / reminder
cron against the real Postgres test DB, but **never** hit YCloud — they
inject :class:`FakeYCloudAdapter` whose ``send_*`` methods record calls and
optionally raise. That is the right unit of mocking: the adapter Protocol
is the pinch point between the worker streams and the wire.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest_asyncio
from nexus_channels.base import SendResult, SendStatus

from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Tenant,
    TenantPlan,
    TenantStatus,
)


@dataclass
class FakeYCloudAdapter:
    """Adapter shim with the same shape as :class:`WhatsAppYCloudAdapter`.

    Records every send call, returns a configurable result, and can be
    primed to raise on demand to exercise retry / failure paths.
    """

    channel_type: str = "whatsapp"
    provider: str = "ycloud"
    text_calls: list[dict[str, Any]] = field(default_factory=list)
    template_calls: list[dict[str, Any]] = field(default_factory=list)
    fail_text_with: Exception | None = None
    fail_template_with: Exception | None = None

    async def send_text(self, **kwargs: Any) -> SendResult:
        self.text_calls.append(kwargs)
        if self.fail_text_with is not None:
            raise self.fail_text_with
        return SendResult(
            provider_message_id=f"wamid.{len(self.text_calls)}",
            status=SendStatus.SENT,
        )

    async def send_template(self, **kwargs: Any) -> SendResult:
        self.template_calls.append(kwargs)
        if self.fail_template_with is not None:
            raise self.fail_template_with
        return SendResult(
            provider_message_id=f"wamid.tpl.{len(self.template_calls)}",
            status=SendStatus.SENT,
        )

    async def send_interactive(self, **kwargs: Any) -> SendResult:  # pragma: no cover
        return SendResult(
            provider_message_id="wamid.int",
            status=SendStatus.SENT,
        )


@pytest_asyncio.fixture
async def fake_adapter() -> AsyncIterator[FakeYCloudAdapter]:
    yield FakeYCloudAdapter()


@pytest_asyncio.fixture
async def two_tenants_with_channels(db_session) -> dict[str, dict[str, Any]]:
    """Create two tenants A and B, each with a WhatsApp channel + customer +
    open conversation. Returns ids the tests need to seed messages.
    """
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    db_session.add_all(
        [
            Tenant(
                id=a_id,
                name="F A",
                slug=f"f-a-{a_id.hex[:6]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
                owner_phone="+56999990001",
            ),
            Tenant(
                id=b_id,
                name="F B",
                slug=f"f-b-{b_id.hex[:6]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
                owner_phone="+56999990002",
            ),
        ]
    )
    await db_session.commit()

    async def _seed(tid: uuid.UUID, biz_phone: str, sender_phone: str) -> dict[str, Any]:
        channel = Channel(
            tenant_id=tid,
            type=ChannelType.WHATSAPP,
            provider="ycloud",
            provider_identifier=biz_phone,
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(channel)
        await db_session.commit()
        await db_session.refresh(channel)
        customer = Customer(tenant_id=tid, identifier=sender_phone, preferences={})
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
            "business_phone": biz_phone,
            "customer_id": customer.id,
            "customer_identifier": sender_phone,
            "conversation_id": conv.id,
        }

    return {
        "a": await _seed(a_id, "+56933334441", "+56911112221"),
        "b": await _seed(b_id, "+56933334442", "+56911112222"),
    }
