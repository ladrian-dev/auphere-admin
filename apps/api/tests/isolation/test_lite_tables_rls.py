"""Spec 030 — garantía 1 sobre las tablas de la consola lite (R2.1, R17.3).

El barrido de catálogo (``test_21``) ya obliga a que toda tabla con
``tenant_id`` tenga RLS o una razón escrita; las dos de identidad de la spec
030 tienen la suya allí. Esto prueba el **comportamiento** de las que sí son
datos del cliente: con ``app.tenant_id = A``, las filas de B no se leen ni se
modifican.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.models import ClientAccess
from tests.conftest import make_client_access

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_client_access_is_invisible_across_tenants(
    db_session, console_world, scoped_session_factory
) -> None:
    a, b = console_world["a"], console_world["b"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    await make_client_access(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])

    session = await scoped_session_factory(a["tenant_id"])
    try:
        seen = (await session.execute(sa.select(ClientAccess.tenant_id))).scalars().all()
        assert seen == [a["tenant_id"]]
        result = await session.execute(
            sa.update(ClientAccess)
            .where(ClientAccess.tenant_id == b["tenant_id"])
            .values(enabled=False)
        )
        assert result.rowcount == 0
    finally:
        await session.rollback()
        await session.close()
