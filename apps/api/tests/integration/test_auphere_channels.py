"""Tests for ``auphere_owner_channels`` (migration 0038).

Three layers verified:

1. **Repository** — get_by_phone / get_default / list_all behaviours
   including the active-flag filter and the unique-default constraint.
2. **Resolver** — ``resolve_channel_for_inbound`` and
   ``resolve_channel_for_owner`` cover the lookup priority and the
   legacy settings fallback.
3. **Inbound webhook** — the route accepts traffic for a registered
   channel, falls back to ``settings.auphere_owner_phone`` when the
   registry is empty, and rejects foreign destinations.

A few tests monkeypatch the YCloud signature verifier so we can drive
the inbound endpoint without forging real HMAC headers — the routing
logic (the actual surface this PR changes) is what we want to pin.
"""

from __future__ import annotations

import json
import uuid

import pytest

from nexus_api.config import get_settings
from nexus_api.db.models import AuphereOwnerChannel, OwnerPhoneIndex
from nexus_api.repositories.auphere_channels import (
    AuphereChannelRepository,
    resolve_channel_for_inbound,
    resolve_channel_for_owner,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


_ADMIN_HEADERS = {"Authorization": "Bearer test-admin-token"}


async def _insert_channel(
    db_session,
    *,
    phone: str,
    name: str = "Test channel",
    country: str | None = None,
    provider: str = "ycloud",
    provider_phone_id: str | None = None,
    active: bool = True,
    is_default: bool = False,
    webhook_secret: str | None = None,
) -> AuphereOwnerChannel:
    row = AuphereOwnerChannel(
        phone_e164=phone,
        display_name=name,
        country_code=country,
        provider=provider,
        provider_phone_id=provider_phone_id,
        active=active,
        is_default=is_default,
        webhook_secret_encrypted=(
            webhook_secret.encode("utf-8") if webhook_secret else None
        ),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


# ── Repository ──────────────────────────────────────────────────────


class TestRepository:
    async def test_get_by_phone_returns_active_only_by_default(
        self, db_session
    ):
        active = await _insert_channel(
            db_session, phone="+56000000001", name="A", active=True
        )
        await _insert_channel(
            db_session, phone="+56000000002", name="B", active=False
        )
        repo = AuphereChannelRepository(db_session)
        hit = await repo.get_by_phone("+56000000001")
        assert hit is not None and hit.id == active.id
        # Inactive row hidden by default.
        miss = await repo.get_by_phone("+56000000002")
        assert miss is None
        # ...but visible when explicitly requested.
        miss2 = await repo.get_by_phone("+56000000002", only_active=False)
        assert miss2 is not None

    async def test_get_default_per_provider(self, db_session):
        ycloud_default = await _insert_channel(
            db_session,
            phone="+56000000003",
            name="YCloud default",
            provider="ycloud",
            is_default=True,
        )
        await _insert_channel(
            db_session,
            phone="+56000000004",
            name="Meta default",
            provider="meta",
            is_default=True,
        )
        repo = AuphereChannelRepository(db_session)
        yc = await repo.get_default(provider="ycloud")
        meta = await repo.get_default(provider="meta")
        assert yc is not None and yc.id == ycloud_default.id
        assert meta is not None and meta.provider == "meta"

    async def test_unique_default_constraint(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000005",
            name="first default",
            provider="ycloud",
            is_default=True,
        )
        # Second default for the same provider trips the partial unique
        # index.
        with pytest.raises(Exception):
            await _insert_channel(
                db_session,
                phone="+56000000006",
                name="second default",
                provider="ycloud",
                is_default=True,
            )

    async def test_list_all_active_only_by_default(self, db_session):
        await _insert_channel(
            db_session, phone="+56000000007", name="active", active=True
        )
        await _insert_channel(
            db_session, phone="+56000000008", name="inactive", active=False
        )
        repo = AuphereChannelRepository(db_session)
        active = await repo.list_all()
        assert {c.display_name for c in active} == {"active"}
        all_rows = await repo.list_all(include_inactive=True)
        assert {c.display_name for c in all_rows} == {"active", "inactive"}


# ── Resolver: inbound ───────────────────────────────────────────────


class TestResolverInbound:
    async def test_hit_in_registry(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000010",
            name="CL",
            webhook_secret="per-channel-secret",
        )
        resolved = await resolve_channel_for_inbound(
            db_session, to_phone="+56000000010"
        )
        assert resolved is not None
        assert resolved.phone_e164 == "+56000000010"
        assert resolved.webhook_secret == "per-channel-secret"
        assert resolved.is_legacy_fallback is False

    async def test_falls_back_to_settings_when_registry_empty(
        self, db_session, monkeypatch
    ):
        settings = get_settings()
        monkeypatch.setattr(
            settings, "auphere_owner_phone", "+56000000099"
        )
        resolved = await resolve_channel_for_inbound(
            db_session, to_phone="+56000000099"
        )
        assert resolved is not None
        assert resolved.is_legacy_fallback is True
        # The legacy fallback has no per-channel secret — caller uses
        # the shared YCloud one.
        assert resolved.webhook_secret is None

    async def test_returns_none_for_foreign_destination(
        self, db_session, monkeypatch
    ):
        settings = get_settings()
        monkeypatch.setattr(
            settings, "auphere_owner_phone", "+56000000099"
        )
        # Registry empty, settings doesn't match.
        resolved = await resolve_channel_for_inbound(
            db_session, to_phone="+34000000000"
        )
        assert resolved is None

    async def test_inactive_channel_treated_as_foreign(
        self, db_session, monkeypatch
    ):
        await _insert_channel(
            db_session,
            phone="+56000000011",
            name="paused",
            active=False,
        )
        settings = get_settings()
        # Make sure legacy fallback doesn't accidentally rescue it.
        monkeypatch.setattr(settings, "auphere_owner_phone", None)
        resolved = await resolve_channel_for_inbound(
            db_session, to_phone="+56000000011"
        )
        assert resolved is None


# ── Resolver: outbound ──────────────────────────────────────────────


class TestResolverOutbound:
    async def test_uses_pinned_channel_when_owner_has_one(
        self, db_session, seed_tenants
    ):
        pinned = await _insert_channel(
            db_session,
            phone="+56000000020",
            name="CL pinned",
            is_default=False,
        )
        owner = OwnerPhoneIndex(
            phone_e164="+56999111222",
            tenant_id=seed_tenants["a"],
            added_at=__import__(
                "datetime"
            ).datetime.now(__import__("datetime").UTC),
            active=True,
            auphere_channel_id=pinned.id,
        )
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is not None
        assert resolved.channel_id == pinned.id

    async def test_falls_back_to_default_when_owner_has_no_pin(
        self, db_session, seed_tenants
    ):
        await _insert_channel(
            db_session,
            phone="+56000000021",
            name="YCloud default",
            is_default=True,
        )
        owner = OwnerPhoneIndex(
            phone_e164="+56999333444",
            tenant_id=seed_tenants["a"],
            added_at=__import__(
                "datetime"
            ).datetime.now(__import__("datetime").UTC),
            active=True,
            auphere_channel_id=None,
        )
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is not None
        assert resolved.display_name == "YCloud default"

    async def test_falls_back_to_settings_when_no_default(
        self, db_session, seed_tenants, monkeypatch
    ):
        settings = get_settings()
        monkeypatch.setattr(
            settings, "auphere_owner_phone", "+56000000077"
        )
        owner = OwnerPhoneIndex(
            phone_e164="+56999555666",
            tenant_id=seed_tenants["a"],
            added_at=__import__(
                "datetime"
            ).datetime.now(__import__("datetime").UTC),
            active=True,
        )
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is not None
        assert resolved.is_legacy_fallback is True
        assert resolved.phone_e164 == "+56000000077"

    async def test_inactive_pinned_falls_back_to_default(
        self, db_session, seed_tenants
    ):
        inactive = await _insert_channel(
            db_session,
            phone="+56000000030",
            name="dead",
            active=False,
        )
        default = await _insert_channel(
            db_session,
            phone="+56000000031",
            name="alive default",
            is_default=True,
        )
        owner = OwnerPhoneIndex(
            phone_e164="+56999777888",
            tenant_id=seed_tenants["a"],
            added_at=__import__(
                "datetime"
            ).datetime.now(__import__("datetime").UTC),
            active=True,
            auphere_channel_id=inactive.id,
        )
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is not None
        assert resolved.channel_id == default.id


# ── Inbound webhook end-to-end (multi-channel) ──────────────────────


def _bypass_signature(monkeypatch) -> None:
    """Replace ``verify_ycloud_signature`` with a no-op so the test
    drives the routing logic without forging real HMAC."""
    import nexus_api.api.webhooks.owner_channel as oc

    def _noop(secret, body, sig, *, tolerance_seconds):  # noqa: D401
        return True

    monkeypatch.setattr(oc, "verify_ycloud_signature", _noop)


class TestWebhookMultiChannel:
    async def test_routes_inbound_to_registered_channel(
        self, client, db_session, monkeypatch
    ):
        _bypass_signature(monkeypatch)
        await _insert_channel(
            db_session, phone="+56222000001", name="CL"
        )
        # OwnerPhoneIndex row for the sender → tenant lookup.
        # Without a matching tenant the webhook returns "unknown_phone"
        # which is still a 200 with status payload — that's what we
        # check.
        payload = json.dumps(
            {
                "type": "whatsapp.inbound_message.received",
                "whatsappInboundMessage": {
                    "to": "+56222000001",
                    "from": "+56999000999",
                    "text": {"body": "hola"},
                },
            }
        )
        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=payload,
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200, r.text
        # We expect either "ignored:unknown_phone" or
        # "ignored:no_open_consultation" — both indicate the routing
        # accepted the destination AND looked further. "ignored:
        # wrong_destination" would mean routing rejected.
        assert "wrong_destination" not in r.json()["status"]

    async def test_rejects_foreign_destination(
        self, client, db_session, monkeypatch
    ):
        _bypass_signature(monkeypatch)
        settings = get_settings()
        # Clear legacy fallback to make sure rejection is real.
        monkeypatch.setattr(settings, "auphere_owner_phone", None)
        payload = json.dumps(
            {
                "type": "whatsapp.inbound_message.received",
                "whatsappInboundMessage": {
                    "to": "+99999999999",  # unknown
                    "from": "+56999000999",
                    "text": {"body": "hola"},
                },
            }
        )
        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=payload,
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored:wrong_destination"

    async def test_legacy_settings_fallback_still_works(
        self, client, db_session, monkeypatch
    ):
        """When the registry is empty, an inbound to the legacy
        ``settings.auphere_owner_phone`` MUST still be accepted —
        Phase 1 compatibility."""
        _bypass_signature(monkeypatch)
        settings = get_settings()
        monkeypatch.setattr(
            settings, "auphere_owner_phone", "+56222999999"
        )
        payload = json.dumps(
            {
                "type": "whatsapp.inbound_message.received",
                "whatsappInboundMessage": {
                    "to": "+56222999999",
                    "from": "+56999000999",
                    "text": {"body": "hola"},
                },
            }
        )
        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=payload,
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert "wrong_destination" not in r.json()["status"]
