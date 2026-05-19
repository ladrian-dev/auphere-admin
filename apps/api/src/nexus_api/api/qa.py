"""QA Playground HTTP surface (ADR-020, Phase 3).

Endpoints
---------

``POST   /qa/threads``               — create a thread (tenant_id in body)
``GET    /qa/threads``                — list operator's threads (filter by tenant)
``GET    /qa/threads/{id}``           — detail (thread + counts)
``PATCH  /qa/threads/{id}``           — rename / archive
``GET    /qa/threads/{id}/audit``     — side-effect audit log for this thread

Every request is gated by ``require_qa_operator`` (Bearer admin_token +
``X-Operator-Id`` header). The ``qa_session`` dependency opens a single
transaction per request and applies ``app.operator_id`` (and ``app.tenant_id``
when the body carries it) so RLS holds.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.operator_context import (
    _current_operator,
    apply_operator_to_session,
)
from nexus_api.core.qa_security import require_qa_operator
from nexus_api.core.tenant_context import (
    _current_tenant,
    apply_tenant_to_session,
)
from nexus_api.db.models.qa import QAAuditLog, QASideEffectAudit, QAThread
from nexus_api.db.models.tenant import Tenant

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


# ── dependency: tx + operator-scoped session ─────────────────────────────────


async def qa_session(
    operator_id: Annotated[uuid.UUID, Depends(require_qa_operator)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[tuple[AsyncSession, uuid.UUID]]:
    """Open a transaction + apply ``app.operator_id`` for the request.

    Mirrors ``scoped_session_from_path`` but for the QA dimension:
      - opens the transaction (commits on clean exit, rolls back on error)
      - sets ``app.operator_id`` (RLS gate on qa.*)
      - drops the superuser role to ``nexus_app`` so RLS is actually
        enforced — the connecting user is a superuser that bypasses
        every policy by default. ``apply_tenant_to_session`` does this
        too; we duplicate the SET ROLE here so qa-only endpoints (which
        don't always set a tenant) still get role-switched.
    Returns ``(session, operator_id)`` so handlers can stamp inserts
    without re-parsing the header.
    """
    from sqlalchemy import text

    operator_token = _current_operator.set(operator_id)
    try:
        async with session.begin():
            await apply_operator_to_session(session, operator_id)
            await session.execute(text("SET LOCAL ROLE nexus_app"))
            yield session, operator_id
    finally:
        _current_operator.reset(operator_token)


# ── pydantic schemas ─────────────────────────────────────────────────────────


class ThreadCreate(BaseModel):
    tenant_id: uuid.UUID
    title: str = Field(default="Untitled", max_length=200)


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


class ThreadOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    operator_id: uuid.UUID
    external_id: str | None
    title: str
    archived_at: datetime | None
    last_run_at: datetime | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class SideEffectOut(BaseModel):
    id: uuid.UUID
    tool_name: str
    tool_args: dict[str, Any]
    synthetic_result: dict[str, Any]
    blocked_reason: str
    run_id: str | None
    created_at: datetime


# ── helpers ──────────────────────────────────────────────────────────────────


async def _audit(
    session: AsyncSession,
    *,
    operator_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    thread_id: uuid.UUID | None,
    action: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one row to ``qa.audit_log`` from inside an open transaction."""
    session.add(
        QAAuditLog(
            operator_id=operator_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            action=action,
            target_kind=target_kind,
            target_id=target_id,
            payload=payload or {},
        )
    )


def _thread_out(t: QAThread) -> ThreadOut:
    return ThreadOut(
        id=t.id,
        tenant_id=t.tenant_id,
        operator_id=t.operator_id,
        external_id=t.external_id,
        title=t.title,
        archived_at=t.archived_at,
        last_run_at=t.last_run_at,
        message_count=t.message_count,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def _load_thread(session: AsyncSession, thread_id: uuid.UUID) -> QAThread:
    thread = await session.get(QAThread, thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"thread {thread_id} not found",
        )
    return thread


# ── endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/threads",
    response_model=ThreadOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    body: ThreadCreate,
    scope: Annotated[tuple[AsyncSession, uuid.UUID], Depends(qa_session)],
) -> ThreadOut:
    """Create a QA thread bound to ``body.tenant_id``.

    The tenant must exist (we read it without RLS since ``tenants`` is a
    global table). We then apply ``app.tenant_id`` for the rest of the
    transaction so the audit row stamps the tenant correctly.
    """
    session, operator_id = scope
    tenant = await session.get(Tenant, body.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {body.tenant_id} not found",
        )

    # Set the tenant scope on top of the existing operator scope.
    tenant_token = _current_tenant.set(body.tenant_id)
    try:
        await apply_tenant_to_session(session, body.tenant_id)
        thread = QAThread(
            operator_id=operator_id,
            tenant_id=body.tenant_id,
            title=body.title,
        )
        session.add(thread)
        await session.flush()
        await _audit(
            session,
            operator_id=operator_id,
            tenant_id=body.tenant_id,
            thread_id=thread.id,
            action="thread.create",
            target_kind="qa.thread",
            target_id=str(thread.id),
            payload={"title": body.title},
        )
        await session.refresh(thread)
        return _thread_out(thread)
    finally:
        _current_tenant.reset(tenant_token)


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    scope: Annotated[tuple[AsyncSession, uuid.UUID], Depends(qa_session)],
    tenant_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ThreadOut]:
    """List the operator's threads.

    RLS guarantees we only see the operator's own rows even if the
    WHERE clause is omitted — that's the whole point of the isolation
    layer.
    """
    session, _ = scope
    stmt = select(QAThread).order_by(QAThread.updated_at.desc()).limit(limit)
    if tenant_id is not None:
        stmt = stmt.where(QAThread.tenant_id == tenant_id)
    if not include_archived:
        stmt = stmt.where(QAThread.archived_at.is_(None))
    rows = (await session.execute(stmt)).scalars().all()
    return [_thread_out(t) for t in rows]


