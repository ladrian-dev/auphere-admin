"""Spec 026: the home page blocks through ``GET /console/home``.

What fails (worst first, with its fix), what waits for a person, the 7-day
trend against the 7 before, the credit and the portfolio — permission-gated,
isolated between partners, without tenant ids, Playground excluded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    PaymentReview,
    TenantStatus,
)
from tests.conftest import add_console_member
from tests.unit.test_endpoint_console_home_usage import _add_client

pytestmark = pytest.mark.asyncio


async def _seed_activity(db_session, tenant_id: uuid.UUID) -> None:
    """A working client: active agent, active channel with RED quality, two
    conversations today and one 9 days ago, one escalated with a recent
    inbound, one failed message, one unanswered inbound and one pending
    payment review. Plus a Playground conversation that must not count."""
    now = datetime.now(UTC)
    ch = Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
        config={"quality_rating": "RED", "waba_id": "WABA_HOME"},
        status=ChannelStatus.ACTIVE,
    )
    qa = Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="qa_playground",
        provider_identifier=f"qa-{uuid.uuid4().hex[:8]}",
        config={},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add_all([ch, qa])
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="x",
            tools=[],
        )
    )
    cust = Customer(id=uuid.uuid4(), tenant_id=tenant_id, identifier="56912345678")
    db_session.add(cust)
    await db_session.flush()

    def conv(**kw: object) -> Conversation:
        c = Conversation(
            id=uuid.uuid4(), tenant_id=tenant_id, customer_id=cust.id, channel_id=ch.id, **kw
        )
        db_session.add(c)
        return c

    today = conv(status=ConversationStatus.OPEN, last_inbound_at=now)
    escalated = conv(status=ConversationStatus.ESCALATED, last_inbound_at=now)
    old = conv(status=ConversationStatus.OPEN, created_at=now - timedelta(days=9))
    playground = Conversation(
        id=uuid.uuid4(), tenant_id=tenant_id, customer_id=cust.id, channel_id=qa.id
    )
    db_session.add(playground)
    await db_session.flush()
    db_session.add_all(
        [
            Message(
                tenant_id=tenant_id,
                conversation_id=today.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.FAILED,
                content="x",
            ),
            Message(
                tenant_id=tenant_id,
                conversation_id=today.id,
                direction=MessageDirection.INBOUND,
                content="hola",
                skipped_reason="not_admin",
            ),
            PaymentReview(
                tenant_id=tenant_id,
                conversation_id=escalated.id,
                channel_id=ch.id,
                token=uuid.uuid4().hex[:12],
                method="transfer",
            ),
        ]
    )
    _ = old
    await db_session.commit()


async def test_the_home_says_what_fails_what_waits_and_how_it_goes(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed_activity(db_session, a["tenant_id"])
    await _add_client(db_session, a["partner_id"], "nuevo", TenantStatus.PROVISIONING)

    r = await client.get("/console/home", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tenant_id" not in r.text and "cost" not in r.text.lower()

    kinds = [(i["external_client_ref"], i["kind"]) for i in body["attention"]["items"]]
    assert (a["ref"], "quality_red") in kinds
    assert (a["ref"], "failed_messages") in kinds
    assert ("nuevo", "provisioning") in kinds
    severities = [i["severity"] for i in body["attention"]["items"]]
    assert severities == sorted(severities)
    quality = next(i for i in body["attention"]["items"] if i["kind"] == "quality_red")
    assert quality["href"] == f"/clients/{a['ref']}/channels"

    review = body["to_review"]
    assert (review["escalated"], review["payments"], review["unanswered"]) == (1, 1, 1)
    assert review["clients"][0]["href"] == f"/clients/{a['ref']}/conversations"

    trend = body["conversations_trend"]
    assert len(trend["days"]) == 7 and trend["series"][-1] == 2  # Playground excluded
    assert trend["current"] == 2 and trend["previous"] == 1

    rows = {row["external_client_ref"]: row for row in body["portfolio"]}
    assert rows[a["ref"]]["conversations_7d"] == 2
    assert rows[a["ref"]]["attention"] >= 2
    assert rows["nuevo"]["status"] == "provisioning"


async def test_a_billing_member_sees_the_credit_and_not_the_clients(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    billing = await add_console_member(db_session, partner_id=a["partner_id"], role="billing")
    body = (await client.get("/console/home", headers=billing["headers"]())).json()
    assert body["attention"] is None and body["portfolio"] is None
    assert body["credit"] is not None
    assert {"available", "spent_7d", "daily_average", "days_left", "at_risk"} <= set(body["credit"])


async def test_another_partner_sees_none_of_it(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_activity(db_session, a["tenant_id"])
    body = (await client.get("/console/home", headers=b["headers"]())).json()
    refs = {row["external_client_ref"] for row in body["portfolio"]}
    assert a["ref"] not in refs
    assert body["to_review"]["escalated"] == 0
    assert body["conversations_trend"]["current"] == 0
