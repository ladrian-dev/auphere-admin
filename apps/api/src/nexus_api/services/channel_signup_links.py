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

MODES = ("coexistence", "cloud_api")


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
    session: AsyncSession, *, tenant_id: uuid.UUID, mode: str, actor: str
) -> MintedLink:
    """A new link for the client. Earlier unused links of the client stay valid."""
    if mode not in MODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown_mode")
    token = secrets.token_urlsafe(32)
    link = ChannelSignupLink(
        tenant_id=tenant_id,
        token_hash=hash_token(token),
        channel="whatsapp",
        mode=mode,
        created_by=actor,
        expires_at=datetime.now(UTC) + CHANNEL_SIGNUP_LINK_TTL,
    )
    session.add(link)
    await session.flush()
    await AuditRepository(session).record(
        actor=actor,
        action="channel.signup_link.created",
        target=f"tenant:{tenant_id}",
        before=None,
        after={"link_id": str(link.id), "mode": mode, "expires_at": link.expires_at.isoformat()},
    )
    return MintedLink(link=link, token=token, url=link_url(token))


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
            payload=payload,
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
    if partner is not None:
        await activate_tenant_if_ready(session, partner=partner, tenant_id=tenant.id)
    link.consumed_at = datetime.now(UTC)
    link.channel_id = result.channel_id
    return LinkConnected(
        channel_id=result.channel_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
    )
