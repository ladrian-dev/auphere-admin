"""Spec 030 T056 — el webhook de estados de Meta avisa a la Bandeja.

Cuando Meta dice que un saliente se entregó, se leyó o falló, la fila sube de
estado y —después del commit— se publica ``message.status`` en el canal del
cliente, sin cuerpo. Un reenvío que no mueve nada (Meta repite y desordena
callbacks) no publica.
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signature import sign_meta_request

from nexus_api.db.models import Channel, Message, MessageDirection, MessageStatus
from nexus_api.services.inbox_stream import inbox_channel
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

META_APP_SECRET = "dev-meta-app-secret-change-me"


def _status_payload(business_phone: str, wamid: str, status: str) -> bytes:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN",
                            },
                            "statuses": [
                                {
                                    "id": wamid,
                                    "status": status,
                                    "timestamp": "1760000000",
                                    "recipient_id": "5491100000000",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode()


async def _post(client, body: bytes):
    return await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )


async def _next(pubsub):
    got = None
    for _ in range(3):
        got = got or await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
    return got


async def test_a_delivery_is_published_once(client, db_session, console_world, fake_redis) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    conv = inbox["conversations"][0]
    phone = (
        await db_session.execute(
            sa.select(Channel.provider_identifier).where(Channel.id == inbox["channel_id"])
        )
    ).scalar_one()
    msg = Message(
        tenant_id=w["tenant_id"],
        conversation_id=conv,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        content="Te confirmo la cita",
        tool_calls=[],
        actor_kind="member",
        provider_message_id="wamid.out-1",
    )
    db_session.add(msg)
    await db_session.commit()
    msg_id = msg.id
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(inbox_channel(w["tenant_id"]))

    r = await _post(client, _status_payload(phone, "wamid.out-1", "delivered"))
    assert r.status_code == 200, r.text
    event = await _next(pubsub)
    assert event is not None
    body = json.loads(event["data"])
    assert body["event"] == "message.status"
    assert body["conversation_id"] == str(conv)
    assert body["message_id"] == str(msg_id)
    assert body["status"] == "delivered"
    assert "Te confirmo" not in event["data"]

    # Un «sent» tardío no mueve un «delivered»: ni cambia ni se publica.
    # (Meta siempre recibe 200: la ruta no le cuenta lo que pasó dentro.)
    r = await _post(client, _status_payload(phone, "wamid.out-1", "sent"))
    assert r.status_code == 200
    assert await _next(pubsub) is None
    assert (
        await db_session.execute(sa.select(Message.status).where(Message.id == msg_id))
    ).scalar_one() == MessageStatus.DELIVERED
