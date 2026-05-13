from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog
from nexus_api.repositories import ConversationRepository, MessageRepository
from nexus_api.schemas.conversation import (
    ConversationAgentToggleIn,
    ConversationOut,
    ConversationPageOut,
    MessageOut,
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
    return ConversationPageOut(
        items=[ConversationOut.model_validate(c) for c in page.items],
        next_cursor=page.next_cursor,
    )


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
    return ConversationOut.model_validate(conv)


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
    actor: str = Depends(require_admin_token),
) -> ConversationOut:
    """Block M.3 — toggle per-conversation agent control.

    ``agent_active=false`` puts the operator in the loop: the dispatcher
    still persists inbound messages on this thread but does NOT invoke
    the pipeline. The operator answers manually (currently via an
    external WhatsApp client; M.5+ may surface composing inline) until
    they flip ``agent_active=true`` again.

    Resuming the agent does NOT trigger a backlog reply — only the next
    inbound turn is processed. This avoids surprise floods after a
    multi-hour takeover.
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
        return ConversationOut.model_validate(conv)

    before = conv.agent_active
    conv.agent_active = body.agent_active
    action = "conversation.release" if body.agent_active else "conversation.takeover"
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action=action,
            target=f"conversation:{conversation_id}",
            before_json={"agent_active": before},
            after_json={"agent_active": body.agent_active},
        )
    )
    await session.flush()
    await session.refresh(conv)
    return ConversationOut.model_validate(conv)


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
