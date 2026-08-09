"""Admin endpoint that surfaces the per-tenant audit log (Bloque B4).

Reads ``audit_log`` filtered by tenant (RLS-scoped via
``ro_scoped_session_from_path``) with optional filters on actor, action,
target and a date range. Cursor-based pagination so a tenant with
10k+ rows pages cheaply without OFFSET cost.

The companion ``GET .../audit-log/actions`` returns the distinct
action names this tenant has ever produced — the admin uses it to
populate a select filter without hardcoding the catalog of action
strings (which grows as new endpoints add audit calls).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import ro_scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.repositories.audit import AuditRepository
from nexus_api.schemas.audit import AuditLogOut, AuditLogPageOut

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/audit-log",
    response_model=AuditLogPageOut,
    dependencies=[Depends(require_admin_token)],
)
async def list_audit_log(
    tenant_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    actor: str | None = Query(default=None, description="Substring match (case-insensitive)"),
    action: str | None = Query(
        default=None,
        description="Exact action name. Mutually exclusive with action_prefix.",
    ),
    action_prefix: str | None = Query(
        default=None,
        description="Prefix LIKE — e.g. 'connector.' for all connector events.",
    ),
    target: str | None = Query(default=None, description="Substring match (case-insensitive)"),
    after: datetime | None = Query(
        default=None, description="Only entries with created_at >= this timestamp."
    ),
    before: datetime | None = Query(
        default=None, description="Only entries with created_at <= this timestamp."
    ),
    session: AsyncSession = Depends(ro_scoped_session_from_path),
) -> AuditLogPageOut:
    repo = AuditRepository(session)
    page = await repo.list_paginated(
        limit=limit,
        cursor=cursor,
        actor_contains=actor,
        action_eq=action,
        action_prefix=action_prefix,
        target_contains=target,
        after=after,
        before=before,
    )
    return AuditLogPageOut(
        items=[AuditLogOut.model_validate(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/tenants/{tenant_id}/audit-log/actions",
    response_model=list[str],
    dependencies=[Depends(require_admin_token)],
)
async def list_audit_actions(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(ro_scoped_session_from_path),
) -> list[str]:
    """Distinct action names this tenant has produced — drives the
    filter dropdown in the admin UI. Sorted by frequency (most common
    first) so the operator sees the relevant ones at the top."""
    repo = AuditRepository(session)
    return await repo.distinct_actions()
