"""Repository + resolver for ``auphere_owner_channels`` (migration 0038).

Centralises three lookups the webhook + outbox + admin endpoints all
need:

- :meth:`AuphereChannelRepository.get_by_phone` — for the inbound
  webhook, given the ``to`` field of an incoming WhatsApp message.
- :meth:`AuphereChannelRepository.get_default` — fallback when an
  ``OwnerPhoneIndex`` row carries no explicit ``auphere_channel_id``.
- :func:`resolve_channel_for_owner` — combines the two with the
  legacy-settings fallback so callers don't repeat the if-else dance.

The resolver returns a :class:`ResolvedAuphereChannel` value object —
either a real row from the registry OR a legacy fallback synthesised
from ``settings.auphere_owner_phone``. The caller treats both the same
way (``phone_e164`` + optional ``webhook_secret``), which keeps the
webhook + outbox blissfully unaware of the migration boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import AuphereOwnerChannel, OwnerPhoneIndex


@dataclass(frozen=True)
class ResolvedAuphereChannel:
    """A backchannel number ready to use — either a real registry row
    or the legacy settings-based fallback.

    ``channel_id`` is ``None`` when the resolution fell back to
    ``settings.auphere_owner_phone`` (Phase 1 compatibility). The
    webhook + outbox treat both the same way; only the admin UI
    distinguishes ("default" vs "registered") in display.

    ``webhook_secret`` is the DECRYPTED secret ready to feed into
    :func:`verify_ycloud_signature`. When the registry row has
    ``webhook_secret_encrypted=NULL`` OR the resolution fell back to
    settings, this is ``None`` and the caller uses
    ``settings.ycloud_webhook_secret`` (or provider equivalent).
    """

    phone_e164: str
    provider: str
    provider_phone_id: str | None
    webhook_secret: str | None
    channel_id: uuid.UUID | None
    display_name: str

    @property
    def is_legacy_fallback(self) -> bool:
        return self.channel_id is None


class AuphereChannelRepository:
    """Reads + writes on ``auphere_owner_channels``.

    No tenant scoping — this is a GLOBAL registry (like ``connectors``
    and ``owner_phone_index``). Callers MUST hold a session that has
    NOT entered tenant_scoped_session, or they'll hit empty results.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, *, include_inactive: bool = False) -> Sequence[AuphereOwnerChannel]:
        stmt = select(AuphereOwnerChannel).order_by(
            AuphereOwnerChannel.is_default.desc(),
            AuphereOwnerChannel.display_name.asc(),
        )
        if not include_inactive:
            stmt = stmt.where(AuphereOwnerChannel.active.is_(True))
        rows = await self._session.execute(stmt)
        return rows.scalars().all()

    async def get_by_id(
        self, channel_id: uuid.UUID
    ) -> AuphereOwnerChannel | None:
        return await self._session.get(AuphereOwnerChannel, channel_id)

    async def get_by_phone(
        self, phone_e164: str, *, only_active: bool = True
    ) -> AuphereOwnerChannel | None:
        """Inbound webhook entry point — given the ``to`` field of the
        incoming message, find the channel row. Active-only by default
        so a deactivated number's traffic is rejected (204) at the
        webhook layer."""
        stmt = select(AuphereOwnerChannel).where(
            AuphereOwnerChannel.phone_e164 == phone_e164
        )
        if only_active:
            stmt = stmt.where(AuphereOwnerChannel.active.is_(True))
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def get_default(
        self, *, provider: str = "ycloud"
    ) -> AuphereOwnerChannel | None:
        """Resolver fallback — the row marked ``is_default=true`` for
        the provider. The partial unique index guarantees at most one
        per provider; returns ``None`` when the registry is empty for
        that provider."""
        row = await self._session.execute(
            select(AuphereOwnerChannel).where(
                AuphereOwnerChannel.provider == provider,
                AuphereOwnerChannel.is_default.is_(True),
                AuphereOwnerChannel.active.is_(True),
            )
        )
        return row.scalar_one_or_none()


def _to_resolved(
    channel: AuphereOwnerChannel,
) -> ResolvedAuphereChannel:
    """Wrap an ORM row in the value object. The Fernet column's
    ``__get__`` returns ``bytes | None``; we decode to UTF-8 because
    the upstream signature helpers expect ``str``."""
    secret_raw = channel.webhook_secret_encrypted
    secret = secret_raw.decode("utf-8") if secret_raw else None
    return ResolvedAuphereChannel(
        phone_e164=channel.phone_e164,
        provider=channel.provider,
        provider_phone_id=channel.provider_phone_id,
        webhook_secret=secret,
        channel_id=channel.id,
        display_name=channel.display_name,
    )


def _legacy_fallback() -> ResolvedAuphereChannel | None:
    """Build a ResolvedAuphereChannel from the legacy
    ``settings.auphere_owner_phone`` — preserves Phase 1 behaviour when
    the registry is empty. Returns ``None`` when even the settings are
    unset (the backchannel is simply disabled)."""
    settings = get_settings()
    if not settings.auphere_owner_phone:
        return None
    return ResolvedAuphereChannel(
        phone_e164=settings.auphere_owner_phone,
        provider="ycloud",  # Phase 1 only ever ran on YCloud
        provider_phone_id=settings.auphere_owner_number_id,
        webhook_secret=None,  # caller uses settings.ycloud_webhook_secret
        channel_id=None,
        display_name="Auphere (legacy settings)",
    )


async def resolve_channel_for_inbound(
    session: AsyncSession, *, to_phone: str
) -> ResolvedAuphereChannel | None:
    """Inbound webhook resolution.

    1. Try the registry by ``to_phone``. If hit + active → use it.
    2. Else, if ``to_phone`` matches the legacy
       ``settings.auphere_owner_phone`` → return the legacy fallback
       (Phase 1 compatibility).
    3. Else, ``None`` — webhook returns 204 (foreign destination).
    """
    repo = AuphereChannelRepository(session)
    row = await repo.get_by_phone(to_phone)
    if row is not None:
        return _to_resolved(row)
    legacy = _legacy_fallback()
    if legacy is not None and legacy.phone_e164 == to_phone:
        return legacy
    return None


async def resolve_channel_for_owner(
    session: AsyncSession,
    *,
    owner: OwnerPhoneIndex,
    provider: str = "ycloud",
) -> ResolvedAuphereChannel | None:
    """Outbound resolution — when the dispatcher needs to send a
    template TO an owner, decide which Auphere number to send FROM.

    1. If ``owner.auphere_channel_id`` is set → load that row (must be
       active).
    2. Else load the provider's default channel.
    3. Else fall back to ``settings.auphere_owner_phone``.
    4. Else ``None`` — backchannel disabled.
    """
    repo = AuphereChannelRepository(session)
    if owner.auphere_channel_id is not None:
        pinned = await repo.get_by_id(owner.auphere_channel_id)
        if pinned is not None and pinned.active:
            return _to_resolved(pinned)
    default = await repo.get_default(provider=provider)
    if default is not None:
        return _to_resolved(default)
    return _legacy_fallback()
