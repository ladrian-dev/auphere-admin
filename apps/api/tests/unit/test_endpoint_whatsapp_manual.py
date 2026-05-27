"""Tests Block J — WhatsApp manual setup endpoints.

Phase 1 onboarding (Camino C): owner creates the WABA in YCloud's SMB
dashboard, copies ``waba_id`` + the phone number in E.164 (``+34...``),
and pastes both in the wizard. Backend uses the phone as the second
path segment of ``GET /v2/whatsapp/phoneNumbers/{wabaId}/{lookup}`` —
YCloud SMB doesn't expose a listing endpoint, so we never query the
WABA without a phone lookup.

YCloud transport stubbed via a fake module-level factory; no network
calls.

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

    ``responses`` is a ``(waba_id, phone_lookup) → dict | YCloudAPIError``
    map. The lookup is whatever the caller passed as the second path
    segment (phone E.164 in the new flow; numeric Meta id in TP flows).
    """

    def __init__(self, responses: dict[tuple[str, str], Any]) -> None:
        self._responses = responses
        self.closed = False
        self.calls: list[tuple[str, str]] = []

    async def get_phone_number(
        self, *, waba_id: str, phone_lookup: str
    ) -> dict[str, Any]:
        from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError

        key = (waba_id, phone_lookup)
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


# Canonical fixture values: WABA `2038094370103030` + phone `+34632719028`
# — same shape as the Auphere production case that surfaced this bug.
_WABA = "2038094370103030"
_E164 = "+34632719028"
_CANONICAL_PHONE_ID = "987654321098765"


def _ycloud_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "phoneNumber": _E164,
        "displayName": "Auphere",
        "verifiedName": "Auphere",
        "qualityRating": "GREEN",
        "id": _CANONICAL_PHONE_ID,
    }
    payload.update(overrides)
    return payload


# ── verify (dry-run) ───────────────────────────────────────────────────────


async def test_verify_returns_phone_summary(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_payload()})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        f"&phone_number_e164={_E164.replace('+', '%2B')}",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phone_number"] == _E164
    assert body["display_name"] == "Auphere"
    assert body["quality_rating"] == "GREEN"
    # The canonical id YCloud surfaced is what we forward to the wizard.
    assert body["phone_number_id"] == _CANONICAL_PHONE_ID
    assert fake.closed is True
    assert fake.calls == [(_WABA, _E164)]


async def test_verify_404_returns_400_with_friendly_message(
    client, admin_headers, monkeypatch
):
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_error(404, "Not Found")})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        f"&phone_number_e164={_E164.replace('+', '%2B')}",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "no encontró" in r.json()["detail"]


async def test_verify_401_returns_400_pointing_at_doppler(
    client, admin_headers, monkeypatch
):
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_error(401, "Unauthorized")})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        f"&phone_number_e164={_E164.replace('+', '%2B')}",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "NEXUS_YCLOUD_API_KEY" in r.json()["detail"]


async def test_verify_403_returns_400_pointing_at_tech_provider(
    client, admin_headers, monkeypatch
):
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_error(403, "Forbidden")})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        f"&phone_number_e164={_E164.replace('+', '%2B')}",
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "Tech Provider" in r.json()["detail"]


async def test_verify_requires_auth(client, monkeypatch):
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        f"&phone_number_e164={_E164.replace('+', '%2B')}"
    )
    assert r.status_code == 401


async def test_verify_rejects_non_e164_phone(client, admin_headers, monkeypatch):
    """The most common typo: pasting just digits (no leading +) or a
    Meta phone_number_id into the phone field. Caught client-side too
    but the backend is the line of defense."""
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        "&phone_number_e164=34632719028",  # no +
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "E.164" in r.json()["detail"]
    # We never reached YCloud.
    assert fake.calls == []


async def test_verify_normalises_whitespace_and_dashes(
    client, admin_headers, monkeypatch
):
    """YCloud's dashboard often shows the phone with spaces or dashes —
    accept it and strip before forwarding."""
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_payload()})
    _patch_ycloud(monkeypatch, fake)
    # "+34 632 719-028" with the + URL-encoded.
    r = await client.get(
        f"/admin/integrations/whatsapp/verify?waba_id={_WABA}"
        "&phone_number_e164=%2B34%20632%20719-028",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert fake.calls == [(_WABA, _E164)]


# ── connect-manual ─────────────────────────────────────────────────────────


async def test_connect_manual_creates_channel_and_audit(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_payload()})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": _WABA, "phone_number_e164": _E164},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["phone_number"] == _E164
    assert body["display_name"] == "Auphere"
    # We persist the canonical id YCloud surfaced.
    assert body["phone_number_id"] == _CANONICAL_PHONE_ID

    # Channel row created with the right shape.
    channel = (
        await db_session.execute(
            select(Channel).where(
                Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
            )
        )
    ).scalar_one()
    assert channel.provider == "ycloud"
    assert channel.provider_identifier == _E164
    assert channel.status == ChannelStatus.ACTIVE
    assert channel.config["waba_id"] == _WABA
    assert channel.config["phone_number_id"] == _CANONICAL_PHONE_ID
    assert channel.config["display_name"] == "Auphere"
    assert channel.config["verified_name"] == "Auphere"
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
    assert audit.after_json["phone_number"] == _E164


async def test_connect_manual_persists_empty_phone_number_id_when_ycloud_omits_it(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    """Some YCloud SMB responses don't include an ``id`` field. Outbound
    routes by E.164, so the channel still works — we persist ``""``."""
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_payload(id=None)})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": _WABA, "phone_number_e164": _E164},
    )
    assert r.status_code == 201, r.text
    assert r.json()["phone_number_id"] == ""
    channel = (
        await db_session.execute(
            select(Channel).where(
                Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
            )
        )
    ).scalar_one()
    assert channel.config["phone_number_id"] == ""


async def test_connect_manual_idempotent_reconnects_in_place(
    client, admin_headers, monkeypatch, seed_tenants, db_session
):
    """Re-running connect-manual for the same tenant updates the existing
    Channel row (rather than tripping UNIQUE on a 2nd insert)."""
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_payload()})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    url = f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual"
    body = {"waba_id": _WABA, "phone_number_e164": _E164}
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
    """Tenant A connects +34632719028. Tenant B tries the same number → 409
    (the global UNIQUE on (type, provider_identifier) trips)."""
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_payload()})
    _patch_ycloud(monkeypatch, fake)
    tenant_a = seed_tenants["a"]
    tenant_b = seed_tenants["b"]
    body = {"waba_id": _WABA, "phone_number_e164": _E164}
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
    fake = _FakeYCloudClient({(_WABA, _E164): _ycloud_error(404, "Not Found")})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": _WABA, "phone_number_e164": _E164},
    )
    assert r.status_code == 400
    assert "no encontró" in r.json()["detail"]


async def test_connect_manual_unknown_tenant_404(client, admin_headers, monkeypatch):
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    r = await client.post(
        f"/admin/tenants/{uuid.uuid4()}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": _WABA, "phone_number_e164": _E164},
    )
    assert r.status_code == 404


async def test_connect_manual_rejects_non_e164_phone(
    client, admin_headers, monkeypatch, seed_tenants
):
    fake = _FakeYCloudClient({})
    _patch_ycloud(monkeypatch, fake)
    tenant_id = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
        headers=admin_headers,
        json={"waba_id": _WABA, "phone_number_e164": "34632719028"},  # missing +
    )
    assert r.status_code == 400
    assert "E.164" in r.json()["detail"]
    assert fake.calls == []
