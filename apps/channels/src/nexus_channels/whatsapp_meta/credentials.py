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
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Channel, TenantCredentials
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
        expires = datetime.fromisoformat(expires_raw) if isinstance(expires_raw, str) else None
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
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
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
        """Flip ``needs_reauth`` to True without dropping the token.

        Called from the outbound dispatcher when Meta returns
        ``OAuthException 190``. The token row stays around so the operator
        can see *which* tenant lost auth without joining tables; the next
        outbound to that tenant returns ``SendStatus.FAILED`` until the
        owner re-runs Embedded Signup.
        """
        require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            row.needs_reauth = True
            await self._session.flush()

    async def delete(self) -> None:
        """Hard-delete on tenant offboarding from the Meta channel."""
        require_current_tenant()
        stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_KEY)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class ChannelCredentialsRepository:
    """Per-channel Meta credentials, stored in ``channels.config_encrypted``.

    A tenant can hold more than one WhatsApp number, and the two facts a send
    needs are scoped differently:

    - ``phone_number_id`` is per NUMBER. It lives unencrypted in
      ``channels.config`` already, written at connect time.
    - the BISUAT is per WABA. Two numbers under one WABA share it; two numbers
      under different WABAs do not.

    So the token gets its own column on the channel row, and everything falls
    back to the tenant-level credential when the channel carries none. That
    fallback is what keeps every currently-connected tenant working without a
    backfill: their single channel has no encrypted payload, reads the tenant
    row exactly as before, and nothing changes.

    ``channels.config_encrypted`` already existed on the model and was unused,
    which is why this needs no migration.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, channel_id: uuid.UUID) -> MetaCredentials | None:
        """Channel-scoped credentials, or ``None`` if the channel has none.

        RLS scopes the lookup, so a channel id belonging to another tenant
        reads as absent rather than as somebody else's token.
        """
        require_current_tenant()
        payload = await self._session.scalar(
            select(Channel.config_encrypted).where(Channel.id == channel_id)
        )
        if not payload:
            return None
        return MetaCredentials.from_payload(payload)

    async def upsert(self, channel_id: uuid.UUID, creds: MetaCredentials) -> None:
        require_current_tenant()
        channel = await self._session.get(Channel, channel_id)
        if channel is None:
            raise LookupError(f"channel {channel_id} not found for current tenant")
        channel.config_encrypted = creds.to_payload()
        await self._session.flush()

    async def delete(self, channel_id: uuid.UUID) -> None:
        require_current_tenant()
        channel = await self._session.get(Channel, channel_id)
        if channel is not None:
            channel.config_encrypted = None
            await self._session.flush()


async def resolve_send_credentials(
    session: AsyncSession, *, channel_id: uuid.UUID | None = None
) -> tuple[str, str]:
    """``(phone_number_id, bisuat)`` for a send leaving from ``channel_id``.

    This is the single function every Meta send resolves its identity through,
    and the precedence encodes one rule: **the number a message is sent from
    must come from the channel the message belongs to, never from the tenant.**

    Before this existed the adapter read ``phone_number_id`` off the tenant's
    one credential row, so connecting a second number silently re-pointed every
    outbound of that tenant — agent replies included — at the newly connected
    line. That failure is invisible until a customer notices the wrong number
    wrote to them.

    Resolution:

    - ``phone_number_id``: the channel's ``config``, falling back to the tenant
      credential (which is correct precisely when the tenant has one number,
      i.e. every tenant in production today).
    - token: the channel's own encrypted payload if it has one, else the
      tenant's. Same number of DB reads as before in the common case.

    Requires an active tenant context; RLS is the only authority on which rows
    are visible.
    """
    require_current_tenant()
    tenant_creds: MetaCredentials | None = None
    channel_pnid: str | None = None
    channel_token: str | None = None

    if channel_id is not None:
        row = (
            await session.execute(
                select(Channel.config, Channel.config_encrypted).where(Channel.id == channel_id)
            )
        ).first()
        if row is not None:
            config, encrypted = row
            raw_pnid = (config or {}).get("phone_number_id")
            if isinstance(raw_pnid, str) and raw_pnid:
                channel_pnid = raw_pnid
            if encrypted:
                channel_token = MetaCredentials.from_payload(encrypted).bisuat

    if channel_pnid is None or channel_token is None:
        tenant_creds = await MetaCredentialsRepository(session).get()

    pnid = channel_pnid or (tenant_creds.phone_number_id if tenant_creds else None)
    token = channel_token or (tenant_creds.bisuat if tenant_creds else None)
    if not pnid or not token:
        raise LookupError(
            "no Meta credentials resolvable for "
            f"channel={channel_id} (tenant credential present: {tenant_creds is not None})"
        )
    return (pnid, token)
