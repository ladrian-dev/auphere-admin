"""Extra: tenant_credentials isolation.

Encrypted credentials per tenant must not leak across tenants. Combines RLS
(garantía 1) with at-rest encryption (Fernet) so that a misconfigured key
cannot accidentally surface another tenant's blob.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from nexus_api.db.models import TenantCredentials

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_credentials_invisible_across_tenants(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            TenantCredentials(
                tenant_id=a,
                integration="agendapro",
                encrypted_payload=b"A-secret",
            )
        )

    async with db_session.begin():
        await set_tenant(db_session, b)
        db_session.add(
            TenantCredentials(
                tenant_id=b,
                integration="agendapro",
                encrypted_payload=b"B-secret",
            )
        )

    async with db_session.begin():
        await set_tenant(db_session, a)
        rows = (await db_session.execute(select(TenantCredentials))).scalars().all()
        assert len(rows) == 1
        assert rows[0].encrypted_payload == b"A-secret"


async def test_credentials_table_unique_constraint_per_tenant(db_session, tenants_ab):
    """Same tenant can't have two rows for the same integration; different
    tenants both can have agendapro creds at once."""
    a = tenants_ab["a"]
    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            TenantCredentials(
                tenant_id=a,
                integration="agendapro",
                encrypted_payload=b"v1",
            )
        )

    # Adding another agendapro for the same tenant should violate the unique
    # constraint.
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        async with db_session.begin():
            await set_tenant(db_session, a)
            db_session.add(
                TenantCredentials(
                    tenant_id=a,
                    integration="agendapro",
                    encrypted_payload=b"v2",
                )
            )
