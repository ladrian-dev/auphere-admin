"""Spec 005 · the tier caps, in one place.

R1.2 and R1.3. Two rules that read as one:

* a partner cannot create the teammate or the member above their tier's cap;
* **nothing existing is ever archived to make room** (principle IV).

The second is the one that needs saying. A partner who downgrades to a tier
with fewer seats than they are using keeps every one of them; what they lose
is the ability to create more. Freeing a seat is their decision, not ours.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.membership import (
    STATE_CANCELED,
    TIER_FREE,
    MembershipTier,
    PartnerSubscription,
)


@dataclass(frozen=True)
class Caps:
    """What a partner's tier allows right now."""

    tier_code: str
    max_teammates: int
    max_members: int


class TierLimitReached(Exception):
    """Refused because the tier's cap is full.

    Carries what the partner needs in order to act: which cap, what it is,
    and how many they have. A message that only says "limit reached" makes
    someone open a support ticket to learn a number we already know.
    """

    def __init__(self, *, kind: str, limit: int, current: int, tier_code: str) -> None:
        self.kind = kind
        self.limit = limit
        self.current = current
        self.tier_code = tier_code
        super().__init__(f"el nivel «{tier_code}» admite {limit} {kind} y ya hay {current}")


async def effective_caps(session: AsyncSession, partner_id: uuid.UUID) -> Caps:
    """The caps in force for a partner.

    **A partner with no subscription row is Free**, and so is a cancelled
    one. Absence is a valid state and is designed as one (principle V): no
    row has to be seeded for the system to behave correctly, which also means
    there is no seeding step that can be forgotten.
    """
    row = (
        await session.execute(
            sa.select(PartnerSubscription.tier_code, PartnerSubscription.state).where(
                PartnerSubscription.partner_id == partner_id
            )
        )
    ).first()

    code = TIER_FREE
    if row is not None and row.state != STATE_CANCELED:
        code = row.tier_code

    tier = (
        await session.execute(sa.select(MembershipTier).where(MembershipTier.code == code))
    ).scalar_one_or_none()
    if tier is None:  # pragma: no cover - only if the catalogue is gutted
        return Caps(tier_code=TIER_FREE, max_teammates=0, max_members=1)
    return Caps(
        tier_code=tier.code,
        max_teammates=tier.max_teammates,
        max_members=tier.max_members,
    )


async def assert_can_add_teammate(session: AsyncSession, partner_id: uuid.UUID) -> None:
    caps = await effective_caps(session, partner_id)
    current = int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(partner_id)},
        )
        or 0
    )
    if current >= caps.max_teammates:
        raise TierLimitReached(
            kind="teammates", limit=caps.max_teammates, current=current, tier_code=caps.tier_code
        )


async def assert_can_add_member(session: AsyncSession, partner_id: uuid.UUID) -> None:
    caps = await effective_caps(session, partner_id)
    current = int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM partner_memberships "
                "WHERE partner_id = :p AND status = 'active'"
            ),
            {"p": str(partner_id)},
        )
        or 0
    )
    if current >= caps.max_members:
        raise TierLimitReached(
            kind="personas", limit=caps.max_members, current=current, tier_code=caps.tier_code
        )


async def over_cap_by(
    session: AsyncSession, partner_id: uuid.UUID, tier_code: str
) -> dict[str, int]:
    """How much a partner would exceed a target tier by. Empty means it fits.

    Used to refuse a downgrade *before* it happens rather than archive
    anything after. Returning the numbers means the console can tell the
    partner exactly what to free up.
    """
    tier = (
        await session.execute(sa.select(MembershipTier).where(MembershipTier.code == tier_code))
    ).scalar_one_or_none()
    if tier is None:
        return {}

    teammates = int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(partner_id)},
        )
        or 0
    )
    members = int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM partner_memberships "
                "WHERE partner_id = :p AND status = 'active'"
            ),
            {"p": str(partner_id)},
        )
        or 0
    )
    over: dict[str, int] = {}
    if teammates > tier.max_teammates:
        over["teammates"] = teammates - tier.max_teammates
    if members > tier.max_members:
        over["members"] = members - tier.max_members
    return over
