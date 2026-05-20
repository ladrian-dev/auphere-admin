"""Operator context — RLS gate for the QA Playground (ADR-020 / Phase 3).

The QA Playground introduces a second isolation dimension on top of the
existing tenant scoping: every QA thread, audit row and side-effect record
belongs to a specific *operator* (an Auphere staff member with role
``qa_operator``). Two operators must NEVER see each other's threads, even
when they're inspecting the same tenant.

Mirrors ``core/tenant_context.py`` field-for-field but uses
``app.operator_id`` instead of ``app.tenant_id``. The two settings coexist
inside the same transaction — a QA request opens a session, applies BOTH
``app.tenant_id`` (for the tenant-scoped tables the agent reads) AND
``app.operator_id`` (for the qa.* tables). RLS policies on each schema
read the setting that applies to them.

A request that forgets to call ``apply_operator_to_session`` will see zero
rows from any ``qa.*`` table — the policies fail closed by reading
``current_setting('app.operator_id', true)`` and treating missing values
as a NULL mismatch.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import IsolationViolation

# Migration 0026 (Fase 6 follow-up): ``operator_id`` is TEXT, not UUID.
# Better Auth's ``session.user.id`` is a cuid-style short id, so the GUC
# stores whatever the BFF forwards as ``X-Operator-Id``. The RLS policies
# compare text to text; security comes from the Bearer + the WITH CHECK
# symmetry, not from the id's shape.
_current_operator: ContextVar[str | None] = ContextVar("current_operator", default=None)

# Phase 3 (ADR-020): the QA thread the current request is editing.
# Set by the LangGraph Server's auth handler (or any caller that wants
# the dry_run audit writer to stamp rows). Independent from
# ``_current_operator`` because some requests (creating a thread) don't
# yet have a thread id, and some operator actions span no thread at all.
_current_qa_thread: ContextVar[uuid.UUID | None] = ContextVar("current_qa_thread", default=None)


def get_current_operator() -> str | None:
    return _current_operator.get()


def require_current_operator() -> str:
    operator_id = _current_operator.get()
    if operator_id is None:
        raise IsolationViolation(
            "No operator_id in context — qa.* repository was invoked outside a QA-scoped request."
        )
    return operator_id


def get_current_qa_thread() -> uuid.UUID | None:
    """The QA thread the current request is bound to, or ``None``."""
    return _current_qa_thread.get()


@contextmanager
def operator_context(operator_id: str) -> Iterator[str]:
    token = _current_operator.set(operator_id)
    try:
        yield operator_id
    finally:
        _current_operator.reset(token)


@contextmanager
def qa_thread_context(thread_id: uuid.UUID) -> Iterator[uuid.UUID]:
    """Bind the current QA thread for the duration of the block.

    The LangGraph Server sets this per-run so the dry_run audit writer
    can stamp rows with the correct ``thread_id``. Tests and ad-hoc
    code can use the contextmanager directly.
    """
    token = _current_qa_thread.set(thread_id)
    try:
        yield thread_id
    finally:
        _current_qa_thread.reset(token)


async def apply_operator_to_session(session: AsyncSession, operator_id: str) -> None:
    """Set ``app.operator_id`` for the current transaction.

    Like ``apply_tenant_to_session`` this uses ``set_config(..., is_local=true)``
    so the value resets at COMMIT/ROLLBACK and can't leak between requests
    sharing a connection pool. The qa.* policies read it via
    ``current_setting('app.operator_id', true)`` and reject when unset.

    Does NOT switch DB role — that's already done by ``apply_tenant_to_session``
    earlier in the request. Calling this without the tenant role switch would
    let a superuser session bypass RLS; the qa endpoints always layer both.
    """
    await session.execute(
        text("SELECT set_config('app.operator_id', :oid, true)"),
        {"oid": str(operator_id)},
    )


@asynccontextmanager
async def qa_scoped_session(
    session: AsyncSession,
    *,
    operator_id: str,
    tenant_id: uuid.UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Apply QA scope to ``session`` inside an existing transaction.

    Two-dimensional scoping:
      - ``operator_id`` is REQUIRED — RLS on qa.* fails closed without it.
      - ``tenant_id`` is OPTIONAL — set it when the block also reads
        tenant-scoped tables (e.g. ``messages``, ``conversations``).

    The transaction must already be open on ``session`` when this is
    called. ``SET LOCAL`` only takes effect inside a transaction; calling
    it outside a tx is a silent no-op that lets RLS fail closed on the
    next query, which manifests as confusing empty result sets. We
    fail loud instead.

    For FastAPI handlers, layer this on top of ``get_db_session`` after
    opening a transaction (the ``qa_session`` dependency below does
    exactly that). For ad-hoc scripts / tests, open the transaction
    yourself with ``async with session.begin():`` first.

    Always resets the contextvars on exit.
    """
    from nexus_api.core.tenant_context import (
        _current_tenant,
        apply_tenant_to_session,
    )

    if not session.in_transaction():
        raise IsolationViolation(
            "qa_scoped_session must be called inside an open transaction; "
            "wrap with `async with session.begin():` or use the "
            "`qa_session` FastAPI dependency."
        )

    operator_token = _current_operator.set(operator_id)
    tenant_token = _current_tenant.set(tenant_id) if tenant_id is not None else None
    try:
        if tenant_id is not None:
            await apply_tenant_to_session(session, tenant_id)
        await apply_operator_to_session(session, operator_id)
        yield session
    finally:
        _current_operator.reset(operator_token)
        if tenant_token is not None:
            _current_tenant.reset(tenant_token)
