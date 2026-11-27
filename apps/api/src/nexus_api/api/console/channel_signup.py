"""``/console/channel-signup/{token}`` — the owner connects a channel from a link.

WhatsApp since spec 040; Instagram and Messenger since spec 085.

The business owner has no account: the link's token is what authorizes the
signup. It is single use, expires and can be revoked
(``services/channel_signup_links``), and each token has its own small rate
limit. Like every other ``/console/*`` route the API never answers it
without a credential: the console's server calls it with its **service**
token (``require_console_service``), the same way it serves invitations and
password resets — the API surface stays closed to the internet.

``GET`` tells the page who the link is for, which channel it connects and
how to open Meta's popup. ``POST`` takes what Meta's Embedded Signup returned
and connects the number under the client's own tenant scope.

Spec 085: ``POST …/meta-social`` takes the single-use code of Facebook Login
for Business and runs the console's own Instagram / Messenger connection;
``POST …/meta-social/complete`` connects the account the owner picked, only
for the link that began the choice. Neither takes nor returns a tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.meta_social import MetaSocialConnectError
from nexus_channels.whatsapp_meta import SignupIngressPayload
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_redis
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.core.rate_limit import allow
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ChannelSignupLink, Partner, Tenant
from nexus_api.services import meta_social_service
from nexus_api.services.channel_signup_links import (
    META_SOCIAL_CHANNELS,
    SocialLinkOutcome,
    announce_connected,
    complete_meta_social_with_link,
    connect_meta_social_with_link,
    connect_with_link,
    find_link,
    hash_token,
    link_state,
    require_valid,
)

from .meta_social import AccountOut, CompleteIn, ConnectIn

router = APIRouter(prefix="/channel-signup")

#: Calls per minute and token: the page needs two or three.
_PER_MINUTE = 10


class LinkInfoOut(BaseModel):
    state: str
    business_name: str | None = None
    #: Spec 085: ``whatsapp``, ``instagram`` or ``messenger``.
    channel: str | None = None
    mode: str | None = None
    expires_at: datetime | None = None
    meta_app_id: str | None = None
    meta_config_id: str | None = None
    meta_graph_version: str | None = None
    meta_signup_version: str | None = None
    #: Spec 085 (081): Instagram's configuration with the linked Facebook Page,
    #: when the environment has it. The owner chooses between the two.
    meta_page_config_id: str | None = None


class LinkSignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=2048)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str | None = Field(default=None, max_length=64)
    business_id: str | None = Field(default=None, max_length=64)


class LinkSignupOut(BaseModel):
    status: str
    channel_id: uuid.UUID
    display_phone_number: str | None
    business_name: str


class LinkSocialOut(BaseModel):
    """Spec 085 (R7): what the owner's page needs, and nothing else."""

    status: Literal["connected", "choose"]
    #: ``@username`` or the Page's name, once connected.
    display_name: str | None = None
    business_name: str | None = None
    nonce: str | None = None
    accounts: list[AccountOut] = Field(default_factory=list)


