"""Spec 004 · R1 — every model the product SELLS has a loaded rate.

Why this test exists, in one fact: ``config.py`` ships
``llm_companion_model = "openai/gpt-5.6-sol"``, and that row entered the
catalog in migration ``0095`` with all five price columns NULL. So every
Companion turn — and therefore every teammate turn — is measured and left
**unpriced**: ``_turn_cost_usd`` returns ``None`` and ``usage_records.cost_usd``
stays empty. The margin is not bad, it does not exist.

Cache-write stays NULL on purpose and the test asserts it, because a zero
would be a different claim. Migration ``0076`` already wrote the reasoning for
``gpt-4o``: OpenAI does not charge for writing to cache, and the emitter never
produces ``llm.cache_write`` for OpenAI at all (LiteLLM only reports
``cache_creation_input_tokens`` on Anthropic). NULL leaves the hole visible if
that meter ever starts arriving; 0 would say "measured, free", which is a
statement nobody verified.

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
async def test_sold_model_leaves_cache_write_absent_not_zero(db_session, model_id) -> None:
    """NULL, not 0. See the module docstring: they are different claims."""
    row = await _row(db_session, model_id)
    assert row is not None
    assert row["price_cache_write_per_mtok"] is None, (
        f"{model_id} has a cache-write rate. OpenAI does not charge for it and the "
        "emitter never produces that meter for OpenAI — a number here would be read "
        "as a verified price. Leave it NULL."
    )


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
