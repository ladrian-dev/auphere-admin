import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def test_webhook_rejects_missing_signature(client):
    r = await client.post("/webhook/ycloud", content=b"{}")
    assert r.status_code == 401


async def test_webhook_rejects_wrong_signature(client):
    r = await client.post(
        "/webhook/ycloud",
        content=b'{"phoneNumberId":"x"}',
        headers={"X-YCloud-Signature": "deadbeef"},
    )
    assert r.status_code == 401


async def test_webhook_rejects_invalid_json(client):
    body = b"not json"
    sig = _sign("test-hmac-secret", body)
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"X-YCloud-Signature": sig},
    )
    assert r.status_code == 400


async def test_webhook_ignored_when_no_identifier(client):
    body = json.dumps({"type": "x"}).encode()
    sig = _sign("test-hmac-secret", body)
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={
            "X-YCloud-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_webhook_ignored_when_unknown_identifier(client):
    body = json.dumps({"type": "whatsapp.inbound_message", "phoneNumberId": "ghost"}).encode()
    sig = _sign("test-hmac-secret", body)
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={
            "X-YCloud-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_webhook_accepts_known_identifier(client, db_session, seed_tenants):
    """Seed a channel, send a webhook, expect 'accepted'."""
    tid = seed_tenants["a"]
    from nexus_api.db.models import Channel, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tid,
                type=ChannelType.WHATSAPP,
                provider="ycloud",
                provider_identifier="phone-known-1",
            )
        )

    body = json.dumps(
        {
            "type": "whatsapp.inbound_message",
            "phoneNumberId": "phone-known-1",
            "message": {"id": str(uuid.uuid4()), "text": "hola"},
        }
    ).encode()
    sig = _sign("test-hmac-secret", body)
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={
            "X-YCloud-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


async def test_webhook_accepts_prefixed_signature(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    from nexus_api.db.models import Channel, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tid,
                type=ChannelType.WHATSAPP,
                provider="ycloud",
                provider_identifier="phone-known-2",
            )
        )

    body = json.dumps({"type": "x", "phoneNumberId": "phone-known-2"}).encode()
    sig = "sha256=" + _sign("test-hmac-secret", body)
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={
            "X-YCloud-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
