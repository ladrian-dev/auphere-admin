"""Spec 004 · R2.3-R2.7 — the pool comes back on its own, and nothing carries over.

``renew_included_if_expired`` is NOT rewritten by this spec, and that is half
the saving: it already fires on **expiry, not on the calendar**, which is why a
renewal process that was down for three days catches up the moment it returns
instead of waiting for the next period. What changes is the date it writes
(``next_period_end``, now weekly and anchored to the partner) and where the
size comes from (``weekly_pool_tokens`` instead of the deprecated monthly cap).

A second renewal function would have been the obvious move and the wrong one:
two functions that start out identical are exactly the shape of the defect this
spec removes from the read path.

The one thing that must not happen: unspent pool accumulating. A weekly window
exists to bound the worst case; letting four weeks pile up turns a bounded
weekly maximum into a 4x monthly burst, which is exactly what it was meant to
prevent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.conftest import make_partner_with_wallet, spend_from_wallet

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _wallet(db_session, partner_id):
    row = (
        await db_session.execute(
            sa.text(
                "SELECT included_remaining, purchased_remaining, included_expires_at "
                "FROM partner_wallets WHERE partner_id = :p"
            ),
            {"p": str(partner_id)},
        )
    ).first()
    return row


async def test_an_expired_pool_comes_back_full(db_session) -> None:
    from nexus_api.metering.wallet import renew_included_if_expired

    past = datetime.now(UTC) - timedelta(days=1)
    world = await make_partner_with_wallet(db_session, included=10, expires_at=past)
    pid = world["partner_id"]

    renewed = await renew_included_if_expired(db_session, partner_id=pid)

    assert renewed is True
    row = await _wallet(db_session, pid)
    assert int(row[0]) == world["monthly_cap"]


async def test_unspent_pool_does_not_accumulate(db_session) -> None:
    """R2.3. The property the weekly window exists for."""
    from nexus_api.metering.wallet import renew_included_if_expired

    past = datetime.now(UTC) - timedelta(days=1)
    world = await make_partner_with_wallet(db_session, included=10_000, expires_at=past)
    pid = world["partner_id"]
    size = world["monthly_cap"]

    await renew_included_if_expired(db_session, partner_id=pid)

    row = await _wallet(db_session, pid)
    assert int(row[0]) == size, (
        f"the pool came back as {row[0]} instead of {size}: what was left over was "
        "added on top. Four weeks of that is a 4x burst, which is what the weekly "
        "window exists to prevent"
    )


async def test_a_live_pool_is_left_alone(db_session) -> None:
    from nexus_api.metering.wallet import renew_included_if_expired

    future = datetime.now(UTC) + timedelta(days=3)
    world = await make_partner_with_wallet(db_session, included=42, expires_at=future)
    pid = world["partner_id"]

    assert await renew_included_if_expired(db_session, partner_id=pid) is False
    row = await _wallet(db_session, pid)
    assert int(row[0]) == 42, "renewal is idempotent: a live pool is not topped up"


async def test_a_renewal_process_down_for_three_days_catches_up(db_session) -> None:
    """R2.4 — it fires on expiry, not on the calendar."""
    from nexus_api.metering.wallet import renew_included_if_expired

    long_past = datetime.now(UTC) - timedelta(days=3)
    world = await make_partner_with_wallet(db_session, included=0, expires_at=long_past)
    pid = world["partner_id"]

    assert await renew_included_if_expired(db_session, partner_id=pid) is True
    row = await _wallet(db_session, pid)
    assert int(row[0]) == world["monthly_cap"]
    assert row[2] > datetime.now(UTC), "the new boundary must be in the future"


async def test_purchased_survives_every_renewal(db_session) -> None:
    """R2.5 — an invariant, not a behaviour. It was paid for."""
    from nexus_api.metering.wallet import renew_included_if_expired

    past = datetime.now(UTC) - timedelta(days=1)
    world = await make_partner_with_wallet(db_session, included=0, purchased=7_777, expires_at=past)
    pid = world["partner_id"]

    await renew_included_if_expired(db_session, partner_id=pid)
    await renew_included_if_expired(db_session, partner_id=pid)

    row = await _wallet(db_session, pid)
    assert int(row[1]) == 7_777


async def test_a_new_partner_is_born_with_a_live_pool(db_session) -> None:
    """R2.7 — no window in which a partner exists without balance.

    The wallet is seeded by a trigger on insert (migration 0094), in the same
    transaction as the partner. This holds that it stays that way.
    """
    world = await make_partner_with_wallet(db_session, included=500, purchased=0)
    row = await _wallet(db_session, world["partner_id"])

    assert row is not None
    assert row[2] is not None, "a partner without an expiry date never renews"


async def test_spend_then_renew_returns_the_whole_pool(db_session) -> None:
    from nexus_api.metering.wallet import renew_included_if_expired

    world = await make_partner_with_wallet(db_session, included=1_000)
    pid = world["partner_id"]
    await spend_from_wallet(partner_id=pid, qty=900, lane="companion")

    await db_session.execute(
        sa.text("UPDATE partner_wallets SET included_expires_at = :t WHERE partner_id = :p"),
        {"t": datetime.now(UTC) - timedelta(minutes=1), "p": str(pid)},
    )
    await db_session.commit()

    await renew_included_if_expired(db_session, partner_id=pid)

    row = await _wallet(db_session, pid)
    assert int(row[0]) == 1_000
