"""Spec 038/039 — the consumption of every partner and client, and our profit.

Sale price from each partner's book (read under the partner's GUC), model
cost and messages from each client (read under the client's GUC), and the
same money per day. Every figure is labelled with whose it is.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

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
    # Meta's price on the message is not our cost: it must not count.
    await _message(a["tenant_id"], direction=MessageDirection.OUTBOUND, cost=0.12)
    # What the model cost us: US$1.00 for the client's turns (sold at 2.50),
    # US$0.10 for an operator's tests (nobody pays them), one unpriced event.
    for source, cost in (("channel", "1.00"), ("qa", "0.10"), ("channel", None)):
        await db_session.execute(
            sa.text(
                "INSERT INTO usage_records (tenant_id, partner_id, occurred_at, meter, quantity, "
                "cost_usd, billable_qty, idempotency_key, source) "
                "VALUES (:t, :p, now(), 'llm.output_tokens', 10, :c, 10, :k, :s)"
            ),
            {
                "t": str(a["tenant_id"]),
                "p": str(a["partner_id"]),
                "c": cost,
                "k": f"k:{uuid.uuid4()}",
                "s": source,
            },
        )
    await db_session.commit()

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
    # Sold 2.50, cost 1.00: profit 1.50, margin 60 %, charged 150 % over cost.
    assert ca["cost_usd"] == "1"
    assert ca["profit_usd"] == "1.5"
    assert ca["margin_pct"] == 60.0
    assert ca["markup_pct"] == 150.0
    assert ca["tests_cost_usd"] == "0.1"
    assert ca["unpriced_events"] == 1

    t = body["totals"]
    assert t["configured_multiplier"] == "2.2"
    assert t["tests_cost_usd"] != "0"
    assert Decimal(t["net_profit_usd"]) == Decimal(t["profit_usd"]) - Decimal(t["tests_cost_usd"])

    assert body["totals"]["spend_cents"] >= 350
    assert body["totals"]["messages"] >= 2
    today = datetime.now(UTC).date().isoformat()
    day = next(d for d in body["daily"] if d["day"] == today)
    assert day["spend_cents"] >= 350
    assert body["unreadable"] == {"partners": [], "clients": []}


async def test_usage_needs_the_admin_token(client) -> None:
    assert (await client.get("/admin/usage")).status_code in (401, 403)
