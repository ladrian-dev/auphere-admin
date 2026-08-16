"""``/console/clients/{ref}/channels`` — channel metadata for a client
(CP-17: overview + roles; connecting lives in ``whatsapp.py``).

What a partner sees per channel: type, provider, identifier (the
WhatsApp number they already know), status, role and the Meta health
snapshot kept in ``channels.config`` (quality rating, messaging tier,
verified name). Never ``config`` as a whole (it holds provider ids)
and never ``config_encrypted``.

Roles: ``services/channel_routing.py`` refuses a role-based send when
a tenant has more than one active WhatsApp channel and none carries
the requested role — so the console must make tagging obvious.
``PATCH .../channels/{channel_id}/role`` writes ``config.role`` through
the same vocabulary (``CHANNEL_ROLES``) the router reads.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta.credentials import MetaCredentialsRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.channel_routing import channel_agent_enabled, channel_role

from .deps import ClientScope, client_scope
from .schemas import ChannelOut
from .schemas_channels import ChannelDetailOut, ChannelRoleIn, ChannelsOverviewOut

router = APIRouter(prefix="/clients/{ref}/channels")

#: Platform-internal pseudo-channels (the QA playground's ``web`` channel,
#: ``api/qa.py::_QA_CHANNEL_PROVIDER``). Not the partner's, never shown,
#: never counted against ``max_channels_per_client``.
INTERNAL_PROVIDERS: frozenset[str] = frozenset({"qa_playground"})


def _detail(ch: Channel) -> ChannelDetailOut:
    cfg = ch.config or {}

    def _s(key: str) -> str | None:
        v = cfg.get(key)
        return v if isinstance(v, str) and v else None

    return ChannelDetailOut(
        id=ch.id,
        type=ch.type.value,
        provider=ch.provider,
        provider_identifier=ch.provider_identifier,
        status=ch.status.value,
        role=channel_role(ch),
        last_health_check_at=ch.last_health_check_at,
        created_at=ch.created_at,
        quality_rating=_s("quality_rating"),
        messaging_tier=_s("messaging_tier"),
        verified_name=_s("verified_name"),
        mode=_s("mode"),
        agent_enabled=channel_agent_enabled(ch),
    )


async def _all_channels(session: AsyncSession) -> list[Channel]:
    return list(
        (
            await session.execute(
                sa.select(Channel)
                .where(Channel.provider.not_in(INTERNAL_PROVIDERS))
                .order_by(Channel.created_at)
            )
        )
        .scalars()
        .all()
    )


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
            )
        )
        or 0
    )


def roles_required(channels: list[Channel]) -> bool:
    """The refusal condition of ``channel_routing``: >1 active WhatsApp
    channel and at least one untagged."""
    active = [
        c for c in channels if c.type is ChannelType.WHATSAPP and c.status is ChannelStatus.ACTIVE
    ]
    return len(active) > 1 and any(channel_role(c) is None for c in active)


@router.get("", response_model=list[ChannelOut])
async def list_channels(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> list[ChannelOut]:
    rows = await _all_channels(scope.session)
    return [
        ChannelOut(
            id=ch.id,
            type=ch.type.value,
            provider=ch.provider,
            provider_identifier=ch.provider_identifier,
            status=ch.status.value,
            role=channel_role(ch),
            last_health_check_at=ch.last_health_check_at,
            created_at=ch.created_at,
        )
        for ch in rows
    ]


@router.get("/overview", response_model=ChannelsOverviewOut)
async def channels_overview(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> ChannelsOverviewOut:
    rows = await _all_channels(scope.session)
    used = sum(1 for c in rows if c.status is not ChannelStatus.DISCONNECTED)
    limit = scope.principal.partner.max_channels_per_client
    creds = await MetaCredentialsRepository(scope.session).get()
    return ChannelsOverviewOut(
        channels=[_detail(c) for c in rows],
        max_channels=limit,
        used_channels=used,
        can_connect=used < limit,
        roles_required=roles_required(rows),
        meta_connected=creds is not None,
    )


@router.patch("/{channel_id}/role", response_model=ChannelDetailOut)
async def set_channel_role(
    channel_id: uuid.UUID,
    body: ChannelRoleIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelDetailOut:
    ch = await scope.session.get(Channel, channel_id)
    if ch is None:  # RLS hides other tenants' rows → same 404 as "no such row"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    if ch.type is not ChannelType.WHATSAPP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="roles apply to WhatsApp channels only"
        )
    before = channel_role(ch)
    cfg = dict(ch.config or {})
    if body.role is None:
        cfg.pop("role", None)
    else:
        cfg["role"] = body.role
    ch.config = cfg
    flag_modified(ch, "config")
    await scope.session.flush()
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.channel.role",
        target=f"channel:{ch.id}",
        before={"role": before},
        after={"role": body.role, "identifier": ch.provider_identifier},
    )
    return _detail(ch)


__all__ = ["count_connected_channels", "roles_required", "router"]
