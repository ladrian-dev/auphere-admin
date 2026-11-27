"""Isolation guarantee — the client report (spec 083, requisito 10).

``tests/isolation/test_console_scope.py`` already sweeps the route with every
other ``{ref}`` route (opaque 404, no tenant or partner ids, no body fields).
This file proves the two things that sweep does not see:

1. **Garantía 1 inside one partner.** A partner with two clients asks for the
   report of one: nothing of the other counts, and the other's report counts
   only its own. The report joins several tables; every one of them is read
   under the client's RLS.
2. **Across partners**, the report of partner B's client is the very same 404
   as a reference that does not exist — with data on B's side, so a leak would
   show as a 200 with B's numbers.

And the C8 check with real data: none of the end customer's words, nor the free
text of an escalation, nor the contact's name or phone leave in the body.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    PartnerTenant,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]

CANARY = "CANARY-isolation-083"
PHONE = "+56911223344"
NOW = datetime.now(UTC)
AT = NOW - timedelta(days=2)
DAY_FROM = (NOW - timedelta(days=5)).date()
DAY_TO = (NOW - timedelta(days=1)).date()


async def _seed_client(db: Any, tenant_id: uuid.UUID, conversations: int) -> None:
    """``conversations`` contacts who wrote, the agent answered, one escalated."""
    async with db.begin():
        await db.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db.execute(text("SET LOCAL ROLE nexus_app"))
        channel = uuid.uuid4()
        db.add(
            Channel(
                id=channel,
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
                status=ChannelStatus.ACTIVE,
                config={"phone_number_id": "PN"},
            )
        )
        await db.flush()
        for n in range(conversations):
            customer, conv = uuid.uuid4(), uuid.uuid4()
            db.add(
                Customer(
                    id=customer,
                    tenant_id=tenant_id,
                    identifier=f"{PHONE}{n}",
                    name=f"{CANARY} Pérez",
                )
            )
            await db.flush()
            db.add(
                Conversation(
                    id=conv,
                    tenant_id=tenant_id,
                    channel_id=channel,
                    customer_id=customer,
                    status=ConversationStatus.ESCALATED,
                    created_at=AT,
                )
            )
            await db.flush()
            for direction, actor in (
                (MessageDirection.INBOUND, None),
                (MessageDirection.OUTBOUND, "agent"),
            ):
                db.add(
                    Message(
                        tenant_id=tenant_id,
                        conversation_id=conv,
                        direction=direction,
                        status=MessageStatus.SENT,
                        content=f"{CANARY} {PHONE}",
                        tool_calls=[],
                        actor_kind=actor,
                        created_at=AT + timedelta(seconds=2 if actor else 0),
                    )
                )
            db.add(
                ConversationEvent(
                    tenant_id=tenant_id,
                    conversation_id=conv,
                    kind="escalated",
                    actor="agent",
                    payload={"reason": f"{CANARY} dice {PHONE}", "customer_summary": CANARY},
                    created_at=AT + timedelta(minutes=1),
                )
            )


async def _second_client(db: Any, partner_id: uuid.UUID) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    ref = f"client-second-{tenant_id.hex[:6]}"
    db.add(
        Tenant(
            id=tenant_id,
            name="Second Client",
            slug=f"second-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=partner_id,
        )
    )
    await db.flush()
    db.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=ref,
            tenant_id=tenant_id,
            client_name="Second Client",
        )
    )
    await db.commit()
    return {"tenant_id": tenant_id, "ref": ref}


def _get(client: Any, ref: str, headers: dict[str, str]) -> Any:
    return client.get(
        f"/console/clients/{ref}/report",
        params={"from": DAY_FROM.isoformat(), "to": DAY_TO.isoformat()},
        headers=headers,
    )


async def test_two_clients_of_one_partner_never_mix(client, db_session, console_world) -> None:
    a = console_world["a"]
    second = await _second_client(db_session, a["partner_id"])
    await _seed_client(db_session, a["tenant_id"], conversations=1)
    await _seed_client(db_session, second["tenant_id"], conversations=3)

    mine = await _get(client, a["ref"], a["headers"]())
    other = await _get(client, second["ref"], a["headers"]())
    assert mine.status_code == other.status_code == 200, (mine.text, other.text)
    assert mine.json()["conversations"]["total"] == 1
    assert mine.json()["incidents"]["total"] == 1
    assert other.json()["conversations"]["total"] == 3
    assert other.json()["incidents"]["total"] == 3


async def test_another_partners_client_is_an_opaque_404(client, db_session, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_client(db_session, b["tenant_id"], conversations=2)

    foreign = await _get(client, b["ref"], a["headers"]())
    missing = await _get(client, "does-not-exist", a["headers"]())
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}
    # B ve lo suyo: la siembra existe y el 404 de A no es un informe vacío.
    own = await _get(client, b["ref"], b["headers"]())
    assert own.status_code == 200 and own.json()["conversations"]["total"] == 2


async def test_no_words_names_or_phones_leave(client, db_session, console_world) -> None:
    a = console_world["a"]
    await _seed_client(db_session, a["tenant_id"], conversations=2)
    r = await _get(client, a["ref"], a["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["conversations"]["total"] == 2
    assert CANARY not in r.text
    assert PHONE not in r.text
    assert str(a["tenant_id"]) not in r.text and str(a["partner_id"]) not in r.text
