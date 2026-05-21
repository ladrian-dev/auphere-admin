"""Helpers to read/write the per-tenant Meta WhatsApp credentials.

Stored in ``tenant_credentials`` with ``integration="meta_whatsapp"``. The
``encrypted_payload`` column (FernetEncrypted) holds a JSON document with
the fields below — keeping them together means a single decrypt buys the
full set instead of one per call.

JSON shape::

    {
      "bisuat": "EAAxxxx",                    # Business Integration System User Access Token
      "bisuat_expires_at": "2026-07-19T00:00:00Z" | null,
      "waba_id": "100123456789",
      "phone_number_id": "200123456789",
      "business_id": "300123456789",
      "display_phone_number": "+56933334444",
      "verify_token": "<32 chars>",           # webhook handshake (per-tenant)
      "mode": "cloud_api" | "coexistence",
      "external_user_id_enrolled": false      # BSUID rollout flag
    }

This module deliberately knows nothing about Fernet — the SQLAlchemy
``FernetEncrypted`` type does the encryption transparently. It only
serialises and validates the structure.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import TenantCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

INTEGRATION_KEY = "meta_whatsapp"


@dataclass(slots=True)
class MetaCredentials:
    """In-memory shape of a tenant's Meta credentials."""

    bisuat: str
    waba_id: str
    phone_number_id: str
    business_id: str
    display_phone_number: str
    verify_token: str
    mode: Literal["cloud_api", "coexistence"] = "cloud_api"
    bisuat_expires_at: datetime | None = None
    external_user_id_enrolled: bool = False

    def to_payload(self) -> bytes:
        """Serialise to bytes for ``FernetEncrypted`` (the type expects
        ``bytes`` and encrypts it before INSERT/UPDATE).
        """
        data = asdict(self)
        if self.bisuat_expires_at is not None:
            data["bisuat_expires_at"] = self.bisuat_expires_at.isoformat()
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_payload(cls, payload: bytes) -> MetaCredentials:
        raw = json.loads(payload.decode("utf-8"))
        expires_raw = raw.get("bisuat_expires_at")
        expires = (
            datetime.fromisoformat(expires_raw) if isinstance(expires_raw, str) else None
        )
        return cls(
            bisuat=raw["bisuat"],
            waba_id=raw["waba_id"],
            phone_number_id=raw["phone_number_id"],
            business_id=raw["business_id"],
            display_phone_number=raw["display_phone_number"],
            verify_token=raw["verify_token"],
            mode=raw.get("mode", "cloud_api"),
            bisuat_expires_at=expires,
            external_user_id_enrolled=bool(raw.get("external_user_id_enrolled", False)),
        )


class MetaCredentialsRepository:
    """Read/write helper around ``tenant_credentials``.

    All methods require an active tenant context — they intentionally
    don't accept ``tenant_id`` to keep RLS the only authority on which
    rows are visible.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> MetaCredentials | None:
        require_current_tenant()
        stmt = select(TenantCredentials).where(
            TenantCredentials.integration == INTEGRATION_KEY
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return MetaCredentials.from_payload(row.encrypted_payload)

    async def get_or_raise(self) -> MetaCredentials:
        creds = await self.get()
        if creds is None:
            raise LookupError("no Meta credentials for current tenant")
        return creds

    async def upsert(self, creds: MetaCredentials) -> None:
        """Insert or update the row for the current tenant.

        Returning early on the equal-payload case is intentional — Fernet
        re-encrypts with a fresh nonce, so a no-op write would still rotate
        the ciphertext and invalidate caches downstream unnecessarily.
        """
        tenant_id = require_current_tenant()
        stmt = select(TenantCredentials).where(
            TenantCredentials.integration == INTEGRATION_KEY
        )
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
        """Flip ``needs_reauth`` to True without dropping the token.

        Called from the outbound dispatcher when Meta returns
        ``OAuthException 190``. The token row stays around so the operator
        can see *which* tenant lost auth without joining tables; the next
        outbound to that tenant returns ``SendStatus.FAILED`` until the
        owner re-runs Embedded Signup.
        """
        require_current_tenant()
        stmt = select(TenantCredentials).where(
            TenantCredentials.integration == INTEGRATION_KEY
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            row.needs_reauth = True
            await self._session.flush()

    async def delete(self) -> None:
        """Hard-delete on tenant offboarding from the Meta channel."""
        require_current_tenant()
        stmt = select(TenantCredentials).where(
            TenantCredentials.integration == INTEGRATION_KEY
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
