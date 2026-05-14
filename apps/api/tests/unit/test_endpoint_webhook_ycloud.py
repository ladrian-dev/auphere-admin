"""Tests for the YCloud webhook endpoint with the real signature scheme.

Block F replaced B's generic HMAC verifier with the YCloud-specific
``YCloud-Signature: t=...,s=...`` over ``{ts}.{raw_body}``. These tests
exercise the new shape end-to-end (HTTP → verifier → adapter → Redis XADD).
"""

from __future__ import annotations

import json
import time

import pytest
from nexus_channels.whatsapp_ycloud.signature import sign_ycloud_request
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


# Matches the test settings override in tests/conftest.py.
YCLOUD_WEBHOOK_SECRET = "test-ycloud-webhook-secret"


def _sig(body: bytes, *, ts: int | None = None) -> str:
    return sign_ycloud_request(YCLOUD_WEBHOOK_SECRET, body, timestamp=ts)


def _now() -> int:
    return int(time.time())


def _inbound_envelope(
    *,
    business_phone: str,
    sender_phone: str = "+56911112222",
    text_body: str = "hola",
    wamid: str = "wamid.HBgN-xyz",
) -> dict:
    return {
        "id": "evt_1",
        "type": "whatsapp.inbound_message.received",
        "createTime": "2026-05-09T12:00:00Z",
        "whatsappInboundMessage": {
            "wabaId": "WABA1",
            "to": business_phone,
            "from": sender_phone,
            "wamid": wamid,
            "type": "text",
            "text": {"body": text_body},
            "customerProfile": {"name": "Juan"},
        },
    }


async def test_webhook_rejects_missing_signature(client):
    r = await client.post("/webhook/ycloud", content=b"{}")
    assert r.status_code == 401


async def test_webhook_rejects_wrong_secret(client):
    body = json.dumps(_inbound_envelope(business_phone="+5693999")).encode()
    bad = sign_ycloud_request("nope", body, timestamp=_now())
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": bad},
    )
    assert r.status_code == 401


async def test_webhook_rejects_old_timestamp(client):
    body = b"{}"
    too_old = _sig(body, ts=_now() - 600)
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": too_old},
    )
    assert r.status_code == 401


async def test_webhook_rejects_invalid_json(client):
    body = b"not json"
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 400


async def test_webhook_ignores_status_callback(client):
    body = json.dumps(
        {"type": "whatsapp.message.updated", "whatsappMessage": {"status": "delivered"}}
    ).encode()
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_webhook_ignores_unknown_business_phone(client):
    body = json.dumps(_inbound_envelope(business_phone="+99999999")).encode()
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


async def test_webhook_accepts_known_business_phone(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    from nexus_api.db.models import Channel, ChannelType

    business_phone = "+56933334444"
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
                provider_identifier=business_phone,
            )
        )
    body = json.dumps(_inbound_envelope(business_phone=business_phone)).encode()
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_webhook_accepts_legacy_x_ycloud_signature_header(client, db_session, seed_tenants):
    """Some YCloud accounts emit ``X-YCloud-Signature``; we accept both."""
    tid = seed_tenants["a"]
    from nexus_api.db.models import Channel, ChannelType

    business_phone = "+56933335555"
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
                provider_identifier=business_phone,
            )
        )

    body = json.dumps(_inbound_envelope(business_phone=business_phone)).encode()
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"X-YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_webhook_passes_button_reply_through(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    from nexus_api.db.models import Channel, ChannelType

    business_phone = "+56933336666"
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
                provider_identifier=business_phone,
            )
        )

    payload = {
        "id": "evt_btn",
        "type": "whatsapp.inbound_message.received",
        "createTime": "2026-05-09T12:00:00Z",
        "whatsappInboundMessage": {
            "to": business_phone,
            "from": "+56911112222",
            "wamid": "wamid.btn1",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "btn_yes", "title": "Sí"},
            },
        },
    }
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_webhook_audio_message_enqueued_for_multimodal(
    client, db_session, seed_tenants
):
    """Block N promoted audio inbound to a first-class kind.

    Pre-Block-N the webhook returned ``accepted_no_dispatch`` for media.
    Now the webhook attempts to download the media to S3 (falling back to
    in-memory storage in tests when no S3 creds are configured), enqueues
    a ``kind=audio`` event onto the inbound stream, and the worker's
    multimodal pipeline transcribes it via Whisper before the classifier
    sees it. The ``media_download_failed`` warning logged here is expected
    because the test rig does not have a real YCloud media endpoint to
    fetch from — the webhook still enqueues the inbound so the agent can
    answer "no pude leerlo, ¿lo subes de nuevo?" instead of going silent.
    """
    tid = seed_tenants["a"]
    from nexus_api.db.models import Channel, ChannelType

    business_phone = "+56933337777"
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
                provider_identifier=business_phone,
            )
        )

    payload = {
        "id": "evt_audio",
        "type": "whatsapp.inbound_message.received",
        "createTime": "2026-05-09T12:00:00Z",
        "whatsappInboundMessage": {
            "to": business_phone,
            "from": "+56911112222",
            "wamid": "wamid.audio1",
            "type": "audio",
            "audio": {"id": "media_1", "link": "https://..."},
        },
    }
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/ycloud",
        content=body,
        headers={"YCloud-Signature": _sig(body)},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
