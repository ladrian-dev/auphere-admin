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


# ── verify_token contract ──────────────────────────────────────────────────


async def test_meta_signup_subscribed_apps_uses_global_verify_token(
    client, admin_headers, seed_tenants
):
    """``subscribed_apps`` MUST send the verify_token configured in
    settings.meta_webhook_verify_token, NOT a per-tenant random value.

    Otherwise Meta's GET handshake hits our /webhook/meta with a token
    the handshake handler doesn't recognise, returns 403, and
    subscribed_apps fails with "(#2200) Callback verification failed".
    """
    tenant_id = seed_tenants["a"]
    captured: dict[str, object] = {}

    def capture_body(request):
        captured["body"] = request.read()
        return respx.MockResponse(200, json={"success": True})

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.get("/oauth/access_token").respond(
            200, json={"access_token": "EAA-x", "expires_in": 60}
        )
        mock.post("/PN_TEST/register").respond(200, json={"success": True})
        mock.post("/WABA_TEST/subscribed_apps").mock(side_effect=capture_body)
        mock.get("/PN_TEST").respond(200, json=_ok_phone_response())
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/signup",
            json=_signup_body(),
            headers=admin_headers,
        )
    assert r.status_code == 201, r.text
    # The test settings fixture sets meta_webhook_verify_token; whatever
    # the value is, the subscribed_apps POST must echo it back in the
    # body, NOT a freshly-generated random hex string.
    from nexus_api.config import get_settings

    expected = get_settings().meta_webhook_verify_token
    body_bytes = captured["body"]
    assert isinstance(body_bytes, (bytes, bytearray))
    assert expected.encode("utf-8") in bytes(body_bytes), (
        f"expected verify_token {expected!r} in subscribed_apps body but got "
        f"{body_bytes!r}"
    )


# ── Coexistence happy path ─────────────────────────────────────────────────


def _coex_body() -> dict:
    """Coexistence FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING payload — the
    backend gets only ``waba_id`` and must derive the rest."""
    return {
        "code": "OAUTH_CODE_COEX",
        "waba_id": "WABA_COEX",
        "mode": "coexistence",
    }


def _mock_coex_happy_path(mock: respx.MockRouter) -> None:
    """Orchestrator under Coexistence skips ``/register`` and instead
    discovers the phone via ``GET /{waba_id}/phone_numbers``."""
    mock.get("/oauth/access_token").respond(
        200, json={"access_token": "EAA-coex-bisuat", "expires_in": 5_184_000}
    )
    mock.get("/WABA_COEX/phone_numbers").respond(
        200,
        json={
            "data": [
                {
                    "id": "PN_COEX",
                    "display_phone_number": "56999998888",
                    "verified_name": "Coex Test",
                }
            ]
        },
    )
    mock.post("/WABA_COEX/subscribed_apps").respond(200, json={"success": True})
    mock.get("/PN_COEX").respond(
        200,
        json={
            "display_phone_number": "56999998888",
            "verified_name": "Coex Test",
            "quality_rating": "GREEN",
            "messaging_limit_tier": "TIER_1K",
        },
    )


async def test_meta_signup_coexistence_skips_register_and_derives_phone(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    # ``assert_all_called=False`` so the canary /register route below
    # doesn't fail the fixture — the whole point is to assert it was
    # NOT touched, which is verified explicitly via ``register_route.called``.
    async with respx.mock(
        base_url=META_GRAPH_BASE_URL, assert_all_called=False
    ) as mock:
        _mock_coex_happy_path(mock)
        register_route = mock.post("/PN_COEX/register").respond(
            500, json={"error": {"message": "should_not_be_called"}}
        )
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/signup",
            json=_coex_body(),
            headers=admin_headers,
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mode"] == "coexistence"
    assert body["waba_id"] == "WABA_COEX"
    assert body["phone_number_id"] == "PN_COEX"
    assert body["display_phone_number"] == "+56999998888"
    # /register must NOT have been called for Coexistence
    assert register_route.called is False

    chan = await db_session.scalar(
        select(Channel).where(
            Channel.tenant_id == tenant_id,
            Channel.provider == "meta",
        )
    )
    assert chan is not None
    assert chan.config["mode"] == "coexistence"
    assert chan.config["waba_id"] == "WABA_COEX"
    assert chan.config["phone_number_id"] == "PN_COEX"


async def test_meta_signup_coexistence_empty_phone_list_returns_400(
    client, admin_headers, seed_tenants
):
    """If Meta returns no phones for the WABA mid-onboarding (rare race),
    the orchestrator surfaces a 400 instead of writing a half-formed
    channel row."""
    tenant_id = seed_tenants["a"]
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.get("/oauth/access_token").respond(
            200, json={"access_token": "EAA-x", "expires_in": 60}
        )
        mock.get("/WABA_COEX/phone_numbers").respond(200, json={"data": []})
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/signup",
            json=_coex_body(),
            headers=admin_headers,
        )
    assert r.status_code == 400


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
