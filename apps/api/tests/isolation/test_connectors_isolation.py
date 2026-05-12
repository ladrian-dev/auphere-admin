"""Isolation tests for the Connectors module (Bloque L).

These run two tenants in parallel-ish and verify that every connector
operation in tenant A is invisible to / un-influenced by tenant B.

If any of these go red the module is unfit to ship — autonomous agents
without a panel cannot afford a leak.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text, update

from nexus_api.db.models import (
    Tenant,
    TenantConnector,
    TenantConnectorToolOverride,
    ToolCatalog,
)
from nexus_api.services.connectors.composio_client import (
    ComposioTool,
    FakeComposioClient,
)
from nexus_api.services.connectors.seed_loader import load_all_seeds
from nexus_api.services.connectors.seed_runner import apply_seeds

pytestmark = pytest.mark.asyncio


# ── shared setup ────────────────────────────────────────────────────────────


@pytest.fixture
async def two_tenants_with_catalog(db_session, seed_tenants):
    seeds = load_all_seeds()
    await apply_seeds(db_session, seeds)
    await db_session.execute(
        update(Tenant)
        .values(owner_phone="+56911")
        .where(Tenant.id.in_(list(seed_tenants.values())))
    )
    await db_session.commit()
    return seed_tenants


@pytest.fixture
def composio_with_two_tenants() -> FakeComposioClient:
    from nexus_api.api.admin import connectors as admin_connectors

    c = FakeComposioClient()
    c.register_tools(
        "googlecalendar",
        [
            ComposioTool(
                slug="GOOGLECALENDAR_LIST_EVENTS",
                description="List",
                input_schema={"type": "object"},
            ),
        ],
    )
    c.register_auth_config("googlecalendar", "ac_test_iso")
    admin_connectors.set_composio_client_for_tests(c)
    yield c
    admin_connectors.set_composio_client_for_tests(None)


def _admin(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── tests ───────────────────────────────────────────────────────────────────


async def test_list_tenant_connectors_does_not_leak(
    client, admin_headers, db_session, two_tenants_with_catalog, composio_with_two_tenants
) -> None:
    """Tenant A connects googlecalendar; tenant B's list returns empty."""
    # Tenant A initiates consent.
    r = await client.post(
        f"/admin/tenants/{two_tenants_with_catalog['a']}/connectors/"
        f"googlecalendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 201

    # Tenant A sees 1 install, tenant B sees 0.
    r_a = await client.get(
        f"/admin/tenants/{two_tenants_with_catalog['a']}/connectors",
        headers=admin_headers,
    )
    r_b = await client.get(
        f"/admin/tenants/{two_tenants_with_catalog['b']}/connectors",
        headers=admin_headers,
    )
    assert r_a.status_code == 200 and r_b.status_code == 200
    assert len(r_a.json()) == 1
    assert r_b.json() == []


async def test_composio_user_id_is_tenant_scoped(
    client, admin_headers, db_session, two_tenants_with_catalog, composio_with_two_tenants
) -> None:
    """Each tenant's initiate_consent sends its own user_id to Composio.
    Tenant A and tenant B end up with different user_id strings on the
    fake client; a tools.execute with mismatched user_id raises."""

    for key in ("a", "b"):
        r = await client.post(
            f"/admin/tenants/{two_tenants_with_catalog[key]}/connectors/"
            f"googlecalendar/initiate-consent",
            headers=admin_headers,
        )
        assert r.status_code == 201, r.text

    # Read each tenant_connectors row and check user_id.
    rows = (await db_session.execute(select(TenantConnector))).scalars().all()
    user_ids = {r.tenant_id: r.credentials_ref["user_id"] for r in rows}
    a_uid = user_ids[two_tenants_with_catalog["a"]]
    b_uid = user_ids[two_tenants_with_catalog["b"]]
    assert a_uid != b_uid
    assert a_uid.startswith("tenant_")
    assert b_uid.startswith("tenant_")


async def test_overrides_are_tenant_scoped(
    client, admin_headers, db_session, two_tenants_with_catalog
) -> None:
    """An override set for tenant A's tool must not affect tenant B."""
    db_session.add(
        ToolCatalog(
            name="SHARED_TOOL_FOR_ISOLATION",
            description="d",
            mcp_server="composio:x",
            input_schema={},
            output_schema={},
            side_effects=[],
            capability_tags=[],
            cost_estimate={},
            read_only=True,
            destructive=False,
            default_mode="always",
        )
    )
    await db_session.commit()

    # PUT override for tenant A.
    r_a = await client.put(
        f"/admin/tenants/{two_tenants_with_catalog['a']}/connector-tool-overrides/SHARED_TOOL_FOR_ISOLATION",
        headers=admin_headers,
        json={"mode": "blocked", "reason": "tenant A only"},
    )
    assert r_a.status_code == 200

    # Tenant B sees no override.
    r_b = await client.get(
        f"/admin/tenants/{two_tenants_with_catalog['b']}/connector-tool-overrides",
        headers=admin_headers,
    )
    assert r_b.status_code == 200
    assert r_b.json() == []

    # And direct DB scan via RLS-scoped session for tenant B is also empty.
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(two_tenants_with_catalog["b"])},
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    rows = (await db_session.scalars(select(TenantConnectorToolOverride))).all()
    assert rows == []


