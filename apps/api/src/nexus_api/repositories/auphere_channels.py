"""Repository + resolver for ``auphere_owner_channels`` (migration 0038).

Centralises the lookups the webhook + outbox + admin endpoints all need:

- :meth:`AuphereChannelRepository.get_by_phone` — given the E.164 of an
  incoming WhatsApp message's destination.
- :meth:`AuphereChannelRepository.get_by_provider_phone_id` — for the
  Meta webhook, given the ``metadata.phone_number_id`` of the event.
- :meth:`AuphereChannelRepository.get_default` — fallback when an
  ``OwnerPhoneIndex`` row carries no explicit ``auphere_channel_id``.
- :func:`resolve_channel_for_owner` — combines the lookups so callers
  don't repeat the if-else dance.

The resolver returns a :class:`ResolvedAuphereChannel` value object with
the decrypted Meta access token ready for :class:`MetaClient` sends.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuphereOwnerChannel, OwnerPhoneIndex


@dataclass(frozen=True)
class ResolvedAuphereChannel:
    """A backchannel number ready to use.

    ``provider_phone_id`` is the Meta ``phone_number_id``;
    ``access_token`` is the DECRYPTED system-user token (BISUAT) for
    sends from this number — ``None`` means the channel can receive but
    not send (operator must finish setup in the panel).
    """

    phone_e164: str
    provider: str
    provider_phone_id: str | None
    access_token: str | None
    channel_id: uuid.UUID
    display_name: str

    @property
    def can_send(self) -> bool:
        return bool(self.provider_phone_id and self.access_token)


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

    async def get_by_id(self, channel_id: uuid.UUID) -> AuphereOwnerChannel | None:
        return await self._session.get(AuphereOwnerChannel, channel_id)

    async def get_by_phone(
        self, phone_e164: str, *, only_active: bool = True
    ) -> AuphereOwnerChannel | None:
        """Given the destination phone of an incoming message, find the
        channel row. Active-only by default so a deactivated number's
        traffic is rejected at the webhook layer."""
        stmt = select(AuphereOwnerChannel).where(AuphereOwnerChannel.phone_e164 == phone_e164)
        if only_active:
            stmt = stmt.where(AuphereOwnerChannel.active.is_(True))
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def get_by_provider_phone_id(
        self, provider_phone_id: str, *, only_active: bool = True
    ) -> AuphereOwnerChannel | None:
        """Meta webhook entry point — given ``metadata.phone_number_id``
        of the incoming event, find the Auphere channel row. ``None``
        means the event belongs to a tenant channel, not the
        backchannel."""
        stmt = select(AuphereOwnerChannel).where(
            AuphereOwnerChannel.provider_phone_id == provider_phone_id
        )
        if only_active:
            stmt = stmt.where(AuphereOwnerChannel.active.is_(True))
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def get_default(self, *, provider: str = "meta") -> AuphereOwnerChannel | None:
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
    the Meta client expects ``str``."""
    token_raw = channel.access_token_encrypted
    token = token_raw.decode("utf-8") if token_raw else None
    return ResolvedAuphereChannel(
        phone_e164=channel.phone_e164,
        provider=channel.provider,
        provider_phone_id=channel.provider_phone_id,
        access_token=token,
        channel_id=channel.id,
        display_name=channel.display_name,
    )


async def resolve_channel_for_inbound(
    session: AsyncSession, *, provider_phone_id: str
) -> ResolvedAuphereChannel | None:
    """Inbound webhook resolution by Meta ``phone_number_id``.

    Returns ``None`` when the phone_number_id doesn't belong to any
    active Auphere channel — the caller treats the event as regular
    tenant traffic.
    """
    repo = AuphereChannelRepository(session)
    row = await repo.get_by_provider_phone_id(provider_phone_id)
    if row is not None:
        return _to_resolved(row)
    return None


# ── membership cache for the webhook hot path ─────────────────────────────

