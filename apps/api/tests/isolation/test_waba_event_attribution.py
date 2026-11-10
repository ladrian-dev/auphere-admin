"""Spec 050 (4.3, garantía 1): an event that only names a WABA crosses no boundary.

Meta's partner events (``account_update`` with ``waba_info``), templates and
account alerts name the WABA, not a number. ``resolve_waba_tenants`` turns it
into the businesses that own live numbers there, and the event is applied
under each one's RLS. Verified here:

1. The function answers tenant ids, never rows or data, and leaves out a
   disconnected number.
2. An event of A's WABA never touches B's channels.
3. A WABA nobody owns is not applied anywhere.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select, text

from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.services import whatsapp_account_events

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

WABA_A = "WABA_ISO_A"
WABA_B = "WABA_ISO_B"


async def _add(
    db_session, tenant_id: uuid.UUID, waba: str, number: str, *, status=ChannelStatus.ACTIVE
) -> uuid.UUID:
    channel_id = uuid.uuid4()
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        db_session.add(
            Channel(
                id=channel_id,
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=number,
                status=status,
                config={"waba_id": waba, "phone_number_id": f"PN{number[-4:]}"},
            )
        )
    return channel_id


async def _status(db_session, tenant_id: uuid.UUID, channel_id: uuid.UUID) -> tuple[Any, Any]:
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        row = (
            await db_session.execute(
                select(Channel.status, Channel.problem_reason).where(Channel.id == channel_id)
            )
        ).one()
    return row[0], row[1]


def _partner_removed(waba: str) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba,
                "changes": [
                    {
                        "field": "account_update",
                        "value": {"event": "PARTNER_REMOVED", "waba_info": {"waba_id": waba}},
                    }
                ],
            }
        ],
    }


async def test_the_resolver_answers_only_tenant_ids(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]
    await _add(db_session, a, WABA_A, "+34600111001")
    await _add(db_session, b, WABA_B, "+34600111002")
    await _add(db_session, b, WABA_A, "+34600111003", status=ChannelStatus.DISCONNECTED)

    async with db_session.begin():
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        rows = (
            await db_session.execute(text("SELECT * FROM resolve_waba_tenants(:w)"), {"w": WABA_A})
        ).all()
        nobody = (
            await db_session.execute(text("SELECT * FROM resolve_waba_tenants('WABA_NOBODY')"))
        ).all()
    # One column, one row per business, and the disconnected number is not one.
    assert [tuple(r) for r in rows] == [(a,)]
    assert nobody == []

    async with db_session.begin():
        kind = (
            await db_session.execute(
                text(
                    "SELECT format_type(prorettype, NULL), proretset, prosecdef "
                    "FROM pg_proc WHERE proname = 'resolve_waba_tenants'"
                )
            )
        ).one()
    assert tuple(kind) == ("uuid", True, True)


async def test_an_event_of_as_waba_never_touches_bs_channels(db_session, tenants_ab, fake_redis):
    a, b = tenants_ab["a"], tenants_ab["b"]
    ch_a = await _add(db_session, a, WABA_A, "+34600111011")
    ch_b = await _add(db_session, b, WABA_B, "+34600111012")

    result = await whatsapp_account_events.handle(
        "account_update", _partner_removed(WABA_A), session=db_session, redis=fake_redis
    )

    assert result == "applied"
    assert await _status(db_session, a, ch_a) == (ChannelStatus.DEGRADED, "auth_expired")
    assert await _status(db_session, b, ch_b) == (ChannelStatus.ACTIVE, None)


async def test_a_waba_nobody_owns_is_not_applied(db_session, tenants_ab, fake_redis):
    a = tenants_ab["a"]
    ch_a = await _add(db_session, a, WABA_A, "+34600111021")

    result = await whatsapp_account_events.handle(
        "account_update", _partner_removed("WABA_NOBODY"), session=db_session, redis=fake_redis
    )

    assert result == "ignored"
    assert await _status(db_session, a, ch_a) == (ChannelStatus.ACTIVE, None)
