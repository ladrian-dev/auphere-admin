"""Spec 004 · R3.3, R3.4, R3.5 — a model with no weight does not serve a turn.

Decided 2026-09-11 out of three options with opposite consequences:

- a neutral weight of 1 eats our margin in silence;
- the most expensive known weight charges the partner for an oversight of ours;
- refusing says what happened and to whom.

The third one wins, and it is not a new failure mode: the platform **already**
refuses a model that is not in the catalog. A model in the catalog with no
weight is the same class of configuration error, one row away from fixed.

The other half — and it is the one somebody will "fix" in six months — is that
the refusal applies **only to the LLM quota lane**. ``openai/whisper-1`` has no
weight and must keep working: it is measured in minutes and never passes
through ``quota_tokens()``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.asyncio]


async def test_a_model_without_a_weight_is_refused_by_name(db_session) -> None:
    from nexus_api.metering.pricing_policy import UnweightedModel, weight_for

    await db_session.execute(
        sa.text("UPDATE model_profiles SET quota_weight = NULL WHERE model_id = :m"),
        {"m": "openai/gpt-4o"},
    )
    await db_session.commit()

    with pytest.raises(UnweightedModel) as exc:
        weight_for("openai/gpt-4o", {"openai/gpt-4o": None})
    assert "openai/gpt-4o" in str(exc.value)


async def test_voice_is_not_touched_by_the_refusal() -> None:
    """``whisper-1`` has no weight and keeps working: minutes, not tokens."""
    from nexus_api.metering.pricing_policy import lane_needs_weight

    assert lane_needs_weight("llm.input_tokens") is True
    assert lane_needs_weight("llm.cache_read") is True
    assert lane_needs_weight("voice.minutes") is False
    assert lane_needs_weight("media.image") is False


async def test_a_known_weight_comes_back_as_given(db_session) -> None:
    from nexus_api.metering.pricing_policy import weight_for

    assert weight_for("x", {"x": Decimal("1.828")}) == Decimal("1.828")


async def test_a_weight_change_does_not_revalue_what_is_already_posted(db_session) -> None:
    """R3.5 — a ledger entry is a historical fact.

    Changing a weight must apply to what comes next, never to what was already
    debited: re-valuing history would move a partner's balance under them.
    """
    from tests.conftest import make_partner_with_wallet, spend_from_wallet

    world = await make_partner_with_wallet(db_session, included=10_000)
    pid = world["partner_id"]
    await spend_from_wallet(partner_id=pid, qty=1_000, lane="companion")

    before = await db_session.scalar(
        sa.text("SELECT included_remaining FROM partner_wallets WHERE partner_id = :p"),
        {"p": str(pid)},
    )
    await db_session.execute(
        sa.text("UPDATE model_profiles SET quota_weight = 9.999 WHERE model_id = :m"),
        {"m": "openai/gpt-5.6-sol"},
    )
    await db_session.commit()

    after = await db_session.scalar(
        sa.text("SELECT included_remaining FROM partner_wallets WHERE partner_id = :p"),
        {"p": str(pid)},
    )
    assert before == after