@router.get("/threads/{thread_id}", response_model=ThreadOut)
async def get_thread(
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, uuid.UUID], Depends(qa_session)],
) -> ThreadOut:
    session, _ = scope
    thread = await _load_thread(session, thread_id)
    return _thread_out(thread)


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def patch_thread(
    body: ThreadPatch,
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, uuid.UUID], Depends(qa_session)],
) -> ThreadOut:
    """Rename or archive a thread.

    Archive is soft (``archived_at = now()``) so audit + side-effect
    rows remain queryable. Un-archive: ``archived: false``.
    """
    if body.title is None and body.archived is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of title or archived must be set",
        )
    session, operator_id = scope
    thread = await _load_thread(session, thread_id)
    changes: dict[str, Any] = {}
    if body.title is not None:
        thread.title = body.title
        changes["title"] = body.title
    if body.archived is not None:
        if body.archived and thread.archived_at is None:
            thread.archived_at = func.now()
            changes["archived"] = True
        elif not body.archived and thread.archived_at is not None:
            thread.archived_at = None
            changes["archived"] = False
    if changes:
        await _audit(
            session,
            operator_id=operator_id,
            tenant_id=thread.tenant_id,
            thread_id=thread.id,
            action="thread.patch",
            target_kind="qa.thread",
            target_id=str(thread.id),
            payload=changes,
        )
    await session.flush()
    await session.refresh(thread)
    return _thread_out(thread)


@router.get(
    "/threads/{thread_id}/audit",
    response_model=list[SideEffectOut],
)
async def get_thread_audit(
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, uuid.UUID], Depends(qa_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SideEffectOut]:
    """Side-effect audit rows for a single thread.

    RLS-scoped by operator_id; the thread_id filter further constrains
    to this conversation. If the operator doesn't own the thread the
    ``_load_thread`` check returns 404 before the audit query runs.
    """
    session, _ = scope
    await _load_thread(session, thread_id)
    stmt = (
        select(QASideEffectAudit)
        .where(QASideEffectAudit.thread_id == thread_id)
        .order_by(QASideEffectAudit.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SideEffectOut(
            id=r.id,
            tool_name=r.tool_name,
            tool_args=r.tool_args,
            synthetic_result=r.synthetic_result,
            blocked_reason=r.blocked_reason,
            run_id=r.run_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
