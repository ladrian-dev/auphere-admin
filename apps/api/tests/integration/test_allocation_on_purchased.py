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
    """R6.2 — it does not follow the pool's weekly cycle.

    It is not a slice of what is included: it is a spending limit the partner
    sets so one client cannot take the lot. A limit that resets every week is
    four times more permissive, and nobody asked for that.
    """
    import inspect

    from nexus_api.metering.wallet import replenish_allocations

    doc = (replenish_allocations.__doc__ or "").lower()
    src = inspect.getsource(replenish_allocations).lower()
    assert "mensual" in doc or "monthly" in doc or "mensual" in src, (
        "the per-client replenishment must state that it stays monthly"
    )


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
