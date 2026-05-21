"""Tests for the Meta Embedded Signup admin endpoint.

The endpoint orchestrates the post-signup flow: code → BISUAT exchange,
phone registration, webhook subscription, credentials persistence,
channel upsert. We stub the Graph API at the HTTP layer via respx so the
test exercises the real orchestrator + DB writes.

Test matrix:

- Happy path: 201 + channels row + tenant_credentials row + audit log.
- Bad OAuth code: 400 with operator-friendly detail.
- subscribed_apps fails: 400; orchestrator surfaces the error.
- Auth missing: 401.
- Unknown tenant: 404.
"""

from __future__ import annotations

import uuid

import pytest
import respx
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL
from sqlalchemy import select

from nexus_api.db.models import AuditLog, Channel, ChannelType, TenantCredentials

pytestmark = pytest.mark.asyncio


def _ok_phone_response() -> dict:
    return {
        "display_phone_number": "56933334444",
        "verified_name": "Cultor Barber",
        "quality_rating": "GREEN",
        "messaging_limit_tier": "TIER_1K",
    }


def _signup_body() -> dict:
    return {
        "code": "OAUTH_CODE_XYZ",
        "waba_id": "WABA_TEST",
        "phone_number_id": "PN_TEST",
        "business_id": "BIZ_TEST",
        "mode": "cloud_api",
    }


def _mock_happy_path(mock: respx.MockRouter) -> None:
    """Set up the four Graph API endpoints the orchestrator hits."""
    mock.get("/oauth/access_token").respond(
        200, json={"access_token": "EAA-bisuat-test", "expires_in": 5_184_000}
    )
    mock.post("/PN_TEST/register").respond(200, json={"success": True})
    mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
    mock.get("/PN_TEST").respond(200, json=_ok_phone_response())


# ── happy path ─────────────────────────────────────────────────────────────


async def test_meta_signup_creates_channel_credentials_and_audit(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_happy_path(mock)
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/signup",
            json=_signup_body(),
            headers=admin_headers,
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["waba_id"] == "WABA_TEST"
    assert body["phone_number_id"] == "PN_TEST"
    assert body["display_phone_number"] == "+56933334444"
    assert body["mode"] == "cloud_api"
    assert body["bisuat_expires_at"] is not None

    # Channel row created with provider="meta"
    chan = await db_session.scalar(
        select(Channel).where(
            Channel.tenant_id == tenant_id,
            Channel.provider == "meta",
        )
    )
    assert chan is not None
    assert chan.type == ChannelType.WHATSAPP
    assert chan.provider_identifier == "+56933334444"
    assert chan.config["waba_id"] == "WABA_TEST"
    assert chan.config["phone_number_id"] == "PN_TEST"
    assert chan.config["mode"] == "cloud_api"

    # Credentials persisted (Fernet round-trip via the type decorator)
    cred = await db_session.scalar(
        select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == "meta_whatsapp",
        )
    )
    assert cred is not None
    assert cred.needs_reauth is False
    # encrypted_payload arrives back as plaintext bytes after the type decoder.
    assert b"EAA-bisuat-test" in cred.encrypted_payload
    assert b"WABA_TEST" in cred.encrypted_payload

    # Audit log entry
    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "channel.whatsapp.meta_signup",
        )
    )
    assert audit is not None
    assert audit.after_json["waba_id"] == "WABA_TEST"
    assert audit.after_json["channel_id"] == str(chan.id)


# ── failure paths ──────────────────────────────────────────────────────────


async def test_meta_signup_oauth_code_expired_returns_400(client, admin_headers, seed_tenants):
    tenant_id = seed_tenants["a"]
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.get("/oauth/access_token").respond(
            400,
            json={
                "error": {
                    "message": "This authorization code has been used.",
                    "type": "OAuthException",
                    "code": 100,
                }
            },
        )
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/signup",
            json=_signup_body(),
            headers=admin_headers,
        )
    assert r.status_code == 400
    assert "OAuth code" in r.json()["detail"]


async def test_meta_signup_subscribe_failure_returns_400(client, admin_headers, seed_tenants):
    tenant_id = seed_tenants["a"]
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.get("/oauth/access_token").respond(
            200, json={"access_token": "EAA-x", "expires_in": 60}
        )
        mock.post("/PN_TEST/register").respond(200, json={"success": True})
        # subscribed_apps fails -> SubscribeWebhookError -> 400
        mock.post("/WABA_TEST/subscribed_apps").respond(
            400, json={"error": {"message": "WABA not eligible", "code": 100}}
        )
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/signup",
            json=_signup_body(),
            headers=admin_headers,
        )
    assert r.status_code == 400
    assert "subscribed_apps" in r.json()["detail"]


# ── auth + 404 ─────────────────────────────────────────────────────────────


async def test_meta_signup_requires_admin_token(client, seed_tenants):
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/meta/signup",
        json=_signup_body(),
    )
    assert r.status_code == 401


async def test_meta_signup_unknown_tenant_returns_404(client, admin_headers):
    r = await client.post(
        f"/admin/tenants/{uuid.uuid4()}/integrations/meta/signup",
        json=_signup_body(),
        headers=admin_headers,
    )
    assert r.status_code == 404
