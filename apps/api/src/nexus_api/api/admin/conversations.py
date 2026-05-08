from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import ConversationRepository
from nexus_api.schemas.conversation import ConversationOut, ConversationPageOut

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
