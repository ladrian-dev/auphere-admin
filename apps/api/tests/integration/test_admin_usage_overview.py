"""Spec 038 — the consumption of every partner and every client.

Sale price from each partner's book (read under the partner's GUC), model
cost and messages from each client (read under the client's GUC), and the
same money per day. Every figure is labelled with whose it is.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, UsageLedger
from nexus_api.db.models.conversation import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _message(
    tenant_id: uuid.UUID, *, direction: MessageDirection, cost: float | None
) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+569{uuid.uuid4().int % 10**8:08d}",
            config={},
            status=ChannelStatus.ACTIVE,
        )
        customer = Customer(tenant_id=tenant_id, identifier=f"+5698{uuid.uuid4().int % 10**7:07d}")
        s.add_all([channel, customer])
        await s.flush()
        conv = Conversation(
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
            last_message_at=datetime.now(UTC),
        )
        s.add(conv)
        await s.flush()
        s.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=direction,
                status=MessageStatus.SENT,
                content="hola",
                cost_usd=cost,
            )
        )


async def test_the_whole_platform_in_one_reading(
    client, console_world, admin_headers, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    # 1 US$ = 100 000 credits: US$2.50 on A's client, US$1.00 on A's Companion.
    db_session.add_all(
        [
            UsageLedger(
                partner_id=a["partner_id"],
                tenant_id=a["tenant_id"],
                qty=250_000,
                bucket="purchased",
                kind="debit",
                idempotency_key=f"t:{uuid.uuid4().hex}",
            ),
            UsageLedger(
                partner_id=a["partner_id"],
                tenant_id=None,
                qty=100_000,
                bucket="purchased",
                kind="debit",
                idempotency_key=f"t:{uuid.uuid4().hex}",
            ),
        ]
    )
    await db_session.commit()
    await _message(a["tenant_id"], direction=MessageDirection.INBOUND, cost=None)
    await _message(a["tenant_id"], direction=MessageDirection.OUTBOUND, cost=0.12)

    res = await client.get("/admin/usage?days=30", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()

    pa = next(p for p in body["partners"] if p["partner_id"] == str(a["partner_id"]))
    assert pa["spend_cents"] == 350
    assert pa["spend_outside_clients_cents"] == 100
    pb = next(p for p in body["partners"] if p["partner_id"] == str(b["partner_id"]))
    assert pb["spend_cents"] == 0

    ca = next(c for c in body["clients"] if c["tenant_id"] == str(a["tenant_id"]))
    assert ca["spend_cents"] == 250
    assert ca["partner_id"] == str(a["partner_id"])
    assert ca["messages_inbound"] == 1
    assert ca["messages_outbound"] == 1
    assert ca["internal_cost_usd"] == "0.12"

    assert body["totals"]["spend_cents"] >= 350
    assert body["totals"]["messages"] >= 2
    today = datetime.now(UTC).date().isoformat()
    day = next(d for d in body["daily"] if d["day"] == today)
    assert day["spend_cents"] >= 350
    assert body["unreadable"] == {"partners": [], "clients": []}


async def test_usage_needs_the_admin_token(client) -> None:
    assert (await client.get("/admin/usage")).status_code in (401, 403)
