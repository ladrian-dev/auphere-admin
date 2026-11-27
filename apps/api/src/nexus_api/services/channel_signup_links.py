"""Shareable signup links: the owner connects a channel themselves.

The operator (panel) or a partner member (console) mints a link for one
client. The business owner opens it on their own phone or computer — where
they are already logged in to Meta — and connects there.

- **WhatsApp** (spec 040): Embedded Signup, then the console's own path:
  quota, ``complete_meta_signup``, «number in use» as a clean 409, the
  ``whatsapp_meta`` connector row, and the client activated when it can serve.
- **Instagram and Messenger** (spec 085): the console's own connection of
  spec 049 (:class:`MetaSocialConnector`), with the pending account choice
  tied to this link (``origin = link:{id}``), and no number quota.

One link per channel. The token is 32 random bytes shown once; only its
SHA-256 is stored. A link works once, for :data:`CHANNEL_SIGNUP_LINK_TTL`,
and can be revoked.
"""

from __future__ import annotations

import dataclasses
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

import sqlalchemy as sa
import structlog
from fastapi import HTTPException, status
from nexus_channels.meta_social.connect import ConnectableAccount, ConnectOutcome
from nexus_channels.whatsapp_meta import SignupIngressPayload
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import (
    CHANNEL_SIGNUP_LINK_TTL,
    Channel,
    ChannelSignupLink,
    Partner,
    Tenant,
)
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services import meta_social_service
from nexus_api.services.channel_quota import count_connected_channels, is_reconnect
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.meta_signup_service import complete_meta_signup
from nexus_api.services.partner_provisioning import activate_tenant_if_ready

log = structlog.get_logger(__name__)

#: The UNIQUE that says «this number already belongs to a client» (spec 021).
_NUMBER_UNIQUE = "uq_channels_live_number"

MODES = ("coexistence", "cloud_api", "whatsapp_login")
#: Spec 085: the channels a link connects, one per link.
CHANNELS = ("whatsapp", "instagram", "messenger")
META_SOCIAL_CHANNELS = ("instagram", "messenger")
#: The only mode of an Instagram or Messenger link: the owner signs in to Meta
#: and picks how on their page (spec 085, 1.3 and 2.2).
META_LOGIN = "meta_login"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_url(token: str, channel: str = "whatsapp") -> str:
    """The page lives on the console: its domain is the one Meta allows."""
    base = get_settings().console_base_url.rstrip("/")
    return f"{base}/connect/{channel}/{token}"


@dataclass(frozen=True)
class MintedLink:
    link: ChannelSignupLink
    token: str
    url: str


async def mint_link(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    mode: str | None = None,
    actor: str,
    agent_id: uuid.UUID | None = None,
    replace: bool = False,
    channel: str = "whatsapp",
) -> MintedLink:
    """A new link for the client and channel. It replaces the earlier unused
    ones of that channel.

    One live link per client (owner, 2026-10-20): every «Enviar enlace» used
    to leave another valid link around, and nobody could tell which one the
    owner had. The earlier ones are revoked here, each with its audit row.
    Spec 085: per channel — an Instagram link leaves a WhatsApp one alive.
    """
    if channel not in CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_channel"
        )
    if channel in META_SOCIAL_CHANNELS:
        # The owner picks how to sign in on their page; the partner picks nothing.
        if mode not in (None, META_LOGIN):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_mode"
            )
        mode = META_LOGIN
    elif mode not in MODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_mode")
    if mode == "whatsapp_login" and not await whatsapp_login_allowed(session, tenant_id):
        # Spec 047 (31.5): la beta solo donde Auphere la activó, nunca en la UE.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "whatsapp_login_unavailable"}
        )
    assert mode is not None
    live = await live_links(session, tenant_id, channel=channel)
    if agent_id is not None:
        # Spec 047 (31.2): como mucho un enlace pendiente por agente; crear otro
        # ofrece revocar el pendiente («Revocar y crear»). Spec 085: por agente
        # y canal.
        pending = [link for link in live if link.agent_id == agent_id]
        if pending and not replace:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "link_pending_exists", "link_id": str(pending[0].id)},
            )
        # An expired link was never revoked nor used, so the one-pending index
        # still counts it (it cannot test ``now()``): put it away first, or the
        # INSERT below fails.
        for stale in await _expired_pending(session, tenant_id, agent_id, channel):
            await revoke_link(session, stale, actor=actor, reason="expired")
        earlier_links = pending
    else:
        earlier_links = live
    for earlier in earlier_links:
        await revoke_link(session, earlier, actor=actor, reason="replaced")
    token = secrets.token_urlsafe(32)
    link = ChannelSignupLink(
        tenant_id=tenant_id,
        token_hash=hash_token(token),
        channel=channel,
        mode=mode,
        created_by=actor,
        expires_at=datetime.now(UTC) + CHANNEL_SIGNUP_LINK_TTL,
        agent_id=agent_id,
    )
    session.add(link)
    await session.flush()
    await AuditRepository(session).record(
        actor=actor,
        action="channel.signup_link.created",
        target=f"tenant:{tenant_id}",
        before=None,
        after={
            "link_id": str(link.id),
            "channel": channel,
            "mode": mode,
            "agent_id": str(agent_id) if agent_id else None,
            "expires_at": link.expires_at.isoformat(),
        },
    )
    return MintedLink(link=link, token=token, url=link_url(token, channel))


