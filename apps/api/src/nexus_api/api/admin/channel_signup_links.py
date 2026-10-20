"""Admin — a link for the business owner to connect WhatsApp (spec 040).

The operator copies it and sends it: the owner opens it on their own device,
already logged in to Meta, and runs Embedded Signup there.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ChannelSignupLink, OperatorAccount, Tenant
from nexus_api.services.channel_signup_links import link_state, mint_link, revoke_link

router = APIRouter(dependencies=[Depends(require_admin_token)])


class SignupLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = "coexistence"


class SignupLinkOut(BaseModel):
    id: uuid.UUID
    mode: str
    #: Only on creation: the token is never stored, so it cannot be shown again.
    url: str | None = None
    state: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None


def _out(link: ChannelSignupLink, url: str | None = None) -> SignupLinkOut:
    return SignupLinkOut(
        id=link.id,
        mode=link.mode,
        url=url,
        state=link_state(link),
        created_by=link.created_by,
        created_at=link.created_at,
        expires_at=link.expires_at,
        consumed_at=link.consumed_at,
    )


@router.post(
    "/tenants/{tenant_id}/channels/whatsapp/signup-link",
    response_model=SignupLinkOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_signup_link(
    tenant_id: uuid.UUID,
    body: SignupLinkIn,
    operator: OperatorAccount = Depends(require_operator),
) -> SignupLinkOut:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        if await s.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_tenant")
        minted = await mint_link(
            s, tenant_id=tenant_id, mode=body.mode, actor=operator_actor(operator)
        )
        await s.refresh(minted.link)
        return _out(minted.link, minted.url)


@router.get(
    "/tenants/{tenant_id}/channels/whatsapp/signup-links", response_model=list[SignupLinkOut]
)
async def list_signup_links(tenant_id: uuid.UUID) -> list[SignupLinkOut]:
    async with get_sessionmaker()() as s, s.begin():
        rows = (
            (
                await s.execute(
                    sa.select(ChannelSignupLink)
                    .where(ChannelSignupLink.tenant_id == tenant_id)
                    .order_by(ChannelSignupLink.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        return [_out(r) for r in rows]


@router.delete(
    "/tenants/{tenant_id}/channels/whatsapp/signup-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_signup_link(
    tenant_id: uuid.UUID,
    link_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        link = await s.get(ChannelSignupLink, link_id)
        if link is None or link.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_link")
        await revoke_link(s, link, actor=operator_actor(operator))
