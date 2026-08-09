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

import json
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


# ── connect owned number (System User token) ─────────────────────────────────


async def test_meta_connect_owned_creates_channel_with_catalog(
    client, admin_headers, seed_tenants, db_session
):
    """Owned-number path: no OAuth exchange; a provided System User token is
    persisted as the credential and ``catalog_id`` lands on the channel."""
    tenant_id = seed_tenants["a"]
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        # No /oauth/access_token here — the token is supplied directly.
        mock.post("/PN_TEST/register").respond(200, json={"success": True})
        mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
        mock.get("/PN_TEST").respond(200, json=_ok_phone_response())
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/connect-owned",
            json={
                "system_user_token": "EAA-system-user-permanent-token-xyz",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_TEST",
                "catalog_id": "CATALOG_123",
            },
            headers=admin_headers,
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["display_phone_number"] == "+56933334444"
    assert body["bisuat_expires_at"] is None  # permanent token
    assert body["catalog_id"] == "CATALOG_123"

    chan = await db_session.scalar(
        select(Channel).where(Channel.tenant_id == tenant_id, Channel.provider == "meta")
    )
    assert chan is not None
    assert chan.config["catalog_id"] == "CATALOG_123"
    assert chan.config["waba_id"] == "WABA_TEST"

    cred = await db_session.scalar(
        select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == "meta_whatsapp",
        )
    )
    assert cred is not None
    assert b"EAA-system-user-permanent-token-xyz" in cred.encrypted_payload

    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "channel.whatsapp.meta_connect_owned",
        )
    )
    assert audit is not None
    assert audit.after_json["catalog_id"] == "CATALOG_123"


async def test_meta_connect_owned_survives_register_failure(client, admin_headers, seed_tenants):
    """register_phone is best-effort — an already-registered live number
    (Meta 400 on re-register) must NOT block the connect; subscribe is what
    matters."""
    tenant_id = seed_tenants["a"]
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_TEST/register").respond(
            400, json={"error": {"message": "already registered"}}
        )
        mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
        mock.get("/PN_TEST").respond(200, json=_ok_phone_response())
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/connect-owned",
            json={
                "system_user_token": "EAA-token-abcdefghij",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_TEST",
            },
            headers=admin_headers,
        )
    assert r.status_code == 201, r.text


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
        f"expected verify_token {expected!r} in subscribed_apps body but got {body_bytes!r}"
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
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
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


# ── test-send ──────────────────────────────────────────────────────────────


async def _seed_meta_credentials(db_session, tenant_id) -> None:
    """Helper to put a tenant_credentials row in place so test-send has a
    BISUAT to read."""
    from nexus_channels.whatsapp_meta.credentials import MetaCredentials
    from sqlalchemy import text as sql_text

    from nexus_api.db.models import TenantCredentials

    creds = MetaCredentials(
        bisuat="EAA-fake-bisuat",
        waba_id="WABA_TEST",
        phone_number_id="PN_TEST",
        business_id="BIZ_TEST",
        display_phone_number="+56933334444",
        verify_token="dev-meta-verify-token-change-me",
        mode="cloud_api",
    )
    async with db_session.begin():
        await db_session.execute(
            sql_text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(sql_text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            TenantCredentials(
                tenant_id=tenant_id,
                integration="meta_whatsapp",
                encrypted_payload=creds.to_payload(),
                needs_reauth=False,
            )
        )


async def test_meta_test_send_template_returns_wamid(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    await _seed_meta_credentials(db_session, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        sent = mock.post("/PN_TEST/messages").respond(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "+56911112222", "wa_id": "56911112222"}],
                "messages": [{"id": "wamid.HBg-TEST-1", "message_status": "accepted"}],
            },
        )
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/test-send",
            json={"to": "+56911112222"},  # defaults: kind=template, hello_world, en_US
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wamid"] == "wamid.HBg-TEST-1"
    assert body["kind"] == "template"
    # Verify the body Meta received carried the template, not text.
    assert sent.called
    payload = json.loads(sent.calls.last.request.content)
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "hello_world"
    assert payload["template"]["language"]["code"] == "en_US"
    assert payload["to"] == "+56911112222"


