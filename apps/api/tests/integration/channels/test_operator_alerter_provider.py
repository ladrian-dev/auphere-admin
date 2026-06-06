"""Operator alerter provider routing.

The alerter resolves the adapter from the tenant's active WhatsApp channel
provider, and calls ``send_template`` with the shape that adapter expects
(YCloud: ``body_params``; Meta: ``params={"body": [...]}``). This test pins
the Meta branch so a Meta-served tenant is alerted through Meta.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_channels.base import SendResult, SendStatus
from nexus_worker.streams.operator_alerts import _process_pending

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Customer,
    OperatorNotification,
    OperatorNotificationStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


@dataclass
class RecordingAdapter:
    provider: str = "ycloud"
    channel_type: str = "whatsapp"
    template_calls: list[dict[str, Any]] = field(default_factory=list)

    async def send_template(self, **kwargs: Any) -> SendResult:
        self.template_calls.append(kwargs)
        return SendResult(provider_message_id="wamid.tpl", status=SendStatus.SENT)


@pytest_asyncio.fixture
async def meta_tenant_with_customer(db_session) -> dict[str, Any]:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Meta Alert",
            slug=f"meta-alert-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            owner_phone="+56999990009",
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
    customer = Customer(tenant_id=tid, identifier="+56911119999", preferences={})
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return {"tenant_id": tid, "business_phone": "+34632719028", "customer_id": customer.id}


async def test_meta_tenant_alert_routes_to_meta_adapter(meta_tenant_with_customer):
    info = meta_tenant_with_customer
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(
            AuditLog(
                tenant_id=info["tenant_id"],
                actor="system:test",
                action="conversation.escalated",
                target=f"tenant:{info['tenant_id']}",
                before_json=None,
                after_json={"customer_id": str(info["customer_id"]), "reason": "urgente"},
            )
        )

    meta = RecordingAdapter(provider="meta")
    ycloud = RecordingAdapter(provider="ycloud")
    await _process_pending(sm, {"ycloud": ycloud, "meta": meta})

    # Routed to Meta, not YCloud.
    assert len(meta.template_calls) == 1
    assert len(ycloud.template_calls) == 0
    call = meta.template_calls[0]
    assert call["template_name"] == "alert_escalation_v1"
    assert call["from_phone"] == info["business_phone"]
    assert call["recipient"] == "+56999990009"
    # Meta signature: a ``params`` dict carrying the positional body params,
    # NOT the YCloud ``body_params`` kwarg. Second param is the escalation
    # reason; first is the customer label (name or identifier fallback).
    assert "body_params" not in call
    assert list(call["params"].keys()) == ["body"]
    assert call["params"]["body"][1] == "urgente"
    assert len(call["params"]["body"]) == 2

    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        notif = (
            await session.execute(
                sa.select(OperatorNotification).where(
                    OperatorNotification.tenant_id == info["tenant_id"]
                )
            )
        ).scalar_one()
        assert notif.status is OperatorNotificationStatus.SENT