async def test_tenant_connector_rls_blocks_cross_tenant_select(
    db_session, two_tenants_with_catalog
) -> None:
    """Raw SQL check: with set_config(tenant_id=A), selecting tenant_connectors
    must not return tenant B's rows. (Defense-in-depth on top of the API.)

    Uses ``agendapro`` because it's a custom seed (already in DB after
    ``apply_seeds``). OAuth toolkits like ``googlecalendar`` only land in
    the ``connectors`` table after a lazy upsert at initiate-consent time;
    this test exercises RLS directly without going through the endpoint.
    """
    # Insert one row for each tenant directly with row_security off.
    from nexus_api.db.models import Connector

    conn = await db_session.scalar(select(Connector).where(Connector.slug == "agendapro"))
    assert conn is not None

    await db_session.execute(text("SET LOCAL row_security = off"))
    db_session.add_all(
        [
            TenantConnector(
                tenant_id=two_tenants_with_catalog["a"],
                connector_id=conn.id,
                status="connected",
                credentials_ref={"x": 1},
                scopes_granted=[],
                config={},
            ),
            TenantConnector(
                tenant_id=two_tenants_with_catalog["b"],
                connector_id=conn.id,
                status="connected",
                credentials_ref={"x": 2},
                scopes_granted=[],
                config={},
            ),
        ]
    )
    await db_session.commit()

    # Now scope to tenant A and select — only A's row appears.
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(two_tenants_with_catalog["a"])},
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    rows = (await db_session.scalars(select(TenantConnector))).all()
    assert len(rows) == 1
    assert rows[0].tenant_id == two_tenants_with_catalog["a"]


async def test_disconnect_one_tenant_does_not_affect_other(
    client, admin_headers, db_session, two_tenants_with_catalog, composio_with_two_tenants
) -> None:
    # Both connect.
    for key in ("a", "b"):
        await client.post(
            f"/admin/tenants/{two_tenants_with_catalog[key]}/connectors/"
            f"googlecalendar/initiate-consent",
            headers=admin_headers,
        )

    # Tenant A disconnects.
    r_a = await client.post(
        f"/admin/tenants/{two_tenants_with_catalog['a']}/connectors/googlecalendar/disconnect",
        headers=admin_headers,
    )
    assert r_a.status_code == 200

    # Tenant B still has its install in pending/connected (depending on race —
    # we didn't fire the webhook in this test; whatever the status is, it
    # must not be 'disconnected').
    r_b_list = await client.get(
        f"/admin/tenants/{two_tenants_with_catalog['b']}/connectors",
        headers=admin_headers,
    )
    items = r_b_list.json()
    assert len(items) == 1
    assert items[0]["status"] != "disconnected"