async def _limit(redis: Redis, token: str) -> None:
    if not await allow(
        redis,
        key=f"rl:public_signup:{hash_token(token)[:24]}",
        per_minute=_PER_MINUTE,
        surface="public_signup",
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow_down")


async def _locked(session: AsyncSession, link_id: uuid.UUID) -> ChannelSignupLink | None:
    found: ChannelSignupLink | None = await session.scalar(
        select(ChannelSignupLink).where(ChannelSignupLink.id == link_id).with_for_update()
    )
    return found


@router.get("/{token}", response_model=LinkInfoOut)
async def link_info(
    token: str,
    _svc: ConsoleService = Depends(require_console_service()),
    redis: Redis = Depends(get_redis),
) -> LinkInfoOut:
    await _limit(redis, token)
    async with get_sessionmaker()() as s, s.begin():
        link = await find_link(s, token)
        state = link_state(link)
        if state != "valid" or link is None:
            # The page says why; it never says whose link it was.
            return LinkInfoOut(state=state)
        tenant_id = link.tenant_id
        channel = link.channel
        mode = link.mode
        expires_at = link.expires_at
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        tenant = await s.get(Tenant, tenant_id)
        name = tenant.name if tenant else None
        partner = await s.get(Partner, tenant.partner_id) if tenant and tenant.partner_id else None
    if channel in META_SOCIAL_CHANNELS:
        # Spec 085: the console's own offer for that partner (spec 049, 081).
        # A channel the partner does not have: as if the link did not exist.
        offer = meta_social_service.offer(partner)
        entry = next((c for c in offer["channels"] if c["kind"] == channel), None)
        if entry is None:
            return LinkInfoOut(state="unknown")
        return LinkInfoOut(
            state="valid",
            business_name=name,
            channel=channel,
            mode=mode,
            expires_at=expires_at,
            meta_app_id=offer["app_id"] or None,
            meta_config_id=entry["config_id"] or None,
            meta_page_config_id=entry["page_config_id"],
            meta_graph_version=offer["graph_version"],
        )
    settings = get_settings()
    return LinkInfoOut(
        state="valid",
        business_name=name,
        channel=channel,
        mode=mode,
        expires_at=expires_at,
        meta_app_id=settings.meta_app_id or None,
        meta_config_id=(
            settings.meta_config_id_wa_coexistence
            if mode == "coexistence"
            # Spec 047 (D12): la beta «WhatsApp login» tiene su propia
            # configuración de ES cuando Meta la da; hasta entonces, la de Cloud API.
            else (settings.meta_config_id_wa_login or settings.meta_config_id_wa_cloud_api)
            if mode == "whatsapp_login"
            else settings.meta_config_id_wa_cloud_api
        )
        or None,
        meta_graph_version=settings.meta_graph_api_version,
        meta_signup_version=settings.meta_embedded_signup_version,
    )


@router.post("/{token}", response_model=LinkSignupOut, status_code=status.HTTP_201_CREATED)
async def link_signup(
    token: str,
    body: LinkSignupIn,
    _svc: ConsoleService = Depends(require_console_service()),
    redis: Redis = Depends(get_redis),
) -> LinkSignupOut:
    await _limit(redis, token)
    async with get_sessionmaker()() as s, s.begin():
        link = require_valid(await find_link(s, token))
        tenant_id = link.tenant_id
        link_id = link.id
        if link.channel != "whatsapp":
            # Spec 085: an Instagram or Messenger link never runs a WhatsApp
            # signup, and stays valid for its own page.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail={"code": "link_channel_mismatch"}
            )
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        # Read again inside the transaction that consumes it, locked, so two
        # tabs posting at once cannot both connect.
        link = require_valid(await _locked(s, link_id))
        result = await connect_with_link(
            s,
            redis,
            link=link,
            payload=SignupIngressPayload(
                code=body.code,
                waba_id=body.waba_id,
                phone_number_id=body.phone_number_id,
                business_id=body.business_id,
                mode=link.mode,
            ),
        )
        tenant = await s.get(Tenant, tenant_id)
        out = LinkSignupOut(
            status="connected",
            channel_id=result.channel_id,
            display_phone_number=result.display_phone_number,
            business_name=tenant.name if tenant else "",
        )
        agent_id = link.agent_id
    # Spec 047 (31.1): committed; now the partner hears about it.
    await announce_connected(tenant_id=tenant_id, channel_id=out.channel_id, agent_id=agent_id)
    return out


# ── Spec 085: Instagram and Messenger ────────────────────────────────────────

_SocialRun = Callable[[AsyncSession, ChannelSignupLink], Awaitable[SocialLinkOutcome]]


async def _social(token: str, redis: Redis, run: _SocialRun) -> LinkSocialOut:
    """The link decides the client; the connection runs under that client's
    tenant scope, with the link locked like WhatsApp's. A refusal or Meta not
    answering rolls everything back and leaves the link valid (5.5)."""
    await _limit(redis, token)
    async with get_sessionmaker()() as s, s.begin():
        link = require_valid(await find_link(s, token))
        tenant_id, link_id = link.tenant_id, link.id
    try:
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            link = require_valid(await _locked(s, link_id))
            outcome = await run(s, link)
            tenant = await s.get(Tenant, tenant_id)
            business_name = tenant.name if tenant else None
    except MetaSocialConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.reason, "help": meta_social_service.REASON_HELP.get(exc.reason)},
        ) from None
    except MetaAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Meta did not answer"
        ) from exc
    if outcome.status == "choose":
        return LinkSocialOut(
            status="choose",
            nonce=outcome.nonce,
            accounts=[
                AccountOut(id=a.id, name=a.name, username=a.username, picture_url=a.picture_url)
                for a in outcome.accounts
            ],
        )
    assert outcome.channel_id is not None
    # Committed; now the partner hears about it, as with WhatsApp (5.3).
    await announce_connected(
        tenant_id=tenant_id, channel_id=outcome.channel_id, agent_id=outcome.agent_id
    )
    return LinkSocialOut(
        status="connected", display_name=outcome.display_name, business_name=business_name
    )


@router.post("/{token}/meta-social", response_model=LinkSocialOut)
async def link_meta_social(
    token: str,
    body: ConnectIn,
    _svc: ConsoleService = Depends(require_console_service()),
    redis: Redis = Depends(get_redis),
) -> LinkSocialOut:
    """Spec 085: the code from Facebook Login for Business, on the owner's device."""

    async def run(s: AsyncSession, link: ChannelSignupLink) -> SocialLinkOutcome:
        return await connect_meta_social_with_link(s, redis, link=link, code=body.code)

    return await _social(token, redis, run)


@router.post("/{token}/meta-social/complete", response_model=LinkSocialOut)
async def link_meta_social_complete(
    token: str,
    body: CompleteIn,
    _svc: ConsoleService = Depends(require_console_service()),
    redis: Redis = Depends(get_redis),
) -> LinkSocialOut:
    """Spec 085 (4.3, 7.3): the account the owner picked. Only the link that
    began the choice completes it; anything else is ``pending_expired`` and
    the link stays valid (4.4)."""

    async def run(s: AsyncSession, link: ChannelSignupLink) -> SocialLinkOutcome:
        return await complete_meta_social_with_link(
            s, redis, link=link, nonce=body.nonce, account_id=body.account_id
        )

    return await _social(token, redis, run)
