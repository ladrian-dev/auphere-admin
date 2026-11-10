"""Shareable WhatsApp signup links (spec 040).

The operator (panel) or a partner member (console) mints a link for one
client. The business owner opens it on their own phone or computer — where
they are already logged in to Meta — and runs Embedded Signup there. The
signup then follows the console's own path: quota, ``complete_meta_signup``,
«number in use» as a clean 409, the ``whatsapp_meta`` connector row, and the
client activated when it can serve.

The token is 32 random bytes shown once; only its SHA-256 is stored. A link
works once, for :data:`CHANNEL_SIGNUP_LINK_TTL`, and can be revoked.
"""

from __future__ import annotations

import dataclasses
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import HTTPException, status
from nexus_channels.whatsapp_meta import SignupIngressPayload
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import (
    CHANNEL_SIGNUP_LINK_TTL,
    Channel,
    ChannelSignupLink,
    ChannelStatus,
    Partner,
    Tenant,
)
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.meta_signup_service import complete_meta_signup
from nexus_api.services.partner_provisioning import activate_tenant_if_ready

log = structlog.get_logger(__name__)

#: The UNIQUE that says «this number already belongs to a client» (spec 021).
_NUMBER_UNIQUE = "uq_channels_live_number"
#: Providers that are not a client's channel (the Playground's).
_INTERNAL_PROVIDERS = ("qa_playground",)

MODES = ("coexistence", "cloud_api", "whatsapp_login")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_url(token: str) -> str:
    """The page lives on the console: its domain is the one Meta allows."""
    base = get_settings().console_base_url.rstrip("/")
    return f"{base}/connect/whatsapp/{token}"


@dataclass(frozen=True)
class MintedLink:
    link: ChannelSignupLink
    token: str
    url: str


async def mint_link(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    mode: str,
    actor: str,
    agent_id: uuid.UUID | None = None,
    replace: bool = False,
) -> MintedLink:
    """A new link for the client. It replaces the client's earlier unused ones.

    One live link per client (owner, 2026-10-20): every «Enviar enlace» used
    to leave another valid link around, and nobody could tell which one the
    owner had. The earlier ones are revoked here, each with its audit row.
    """
    if mode not in MODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_mode")
    if mode == "whatsapp_login" and not await whatsapp_login_allowed(session, tenant_id):
        # Spec 047 (31.5): la beta solo donde Auphere la activó, nunca en la UE.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "whatsapp_login_unavailable"}
        )
    if agent_id is not None:
        # Spec 047 (31.2): como mucho un enlace pendiente por agente; crear otro
        # ofrece revocar el pendiente («Revocar y crear»).
        pending = [
            link for link in await live_links(session, tenant_id) if link.agent_id == agent_id
        ]
        if pending and not replace:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "link_pending_exists", "link_id": str(pending[0].id)},
            )
        earlier_links = pending
    else:
        earlier_links = await live_links(session, tenant_id)
    for earlier in earlier_links:
        await revoke_link(session, earlier, actor=actor, reason="replaced")
    token = secrets.token_urlsafe(32)
    link = ChannelSignupLink(
        tenant_id=tenant_id,
        token_hash=hash_token(token),
        channel="whatsapp",
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
            "mode": mode,
            "agent_id": str(agent_id) if agent_id else None,
            "expires_at": link.expires_at.isoformat(),
        },
    )
    return MintedLink(link=link, token=token, url=link_url(token))


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


async def live_links(session: AsyncSession, tenant_id: uuid.UUID) -> list[ChannelSignupLink]:
    """The client's links that still work: not used, not revoked, not expired."""
    rows = (
        await session.execute(
            sa.select(ChannelSignupLink)
            .where(
                ChannelSignupLink.tenant_id == tenant_id,
                ChannelSignupLink.revoked_at.is_(None),
                ChannelSignupLink.consumed_at.is_(None),
                ChannelSignupLink.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
    ).scalars()
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
        used = int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(Channel)
                .where(
                    Channel.status != ChannelStatus.DISCONNECTED,
                    Channel.provider.not_in(_INTERNAL_PROVIDERS),
                )
            )
            or 0
        )
        if used >= partner.max_channels_per_client:
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
