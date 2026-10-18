"""Spec 034 — the console is free while the Teammate is finished.

With ``membership_enabled`` off (the default): no tier caps people or
teammates, the weekly pool refills whatever a leftover subscription says,
and the plans, the provider portal and the cancellation do not exist.
Buying credit and the receipts keep working.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import PartnerWallet
from nexus_api.metering.wallet import renew_included_if_expired
from nexus_api.services.membership_limits import (
    TierLimitReached,
    assert_can_add_member,
    assert_can_add_teammate,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _free_partner(session) -> uuid.UUID:
    """A partner with no subscription row — the Free tier: 0 teammates, 1 person."""
    pid = uuid.uuid4()
    slug = f"free-{pid.hex[:10]}"
    await session.execute(
        sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
        {"i": str(pid), "n": slug, "s": slug},
    )
    await session.execute(
        sa.text(
            "INSERT INTO partner_memberships (id, partner_id, user_id, email, role, status) "
            "VALUES (:i, :p, :u, :e, 'owner', 'active')"
        ),
        {"i": str(uuid.uuid4()), "p": str(pid), "u": f"u-{pid.hex[:8]}", "e": f"{slug}@x.example"},
    )
    await session.commit()
    return pid


async def test_the_flag_is_off_by_default() -> None:
    assert get_settings().membership_enabled is False


async def test_no_tier_caps_people_or_teammates(db_session) -> None:
    pid = await _free_partner(db_session)
    async with get_sessionmaker()() as s:
        await assert_can_add_member(s, pid)
        await assert_can_add_teammate(s, pid)


async def test_the_same_partner_is_capped_when_memberships_are_on(
    db_session, memberships_on
) -> None:
    pid = await _free_partner(db_session)
    async with get_sessionmaker()() as s:
        with pytest.raises(TierLimitReached):
            await assert_can_add_teammate(s, pid)


async def test_the_pool_refills_even_with_a_canceled_subscription(db_session) -> None:
    pid = await _free_partner(db_session)
    await db_session.execute(
        sa.text(
            "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
            "VALUES (:p, 'pro', 'canceled')"
        ),
        {"p": str(pid)},
    )
    await db_session.commit()
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, pid)
        row = await s.get(PartnerWallet, pid)
        if row is None:
            row = PartnerWallet(partner_id=pid)
            s.add(row)
        row.included_remaining = 0
        row.purchased_remaining = 0
        row.included_expires_at = datetime.now(UTC) - timedelta(hours=1)
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, pid)
        renewed = await renew_included_if_expired(s, partner_id=pid, pool_size=1_000)
    assert renewed is True


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/console/billing/membership", None),
        ("POST", "/console/billing/checkout", {"tier_code": "pro"}),
        ("GET", "/console/billing/portal", None),
        ("DELETE", "/console/billing/subscription", None),
    ],
)
async def test_plans_portal_and_cancel_do_not_exist(
    client, console_world, method, path, body
) -> None:
    a = console_world["a"]
    res = await client.request(method, path, headers=a["headers"](), json=body)
    assert res.status_code == 404, res.text


async def test_billing_says_memberships_are_off_and_keeps_receipts(client, console_world) -> None:
    a = console_world["a"]
    res = await client.get("/console/billing", headers=a["headers"]())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["memberships_enabled"] is False
    assert "receipts" in body
