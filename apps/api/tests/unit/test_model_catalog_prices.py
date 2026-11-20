"""Spec 004 · R1 — every model the product SELLS has a loaded rate.

Why this test exists, in one fact: ``config.py`` ships
``llm_companion_model = "openai/gpt-5.6-sol"``, and that row entered the
catalog in migration ``0095`` with all five price columns NULL. So every
Companion turn — and therefore every teammate turn — is measured and left
**unpriced**: ``_turn_cost_usd`` returns ``None`` and ``usage_records.cost_usd``
stays empty. The margin is not bad, it does not exist.

Cache-write: until spec 065 it stayed NULL on purpose, because OpenAI did not charge
for writing to cache and the emitter never produced ``llm.cache_write`` for OpenAI.
Both changed. Since GPT-5.6, OpenAI bills cache writes at 1.25x the input rate
(prompt-caching guide; research.md §D14) and Luis decided on 2026-11-19 to pass it on;
migration ``0239`` loads the rate. And the collector now records the
``prompt_tokens_details.cache_write_tokens`` that LiteLLM passes through
(``apps/worker/tests/unit/test_cache_write_on_the_wire.py``). ``gpt-4o`` keeps NULL:
no write tariff, so its quota weight for that lane is 0.

Rates verified 2026-09-11 at developers.openai.com/api/docs/pricing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.asyncio]

#: The closed catalog the console sells (migration 0095 / ``respond_catalog``).
#: USD per million tokens: input, cached input, output.
SOLD_MODELS: dict[str, tuple[str, str, str]] = {
    "openai/gpt-5.6-sol": ("4.000000", "0.400000", "20.000000"),
    "openai/gpt-5.6-terra": ("2.000000", "0.200000", "12.000000"),
    "openai/gpt-5.6-luna": ("0.200000", "0.020000", "1.200000"),
}


async def _row(db_session, model_id: str):
    return (
        (
            await db_session.execute(
                sa.text(
                    """
                SELECT price_input_per_mtok, price_output_per_mtok,
                       price_cache_read_per_mtok, price_cache_write_per_mtok
                  FROM model_profiles
                 WHERE model_id = :m
                """
                ),
                {"m": model_id},
            )
        )
        .mappings()
        .first()
    )


@pytest.mark.parametrize("model_id", sorted(SOLD_MODELS))
async def test_sold_model_has_input_cached_and_output_rates(db_session, model_id) -> None:
    row = await _row(db_session, model_id)
    assert row is not None, f"{model_id} is not in model_profiles at all"

    want_in, want_cached, want_out = SOLD_MODELS[model_id]
    assert row["price_input_per_mtok"] == Decimal(want_in)
    assert row["price_cache_read_per_mtok"] == Decimal(want_cached)
    assert row["price_output_per_mtok"] == Decimal(want_out)


@pytest.mark.parametrize("model_id", sorted(SOLD_MODELS))
async def test_sold_model_bills_cache_write_at_125_percent_of_input(db_session, model_id) -> None:
    """Spec 065 (0239): 1.25 x input. Sol 4.00 → 5.00, Terra 2.00 → 2.50, Luna 0.20 → 0.25."""
    row = await _row(db_session, model_id)
    assert row is not None
    want_in, _cached, _out = SOLD_MODELS[model_id]
    assert row["price_cache_write_per_mtok"] == Decimal(want_in) * Decimal("1.25")


async def test_gpt4o_still_has_no_cache_write_rate(db_session) -> None:
    """NULL, not 0: OpenAI does not bill gpt-4o cache writes, and 0 would read as a
    verified price."""
    row = await _row(db_session, "openai/gpt-4o")
    assert row is not None
    assert row["price_cache_write_per_mtok"] is None


async def test_the_companion_default_model_is_priced(db_session) -> None:
    """The model every teammate turn actually runs on must be priceable.

    Pinned to the setting rather than to a literal: if someone changes the
    default to a model with no rate, this fails instead of silently making the
    margin invisible again.
    """
    from nexus_api.config import get_settings

    model_id = get_settings().llm_companion_model
    row = await _row(db_session, model_id)
    assert row is not None, f"default Companion model {model_id} is not in the catalog"
    assert row["price_input_per_mtok"] is not None, (
        f"default Companion model {model_id} has no input rate: every turn it runs "
        "is measured and left unpriced"
    )
    assert row["price_output_per_mtok"] is not None
