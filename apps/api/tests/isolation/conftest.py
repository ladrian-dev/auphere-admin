"""Isolation suite shared fixtures: two distinct tenants per test."""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def tenants_ab(db_session) -> dict[str, uuid.UUID]:
    from nexus_api.db.models import Tenant, TenantPlan

    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    db_session.add_all(
        [
            Tenant(id=a_id, name="Iso A", slug=f"iso-a-{a_id.hex[:6]}", plan=TenantPlan.PRO),
            Tenant(id=b_id, name="Iso B", slug=f"iso-b-{b_id.hex[:6]}", plan=TenantPlan.ESSENTIAL),
        ]
    )
    await db_session.commit()
    return {"a": a_id, "b": b_id}


async def set_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await session.execute(text("SET LOCAL ROLE nexus_app"))
