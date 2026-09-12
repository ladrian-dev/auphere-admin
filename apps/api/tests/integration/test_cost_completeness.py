"""Spec 004 · R1.4 / CE-003 — a partial total says so.

``/admin/tenants/{id}/cost`` already carries ``complete`` and
``total_unpriced_records``; migration 0072 already decided that an unpriceable
row gets NULL rather than 0. What was missing is the thing that makes those
fields useful: the models the product actually sells having a rate, so that
``complete`` is true for ordinary traffic instead of permanently false.

This is the acceptance test of the story: a month of traffic on the closed
catalog answers ``complete = true``; a month with one unpriceable row answers
``complete = false`` and counts it apart, never folding it into the total as a
zero.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantPlan

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOLD_MODEL = "openai/gpt-5.6-sol"
#: In the catalog on purpose and with no rate: migration 0072 seeded it that
#: way and 0076 only priced gpt-4o. Used here as the unpriceable case.
UNPRICED_MODEL = "openai/whisper-1"


async def _tenant(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Completeness",
            slug=f"cc-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()
    return tenant_id


async def _usage(tenant_id: uuid.UUID, *, model: str, cost: str | None) -> None:
    occurred_at = datetime.now(UTC) - timedelta(minutes=1)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        month = occurred_at.date().replace(day=1)
        name = f"usage_records_y{month.year}m{month.month:02d}"
        exists = await session.scalar(
            sa.text("SELECT 1 FROM pg_class WHERE relname = :n"), {"n": name}
        )
        if not exists:
            await session.execute(
                sa.text("SELECT ensure_month_partition('usage_records', :m)"),
                {"m": month},
            )
        await session.execute(
            sa.text(
                """
                INSERT INTO usage_records
                    (tenant_id, occurred_at, meter, quantity, billable_qty,
                     cost_usd, model, idempotency_key)
                VALUES (:t, :at, 'llm.input_tokens', 1000, 1000,
                        CAST(:cost AS numeric), :model, :idem)
                """
            ),
            {
                "t": str(tenant_id),
                "at": occurred_at,
                "cost": cost,
                "model": model,
                "idem": uuid.uuid4().hex,
            },
        )
        await session.commit()


async def test_a_month_on_the_sold_catalog_is_complete(client, admin_headers, db_session) -> None:
    """Rows arrive UNPRICED and the loaded rates make the month complete.

    Inserting them with a cost already filled in would make this pass on an
    empty catalog — it would assert that the endpoint can add up numbers, not
    that the models we sell have rates. The rows go in as the emitter leaves
    them (``cost_usd`` NULL, §0071) and the backfill values them.
    """
    from tests.integration.test_reprice_backfill import _run_backfill

    tenant_id = await _tenant(db_session)
    await _usage(tenant_id, model=SOLD_MODEL, cost=None)
    await _usage(tenant_id, model=SOLD_MODEL, cost=None)

    before = await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)
    assert before.json()["complete"] is False, "precondition: they start unpriced"

    await _run_backfill()

    res = await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total_unpriced_records"] == 0
    assert body["complete"] is True


async def test_one_unpriceable_row_makes_the_total_declare_itself_partial(
    client, admin_headers, db_session
) -> None:
    tenant_id = await _tenant(db_session)
    await _usage(tenant_id, model=SOLD_MODEL, cost="0.00400000")
    await _usage(tenant_id, model=UNPRICED_MODEL, cost=None)

    res = await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total_unpriced_records"] == 1, (
        "the unpriceable row was not counted apart; SUM(cost_usd) swallowed it"
    )
    assert body["complete"] is False
