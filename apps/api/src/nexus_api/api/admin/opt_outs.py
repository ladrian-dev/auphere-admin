"""Spec 050 (5.5): the operator sees a business's WhatsApp opt-outs and lifts
one written by a stop word or by an operator, with a reason.

Meta's own opt-out (``user_preferences`` ``stop``) is the person's choice in
WhatsApp: only their ``resume`` lifts it, so the panel answers 409
``lifted_by_person_only``. Every lift is audited (``customer.opt_out.lifted``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import Channel, Customer, WhatsAppOptOut
from nexus_api.services import whatsapp_opt_outs

router = APIRouter()

#: The newest first; a business with more is a conversation, not a list.
LIST_LIMIT = 200


class OptOutOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    channel_identifier: str | None
    customer_id: uuid.UUID | None
    customer_name: str | None
    phone: str | None
    scope: str
    source: str
    reason: str
    opted_out_at: datetime
    opted_in_at: datetime | None
    lifted_by: str | None
    #: Whether the operator may lift it (``source`` is not Meta's).
    liftable: bool


class LiftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


@router.get("/tenants/{tenant_id}/opt-outs", response_model=list[OptOutOut])
async def list_opt_outs(
    session: AsyncSession = Depends(scoped_session_from_path),
    _actor: str = Depends(require_admin_token),
) -> list[OptOutOut]:
    rows = (
        await session.execute(
            select(WhatsAppOptOut, Channel.provider_identifier, Customer.name)
            .join(Channel, Channel.id == WhatsAppOptOut.channel_id)
            .outerjoin(Customer, Customer.id == WhatsAppOptOut.customer_id)
            .order_by(WhatsAppOptOut.opted_out_at.desc())
            .limit(LIST_LIMIT)
        )
    ).all()
    return [
        OptOutOut(
            id=o.id,
            channel_id=o.channel_id,
            channel_identifier=identifier,
            customer_id=o.customer_id,
            customer_name=name,
            phone=o.recipient_phone,
            scope=o.scope,
            source=o.source,
            reason=o.reason,
            opted_out_at=o.opted_out_at,
            opted_in_at=o.opted_in_at,
            lifted_by=o.lifted_by,
            liftable=o.opted_in_at is None and o.source != "meta",
        )
        for o, identifier, name in rows
    ]


@router.post("/tenants/{tenant_id}/opt-outs/{opt_out_id}/lift", response_model=OptOutOut)
async def lift_opt_out(
    opt_out_id: uuid.UUID,
    body: LiftIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> OptOutOut:
    row = await session.get(WhatsAppOptOut, opt_out_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opt_out_not_found")
    if row.opted_in_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_lifted")
    try:
        await whatsapp_opt_outs.lift(
            session, row, actor=f"admin:{actor[:8]}", by="operator", reason=body.reason
        )
    except whatsapp_opt_outs.OptOutLiftRefused as exc:
        code = status.HTTP_409_CONFLICT if exc.code == "lifted_by_person_only" else 422
        raise HTTPException(status_code=code, detail=exc.code) from exc
    channel = await session.get(Channel, row.channel_id)
    customer = await session.get(Customer, row.customer_id) if row.customer_id else None
    return OptOutOut(
        id=row.id,
        channel_id=row.channel_id,
        channel_identifier=channel.provider_identifier if channel else None,
        customer_id=row.customer_id,
        customer_name=customer.name if customer else None,
        phone=row.recipient_phone,
        scope=row.scope,
        source=row.source,
        reason=row.reason,
        opted_out_at=row.opted_out_at,
        opted_in_at=row.opted_in_at,
        lifted_by=row.lifted_by,
        liftable=False,
    )
