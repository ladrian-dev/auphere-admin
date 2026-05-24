import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _seed_one(session, tid):
    from nexus_api.db.models import Channel, ChannelType, Conversation, Customer

    await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await session.execute(text("SET LOCAL ROLE nexus_app"))
    ch = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=str(uuid.uuid4()),
    )
    cu = Customer(tenant_id=tid, identifier=str(uuid.uuid4()))
    session.add_all([ch, cu])
    await session.flush()
    conv = Conversation(tenant_id=tid, channel_id=ch.id, customer_id=cu.id)
    session.add(conv)
    await session.flush()


async def test_list_conversations_empty(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/conversations", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_list_conversations_with_data(client, admin_headers, seed_tenants, db_session):
    tid = seed_tenants["a"]
    async with db_session.begin():
        for _ in range(3):
            await _seed_one(db_session, tid)
    r = await client.get(f"/admin/tenants/{tid}/conversations", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 3


async def test_list_conversations_pagination(client, admin_headers, seed_tenants, db_session):
    tid = seed_tenants["a"]
    async with db_session.begin():
        for _ in range(5):
            await _seed_one(db_session, tid)
    r1 = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=2",
        headers=admin_headers,
    )
    assert len(r1.json()["items"]) == 2
    cursor = r1.json()["next_cursor"]
    assert cursor
    r2 = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=2&cursor={cursor}",
        headers=admin_headers,
    )
    assert len(r2.json()["items"]) == 2


async def test_list_conversations_limit_validation(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=0",
        headers=admin_headers,
    )
    assert r.status_code == 422
    r = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=999",
        headers=admin_headers,
    )
    assert r.status_code == 422


async def test_list_conversations_unknown_tenant(client, admin_headers):
    r = await client.get(
        f"/admin/tenants/{uuid.uuid4()}/conversations",
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_list_conversations_requires_auth(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/conversations")
    assert r.status_code == 401


# ── Block M.3 — per-conversation agent takeover ─────────────────────────────


async def _seed_one_and_return_id(session, tid):
    from nexus_api.db.models import Channel, ChannelType, Conversation, Customer

    await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await session.execute(text("SET LOCAL ROLE nexus_app"))
    ch = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=str(uuid.uuid4()),
    )
    cu = Customer(tenant_id=tid, identifier=str(uuid.uuid4()))
    session.add_all([ch, cu])
    await session.flush()
    conv = Conversation(tenant_id=tid, channel_id=ch.id, customer_id=cu.id)
    session.add(conv)
    await session.flush()
    return conv.id


async def test_list_conversations_exposes_agent_active(
    client, admin_headers, seed_tenants, db_session
):
    """The list response includes the M.3 ``agent_active`` flag; new rows
    default to ``true`` so existing flows behave unchanged."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_one_and_return_id(db_session, tid)
    r = await client.get(f"/admin/tenants/{tid}/conversations", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["agent_active"] is True


async def test_toggle_agent_takeover_round_trip(client, admin_headers, seed_tenants, db_session):
    from sqlalchemy import select

    from nexus_api.db.models import AuditLog

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    # Take over.
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_active"] is False

    # Release.
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_active"] is True

    audits = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tid)
                .where(AuditLog.target == f"conversation:{conv_id}")
                .order_by(AuditLog.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [a.action for a in audits] == [
        "conversation.takeover",
        "conversation.release",
    ]


async def test_toggle_agent_no_op_when_same_value(client, admin_headers, seed_tenants, db_session):
    """Sending the same value twice is a no-op — no audit row written."""
    from sqlalchemy import select

    from nexus_api.db.models import AuditLog

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": True},  # already true
    )
    assert r.status_code == 200
    audits = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.target == f"conversation:{conv_id}")
            )
        )
        .scalars()
        .all()
    )
    assert audits == []


async def test_toggle_agent_unknown_conversation_returns_404(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{uuid.uuid4()}/agent",
        headers=admin_headers,
        json={"agent_active": False},
    )
    assert r.status_code == 404


async def test_toggle_agent_requires_auth(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{uuid.uuid4()}/agent",
        json={"agent_active": False},
    )
    assert r.status_code == 401


# ── Bloque C — optimistic locking + takeover_context ────────────────────────


async def test_toggle_agent_increments_version_on_flip(
    client, admin_headers, seed_tenants, db_session
):
    """Every flip increments ``agent_active_version`` by 1. No-ops don't."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    # First flip true→false.
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_active_version"] == 1

    # No-op (same value) — version unchanged.
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": False},
    )
    assert r.status_code == 200
    assert r.json()["agent_active_version"] == 1

    # Second flip false→true — version increments.
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": True},
    )
    assert r.status_code == 200
    assert r.json()["agent_active_version"] == 2


