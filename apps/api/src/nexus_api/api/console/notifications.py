"""``/console/notifications`` — the partner's in-app notification centre
(CP-29; table from migration 0086).

Visible to a member: every notification of their partner addressed to
everyone (``recipient_user_id IS NULL``) or to them. Read state:
``read_at`` on the row when it is personal, one
``console_notification_reads`` row per user when it is broadcast. A
client is referenced by ``external_client_ref`` (never a tenant id).

Cursor paging on ``(created_at, id)`` — newest first.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import ConsoleNotification, ConsoleNotificationRead

from .schemas_onboarding import NotificationOut, NotificationPageOut, ReadAllOut, UnreadCountOut

router = APIRouter(prefix="/notifications")

NotificationId = Path(..., description="Notification id")


def _visible(principal: ConsolePrincipal) -> sa.ColumnElement[bool]:
    return sa.and_(
        ConsoleNotification.partner_id == principal.partner.id,
        sa.or_(
            ConsoleNotification.recipient_user_id.is_(None),
            ConsoleNotification.recipient_user_id == principal.user_id,
        ),
    )


def _read_expr(user_id: str) -> sa.ColumnElement[bool]:
    """``read`` = personal row marked, or a per-user read row exists."""
    exists = (
        sa.select(sa.literal(1))
        .select_from(ConsoleNotificationRead)
        .where(
            ConsoleNotificationRead.notification_id == ConsoleNotification.id,
            ConsoleNotificationRead.user_id == user_id,
        )
        .exists()
    )
    return sa.or_(ConsoleNotification.read_at.is_not(None), exists)


def _encode_cursor(created_at: datetime, id_: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{id_}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        text = base64.urlsafe_b64decode(padded.encode()).decode()
        ts, id_ = text.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bad cursor"
        ) from None


async def _unread_count(session: AsyncSession, principal: ConsolePrincipal) -> int:
    value = await session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(_visible(principal), sa.not_(_read_expr(principal.user_id)))
    )
    return int(value or 0)


@router.get("", response_model=NotificationPageOut)
async def list_notifications(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
    unread: bool | None = Query(default=None, description="Only unread (true) / only read (false)"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
) -> NotificationPageOut:
    read_expr = _read_expr(principal.user_id)
    stmt = (
        sa.select(ConsoleNotification, read_expr.label("is_read"))
        .where(_visible(principal))
        .order_by(ConsoleNotification.created_at.desc(), ConsoleNotification.id.desc())
        .limit(limit + 1)
    )
    if unread is True:
        stmt = stmt.where(sa.not_(read_expr))
    elif unread is False:
        stmt = stmt.where(read_expr)
    if cursor:
        c_at, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            sa.or_(
                ConsoleNotification.created_at < c_at,
                sa.and_(ConsoleNotification.created_at == c_at, ConsoleNotification.id < c_id),
            )
        )
    async with session.begin():
        rows = (await session.execute(stmt)).all()
        page = rows[:limit]
        unread_total = await _unread_count(session, principal)
    items = [
        NotificationOut(
            id=n.id,
            kind=n.kind,
            severity=n.severity,
            data=dict(n.payload or {}),
            external_client_ref=n.external_client_ref,
            read=bool(is_read),
            created_at=n.created_at,
        )
        for n, is_read in page
    ]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1][0]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return NotificationPageOut(items=items, next_cursor=next_cursor, unread=unread_total)


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> UnreadCountOut:
    async with session.begin():
        return UnreadCountOut(unread=await _unread_count(session, principal))


@router.post("/read-all", response_model=ReadAllOut)
async def read_all(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> ReadAllOut:
    now = datetime.now(UTC)
    async with session.begin():
        unread_rows = (
            await session.execute(
                sa.select(ConsoleNotification.id, ConsoleNotification.recipient_user_id).where(
                    _visible(principal), sa.not_(_read_expr(principal.user_id))
                )
            )
        ).all()
        personal = [nid for nid, rcpt in unread_rows if rcpt is not None]
        broadcast = [nid for nid, rcpt in unread_rows if rcpt is None]
        if personal:
            await session.execute(
                sa.update(ConsoleNotification)
                .where(ConsoleNotification.id.in_(personal))
                .values(read_at=now)
            )
        for nid in broadcast:
            session.add(
                ConsoleNotificationRead(notification_id=nid, user_id=principal.user_id, read_at=now)
            )
        await session.flush()
    return ReadAllOut(marked=len(unread_rows))


@router.post(
    "/{notification_id}/read",
    response_model=NotificationOut,
    responses={404: {"description": "Not one of yours."}},
)
async def mark_read(
    notification_id: uuid.UUID = NotificationId,
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> NotificationOut:
    async with session.begin():
        row = await session.scalar(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.id == notification_id, _visible(principal)
            )
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown notification"
            )
        now = datetime.now(UTC)
        if row.recipient_user_id is not None:
            if row.read_at is None:
                row.read_at = now
        else:
            existing = await session.get(ConsoleNotificationRead, (row.id, principal.user_id))
            if existing is None:
                session.add(
                    ConsoleNotificationRead(
                        notification_id=row.id, user_id=principal.user_id, read_at=now
                    )
                )
        await session.flush()
        out = NotificationOut(
            id=row.id,
            kind=row.kind,
            severity=row.severity,
            data=dict(row.payload or {}),
            external_client_ref=row.external_client_ref,
            read=True,
            created_at=row.created_at,
        )
    return out


__all__ = ["router"]
