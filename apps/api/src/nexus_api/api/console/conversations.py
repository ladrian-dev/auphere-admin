"""``/console/clients/{ref}/conversations`` — **metadata only** (C1 · C8 ·
CP-21).

A partner sees that conversations exist, on which channel, in what state
and with what shape (turns, errors, latency, duration). It never sees a
word of them. This is enforced in the backend, not the UI: these are
distinct routes with distinct response models
(:class:`ConversationMetaOut`) that have no field able to carry a body.
``tests/isolation/test_console_no_message_bodies.py`` walks the OpenAPI
schema of ``/console/*`` and fails if any response model grows one.

Deliberately NOT reusing ``api/admin/conversations.py`` or
``schemas/conversation.py`` — importing a model that has ``content`` is
how a field leaks in a refactor.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query

from nexus_api.db.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)

from .deps import ClientScope, client_scope
from .schemas import ConversationMetaOut, ConversationPageOut, ConversationStatsOut

router = APIRouter(prefix="/clients/{ref}/conversations")


def _agg_columns() -> list[sa.Label[Any]]:
    """Per-conversation aggregates over ``messages`` — counts and timings,
    never a projection of a text column."""
    return [
        sa.func.count(Message.id).label("turns"),
        sa.func.count(Message.id)
        .filter(Message.direction == MessageDirection.INBOUND)
        .label("inbound"),
        sa.func.count(Message.id)
        .filter(Message.direction == MessageDirection.OUTBOUND)
        .label("outbound"),
        sa.func.count(Message.id).filter(Message.status == MessageStatus.FAILED).label("failed"),
        sa.func.avg(Message.latency_ms).label("avg_latency"),
        sa.func.min(Message.created_at).label("first_at"),
        sa.func.max(Message.created_at).label("last_at"),
    ]


@router.get("", response_model=ConversationPageOut)
async def list_conversations(
    scope: ClientScope = Depends(client_scope("conversations:read")),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    escalated: bool | None = Query(default=None),
    with_errors: bool | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationPageOut:
    session = scope.session
    filters: list[sa.ColumnElement[bool]] = []
    if status_filter:
        filters.append(Conversation.status == ConversationStatus(status_filter))
    if escalated is True:
        filters.append(Conversation.status == ConversationStatus.ESCALATED)
    if since is not None:
        filters.append(Conversation.updated_at >= since)

    stats = (
        sa.select(Message.conversation_id.label("cid"), *_agg_columns())
        .group_by(Message.conversation_id)
        .subquery("stats")
    )
    base = (
        sa.select(Conversation, Channel.type.label("channel_type"), stats)
        .outerjoin(stats, stats.c.cid == Conversation.id)
        .outerjoin(Channel, Channel.id == Conversation.channel_id)
        .where(*filters)
    )
    if with_errors is True:
        base = base.where(sa.func.coalesce(stats.c.failed, 0) > 0)

    total = await session.scalar(sa.select(sa.func.count()).select_from(base.subquery()))
    rows = (
        await session.execute(
            base.order_by(Conversation.updated_at.desc(), Conversation.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items: list[ConversationMetaOut] = []
    for row in rows:
        conv: Conversation = row[0]
        first_at, last_at = row.first_at, row.last_at
        duration = int((last_at - first_at).total_seconds()) if first_at and last_at else None
        items.append(
            ConversationMetaOut(
                id=conv.id,
                channel_id=conv.channel_id,
                channel_type=row.channel_type.value if row.channel_type else None,
                status=conv.status.value,
                agent_active=conv.agent_active,
                started_at=conv.created_at,
                last_activity_at=last_at or conv.updated_at,
                turns=int(row.turns or 0),
                inbound_messages=int(row.inbound or 0),
                outbound_messages=int(row.outbound or 0),
                failed_messages=int(row.failed or 0),
                escalated=conv.status is ConversationStatus.ESCALATED,
                avg_latency_ms=int(row.avg_latency) if row.avg_latency is not None else None,
                duration_seconds=duration,
            )
        )
    return ConversationPageOut(items=items, total=int(total or 0), limit=limit, offset=offset)


@router.get("/stats", response_model=ConversationStatsOut)
async def conversation_stats(
    scope: ClientScope = Depends(client_scope("conversations:read")),
    days: int = Query(default=30, ge=1, le=365),
) -> ConversationStatsOut:
    session = scope.session
    until = datetime.now(UTC)
    since = until - timedelta(days=days)
    conv_row = (
        await session.execute(
            sa.select(
                sa.func.count(Conversation.id),
                sa.func.count(Conversation.id).filter(
                    Conversation.status == ConversationStatus.OPEN
                ),
                sa.func.count(Conversation.id).filter(
                    Conversation.status == ConversationStatus.ESCALATED
                ),
                sa.func.count(Conversation.id).filter(
                    Conversation.status == ConversationStatus.CLOSED
                ),
            ).where(Conversation.created_at >= since)
        )
    ).one()
    msg_row = (
        await session.execute(
            sa.select(
                sa.func.count(Message.id),
                sa.func.count(Message.id).filter(Message.status == MessageStatus.FAILED),
                sa.func.avg(Message.latency_ms),
            ).where(Message.created_at >= since)
        )
    ).one()
    return ConversationStatsOut(
        since=since,
        until=until,
        conversations=int(conv_row[0] or 0),
        open=int(conv_row[1] or 0),
        escalated=int(conv_row[2] or 0),
        closed=int(conv_row[3] or 0),
        turns=int(msg_row[0] or 0),
        failed_messages=int(msg_row[1] or 0),
        avg_latency_ms=int(msg_row[2]) if msg_row[2] is not None else None,
    )
