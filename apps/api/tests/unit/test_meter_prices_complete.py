"""Spec 004 · R1.6 — no meter disappears from a total in silence.

``SUM(cost_usd)`` ignores NULLs. A meter that is measured but has no rate
anywhere therefore contributes a perfectly credible zero to every margin
panel, and nobody has a reason to doubt it.

There are exactly two ways to price a meter in this platform:

- **by model** — ``model_profiles`` holds a rate per million tokens (or per
  minute for voice). Migration 0072 built it.
- **by unit** — ``meter_prices`` holds a flat price per unit, for meters that
  have no model at all. Migration 0083 built it for ``media.*``.

Every meter in ``USAGE_METERS`` must fall in one of the two, or be listed as
deliberately not valued. This test is the thing that makes "deliberately" a
decision somebody wrote down rather than a row nobody noticed.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.models.usage_record import USAGE_METERS

pytestmark = [pytest.mark.asyncio]


async def test_every_known_meter_is_priced_or_declared(db_session) -> None:
    from nexus_api.metering.pricing_policy import MODEL_PRICED_METERS, NOT_VALUED_METERS

    unit_priced = {
        r[0] for r in (await db_session.execute(sa.text("SELECT meter FROM meter_prices"))).all()
    }

    unaccounted = sorted(USAGE_METERS - MODEL_PRICED_METERS - NOT_VALUED_METERS - unit_priced)
    assert not unaccounted, (
        f"meters measured but priced nowhere: {unaccounted}. Each one silently adds "
        "zero to every margin total. Give it a rate, or add it to NOT_VALUED_METERS "
        "with the reason."
    )


async def test_the_three_declarations_do_not_overlap() -> None:
    """A meter priced two ways would be charged twice, or read from whichever
    lookup happened to run first. Both are wrong and neither raises."""
    from nexus_api.metering.pricing_policy import MODEL_PRICED_METERS, NOT_VALUED_METERS

    overlap = MODEL_PRICED_METERS & NOT_VALUED_METERS
    assert not overlap, f"meters declared both model-priced and not-valued: {sorted(overlap)}"


async def test_declarations_only_name_meters_that_exist() -> None:
    """A typo in a declaration is worse than a missing one: it silences a real
    meter and satisfies the check above at the same time."""
    from nexus_api.metering.pricing_policy import MODEL_PRICED_METERS, NOT_VALUED_METERS

    ghosts = sorted((MODEL_PRICED_METERS | NOT_VALUED_METERS) - USAGE_METERS)
    assert not ghosts, f"declared meters that are not in USAGE_METERS: {ghosts}"
