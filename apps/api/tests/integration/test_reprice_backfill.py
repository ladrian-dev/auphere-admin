"""Spec 004 · R1.3 — the backfill prices what was measured, and only that.

Integration and not unit because the thing under test is SQL against the real
table: ``usage_records`` is partitioned by month and has RLS ENABLE + FORCE,
and either can make an UPDATE touch zero rows without raising.

Two properties, and the second is the one that costs money if it breaks:

1. A row measured but left unpriced (``cost_usd IS NULL``) gets valued once the
   rate exists.
2. A row that ALREADY had a cost is never touched. Re-running the backfill —
   which happens every time the migration is replayed on a restored dump —
   must not re-value history at yesterday's rate.

The statement is loaded from the migration module itself rather than copied
here. Migration 0076 says a migration is a historical fact that must not change
because someone edits a shared module six months later; that rule is about
migrations sharing code with each other, not about a test reading the migration
it is testing. Loading it means editing the migration's SQL breaks this test,
which is the point.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantPlan

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0114_sold_model_prices.py"
)

#: A model the spec loads a rate for, and the meter that rate applies to.
PRICED_MODEL = "openai/gpt-5.6-terra"
PRICED_METER = "llm.input_tokens"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("m0114", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _tenant(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Reprice",
            slug=f"rp-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()
    return tenant_id


async def _usage(tenant_id: uuid.UUID, *, cost: str | None, quantity: int = 1_000_000) -> str:
    """One usage row. Returns its idempotency key so the test can find it."""
    key = uuid.uuid4().hex
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
                VALUES (:t, :at, :meter, :q, :q,
                        CAST(:cost AS numeric), :model, :idem)
                """
            ),
            {
                "t": str(tenant_id),
                "at": occurred_at,
                "meter": PRICED_METER,
                "q": quantity,
                "cost": cost,
                "model": PRICED_MODEL,
                "idem": key,
            },
        )
        await session.commit()
    return key


async def _cost_of(tenant_id: uuid.UUID, key: str) -> Any:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await session.scalar(
            sa.text("SELECT cost_usd FROM usage_records WHERE idempotency_key = :k"),
            {"k": key},
        )


async def _run_backfill() -> None:
    """Run the migration's own repricing statement against the test database."""
    module = _load_migration()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text("SET LOCAL row_security = off"))
        await session.execute(sa.text(module.BACKFILL_SQL))
        await session.commit()


async def test_backfill_prices_a_row_that_was_measured_without_a_rate(db_session) -> None:
    tenant_id = await _tenant(db_session)
    key = await _usage(tenant_id, cost=None)
    assert await _cost_of(tenant_id, key) is None

    await _run_backfill()

    # 1M input tokens of terra at $2.00/Mtok. Compared as Decimal, not float:
    # ``cost_usd`` is numeric(14,8) and money read back as a float is exactly
    # how a cent goes missing between the database and the assertion.
    assert await _cost_of(tenant_id, key) == Decimal("2.00000000")


async def test_backfill_never_touches_a_row_that_already_had_a_cost(db_session) -> None:
    tenant_id = await _tenant(db_session)
    key = await _usage(tenant_id, cost="0.00000001")

    await _run_backfill()

    assert await _cost_of(tenant_id, key) == Decimal("0.00000001"), (
        "the backfill re-valued history. Its WHERE clause must be cost_usd IS NULL."
    )


async def test_backfill_is_idempotent(db_session) -> None:
    tenant_id = await _tenant(db_session)
    key = await _usage(tenant_id, cost=None)

    await _run_backfill()
    once = await _cost_of(tenant_id, key)
    await _run_backfill()
    twice = await _cost_of(tenant_id, key)

    assert once == twice, "running the backfill twice changed a row"
