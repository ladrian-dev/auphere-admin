from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Conversation, Message


@dataclass(frozen=True)
class ConversationPage:
    items: Sequence[Conversation]
    next_cursor: str | None  # opaque ISO-8601 timestamp + id of the last item


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_paginated(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ConversationPage:
        require_current_tenant()
        stmt = select(Conversation).order_by(desc(Conversation.created_at), desc(Conversation.id))

        if cursor is not None:
            cursor_dt, cursor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Conversation.created_at < cursor_dt,
                    and_(
                        Conversation.created_at == cursor_dt,
                        Conversation.id < cursor_id,
                    ),
                )
            )
        stmt = stmt.limit(limit + 1)

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            tail = rows[limit - 1]
            next_cursor = _encode_cursor(tail.created_at, tail.id)
            rows = rows[:limit]
        return ConversationPage(items=rows, next_cursor=next_cursor)

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        require_current_tenant()
        return await self._session.get(Conversation, conversation_id)


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> Sequence[Message]:
        require_current_tenant()
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


def _encode_cursor(dt: datetime, row_id: uuid.UUID) -> str:
    import base64

    raw = f"{dt.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    import base64

    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(padded.encode()).decode()
    iso, row_id = raw.split("|", 1)
    return datetime.fromisoformat(iso), uuid.UUID(row_id)
