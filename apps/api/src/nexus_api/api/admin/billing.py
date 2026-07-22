"""Admin catalogue of billing plans (USD monthly prices) — operator only.

Platform-level (no tenant scope): prices are Auphere's. The Facturación tab
lists these for the plan dropdown and can create a new one inline.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import BillingPlan
from nexus_api.schemas.billing import BillingPlanCreateIn, BillingPlanOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/billing-plans", dependencies=[Depends(require_admin_token)])


@router.get("", response_model=list[BillingPlanOut])
async def list_billing_plans(
    session: AsyncSession = Depends(get_db_session),
) -> list[BillingPlanOut]:
    rows = (
        (await session.execute(select(BillingPlan).order_by(BillingPlan.monthly_amount_cents)))
        .scalars()
        .all()
    )
    return [BillingPlanOut.model_validate(p) for p in rows]


@router.post("", response_model=BillingPlanOut, status_code=status.HTTP_201_CREATED)
async def create_billing_plan(
    body: BillingPlanCreateIn,
    session: AsyncSession = Depends(get_db_session),
) -> BillingPlanOut:
    plan = BillingPlan(
        code=body.code, name=body.name, monthly_amount_cents=body.monthly_amount_cents, active=True
    )
    session.add(plan)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"billing plan code '{body.code}' already exists"
        ) from exc
    log.info("billing_plan.created", code=plan.code, cents=plan.monthly_amount_cents)
    return BillingPlanOut.model_validate(plan)
