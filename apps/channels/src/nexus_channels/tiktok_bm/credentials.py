"""Helpers to read/write the per-tenant TikTok Business Messaging credentials.

Stored in ``tenant_credentials`` with ``integration="tiktok_bm"``. The
``encrypted_payload`` column (FernetEncrypted) holds a JSON document with the
fields below — keeping them together means a single decrypt buys the full set
instead of one per call.

JSON shape::

    {
      "access_token": "act.xxxx",
      "access_token_expires_at": "2026-07-29T12:00:00Z",
      "refresh_token": "rft.xxxx",
      "refresh_token_expires_at": "2027-07-28T12:00:00Z",
      "business_id": "7123456789012345678",
      "display_name": "Clínica Boreal",
      "region": "VE" | null,
      "webhook_config_id": "abc123" | null
    }

The critical difference from the Meta credentials next door: **these expire
fast**. A TikTok access token lives ~24 hours, so ``access_token_expires_at``
is not decoration — the refresh cron reads it to decide what to rotate, and a
tenant whose token lapses goes silent within a day. The refresh token lasts a
year; when *that* expires the business owner has to re-authorise by hand.

This module deliberately knows nothing about Fernet — the SQLAlchemy
``FernetEncrypted`` type does the encryption transparently. It only
serialises and validates the structure.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import TenantCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

INTEGRATION_KEY = "tiktok_bm"

# Refresh this far ahead of the stated expiry. The cron runs hourly, so an
# hour of slack would technically do; six hours means a couple of missed cron
# ticks (deploy, restart, transient TikTok outage) still can't kill a channel.
REFRESH_LEEWAY = timedelta(hours=6)


@dataclass(slots=True)
class TikTokCredentials:
    """In-memory shape of a tenant's TikTok Business Messaging credentials."""

    access_token: str
    refresh_token: str
    business_id: str
    display_name: str = ""
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    region: str | None = None
    webhook_config_id: str | None = None

    def needs_refresh(self, *, now: datetime | None = None) -> bool:
        """True when the access token is expired or close enough to it.

        An unknown expiry counts as "refresh now": TikTok always returns
        ``expires_in`` on both exchange and refresh, so a missing value means
        the row predates a schema change or was written by hand, and
        refreshing is the safe interpretation.
        """
        if self.access_token_expires_at is None:
            return True
        current = datetime.now(UTC) if now is None else now
        return self.access_token_expires_at - REFRESH_LEEWAY <= current

    def refresh_token_expired(self, *, now: datetime | None = None) -> bool:
        """True when even the refresh token is gone — only re-auth recovers."""
        if self.refresh_token_expires_at is None:
            return False
        current = datetime.now(UTC) if now is None else now
        return self.refresh_token_expires_at <= current

    def to_payload(self) -> bytes:
        """Serialise to bytes for ``FernetEncrypted`` (the type expects
        ``bytes`` and encrypts it before INSERT/UPDATE).
        """
        data = asdict(self)
        for key in ("access_token_expires_at", "refresh_token_expires_at"):
            value = data.get(key)
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_payload(cls, payload: bytes) -> TikTokCredentials:
        raw = json.loads(payload.decode("utf-8"))
        return cls(
            access_token=raw["access_token"],
            refresh_token=raw["refresh_token"],
            business_id=raw["business_id"],
            display_name=raw.get("display_name", ""),
            access_token_expires_at=_parse_dt(raw.get("access_token_expires_at")),
            refresh_token_expires_at=_parse_dt(raw.get("refresh_token_expires_at")),
            region=raw.get("region"),
            webhook_config_id=raw.get("webhook_config_id"),
        )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Everything downstream compares against timezone-aware ``now``; a naive
    # value here would raise at comparison time instead of at parse time,
    # which is much harder to trace back to a bad credential row.
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class TikTokCredentialsRepository:
    """Read/write helper around ``tenant_credentials``.

    All methods require an active tenant context — they intentionally don't
    accept ``tenant_id`` to keep RLS the only authority on which rows are
    visible. That includes the refresh cron: ``tenant_credentials`` is
    RLS-protected, so the cron enumerates *tenants* (an unprotected registry
    table) and then opens one scoped session per tenant, rather than trying
    to sweep credential rows cross-tenant. No token ever crosses a boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> TikTokCredentials | None:
        require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return TikTokCredentials.from_payload(row.encrypted_payload)

    async def get_or_raise(self) -> TikTokCredentials:
        creds = await self.get()
        if creds is None:
            raise LookupError("no TikTok credentials for current tenant")
        return creds

    async def upsert(self, creds: TikTokCredentials) -> None:
        """Insert or update the row for the current tenant.

        Always writes, even when the payload is unchanged: unlike the Meta
        path there is no meaningful no-op case here, because every write
        carries a freshly rotated token.
        """
        tenant_id = require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        payload = creds.to_payload()
        if row is None:
            self._session.add(
                TenantCredentials(
                    tenant_id=tenant_id,
                    integration=INTEGRATION_KEY,
                    encrypted_payload=payload,
                    needs_reauth=False,
                )
            )
        else:
            row.encrypted_payload = payload
            row.needs_reauth = False
        await self._session.flush()

    async def mark_reauth_needed(self) -> None:
        """Flip ``needs_reauth`` without dropping the token row.

        Called when TikTok rejects the token outright, or when the refresh
        token itself has expired. Keeping the row lets the operator panel
        show *which* tenant lost auth without a join; outbound sends fail
        until the owner re-authorises from the panel.
        """
        require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            row.needs_reauth = True
            await self._session.flush()

    async def touch_health_check(self) -> None:
        """Stamp ``last_health_check_at`` after a successful refresh, so the
        panel can distinguish "quiet but healthy" from "quietly broken"."""
        require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            row.last_health_check_at = datetime.now(UTC)
            await self._session.flush()

    async def delete(self) -> None:
        """Hard-delete on tenant offboarding from the TikTok channel."""
        require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