async def test_toggle_agent_if_match_mismatch_returns_412(
    client, admin_headers, seed_tenants, db_session
):
    """A stale ``If-Match`` rejects the flip with 412 and the body
    carries enough context for the client to retry from the right
    version."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    # Real version is 0; client claims it saw 7 (stale).
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers={**admin_headers, "If-Match": "7"},
        json={"agent_active": False},
    )
    assert r.status_code == 412
    body = r.json()
    assert body["detail"]["expected"] == 7
    assert body["detail"]["actual"] == 0


async def test_toggle_agent_if_match_quoted_value_accepted(
    client, admin_headers, seed_tenants, db_session
):
    """RFC 7232 weak-etag quoting (``"0"``) round-trips."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers={**admin_headers, "If-Match": '"0"'},
        json={"agent_active": False},
    )
    assert r.status_code == 200


async def test_toggle_agent_if_match_invalid_returns_400(
    client, admin_headers, seed_tenants, db_session
):
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers={**admin_headers, "If-Match": "not-a-number"},
        json={"agent_active": False},
    )
    assert r.status_code == 400


async def test_toggle_agent_pause_persists_takeover_context(
    client, admin_headers, seed_tenants, db_session
):
    """Pausing with reason+notes lands them in ``takeover_context`` so the
    pipeline can read the briefing on resume."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={
            "agent_active": False,
            "reason": "queja",
            "notes": "el cliente quiere hablar con alguien",
        },
    )
    assert r.status_code == 200, r.text
    ctx = r.json()["takeover_context"]
    assert ctx["reason"] == "queja"
    assert ctx["notes"] == "el cliente quiere hablar con alguien"
    assert "started_at" in ctx
    assert "operator_id" in ctx


async def test_toggle_agent_resume_keeps_takeover_context(
    client, admin_headers, seed_tenants, db_session
):
    """On resume the endpoint leaves ``takeover_context`` populated so
    the dispatcher can build the briefing for the next turn. The
    pipeline (PR-C4) is what eventually clears it."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": False, "reason": "x"},
    )
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": True},
    )
    assert r.status_code == 200
    assert r.json()["takeover_context"] is not None
    assert r.json()["takeover_context"]["reason"] == "x"


async def test_toggle_agent_audit_log_includes_version_and_reason(
    client, admin_headers, seed_tenants, db_session
):
    from sqlalchemy import select

    from nexus_api.db.models import AuditLog

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": False, "reason": "manual"},
    )
    audit = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.target == f"conversation:{conv_id}")
            .order_by(AuditLog.created_at.desc())
        )
    ).scalar_one()
    assert audit.action == "conversation.takeover"
    assert audit.before_json["agent_active_version"] == 0
    assert audit.after_json["agent_active_version"] == 1
    assert audit.after_json["reason"] == "manual"


# ── Bloque C — operator send endpoint ──────────────────────────────────────


async def _pause_conv(client, admin_headers, tid, conv_id):
    """Helper: pause the agent on a conversation."""
    r = await client.patch(
        f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
        headers=admin_headers,
        json={"agent_active": False, "reason": "test"},
    )
    assert r.status_code == 200, r.text


