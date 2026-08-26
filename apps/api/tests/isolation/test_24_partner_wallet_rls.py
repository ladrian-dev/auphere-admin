"""Libro Fase 3: FORCE RLS por partner_id, 404 opaco, no GUC = cero filas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker
from nexus_api.metering.wallet import (
    OverAllocation,
    add_purchased,
    debit_allocation,
    debit_wallet,
    set_allocation,
)
from tests.isolation.test_21_rls_covers_every_tenant_table import (
    PARTNER_FORCE_TABLES,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


def _expires() -> datetime:
    return datetime.now(UTC) + timedelta(days=20)


async def _as_app(session, partner_id: uuid.UUID | None) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.partner_id', :p, false)"),
        {"p": "" if partner_id is None else str(partner_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def _seed_partner(session, partner_id: uuid.UUID, slug: str) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO partners (id, name, slug, status, console_enabled) "
            "VALUES (:id, :n, :s, 'active', true) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": str(partner_id), "n": slug, "s": slug},
    )


async def _seed_wallet(
    session,
    partner_id: uuid.UUID,
    *,
    included: int,
    purchased: int,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO partner_wallets "
            "(partner_id, included_remaining, included_expires_at, purchased_remaining) "
            "VALUES (:p, :i, :e, :u) "
            "ON CONFLICT (partner_id) DO UPDATE SET "
            "included_remaining = EXCLUDED.included_remaining, "
            "included_expires_at = EXCLUDED.included_expires_at, "
            "purchased_remaining = EXCLUDED.purchased_remaining"
        ),
        {"p": str(partner_id), "i": included, "e": _expires(), "u": purchased},
    )


async def test_force_rls_catalog_matches_architect_tables() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (
            await session.execute(
                sa.text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                           (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
                      FROM pg_class c
                      JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'public'
                       AND c.relname = ANY(:names)
                    """
                ),
                {"names": list(PARTNER_FORCE_TABLES)},
            )
        ).all()
    found = {r[0] for r in rows}
    assert found == set(PARTNER_FORCE_TABLES)
    for name, enabled, forced, policies in rows:
        assert enabled and forced and policies >= 1, name


async def test_no_guc_yields_zero_rows(db_session) -> None:
    a = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"wal-{a.hex[:8]}")
        await _seed_wallet(session, a, included=100, purchased=50)
        await session.commit()

    async with sm() as session:
        await _as_app(session, None)
        wallets = await session.scalar(sa.text("SELECT count(*) FROM partner_wallets"))
        allocs = await session.scalar(sa.text("SELECT count(*) FROM partner_allocations"))
        ledger = await session.scalar(sa.text("SELECT count(*) FROM usage_ledger"))
        assert wallets == 0
        assert allocs == 0
        assert ledger == 0


async def test_partner_a_cannot_see_partner_b(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"wa-{a.hex[:8]}")
        await _seed_partner(session, b, f"wb-{b.hex[:8]}")
        await _seed_wallet(session, a, included=100, purchased=0)
        await _seed_wallet(session, b, included=999, purchased=0)
        ta, tb = uuid.uuid4(), uuid.uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO tenants (id, name, slug, plan, status) VALUES "
                "(:ta, 'ta', :sa, 'pro', 'active'), "
                "(:tb, 'tb', :sb, 'pro', 'active')"
            ),
            {"ta": str(ta), "tb": str(tb), "sa": f"ta-{ta.hex[:8]}", "sb": f"tb-{tb.hex[:8]}"},
        )
        await session.execute(
            sa.text(
                "INSERT INTO partner_allocations (partner_id, tenant_id, cap, remaining) "
                "VALUES (:a, :ta, 40, 40), (:b, :tb, 70, 70)"
            ),
            {"a": str(a), "ta": str(ta), "b": str(b), "tb": str(tb)},
        )
        await session.commit()

    async with sm() as session:
        await _as_app(session, a)
        visible = (
            (await session.execute(sa.text("SELECT partner_id FROM partner_wallets")))
            .scalars()
            .all()
        )
        assert visible == [a]
        other = await session.scalar(
            sa.text("SELECT included_remaining FROM partner_wallets WHERE partner_id = :b"),
            {"b": str(b)},
        )
        assert other is None
        allocs = (
            (await session.execute(sa.text("SELECT partner_id FROM partner_allocations")))
            .scalars()
            .all()
        )
        assert allocs == [a]
        other_alloc = await session.scalar(
            sa.text("SELECT remaining FROM partner_allocations WHERE partner_id = :b"),
            {"b": str(b)},
        )
        assert other_alloc is None


