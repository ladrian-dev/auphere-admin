"""Spec 023 (Requisitos 2.3, 2.4 · T-ISO · T-MET): syncing a toolkit with a
closed list keeps only the list.

The fake provider returns three Stripe tools from the list plus two that
are not in it; only the three get rows. A listed slug the provider stops
returning is logged as ``missing`` and its row, if any, is retired. A
toolkit without a list (Notion) syncs everything as before, and syncing one
connector never touches another's rows. Nothing here writes a usage event.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import (
    AuditLog,
    Connector,
    TenantConnector,
    TenantConnectorStatus,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.services.connectors.composio_client import ComposioTool, FakeComposioClient
from nexus_api.services.connectors.service import sync_tools_for

pytestmark = pytest.mark.asyncio


def _tool(slug: str) -> ComposioTool:
    return ComposioTool(slug=slug, description=f"upstream {slug}", input_schema={"type": "object"})


IN_LIST = ["STRIPE_SEARCH_CUSTOMERS", "STRIPE_LIST_PAYMENT_LINKS", "STRIPE_CREATE_REFUND"]
OUT_OF_LIST = ["STRIPE_ADVANCE_TEST_CLOCK", "STRIPE_CLOSE_DISPUTE"]


async def _connector(db_session, slug: str) -> Connector:
    row = Connector(
        slug=slug,
        display_name=slug.title(),
        vendor=slug.title(),
        category="billing" if slug == "stripe" else "docs",
        auth_kind="oauth_composio",
        mcp_server_ref=f"composio:{slug}",
        auto_enable_on_connect=True,
        auto_enable_destructive=False,
        status="available",
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _install(db_session, tenant_id: uuid.UUID, connector: Connector) -> TenantConnector:
    row = TenantConnector(
        tenant_id=tenant_id,
        connector_id=connector.id,
        status=TenantConnectorStatus.CONNECTED.value,
        credentials_ref={"user_id": "tenant_tenant-a", "composio_connection_id": "conn_x"},
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _rows(db_session, connector: Connector) -> dict[str, ToolCatalog]:
    rows = (
        await db_session.scalars(
            select(ToolCatalog).where(ToolCatalog.connector_id == connector.id)
        )
    ).all()
    return {r.name: r for r in rows}


async def _last_sync_audit(db_session, tenant_id: uuid.UUID, slug: str) -> AuditLog:
    rows = (
        await db_session.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == "connector.tools.synced",
                AuditLog.target == f"connector:{slug}",
            )
            .order_by(AuditLog.created_at.desc())
        )
    ).all()
    assert rows, "sync did not audit"
    return rows[0]


async def _usage_events(db_session, tenant_id: uuid.UUID) -> int:
    return int(
        await db_session.scalar(
            sa.text("SELECT count(*) FROM usage_events WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        )
        or 0
    )


async def test_only_the_closed_list_gets_rows_and_the_rest_is_counted(
    db_session, seed_tenants
) -> None:
    tenant_id = seed_tenants["a"]
    stripe = await _connector(db_session, "stripe")
    fake = FakeComposioClient()
    fake.register_tools("stripe", [_tool(s) for s in IN_LIST + OUT_OF_LIST])

    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        install = await _install(db_session, tenant_id, stripe)
        before = await _usage_events(db_session, tenant_id)

        result = await sync_tools_for(
            db_session, tenant_connector=install, connector=stripe, composio=fake, actor="test"
        )

        rows = await _rows(db_session, stripe)
        assert set(rows) == set(IN_LIST)
        assert sorted(result.added) == sorted(IN_LIST)
        assert result.dropped_count == 2
        assert len(result.missing) == 12 - len(IN_LIST)
        assert "STRIPE_LIST_INVOICES" in result.missing
        assert not any(s in result.missing for s in IN_LIST)

        # Annotations come from the list, not from the prefix heuristic.
        assert rows["STRIPE_SEARCH_CUSTOMERS"].read_only is True
        assert rows["STRIPE_SEARCH_CUSTOMERS"].default_mode == "always"
        assert rows["STRIPE_CREATE_REFUND"].destructive is True
        assert rows["STRIPE_CREATE_REFUND"].default_mode == "blocked"

        audit = await _last_sync_audit(db_session, tenant_id, "stripe")
        assert audit.after_json["dropped_count"] == 2
        assert audit.after_json["missing"] == result.missing

        # T-MET: syncing costs nothing the meter sees.
        assert await _usage_events(db_session, tenant_id) == before


async def test_a_listed_slug_the_provider_stops_returning_is_retired_not_invented(
    db_session, seed_tenants
) -> None:
    tenant_id = seed_tenants["a"]
    stripe = await _connector(db_session, "stripe")
    fake = FakeComposioClient()
    fake.register_tools("stripe", [_tool(s) for s in IN_LIST])

    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        install = await _install(db_session, tenant_id, stripe)
        await sync_tools_for(
            db_session, tenant_connector=install, connector=stripe, composio=fake, actor="test"
        )
        assert set(await _rows(db_session, stripe)) == set(IN_LIST)

        # The provider withdraws one of the three.
        fake.register_tools("stripe", [_tool(s) for s in IN_LIST[:2]])
        result = await sync_tools_for(
            db_session, tenant_connector=install, connector=stripe, composio=fake, actor="test"
        )

        rows = await _rows(db_session, stripe)
        assert rows["STRIPE_CREATE_REFUND"].status == ToolStatus.DEPRECATED
        assert result.deprecated == ["STRIPE_CREATE_REFUND"]
        assert "STRIPE_CREATE_REFUND" in result.missing
        assert result.added == []


async def test_a_toolkit_without_list_syncs_everything_as_before(db_session, seed_tenants) -> None:
    tenant_id = seed_tenants["a"]
    notion = await _connector(db_session, "notion")
    fake = FakeComposioClient()
    fake.register_tools("notion", [_tool("NOTION_SEARCH"), _tool("NOTION_DO_ANYTHING")])

    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        install = await _install(db_session, tenant_id, notion)
        result = await sync_tools_for(
            db_session, tenant_connector=install, connector=notion, composio=fake, actor="test"
        )

        assert set(await _rows(db_session, notion)) == {"NOTION_SEARCH", "NOTION_DO_ANYTHING"}
        assert result.missing == [] and result.dropped_count == 0
        audit = await _last_sync_audit(db_session, tenant_id, "notion")
        assert "missing" not in audit.after_json
        assert "dropped_count" not in audit.after_json


async def test_syncing_one_connector_never_touches_another(db_session, seed_tenants) -> None:
    """T-ISO: the filter is per connector. Notion's rows survive a Stripe
    sync untouched, and Stripe never gains a Notion row."""
    tenant_id = seed_tenants["a"]
    stripe = await _connector(db_session, "stripe")
    notion = await _connector(db_session, "notion")
    fake = FakeComposioClient()
    fake.register_tools("stripe", [_tool(s) for s in IN_LIST + OUT_OF_LIST])
    fake.register_tools("notion", [_tool("NOTION_SEARCH")])

    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        notion_install = await _install(db_session, tenant_id, notion)
        stripe_install = await _install(db_session, tenant_id, stripe)
        await sync_tools_for(
            db_session, tenant_connector=notion_install, connector=notion, composio=fake, actor="t"
        )
        notion_before = {n: r.status for n, r in (await _rows(db_session, notion)).items()}

        await sync_tools_for(
            db_session, tenant_connector=stripe_install, connector=stripe, composio=fake, actor="t"
        )

        assert {n: r.status for n, r in (await _rows(db_session, notion)).items()} == notion_before
        assert set(await _rows(db_session, stripe)) == set(IN_LIST)
