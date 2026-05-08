"""Extra: audit_log isolation.

The audit table is the operational record of mutations. Its rows MUST honour
RLS — a B-scoped session cannot see A's audit entries.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import AuditLog
from nexus_api.repositories import AuditRepository

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_audit_log_isolated(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    with tenant_context(a):
        async with db_session.begin():
            await set_tenant(db_session, a)
            await AuditRepository(db_session).record(
                actor="alice",
                action="agent_config.stage",
                target="A-only",
            )

    with tenant_context(b):
        async with db_session.begin():
            await set_tenant(db_session, b)
            await AuditRepository(db_session).record(
                actor="bob",
                action="agent_config.stage",
                target="B-only",
            )
            rows = (await db_session.execute(select(AuditLog))).scalars().all()
            targets = {r.target for r in rows}
            assert targets == {"B-only"}

    with tenant_context(a):
        async with db_session.begin():
            await set_tenant(db_session, a)
            rows = (await db_session.execute(select(AuditLog))).scalars().all()
            targets = {r.target for r in rows}
            assert targets == {"A-only"}
