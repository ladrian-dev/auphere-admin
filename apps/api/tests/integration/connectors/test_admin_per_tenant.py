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
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlecalendar/initiate-consent",
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


async def test_initiate_consent_without_owner_phone_still_succeeds(
    client, admin_headers, seed_tenants, seeded_catalog, fake_composio
) -> None:
    """The panel can ship the consent URL by email/copy-paste, so the
    endpoint no longer requires owner_phone. WhatsApp dispatch via the
    template is best-effort and not enforced here."""
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlecalendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["signed_consent_url"].startswith("http")
    assert body["tenant_connector_id"]


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


async def test_initiate_consent_slug_not_in_catalog(
    client,
    admin_headers,
    db_session,
    seed_tenants,
    seeded_catalog,
    fake_composio,
) -> None:
    """If the slug isn't registered in Composio (and isn't a custom seed),
    the lazy upsert can't materialize the connector → 404.

    Simulates the operator giving a slug that doesn't exist anywhere.
    """
    await _set_owner_phone(db_session, seed_tenants["a"])
    # Remove the pre-registered auth_config for googlecalendar so neither
    # the catalog ensure-persisted lookup nor find_auth_config_id can
    # resolve the slug.
    fake_composio._auth_configs_by_toolkit.pop("googlecalendar", None)
    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlecalendar/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert "not registered" in r.json()["detail"].lower()


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
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlecalendar/initiate-consent",
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
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlecalendar/initiate-consent",
        headers=admin_headers,
    )
    assert r1.status_code == 201
    # disconnect
    r2 = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlecalendar/disconnect",
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


async def test_initiate_consent_lazy_upserts_composio_connector(
    client, admin_headers, db_session, seed_tenants, seeded_catalog, fake_composio
) -> None:
    """A toolkit added in Composio post-deploy doesn't need a seed.

    Simulates the operator going to the Composio dashboard, adding
    ``googlesheets`` as a new auth_config, and then connecting it from
    the panel — the connector row is materialized on the fly by the
    lazy upsert in initiate-consent.
    """
    from sqlalchemy import select

    from nexus_api.db.models import Connector

    fake_composio.register_auth_config(
        "googlesheets",
        "ac_gs_dynamic",
        display_name="Google Sheets",
        vendor="Google",
        category="Productivity",
    )
    fake_composio.register_tools("googlesheets", [])

    # Sanity: no row in DB yet.
    pre = await db_session.scalar(select(Connector).where(Connector.slug == "googlesheets"))
    assert pre is None

    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/connectors/googlesheets/initiate-consent",
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text

    # The connector row got materialized with the metadata from Composio.
    post = await db_session.scalar(select(Connector).where(Connector.slug == "googlesheets"))
    assert post is not None
    assert post.display_name == "Google Sheets"
    assert post.auth_kind == "oauth_composio"
    assert post.mcp_server_ref == "composio:googlesheets"
    assert post.category == "docs"  # Productivity → docs in _CATEGORY_MAP
    assert post.consent_link_template_name == "connector_consent_request_v1"


# ── Block M.5 — pause / resume ─────────────────────────────────────────────


async def _seed_installed_connector(db_session, tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    """Insert a ``connected`` install row directly so the pause/resume
    tests don't have to drive the full consent webhook flow. Returns the
    connector row id."""
    from nexus_api.db.models import Connector

    conn = await db_session.scalar(select(Connector).where(Connector.slug == slug))
    if conn is None:
        # Pre-create the connector row (mirrors what initiate-consent does
        # for Composio toolkits via lazy upsert).
        conn = Connector(
            slug=slug,
            display_name=slug,
            vendor="test",
            category="other",
            capabilities=[],
            auth_kind="oauth_composio",
            mcp_server_ref=f"composio:{slug}",
            provider_meta={},
            consent_link_template_name="connector_consent_request_v1",
            status="available",
        )
        db_session.add(conn)
        await db_session.commit()
        await db_session.refresh(conn)
    db_session.add(
        TenantConnector(
            tenant_id=tenant_id,
            connector_id=conn.id,
            status="connected",
            credentials_ref={"composio_connection_id": "test-cn"},
            scopes_granted=[],
            config={},
        )
    )
    await db_session.commit()
    return conn.id


async def test_pause_connector_happy(
    client, admin_headers, db_session, seed_tenants, seeded_catalog
) -> None:
    tid = seed_tenants["a"]
    await _seed_installed_connector(db_session, tid, "googlecalendar")
    r = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/pause",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paused"
    # Token + credentials persist (operator can resume without re-consent).
    tc = (
        await db_session.execute(select(TenantConnector).where(TenantConnector.tenant_id == tid))
    ).scalar_one()
    assert tc.credentials_ref == {"composio_connection_id": "test-cn"}


async def test_resume_connector_happy(
    client, admin_headers, db_session, seed_tenants, seeded_catalog
) -> None:
    tid = seed_tenants["a"]
    await _seed_installed_connector(db_session, tid, "googlecalendar")
    pause = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/pause",
        headers=admin_headers,
    )
    assert pause.status_code == 200
    resume = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/resume",
        headers=admin_headers,
    )
    assert resume.status_code == 200, resume.text
    assert resume.json()["status"] == "connected"


async def test_pause_rejects_pending_install(
    client, admin_headers, db_session, seed_tenants, seeded_catalog, fake_composio
) -> None:
    """Pause only makes sense from connected-ish states; a freshly
    initiated install is ``pending`` and should be rejected (the operator
    needs to either complete consent or disconnect)."""
    tid = seed_tenants["a"]
    await _set_owner_phone(db_session, tid)
    initiate = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/initiate-consent",
        headers=admin_headers,
    )
    assert initiate.status_code == 201
    r = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/pause",
        headers=admin_headers,
    )
    assert r.status_code == 409, r.text


async def test_pause_unknown_install_404(
    client, admin_headers, seed_tenants, seeded_catalog
) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/pause",
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_resume_only_from_paused(
    client, admin_headers, db_session, seed_tenants, seeded_catalog
) -> None:
    """Resume requires status='paused'. A connected install can't be
    resumed — it's already running."""
    tid = seed_tenants["a"]
    await _seed_installed_connector(db_session, tid, "googlecalendar")
    r = await client.post(
        f"/admin/tenants/{tid}/connectors/googlecalendar/resume",
        headers=admin_headers,
    )
    assert r.status_code == 409, r.text
