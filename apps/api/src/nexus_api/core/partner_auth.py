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

from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_keys import checksum_ok, hash_key
from nexus_api.db.models import Partner, PartnerApiKey, PartnerStatus

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PartnerContext:
    partner: Partner
    api_key: PartnerApiKey


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


def require_partner_key(scope: str):
    """Dependency factory: ``Depends(require_partner_key("provision"))``."""

    async def _dependency(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        session: AsyncSession = Depends(get_db_session),
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
