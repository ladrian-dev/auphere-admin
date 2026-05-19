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

_current_operator: ContextVar[uuid.UUID | None] = ContextVar(
    "current_operator", default=None
)


def get_current_operator() -> uuid.UUID | None:
    return _current_operator.get()


def require_current_operator() -> uuid.UUID:
    operator_id = _current_operator.get()
    if operator_id is None:
        raise IsolationViolation(
            "No operator_id in context — qa.* repository was invoked outside a "
            "QA-scoped request."
        )
    return operator_id


@contextmanager
def operator_context(operator_id: uuid.UUID) -> Iterator[uuid.UUID]:
    token = _current_operator.set(operator_id)
    try:
        yield operator_id
    finally:
        _current_operator.reset(token)


async def apply_operator_to_session(
    session: AsyncSession, operator_id: uuid.UUID
) -> None:
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
    operator_id: uuid.UUID,
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
