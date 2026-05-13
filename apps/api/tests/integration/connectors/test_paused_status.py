"""Block M.6 — ``paused`` is a valid TenantConnector status.

Verifies the migration 0015 + ORM enum: an install can carry status
``paused``, the round-trip preserves it, and the CHECK constraint
accepts it. M.5 will wire the runtime check that treats paused tools
as skipped — this test is the schema-level foundation.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Connector,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    TenantPlan,
    TenantStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_paused_is_in_enum() -> None:
    assert TenantConnectorStatus("paused") is TenantConnectorStatus.PAUSED


async def test_tenant_connector_accepts_paused_status(db_session) -> None:
    tenant_id = uuid.uuid4()
    connector = Connector(
        slug=f"m6-conn-{tenant_id.hex[:6]}",
        display_name="M6 fake",
        vendor="m6",
        category="other",
        capabilities=[],
        auth_kind="api_key",
        mcp_server_ref="m6_server",
        provider_meta={},
        status="available",
    )
    db_session.add_all(
        [
            Tenant(
                id=tenant_id,
                name="M6 Tenant",
                slug=f"m6-{tenant_id.hex[:6]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
            ),
            connector,
        ]
    )
    await db_session.commit()
    await db_session.refresh(connector)

    db_session.add(
        TenantConnector(
            tenant_id=tenant_id,
            connector_id=connector.id,
            status=TenantConnectorStatus.PAUSED.value,
            credentials_ref={},
            scopes_granted=[],
            config={},
        )
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            sa.select(TenantConnector).where(
                TenantConnector.connector_id == connector.id,
            )
        )
    ).scalar_one()
    assert row.status == "paused"
