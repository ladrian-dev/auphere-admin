"""Tests Block J — WhatsApp manual setup endpoints.

Phase 1 onboarding: owner crea la WABA en YCloud dashboard, copia
``waba_id`` + ``phone_number_id`` y los pega en el wizard. Backend valida
contra YCloud, crea la fila ``Channel``.

YCloud transport stubbed via a fake module-level factory; no network calls.

Note: imports of ``nexus_api.api.admin.integrations`` and the YCloud
exception types are deferred to function scope. Importing them at module
top-level loaded ``nexus_api.api.deps`` during pytest collection, which
disrupted the engine-cache lifecycle of subsequent webhook tests in the
same session (deterministic flake reproduced 2026-05-09 while wiring
this file). Function-scoped imports keep the side effects bound to the
test function and the autouse engine-reset fixture.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from nexus_api.db.models import AuditLog, Channel, ChannelStatus, ChannelType

if TYPE_CHECKING:
    from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError

pytestmark = pytest.mark.asyncio


class _FakeYCloudClient:
    """Mimics :class:`YCloudClient` for the two endpoints we exercise.

    ``responses`` is a (waba_id, phone_number_id_or_None) → either dict
    (success) or YCloudAPIError instance (raise on call). ``None`` as
    the second tuple element matches the WABA-listing fallback (when the
    operator omits ``phone_number_id`` and the backend lists the WABA).
    """

    def __init__(self, responses: dict[tuple[str, str | None], Any]) -> None:
        self._responses = responses
        self.closed = False
        self.calls: list[tuple[str, str | None]] = []

    async def get_phone_number(
        self, *, waba_id: str, phone_number_id: str | None = None
    ) -> dict[str, Any]:
        from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError

        key: tuple[str, str | None] = (waba_id, phone_number_id)
        self.calls.append(key)
        match = self._responses.get(key)
        if match is None:
            raise _ycloud_error(404, "phone number not found")
        if isinstance(match, YCloudAPIError):
            raise match
        return match

    async def close(self) -> None:
        self.closed = True


def _patch_ycloud(monkeypatch: pytest.MonkeyPatch, fake: _FakeYCloudClient) -> None:
    from nexus_api.api.admin import integrations as integrations_module

    monkeypatch.setattr(integrations_module, "_build_ycloud_client", lambda: fake)


def _ycloud_error(status_code: int, message: str) -> YCloudAPIError:
    from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError

    return YCloudAPIError(status_code, message)


# ── verify (dry-run) ───────────────────────────────────────────────────────


async def test_verify_returns_phone_summary(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient(
        {
            ("WABA1", "123412341234123"): {
                "phoneNumber": "+56911112222",
                "displayName": "Cultor Barber",
                "verifiedName": "Cultor Barber SpA",
                "qualityRating": "GREEN",
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        "/admin/integrations/whatsapp/verify?waba_id=WABA1&phone_number_id=123412341234123",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phone_number"] == "+56911112222"
    assert body["display_name"] == "Cultor Barber"
    assert body["quality_rating"] == "GREEN"
    assert fake.closed is True


async def test_verify_404_returns_400_with_friendly_message(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient({("WABA1", "123412341234123"): _ycloud_error(404, "Not Found")})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        "/admin/integrations/whatsapp/verify?waba_id=WABA1&phone_number_id=123412341234123",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "no encontró" in r.json()["detail"]


async def test_verify_401_returns_400_pointing_at_doppler(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient({("WABA1", "123412341234123"): _ycloud_error(401, "Unauthorized")})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        "/admin/integrations/whatsapp/verify?waba_id=WABA1&phone_number_id=123412341234123",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "NEXUS_YCLOUD_API_KEY" in r.json()["detail"]


async def test_verify_403_returns_400_pointing_at_tech_provider(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient({("WABA1", "123412341234123"): _ycloud_error(403, "Forbidden")})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        "/admin/integrations/whatsapp/verify?waba_id=WABA1&phone_number_id=123412341234123",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "Tech Provider" in r.json()["detail"]


async def test_verify_requires_auth(client, monkeypatch):
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get("/admin/integrations/whatsapp/verify?waba_id=WABA1&phone_number_id=123412341234123")
    assert r.status_code == 401


# ── connect-manual ─────────────────────────────────────────────────────────


async def test_connect_manual_creates_channel_and_audit(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    fake = _FakeYCloudClient(
        {
            ("WABA1", "123412341234123"): {
                "phoneNumber": "+56911112222",
                "displayName": "Cultor Barber",
                "verifiedName": "Cultor Barber SpA",
                "qualityRating": "GREEN",
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": "WABA1", "phone_number_id": "123412341234123"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["phone_number"] == "+56911112222"
    assert body["display_name"] == "Cultor Barber"

    # Channel row created with the right shape.
    channel = (
        await db_session.execute(
            select(Channel).where(
                Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
            )
        )
    ).scalar_one()
    assert channel.provider == "ycloud"
    assert channel.provider_identifier == "+56911112222"
    assert channel.status == ChannelStatus.ACTIVE
    assert channel.config["waba_id"] == "WABA1"
    assert channel.config["phone_number_id"] == "123412341234123"
    assert channel.config["display_name"] == "Cultor Barber"
    assert channel.config["verified_name"] == "Cultor Barber SpA"
    assert channel.config["quality_rating"] == "GREEN"

    # Audit row.
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == "channel.whatsapp.connect_manual",
            )
        )
    ).scalar_one()
    assert audit.before_json is None
    assert audit.after_json["phone_number"] == "+56911112222"


async def test_connect_manual_idempotent_reconnects_in_place(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    """Re-running connect-manual for the same tenant updates the existing
    Channel row (rather than tripping UNIQUE on a 2nd insert)."""
    fake = _FakeYCloudClient(
        {
            ("WABA1", "123412341234123"): {
                "phoneNumber": "+56911112222",
                "displayName": "Cultor Barber",
                "qualityRating": "GREEN",
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    url = f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual"
    body = {"waba_id": "WABA1", "phone_number_id": "123412341234123"}
    r1 = await client.post(url, headers=admin_headers, json=body)
    assert r1.status_code == 201
    r2 = await client.post(url, headers=admin_headers, json=body)
    assert r2.status_code == 201
    # Only one channel row.
    channels = (
        (
            await db_session.execute(
                select(Channel).where(
                    Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(channels) == 1


async def test_connect_manual_duplicate_e164_across_tenants_409(
    client, admin_headers, monkeypatch, seed_tenants
):
    """Tenant A connects +56911112222. Tenant B tries the same number → 409
    (the global UNIQUE on (type, provider_identifier) trips)."""
    fake = _FakeYCloudClient(
        {
            ("WABA1", "123412341234123"): {
                "phoneNumber": "+56911112222",
                "displayName": "Cultor Barber",
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    tenant_a = seed_tenants["a"]
    tenant_b = seed_tenants["b"]
    body = {"waba_id": "WABA1", "phone_number_id": "123412341234123"}
    r1 = await client.post(
        f"/admin/tenants/{tenant_a}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json=body,
    )
    assert r1.status_code == 201
    r2 = await client.post(
        f"/admin/tenants/{tenant_b}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json=body,
    )
    assert r2.status_code == 409
    assert "ya está conectado" in r2.json()["detail"]


async def test_connect_manual_ycloud_404_returns_400(
    client, admin_headers, monkeypatch, seed_tenants
):
    fake = _FakeYCloudClient({("WABA1", "123412341234123"): _ycloud_error(404, "Not Found")})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": "WABA1", "phone_number_id": "123412341234123"},
    )
    assert r.status_code == 400


async def test_connect_manual_unknown_tenant_404(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    r = await client.post(
        f"/admin/tenants/{uuid.uuid4()}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": "WABA1", "phone_number_id": "123412341234123"},
    )
    assert r.status_code == 404


# ── phone_number_id is optional + validated (Camino B regression suite) ────


async def test_verify_without_phone_number_id_uses_waba_listing(
    client, admin_headers, monkeypatch
):
    """When the operator omits ``phone_number_id``, the backend falls
    back to the WABA-listing endpoint of YCloud and resolves the single
    phone registered under the WABA. The wizard's primary path."""
    fake = _FakeYCloudClient(
        {
            ("WABA1", None): {
                "phoneNumber": "+34632719028",
                "displayName": None,
                "verifiedName": "Auphere",
                "qualityRating": "GREEN",
                "id": "987654321098765",
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        "/admin/integrations/whatsapp/verify?waba_id=WABA1",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phone_number"] == "+34632719028"
    assert body["verified_name"] == "Auphere"
    # YCloud's listing returned an ``id`` — that's the canonical one we surface.
    assert body["phone_number_id"] == "987654321098765"
    assert fake.calls == [("WABA1", None)]


async def test_verify_rejects_e164_in_phone_number_id_field(
    client, admin_headers, monkeypatch
):
    """Most common operator typo: pasting the phone number itself into
    the phone_number_id field. Caught client-side too, but the backend
    is the line of defense — must 400 before touching YCloud."""
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        "/admin/integrations/whatsapp/verify"
        "?waba_id=WABA1&phone_number_id=%2B34632719028",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "número de teléfono" in r.json()["detail"]
    # We never reached YCloud.
    assert fake.calls == []


async def test_connect_manual_without_phone_number_id_uses_waba_listing(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    fake = _FakeYCloudClient(
        {
            ("WABA1", None): {
                "phoneNumber": "+34632719028",
                "verifiedName": "Auphere",
                "qualityRating": "GREEN",
                "id": "987654321098765",
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": "WABA1"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phone_number"] == "+34632719028"
    # Persisted the canonical id returned by YCloud's listing, not "".
    assert body["phone_number_id"] == "987654321098765"
    channel = (
        await db_session.execute(
            select(Channel).where(
                Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
            )
        )
    ).scalar_one()
    assert channel.config["phone_number_id"] == "987654321098765"
    assert fake.calls == [("WABA1", None)]


async def test_connect_manual_rejects_e164_in_phone_number_id_field(
    client, admin_headers, monkeypatch, seed_tenants
):
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": "WABA1", "phone_number_id": "+34632719028"},
    )
    # Pydantic validators bubble up as 422 by default — but our normalizer
    # raises HTTPException(400) explicitly to keep the contract uniform
    # with the verify endpoint and with the operator-facing toast.
    assert r.status_code == 400, r.text
    assert "número de teléfono" in r.json()["detail"]
    assert fake.calls == []


async def test_connect_manual_trusts_ycloud_canonical_id_over_operator_input(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    """When the operator pastes one id but YCloud returns a different
    canonical id in the payload, persist YCloud's version. Defensive
    against operator typos that YCloud silently soft-matches."""
    fake = _FakeYCloudClient(
        {
            ("WABA1", "111111111111111"): {
                "phoneNumber": "+34632719028",
                "verifiedName": "Auphere",
                "id": "987654321098765",  # canonical, differs from input
            }
        }
    )
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": "WABA1", "phone_number_id": "111111111111111"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["phone_number_id"] == "987654321098765"
    channel = (
        await db_session.execute(
            select(Channel).where(
                Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
            )
        )
    ).scalar_one()
    assert channel.config["phone_number_id"] == "987654321098765"
