"""Which of a tenant's WhatsApp channels does an outbound send leave from?

For every tenant in production today the answer is trivial — they have one
active WhatsApp channel — and this module is written so that case behaves
*exactly* as it did before roles existed. The interesting case is a tenant
with two numbers doing different jobs: one line the agent converses on, one
line that only emits notifications to third parties.

Roles live in ``channels.config`` (``role``, ``agent_enabled``) rather than
in dedicated columns. That is a deliberate trade: the column already exists,
is already read on every send, and carries the Meta identifiers next to which
these flags belong. Nothing here needs a migration, and an untagged channel is
indistinguishable from one that predates this module.

The resolution rule
-------------------
1. An explicit ``channel_id`` wins. The caller knows exactly what it wants.
2. Otherwise a requested ``role``, if some active channel carries it.
3. Otherwise the oldest active channel — the historical behaviour.

Step 3 has one exception, and it is the whole safety argument of this module:
**when the tenant has more than one active channel and the requested role
matches none of them, we refuse instead of guessing.** Falling back would mean
a cobranza reminder going out from the line the owner administers on — to
someone else's customer, irreversibly. Refusing means the send fails, an
operator sees why, and tags the channel. One of those is recoverable.

With a single active channel there is no wrong line to pick, so the fallback
stands and every existing tenant is untouched.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Channel, ChannelStatus, ChannelType

log = structlog.get_logger(__name__)

#: The line the agent converses on. Default meaning for an untagged channel.
CHANNEL_ROLE_AGENT = "agent"
#: A send-only line: templates go out, the agent never answers what comes back.
CHANNEL_ROLE_NOTIFICATIONS = "notifications"

CHANNEL_ROLES: frozenset[str] = frozenset({CHANNEL_ROLE_AGENT, CHANNEL_ROLE_NOTIFICATIONS})


class ChannelResolutionError(Exception):
    """No channel could be resolved for this send.

    Carries ``reason`` so callers can map it onto their own error contract —
    the API layer turns it into a 409, the reminder engine into a status
    string the agent reports back to the admin.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def config_role(config: dict[str, Any] | None) -> str | None:
    """The declared role in a raw ``channels.config``, or ``None`` when untagged.

    An unknown string is treated as untagged rather than raising: config is
    operator-editable, and a typo must not take a live channel out of service.
    """
    raw = (config or {}).get("role")
    return raw if isinstance(raw, str) and raw in CHANNEL_ROLES else None


def config_agent_enabled(config: dict[str, Any] | None) -> bool:
    """Whether inbound on a channel with this config reaches the agent pipeline.

    Defaults to ``True`` — absent config means "behave as always". Only an
    explicit ``false`` makes a channel send-only. A channel tagged
    ``notifications`` does NOT imply it by itself: the two flags answer
    different questions (which line do I send FROM, versus does this line
    answer), and conflating them would make one of them impossible to express —
    a business could legitimately want its notification line to also reply.

    Takes the raw dict rather than a ``Channel`` because the inbound dispatcher
    reads just this column, and loading the whole row to answer a boolean would
    be a second query on the hot path of every single turn.
    """
    return (config or {}).get("agent_enabled") is not False


def channel_role(channel: Channel) -> str | None:
    """:func:`config_role` for a loaded channel row."""
    return config_role(channel.config)


def channel_agent_enabled(channel: Channel) -> bool:
    """:func:`config_agent_enabled` for a loaded channel row."""
    return config_agent_enabled(channel.config)


async def active_whatsapp_channels(
    session: AsyncSession, *, provider: str | None = None
) -> list[Channel]:
    """Every active WhatsApp channel of the current tenant, oldest first.

    No tenant filter in the SQL: RLS scopes the query, and per the isolation
    rules the tenant is never taken from a caller argument. ``require_current_
    tenant`` is the tripwire for the failure mode that would otherwise be
    silent — a caller that forgot ``tenant_scoped_session`` would run this
    unscoped and get *every* tenant's channels back, then send from one of
    them. Raising beats resolving the wrong WABA.

    Ordering is explicit so callers that fall back to "the first one" are
    deterministic across worker replicas.
    """
    require_current_tenant()
    stmt = sa.select(Channel).where(
        Channel.type == ChannelType.WHATSAPP,
        Channel.status == ChannelStatus.ACTIVE,
    )
    if provider is not None:
        stmt = stmt.where(Channel.provider == provider)
    result = await session.execute(stmt.order_by(Channel.created_at.asc()))
    return list(result.scalars())


