"""Admin — erase one person's Instagram / Messenger data (spec 049, R5.6).

A person who writes to ``privacidad@`` asking Auphere to delete what it
received from Instagram or Messenger is located by the operator by business
and channel and their IGSID / PSID. The messages are emptied and, when the
person exists only through that channel, the identity too
(``services/meta_social_retention``). Within the 30 days the privacy policy
promises; the audit names who asked, who did it and when.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Path, status
from nexus_channels.meta_social import META_SOCIAL_PROVIDERS
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog, Channel, Customer, OperatorAccount
from nexus_api.services.meta_social_retention import erase_customer_in_channel

from .operator import operator_actor, require_operator

router = APIRouter()


class ErasePersonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The IGSID / PSID as Meta gives it (the inbox shows it on the contact).
    identifier: str = Field(min_length=1, max_length=128)
    #: Who asked: the e-mail address or the ticket the request came in.
    requested_by: str = Field(min_length=3, max_length=255)


class ErasePersonOut(BaseModel):
    erased: bool
    messages_emptied: int


@router.post(
    "/tenants/{tenant_id}/channels/{channel_id}/erase-person",
    response_model=ErasePersonOut,
    dependencies=[Depends(require_admin_token)],
)
async def erase_person(
    tenant_id: uuid.UUID,
    body: ErasePersonIn,
    channel_id: uuid.UUID = Path(...),
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> ErasePersonOut:
    channel = await session.get(Channel, channel_id)
    if channel is None or channel.provider not in META_SOCIAL_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    customer_id = await session.scalar(
        sa.select(Customer.id).where(Customer.identifier == body.identifier)
    )
    if customer_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="person not found")
    emptied = await erase_customer_in_channel(
        session, channel_id=channel.id, customer_id=customer_id
    )
    cfg = channel.config or {}
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=operator_actor(operator),
            action="customer.meta_social.erase",
            target=f"channel:{channel.id}",
            before_json=None,
            after_json={
                "display_name": f"@{cfg['username']}" if cfg.get("username") else cfg.get("name"),
                "requested_by": body.requested_by,
                "messages": emptied,
            },
        )
    )
    await session.flush()
    return ErasePersonOut(erased=True, messages_emptied=emptied)


__all__ = ["router"]
