"""Spec 005 · the tier catalogue, and what the partner is told about it.

Two jobs:

* resolve a tier code to the provider's price id — a **replaceable reference**
  read from a row, never a literal in the code (research D5.2);
* turn the internal pool size into the **consumption multiple** that the plans
  screen publishes instead of the figure (research D9).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.membership import BASE_PAID_TIER, MembershipTier


def consumption_multiple(*, pool: int, base_pool: int) -> int | None:
    """How many times the base paid tier's consumption this tier gets.

    ``None`` means "say nothing", and it is returned in three cases that all
    amount to the same thing — any number we printed would be worse than
    silence:

    * the free tier, where "0.2x Pro" tells a prospect nothing;
    * a ratio that is not a whole number, where rounding would advertise "4x"
      for something that is 3.7x — a false commercial promise;
    * a base of zero, which is a misconfiguration and not a multiple.

    The figure itself is never published. It is provisional by product
    decision (ADR-037) and **will** be adjusted; printing it turns every
    capacity change into a visible cut or gift, which is exactly what the
    Spec A R7.3 forbids on the consumption screen and which does not stop
    being true on the plans screen.
    """
    if base_pool <= 0 or pool < base_pool:
        return None
    if pool % base_pool:
        return None
    return pool // base_pool


async def load_public_tiers(session: AsyncSession) -> list[MembershipTier]:
    """The tiers on offer, in display order. A retired tier is not deleted."""
    rows = await session.execute(
        sa.select(MembershipTier)
        .where(MembershipTier.is_public.is_(True))
        .order_by(MembershipTier.sort_order)
    )
    return list(rows.scalars())


async def base_paid_pool(session: AsyncSession) -> int:
    """The pool of the tier every published multiple hangs off."""
    value = await session.scalar(
        sa.select(MembershipTier.weekly_pool_tokens).where(MembershipTier.code == BASE_PAID_TIER)
    )
    return int(value or 0)


async def price_id_for(session: AsyncSession, code: str) -> str | None:
    """The provider's price id for a tier, or ``None``.

    ``None`` is a valid answer, not an error: the free tier has no price, and
    neither does any tier right after the catalogue is recreated against a new
    account. The caller decides what that means.
    """
    return await session.scalar(
        sa.select(MembershipTier.stripe_price_id).where(MembershipTier.code == code)
    )
