"""Garantía 3 — Knowledge graph scoping.

KG queries always carry tenant_id; without app.tenant_id set, no rows return.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from nexus_api.db.models import KGNode

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_kg_nodes_isolated_per_tenant(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]
    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add_all(
            [
                KGNode(tenant_id=a, label="Barber", properties={"name": "Pedro"}),
                KGNode(tenant_id=a, label="Barber", properties={"name": "Ana"}),
            ]
        )

    async with db_session.begin():
        await set_tenant(db_session, b)
        db_session.add(KGNode(tenant_id=b, label="Barber", properties={"name": "Carlos"}))

    async with db_session.begin():
        await set_tenant(db_session, a)
        rows = (
            (await db_session.execute(select(KGNode).where(KGNode.label == "Barber")))
            .scalars()
            .all()
        )
        names = {n.properties["name"] for n in rows}
        assert names == {"Pedro", "Ana"}
        assert "Carlos" not in names
