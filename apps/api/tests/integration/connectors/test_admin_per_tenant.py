"""Per-tenant connector admin endpoints — install lifecycle.

Covers:
- list_tenant_connectors (empty + after install)
- initiate_consent happy path + 400 missing owner_phone + 503 missing auth_config
- disconnect + reissue_consent
- override CRUD
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from nexus_api.db.models import Tenant, TenantConnector

pytestmark = pytest.mark.asyncio


# The auth_config_id is now resolved at runtime via ``find_auth_config_id``
# against the Composio adapter. The ``fake_composio`` fixture pre-registers
# the auth_configs for googlecalendar/calendly/notion, so no settings
# patching is needed here.


async def _set_owner_phone(db_session, tenant_id: uuid.UUID, phone: str = "+56911112222") -> None:
    await db_session.execute(update(Tenant).where(Tenant.id == tenant_id).values(owner_phone=phone))
    await db_session.commit()


async def test_list_tenant_connectors_empty(
    client, admin_headers, seed_tenants, seeded_catalog
) -> None:
    r = await client.get(f"/admin/tenants/{seed_tenants['a']}/connectors", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


async def test_initiate_consent_happy(
    client, admin_headers, db_session, seed_tenants, seeded_catalog, fake_composio
) -> None:
    await _set_owner_phone(db_session, seed_tenants["a"])
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/google_calendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["redirect_url"].startswith("https://")
    assert "consent_token=" in body["signed_consent_url"]
    # tenant_connector row created in pending state
    rows = (
        (
            await db_session.execute(
                select(TenantConnector).where(TenantConnector.tenant_id == seed_tenants["a"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].credentials_ref["composio_connection_id"].startswith("conn_fake_")


async def test_initiate_consent_no_owner_phone(
    client, admin_headers, seed_tenants, seeded_catalog, fake_composio
) -> None:
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/google_calendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "owner_phone" in r.json()["detail"]


async def test_initiate_consent_unknown_slug(
    client, admin_headers, db_session, seed_tenants, seeded_catalog
) -> None:
    await _set_owner_phone(db_session, seed_tenants["a"])
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/no_such/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_initiate_consent_wrong_auth_kind(
    client, admin_headers, db_session, seed_tenants, seeded_catalog
) -> None:
    """Trying to initiate consent on a webhook_manual connector → 400."""
    await _set_owner_phone(db_session, seed_tenants["a"])
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/whatsapp_ycloud/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 400


async def test_initiate_consent_missing_auth_config(
    client,
    admin_headers,
    db_session,
    seed_tenants,
    seeded_catalog,
    fake_composio,
) -> None:
    """If no auth_config is registered in Composio for this toolkit → 503.

    Simulates the operator forgetting to create the auth_config in the
    Composio dashboard before initiating consent.
    """
    await _set_owner_phone(db_session, seed_tenants["a"])
    # Remove the pre-registered auth_config for googlecalendar so the lookup
    # raises ComposioAuthConfigMissing.
    fake_composio._auth_configs_by_toolkit.pop("googlecalendar", None)
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/google_calendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 503
    assert "no auth_config" in r.json()["detail"].lower()


async def test_initiate_consent_ambiguous_auth_config(
    client,
    admin_headers,
    db_session,
    seed_tenants,
    seeded_catalog,
    fake_composio,
) -> None:
    """If Composio has multiple auth_configs for the toolkit → 409.

    Phase 1 expects exactly one auth_config per toolkit per Composio project.
    """
    await _set_owner_phone(db_session, seed_tenants["a"])
    # Register a second auth_config for googlecalendar.
    fake_composio.register_auth_config("googlecalendar", "ac_duplicate")
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/google_calendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "auth_config" in r.json()["detail"].lower()


async def test_disconnect_happy(
    client, admin_headers, db_session, seed_tenants, seeded_catalog, fake_composio
) -> None:
    await _set_owner_phone(db_session, seed_tenants["a"])
    # initiate first
    r1 = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/google_calendar/initiate-consent",
        headers=admin_headers,
    )
    assert r1.status_code == 201
    # disconnect
    r2 = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/google_calendar/disconnect",
        headers=admin_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "disconnected"


async def test_override_crud(
    client, admin_headers, seed_tenants, seeded_catalog, db_session
) -> None:
    # Insert a tool_catalog row to point the override at. The seed catalog
    # doesn't add tools by itself — we manually add one for this test.
    from nexus_api.db.models import ToolCatalog

    db_session.add(
        ToolCatalog(
            name="TEST_TOOL_FOR_OVERRIDE",
            description="Used by test_override_crud only",
            mcp_server="composio:googlecalendar",
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

    # PUT override
    r1 = await client.put(
        f"/admin/tenants/{seed_tenants['a']}/connector-tool-overrides/TEST_TOOL_FOR_OVERRIDE",
        headers=admin_headers,
        json={"mode": "blocked", "reason": "soak period"},
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["mode"] == "blocked"
    assert body["reason"] == "soak period"

    # GET list
    r2 = await client.get(
        f"/admin/tenants/{seed_tenants['a']}/connector-tool-overrides",
        headers=admin_headers,
    )
    assert r2.status_code == 200
    items = r2.json()
    assert any(o["tool_name"] == "TEST_TOOL_FOR_OVERRIDE" for o in items)

    # PUT same again — update existing
    r3 = await client.put(
        f"/admin/tenants/{seed_tenants['a']}/connector-tool-overrides/TEST_TOOL_FOR_OVERRIDE",
        headers=admin_headers,
        json={"mode": "always", "reason": None},
    )
    assert r3.status_code == 200
    assert r3.json()["mode"] == "always"

    # DELETE
    r4 = await client.delete(
        f"/admin/tenants/{seed_tenants['a']}/connector-tool-overrides/TEST_TOOL_FOR_OVERRIDE",
        headers=admin_headers,
    )
    assert r4.status_code == 204

    # DELETE again → 404
    r5 = await client.delete(
        f"/admin/tenants/{seed_tenants['a']}/connector-tool-overrides/TEST_TOOL_FOR_OVERRIDE",
        headers=admin_headers,
    )
    assert r5.status_code == 404


async def test_override_unknown_tool_404(
    client, admin_headers, seed_tenants, seeded_catalog
) -> None:
    r = await client.put(
        f"/admin/tenants/{seed_tenants['a']}/connector-tool-overrides/NOT_A_TOOL",
        headers=admin_headers,
        json={"mode": "blocked", "reason": None},
    )
    assert r.status_code == 404
