"""Tests for ``auphere_owner_channels`` (migrations 0038 + 0044).

Three layers verified:

1. **Repository** — get_by_phone / get_by_provider_phone_id /
   get_default / list_all behaviours including the active-flag filter
   and the unique-default constraint.
2. **Resolver** — ``resolve_channel_for_inbound`` (by Meta
   ``phone_number_id``) and ``resolve_channel_for_owner`` cover the
   lookup priority. There is no settings fallback anymore — an empty
   registry means the backchannel is disabled.
3. **Inbound webhook** — ``/webhook/meta`` routes events whose
   ``metadata.phone_number_id`` matches a registered Auphere channel to
   the owner flow, and treats foreign phone_number_ids as regular
   tenant traffic.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request

from nexus_api.db.models import AuphereOwnerChannel, OwnerPhoneIndex
from nexus_api.repositories.auphere_channels import (
    AuphereChannelRepository,
    resolve_channel_for_inbound,
    resolve_channel_for_owner,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


META_APP_SECRET = "dev-meta-app-secret-change-me"


async def _insert_channel(
    db_session,
    *,
    phone: str,
    name: str = "Test channel",
    country: str | None = None,
    provider: str = "meta",
    provider_phone_id: str | None = None,
    access_token: str | None = None,
    active: bool = True,
    is_default: bool = False,
) -> AuphereOwnerChannel:
    row = AuphereOwnerChannel(
        phone_e164=phone,
        display_name=name,
        country_code=country,
        provider=provider,
        provider_phone_id=provider_phone_id,
        access_token_encrypted=(
            access_token.encode("utf-8") if access_token else None
        ),
        active=active,
        is_default=is_default,
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

    async def test_get_by_provider_phone_id(self, db_session):
        hit_row = await _insert_channel(
            db_session,
            phone="+56000000003",
            name="CL",
            provider_phone_id="111000111",
        )
        await _insert_channel(
            db_session,
            phone="+56000000004",
            name="dead",
            provider_phone_id="222000222",
            active=False,
        )
        repo = AuphereChannelRepository(db_session)
        hit = await repo.get_by_provider_phone_id("111000111")
        assert hit is not None and hit.id == hit_row.id
        # Inactive rows are hidden by default at the webhook layer.
        assert await repo.get_by_provider_phone_id("222000222") is None
        assert (
            await repo.get_by_provider_phone_id("222000222", only_active=False)
            is not None
        )

    async def test_get_default_returns_meta_default(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000005",
            name="not default",
            is_default=False,
        )
        the_default = await _insert_channel(
            db_session,
            phone="+56000000006",
            name="Meta default",
            is_default=True,
        )
        repo = AuphereChannelRepository(db_session)
        default = await repo.get_default()
        assert default is not None and default.id == the_default.id

    async def test_unique_default_constraint(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000007",
            name="first default",
            is_default=True,
        )
        # Second default for the same provider trips the partial unique
        # index.
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await _insert_channel(
                db_session,
                phone="+56000000008",
                name="second default",
                is_default=True,
            )

    async def test_list_all_active_only_by_default(self, db_session):
        await _insert_channel(
            db_session, phone="+56000000009", name="active", active=True
        )
        await _insert_channel(
            db_session, phone="+56000000010", name="inactive", active=False
        )
        repo = AuphereChannelRepository(db_session)
        active = await repo.list_all()
        assert {c.display_name for c in active} == {"active"}
        all_rows = await repo.list_all(include_inactive=True)
        assert {c.display_name for c in all_rows} == {"active", "inactive"}


# ── Resolver: inbound (by Meta phone_number_id) ─────────────────────


class TestResolverInbound:
    async def test_hit_in_registry(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000020",
            name="CL",
            provider_phone_id="333000333",
            access_token="EAAtoken",
        )
        resolved = await resolve_channel_for_inbound(
            db_session, provider_phone_id="333000333"
        )
        assert resolved is not None
        assert resolved.phone_e164 == "+56000000020"
        assert resolved.provider == "meta"
        assert resolved.provider_phone_id == "333000333"
        assert resolved.access_token == "EAAtoken"
        assert resolved.can_send is True

    async def test_resolved_without_token_cannot_send(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000021",
            name="setup pending",
            provider_phone_id="444000444",
            access_token=None,
        )
        resolved = await resolve_channel_for_inbound(
            db_session, provider_phone_id="444000444"
        )
        assert resolved is not None
        assert resolved.access_token is None
        assert resolved.can_send is False

    async def test_returns_none_for_foreign_phone_number_id(self, db_session):
        resolved = await resolve_channel_for_inbound(
            db_session, provider_phone_id="999999999"
        )
        assert resolved is None

    async def test_inactive_channel_treated_as_foreign(self, db_session):
        await _insert_channel(
            db_session,
            phone="+56000000022",
            name="paused",
            provider_phone_id="555000555",
            active=False,
        )
        resolved = await resolve_channel_for_inbound(
            db_session, provider_phone_id="555000555"
        )
        assert resolved is None


# ── Resolver: outbound ──────────────────────────────────────────────


def _owner(
    *, phone: str, tenant_id: uuid.UUID, channel_id: uuid.UUID | None = None
) -> OwnerPhoneIndex:
    return OwnerPhoneIndex(
        phone_e164=phone,
        tenant_id=tenant_id,
        added_at=datetime.now(UTC),
        active=True,
        auphere_channel_id=channel_id,
    )


class TestResolverOutbound:
    async def test_uses_pinned_channel_when_owner_has_one(
        self, db_session, seed_tenants
    ):
        pinned = await _insert_channel(
            db_session,
            phone="+56000000030",
            name="CL pinned",
            is_default=False,
        )
        owner = _owner(
            phone="+56999111222",
            tenant_id=seed_tenants["a"],
            channel_id=pinned.id,
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
            phone="+56000000031",
            name="Meta default",
            is_default=True,
        )
        owner = _owner(phone="+56999333444", tenant_id=seed_tenants["a"])
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is not None
        assert resolved.display_name == "Meta default"

    async def test_returns_none_when_registry_empty(
        self, db_session, seed_tenants
    ):
        """No registered channel and no default → backchannel disabled.
        (The legacy settings fallback was removed with YCloud.)"""
        owner = _owner(phone="+56999555666", tenant_id=seed_tenants["a"])
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is None

    async def test_inactive_pinned_falls_back_to_default(
        self, db_session, seed_tenants
    ):
        inactive = await _insert_channel(
            db_session,
            phone="+56000000032",
            name="dead",
            active=False,
        )
        default = await _insert_channel(
            db_session,
            phone="+56000000033",
            name="alive default",
            is_default=True,
        )
        owner = _owner(
            phone="+56999777888",
            tenant_id=seed_tenants["a"],
            channel_id=inactive.id,
        )
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)

        resolved = await resolve_channel_for_owner(db_session, owner=owner)
        assert resolved is not None
        assert resolved.channel_id == default.id


# ── Inbound webhook end-to-end (multi-channel) ──────────────────────


def _meta_inbound_payload(
    *, phone_number_id: str, sender: str, text: str
) -> bytes:
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "56222000001",
                                    "phone_number_id": phone_number_id,
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Owner"},
                                        "wa_id": sender.lstrip("+"),
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": sender.lstrip("+"),
                                        "id": f"wamid.{uuid.uuid4().hex}",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()


async def _post_meta(client, body: bytes):
    return await client.post(
        "/webhook/meta",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body),
        },
    )


class TestWebhookMultiChannel:
    async def test_routes_inbound_to_registered_channel(
        self, client, db_session
    ):
        await _insert_channel(
            db_session,
            phone="+56222000001",
            name="CL",
            provider_phone_id="666000666",
        )
        # Sender has no OwnerPhoneIndex row → the owner flow answers
        # "unknown_phone", which proves the event was routed to the
        # backchannel (and not treated as tenant traffic).
        body = _meta_inbound_payload(
            phone_number_id="666000666",
            sender="+56999000999",
            text="hola",
        )
        r = await _post_meta(client, body)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "owner_channel:ignored:unknown_phone"

    async def test_foreign_phone_number_id_is_tenant_traffic(
        self, client, db_session
    ):
        """An event whose phone_number_id is NOT in the registry must go
        down the regular tenant path, never the owner flow."""
        body = _meta_inbound_payload(
            phone_number_id="999888777",
            sender="+56999000999",
            text="hola",
        )
        r = await _post_meta(client, body)
        assert r.status_code == 200
        assert not r.json()["status"].startswith("owner_channel:")

    async def test_inactive_channel_is_tenant_traffic(
        self, client, db_session
    ):
        """A deactivated Auphere number no longer captures traffic."""
        await _insert_channel(
            db_session,
            phone="+56222000002",
            name="off",
            provider_phone_id="777000777",
            active=False,
        )
        body = _meta_inbound_payload(
            phone_number_id="777000777",
            sender="+56999000999",
            text="hola",
        )
        r = await _post_meta(client, body)
        assert r.status_code == 200
        assert not r.json()["status"].startswith("owner_channel:")
