from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from nexus_api.api.deps import get_redis, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AuditLog,
    Channel,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.repositories import ConversationRepository, MessageRepository
from nexus_api.schemas.conversation import (
    ConversationAgentToggleIn,
    ConversationOut,
    ConversationPageOut,
    MessageOut,
    OperatorSendIn,
)
from nexus_api.services.conversation_stream import (
    conversation_channel,
    publish_conversation_event,
)

router = APIRouter()
log = structlog.get_logger()


@router.get(
    "/tenants/{tenant_id}/conversations",
    response_model=ConversationPageOut,
    dependencies=[Depends(require_admin_token)],
)
async def list_conversations(
    tenant_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> ConversationPageOut:
    repo = ConversationRepository(session)
    page = await repo.list_paginated(limit=limit, cursor=cursor)
    providers = await _provider_map(session, [c.channel_id for c in page.items])
    items: list[ConversationOut] = []
    for c in page.items:
        out = ConversationOut.model_validate(c)
        out.provider = providers.get(c.channel_id)
        items.append(out)
    return ConversationPageOut(items=items, next_cursor=page.next_cursor)


async def _provider_map(
    session: AsyncSession, channel_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Resolve ``channel_id -> provider`` for a page of conversations in a
    single query. RLS-scoped via the request session, so it only ever sees
    the active tenant's channels."""
    if not channel_ids:
        return {}
    rows = await session.execute(
        select(Channel.id, Channel.provider).where(Channel.id.in_(set(channel_ids)))
    )
    return {cid: provider for cid, provider in rows}


@router.get(
    "/tenants/{tenant_id}/conversations/{conversation_id}",
    response_model=ConversationOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_conversation(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> ConversationOut:
    """Block M.3 — detail of a single conversation. Used by the detail
    view to render the takeover control alongside the message history."""
    conv = await ConversationRepository(session).get(conversation_id)
    if conv is None or conv.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conversation {conversation_id} not found",
        )
    out = ConversationOut.model_validate(conv)
    out.provider = (await _provider_map(session, [conv.channel_id])).get(conv.channel_id)
    return out


@router.get(
    "/tenants/{tenant_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_conversation_messages(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> list[MessageOut]:
    """Block M.3 — chronological message history for the detail view."""
    conv = await ConversationRepository(session).get(conversation_id)
    if conv is None or conv.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conversation {conversation_id} not found",
        )
    messages = await MessageRepository(session).list_for_conversation(conversation_id)
    return [MessageOut.model_validate(m) for m in messages]


@router.patch(
    "/tenants/{tenant_id}/conversations/{conversation_id}/agent",
    response_model=ConversationOut,
)
async def toggle_conversation_agent(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: ConversationAgentToggleIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> ConversationOut:
    """Block M.3 + Bloque C — toggle per-conversation agent control with
    optimistic locking.

    ``agent_active=false`` puts the operator in the loop: the dispatcher
    still persists inbound messages on this thread but does NOT invoke
    the pipeline. The operator answers manually (via the ``POST
    .../conversations/:id/send`` endpoint or, transitionally, an external
    WhatsApp client) until they flip ``agent_active=true`` again.

    Resuming the agent does NOT trigger a backlog reply — only the next
    inbound turn is processed. That turn carries a "what the human did
    while you were paused" briefing built from ``takeover_context`` + the
    operator-authored messages, so the LLM picks up the thread without
    re-greeting or re-asking what was already resolved.

    ``If-Match`` (optional) carries the ``agent_active_version`` value
    the client last saw. If it mismatches the current row, returns 412
    — two operators racing on the same conversation can't silently
    clobber each other. Back-compat: when the header is omitted, the
    flip proceeds without the check (older UI builds).
    """
    repo = ConversationRepository(session)
    conv = await repo.get(conversation_id)
    if conv is None or conv.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conversation {conversation_id} not found",
        )
    if conv.agent_active == body.agent_active:
        # No-op — return current state without auditing the noise.
        # Skip the version check too: if the caller's expectation matches
        # reality the answer is already correct.
        return ConversationOut.model_validate(conv)

    if if_match is not None:
        try:
            expected_version = int(if_match.strip().strip('"'))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="If-Match must be an integer version",
            )
        if expected_version != conv.agent_active_version:
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail={
                    "error": "version_mismatch",
                    "expected": expected_version,
                    "actual": conv.agent_active_version,
                },
            )

    before_active = conv.agent_active
    before_version = conv.agent_active_version
    conv.agent_active = body.agent_active
    conv.agent_active_version = before_version + 1

    if body.agent_active is False:
        # Pause — capture the operator's reason for the LLM to read on
        # resume. ``operator_id`` is the token prefix (matches the
        # audit-log convention) so the panel can show "Luis pausó esto
        # hace 5 min".
        conv.takeover_context = {
            "reason": body.reason,
            "notes": body.notes,
            "started_at": datetime.now(UTC).isoformat(),
            "operator_id": actor[:8],
        }
    # On resume we LEAVE ``takeover_context`` set — the dispatcher consumes
    # it on the first turn post-resume and clears it itself. If we cleared
    # it here the LLM would never see the briefing.

    action = "conversation.release" if body.agent_active else "conversation.takeover"
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action=action,
            target=f"conversation:{conversation_id}",
            before_json={
                "agent_active": before_active,
                "agent_active_version": before_version,
            },
            after_json={
                "agent_active": body.agent_active,
                "agent_active_version": conv.agent_active_version,
                "reason": body.reason,
                "notes": body.notes,
            },
        )
    )
    await session.flush()
    await session.refresh(conv)
    # Bloque C — broadcast the toggle so any open conversation detail
    # page updates the takeover banner without a hard refresh.
    await publish_conversation_event(
        redis,
        conversation_id=conversation_id,
        event="agent.toggled",
        payload={
            "agent_active": conv.agent_active,
            "agent_active_version": conv.agent_active_version,
        },
    )
    return ConversationOut.model_validate(conv)


