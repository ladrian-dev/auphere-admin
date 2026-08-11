"""Partner API key authentication for the ``/v1/partners/*`` surface (ADR-028).

Server-to-server auth: the partner's backend sends
``Authorization: Bearer ak_live_…``. Flow per request:

1. Offline CRC32 checksum check — typos and garbage never reach the DB.
2. SHA-256 the plaintext → UNIQUE lookup on ``api_keys.key_hash``.
3. Fail closed: unknown hash, revoked (grace expired), expired key or
   suspended partner all end the request. 401 for credential problems,
   403 for authorization problems (valid key, insufficient scope /
   suspended partner).
4. ``last_used_at``/``last_used_ip`` update is best-effort bookkeeping.

Timing note: the SHA-256 + indexed UNIQUE lookup is not a
secret-dependent comparison (the hash either exists or it doesn't), so
constant-time handling is not required the way it is for the static
admin token.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core import rate_limit
from nexus_api.core.otel_metrics import record_rate_limit_rejection
from nexus_api.core.partner_keys import checksum_ok, hash_key
from nexus_api.db.models import (
    TENANT_SCOPED_API_KEY_SCOPES,
    Partner,
    PartnerApiKey,
    PartnerStatus,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PartnerContext:
    partner: Partner
    api_key: PartnerApiKey


@dataclass(frozen=True)
class TenantKeyContext:
    """A request authenticated by a key bound to exactly one tenant.

    The distinction from ``PartnerContext`` is the whole point: here the
    tenant comes from the key row, so no request field can widen it.
    Endpoints taking this context cannot be talked into touching another
    tenant — there is no input to talk them with.
    """

    partner: Partner
    api_key: PartnerApiKey
    tenant_id: uuid.UUID


def _unauthorized(detail: str = "Invalid API key") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def key_is_active(key: PartnerApiKey, *, now: datetime) -> bool:
    """A key authenticates while not expired and either not revoked or
    still inside its rotation grace window."""
    if key.expires_at is not None and key.expires_at <= now:
        return False
    if key.revoked_at is not None:
        return key.grace_expires_at is not None and now < key.grace_expires_at
    return True


# WP-30: qué cubo y qué límite le toca a cada scope.
#
# Antes de esto, ``rate_limit_mint_per_min`` no se leía en NINGÚN sitio y
# ``mint_bucket_key``/``embed_bucket_key`` eran código muerto con un test
# que solo comprobaba cómo se escribe la clave. Es decir: el panel dejaba
# configurar un tope de aprovisionamiento, lo guardaba, lo devolvía por
# API — y una clave de partner podía crear tenants sin freno. Peor que
# fail-open: un límite que se enseña y no existe.
#
# El límite se aplica AQUÍ y no en cada endpoint porque este es el único
# punto por el que pasan todos (``require_tenant_key`` también depende de
# él), así que una superficie nueva nace limitada en vez de nacer
# olvidada.
_SURFACE_BY_SCOPE: dict[str, str] = {
    "provision": "mint",
    "broadcasts": "broadcast",
    "widget_sessions": "embed",
    "messages_send": "embed",
}

_BUCKET_KEY = {
    "mint": rate_limit.mint_bucket_key,
    "embed": rate_limit.embed_bucket_key,
    "broadcast": rate_limit.broadcast_bucket_key,
}


def _limit_for(surface: str, partner: Partner) -> int:
    # El de emisión y el de lectura comparten cifra configurada
    # (``rate_limit_embed_per_min``) pero NO cubo: un partner que satura
    # sus difusiones no puede quedarse sin poder consultar el estado de
    # las que ya mandó.
    return (
        partner.rate_limit_mint_per_min if surface == "mint" else partner.rate_limit_embed_per_min
    )


def require_partner_key(
    scope: str,
) -> Callable[..., Awaitable[PartnerContext]]:
    """Dependency factory: ``Depends(require_partner_key("provision"))``."""

    async def _dependency(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        session: AsyncSession = Depends(get_db_session),
        redis: Redis = Depends(get_redis),
    ) -> PartnerContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise _unauthorized("Missing bearer token")
        plaintext = authorization.removeprefix("Bearer ").strip()
        if not checksum_ok(plaintext):
            # Offline reject — no DB roundtrip for garbage input.
            raise _unauthorized()

        now = datetime.now(UTC)
        result = await session.execute(
            sa.select(PartnerApiKey, Partner)
            .join(Partner, Partner.id == PartnerApiKey.partner_id)
            .where(PartnerApiKey.key_hash == hash_key(plaintext))
            .limit(1)
        )
        row = result.first()
        if row is None:
            raise _unauthorized()
        api_key, partner = row

        if not key_is_active(api_key, now=now):
            raise _unauthorized("API key revoked or expired")
        if partner.status != PartnerStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Partner is suspended",
            )
        if scope not in (api_key.scopes or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required scope: {scope}",
            )
        # A key confined to one tenant may NEVER exercise a partner-level
        # scope: those endpoints pick the tenant from ``external_client_ref``,
        # so honouring one here would let a key issued for tenant A act on
        # every other client of the partner. The DB check constraint only
        # covers ``provision`` (migration 0052); this covers every present
        # and future partner-level scope. Tenant-scoped scopes
        # (``messages_send``) are exactly the ones that MUST carry a
        # tenant, so they are not affected.
        if api_key.tenant_id is not None and scope not in TENANT_SCOPED_API_KEY_SCOPES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"scope {scope!r} is partner-level and cannot be used from a "
                    "tenant-scoped API key"
                ),
            )

        # El límite va DESPUÉS de autenticar, no antes: el cubo es por
        # partner y hasta aquí no se sabe qué partner es. Una avalancha
        # de credenciales inválidas cuesta el checksum y una búsqueda por
        # índice — eso lo para el ALB, no esto.
        surface = _SURFACE_BY_SCOPE.get(scope, "embed")
        if not await rate_limit.allow(
            redis,
            key=_BUCKET_KEY[surface](str(partner.id)),
            per_minute=_limit_for(surface, partner),
            surface=surface,
        ):
            record_rate_limit_rejection(surface=surface, degraded=False)
            log.warning(
                "partner_auth.rate_limited",
                partner=partner.slug,
                surface=surface,
                scope=scope,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for the {surface} surface",
            )

        # Bookkeeping — never let it fail the authenticated request.
        try:
            client_ip = request.client.host if request.client else None
            await session.execute(
                sa.update(PartnerApiKey)
                .where(PartnerApiKey.id == api_key.id)
                .values(last_used_at=now, last_used_ip=client_ip)
            )
            await session.commit()
        except Exception:  # pragma: no cover - purely defensive
            log.warning("partner_auth.last_used_update_failed", key_id=str(api_key.id))
            await session.rollback()

        return PartnerContext(partner=partner, api_key=api_key)

    return _dependency


def require_tenant_key(
    scope: str,
) -> Callable[..., Awaitable[TenantKeyContext]]:
    """Like ``require_partner_key``, but the key must name a tenant.

    Layered on top rather than beside it: every credential check
    (checksum, hash lookup, revocation, grace window, partner status,
    scope) stays in one place, and this adds the single extra condition.

    A key without ``tenant_id`` is a *valid* credential used on the wrong
    surface — 403, not 401. Retrying with the same key will never work;
    the caller needs a different key.
    """

    async def _dependency(
        ctx: PartnerContext = Depends(require_partner_key(scope)),
    ) -> TenantKeyContext:
        if ctx.api_key.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint requires a tenant-scoped API key",
            )
        return TenantKeyContext(
            partner=ctx.partner,
            api_key=ctx.api_key,
            tenant_id=ctx.api_key.tenant_id,
        )

    return _dependency
