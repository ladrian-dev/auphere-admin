"""BUG-E2E-02 — the seed-apply endpoint unions the seed's required tools
with the read-only ("always"-mode) tools of every installed connector.

The wedge bug before this fix: an operator who connected WooCommerce
BEFORE applying a seed landed on an editor where the woocommerce.*
tools were visible (via the per-tenant catalog) but UNSELECTED. The
agent silently couldn't use the connector. The mirror path (connect
AFTER seed) already worked via ``auto_enable_connector_tools`` —
these tests pin both orderings to behave the same.
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


_ADMIN_HEADERS = {"Authorization": "Bearer test-admin-token"}

_PLACEHOLDERS = {
    "tenant.name": "Cultor Barber",
    "tenant.address": "Av. Apoquindo 1234",
    "tenant.timezone": "America/Santiago",
    "tenant.business_hours_label": "Lun-Sáb 10-19",
}


async def _seed_tenant_with_connector(
    db_session,
    *,
    tenant_id: uuid.UUID,
    install_status: str = "connected",
    auto_enable: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create one tenant, one connector (auto-enable configurable), and
    two tool rows under it: one ``always``-mode and one ``blocked``.
    Returns ``(connector_id, always_tool_id, blocked_tool_id)``.

    Caller is responsible for committing — we flush so the IDs are
    available before the test calls the endpoint.
    """
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Seed-Connector Merge Test",
            slug=f"seed-merge-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    connector = Connector(
        slug=f"seed-merge-conn-{tenant_id.hex[:6]}",
        display_name="Seed-Merge Connector",
        vendor="seed-merge",
        category="other",
        capabilities=[],
        auth_kind="api_key",
        mcp_server_ref="seed_merge_server",
        provider_meta={},
        auto_enable_on_connect=auto_enable,
        status="available",
    )
    db_session.add(connector)
    await db_session.commit()
    await db_session.refresh(connector)

    always_tool = ToolCatalog(
        name="seedmerge.read_only_thing",
        description="A read-only connector tool — should be pre-selected.",
        mcp_server="composio:seed_merge_server",
        input_schema={},
        output_schema={},
        side_effects=[],
        capability_tags=[],
        cost_estimate={},
        status=ToolStatus.ACTIVE,
        connector_id=connector.id,
        read_only=True,
        destructive=False,
        requires_consent=False,
        default_mode="always",
    )
    blocked_tool = ToolCatalog(
        name="seedmerge.destructive_thing",
        description="A destructive connector tool — should NOT be pre-selected.",
        mcp_server="composio:seed_merge_server",
        input_schema={},
        output_schema={},
        side_effects=["external_api"],
        capability_tags=[],
        cost_estimate={},
        status=ToolStatus.ACTIVE,
        connector_id=connector.id,
        read_only=False,
        destructive=True,
        requires_consent=True,
        default_mode="blocked",
    )
    db_session.add_all([always_tool, blocked_tool])
    await db_session.commit()
    await db_session.refresh(always_tool)
    await db_session.refresh(blocked_tool)

    db_session.add(
        TenantConnector(
            tenant_id=tenant_id,
            connector_id=connector.id,
            status=install_status,
            credentials_ref={},
            scopes_granted=[],
            config={},
        )
    )
    await db_session.commit()
    return connector.id, always_tool.id, blocked_tool.id


async def test_seed_apply_includes_always_mode_connector_tools(
    client, db_session
):
    """Happy path: connect first, then apply seed → the connector's
    ``always``-mode tool lands in the staged config alongside the seed's
    ``tools_required``. The ``blocked``-mode tool stays out."""
    tenant_id = uuid.uuid4()
    await _seed_tenant_with_connector(db_session, tenant_id=tenant_id)

    r = await client.post(
        f"/admin/tenants/{tenant_id}/agent-config/from-seed",
        headers=_ADMIN_HEADERS,
        json={
            "seed_template_ref": "barbershop_v1",
            "placeholders": _PLACEHOLDERS,
        },
    )
    assert r.status_code == 201, r.text
    config = r.json()
    tools = set(config["tools"])
    # Seed's own required tools survive the merge.
    assert "booking.create_appointment" in tools
    # Connector's "always"-mode tool is auto-picked.
    assert "seedmerge.read_only_thing" in tools
    # Connector's "blocked"-mode tool is NOT auto-picked.
    assert "seedmerge.destructive_thing" not in tools