async def _expired_pending(
    session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID, channel: str
) -> list[ChannelSignupLink]:
    rows = (
        await session.execute(
            sa.select(ChannelSignupLink)
            .where(
                ChannelSignupLink.tenant_id == tenant_id,
                ChannelSignupLink.agent_id == agent_id,
                ChannelSignupLink.channel == channel,
                ChannelSignupLink.revoked_at.is_(None),
                ChannelSignupLink.consumed_at.is_(None),
                ChannelSignupLink.expires_at <= datetime.now(UTC),
            )
            .with_for_update()
        )
    ).scalars()
    return list(rows)


async def whatsapp_login_allowed(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """La beta «WhatsApp login» (31.5): el país del negocio está en la lista que
    activa Auphere. La lista nunca tiene un país de la UE o del EEE (CHECK)."""
    from nexus_api.db.models import WhatsappLoginBetaCountry
    from nexus_api.db.models.business import BusinessProfile

    country = await session.scalar(
        sa.select(BusinessProfile.country).where(BusinessProfile.tenant_id == tenant_id)
    )
    if not country:
        return False
    found = await session.scalar(
        sa.select(WhatsappLoginBetaCountry.country).where(
            WhatsappLoginBetaCountry.country == str(country).upper()
        )
    )
    return found is not None


async def live_links(
    session: AsyncSession, tenant_id: uuid.UUID, *, channel: str | None = None
) -> list[ChannelSignupLink]:
    """The client's links that still work: not used, not revoked, not expired.
    With ``channel``, only that channel's (spec 085)."""
    query = sa.select(ChannelSignupLink).where(
        ChannelSignupLink.tenant_id == tenant_id,
        ChannelSignupLink.revoked_at.is_(None),
        ChannelSignupLink.consumed_at.is_(None),
        ChannelSignupLink.expires_at > datetime.now(UTC),
    )
    if channel is not None:
        query = query.where(ChannelSignupLink.channel == channel)
    rows = (await session.execute(query.with_for_update())).scalars()
    return list(rows)


async def recent_links(
    session: AsyncSession, tenant_id: uuid.UUID, *, limit: int = 20
) -> list[ChannelSignupLink]:
    rows = (
        await session.execute(
            sa.select(ChannelSignupLink)
            .where(ChannelSignupLink.tenant_id == tenant_id)
            .order_by(ChannelSignupLink.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return list(rows)


async def revoke_link(
    session: AsyncSession, link: ChannelSignupLink, *, actor: str, reason: str = "revoked"
) -> bool:
    """Revoke a link that still works. Returns False if it was already done."""
    if link.revoked_at is not None or link.consumed_at is not None:
        return False
    link.revoked_at = datetime.now(UTC)
    await AuditRepository(session).record(
        actor=actor,
        action="channel.signup_link.revoked",
        target=f"tenant:{link.tenant_id}",
        before=None,
        after={"link_id": str(link.id), "reason": reason},
    )
    return True


def link_state(link: ChannelSignupLink | None, now: datetime | None = None) -> str:
    """``valid``, ``used``, ``revoked``, ``expired`` or ``unknown``."""
    if link is None:
        return "unknown"
    now = now or datetime.now(UTC)
    if link.revoked_at is not None:
        return "revoked"
    if link.consumed_at is not None:
        return "used"
    if link.expires_at <= now:
        return "expired"
    return "valid"


async def find_link(session: AsyncSession, token: str) -> ChannelSignupLink | None:
    found: ChannelSignupLink | None = await session.scalar(
        sa.select(ChannelSignupLink).where(ChannelSignupLink.token_hash == hash_token(token))
    )
    return found


def require_valid(link: ChannelSignupLink | None) -> ChannelSignupLink:
    state = link_state(link)
    if state != "valid" or link is None:
        # 404 for an unknown token (never says whether it existed); 410 for
        # one that did and no longer works, with the reason for the page.
        raise HTTPException(
            status_code=(status.HTTP_404_NOT_FOUND if state == "unknown" else status.HTTP_410_GONE),
            detail={"code": f"link_{state}"},
        )
    return link


async def announce_connected(
    *, tenant_id: uuid.UUID, channel_id: uuid.UUID, agent_id: uuid.UUID | None
) -> None:
    """El partner se entera de que el dueño completó el enlace (31.1)."""
    from nexus_api.services.channel_config import announce

    await announce(
        tenant_id=tenant_id,
        kind="channel.connected",
        data={
            "channel_id": str(channel_id),
            "agent_id": str(agent_id) if agent_id else None,
            "via": "owner_link",
        },
    )


@dataclass(frozen=True)
class LinkConnected:
    channel_id: uuid.UUID
    display_phone_number: str | None
    mode: str


async def connect_with_link(
    session: AsyncSession,
    redis: Redis,
    *,
    link: ChannelSignupLink,
    payload: SignupIngressPayload,
) -> LinkConnected:
    """The signup, inside the client's tenant scope already set on ``session``."""
    tenant = await session.get(Tenant, link.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "link_unknown"})
    partner = await session.get(Partner, tenant.partner_id) if tenant.partner_id else None
    if partner is not None:
        # The console's rule (``services/channel_quota``): Instagram and
        # Messenger do not take a number's slot (spec 049), and authorising
        # again a number this client already has is not another one (076, 4.3).
        used = await count_connected_channels(session)
        if used >= partner.max_channels_per_client and not await is_reconnect(
            session, payload.phone_number_id
        ):
            # Before Meta is called: the code stays unused for a retry.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail={"code": "channel_quota_full"}
            )
    actor = f"link:{link.id}"
    try:
        bundle = await complete_meta_signup(
            session=session,
            redis=redis,
            # «WhatsApp login» registra un número de Cloud API.
            payload=(
                dataclasses.replace(payload, mode="cloud_api")
                if payload.mode == "whatsapp_login"
                else payload
            ),
            tenant_id=tenant.id,
            actor=actor,
            audit_action="channel.signup_link.connect",
        )
        await session.flush()
    except IntegrityError as exc:
        if _NUMBER_UNIQUE not in str(exc.orig or exc):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "number_in_use"}
        ) from None
    result = bundle.result
    # The panel shows WhatsApp through its connector row too (Block J). The
    # channel is the truth; a catalog without ``whatsapp_meta`` (a bare test
    # database) must not undo a number Meta already registered.
    try:
        await connector_service.bootstrap_webhook_manual(
            session,
            tenant=tenant,
            connector_slug="whatsapp_meta",
            channel_id=result.channel_id,
            actor=actor,
        )
    except connector_service.ConnectorNotFound:
        log.warning("signup_link.connector_missing", tenant_id=str(tenant.id))
    if link.agent_id is not None:
        # Spec 047 (31.1): el número queda en el agente del enlace y empieza en
        # modo prueba con el número del dueño, que es quien lo conectó (32.9).
        from nexus_api.services.channel_config import start_in_test_mode

        channel = await session.get(Channel, result.channel_id)
        if channel is not None:
            channel.agent_id = link.agent_id
            await start_in_test_mode(
                session, channel, connector_phone=tenant.owner_phone, actor=actor
            )
    if partner is not None:
        await activate_tenant_if_ready(session, partner=partner, tenant_id=tenant.id)
    link.consumed_at = datetime.now(UTC)
    link.channel_id = result.channel_id
    return LinkConnected(
        channel_id=result.channel_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
    )


