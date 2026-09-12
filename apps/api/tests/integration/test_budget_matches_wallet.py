"""Spec 004 · R4.1, R4.3 — the meter shown is the meter that decides.

The defect this story removes: two counters over the same money.

- ``/console/companion/budget`` summed rows of ``companion.runs``, which only
  ever sees Companion and teammate turns;
- ``partner_wallets.included_remaining`` is the book, which is ALSO drained by
  local execution.

And the same number — ``partners.companion_monthly_token_cap`` — sized both. So
a partner could see "20 % used" and get a ``409 wallet_empty`` at the same time.

**One scenario moved while this story was being written, and it is worth
recording.** The original example was "an end client's channel turns drain the
book and the partner's meter does not notice". R5.2 removes that case at the
root: the channel no longer touches the included pool at all, so a busy client
can no longer empty it. What is left — and what these tests hold — is the other
half: the total must come from the **book** and not from the run log, so that
spend the run log cannot see (local execution) still shows up. See
``test_pocket_separation`` for the channel half.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from tests.conftest import make_partner_with_wallet, spend_from_wallet

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_local_execution_spend_shows_up_in_the_budget(db_session) -> None:
    """Local execution leaves NO row in ``companion.runs``.

    Under the old reading this spend was invisible in the meter and perfectly
    visible to the wallet gate — the two-numbers bug, in its purest form.
    """
    world = await make_partner_with_wallet(db_session, included=50_000, purchased=0)
    partner_id = world["partner_id"]

    await spend_from_wallet(partner_id=partner_id, qty=20_000, lane="local_exec")

    from nexus_api.api.console.companion import partner_budget_in_tx

    budget = await partner_budget_in_tx(db_session, partner_id)
    assert budget.used == 20_000
    assert budget.remaining == 30_000


async def test_an_emptied_book_reads_as_exhausted(db_session) -> None:
    world = await make_partner_with_wallet(db_session, included=10_000, purchased=0)
    partner_id = world["partner_id"]

    await spend_from_wallet(partner_id=partner_id, qty=10_000, lane="companion")

    from nexus_api.api.console.companion import partner_budget_in_tx

    budget = await partner_budget_in_tx(db_session, partner_id)
    assert budget.remaining == 0
    assert budget.exhausted is True, (
        "the book is empty; the meter must say so, because this is the state in "
        "which the platform refuses a turn"
    )


async def test_remaining_is_the_column_not_a_subtraction(db_session) -> None:
    """``remaining`` must BE ``included_remaining``.

    The difference matters the day the two disagree: a subtraction keeps
    producing a plausible number long after the book says zero.
    """
    world = await make_partner_with_wallet(db_session, included=80_000, purchased=0)
    partner_id = world["partner_id"]
    await spend_from_wallet(partner_id=partner_id, qty=30_000, lane="companion")

    from nexus_api.api.console.companion import partner_budget_in_tx

    budget = await partner_budget_in_tx(db_session, partner_id)
    column = await db_session.scalar(
        sa.text("SELECT included_remaining FROM partner_wallets WHERE partner_id = :p"),
        {"p": str(partner_id)},
    )
    assert budget.remaining == column


async def test_an_unreadable_book_reads_as_exhausted_not_as_full(db_session, monkeypatch) -> None:
    """Fail-closed survives the rewiring (R4.5)."""
    world = await make_partner_with_wallet(db_session, included=90_000, purchased=0)
    partner_id = world["partner_id"]

    from nexus_api.api.console import companion
    from nexus_api.metering import wallet

    async def _unreadable(_pid):
        return None

    monkeypatch.setattr(wallet, "read_wallet", _unreadable)
    monkeypatch.setattr(companion, "month_window", companion.month_window)

    budget = await companion.partner_budget_in_tx(db_session, partner_id)
    assert budget.remaining == 0
    assert budget.exhausted is True
