"""La membresía de un cliente en el panel — spec 077, requisitos 6, 7 y 8.

Rutas bajo ``/admin/tenants/{id}/membership`` (``contracts/admin-api.md``). Las
que escriben exigen un operador habilitado y lo nombran en la auditoría del
cliente (constitución §IV). La lógica vive en ``services/service_memberships``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.api.admin.operator import operator_actor, require_enabled_operator
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.db.models.service_membership import DEFAULT_AMOUNT_CENTS
from nexus_api.services import service_memberships as memberships

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])


class MembershipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payer: str = Field(pattern="^(stripe|partner_wallet)$")
    amount_cents: int = Field(default=DEFAULT_AMOUNT_CENTS, gt=0, le=10_000_000)
    billing_email: str | None = Field(default=None, max_length=320)


class MembershipOut(BaseModel):
    tenant_id: uuid.UUID
    payer: str
    amount_cents: int
    pending_amount_cents: int | None
    status: str
    active: bool
    current_period_end: datetime | None
    billing_email: str | None
    checkout_url: str | None
    checkout_expires_at: datetime | None
    last_synced_at: datetime | None
    last_failure: str | None
    partner_id: uuid.UUID | None
    partner_name: str | None
    has_subscription: bool


class CheckoutOut(BaseModel):
    url: str
    expires_at: datetime | None


class ChargeOut(BaseModel):
    period_start: datetime | None
    period_end: datetime | None
    amount_cents: int
    status: str
    url: str | None


def _out(view: memberships.MembershipView) -> MembershipOut:
    return MembershipOut(**view.__dict__)


@router.get("/{tenant_id}/membership", response_model=MembershipOut)
async def get_membership(tenant_id: uuid.UUID) -> MembershipOut:
    view = await memberships.get_view(tenant_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_membership")
    return _out(view)


@router.put("/{tenant_id}/membership", response_model=MembershipOut)
async def put_membership(
    tenant_id: uuid.UUID,
    body: MembershipIn,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> MembershipOut:
    return _out(
        await memberships.configure(
            tenant_id,
            payer=body.payer,
            amount_cents=body.amount_cents,
            billing_email=body.billing_email,
            actor=operator_actor(operator),
        )
    )


@router.post(
    "/{tenant_id}/membership/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def archive_membership(
    tenant_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> Response:
    await memberships.archive(tenant_id, actor=operator_actor(operator))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{tenant_id}/membership/checkout", response_model=CheckoutOut)
async def create_membership_checkout(
    tenant_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> CheckoutOut:
    url, expires_at = await memberships.create_checkout(tenant_id, actor=operator_actor(operator))
    return CheckoutOut(url=url, expires_at=expires_at)


@router.post("/{tenant_id}/membership/refresh", response_model=MembershipOut)
async def refresh_membership(
    tenant_id: uuid.UUID,
    _operator: OperatorAccount = Depends(require_enabled_operator),
) -> MembershipOut:
    return _out(await memberships.refresh_from_stripe(tenant_id))


@router.post("/{tenant_id}/membership/charge", response_model=MembershipOut)
async def charge_membership(
    tenant_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> MembershipOut:
    return _out(await memberships.charge_now(tenant_id, actor=operator_actor(operator)))


@router.post("/{tenant_id}/membership/cancel", response_model=MembershipOut)
async def cancel_membership(
    tenant_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> MembershipOut:
    return _out(await memberships.cancel(tenant_id, actor=operator_actor(operator)))


@router.get("/{tenant_id}/membership/charges", response_model=list[ChargeOut])
async def membership_charges(tenant_id: uuid.UUID) -> list[ChargeOut]:
    return [ChargeOut(**row) for row in await memberships.charges(tenant_id)]
