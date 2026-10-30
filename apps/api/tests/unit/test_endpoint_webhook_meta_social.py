"""Spec 049 — Instagram and Page events on ``/webhook/meta``.

Requirement 1 in the order it bites: the signature gates everything; the
tenant comes from the connected channel, never from the payload; echoes and
the business's own comments never reach the agent; a redrive is processed
once; an account this environment does not own is forwarded, signed as it
came, and a forwarded delivery is never forwarded again; WhatsApp is
untouched.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

APP_SECRET = "dev-meta-app-secret-change-me"
IG_ID = "17841400000000001"
PAGE_ID = "105000000000001"
IGSID = "530000000000001"


def _dm(
    account: str = IG_ID,
    *,
    obj: str = "instagram",
    mid: str = "m_1",
    text_: str = "hola",
    **msg: Any,
) -> dict[str, Any]:
    return {
        "object": obj,
        "entry": [
            {
                "id": account,
                "time": 1730200000000,
                "messaging": [
                    {
                        "sender": {"id": IGSID},
                        "recipient": {"id": account},
                        "timestamp": 1730200000000,
                        "message": {"mid": mid, "text": text_, **msg},
                    }
                ],
            }
        ],
    }


def _comment(comment_id: str = "C_1", author: str = IGSID) -> dict[str, Any]:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": IG_ID,
                "time": 1730200000,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "from": {"id": author, "username": "maria"},
                            "id": comment_id,
                            "text": "Price?",
                        },
                    }
                ],
            }
        ],
    }


def _signed(payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    return body, {
        "X-Hub-Signature-256": sign_meta_request(APP_SECRET, body),
        "Content-Type": "application/json",
    }


async def _seed(
    db_session,
    tenant_id,
    *,
    provider: str = "meta_instagram",
    identifier: str = IG_ID,
    config: dict | None = None,
) -> None:
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.INSTAGRAM
                if provider == "meta_instagram"
                else ChannelType.MESSENGER,
                provider=provider,
                provider_identifier=identifier,
                status=ChannelStatus.ACTIVE,
                config=config or {"account_id": identifier},
            )
        )


async def _entries(fake_redis) -> list[dict[str, str]]:
    raw = await fake_redis.xrange("nexus:inbound:standard", count=100)
    return [
        {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in f.items()
        }
        for _id, f in raw
    ]


@pytest.fixture
def no_peer(monkeypatch):
    from nexus_api.config import get_settings

    monkeypatch.setattr(get_settings(), "meta_webhook_peer_url", "", raising=False)
    monkeypatch.setattr(get_settings(), "environment", "test", raising=False)


@pytest.fixture
def peer(monkeypatch):
    """Capture forwards instead of calling the other environment."""
    from nexus_api.api.webhooks import meta_social
    from nexus_api.config import get_settings

    monkeypatch.setattr(
        get_settings(), "meta_webhook_peer_url", "https://peer.example/webhook/meta", raising=False
    )
    sent: list[dict[str, Any]] = []

    class _Resp:
        status_code = 200

    class _Client:
        async def post(self, url, *, content, headers):
            sent.append({"url": url, "content": content, "headers": headers})
            return _Resp()

    monkeypatch.setattr(meta_social, "_client", lambda: _Client())
    return sent


async def test_unsigned_instagram_event_is_rejected(client):
    r = await client.post("/webhook/meta", content=json.dumps(_dm()).encode())
    assert r.status_code == 401


async def test_instagram_dm_is_enqueued_for_the_channel_owner(
    client, db_session, fake_redis, seed_tenants, no_peer
):
    tenant_id = seed_tenants["a"]
    await _seed(db_session, tenant_id)
    body, headers = _signed(_dm(mid="m_enq"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    [entry] = [e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_enq"]
    assert entry["tenant_id"] == str(tenant_id)
    assert entry["provider"] == "meta_instagram"
    assert entry["user_id"] == IGSID
    assert entry["content"] == "hola"
    assert "mark_read" not in entry


async def test_messenger_dm_is_enqueued(client, db_session, fake_redis, seed_tenants, no_peer):
    tenant_id = seed_tenants["a"]
    await _seed(db_session, tenant_id, provider="meta_messenger", identifier=PAGE_ID)
    body, headers = _signed(_dm(PAGE_ID, obj="page", mid="m_page"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.json()["status"] == "ok"
    [entry] = [e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_page"]
    assert entry["provider"] == "meta_messenger"


async def test_echo_is_not_a_turn(client, db_session, fake_redis, seed_tenants, no_peer):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_dm(mid="m_echo", is_echo=True))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.json()["status"] == "ignored"
    assert not [e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_echo"]


async def test_redrive_is_processed_once(client, db_session, fake_redis, seed_tenants, no_peer):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_dm(mid="m_dupe"))

    await client.post("/webhook/meta", content=body, headers=headers)
    second = await client.post("/webhook/meta", content=body, headers=headers)

    assert second.json()["status"] == "ignored"
    assert (
        len([e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_dupe"])
        == 1
    )


async def test_a_failed_enqueue_lets_metas_retry_through(
    client, db_session, fake_redis, seed_tenants, no_peer, monkeypatch
):
    """QA 2026-10-30 (INC-17): the dedupe mark was set before enqueueing and
    never released, so Meta's retry after a failure was dropped for 48 h."""
    from nexus_api.api.webhooks import meta_social as route

    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_dm(mid="m_retry"))
    real = route.xadd_capped

    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("redis stream down")

    monkeypatch.setattr(route, "xadd_capped", boom)
    with pytest.raises(RuntimeError):
        await client.post("/webhook/meta", content=body, headers=headers)
    assert await fake_redis.get("nexus:msocial:meta_instagram:m_retry") is None

    monkeypatch.setattr(route, "xadd_capped", real)
    again = await client.post("/webhook/meta", content=body, headers=headers)
    assert again.json()["status"] == "ok"
    assert [e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_retry"]


async def test_comment_carries_its_reference(client, db_session, fake_redis, seed_tenants, no_peer):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_comment("C_enq"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.json()["status"] == "ok"
    [entry] = [
        e for e in await _entries(fake_redis) if e.get("provider_message_id") == "comment:C_enq"
    ]
    assert entry["context_message_id"] == "comment:C_enq"
    assert entry["customer_name"] == "maria"


async def test_business_own_comment_and_disabled_comments(
    client, db_session, fake_redis, seed_tenants, no_peer
):
    await _seed(db_session, seed_tenants["a"], config={"comments_enabled": False})
    own, h1 = _signed(_comment("C_own", author=IG_ID))
    other, h2 = _signed(_comment("C_off"))

    assert (await client.post("/webhook/meta", content=own, headers=h1)).json()[
        "status"
    ] == "ignored"
    assert (await client.post("/webhook/meta", content=other, headers=h2)).json()[
        "status"
    ] == "ignored"
    assert not [
        e
        for e in await _entries(fake_redis)
        if e.get("provider_message_id", "").startswith("comment:C_")
    ]


async def test_foreign_account_is_forwarded_with_its_signature(
    client, fake_redis, seed_tenants, peer
):
    body, headers = _signed(_dm("99999999", mid="m_foreign"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["forwarded"] is True
    [fwd] = peer
    assert fwd["content"] == body
    assert fwd["headers"]["X-Hub-Signature-256"] == headers["X-Hub-Signature-256"]
    assert fwd["headers"]["X-Auphere-Forwarded"] == "1"
    assert not [
        e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_foreign"
    ]


async def test_forwarded_delivery_is_never_forwarded_again(client, fake_redis, seed_tenants, peer):
    body, headers = _signed(_dm("99999999", mid="m_loop"))

    r = await client.post(
        "/webhook/meta", content=body, headers={**headers, "X-Auphere-Forwarded": "1"}
    )

    assert r.status_code == 200
    assert r.json()["forwarded"] is False
    assert peer == []


async def test_forwarded_delivery_for_an_owned_account_is_processed(
    client, db_session, fake_redis, seed_tenants, peer
):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_dm(mid="m_from_peer"))

    r = await client.post(
        "/webhook/meta", content=body, headers={**headers, "X-Auphere-Forwarded": "1"}
    )

    assert r.json()["status"] == "ok"
    assert peer == []


async def test_other_tenant_never_receives_the_event(
    client, db_session, fake_redis, seed_tenants, no_peer
):
    """Garantía 1: the owner of the IG account is the only tenant stamped."""
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_dm(mid="m_iso"))

    await client.post("/webhook/meta", content=body, headers=headers)

    [entry] = [e for e in await _entries(fake_redis) if e.get("provider_message_id") == "m_iso"]
    assert entry["tenant_id"] == str(seed_tenants["a"])
    assert entry["tenant_id"] != str(seed_tenants["b"])
