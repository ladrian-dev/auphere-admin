"""La cuota de números de WhatsApp de un cliente (``partners.max_channels_per_client``).

Una sola regla para los dos caminos que conectan un número: la consola
(``api/console/whatsapp.py``) y el enlace del dueño
(``services/channel_signup_links.py``). Antes, el enlace tenía su propia copia,
que contaba Instagram y Messenger y no dejaba volver a autorizar un número
(bug ``el-enlace-cuenta-instagram-como-numero``).

Las dos funciones corren dentro del ámbito del cliente: la RLS solo deja ver
sus canales, y ninguna acepta un ``tenant_id``.
"""

from __future__ import annotations

import sqlalchemy as sa
from nexus_channels.meta_social import META_SOCIAL_PROVIDERS
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Channel, ChannelStatus, ChannelType

#: Platform-internal pseudo-channels (the QA playground's ``web`` channel,
#: ``api/qa.py::_QA_CHANNEL_PROVIDER``). Not the partner's, never shown,
#: never counted against ``max_channels_per_client``.
INTERNAL_PROVIDERS: frozenset[str] = frozenset({"qa_playground"})


async def count_connected_channels(session: AsyncSession) -> int:
    """Channels that count against ``partners.max_channels_per_client``:
    every row that is not ``disconnected``. Must run inside the tenant scope."""
    return int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Channel)
            .where(
                Channel.status != ChannelStatus.DISCONNECTED,
                Channel.provider.not_in(INTERNAL_PROVIDERS),
                # Spec 049: the quota is WhatsApp numbers; an Instagram
                # account or a Page does not take a number's slot.
                Channel.provider.not_in(tuple(META_SOCIAL_PROVIDERS)),
            )
        )
        or 0
    )


async def is_reconnect(session: AsyncSession, phone_number_id: str | None) -> bool:
    """Whether ``phone_number_id`` is already a connected WhatsApp number of
    this client (spec 076, 4.3): authorising it again is not connecting
    another one. Must run inside the tenant scope."""
    if not phone_number_id:
        return False
    found = await session.scalar(
        sa.select(Channel.id)
        .where(
            Channel.type == ChannelType.WHATSAPP,
            Channel.status != ChannelStatus.DISCONNECTED,
            Channel.config["phone_number_id"].astext == phone_number_id,
        )
        .limit(1)
    )
    return found is not None


__all__ = ["INTERNAL_PROVIDERS", "count_connected_channels", "is_reconnect"]