@router.post(
    "/tenants/{tenant_id}/conversations/{conversation_id}/send",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def operator_send_message(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: OperatorSendIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
) -> MessageOut:
    """Bloque C — operator sends a free-form text reply on a paused
    conversation.

    The endpoint:

    1. Loads the conversation (404 if missing / wrong tenant).
    2. Refuses when ``agent_active`` is true with 409 — the operator
       must explicitly pause via ``PATCH .../agent`` before sending so
       the agent and the human can't write the same turn simultaneously.
    3. Persists ``Message`` with ``direction='outbound'``,
       ``status='pending'``, ``actor_kind='operator'``, ``actor_id``
       left NULL (admin auth is token-based, no stable user uuid yet).
    4. Records an ``operator.message_sent`` audit row so the timeline
       view shows who said what.

    The outbound dispatcher tick (``apps/worker/.../streams/outbound.py``)
    picks the row up on its next pass and ships it through the channel
    adapter exactly like an agent-generated reply, so delivery /
    failure callbacks (Meta status webhook) update the same row.
    """
    repo = ConversationRepository(session)
    conv = await repo.get(conversation_id)
    if conv is None or conv.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conversation {conversation_id} not found",
        )
    if conv.agent_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "agent_active",
                "message": (
                    "Pause the agent (PATCH .../agent agent_active=false) "
                    "before sending as the operator."
                ),
            },
        )

    msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=body.content,
        tool_calls=[],
        actor_kind="operator",
        actor_id=None,
    )
    session.add(msg)
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action="operator.message_sent",
            target=f"conversation:{conversation_id}",
            before_json=None,
            after_json={"message_id": None, "content_length": len(body.content)},
        )
    )
    await session.flush()
    await session.refresh(msg)
    await publish_conversation_event(
        redis,
        conversation_id=conversation_id,
        event="message.new",
        payload={
            "message_id": str(msg.id),
            "direction": "outbound",
            "actor_kind": "operator",
        },
    )
    return MessageOut.model_validate(msg)


@router.get(
    "/tenants/{tenant_id}/conversations/{conversation_id}/stream",
    dependencies=[Depends(require_admin_token)],
)
async def stream_conversation_events(
    request: Request,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
) -> EventSourceResponse:
    """Bloque C — per-conversation live event stream.

    The admin operator panel opens this SSE on the conversation detail
    view. Producers publish to the ``conv:{id}:events`` Redis pub/sub
    channel; we subscribe and re-emit each message as an SSE event.
    A 15-second heartbeat keeps intermediate proxies (Vercel, Cloudflare)
    from killing the connection on idle.

    Authorization: the path tenant check (404 if the conversation
    doesn't belong to ``tenant_id``) runs once at subscribe time, then
    the channel is name-scoped to the conversation UUID for the duration
    of the stream.
    """
    conv = await ConversationRepository(session).get(conversation_id)
    if conv is None or conv.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"conversation {conversation_id} not found",
        )

    channel = conversation_channel(conversation_id)

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        # Tell the browser the stream is live before the first heartbeat
        # so EventSource.onopen fires without a 15s wait.
        yield {"event": "ready", "data": str(conversation_id)}
        try:
            while True:
                if await request.is_disconnected():
                    log.info(
                        "conversation_stream.disconnected",
                        conversation_id=str(conversation_id),
                    )
                    break
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if msg is None:
                    yield {"event": "heartbeat", "data": "ping"}
                    continue
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode()
                try:
                    parsed = json.loads(data) if data else {}
                except json.JSONDecodeError:
                    continue
                event_name = parsed.get("event") or "message"
                yield {"event": event_name, "data": json.dumps(parsed)}
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass

    return EventSourceResponse(event_gen())


@router.get(
    "/tenants/{tenant_id}/conversations/stream",
    dependencies=[Depends(require_admin_token)],
)
async def stream_conversations(
    request: Request,
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> EventSourceResponse:
    """SSE stream of conversation IDs for live tailing.

    Block B emits a heartbeat every few seconds plus the current snapshot once.
    Block C/F replace the polling with a Redis pubsub fed by the agent runtime;
    the wire format stays identical so the panel doesn't change.
    """

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        # M.4 — emit a ``ready`` event before the first DB read so the
        # browser's ``EventSource.onopen`` fires immediately and the
        # LiveIndicator flips to "En vivo" without waiting on the
        # 15-second heartbeat loop (this is what kept the indicator
        # stuck in "CONECTANDO…" for tenants with zero conversations:
        # no events would flow through Vercel's buffer until the first
        # heartbeat, by which time the 4-second client-side fallback
        # had already degraded the badge to "polling").
        yield {"event": "ready", "data": str(tenant_id)}

        repo = ConversationRepository(session)
        page = await repo.list_paginated(limit=20)
        for conv in page.items:
            yield {"event": "conversation", "data": str(conv.id)}
        while True:
            if await request.is_disconnected():
                log.info("sse.disconnected", tenant_id=str(tenant_id))
                break
            yield {"event": "heartbeat", "data": "ping"}
            await asyncio.sleep(15)

    return EventSourceResponse(event_gen())
