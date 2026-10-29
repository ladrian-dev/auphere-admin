"""Spec 049, requirements 5.3, 5.6 and 5.7 — what the cron and the operator do.

- 30 days after a disconnect the channel's people are anonymised, once.
- An operator can erase one person by channel and IGSID / PSID; another
  person, another channel and another tenant are untouched.
- The health tick resubscribes a dropped Page and flags a revoked token.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from nexus_channels.meta_social import MetaSocialClient
from nexus_channels.meta_social.credentials import SocialCredentials
from nexus_worker.streams.meta_social_cron import tick_tenant
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.services.meta_social_retention import ERASED_TEXT

pytestmark = pytest.mark.asyncio

PAGE_ID = "105000000000888"
APP_ID = "957213733862330"


async def _world(db_session, *, disconnected_days: int | None = None) -> dict[str, Any]:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(id=tid, name="Ret", slug=f"ret-{tid.hex[:6]}", plan=TenantPlan.PRO, status=TenantStatus.ACTIVE, owner_phone="+56999990088")
    )
    await db_session.commit()
    cfg: dict[str, Any] = {"name": "Demo Page"}
    status = ChannelStatus.ACTIVE
    if disconnected_days is not None:
        status = ChannelStatus.DISCONNECTED
        cfg["disconnected_at"] = (datetime.now(UTC) - timedelta(days=disconnected_days)).isoformat()
    channel = Channel(
        tenant_id=tid,
        type=ChannelType.MESSENGER,
        provider="meta_messenger",
        provider_identifier=PAGE_ID + tid.hex[:3],
        status=status,
        config=cfg,
        config_encrypted=None if disconnected_days is not None else SocialCredentials(token="SU", page_token="PT").to_payload(),
    )
    db_session.add(channel)
    await db_session.commit()
    people: list[uuid.UUID] = []
    for psid in ("PSID_1", "PSID_2"):
        customer = Customer(tenant_id=tid, identifier=psid, name=f"Name {psid}", preferences={})
        db_session.add(customer)
        await db_session.commit()
        conv = Conversation(tenant_id=tid, channel_id=channel.id, customer_id=customer.id, status=ConversationStatus.OPEN)
        db_session.add(conv)
        await db_session.commit()
        db_session.add(
            Message(
                tenant_id=tid,
                conversation_id=conv.id,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content=f"private text of {psid}",
                tool_calls=[],
            )
        )
        await db_session.commit()
        people.append(customer.id)
    return {"tenant_id": tid, "channel_id": channel.id, "people": people, "page": channel.provider_identifier}


async def _contents(tenant_id: uuid.UUID) -> dict[str, str]:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        rows = await s.execute(
            select(Customer.identifier, Message.content)
            .join(Conversation, Conversation.customer_id == Customer.id)
            .join(Message, Message.conversation_id == Conversation.id)
        )
        return {r[0]: r[1] for r in rows}


def _graph(handler) -> MetaSocialClient:
    return MetaSocialClient("dev-meta-app-secret-change-me", transport=httpx.MockTransport(handler))


async def test_channel_is_anonymised_30_days_after_disconnect(db_session, fake_redis):
    old = await _world(db_session, disconnected_days=31)
    recent = await _world(db_session, disconnected_days=3)
    client = _graph(lambda r: httpx.Response(500))

    await tick_tenant(old["tenant_id"], client=client, redis=fake_redis, app_id=APP_ID)
    await tick_tenant(recent["tenant_id"], client=client, redis=fake_redis, app_id=APP_ID)

    erased = await _contents(old["tenant_id"])
    assert set(erased.values()) == {ERASED_TEXT}
    assert all(identifier.startswith("erased:") for identifier in erased)
    assert set((await _contents(recent["tenant_id"])).values()) == {"private text of PSID_1", "private text of PSID_2"}

    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, old["tenant_id"]):
        channel = await s.get(Channel, old["channel_id"])
        assert channel is not None and channel.config.get("purged_at")
        audits = (await s.execute(select(AuditLog).where(AuditLog.action == "channel.meta_social.purge"))).scalars().all()
        assert len(audits) == 1

    # Once: a second tick changes nothing and writes no second audit row.
    await tick_tenant(old["tenant_id"], client=client, redis=fake_redis, app_id=APP_ID)
    async with sm() as s, tenant_scoped_session(s, old["tenant_id"]):
        audits = (await s.execute(select(AuditLog).where(AuditLog.action == "channel.meta_social.purge"))).scalars().all()
        assert len(audits) == 1


async def test_health_resubscribes_a_dropped_page(db_session, fake_redis):
    world = await _world(db_session)
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})  # Meta dropped us
        return httpx.Response(200, json={"success": True})

    await tick_tenant(world["tenant_id"], client=_graph(handler), redis=fake_redis, app_id=APP_ID)

    assert ("POST", f"/v26.0/{world['page']}/subscribed_apps") in calls
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        channel = await s.get(Channel, world["channel_id"])
        assert channel is not None and channel.status is ChannelStatus.ACTIVE
        assert channel.last_health_check_at is not None


async def test_health_flags_a_revoked_token(db_session, fake_redis):
    world = await _world(db_session)
    revoked = _graph(lambda r: httpx.Response(400, json={"error": {"message": "revoked", "code": 190}}))

    await tick_tenant(world["tenant_id"], client=revoked, redis=fake_redis, app_id=APP_ID)

    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        channel = await s.get(Channel, world["channel_id"])
        assert channel is not None
        assert channel.status is ChannelStatus.DEGRADED
        assert channel.config["needs_attention"] == "token_revoked"


async def test_operator_erases_one_person_only(client, db_session, admin_headers):
    from nexus_api.services import operator_identity

    world = await _world(db_session)
    other = await _world(db_session)
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    headers = {**admin_headers, "X-Operator-Id": str(op.id)}

    r = await client.post(
        f"/admin/tenants/{world['tenant_id']}/channels/{world['channel_id']}/erase-person",
        headers=headers,
        json={"identifier": "PSID_1", "requested_by": "persona@example.com"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["messages_emptied"] == 1
    contents = await _contents(world["tenant_id"])
    assert contents["PSID_2"] == "private text of PSID_2"
    assert [v for k, v in contents.items() if k.startswith("erased:")] == [ERASED_TEXT]
    assert set((await _contents(other["tenant_id"])).values()) == {"private text of PSID_1", "private text of PSID_2"}
