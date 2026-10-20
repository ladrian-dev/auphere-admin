"""``/admin/tenants/{tenant_id}/consumption`` — consumo ilimitado de un
cliente de partner (owner, 2026-10-20).

Con el interruptor encendido el agente del cliente **nunca se para por
saldo**: ``allow_channel_turn`` deja pasar el turno sin mirar el saldo del
partner ni el tope del cliente, y el worker lo anota como ``absorbed`` — se
mide igual, pero **no se descuenta del partner**: lo asume Auphere.

Solo se cambia desde aquí. El partner lo ve en su consola, sin poder tocarlo.
Quien lo cambia es el operador de la sesión del panel (``X-Operator-Id``), y
queda en la auditoría del cliente, que el partner lee en frases.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.billing.pricing import credits_to_cents
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import declare_tenant
from nexus_api.db.models import AuditLog, OperatorAccount, Partner, Tenant
from nexus_api.metering.wallet import absorbed_since, partner_id_for_tenant
from nexus_api.services.console_reporting import month_bounds

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])


class UnlimitedConsumptionOut(BaseModel):
    tenant_id: uuid.UUID
    partner_id: uuid.UUID | None
    partner_name: str | None
    unlimited: bool
    #: What Auphere covered for this client this calendar month (UTC), in US$
    #: cents. ``None`` when the ledger could not be read.
    absorbed_month_cents: int | None


class UnlimitedConsumptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unlimited: bool


async def _view(session: AsyncSession, tenant_id: uuid.UUID) -> UnlimitedConsumptionOut:
    async with session.begin():
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "unknown_client"})
        await declare_tenant(session, tenant_id)
        partner_id = await partner_id_for_tenant(session, tenant_id)
        partner_name = (
            await session.scalar(sa.select(Partner.name).where(Partner.id == partner_id))
            if partner_id is not None
            else None
        )
        unlimited = bool(tenant.unlimited_consumption)
    absorbed: int | None = 0
    if partner_id is not None:
        since, _until, _elapsed, _days = month_bounds()
        try:
            got = await absorbed_since(partner_id, [tenant_id], since)
            absorbed = credits_to_cents(got.get(tenant_id, 0), nearest=True)
        except Exception as exc:
            log.warning("unlimited_consumption.absorbed_unreadable", error=str(exc))
            absorbed = None
    return UnlimitedConsumptionOut(
        tenant_id=tenant_id,
        partner_id=partner_id,
        partner_name=partner_name,
        unlimited=unlimited,
        absorbed_month_cents=absorbed,
    )


@router.get("/{tenant_id}/consumption", response_model=UnlimitedConsumptionOut)
async def read_unlimited_consumption(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> UnlimitedConsumptionOut:
    return await _view(session, tenant_id)


@router.put(
    "/{tenant_id}/consumption",
    response_model=UnlimitedConsumptionOut,
    responses={
        404: {"description": "Cliente desconocido."},
        422: {"description": "El cliente no tiene partner: no hay saldo que lo pare."},
    },
)
async def set_unlimited_consumption(
    tenant_id: uuid.UUID,
    body: UnlimitedConsumptionIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> UnlimitedConsumptionOut:
    """Enciende o apaga el consumo ilimitado. Repetir el mismo valor no
    escribe nada."""
    async with session.begin():
        tenant = await session.get(Tenant, tenant_id, with_for_update=True)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "unknown_client"})
        await declare_tenant(session, tenant_id)
        if await partner_id_for_tenant(session, tenant_id) is None:
            # A direct client never stops for balance: there is nothing to lift.
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "no_partner"}
            )
        before = bool(tenant.unlimited_consumption)
        if before != body.unlimited:
            tenant.unlimited_consumption = body.unlimited
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor=operator_actor(operator),
                    action=(
                        "client_consumption.unlimited_on"
                        if body.unlimited
                        else "client_consumption.unlimited_off"
                    ),
                    target=f"tenant:{tenant_id}",
                    before_json={"unlimited": before},
                    after_json={"unlimited": body.unlimited},
                )
            )
            log.info(
                "unlimited_consumption.set",
                tenant_id=str(tenant_id),
                unlimited=body.unlimited,
                operator=operator.email,
            )
    return await _view(session, tenant_id)