# ── Spec 085: Instagram and Messenger ────────────────────────────────────────


@dataclass(frozen=True)
class SocialLinkOutcome:
    """What the owner's page learns: connected (with the account's name), or
    the accounts to choose from. Never the channel row nor the tenant."""

    status: Literal["connected", "choose"]
    channel_id: uuid.UUID | None = None
    #: The agent the channel ended on, for the partner's notice.
    agent_id: uuid.UUID | None = None
    display_name: str | None = None
    nonce: str | None = None
    accounts: list[ConnectableAccount] = field(default_factory=list)


def origin_of(link: ChannelSignupLink) -> str:
    """The pending account choice belongs to this link and to nobody else
    (spec 085, 7.3): not the console, not another link of the same client."""
    return f"link:{link.id}"


async def _social_kind(session: AsyncSession, link: ChannelSignupLink) -> meta_social_service.Kind:
    """The link's channel, if it is Instagram or Messenger and its client's
    partner has it. A channel the partner does not have is a link that does
    not exist (§V): nothing says why."""
    if link.channel not in META_SOCIAL_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "link_channel_mismatch"}
        )
    kind = cast(meta_social_service.Kind, link.channel)
    tenant = await session.get(Tenant, link.tenant_id)
    partner = (
        await session.get(Partner, tenant.partner_id) if tenant and tenant.partner_id else None
    )
    if tenant is None or kind not in meta_social_service.enabled_kinds(partner):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "link_unknown"})
    return kind


