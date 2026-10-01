"""Spec 025 (Requisito 2.4, 2.6): a reviewer's tap is resolved in the webhook
and never reaches the agent; any other button still does.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    PaymentReview,
)
from nexus_api.services.agent_payment_review import Reviewer
from nexus_api.services.payment_reviews import button_id, open_review

from .test_endpoint_webhook_meta_inbound import _hub_sig, _inbound_entries, _inbound_envelope

pytestmark = pytest.mark.asyncio

BUSINESS = "+56999995555"
REVIEWER = Reviewer(phone="+56991280655", name="Daniela")


async def _seed_review(db_session, tenant_id: uuid.UUID) -> str:
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        ch = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=BUSINESS,
            status=ChannelStatus.ACTIVE,
            config={"waba_id": "WABA1", "phone_number_id": "PN1"},
        )
        buyer = Customer(tenant_id=tenant_id, identifier="56912345678")
        reviewer = Customer(tenant_id=tenant_id, identifier="56991280655")
        db_session.add_all([ch, buyer, reviewer])
        await db_session.flush()
        conv = Conversation(
            tenant_id=tenant_id,
            channel_id=ch.id,
            customer_id=buyer.id,
            last_inbound_at=datetime.now(UTC),
        )
        db_session.add(conv)
        db_session.add(
            Conversation(
                tenant_id=tenant_id,
                channel_id=ch.id,
                customer_id=reviewer.id,
                last_inbound_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
        await db_session.flush()
        with tenant_context(tenant_id):
            opened = await open_review(
                db_session,
                conversation=conv,
                reviewers=[REVIEWER],
                business="Flor y Encanto",
                method="transfer",
                summary={"product": "Ramo", "date": "viernes", "slot": "13:00 a 17:00"},
            )
        token = opened.review.token
    return token


def _tap(sender: str, wamid: str, payload_id: str, title: str) -> bytes:
    payload = _inbound_envelope(
        business_phone=BUSINESS,
        sender=sender,
        message={
            "from": sender,
            "id": wamid,
            "timestamp": "1716300000",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": payload_id, "title": title},
            },
        },
    )
    return json.dumps(payload).encode()


async def _status(db_session, tenant_id: uuid.UUID) -> str:
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        return (await db_session.execute(select(PaymentReview.status))).scalar_one()


async def test_a_reviewer_tap_resolves_and_is_not_enqueued(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    token = await _seed_review(db_session, tenant_id)

    body = _tap("56991280655", "wamid.tap-1", button_id(token, "ok"), "Confirmar pago")
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, tenant_id) == "confirmed"
    entries = await _inbound_entries(fake_redis)
    assert not [e for e in entries if e.get("provider_message_id") == "wamid.tap-1"]


async def test_a_stranger_tap_does_not_resolve_nor_reach_the_agent(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    token = await _seed_review(db_session, tenant_id)

    body = _tap("56900000001", "wamid.tap-2", button_id(token, "ok"), "Confirmar pago")
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, tenant_id) == "pending"
    entries = await _inbound_entries(fake_redis)
    assert not [e for e in entries if e.get("provider_message_id") == "wamid.tap-2"]


async def test_any_other_button_still_goes_to_the_agent(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    await _seed_review(db_session, tenant_id)

    body = _tap("56912345678", "wamid.tap-3", "confirmar", "Sí, confirmo")
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text
    entries = await _inbound_entries(fake_redis)
    assert len([e for e in entries if e.get("provider_message_id") == "wamid.tap-3"]) == 1