async def test_seed_apply_skips_connector_with_auto_enable_off(
    client, db_session
):
    """A connector whose ``auto_enable_on_connect=false`` does NOT
    contribute tools to a fresh seed apply — the operator opts in
    deliberately. Mirrors ``auto_enable_connector_tools``."""
    tenant_id = uuid.uuid4()
    await _seed_tenant_with_connector(
        db_session, tenant_id=tenant_id, auto_enable=False
    )

    r = await client.post(
        f"/admin/tenants/{tenant_id}/agent-config/from-seed",
        headers=_ADMIN_HEADERS,
        json={
            "seed_template_ref": "barbershop_v1",
            "placeholders": _PLACEHOLDERS,
        },
    )
    assert r.status_code == 201, r.text
    tools = set(r.json()["tools"])
    assert "booking.create_appointment" in tools
    assert "seedmerge.read_only_thing" not in tools
    assert "seedmerge.destructive_thing" not in tools


async def test_seed_apply_includes_paused_connector_tools(client, db_session):
    """A paused install still contributes — the operator can resume
    later without re-applying the seed. Mirrors the editor's
    ``canSelect`` which allows paused tools to be ticked."""
    tenant_id = uuid.uuid4()
    await _seed_tenant_with_connector(
        db_session, tenant_id=tenant_id, install_status="paused"
    )

    r = await client.post(
        f"/admin/tenants/{tenant_id}/agent-config/from-seed",
        headers=_ADMIN_HEADERS,
        json={
            "seed_template_ref": "barbershop_v1",
            "placeholders": _PLACEHOLDERS,
        },
    )
    assert r.status_code == 201, r.text
    tools = set(r.json()["tools"])
    assert "seedmerge.read_only_thing" in tools


async def test_seed_apply_skips_disconnected_connector(client, db_session):
    """A disconnected install does NOT contribute — the operator
    needs to reconnect or pick another connector. Disconnect is
    terminal in the status machine."""
    tenant_id = uuid.uuid4()
    await _seed_tenant_with_connector(
        db_session, tenant_id=tenant_id, install_status="disconnected"
    )

    r = await client.post(
        f"/admin/tenants/{tenant_id}/agent-config/from-seed",
        headers=_ADMIN_HEADERS,
        json={
            "seed_template_ref": "barbershop_v1",
            "placeholders": _PLACEHOLDERS,
        },
    )
    assert r.status_code == 201, r.text
    tools = set(r.json()["tools"])
    assert "booking.create_appointment" in tools
    assert "seedmerge.read_only_thing" not in tools


async def test_seed_apply_no_connectors_back_compat(client, db_session):
    """A tenant with NO installed connectors keeps the legacy behaviour:
    the staged tools equal the seed template's required set. Confirms
    the union is additive and doesn't regress."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="No-Connector Test",
            slug=f"no-conn-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()

    r = await client.post(
        f"/admin/tenants/{tenant_id}/agent-config/from-seed",
        headers=_ADMIN_HEADERS,
        json={
            "seed_template_ref": "barbershop_v1",
            "placeholders": _PLACEHOLDERS,
        },
    )
    assert r.status_code == 201, r.text
    config = r.json()
    # Seed's required tools all present.
    assert "booking.create_appointment" in config["tools"]
    # No connector contribution.
    assert not any(t.startswith("seedmerge.") for t in config["tools"])
