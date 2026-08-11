"""Tests for the Cloud API inbound-message branch of the Meta webhook.

Covers the two Phase-2 fixes plus a baseline:

- text inbound → enqueued to ``nexus:inbound`` (baseline, previously untested);
- STOP inbound → opt-out persisted AND NOT enqueued (the dispatcher must not
  reply to someone who opted out);
- media inbound → the webhook does ZERO media I/O (WP-11): the stream entry
  carries ``media_provider_id`` and the runner resolves bytes → S3.
"""

from __future__ import annotations

import json

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

META_APP_SECRET = "dev-meta-app-secret-change-me"


def _hub_sig(body: bytes) -> str:
    return sign_meta_request(META_APP_SECRET, body)


def _inbound_envelope(*, business_phone: str, sender: str, message: dict) -> dict:
    return {
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
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN1",
                            },
                            "contacts": [{"profile": {"name": "Cliente"}, "wa_id": sender}],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


async def _seed_meta_channel(db_session, tenant_id, business_phone: str) -> None:
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
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=business_phone,
                status=ChannelStatus.ACTIVE,
                config={"waba_id": "WABA1", "phone_number_id": "PN1"},
            )
        )


async def _inbound_entries(fake_redis) -> list[dict[str, str]]:
    entries = await fake_redis.xrange("nexus:inbound:standard", count=50)
    out = []
    for _id, fields in entries:
        out.append(
            {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in fields.items()
            }
        )
    return out


async def test_inbound_text_enqueues(client, db_session, fake_redis, seed_tenants):
    tenant_id = seed_tenants["a"]
    business_phone = "+56999997777"
    sender = "56911112222"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    payload = _inbound_envelope(
        business_phone=business_phone,
        sender=sender,
        message={
            "from": sender,
            "id": "wamid.text-1",
            "timestamp": "1716300000",
            "type": "text",
            "text": {"body": "hola Auphere"},
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    entries = await _inbound_entries(fake_redis)
    mine = [e for e in entries if e.get("provider_message_id") == "wamid.text-1"]
    assert len(mine) == 1
    assert mine[0]["provider"] == "meta"
    assert mine[0]["content"] == "hola Auphere"
    assert mine[0]["tenant_id"] == str(tenant_id)


async def test_inbound_stop_records_optout_and_skips_enqueue(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    business_phone = "+56999996666"
    sender = "56911113333"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    payload = _inbound_envelope(
        business_phone=business_phone,
        sender=sender,
        message={
            "from": sender,
            "id": "wamid.stop-1",
            "timestamp": "1716300000",
            "type": "text",
            "text": {"body": "STOP"},
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text

    # NOT enqueued — the dispatcher must never reply to an opted-out user.
    entries = await _inbound_entries(fake_redis)
    assert all(e.get("provider_message_id") != "wamid.stop-1" for e in entries)

    # Opt-out row persisted under the tenant.
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        count = await db_session.scalar(
            text(
                "SELECT count(*) FROM whatsapp_opt_outs "
                "WHERE recipient_phone = :r AND opted_in_at IS NULL"
            ),
            {"r": sender},
        )
    assert count == 1


async def test_inbound_image_publishes_provider_id_without_download(
    client, db_session, fake_redis, seed_tenants, monkeypatch
):
    """WP-11 (D10, cierra V7): the webhook must do ZERO media I/O. It
    publishes the provider media id + hints and the RUNNER resolves bytes →
    S3 before classify. Any storage or Graph-media call from the webhook
    path is a regression back to V7 (a burst of voice notes saturating the
    API's pool while Meta waits for its 200)."""
    tenant_id = seed_tenants["a"]
    business_phone = "+56999995555"
    sender = "56911114444"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    def _no_storage_allowed(*args, **kwargs):
        raise AssertionError("webhook must not touch media storage (WP-11)")

    monkeypatch.setattr("nexus_api.services.media_storage.get_media_storage", _no_storage_allowed)

    payload = _inbound_envelope(
        business_phone=business_phone,
        sender=sender,
        message={
            "from": sender,
            "id": "wamid.img-1",
            "timestamp": "1716300000",
            "type": "image",
            "image": {
                "id": "MEDIA_ID_1",
                "mime_type": "image/jpeg",
                "sha256": "abc123",
                "caption": "mira esto",
            },
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    entries = await _inbound_entries(fake_redis)
    mine = [e for e in entries if e.get("provider_message_id") == "wamid.img-1"]
    assert len(mine) == 1
    assert mine[0]["media_kind"] == "image"
    assert mine[0]["media_provider_id"] == "MEDIA_ID_1"
    assert mine[0]["media_mime"] == "image/jpeg"
    assert mine[0]["media_sha256"] == "abc123"
    # No S3 reference yet — that is the runner's job now.
    assert "media_s3_key" not in mine[0]


async def test_inbound_flags_read_receipt_for_the_runner(
    client, db_session, fake_redis, seed_tenants
):
    """El webhook DECIDE el acuse de lectura; ya no lo envía.

    Enviarlo aquí era una llamada HTTPS a Meta esperada antes del 200, con
    la conexión de BD de la petición retenida: ~40% del ack medido en
    staging, y el motivo de que `webhook_ack_ms` p95 < 50 ms fuera
    inalcanzable. Ahora viaja como `mark_read` en la entrada del stream y
    lo envía el runner con su adaptador de larga vida.
    """
    tenant_id = seed_tenants["a"]
    business_phone = "+56999996666"
    sender = "56911113333"
    await _seed_meta_channel(db_session, tenant_id, business_phone)

    payload = _inbound_envelope(
        business_phone=business_phone,
        sender=sender,
        message={
            "from": sender,
            "id": "wamid.read-1",
            "timestamp": "1716300000",
            "type": "text",
            "text": {"body": "¿tienen hora mañana?"},
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text

    entries = await _inbound_entries(fake_redis)
    mine = [e for e in entries if e.get("provider_message_id") == "wamid.read-1"]
    assert len(mine) == 1
    assert mine[0]["mark_read"] == "1"


async def test_send_only_channel_does_not_flag_read_receipt(
    client, db_session, fake_redis, seed_tenants
):
    """Canal send-only: nadie lee al otro lado, así que ni ticks azules ni
    flag. La supresión sigue decidiéndose en el webhook, que es donde está
    la configuración del canal."""
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    tenant_id = seed_tenants["a"]
    business_phone = "+56999995555"
    sender = "56911114444"

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
                status=ChannelStatus.ACTIVE,
                config={
                    "waba_id": "WABA1",
                    "phone_number_id": "PN1",
                    "agent_enabled": False,
                },
            )
        )

    payload = _inbound_envelope(
        business_phone=business_phone,
        sender=sender,
        message={
            "from": sender,
            "id": "wamid.read-2",
            "timestamp": "1716300000",
            "type": "text",
            "text": {"body": "hola"},
        },
    )
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
    )
    assert r.status_code == 200, r.text

    entries = await _inbound_entries(fake_redis)
    mine = [e for e in entries if e.get("provider_message_id") == "wamid.read-2"]
    assert len(mine) == 1, "el mensaje se encola igual: solo se suprime el acuse"
    assert "mark_read" not in mine[0]
