"""Public web chat widget surface ``/v1/widget/*`` E2E (migration 0050).

Everything is real: the ``public_key`` → tenant resolution, origin
allow-list enforcement, session JWT mint/verify, the ``nexus:inbound``
enqueue (fakeredis), lazy web-channel creation, and the RLS-scoped poll.
The agent pipeline itself is not exercised — the poll test inserts an
outbound row directly to stand in for the worker's reply.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core.widget_jwt import mint_widget_session_token
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
    TenantWidgetConfig,
)

pytestmark = pytest.mark.asyncio

_ORIGIN = "https://shop.test"
_PUBLIC_KEY = "wgt_pub_testkey123"


async def _set_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(sa.text("SET LOCAL ROLE nexus_app"))


@pytest_asyncio.fixture
async def world(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(id=tenant_id, name="Shop", slug=f"shop-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    db_session.add(
        TenantWidgetConfig(
            tenant_id=tenant_id,
            public_key=_PUBLIC_KEY,
            allowed_origins=[_ORIGIN],
            greeting="¡Hola! ¿En qué te ayudo?",
            appearance={"title": "Ventas", "accent_color": "#0a0"},
            enabled=True,
        )
    )
    await db_session.commit()
    return {"tenant_id": tenant_id}


def _token(tenant_id: uuid.UUID, session_id: str, origin: str = _ORIGIN) -> str:
    token, _jti, _exp = mint_widget_session_token(
        tenant_id=tenant_id, session_id=session_id, origin=origin
    )
    return token


# ── loader ────────────────────────────────────────────────────────────────────


async def test_widget_loader_is_served(client) -> None:
    resp = await client.get("/widget.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert "data-public-key" in resp.text


# ── session mint ────────────────────────────────────────────────────────────


async def test_session_mint_ok(client, world) -> None:
    resp = await client.post(
        "/v1/widget/session",
        json={"public_key": _PUBLIC_KEY},
        headers={"Origin": _ORIGIN},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_token"]
    assert body["session_id"]
    assert body["config"]["greeting"] == "¡Hola! ¿En qué te ayudo?"
    assert body["config"]["appearance"]["accent_color"] == "#0a0"


async def test_session_mint_echoes_returning_session_id(client, world) -> None:
    resp = await client.post(
        "/v1/widget/session",
        json={"public_key": _PUBLIC_KEY, "session_id": "returning0001"},
        headers={"Origin": _ORIGIN},
    )
    assert resp.status_code == 201
    assert resp.json()["session_id"] == "returning0001"


async def test_session_mint_unknown_key_is_403(client, world) -> None:
    resp = await client.post(
        "/v1/widget/session",
        json={"public_key": "wgt_pub_nope"},
        headers={"Origin": _ORIGIN},
    )
    assert resp.status_code == 403


async def test_session_mint_forbidden_origin_is_403(client, world) -> None:
    resp = await client.post(
        "/v1/widget/session",
        json={"public_key": _PUBLIC_KEY},
        headers={"Origin": "https://evil.test"},
    )
    assert resp.status_code == 403


async def test_session_mint_disabled_widget_is_403(client, world, db_session) -> None:
    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(
            sa.update(TenantWidgetConfig)
            .where(TenantWidgetConfig.tenant_id == world["tenant_id"])
            .values(enabled=False)
        )
    resp = await client.post(
        "/v1/widget/session",
        json={"public_key": _PUBLIC_KEY},
        headers={"Origin": _ORIGIN},
    )
    assert resp.status_code == 403


# ── message send (enqueue) ────────────────────────────────────────────────────


async def test_send_message_enqueues_and_creates_channel(
    client, world, db_session, fake_redis
) -> None:
    token = _token(world["tenant_id"], "sess-aaa")
    resp = await client.post(
        "/v1/widget/messages",
        json={"content": "busco cinta para prótesis"},
        headers={"Authorization": f"Bearer {token}", "Origin": _ORIGIN},
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "enqueued"}

    # Enqueued onto the shared inbound stream with the web_widget provider.
    entries = await fake_redis.xrange("nexus:inbound")
    assert len(entries) == 1
    _id, fields = entries[0]
    assert fields["provider"] == "web_widget"
    assert fields["user_id"] == "sess-aaa"
    assert fields["content"] == "busco cinta para prótesis"

    # The web channel was created lazily under tenant scope.
    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        channel = (
            await db_session.execute(sa.select(Channel).where(Channel.provider == "web_widget"))
        ).scalar_one()
        assert channel.type == ChannelType.WEB
        assert fields["channel_id"] == str(channel.id)


async def test_send_message_missing_token_is_401(client, world) -> None:
    resp = await client.post(
        "/v1/widget/messages",
        json={"content": "hola"},
        headers={"Origin": _ORIGIN},
    )
    assert resp.status_code == 401


async def test_send_message_origin_mismatch_is_403(client, world) -> None:
    # Token minted for _ORIGIN but request arrives from another site.
    token = _token(world["tenant_id"], "sess-bbb")
    resp = await client.post(
        "/v1/widget/messages",
        json={"content": "hola"},
        headers={"Authorization": f"Bearer {token}", "Origin": "https://evil.test"},
    )
    assert resp.status_code == 403


async def test_expired_token_is_401(client, world, monkeypatch) -> None:
    # Freeze mint far in the past so the 900s TTL is already blown.
    token = _token(world["tenant_id"], "sess-ccc")
    # Rebuild an expired token by hand via the same secret path.
    import jwt as _jwt

    from nexus_api.config import get_settings

    now = datetime.now(UTC) - timedelta(hours=1)
    expired = _jwt.encode(
        {
            "tenant_id": str(world["tenant_id"]),
            "session_id": "sess-ccc",
            "origin": _ORIGIN,
            "scope": "widget:chat",
            "aud": "auphere:web-widget",
            "iat": now,
            "exp": now + timedelta(seconds=1),
            "jti": uuid.uuid4().hex,
        },
        get_settings().embed_jwt_secret,
        algorithm="HS256",
    )
    assert token  # sanity: a fresh token exists
    resp = await client.post(
        "/v1/widget/messages",
        json={"content": "hola"},
        headers={"Authorization": f"Bearer {expired}", "Origin": _ORIGIN},
    )
    assert resp.status_code == 401


# ── poll ──────────────────────────────────────────────────────────────────────


async def test_poll_empty_before_any_conversation(client, world) -> None:
    token = _token(world["tenant_id"], "sess-ddd")
    resp = await client.get(
        "/v1/widget/messages",
        headers={"Authorization": f"Bearer {token}", "Origin": _ORIGIN},
    )
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


async def test_poll_returns_agent_reply(client, world, db_session) -> None:
    tenant_id = world["tenant_id"]
    session_id = "sess-eee"

    # Stand in for the worker: create the web channel + this session's
    # customer/conversation + an outbound (SENT) agent reply.
    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, tenant_id)
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WEB,
            provider="web_widget",
            provider_identifier=f"web_widget:{tenant_id}",
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(channel)
        await db_session.flush()
        customer = Customer(tenant_id=tenant_id, identifier=session_id)
        db_session.add(customer)
        await db_session.flush()
        conv = Conversation(tenant_id=tenant_id, channel_id=channel.id, customer_id=customer.id)
        db_session.add(conv)
        await db_session.flush()
        db_session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.SENT,
                content="Tenemos la *Walker Ultra Hold* a *$19.990*.",
                actor_kind="agent",
            )
        )

    token = _token(tenant_id, session_id)
    resp = await client.get(
        "/v1/widget/messages",
        headers={"Authorization": f"Bearer {token}", "Origin": _ORIGIN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["messages"]) == 1
    assert body["messages"][0]["direction"] == "outbound"
    assert "Walker Ultra Hold" in body["messages"][0]["content"]
    assert body["server_time"]

    # A ``since`` at/after the reply returns nothing new. Pass via params so
    # httpx URL-encodes the ``+`` in the ISO offset (the widget.js loader
    # uses encodeURIComponent for the same reason).
    future = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    resp2 = await client.get(
        "/v1/widget/messages",
        params={"since": future},
        headers={"Authorization": f"Bearer {token}", "Origin": _ORIGIN},
    )
    assert resp2.status_code == 200
    assert resp2.json()["messages"] == []