async def resolve_whatsapp_channel(
    session: AsyncSession,
    *,
    role: str | None = None,
    channel_id: uuid.UUID | None = None,
    provider: str | None = None,
    purpose: str = "send",
) -> Channel:
    """Resolve the channel a business-initiated send should leave from.

    Raises :class:`ChannelResolutionError` rather than returning ``None`` —
    every caller has to handle the failure, and an exception makes forgetting
    impossible.
    """
    channels = await active_whatsapp_channels(session, provider=provider)

    if channel_id is not None:
        chosen = next((c for c in channels if c.id == channel_id), None)
        if chosen is None:
            log.warning(
                "channel.resolve.explicit_not_active",
                purpose=purpose,
                requested_channel_id=str(channel_id),
                candidates=[str(c.id) for c in channels],
            )
            raise ChannelResolutionError(
                "channel_not_available",
                f"channel {channel_id} is not an active WhatsApp channel for this tenant",
            )
        log.info(
            "channel.resolved",
            purpose=purpose,
            via="explicit",
            channel_id=str(chosen.id),
            identifier=chosen.provider_identifier,
        )
        return chosen

    if not channels:
        # Distinguish "no WhatsApp at all" from "one exists but is paused" —
        # the second is a one-click fix an operator can only make if the log
        # says the channel is sitting there.
        any_whatsapp = await session.execute(
            sa.select(Channel.id, Channel.status).where(Channel.type == ChannelType.WHATSAPP)
        )
        rows = list(any_whatsapp)
        log.warning(
            "channel.resolve.not_connected",
            purpose=purpose,
            whatsapp_channels_total=len(rows),
            statuses=[str(status) for _cid, status in rows],
        )
        raise ChannelResolutionError("whatsapp_not_connected", "whatsapp_not_connected")

    if role is not None:
        matching = [c for c in channels if channel_role(c) == role]
        if matching:
            if len(matching) > 1:
                log.warning(
                    "channel.resolve.ambiguous_role",
                    purpose=purpose,
                    role=role,
                    chosen_channel_id=str(matching[0].id),
                    candidates=[str(c.id) for c in matching],
                )
            log.info(
                "channel.resolved",
                purpose=purpose,
                via="role",
                role=role,
                channel_id=str(matching[0].id),
                identifier=matching[0].provider_identifier,
            )
            return matching[0]
        if len(channels) > 1:
            # The refusal described in the module docstring. Guessing here
            # sends someone else's customer a message from the wrong number.
            log.error(
                "channel.resolve.role_unassigned",
                purpose=purpose,
                role=role,
                candidates=[str(c.id) for c in channels],
                identifiers=[c.provider_identifier for c in channels],
                hint=(
                    f"tenant has {len(channels)} active WhatsApp channels and none is "
                    f"tagged role={role!r} — tag one in the operator panel"
                ),
            )
            raise ChannelResolutionError(
                "channel_role_unassigned",
                (
                    f"this tenant has {len(channels)} active WhatsApp numbers and none is "
                    f"assigned the {role!r} role — assign one before sending"
                ),
            )

    if len(channels) > 1:
        log.warning(
            "channel.resolve.ambiguous",
            purpose=purpose,
            chosen_channel_id=str(channels[0].id),
            chosen_identifier=channels[0].provider_identifier,
            candidates=[str(c.id) for c in channels],
            identifiers=[c.provider_identifier for c in channels],
        )
    log.info(
        "channel.resolved",
        purpose=purpose,
        via="default",
        channel_id=str(channels[0].id),
        identifier=channels[0].provider_identifier,
    )
    return channels[0]


def describe_channel(channel: Channel) -> dict[str, Any]:
    """Compact identity of a channel for logs and API payloads."""
    return {
        "channel_id": str(channel.id),
        "identifier": channel.provider_identifier,
        "role": channel_role(channel),
        "agent_enabled": channel_agent_enabled(channel),
    }


__all__ = [
    "CHANNEL_ROLES",
    "CHANNEL_ROLE_AGENT",
    "CHANNEL_ROLE_NOTIFICATIONS",
    "ChannelResolutionError",
    "active_whatsapp_channels",
    "channel_agent_enabled",
    "channel_role",
    "config_agent_enabled",
    "config_role",
    "describe_channel",
    "resolve_whatsapp_channel",
]
