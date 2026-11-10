"""``/console/channel-signup/{token}`` — the owner connects WhatsApp from a link (spec 040).

The business owner has no account: the link's token is what authorizes the
signup. It is single use, expires and can be revoked
(``services/channel_signup_links``), and each token has its own small rate
limit. Like every other ``/console/*`` route the API never answers it
without a credential: the console's server calls it with its **service**
token (``require_console_service``), the same way it serves invitations and
password resets — the API surface stays closed to the internet.

``GET`` tells the page who the link is for and how to open Meta's popup.
``POST`` takes what Meta's Embedded Signup returned and connects the number
under the client's own tenant scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import SignupIngressPayload
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.core.rate_limit import allow
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant
from nexus_api.services.channel_signup_links import (
    announce_connected,
    connect_with_link,
    find_link,
    hash_token,
    link_state,
    require_valid,
)

router = APIRouter(prefix="/channel-signup")

#: Calls per minute and token: the page needs two or three.
_PER_MINUTE = 10


class LinkInfoOut(BaseModel):
    state: str
    business_name: str | None = None
    mode: str | None = None
    expires_at: datetime | None = None
    meta_app_id: str | None = None
    meta_config_id: str | None = None
    meta_graph_version: str | None = None
    meta_signup_version: str | None = None


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


async def _limit(redis: Redis, token: str) -> None:
    if not await allow(
        redis,
        key=f"rl:public_signup:{hash_token(token)[:24]}",
        per_minute=_PER_MINUTE,
        surface="public_signup",
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="slow_down")


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
        mode = link.mode
        expires_at = link.expires_at
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        tenant = await s.get(Tenant, tenant_id)
        name = tenant.name if tenant else None
    settings = get_settings()
    return LinkInfoOut(
        state="valid",
        business_name=name,
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
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        # Read again inside the transaction that consumes it, locked, so two
        # tabs posting at once cannot both connect.
        from sqlalchemy import select

        from nexus_api.db.models import ChannelSignupLink

        locked = await s.scalar(
            select(ChannelSignupLink).where(ChannelSignupLink.id == link_id).with_for_update()
        )
        link = require_valid(locked)
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