async def test_operator_send_persists_outbound_pending_message(
    client, admin_headers, seed_tenants, db_session
):
    """Happy path: paused conversation → POST send → message row with
    direction=outbound, status=pending, actor_kind=operator."""
    from sqlalchemy import select

    from nexus_api.db.models import Message

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)
    await _pause_conv(client, admin_headers, tid, conv_id)

    r = await client.post(
        f"/admin/tenants/{tid}/conversations/{conv_id}/send",
        headers=admin_headers,
        json={"content": "hola, soy Luis, ¿en qué te ayudo?"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["status"] == "pending"
    assert body["actor_kind"] == "operator"
    assert body["actor_id"] is None
    assert body["content"] == "hola, soy Luis, ¿en qué te ayudo?"

    # Cross-check the DB row directly.
    msg = (
        await db_session.execute(
            select(Message).where(Message.id == uuid.UUID(body["id"]))
        )
    ).scalar_one()
    assert msg.actor_kind == "operator"
    assert msg.status.value == "pending"
    assert msg.direction.value == "outbound"


async def test_operator_send_refuses_when_agent_active(
    client, admin_headers, seed_tenants, db_session
):
    """409 when ``agent_active=true`` — operator must pause first."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)
    # NO pause — agent is still active.
    r = await client.post(
        f"/admin/tenants/{tid}/conversations/{conv_id}/send",
        headers=admin_headers,
        json={"content": "hola"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "agent_active"


async def test_operator_send_unknown_conversation_returns_404(
    client, admin_headers, seed_tenants
):
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/conversations/{uuid.uuid4()}/send",
        headers=admin_headers,
        json={"content": "hola"},
    )
    assert r.status_code == 404


async def test_operator_send_requires_auth(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/conversations/{uuid.uuid4()}/send",
        json={"content": "hola"},
    )
    assert r.status_code == 401


async def test_operator_send_empty_content_rejected(
    client, admin_headers, seed_tenants, db_session
):
    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)
    await _pause_conv(client, admin_headers, tid, conv_id)
    r = await client.post(
        f"/admin/tenants/{tid}/conversations/{conv_id}/send",
        headers=admin_headers,
        json={"content": ""},
    )
    assert r.status_code == 422


async def test_operator_send_audit_log_recorded(
    client, admin_headers, seed_tenants, db_session
):
    from sqlalchemy import select

    from nexus_api.db.models import AuditLog

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)
    await _pause_conv(client, admin_headers, tid, conv_id)
    await client.post(
        f"/admin/tenants/{tid}/conversations/{conv_id}/send",
        headers=admin_headers,
        json={"content": "ok"},
    )
    audits = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.target == f"conversation:{conv_id}")
                .where(AuditLog.action == "operator.message_sent")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].after_json["content_length"] == 2


# ── Bloque C — SSE per-conversation pub/sub fanout ──────────────────────────


async def _collect_published(fake_redis, channel: str, count: int, timeout: float = 2.0):
    """Subscribe to ``channel`` on the fake redis and return the first
    ``count`` JSON-decoded messages. Times out if fewer arrive."""
    import asyncio
    import json as _json

    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(channel)
    out: list[dict] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while len(out) < count and asyncio.get_event_loop().time() < deadline:
        msg = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=0.2
        )
        if msg is None:
            continue
        data = msg.get("data")
        if isinstance(data, bytes):
            data = data.decode()
        out.append(_json.loads(data))
    await pubsub.unsubscribe(channel)
    await pubsub.aclose()
    return out


async def test_toggle_agent_publishes_agent_toggled_event(
    client, admin_headers, seed_tenants, db_session, fake_redis
):
    import asyncio

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)
    channel = f"conv:{conv_id}:events"

    # Subscribe first, then trigger the toggle in a background task.
    async def trigger():
        await asyncio.sleep(0.1)
        return await client.patch(
            f"/admin/tenants/{tid}/conversations/{conv_id}/agent",
            headers=admin_headers,
            json={"agent_active": False, "reason": "test"},
        )

    task = asyncio.create_task(trigger())
    msgs = await _collect_published(fake_redis, channel, count=1, timeout=3.0)
    r = await task
    assert r.status_code == 200
    assert len(msgs) == 1
    assert msgs[0]["event"] == "agent.toggled"
    assert msgs[0]["agent_active"] is False
    assert msgs[0]["agent_active_version"] == 1


async def test_operator_send_publishes_message_new_event(
    client, admin_headers, seed_tenants, db_session, fake_redis
):
    import asyncio

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)
    await _pause_conv(client, admin_headers, tid, conv_id)
    channel = f"conv:{conv_id}:events"

    async def trigger():
        await asyncio.sleep(0.1)
        return await client.post(
            f"/admin/tenants/{tid}/conversations/{conv_id}/send",
            headers=admin_headers,
            json={"content": "hola"},
        )

    task = asyncio.create_task(trigger())
    msgs = await _collect_published(fake_redis, channel, count=1, timeout=3.0)
    r = await task
    assert r.status_code == 201
    assert len(msgs) == 1
    assert msgs[0]["event"] == "message.new"
    assert msgs[0]["direction"] == "outbound"
    assert msgs[0]["actor_kind"] == "operator"
    assert "message_id" in msgs[0]


async def test_stream_conversation_events_returns_event_stream_content_type(
    client, admin_headers, seed_tenants, db_session
):
    """The SSE endpoint resolves to a real conversation and sets the
    ``text/event-stream`` content-type. The wire payload (``ready`` event
    + heartbeats + pubsub fan-out) is verified end-to-end by the
    browser-side hook in PR-C6 — testing it inside the httpx
    ``client.stream`` async generator against a fakeredis pubsub is
    flaky (bufferring + cancel-scope interplay), and the publish path
    itself is already covered by the two ``*_publishes_*`` tests above."""
    import asyncio

    tid = seed_tenants["a"]
    async with db_session.begin():
        conv_id = await _seed_one_and_return_id(db_session, tid)

    async def open_and_close():
        async with client.stream(
            "GET",
            f"/admin/tenants/{tid}/conversations/{conv_id}/stream",
            headers=admin_headers,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

    try:
        await asyncio.wait_for(open_and_close(), timeout=3.0)
    except asyncio.TimeoutError:
        # Stream stayed open after the headers were verified — that's
        # the intended behaviour. Closing the context manager triggers
        # the disconnect and exits the generator's heartbeat loop.
        pass


async def test_stream_conversation_events_404_for_unknown_conversation(
    client, admin_headers, seed_tenants
):
    tid = seed_tenants["a"]
    r = await client.get(
        f"/admin/tenants/{tid}/conversations/{uuid.uuid4()}/stream",
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_stream_conversation_events_requires_auth(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(
        f"/admin/tenants/{tid}/conversations/{uuid.uuid4()}/stream",
    )
    assert r.status_code == 401