async def test_cannot_over_allocate(db_session) -> None:
    partner_id = uuid.uuid4()
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, partner_id, f"oa-{partner_id.hex[:8]}")
        await session.execute(
            sa.text(
                "INSERT INTO tenants (id, name, slug, plan, status) VALUES "
                "(:t1, 't1', :s1, 'pro', 'active'), "
                "(:t2, 't2', :s2, 'pro', 'active')"
            ),
            {
                "t1": str(t1),
                "t2": str(t2),
                "s1": f"s1-{t1.hex[:8]}",
                "s2": f"s2-{t2.hex[:8]}",
            },
        )
        await _seed_wallet(session, partner_id, included=100, purchased=0)
        await session.commit()

    await set_allocation(partner_id, t1, 60)
    with pytest.raises(OverAllocation):
        await set_allocation(partner_id, t2, 50)


async def test_cannot_spend_without_quota(db_session) -> None:
    partner_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, partner_id, f"em-{partner_id.hex[:8]}")
        await _seed_wallet(session, partner_id, included=0, purchased=0)
        await session.commit()

    result = await debit_wallet(
        partner_id=partner_id, qty=25, idempotency_key=f"empty:{partner_id}"
    )
    assert result.spent == 0
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text("SELECT set_config('app.partner_id', :p, false)"),
            {"p": str(partner_id)},
        )
        await session.execute(sa.text("SET ROLE nexus_app"))
        n = await session.scalar(sa.text("SELECT count(*) FROM usage_ledger"))
        assert n == 0


async def test_debit_twice_same_key_does_not_duplicate(db_session) -> None:
    partner_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, partner_id, f"id-{partner_id.hex[:8]}")
        await _seed_wallet(session, partner_id, included=80, purchased=20)
        await session.commit()

    key = f"turn:{partner_id}"
    first = await debit_wallet(partner_id=partner_id, qty=30, idempotency_key=key)
    second = await debit_wallet(partner_id=partner_id, qty=30, idempotency_key=key)
    assert first.spent == 30
    assert first.from_included == 30
    assert second.duplicate is True
    assert second.spent == 0

    snap_key = await debit_wallet(partner_id=partner_id, qty=10, idempotency_key=key)
    assert snap_key.duplicate is True


async def test_included_spent_before_purchased(db_session) -> None:
    partner_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, partner_id, f"or-{partner_id.hex[:8]}")
        await _seed_wallet(session, partner_id, included=10, purchased=100)
        await session.commit()

    result = await debit_wallet(
        partner_id=partner_id, qty=40, idempotency_key=f"order:{partner_id}"
    )
    assert result.from_included == 10
    assert result.from_purchased == 30


async def test_add_purchased_is_the_manual_topup(db_session) -> None:
    partner_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, partner_id, f"tu-{partner_id.hex[:8]}")
        await _seed_wallet(session, partner_id, included=0, purchased=1)
        await session.commit()
    snap = await add_purchased(partner_id, 50)
    assert snap.purchased_remaining == 51


async def test_debit_allocation_does_not_touch_wallet_or_other_client(db_session) -> None:
    partner_id = uuid.uuid4()
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, partner_id, f"al-{partner_id.hex[:8]}")
        await session.execute(
            sa.text(
                "INSERT INTO tenants (id, name, slug, plan, status) VALUES "
                "(:t1, 't1', :s1, 'pro', 'active'), "
                "(:t2, 't2', :s2, 'pro', 'active')"
            ),
            {
                "t1": str(t1),
                "t2": str(t2),
                "s1": f"s1-{t1.hex[:8]}",
                "s2": f"s2-{t2.hex[:8]}",
            },
        )
        await _seed_wallet(session, partner_id, included=200, purchased=10)
        await session.execute(
            sa.text(
                "INSERT INTO partner_allocations (partner_id, tenant_id, cap, remaining) "
                "VALUES (:p, :t1, 80, 80), (:p, :t2, 60, 60)"
            ),
            {"p": str(partner_id), "t1": str(t1), "t2": str(t2)},
        )
        await session.commit()

    result = await debit_allocation(
        partner_id=partner_id,
        tenant_id=t1,
        qty=25,
        idempotency_key=f"companion:{partner_id}",
    )
    assert result.spent == 25
    again = await debit_allocation(
        partner_id=partner_id,
        tenant_id=t1,
        qty=25,
        idempotency_key=f"companion:{partner_id}",
    )
    assert again.duplicate is True
    assert again.spent == 0

    async with sm() as session:
        wallet = (
            await session.execute(
                sa.text(
                    "SELECT included_remaining, purchased_remaining "
                    "FROM partner_wallets WHERE partner_id = :p"
                ),
                {"p": str(partner_id)},
            )
        ).one()
        assert wallet == (200, 10)
        rem = dict(
            (
                await session.execute(
                    sa.text(
                        "SELECT tenant_id, remaining FROM partner_allocations WHERE partner_id = :p"
                    ),
                    {"p": str(partner_id)},
                )
            ).all()
        )
        assert rem[t1] == 55
        assert rem[t2] == 60


