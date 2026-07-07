from __future__ import annotations

import base64
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import get_current_tenant, require_current_tenant
from nexus_api.db.models import AuditLog


@dataclass(frozen=True)
class AuditLogPage:
    items: Sequence[AuditLog]
    next_cursor: str | None  # opaque base64(created_at|id) of the LAST emitted row


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        platform: bool = False,
    ) -> AuditLog:
        """Write one ``audit_log`` row.

        Tenant resolution:

        - Normal case → reads the request-scoped tenant via
          ``get_current_tenant()``; raises if none is set (isolation
          rule: repos never accept tenant_id from the caller).
        - ``platform=True`` → writes with ``tenant_id = NULL`` for
          deliberate platform-level audit (Auphere channel CRUD,
          global skill publish, feature flags). Callers in this mode
          must NOT be inside a tenant_scoped_session.
        """
        if platform:
            resolved = None
        else:
            resolved = get_current_tenant()
            if resolved is None:
                raise ValueError(
                    "AuditRepository.record requires a tenant context; "
                    "pass platform=True only for platform-level audit "
                    "entries"
                )
        entry = AuditLog(
            tenant_id=resolved,
            actor=actor,
            action=action,
            target=target,
            before_json=before,
            after_json=after,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_paginated(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        actor_contains: str | None = None,
        action_eq: str | None = None,
        action_prefix: str | None = None,
        target_contains: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> AuditLogPage:
        """List audit entries newest-first, with optional filters.

        Filters are AND-combined; each is optional. The cursor pattern
        mirrors ``ConversationRepository``: base64-encoded
        ``created_at|id`` of the LAST emitted row so equal timestamps
        don't drop rows. Tenant scoping is automatic via
        ``require_current_tenant``.

        ``action_eq`` is exact match; ``action_prefix`` matches by
        ``LIKE 'connector.%'`` semantics for "all connector events".
        Use either, not both.
        """
        require_current_tenant()
        stmt = select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id))

        if actor_contains:
            stmt = stmt.where(AuditLog.actor.ilike(f"%{actor_contains}%"))
        if action_eq:
            stmt = stmt.where(AuditLog.action == action_eq)
        if action_prefix:
            stmt = stmt.where(AuditLog.action.ilike(f"{action_prefix}%"))
        if target_contains:
            stmt = stmt.where(AuditLog.target.ilike(f"%{target_contains}%"))
        if after is not None:
            stmt = stmt.where(AuditLog.created_at >= after)
        if before is not None:
            stmt = stmt.where(AuditLog.created_at <= before)

        if cursor is not None:
            cursor_dt, cursor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    AuditLog.created_at < cursor_dt,
                    and_(
                        AuditLog.created_at == cursor_dt,
                        AuditLog.id < cursor_id,
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
        return AuditLogPage(items=rows, next_cursor=next_cursor)

    async def distinct_actions(self, *, limit: int = 50) -> list[str]:
        """Return the action names ever used by THIS tenant — powers
        the filter dropdown in the admin UI. Ordered by frequency
        (most common first) so the operator's eyes land on the
        relevant ones immediately."""
        require_current_tenant()
        stmt = (
            select(AuditLog.action, func.count().label("n"))
            .group_by(AuditLog.action)
            .order_by(desc("n"))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]


def _encode_cursor(dt: datetime, row_id: uuid.UUID) -> str:
    raw = f"{dt.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(padded.encode()).decode()
    iso, row_id = raw.split("|", 1)
    return datetime.fromisoformat(iso), uuid.UUID(row_id)