async def test_meta_test_send_text_requires_text_body(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    await _seed_meta_credentials(db_session, tenant_id)
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/meta/test-send",
        json={"to": "+56911112222", "kind": "text"},
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "text_body" in r.json()["detail"]


async def test_meta_test_send_text_sends_payload(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    await _seed_meta_credentials(db_session, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        sent = mock.post("/PN_TEST/messages").respond(
            200,
            json={
                "messages": [{"id": "wamid.HBg-TEXT", "message_status": "accepted"}],
            },
        )
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/test-send",
            json={"to": "+56911112222", "kind": "text", "text_body": "Hola mundo"},
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    assert r.json()["wamid"] == "wamid.HBg-TEXT"
    payload = json.loads(sent.calls.last.request.content)
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "Hola mundo"


async def test_meta_test_send_returns_404_when_no_credentials(client, admin_headers, seed_tenants):
    """No Embedded Signup completed yet → no credentials row → 404."""
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/meta/test-send",
        json={"to": "+56911112222"},
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_meta_test_send_surfaces_meta_400(client, admin_headers, seed_tenants, db_session):
    """If Meta rejects the send (eg recipient outside service window for
    a text), the endpoint returns 400 with Meta's message."""
    tenant_id = seed_tenants["a"]
    await _seed_meta_credentials(db_session, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_TEST/messages").respond(
            400,
            json={
                "error": {
                    "message": "Re-engagement message",
                    "code": 131047,
                    "type": "OAuthException",
                }
            },
        )
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/test-send",
            json={"to": "+56911112222", "kind": "text", "text_body": "ping"},
            headers=admin_headers,
        )
    assert r.status_code == 400
    assert "Re-engagement" in r.json()["detail"]


async def test_meta_test_send_requires_admin_token(client, seed_tenants):
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/meta/test-send",
        json={"to": "+56911112222"},
    )
    assert r.status_code == 401


# ── connecting a SECOND number ─────────────────────────────────────────────
#
# ``tenant_credentials`` holds one Meta credential per tenant, including a
# single ``phone_number_id``. Connecting a second number used to overwrite it,
# which silently re-pointed every outbound of the tenant — the agent's replies
# on the first line included — at the number just connected. Nothing errored;
# the wrong number simply started writing to people.


async def _connect_owned(client, admin_headers, tenant_id, *, pnid: str, display: str):
    with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post(f"/{pnid}/register").respond(200, json={"success": True})
        mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
        mock.get(f"/{pnid}").respond(
            200, json={**_ok_phone_response(), "display_phone_number": display}
        )
        return await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/connect-owned",
            json={
                "system_user_token": f"EAA-system-user-permanent-token-for-{pnid}",
                "waba_id": "WABA_TEST",
                "phone_number_id": pnid,
            },
            headers=admin_headers,
        )


async def test_connecting_a_second_number_does_not_repoint_the_first(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]

    first = await _connect_owned(
        client, admin_headers, tenant_id, pnid="PN_FIRST", display="56933334444"
    )
    assert first.status_code == 201, first.text
    second = await _connect_owned(
        client, admin_headers, tenant_id, pnid="PN_SECOND", display="56955556666"
    )
    assert second.status_code == 201, second.text

    # Two channel rows, each carrying its own phone_number_id.
    channels = (
        (
            await db_session.execute(
                select(Channel).where(Channel.tenant_id == tenant_id, Channel.provider == "meta")
            )
        )
        .scalars()
        .all()
    )
    by_pnid = {c.config["phone_number_id"]: c for c in channels}
    assert set(by_pnid) == {"PN_FIRST", "PN_SECOND"}

    # THE regression: the tenant-level credential still points at the first
    # number. Had it been overwritten, the first line's sends would now leave
    # from the second number.
    cred = await db_session.scalar(
        select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == "meta_whatsapp",
        )
    )
    assert cred is not None
    assert b"PN_FIRST" in cred.encrypted_payload
    assert b"PN_SECOND" not in cred.encrypted_payload

    # And each channel carries its own token, so neither depends on the
    # tenant row being right.
    assert b"EAA-system-user-permanent-token-for-PN_FIRST" in by_pnid["PN_FIRST"].config_encrypted
    assert b"EAA-system-user-permanent-token-for-PN_SECOND" in by_pnid["PN_SECOND"].config_encrypted


async def test_reconnecting_the_same_number_still_refreshes_the_tenant_credential(
    client, admin_headers, seed_tenants, db_session
):
    """Token rotation must keep working: re-connecting the SAME number is not
    a second number and has to refresh the tenant row as it always did."""
    tenant_id = seed_tenants["a"]

    await _connect_owned(client, admin_headers, tenant_id, pnid="PN_ONLY", display="56933334444")
    with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_ONLY/register").respond(200, json={"success": True})
        mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
        mock.get("/PN_ONLY").respond(200, json=_ok_phone_response())
        again = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/connect-owned",
            json={
                "system_user_token": "EAA-rotated-system-user-token-abcdef",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_ONLY",
            },
            headers=admin_headers,
        )
    assert again.status_code == 201, again.text

    cred = await db_session.scalar(
        select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == "meta_whatsapp",
        )
    )
    assert cred is not None
    assert b"EAA-rotated-system-user-token-abcdef" in cred.encrypted_payload