async def connect_meta_social_with_link(
    session: AsyncSession, redis: Redis, *, link: ChannelSignupLink, code: str
) -> SocialLinkOutcome:
    """The console's own Instagram / Messenger connection (spec 049), run for
    the link's client inside the tenant scope already set on ``session``, with
    the link locked. No number quota (spec 049; 085, 6.1). Several accounts:
    the choice waits, tied to this link, and the link stays valid."""
    kind = await _social_kind(session, link)
    outcome = await meta_social_service.connector(session, redis).begin(
        kind=kind, code=code, origin=origin_of(link)
    )
    return await _social_outcome(session, link, kind, outcome)


async def complete_meta_social_with_link(
    session: AsyncSession,
    redis: Redis,
    *,
    link: ChannelSignupLink,
    nonce: str,
    account_id: str,
) -> SocialLinkOutcome:
    """The account the owner picked, only from the link that began the choice."""
    kind = await _social_kind(session, link)
    outcome = await meta_social_service.connector(session, redis).complete(
        kind=kind, nonce=nonce, account_id=account_id, origin=origin_of(link)
    )
    return await _social_outcome(session, link, kind, outcome)


async def _social_outcome(
    session: AsyncSession,
    link: ChannelSignupLink,
    kind: meta_social_service.Kind,
    outcome: ConnectOutcome,
) -> SocialLinkOutcome:
    if outcome.status == "choose":
        assert outcome.nonce is not None
        return SocialLinkOutcome(status="choose", nonce=outcome.nonce, accounts=outcome.accounts)
    assert outcome.channel_id is not None and outcome.account is not None
    actor = origin_of(link)
    await meta_social_service.audit_connect(
        session, actor=actor, kind=kind, channel_id=outcome.channel_id, account=outcome.account
    )
    channel = await session.get(Channel, outcome.channel_id)
    assert channel is not None
    if link.agent_id is not None:
        await _place_on_agent(session, channel, link.agent_id, actor=actor)
    link.consumed_at = datetime.now(UTC)
    link.channel_id = channel.id
    return SocialLinkOutcome(
        status="connected",
        channel_id=channel.id,
        agent_id=channel.agent_id,
        display_name=meta_social_service.display_name(outcome.account),
    )


async def _place_on_agent(
    session: AsyncSession, channel: Channel, agent_id: uuid.UUID, *, actor: str
) -> None:
    """Spec 085 (R6): the account goes to the link's agent with the console's
    own move. When the console's move would refuse it (an agent no longer
    published, an open audience on an admins-only agent), the account stays
    where it is, as it does in the console: connected to the client."""
    from nexus_api.services import channel_config

    before = channel.agent_id
    try:
        await channel_config.move_channel(session, channel, to_agent_id=agent_id, actor=actor)
    except channel_config.ChannelConfigError as exc:
        channel.agent_id = before
        await session.flush()
        log.info(
            "signup_link.not_placed",
            tenant_id=str(channel.tenant_id),
            channel_id=str(channel.id),
            code=exc.code,
        )
