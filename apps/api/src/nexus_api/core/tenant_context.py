"""Tenant context — the source of truth for the current tenant in a request.

Repositories and tools NEVER accept tenant_id as a parameter; they read it from
this contextvar (architecture/agent-isolation.md, garantía 2 + tabla "Capas").

The contextvar is set by the FastAPI middleware once the tenant has been
resolved (admin endpoints set it from the path; webhooks resolve it from the
provider identifier with Redis cache).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import IsolationViolation

_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> uuid.UUID | None:
    return _current_tenant.get()


def require_current_tenant() -> uuid.UUID:
    tenant_id = _current_tenant.get()
    if tenant_id is None:
        raise IsolationViolation(
            "No tenant_id in context — repository/tool was invoked outside a tenant-scoped request."
        )
    return tenant_id


@contextmanager
def tenant_context(tenant_id: uuid.UUID) -> Iterator[uuid.UUID]:
    token = _current_tenant.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _current_tenant.reset(token)


# Current customer (debtor) of the turn. Set by the runtime per turn so
# customer-facing tools can resolve "the person I'm talking to" WITHOUT
# trusting an LLM-supplied identifier — e.g. billing.get_my_debt looks up
# only this customer's debt, making cross-customer lookups impossible.
_current_customer: ContextVar[uuid.UUID | None] = ContextVar("current_customer", default=None)


def get_current_customer() -> uuid.UUID | None:
    return _current_customer.get()


@contextmanager
def customer_context(customer_id: uuid.UUID | None) -> Iterator[uuid.UUID | None]:
    token = _current_customer.set(customer_id)
    try:
        yield customer_id
    finally:
        _current_customer.reset(token)


async def apply_tenant_to_session(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Scope this transaction to `tenant_id` AND switch to the `nexus_app` role.

    `set_config(..., is_local=true)` is the parameterised form of `SET LOCAL`
    (Postgres rejects bind params on the `SET LOCAL` statement itself).

    Switching to `nexus_app` drops superuser, so RLS policies actually take
    effect. The connecting `nexus` user is a Postgres superuser (it runs
    migrations); without role-switching, RLS would be silently bypassed and
    the isolation guarantees would be a lie. Migration 0004 creates the role
    and grants the connecting user permission to assume it.

    **Both settings travel in ONE statement.** `SET LOCAL ROLE x` is exactly
    `set_config('role', 'x', true)` — `role` is a regular GUC — so the two
    fit in a single target list. It used to be two `execute` calls, which is
    two network round trips on the critical path of every scoped request,
    including the webhook whose ack budget is 50 ms. The tenant GUC goes
    first in the list for readability; the order does not matter because
    `nexus_app` can set `app.*` just as well as the superuser can.
    """
    await session.execute(
        text(
            "SELECT set_config('app.tenant_id', :tid, true), "
            "       set_config('role', 'nexus_app', true)"
        ),
        {"tid": str(tenant_id)},
    )


@asynccontextmanager
async def tenant_scoped_session(
    session: AsyncSession, tenant_id: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    """Begin a transaction, set app.tenant_id, set the contextvar, yield.

    Commits on clean exit, rolls back on exception. Always resets the contextvar.
    """
    token = _current_tenant.set(tenant_id)
    try:
        async with session.begin():
            await apply_tenant_to_session(session, tenant_id)
            yield session
    finally:
        _current_tenant.reset(token)
