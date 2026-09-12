"""Spec 004 · R3 — the quota unit weighs per model.

The property this exists for, in one sentence: **draining a pool of size P
costs the same in dollars whichever brain was used.** Without it, the worst
case of a plan is decided by the partner picking a model, not by us pricing it
— and with the provisional figures of the assessment, the top tier drained
entirely on the expensive brain costs $166.90 against a $150 price.

The factor goes INSIDE ``quota_tokens()``, next to the 0.1 that ``cache_read``
has carried since C3: same kind of weight, same function, so the three surfaces
keep seeing one number. It arrives as an explicit argument rather than being
looked up, because the module is pure — no database, no clock — and that is why
its suite runs in milliseconds without Postgres.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.metering.quota import quota_tokens

pytestmark = [pytest.mark.asyncio]

#: Same reference turn as the assessment: 30 K prompt, 80 % cache hit, 1.5 K out.
TURN = {"prompt_tokens": 30_000, "cache_read": 24_000, "output_tokens": 1_500}

#: USD per million tokens (input, cached, output), verified 2026-09-11, and the
#: weight seeded by migration 0115.
CATALOG = {
    "openai/gpt-5.6-luna": ((0.20, 0.02, 1.20), Decimal("0.100")),
    "anthropic/claude-haiku-4-5": ((1.00, 0.10, 5.00), Decimal("0.457")),
    "openai/gpt-5.6-terra": ((2.00, 0.20, 12.00), Decimal("1.000")),
    "anthropic/claude-sonnet-4-6": ((3.00, 0.30, 15.00), Decimal("1.371")),
    "openai/gpt-4o": ((2.50, 1.25, 10.00), Decimal("1.724")),
    "openai/gpt-5.6-sol": ((4.00, 0.40, 20.00), Decimal("1.828")),
}


def _dollars_per_turn(rates: tuple[float, float, float]) -> float:
    """What one reference turn really costs us on that model."""
    price_in, price_cached, price_out = rates
    uncached = TURN["prompt_tokens"] - TURN["cache_read"]
    return (
        uncached * price_in / 1e6
        + TURN["cache_read"] * price_cached / 1e6
        + TURN["output_tokens"] * price_out / 1e6
    )


async def test_draining_a_pool_costs_the_same_on_every_brain() -> None:
    """R3.2 / CE-002. A property over the whole catalog, not one case.

    A single example would pass with a typo in one weight; this walks every
    model the catalog sells and holds the band.
    """
    pool = 1_000_000
    costs = {}
    for model_id, (rates, weight) in CATALOG.items():
        charged = quota_tokens(**TURN, model_weight=weight)
        turns_to_drain = pool / charged
        costs[model_id] = turns_to_drain * _dollars_per_turn(rates)

    low, high = min(costs.values()), max(costs.values())
    assert high - low < 0.01, (
        f"draining the same pool costs between ${low:.4f} and ${high:.4f} depending "
        f"on the brain: {costs}. The weights no longer bound the worst case."
    )
    assert 3.51 < low < 3.52


async def test_the_expensive_brain_eats_more_pool() -> None:
    """The same work on the expensive brain must consume more quota."""
    cheap = quota_tokens(**TURN, model_weight=Decimal("0.100"))
    dear = quota_tokens(**TURN, model_weight=Decimal("1.828"))
    assert dear > cheap * 10


async def test_a_weight_of_one_leaves_the_old_arithmetic_untouched() -> None:
    """C3 is not being rewritten: with weight 1 the number is the old one."""
    assert quota_tokens(**TURN, model_weight=Decimal(1)) == 9_900


async def test_cache_read_still_weighs_a_tenth_underneath() -> None:
    """The model factor multiplies the C3 result; it does not replace it."""
    with_cache = quota_tokens(
        prompt_tokens=10_000, cache_read=10_000, output_tokens=0, model_weight=Decimal(1)
    )
    assert with_cache == 1_000


async def test_the_weight_is_applied_once_and_before_rounding() -> None:
    """Rounding twice drifts. The function rounds at the end, once."""
    value = quota_tokens(
        prompt_tokens=3, cache_read=0, output_tokens=0, model_weight=Decimal("0.5")
    )
    assert value == 2, "3 x 0.5 = 1.5, rounded half away from zero = 2"


async def test_model_weight_has_no_default() -> None:
    """R3.4's other half: forgetting to pass it must be a TypeError, not a 1.

    A default of 1 would turn every missed call site into a silent undercharge —
    the failure mode this spec removes everywhere else.
    """
    with pytest.raises(TypeError):
        quota_tokens(**TURN)  # type: ignore[call-arg]