async def test_admin_unscoped_without_guc_is_zero_path_guc_is_only_that_partner(
    db_session,
) -> None:
    """Admin without GUC still sees 0 partner_wallets; path GUC is that partner."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"adm-a-{a.hex[:8]}")
        await _seed_partner(session, b, f"adm-b-{b.hex[:8]}")
        await _seed_wallet(session, a, included=100, purchased=10)
        await _seed_wallet(session, b, included=999, purchased=20)
        await session.commit()

    async with sm() as session:
        await _as_app(session, None)
        wallets = await session.scalar(sa.text("SELECT count(*) FROM partner_wallets"))
        assert wallets == 0

    async with sm() as session:
        await _as_app(session, a)
        visible = (
            (await session.execute(sa.text("SELECT partner_id FROM partner_wallets")))
            .scalars()
            .all()
        )
        assert visible == [a]
        other = await session.scalar(
            sa.text("SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :b"),
            {"b": str(b)},
        )
        assert other is None


async def _seed_ticket(session, partner_id: uuid.UUID, ref: str, need: str) -> uuid.UUID:
    ticket_id = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO tickets "
            "(id, partner_id, ticket_ref, category, topic, sla, status, need, checked, opened_by) "
            "VALUES (:id, :p, :r, 'help', 'platform.test', 'best_effort', 'open', :n, '[]'::jsonb, 'test')"
        ),
        {"id": str(ticket_id), "p": str(partner_id), "r": ref, "n": need},
    )
    await session.execute(
        sa.text(
            "INSERT INTO ticket_events "
            "(ticket_id, partner_id, kind, to_status, actor) "
            "VALUES (:id, :p, 'open', 'open', 'test')"
        ),
        {"id": str(ticket_id), "p": str(partner_id)},
    )
    return ticket_id


async def test_tickets_force_rls_a_cannot_see_b(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"tka-{a.hex[:8]}")
        await _seed_partner(session, b, f"tkb-{b.hex[:8]}")
        ticket_a = await _seed_ticket(session, a, f"AU-A-{a.hex[:6]}", "need-a")
        ticket_b = await _seed_ticket(session, b, f"AU-B-{b.hex[:6]}", "need-b")
        await session.commit()

    async with sm() as session:
        await _as_app(session, None)
        assert await session.scalar(sa.text("SELECT count(*) FROM tickets")) == 0
        assert await session.scalar(sa.text("SELECT count(*) FROM ticket_events")) == 0

    async with sm() as session:
        await _as_app(session, a)
        visible = (await session.execute(sa.text("SELECT id FROM tickets"))).scalars().all()
        assert visible == [ticket_a]
        other = await session.scalar(
            sa.text("SELECT id FROM tickets WHERE id = :id"),
            {"id": str(ticket_b)},
        )
        missing = await session.scalar(
            sa.text("SELECT id FROM tickets WHERE id = :id"),
            {"id": str(uuid.uuid4())},
        )
        assert other is None
        assert missing is None
        events = (
            (await session.execute(sa.text("SELECT ticket_id FROM ticket_events"))).scalars().all()
        )
        assert events == [ticket_a]


async def test_tickets_admin_unscoped_sees_a_and_b(db_session) -> None:
    """After admin_unscoped: empty GUC still 0; apply_admin sees A and B."""
    from nexus_api.core.partner_context import apply_admin_to_session

    a, b = uuid.uuid4(), uuid.uuid4()
    ref_a, ref_b = f"AU-A-{a.hex[:6]}", f"AU-B-{b.hex[:6]}"
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"tka-{a.hex[:8]}")
        await _seed_partner(session, b, f"tkb-{b.hex[:8]}")
        await _seed_ticket(session, a, ref_a, "need-a")
        await _seed_ticket(session, b, ref_b, "need-b")
        await session.commit()

    async with sm() as session:
        await _as_app(session, None)
        assert await session.scalar(sa.text("SELECT count(*) FROM tickets")) == 0
        assert await session.scalar(sa.text("SELECT count(*) FROM ticket_events")) == 0

    async with sm() as session:
        async with session.begin():
            await apply_admin_to_session(session)
            visible = set(
                (await session.execute(sa.text("SELECT ticket_ref FROM tickets"))).scalars().all()
            )
            assert {ref_a, ref_b} <= visible
