"""Reusable FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, Path, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core import redis_client
from nexus_api.core.logging_context import bind_tenant
from nexus_api.db.base import get_sessionmaker
from nexus_api.repositories import TenantRepository

if TYPE_CHECKING:
    from nexus_api.core.embed_jwt import WidgetClaims
    from nexus_api.db.models import Partner


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_sessionmaker()
    async with factory() as session:
        yield session


def get_redis() -> Redis:
    # Dereference dynamically so test fixtures that
    # ``monkeypatch.setattr(redis_client, "get_redis", ...)`` take effect.
    # An ``import X as Y`` here would bind to the function object at import
    # time and bypass the monkey-patch (latent bug fixed in Block L).
    return redis_client.get_redis()


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


@dataclass(frozen=True)
class EmbedContext:
    """Everything an ``/v1/embed/*`` handler may use. ``session`` is
    already tenant-scoped from the JWT claims — never from any other
    source."""

    session: AsyncSession
    claims: WidgetClaims
    partner: Partner


async def scoped_session_from_embed_jwt(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> AsyncIterator[EmbedContext]:
    """Sister of ``scoped_session_from_path`` for the embed surface
    (ADR-028). The tenant comes EXCLUSIVELY from the signed widget JWT.

    Fail-closed re-checks inside the transaction, per request:
      - the minting API key is still alive (revocation kills live JWTs),
      - the partner is still active,
      - the ``partner_tenants`` mapping still exists.
    Then the per-partner embed rate limit, then RLS scoping exactly like
    the path-based dependency.
    """
    from nexus_api.core import rate_limit
    from nexus_api.core.embed_jwt import WidgetTokenError, verify_widget_token
    from nexus_api.core.partner_auth import key_is_active
    from nexus_api.core.tenant_context import (
        _current_tenant,
        apply_tenant_to_session,
    )
    from nexus_api.db.models import PartnerStatus

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = verify_widget_token(authorization.removeprefix("Bearer ").strip())
    except WidgetTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        ) from None

    token = _current_tenant.set(claims.tenant_id)
    try:
        async with session.begin():
            from datetime import UTC, datetime

            from nexus_api.db.models import Partner, PartnerApiKey
            from nexus_api.repositories.partner import PartnerTenantRepository

            api_key = await session.get(PartnerApiKey, claims.key_id)
            if api_key is None or not key_is_active(api_key, now=datetime.now(UTC)):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session token no longer valid",
                )
            partner = await session.get(Partner, claims.partner_id)
            if partner is None or partner.status != PartnerStatus.ACTIVE.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Partner is suspended",
                )
            if not await PartnerTenantRepository(session).mapping_exists(
                claims.partner_id, claims.tenant_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Client mapping no longer exists",
                )

            if not await rate_limit.allow(
                redis,
                key=rate_limit.embed_bucket_key(str(claims.partner_id)),
                per_minute=partner.rate_limit_embed_per_min,
            ):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"},
                )

            await apply_tenant_to_session(session, claims.tenant_id)
            bind_tenant(claims.tenant_id)
            yield EmbedContext(session=session, claims=claims, partner=partner)
    finally:
        _current_tenant.reset(token)
