"""``/admin/tenants/{tenant_id}/payments`` — la mensualidad de un cliente,
cobrada fuera del proveedor de pagos.

Un cliente paga por transferencia, en efectivo o por un medio que no pasa por
el proveedor. Aquí se anota: qué mes, cuánto, por dónde llegó y con qué
referencia.

**Anotar un pago no toca el servicio.** No concede nivel, no carga saldo y no
cambia el estado de nadie. Es la constancia que le faltaba al equipo, y por
eso no hay en este módulo ni una llamada a ``billing.ladder`` ni a
``metering.wallet``.

Un pago anotado por error se anula, no se borra; el mes queda libre para
anotarlo bien. Quien anota y quien anula es el operador de la sesión del
panel, nunca el token.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount, TenantPayment
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.billing import TenantPaymentIn, TenantPaymentOut

from .operator import require_operator

log = structlog.get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_admin_token)])


def _actor(operator: OperatorAccount) -> str:
    return f"operator:{operator.email}"


def _snapshot(payment: TenantPayment) -> dict[str, object]:
    return {
        "period_year": payment.period_year,
        "period_month": payment.period_month,
        "amount_cents": payment.amount_cents,
        "currency": payment.currency,
        "method": payment.method,
        "paid_on": payment.paid_on.isoformat(),
    }


def _live_for_period(tenant_id: uuid.UUID, year: int, month: int) -> sa.Select[tuple[uuid.UUID]]:
    return sa.select(TenantPayment.id).where(
        TenantPayment.tenant_id == tenant_id,
        TenantPayment.period_year == year,
        TenantPayment.period_month == month,
        TenantPayment.voided_at.is_(None),
    )


@router.get("/tenant-payments", response_model=list[TenantPaymentOut])
async def list_period_payments(
    year: int = Query(ge=2024, le=2100),
    month: int = Query(ge=1, le=12),
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantPaymentOut]:
    """Quién tiene pagada la mensualidad de un mes, entre todos los clientes."""
    async with session.begin():
        rows = (
            await session.scalars(
                sa.select(TenantPayment).where(
                    TenantPayment.period_year == year,
                    TenantPayment.period_month == month,
                    TenantPayment.voided_at.is_(None),
                )
            )
        ).all()
    return [TenantPaymentOut.model_validate(row) for row in rows]


@router.get("/tenants/{tenant_id}/payments", response_model=list[TenantPaymentOut])
async def list_tenant_payments(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> list[TenantPaymentOut]:
    """Los pagos anotados del cliente, del mes más reciente al más viejo.
    Incluye los anulados: borrar no existe, y ver que uno se anuló es parte
    de la constancia."""
    rows = (
        await session.scalars(
            sa.select(TenantPayment)
            .where(TenantPayment.tenant_id == tenant_id)
            .order_by(
                TenantPayment.period_year.desc(),
                TenantPayment.period_month.desc(),
                TenantPayment.created_at.desc(),
            )
        )
    ).all()
    return [TenantPaymentOut.model_validate(row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/payments",
    response_model=TenantPaymentOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Ese mes ya tiene un pago anotado sin anular."}},
)
async def record_tenant_payment(
    tenant_id: uuid.UUID,
    body: TenantPaymentIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> TenantPaymentOut:
    """Anota la mensualidad de un mes. No cambia nada del servicio."""
    conflict = HTTPException(
        status.HTTP_409_CONFLICT,
        f"{body.period_month:02d}/{body.period_year} ya tiene un pago anotado; "
        "anúlalo antes de anotar otro",
    )
    if await session.scalar(_live_for_period(tenant_id, body.period_year, body.period_month)):
        raise conflict

    payment = TenantPayment(
        tenant_id=tenant_id,
        period_year=body.period_year,
        period_month=body.period_month,
        amount_cents=body.amount_cents,
        method=body.method,
        reference=(body.reference or "").strip() or None,
        paid_on=body.paid_on,
        note=(body.note or "").strip() or None,
        recorded_by=operator.email,
    )
    session.add(payment)
    try:
        await session.flush()
    except IntegrityError:
        # Dos operadores a la vez: gana el índice único, no la comprobación.
        raise conflict from None
    await session.refresh(payment)

    await AuditRepository(session).record(
        actor=_actor(operator),
        action="tenant_payment.recorded",
        target=f"tenant_payment:{payment.id}",
        before=None,
        after=_snapshot(payment),
    )
    log.info(
        "tenant_payment.recorded",
        tenant_id=str(tenant_id),
        period=f"{body.period_year}-{body.period_month:02d}",
        amount_cents=body.amount_cents,
        method=body.method,
    )
    return TenantPaymentOut.model_validate(payment)


@router.post(
    "/tenants/{tenant_id}/payments/{payment_id}/void",
    response_model=TenantPaymentOut,
    responses={409: {"description": "El pago ya estaba anulado."}},
)
async def void_tenant_payment(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> TenantPaymentOut:
    """Anula un pago anotado por error. La fila se queda; el mes se libera."""
    payment = (
        await session.scalars(
            sa.select(TenantPayment).where(
                TenantPayment.id == payment_id, TenantPayment.tenant_id == tenant_id
            )
        )
    ).one_or_none()
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"payment {payment_id} not found")
    if payment.voided_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "el pago ya estaba anulado")

    before = _snapshot(payment)
    payment.voided_at = datetime.now(UTC)
    payment.voided_by = operator.email
    await session.flush()

    await AuditRepository(session).record(
        actor=_actor(operator),
        action="tenant_payment.voided",
        target=f"tenant_payment:{payment.id}",
        before=before,
        after={**before, "voided": True},
    )
    log.info("tenant_payment.voided", tenant_id=str(tenant_id), payment_id=str(payment_id))
    return TenantPaymentOut.model_validate(payment)
