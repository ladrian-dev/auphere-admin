"""Tests for the Coexistence-only branches of the Meta webhook endpoint.

The Cloud API branches (inbound messages, status callbacks, template
status) are exercised by the channels-level unit tests. This module
covers the three Coexistence-only fields wired in by the same PR:

- ``smb_message_echoes``     → ``nexus:meta:echoes`` stream
- ``smb_app_state_sync``     → ``nexus:meta:state_sync`` stream
- ``history``                → ``nexus:meta:history`` stream

For each:

1. The request must include a valid X-Hub-Signature-256 (same secret as
   the existing route) — without it the route 401s before the field
   dispatch even runs.
2. With a known business phone (resolved via a seeded ``channels`` row),
   the handler enqueues the parsed event to its dedicated Redis stream.
3. Unknown business phone → counter bump, no enqueue.

The future consumer (block D) will read from these streams and persist
into Postgres; until it exists, the buffer is the contract.
"""

from __future__ import annotations

import json

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


# Matches the default in apps/api/src/nexus_api/config.py — the test
# settings override doesn't shadow this, so the route uses the same
# string.
META_APP_SECRET = "dev-meta-app-secret-change-me"


def _hub_sig(body: bytes) -> str:
    return sign_meta_request(META_APP_SECRET, body)


def _envelope(*, field: str, business_phone: str, value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_COEX",
                "changes": [
                    {
                        "field": field,
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN_COEX",
                            },
                            **value,
                        },
                    }
                ],
            }
        ],
    }


async def _seed_meta_channel(db_session, tenant_id, business_phone: str) -> None:
    from nexus_api.db.models import Channel, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=business_phone,
                config={"waba_id": "WABA_COEX", "phone_number_id": "PN_COEX"},
            )
        )


# ── smb_message_echoes ─────────────────────────────────────────────────────


async def test_webhook_enqueues_message_echo_to_dedicated_stream(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    business_phone = "+56999998888"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    payload = _envelope(
        field="smb_message_echoes",
        business_phone=business_phone,
        value={
            "messages": [
                {
                    "id": "wamid.echo-1",
                    "from": business_phone.lstrip("+"),
                    "to": "56911112222",
                    "timestamp": "1716300000",
                    "type": "text",
                    "text": {"body": "respondido desde el movil"},
                }
            ],
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": _hub_sig(body)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    # Stream should now carry exactly one entry with the tenant id and the
    # parsed echo fields.
    entries = await fake_redis.xrange("nexus:meta:echoes", count=10)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    decoded = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in fields.items()
    }
    assert decoded["tenant_id"] == str(tenant_id)
    assert decoded["provider_message_id"] == "wamid.echo-1"
    assert decoded["sender_identifier"] == business_phone.lstrip("+")
    assert decoded["recipient_identifier"] == "56911112222"
    assert decoded["text"] == "respondido desde el movil"


# ── smb_app_state_sync ─────────────────────────────────────────────────────


async def test_webhook_enqueues_app_state_sync_with_raw_value_for_consumer(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    business_phone = "+56999998888"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    payload = _envelope(
        field="smb_app_state_sync",
        business_phone=business_phone,
        value={
            "contacts": [
                {"wa_id": "56911110001", "name": "A"},
                {"wa_id": "56911110002", "name": "B"},
            ],
            "has_more": True,
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": _hub_sig(body)},
    )
    assert r.status_code == 200, r.text

    entries = await fake_redis.xrange("nexus:meta:state_sync", count=10)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    decoded = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in fields.items()
    }
    assert decoded["tenant_id"] == str(tenant_id)
    assert decoded["contact_count"] == "2"
    assert decoded["has_more"] == "1"
    # raw_value carries the contacts list so the consumer can do the
    # actual upsert without re-walking the envelope.
    raw = json.loads(decoded["raw_value"])
    assert len(raw["contacts"]) == 2


# ── history ────────────────────────────────────────────────────────────────


async def test_webhook_enqueues_history_with_message_count_and_error_code(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    business_phone = "+56999998888"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    payload = _envelope(
        field="history",
        business_phone=business_phone,
        value={
            "history": [
                {"messages": [{"id": "h1"}, {"id": "h2"}]},
                {"messages": [{"id": "h3"}]},
            ],
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": _hub_sig(body)},
    )
    assert r.status_code == 200, r.text

    entries = await fake_redis.xrange("nexus:meta:history", count=10)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    decoded = {
        k.decode() if isinstance(k, bytes) else k: (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in fields.items()
    }
    assert decoded["tenant_id"] == str(tenant_id)
    assert decoded["message_count"] == "3"
    assert "error_code" not in decoded  # only set when the business opted out


# ── unknown business phone is dropped, not enqueued ────────────────────────


async def test_webhook_drops_coexistence_event_for_unknown_business_phone(
    client, fake_redis, seed_tenants
):
    # No channel seeded — the resolver raises TenantNotFound and the
    # handler returns without enqueueing.
    payload = _envelope(
        field="smb_message_echoes",
        business_phone="+56900000000",
        value={
            "messages": [
                {
                    "id": "wamid.echo-orphan",
                    "from": "56900000000",
                    "to": "56911112222",
                    "timestamp": "1716300000",
                    "type": "text",
                    "text": {"body": "no tengo channel"},
                }
            ],
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": _hub_sig(body)},
    )
    assert r.status_code == 200, r.text

    entries = await fake_redis.xrange("nexus:meta:echoes", count=10)
    assert all(
        b"wamid.echo-orphan" not in (v if isinstance(v, bytes) else v.encode())
        for _id, fields in entries
        for v in fields.values()
    )


# ── signature is enforced before dispatch ──────────────────────────────────


async def test_webhook_rejects_coexistence_event_without_signature(client):
    payload = _envelope(
        field="smb_message_echoes",
        business_phone="+56999998888",
        value={"messages": []},
    )
    body = json.dumps(payload).encode()
    r = await client.post("/webhook/meta", content=body)
    assert r.status_code == 401
