"""Block M.2 — per-tenant tool catalog with connector install status.

Verifies the LEFT JOIN behavior of ``GET /admin/tenants/:id/tool-catalog``:

- Baseline seeded tools (no connector binding, ``connector_id IS NULL``)
  report every install field as ``null`` — they still show up so the
  editor can render them as "internal" capabilities with no connector
  CTA.
- Tools bound to a connector the tenant has installed return the install
  status (``connected``, ``paused``, etc.) and the connector display
  metadata so the UI can group + decorate them.
- Tenant A's install does not bleed into Tenant B for the same global
  tool — RLS-scoped JOIN keeps them separated.

Test-inserted tool rows MUST have either ``connector_id`` set or
``mcp_server LIKE 'composio:%'`` so the global ``tests/conftest.py``
truncate sweep cleans them between tests (see the DELETE rule there).
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.db.models import (
    Connector,
    Tenant,
    TenantConnector,
    TenantPlan,
    TenantStatus,
    ToolCatalog,
    ToolStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-token"}


async def _seed_two_tenants_and_bound_tool(
    db_session,
    *,
    tenant_a_id: uuid.UUID,
    tenant_b_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A + B tenants, one connector, one tool bound to it — A installs
    the connector, B does not. Returns (connector_id, tool_id)."""
    db_session.add_all(
        [
            Tenant(
                id=tenant_a_id,
                name="M2 A",
                slug=f"m2-a-{tenant_a_id.hex[:6]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
            ),
            Tenant(
                id=tenant_b_id,
                name="M2 B",
                slug=f"m2-b-{tenant_b_id.hex[:6]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
            ),
        ]
    )
    connector = Connector(
        slug=f"m2-conn-{tenant_a_id.hex[:6]}",
        display_name="M2 Connector",
        vendor="m2",
        category="other",
        capabilities=[],
        auth_kind="api_key",
        mcp_server_ref="m2_server",
        provider_meta={"logo_url": "https://example.invalid/m2.png"},
        status="available",
    )
    db_session.add(connector)
    await db_session.commit()
    await db_session.refresh(connector)

    bound_tool = ToolCatalog(
        name="m2.bound_tool",
        description="bound to a connector",
        mcp_server="composio:m2_server",  # cleaned by conftest truncate
        input_schema={},
        output_schema={},
        side_effects=[],
        capability_tags=[],
        cost_estimate={},
        status=ToolStatus.ACTIVE,
        connector_id=connector.id,
        read_only=False,
        destructive=True,
        requires_consent=True,
    )
    db_session.add(bound_tool)
    await db_session.commit()
    await db_session.refresh(bound_tool)

    # Tenant A installed the connector. Tenant B did not.
    db_session.add(
        TenantConnector(
            tenant_id=tenant_a_id,
            connector_id=connector.id,
            status="connected",
            credentials_ref={},
            scopes_granted=[],
            config={},
        )
    )
    await db_session.commit()
    return connector.id, bound_tool.id


async def test_tenant_a_sees_connected_status(client, db_session):
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    connector_id, _tool_id = await _seed_two_tenants_and_bound_tool(
        db_session, tenant_a_id=a_id, tenant_b_id=b_id
    )

    r = await client.get(f"/admin/tenants/{a_id}/tool-catalog", headers=_admin_headers())
    assert r.status_code == 200, r.text
    by_name = {t["name"]: t for t in r.json()}

    bound = by_name["m2.bound_tool"]
    assert bound["connector_id"] == str(connector_id)
    assert bound["connector_slug"].startswith("m2-conn-")
    assert bound["connector_display_name"] == "M2 Connector"
    assert bound["connector_logo_url"] == "https://example.invalid/m2.png"
    assert bound["tenant_connector_status"] == "connected"
    assert bound["destructive"] is True
    assert bound["requires_consent"] is True


async def test_baseline_seed_tools_report_no_connector(client, db_session):
    """Baseline tools (booking.*, queue.*, client.*) come from migration
    0003 with ``connector_id IS NULL`` — they should still appear in
    the per-tenant catalog with all install fields ``null``. The editor
    will render them grouped under "Sin connector" or similar."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="M2 Baseline",
            slug=f"m2-base-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()

    r = await client.get(f"/admin/tenants/{tenant_id}/tool-catalog", headers=_admin_headers())
    assert r.status_code == 200, r.text
    by_name = {t["name"]: t for t in r.json()}

    baseline = by_name["booking.check_availability"]
    assert baseline["connector_id"] is None
    assert baseline["connector_slug"] is None
    assert baseline["connector_display_name"] is None
    assert baseline["tenant_connector_status"] is None


async def test_tenant_b_sees_null_install_status_for_same_tool(client, db_session):
    """Same global tool, same connector — Tenant B hasn't installed the
    connector, so install_status is null for them. Tenant A's install
    must not leak across."""
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    await _seed_two_tenants_and_bound_tool(db_session, tenant_a_id=a_id, tenant_b_id=b_id)

    r = await client.get(f"/admin/tenants/{b_id}/tool-catalog", headers=_admin_headers())
    assert r.status_code == 200, r.text
    by_name = {t["name"]: t for t in r.json()}

    bound = by_name["m2.bound_tool"]
    # The connector itself is still surfaced (global catalog) — so the UI
    # can show "Requires M2 Connector — connect first".
    assert bound["connector_slug"].startswith("m2-conn-")
    assert bound["connector_display_name"] == "M2 Connector"
    # But B has not installed it.
    assert bound["tenant_connector_status"] is None


async def test_unknown_tenant_404(client):
    r = await client.get(
        f"/admin/tenants/{uuid.uuid4()}/tool-catalog",
        headers=_admin_headers(),
    )
    assert r.status_code == 404
