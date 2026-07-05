"""Outbound dispatcher — HSM template path (migration 0049, ADR-028).

A pending row with ``template_payload`` set must route through
``adapter.send_template`` with the named params, and never through the
text path. Rows without it are untouched (regression guard).
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
    provider: str = "meta"
    channel_type: str = "whatsapp"
    text_calls: list[dict[str, Any]] = field(default_factory=list)
    template_calls: list[dict[str, Any]] = field(default_factory=list)

    async def send_text(self, **kwargs: Any) -> SendResult:
        self.text_calls.append(kwargs)
        return SendResult(provider_message_id="wamid.text", status=SendStatus.SENT)

    async def send_template(self, **kwargs: Any) -> SendResult:
        self.template_calls.append(kwargs)
        return SendResult(provider_message_id="wamid.tpl", status=SendStatus.SENT)


@pytest_asyncio.fixture
async def tpl_tenant(db_session) -> dict[str, Any]:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Tpl Dispatch",
            slug=f"tpl-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
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
    customer = Customer(tenant_id=tid, identifier="56911112223", preferences={})
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
    return {"tenant_id": tid, "conversation_id": conv.id}


async def _seed_pending(info: dict[str, Any], **message_kwargs: Any) -> uuid.UUID:
    sm = get_sessionmaker()
    msg = Message(
        tenant_id=info["tenant_id"],
        conversation_id=info["conversation_id"],
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        tool_calls=[],
        **message_kwargs,
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


async def test_template_payload_routes_to_send_template(tpl_tenant):
    adapter = RecordingAdapter()
    msg_id = await _seed_pending(
        tpl_tenant,
        content="[template:cobro_pendiente]",
        actor_kind="system",
        template_payload={
            "name": "cobro_pendiente",
            "language": "es",
            "params": {"body": {"cliente": "Ana", "saldo_pendiente": "$12.000"}},
        },
    )

    sm = get_sessionmaker()
    await _drain_tenant(sm, tpl_tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    msg = await _read(tpl_tenant["tenant_id"], msg_id)
    assert msg.status is MessageStatus.SENT
    assert msg.provider_message_id == "wamid.tpl"
    assert len(adapter.template_calls) == 1
    assert len(adapter.text_calls) == 0
    call = adapter.template_calls[0]
    assert call["template_name"] == "cobro_pendiente"
    assert call["language"] == "es"
    assert call["params"] == {"body": {"cliente": "Ana", "saldo_pendiente": "$12.000"}}
    assert call["recipient"] == "56911112223"


async def test_plain_text_row_still_routes_to_send_text(tpl_tenant):
    adapter = RecordingAdapter()
    msg_id = await _seed_pending(tpl_tenant, content="hola normal")

    sm = get_sessionmaker()
    await _drain_tenant(sm, tpl_tenant["tenant_id"], {"meta": adapter}, batch_size=10)

    msg = await _read(tpl_tenant["tenant_id"], msg_id)
    assert msg.status is MessageStatus.SENT
    assert len(adapter.text_calls) == 1
    assert len(adapter.template_calls) == 0
