"""End-to-end consent flow: initiate → webhook → sync → tools land in catalog.

This is the highest-value integration test of the block. If this is green
the entire Phase 1 autonomous-consent contract works."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
from sqlalchemy import select, update

from nexus_api.db.models import Tenant, TenantConnector, ToolCatalog

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _composio_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin a deterministic webhook secret for HMAC build in this file.

    The auth_config_id is resolved via the fake adapter (no settings).
    """
    from nexus_api.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "composio_webhook_secret", "test_whsec_001")


def _signed_webhook(secret: str, body: dict) -> tuple[dict, str]:
    payload = json.dumps(body, separators=(",", ":"))
    wid = f"msg_{uuid.uuid4().hex[:8]}"
    ts = str(int(time.time()))
    sig = base64.b64encode(
        hmac.new(secret.encode(), f"{wid}.{ts}.{payload}".encode(), hashlib.sha256).digest()
    ).decode()
    headers = {
        "webhook-id": wid,
        "webhook-timestamp": ts,
        "webhook-signature": f"v1,{sig}",
        "Content-Type": "application/json",
    }
    return headers, payload


async def test_full_consent_flow(
    client, admin_headers, db_session, seed_tenants, seeded_catalog, fake_composio
) -> None:
    tenant_a = seed_tenants["a"]
    await db_session.execute(
        update(Tenant).where(Tenant.id == tenant_a).values(owner_phone="+56911")
    )
    # Resolve tenant slug so we can build the expected user_id.
    tenant_row = await db_session.scalar(select(Tenant).where(Tenant.id == tenant_a))
    assert tenant_row is not None
    expected_user_id = f"tenant_{tenant_row.slug}"
    await db_session.commit()

    # Step 1: operator initiates consent.
    r1 = await client.post(
        f"/admin/tenants/{tenant_a}/connectors/google_calendar/initiate-consent",
        headers=admin_headers,
    )
    assert r1.status_code == 201, r1.text
    tc_row = await db_session.scalar(
        select(TenantConnector).where(TenantConnector.tenant_id == tenant_a)
    )
    assert tc_row is not None
    composio_conn_id = tc_row.credentials_ref["composio_connection_id"]
    assert tc_row.credentials_ref["user_id"] == expected_user_id

    # Step 2: simulate Composio finishing the OAuth dance (fake-internal state).
    fake_composio.force_connect(
        connection_id=composio_conn_id,
        user_id=expected_user_id,
        toolkit="googlecalendar",
        scopes=["calendar.readonly", "calendar.events.write"],
    )

    # Step 3: Composio webhook fires with status=ACTIVE.
    webhook_body = {
        "type": "connected_account.active",
        "data": {
            "connection_id": composio_conn_id,
            "status": "ACTIVE",
            "granted_scopes": ["calendar.readonly", "calendar.events.write"],
        },
    }
    headers, payload = _signed_webhook("test_whsec_001", webhook_body)
    r2 = await client.post("/connectors/composio-webhook", headers=headers, content=payload)
    assert r2.status_code == 200, r2.text
    assert r2.json()["upstream_status"] == "ACTIVE"

    # Step 4: verify state — connector status is connected, tools landed.
    db_session.expire_all()
    tc_row = await db_session.scalar(
        select(TenantConnector).where(TenantConnector.tenant_id == tenant_a)
    )
    assert tc_row.status == "connected"
    assert "calendar.readonly" in tc_row.scopes_granted
    assert tc_row.connected_at is not None
    assert tc_row.consent_token is None  # consumed

    tools = (
        await db_session.scalars(
            select(ToolCatalog).where(ToolCatalog.name.like("GOOGLECALENDAR_%"))
        )
    ).all()
    slugs = {t.name for t in tools}
    assert "GOOGLECALENDAR_LIST_EVENTS" in slugs
    assert "GOOGLECALENDAR_CREATE_EVENT" in slugs

    # Annotation derivation correctness:
    by_name = {t.name: t for t in tools}
    assert by_name["GOOGLECALENDAR_LIST_EVENTS"].read_only is True
    assert by_name["GOOGLECALENDAR_LIST_EVENTS"].default_mode == "always"
    # google_calendar has auto_enable_destructive=False → CREATE is blocked.
    assert by_name["GOOGLECALENDAR_CREATE_EVENT"].destructive is True
    assert by_name["GOOGLECALENDAR_CREATE_EVENT"].default_mode == "blocked"


async def test_webhook_bad_signature_rejected(
    client, db_session, seed_tenants, seeded_catalog, fake_composio
) -> None:
    body = {
        "type": "connected_account.active",
        "data": {"connection_id": "conn_x", "status": "ACTIVE"},
    }
    headers, payload = _signed_webhook("wrong_secret", body)
    r = await client.post("/connectors/composio-webhook", headers=headers, content=payload)
    assert r.status_code == 401


async def test_webhook_unknown_connection_id_does_not_500(
    client, seeded_catalog, fake_composio
) -> None:
    """A webhook for a connection_id we don't track returns 200 ignored —
    NOT a 5xx that would trigger Composio to retry forever."""
    body = {
        "type": "connected_account.active",
        "data": {"connection_id": "conn_unknown_xyz", "status": "ACTIVE"},
    }
    headers, payload = _signed_webhook("test_whsec_001", body)
    r = await client.post("/connectors/composio-webhook", headers=headers, content=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_oauth_callback_renders_success(client, seeded_catalog) -> None:
    """The OAuth callback is a UX page — even with no token it renders 200."""
    r = await client.get("/connectors/oauth-callback")
    assert r.status_code == 200
    assert "Auphere" in r.text


async def test_oauth_callback_with_bad_token_still_200(client, seeded_catalog) -> None:
    r = await client.get("/connectors/oauth-callback?consent_token=tampered.token")
    assert r.status_code == 200
