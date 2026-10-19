"""Admin — a partner's card, automatic charges and postpaid line (spec 041).

The operator sees the card (brand and last four, never more), how it is
charged and its charges, and grants or withdraws the postpaid credit line.
The line is the operator's decision, not the partner's: it is credit Auphere
extends. Signed by the operator in the audit (ADR-034).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount, Partner
from nexus_api.services.partner_billing import (
    BillingRuleError,
    BillingView,
    billing_view,
    set_charging,
    set_credit_limit,
)

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


class ChargingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    recharge_threshold_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    recharge_amount_cents: int | None = Field(default=None, ge=0, le=10_000_000)


class CreditLimitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credit_limit_cents: int = Field(ge=0, le=100_000_000)


async def _exists(session: AsyncSession, partner_id: uuid.UUID) -> None:
    async with session.begin():
        if await session.get(Partner, partner_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_partner")


@router.get("/{partner_id}/billing", response_model=BillingView)
async def get_partner_billing(
    partner_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> BillingView:
    await _exists(session, partner_id)
    return await billing_view(partner_id)


@router.put("/{partner_id}/credit-limit", response_model=BillingView)
async def put_credit_limit(
    partner_id: uuid.UUID,
    body: CreditLimitIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> BillingView:
    await _exists(session, partner_id)
    try:
        async with session.begin():
            await set_credit_limit(
                session,
                partner_id=partner_id,
                credit_limit_cents=body.credit_limit_cents,
                actor=operator_actor(operator),
            )
    except BillingRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}
        ) from exc
    return await billing_view(partner_id)


@router.put("/{partner_id}/charging", response_model=BillingView)
async def put_partner_charging(
    partner_id: uuid.UUID,
    body: ChargingIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> BillingView:
    """Spec 041: Auphere sets how a partner is charged — the same rules as the
    partner's own console (a card for anything automatic, a credit line for
    postpaid), signed by the operator."""
    await _exists(session, partner_id)
    try:
        async with session.begin():
            await set_charging(
                session,
                partner_id=partner_id,
                mode=body.mode,
                threshold_cents=body.recharge_threshold_cents,
                amount_cents=body.recharge_amount_cents,
                actor=operator_actor(operator),
            )
    except BillingRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}
        ) from exc
    return await billing_view(partner_id)
