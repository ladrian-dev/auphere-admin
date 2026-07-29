"""The TikTok Business Messaging webhook endpoint.

Covers the guarantees the route is responsible for, in the order they'd bite:

- signature verification gates everything;
- an unresolvable business id is acked and dropped, never guessed at;
- ``conversation_id`` reaches the stream, because without it the agent's
  reply has nowhere to go;
- redrives are deduped;
- non-message events are recognised rather than treated as failures.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from nexus_channels.tiktok_bm.signature import sign_tiktok_request
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

TIKTOK_APP_SECRET = "dev-tiktok-app-secret-change-me"
BUSINESS_ID = "7123456789012345678"
SENDER_OPEN_ID = "_000AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCDEF"
CONVERSATION_ID = "conv_abc123"


def _envelope(
    *,
    business_id: str = BUSINESS_ID,
    message_id: str = "msg_1",
    message_type: str = "text",
    content: dict[str, Any] | None = None,
    conversation_id: str | None = CONVERSATION_ID,
    event: str = "message_received",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "message_id": message_id,
        "sender": {"open_id": SENDER_OPEN_ID, "nickname": "Ana"},
        "message_type": message_type,
        "content": content if content is not None else {"text": "hola Auphere"},
    }
    if conversation_id is not None:
        data["conversation_id"] = conversation_id
    return {
        "event": event,
        "business_id": business_id,
        "timestamp": 1_800_000_000,
        "data": data,
    }


def _signed(payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    return body, {"TikTok-Signature": sign_tiktok_request(TIKTOK_APP_SECRET, body)}


async def _seed_tiktok_channel(db_session, tenant_id, business_id: str = BUSINESS_ID) -> None:
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.TIKTOK,
                provider="tiktok",
                provider_identifier=business_id,
                status=ChannelStatus.ACTIVE,
                config={
                    "business_id": business_id,
                    "service_window_hours": 48,
                    "supports_business_initiated": False,
                },
            )
        )


async def _inbound_entries(fake_redis) -> list[dict[str, str]]:
    entries = await fake_redis.xrange("nexus:inbound", count=50)
    return [
        {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in fields.items()
        }
        for _id, fields in entries
    ]


# ── signature ───────────────────────────────────────────────────────────────


async def test_rejects_an_unsigned_delivery(client):
    body = json.dumps(_envelope()).encode()

    r = await client.post("/webhook/tiktok", content=body)

    assert r.status_code == 401


async def test_rejects_a_signature_from_the_wrong_secret(client):
    body = json.dumps(_envelope()).encode()
    bad = sign_tiktok_request("not-our-secret", body)

    r = await client.post("/webhook/tiktok", content=body, headers={"TikTok-Signature": bad})

    assert r.status_code == 401


async def test_rejects_a_tampered_body(client):
    """The signature covers the raw bytes; changing the business id after
    signing must not verify."""
    body, headers = _signed(_envelope())
    tampered = body.replace(BUSINESS_ID.encode(), b"9999999999999999999")

    r = await client.post("/webhook/tiktok", content=tampered, headers=headers)

    assert r.status_code == 401


# ── inbound ─────────────────────────────────────────────────────────────────


async def test_inbound_text_enqueues_with_the_conversation_id(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    await _seed_tiktok_channel(db_session, tenant_id)
    body, headers = _signed(_envelope())

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    mine = [
        e for e in await _inbound_entries(fake_redis) if e.get("provider_message_id") == "msg_1"
    ]
    assert len(mine) == 1
    entry = mine[0]
    assert entry["provider"] == "tiktok"
    assert entry["content"] == "hola Auphere"
    assert entry["tenant_id"] == str(tenant_id)
    assert entry["user_id"] == SENDER_OPEN_ID
    assert entry["customer_name"] == "Ana"
    # Without this the outbound dispatcher has no way to reply at all.
    assert entry["context_message_id"] == CONVERSATION_ID


async def test_an_unresolvable_business_id_is_acked_and_dropped(client, fake_redis, seed_tenants):
    """Fail-closed: no tenant means no processing, and a 200 so TikTok stops
    redriving something we can never route."""
    body, headers = _signed(_envelope(business_id="8888888888888888888"))

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
    assert await _inbound_entries(fake_redis) == []


async def test_a_message_without_a_conversation_id_is_not_enqueued(
    client, db_session, fake_redis, seed_tenants
):
    """Queuing it would produce an answer with nowhere to send it."""
    tenant_id = seed_tenants["a"]
    await _seed_tiktok_channel(db_session, tenant_id)
    body, headers = _signed(_envelope(message_id="msg_noconv", conversation_id=None))

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
    assert not [
        e
        for e in await _inbound_entries(fake_redis)
        if e.get("provider_message_id") == "msg_noconv"
    ]


async def test_a_redrive_is_deduped(client, db_session, fake_redis, seed_tenants):
    tenant_id = seed_tenants["a"]
    await _seed_tiktok_channel(db_session, tenant_id)
    body, headers = _signed(_envelope(message_id="msg_dupe"))

    first = await client.post("/webhook/tiktok", content=body, headers=headers)
    second = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert first.json()["status"] == "ok"
    assert second.json()["status"] == "deduped"

    mine = [
        e for e in await _inbound_entries(fake_redis) if e.get("provider_message_id") == "msg_dupe"
    ]
    assert len(mine) == 1


async def test_an_unsupported_message_type_still_reaches_the_agent(
    client, db_session, fake_redis, seed_tenants
):
    """The agent saying "no pude leer eso" beats the turn vanishing."""
    tenant_id = seed_tenants["a"]
    await _seed_tiktok_channel(db_session, tenant_id)
    body, headers = _signed(
        _envelope(message_id="msg_weird", message_type="sticker_pack_v3", content={})
    )

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.json()["status"] == "ok"
    entry = next(
        e for e in await _inbound_entries(fake_redis) if e["provider_message_id"] == "msg_weird"
    )
    assert entry["kind"] == "unsupported"


# ── non-message events ──────────────────────────────────────────────────────


async def test_a_read_receipt_is_acked_without_enqueuing(client, fake_redis, seed_tenants):
    body, headers = _signed(_envelope(event="message_read"))

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
    assert await _inbound_entries(fake_redis) == []


async def test_an_unknown_event_is_acked(client, fake_redis, seed_tenants):
    body, headers = _signed(_envelope(event="some_future_event"))

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_signed_but_unparseable_json_is_acked_not_500(client):
    """A 500 here would turn one bad payload into a redrive storm."""
    body = b"{not json at all"
    headers = {"TikTok-Signature": sign_tiktok_request(TIKTOK_APP_SECRET, body)}

    r = await client.post("/webhook/tiktok", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
