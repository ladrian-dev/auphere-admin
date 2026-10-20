"""Spec 004 · R6 — the per-client cap changes meaning, and keeps its invariant.

Consequence of R5.2: once the end clients spend **purchased** only, a client's
cap stops being a slice of the book and becomes a **monthly spending ceiling on
purchased credit**. The partner still sets it, it still silences only that
client when exhausted, and the sum of caps still cannot exceed the balance it is
computed against — what changes is which balance that is.

Decided here rather than discovered later: ``data-model.md`` §"Lo que cambia de
significado" says it, and this is the test that holds it.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import make_partner_with_wallet

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _client_of(db_session, partner_id: uuid.UUID) -> uuid.UUID:
    from nexus_api.db.models import PartnerTenant, Tenant, TenantPlan

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Alloc client",
            slug=f"al-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
            partner_id=partner_id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=f"ref-{tenant_id.hex[:6]}",
            tenant_id=tenant_id,
            client_name="Alloc client",
        )
    )
    await db_session.commit()
    return tenant_id


async def test_allocatable_is_computed_against_purchased(db_session) -> None:
    from nexus_api.metering.wallet import allocatable_for

    world = await make_partner_with_wallet(db_session, included=900_000, purchased=20_000)
    pid = world["partner_id"]
    tid = await _client_of(db_session, pid)

    allocatable = await allocatable_for(db_session, pid, tid)
    assert allocatable == 20_000, (
        "the figure the console shows is purchased credit not yet committed to "
        "other clients; counting the application pool in would show budget the "
        "clients can never spend"
    )


async def test_a_cap_is_a_spending_limit_not_a_reservation(db_session) -> None:
    """Decided 2026-09-12: the cap is NOT bounded by the balance.

    Bounding it meant a partner with no purchased credit could not give any
    client a quota, so its clients were **born mute** — the failure mode that
    caused the 31-Aug outage. What stops a turn is ``allow_channel_turn``,
    which reads the real balance on every turn; the cap is the partner's own
    ceiling so one client cannot take the lot.
    """
    from nexus_api.metering.wallet import set_allocation

    world = await make_partner_with_wallet(db_session, included=900_000, purchased=10_000)
    pid = world["partner_id"]
    tid = await _client_of(db_session, pid)

    row = await set_allocation(pid, tid, 50_000)
    assert row.cap == 50_000, "a spending limit above today's balance is legitimate"


async def test_an_exhausted_client_silences_only_itself(db_session) -> None:
    from nexus_api.metering.wallet import allow_channel_turn, set_allocation

    world = await make_partner_with_wallet(db_session, included=0, purchased=10_000)
    pid = world["partner_id"]
    a = await _client_of(db_session, pid)
    b = await _client_of(db_session, pid)
    await set_allocation(pid, a, 0)
    await set_allocation(pid, b, 5_000)

    assert await allow_channel_turn(a) is False
    assert await allow_channel_turn(b) is True


async def test_the_client_cap_is_replenished_monthly_not_weekly(db_session) -> None:
    """R6.2 (spec 004) and spec 033 R6.1 — the cap refills once per calendar
    month and never with the weekly pool. Was a test that read the
    docstring; now it moves the clock."""
    from datetime import UTC, date, datetime

    import sqlalchemy as sa

    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import PartnerAllocation
    from nexus_api.metering.wallet import replenish_allocations

    partner_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    await db_session.execute(
        sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :n, 'active')"),
        {"i": str(partner_id), "n": f"mo-{partner_id.hex[:8]}"},
    )
    await db_session.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan, status, partner_id) "
            "VALUES (:i, 'c', :s, 'pro', 'active', :p)"
        ),
        {"i": str(tenant_id), "s": f"mo-{tenant_id.hex[:8]}", "p": str(partner_id)},
    )
    await db_session.commit()
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        s.add(
            PartnerAllocation(
                partner_id=partner_id,
                tenant_id=tenant_id,
                cap=100,
                remaining=0,
                period_month=date(2026, 9, 1),
            )
        )

    async def refill(at: datetime) -> int:
        async with sm() as s, s.begin():
            await apply_partner_to_session(s, partner_id)
            return await replenish_allocations(s, partner_id=partner_id, now=at)

    async def remaining() -> int:
        async with sm() as s, s.begin():
            await apply_partner_to_session(s, partner_id)
            row = await s.scalar(
                sa.select(PartnerAllocation).where(PartnerAllocation.tenant_id == tenant_id)
            )
            assert row is not None
            return int(row.remaining)

    # Later in September: same month, nothing refills.
    assert await refill(datetime(2026, 9, 28, 23, 0, tzinfo=UTC)) == 0
    assert await remaining() == 0
    # October 1st: the cap is whole again, once.
    assert await refill(datetime(2026, 10, 1, 0, 5, tzinfo=UTC)) == 1
    assert await remaining() == 100
    # A week later (the pool's cycle) nothing happens.
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        await s.execute(
            sa.update(PartnerAllocation)
            .where(PartnerAllocation.tenant_id == tenant_id)
            .values(remaining=10)
        )
    assert await refill(datetime(2026, 10, 8, 0, 5, tzinfo=UTC)) == 0
    assert await remaining() == 10


async def test_a_client_of_a_partner_without_credit_is_not_born_mute(db_session) -> None:
    """The regression this decision exists to prevent."""
    from nexus_api.metering.wallet import seed_default_allocation

    world = await make_partner_with_wallet(db_session, included=5_000_000, purchased=0)
    pid = world["partner_id"]
    tid = await _client_of(db_session, pid)

    cap = await seed_default_allocation(
        db_session, partner_id=pid, tenant_id=tid, default_cap=50_000
    )
    assert cap == 50_000, (
        "the new client was born with a zero quota because the partner has no "
        "purchased credit yet — born mute, the 31-Aug failure mode"
    )


# V35 — "los avisos al 80 % y al 100 % siguen llegando, sin duplicar" — ya lo
# cubre ``tests/integration/test_wallet_alerts.py``, que ejercita el servicio
# entero con su propia gestión de transacción. Repetirlo aquí con una sesión
# de test ya abierta probaba menos y fallaba por la forma de llamarlo, no por
# el comportamiento. Lo que esta spec tiene que garantizar es que ese test
# sigue verde después de mover el tope por cliente a ``purchased``.
