"""Reusable FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Path, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.redis_client import get_redis as _get_redis
from nexus_api.db.base import get_sessionmaker
from nexus_api.repositories import TenantRepository


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_sessionmaker()
    async with factory() as session:
        yield session


def get_redis() -> Redis:
    return _get_redis()


async def scoped_session_from_path(
    tenant_id: uuid.UUID = Path(..., description="Tenant UUID"),
    session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[AsyncSession]:
    """Yield a session inside a transaction with `app.tenant_id` set.

    Flow:
      1. Open the transaction (autobegin).
      2. Resolve the tenant via the global TenantRepository (no RLS on tenants).
      3. If not found → 404.
      4. Apply `set_config('app.tenant_id', ..., true)` so subsequent queries
         hit RLS-protected tables under the right scope.
      5. Bind tenant_id to structlog context.
      6. Yield. The endpoint runs inside this transaction; on clean return
         we commit, on exception we roll back.
    """
    from nexus_api.core.tenant_context import (
        _current_tenant,
        apply_tenant_to_session,
    )

    token = _current_tenant.set(tenant_id)
    try:
        async with session.begin():
            tenant = await TenantRepository(session).get(tenant_id)
            if tenant is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"tenant {tenant_id} not found",
                )
            await apply_tenant_to_session(session, tenant_id)
            bind_tenant(tenant_id)
            yield session
    finally:
        _current_tenant.reset(token)
