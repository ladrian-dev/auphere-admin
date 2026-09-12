"""Spec 004 · R5 — two pockets, and each one is spent by whoever should.

The product decision behind this (ADR-037, D1): the weekly pool belongs to the
**application** — teammates and the Companion — and the end clients' agents
spend **purchased credits only**. Until now every lane spent ``included``
first, so a busy client could leave the partner unable to use the app they pay
for.

This is also what closes debt **D5** of ``PLAN-PENDIENTE-CORTE-2026-09-08``
("separar el bolsillo del Companion del de los clientes"), by product decision
rather than by refactor.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from tests.conftest import make_partner_with_wallet, spend_from_wallet

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _buckets(db_session, partner_id: uuid.UUID) -> tuple[int, int]:
    row = (
        await db_session.execute(
            sa.text(
                "SELECT included_remaining, purchased_remaining "
                "FROM partner_wallets WHERE partner_id = :p"
            ),
            {"p": str(partner_id)},
        )
    ).first()
    return int(row[0]), int(row[1])


async def test_companion_spends_included_first_then_purchased(db_session) -> None:
    world = await make_partner_with_wallet(db_session, included=1_000, purchased=5_000)
    pid = world["partner_id"]

    await spend_from_wallet(partner_id=pid, qty=3_000, lane="companion")

    included, purchased = await _buckets(db_session, pid)
    assert included == 0, "included should be drained first"
    assert purchased == 3_000, "the overflow should come out of purchased"


async def test_local_execution_spends_included_first_too(db_session) -> None:
    world = await make_partner_with_wallet(db_session, included=1_000, purchased=1_000)
    pid = world["partner_id"]

    await spend_from_wallet(partner_id=pid, qty=500, lane="local_exec")

    included, purchased = await _buckets(db_session, pid)
    assert included == 500
    assert purchased == 1_000


async def test_the_channel_never_touches_included(db_session) -> None:
    """R5.2. The one behaviour change of this story."""
    world = await make_partner_with_wallet(db_session, included=10_000, purchased=4_000)
    pid = world["partner_id"]

    await spend_from_wallet(partner_id=pid, qty=3_000, lane="channel")

    included, purchased = await _buckets(db_session, pid)
    assert included == 10_000, (
        "an end client's channel turn ate the partner's application pool. That is "
        "exactly what R5.2 forbids: the pool belongs to the app."
    )
    assert purchased == 1_000


async def test_the_channel_stops_when_purchased_runs_out_even_with_included_left(
    db_session,
) -> None:
    """The flip side, and the one somebody will be tempted to 'fix'.

    A client with no purchased credit does NOT get to fall back on the pool.
    Letting it would re-create the bug this story removes, only quieter.
    """
    world = await make_partner_with_wallet(db_session, included=10_000, purchased=100)
    pid = world["partner_id"]

    result = await spend_from_wallet(partner_id=pid, qty=5_000, lane="channel")

    included, purchased = await _buckets(db_session, pid)
    assert included == 10_000
    assert purchased == 0
    assert result.spent == 100, "it may only spend what purchased had"


async def test_the_same_turn_reprocessed_does_not_debit_twice(db_session) -> None:
    world = await make_partner_with_wallet(db_session, included=10_000, purchased=0)
    pid = world["partner_id"]
    ref = uuid.uuid4().hex

    first = await spend_from_wallet(partner_id=pid, qty=1_000, lane="companion", ref=ref)
    second = await spend_from_wallet(partner_id=pid, qty=1_000, lane="companion", ref=ref)

    assert first.spent == 1_000
    assert second.duplicate is True
    assert second.spent == 0
    included, _ = await _buckets(db_session, pid)
    assert included == 9_000, "the replay debited a second time"