# El registro de números de Auphere es diminuto (un puñado de filas) y
# cambia cuando un humano registra un número, no con el tráfico. El
# webhook, en cambio, preguntaba a la base por CADA mensaje entrante —
# y para el 100% del tráfico de tenants la respuesta era "no". Un ida y
# vuelta a Postgres por mensaje para confirmar un negativo.
_PHONE_IDS_KEY = "nexus:auphere:inbound_phone_ids"
# Corto y además invalidado a mano desde el admin: el TTL es la red de
# seguridad para una invalidación perdida, no el mecanismo principal.
_PHONE_IDS_TTL_S = 60


async def _active_phone_ids(session: AsyncSession, redis: Redis) -> frozenset[str] | None:
    """Conjunto de ``phone_number_id`` de canales Auphere activos.

    ``None`` significa "no se pudo saber" (Redis caído): el llamante debe
    caer al camino de siempre. Nunca se devuelve un conjunto vacío por
    error — un vacío inventado desviaría el backchannel al flujo de
    tenants, donde no resuelve y el evento se descarta en silencio.
    """
    try:
        cached = await redis.get(_PHONE_IDS_KEY)
    except Exception:
        return None
    if cached is not None:
        raw = cached.decode() if isinstance(cached, bytes) else cached
        try:
            return frozenset(json.loads(raw))
        except (ValueError, TypeError):
            pass  # Cache corrupta: se recalcula abajo.

    # El ``None`` se filtra: una fila sin ``provider_phone_id`` es un canal
    # a medio configurar y no puede coincidir con ningún evento entrante.
    ids = {
        phone_id
        for phone_id in (
            await session.execute(
                select(AuphereOwnerChannel.provider_phone_id).where(
                    AuphereOwnerChannel.active.is_(True)
                )
            )
        )
        .scalars()
        .all()
        if phone_id
    }
    # El vacío SÍ se cachea: "no hay backchannel configurado" es una
    # respuesta legítima y frecuente, y volver a preguntarla en cada
    # mensaje es justo lo que esto viene a evitar.
    with contextlib.suppress(Exception):
        await redis.setex(_PHONE_IDS_KEY, _PHONE_IDS_TTL_S, json.dumps(sorted(ids)))
    return frozenset(ids)


async def resolve_channel_for_inbound_cached(
    session: AsyncSession, redis: Redis, *, provider_phone_id: str
) -> ResolvedAuphereChannel | None:
    """Igual que :func:`resolve_channel_for_inbound`, pero sin tocar la
    base cuando el número no es de Auphere — que es el caso normal.

    La consulta completa (con el token descifrado) solo se hace cuando el
    número SÍ está en el conjunto, así que el camino del backchannel se
    comporta exactamente igual que antes.
    """
    known = await _active_phone_ids(session, redis)
    if known is not None and provider_phone_id not in known:
        return None
    return await resolve_channel_for_inbound(session, provider_phone_id=provider_phone_id)


async def invalidate_inbound_phone_ids(redis: Redis) -> None:
    """Llamar tras alta, baja o cambio de estado de un canal Auphere.

    Sin esto, un número recién registrado tardaría hasta un TTL en ser
    reconocido y sus mensajes se irían al flujo de tenants, donde no
    resuelven y se descartan con un log de ``channel.unresolved_event``.
    """
    with contextlib.suppress(Exception):
        await redis.delete(_PHONE_IDS_KEY)


async def resolve_channel_for_owner(
    session: AsyncSession,
    *,
    owner: OwnerPhoneIndex,
    provider: str = "meta",
) -> ResolvedAuphereChannel | None:
    """Outbound resolution — when the dispatcher needs to send a
    template TO an owner, decide which Auphere number to send FROM.

    1. If ``owner.auphere_channel_id`` is set → load that row (must be
       active).
    2. Else load the provider's default channel.
    3. Else ``None`` — backchannel disabled.
    """
    repo = AuphereChannelRepository(session)
    if owner.auphere_channel_id is not None:
        pinned = await repo.get_by_id(owner.auphere_channel_id)
        if pinned is not None and pinned.active:
            return _to_resolved(pinned)
    default = await repo.get_default(provider=provider)
    if default is not None:
        return _to_resolved(default)
    return None
