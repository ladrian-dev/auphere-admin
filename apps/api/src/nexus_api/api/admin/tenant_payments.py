"""``/admin/tenants/{tenant_id}/payments`` — la mensualidad de un cliente,
cobrada fuera del proveedor de pagos.

Un cliente paga por transferencia, en efectivo o por un medio que no pasa por
el proveedor. Aquí se anota: qué mes, cuánto, por dónde llegó y con qué
referencia.

**Quien paga es el partner** (owner, 2026-10-20). El pago se anota contra un
cliente y un mes —lo que pagó—, y **abona ese importe al saldo recargado del
partner**, una vez, por el id del pago (``services/manual_payments``). Anular
un pago descuenta ese abono; si el partner ya lo gastó, la anulación se
rechaza con 409. Un cliente directo de Auphere (sin partner) se anota y no
abona nada. No concede nivel ni cambia el estado de nadie.

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
from nexus_api.db.models.tenant_payment import CREDIT_SINCE
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.billing import (
    PartnerPaymentIn,
    PartnerPaymentOut,
    TenantPaymentIn,
    TenantPaymentOut,
)

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


class PaymentConflict(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def _record(
    tenant_id: uuid.UUID, body: TenantPaymentIn, operator: OperatorAccount
) -> TenantPayment:
    """Anota el pago y, si el cliente tiene partner, abona su saldo."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.manual_payments import credit_payment, partner_of

    conflict = (
        f"{body.period_month:02d}/{body.period_year} ya tiene un pago anotado; "
        "anúlalo antes de anotar otro"
    )
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        if await s.scalar(_live_for_period(tenant_id, body.period_year, body.period_month)):
            raise PaymentConflict(conflict)
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
        s.add(payment)
        try:
            await s.flush()
        except IntegrityError:
            # Dos operadores a la vez: gana el índice único, no la comprobación.
            raise PaymentConflict(conflict) from None
        await s.refresh(payment)
        await AuditRepository(s).record(
            actor=_actor(operator),
            action="tenant_payment.recorded",
            target=f"tenant_payment:{payment.id}",
            before=None,
            after=_snapshot(payment),
        )
        partner_id = await partner_of(s, tenant_id)
    log.info(
        "tenant_payment.recorded",
        tenant_id=str(tenant_id),
        period=f"{body.period_year}-{body.period_month:02d}",
        amount_cents=body.amount_cents,
        method=body.method,
    )
    if partner_id is not None:
        try:
            payment.credited_cents = await credit_payment(
                payment=payment, partner_id=partner_id, actor=_actor(operator)
            )
        except Exception as exc:
            # The payment stays recorded; «Abonar» retries by the same key.
            log.error("tenant_payment.credit_failed", payment_id=str(payment.id), error=str(exc))
    return payment


async def _void(
    tenant_id: uuid.UUID, payment_id: uuid.UUID, operator: OperatorAccount
) -> TenantPayment:
    """Descuenta el abono (si lo hubo) y luego anula. Si el partner ya lo
    gastó, no anula nada (409)."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.manual_payments import (
        NotEnoughBalance,
        partner_of,
        reverse_payment,
    )

    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        payment = await s.get(TenantPayment, payment_id)
        if payment is None or payment.tenant_id != tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"payment {payment_id} not found")
        if payment.voided_at is not None:
            raise PaymentConflict("el pago ya estaba anulado")
        partner_id = await partner_of(s, tenant_id)
        s.expunge(payment)
    if partner_id is not None and payment.credited_cents:
        try:
            await reverse_payment(payment=payment, partner_id=partner_id, actor=_actor(operator))
        except NotEnoughBalance:
            raise PaymentConflict(
                "el partner ya gastó ese saldo: no se puede anular el pago sin dejarlo en negativo"
            ) from None
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        row = await s.get(TenantPayment, payment_id)
        assert row is not None
        before = _snapshot(row)
        row.voided_at = datetime.now(UTC)
        row.voided_by = operator.email
        await s.flush()
        await AuditRepository(s).record(
            actor=_actor(operator),
            action="tenant_payment.voided",
            target=f"tenant_payment:{row.id}",
            before=before,
            after={**before, "voided": True},
        )
        await s.refresh(row)
        s.expunge(row)
    log.info("tenant_payment.voided", tenant_id=str(tenant_id), payment_id=str(payment_id))
    return row


def _http(exc: PaymentConflict) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, exc.detail)


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
    session: AsyncSession = Depends(get_db_session),
) -> TenantPaymentOut:
    """Anota la mensualidad de un mes y abona el saldo del partner."""
    await _tenant_or_404(session, tenant_id)
    try:
        return TenantPaymentOut.model_validate(await _record(tenant_id, body, operator))
    except PaymentConflict as exc:
        raise _http(exc) from None


@router.post(
    "/tenants/{tenant_id}/payments/{payment_id}/void",
    response_model=TenantPaymentOut,
    responses={409: {"description": "Ya estaba anulado, o el partner ya gastó el abono."}},
)
async def void_tenant_payment(
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> TenantPaymentOut:
    """Anula un pago anotado por error. La fila se queda; el mes se libera."""
    await _tenant_or_404(session, tenant_id)
    try:
        return TenantPaymentOut.model_validate(await _void(tenant_id, payment_id, operator))
    except PaymentConflict as exc:
        raise _http(exc) from None


async def _tenant_or_404(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    from nexus_api.db.models import Tenant

    async with session.begin():
        if await session.get(Tenant, tenant_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"tenant {tenant_id} not found")


# ── The partner's payments (owner, 2026-10-20) ──────────────────────────────


async def _partner_tenants(session: AsyncSession, partner_id: uuid.UUID) -> dict[uuid.UUID, str]:
    from nexus_api.db.models import Partner, Tenant
    from nexus_api.db.models.partner import PartnerTenant

    async with session.begin():
        if await session.get(Partner, partner_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown_partner")
        rows = (
            await session.execute(
                sa.select(Tenant.id, Tenant.name)
                .join(PartnerTenant, PartnerTenant.tenant_id == Tenant.id)
                .where(PartnerTenant.partner_id == partner_id)
            )
        ).all()
    return {tid: name for tid, name in rows}


@router.get("/partners/{partner_id}/payments", response_model=list[PartnerPaymentOut])
async def list_partner_payments(
    partner_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> list[PartnerPaymentOut]:
    """Los pagos de todos los clientes del partner, del más reciente al más viejo."""
    tenants = await _partner_tenants(session, partner_id)
    if not tenants:
        return []
    async with session.begin():
        rows = (
            await session.scalars(
                sa.select(TenantPayment)
                .where(TenantPayment.tenant_id.in_(list(tenants)))
                .order_by(
                    TenantPayment.period_year.desc(),
                    TenantPayment.period_month.desc(),
                    TenantPayment.created_at.desc(),
                )
            )
        ).all()
    return [
        PartnerPaymentOut.model_validate(row).model_copy(
            update={"client_name": tenants[row.tenant_id]}
        )
        for row in rows
    ]


@router.post(
    "/partners/{partner_id}/payments",
    response_model=PartnerPaymentOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Ese mes de ese cliente ya tiene un pago anotado."}},
)
async def record_partner_payment(
    partner_id: uuid.UUID,
    body: PartnerPaymentIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> PartnerPaymentOut:
    """Anota un pago del partner por un cliente y un mes, y abona su saldo."""
    tenants = await _partner_tenants(session, partner_id)
    if body.tenant_id not in tenants:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown_client")
    data = TenantPaymentIn.model_validate(body.model_dump(exclude={"tenant_id"}))
    try:
        payment = await _record(body.tenant_id, data, operator)
    except PaymentConflict as exc:
        raise _http(exc) from None
    return PartnerPaymentOut.model_validate(payment).model_copy(
        update={"client_name": tenants[body.tenant_id]}
    )


@router.post(
    "/partners/{partner_id}/payments/{payment_id}/void",
    response_model=PartnerPaymentOut,
    responses={409: {"description": "Ya estaba anulado, o el partner ya gastó el abono."}},
)
async def void_partner_payment(
    partner_id: uuid.UUID,
    payment_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> PartnerPaymentOut:
    tenant_id, name = await _payment_of_partner(session, partner_id, payment_id)
    try:
        payment = await _void(tenant_id, payment_id, operator)
    except PaymentConflict as exc:
        raise _http(exc) from None
    return PartnerPaymentOut.model_validate(payment).model_copy(update={"client_name": name})


@router.post(
    "/partners/{partner_id}/payments/{payment_id}/credit",
    response_model=PartnerPaymentOut,
    responses={409: {"description": "El pago está anulado o es anterior al abono automático."}},
)
async def credit_partner_payment(
    partner_id: uuid.UUID,
    payment_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> PartnerPaymentOut:
    """Reintenta el abono de un pago cuyo abono falló. Nunca abona dos veces."""
    from nexus_api.services.manual_payments import credit_payment

    _tenant_id, name = await _payment_of_partner(session, partner_id, payment_id)
    async with session.begin():
        payment = await session.get(TenantPayment, payment_id)
        assert payment is not None
        session.expunge(payment)
    if payment.voided_at is not None or payment.credited_cents is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "nada que abonar")
    if payment.created_at < CREDIT_SINCE:
        raise HTTPException(status.HTTP_409_CONFLICT, "pago anterior al abono automático")
    payment.credited_cents = await credit_payment(
        payment=payment, partner_id=partner_id, actor=_actor(operator)
    )
    return PartnerPaymentOut.model_validate(payment).model_copy(update={"client_name": name})


async def _payment_of_partner(
    session: AsyncSession, partner_id: uuid.UUID, payment_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    tenants = await _partner_tenants(session, partner_id)
    async with session.begin():
        tenant_id = await session.scalar(
            sa.select(TenantPayment.tenant_id).where(TenantPayment.id == payment_id)
        )
    if tenant_id is None or tenant_id not in tenants:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"payment {payment_id} not found")
    return tenant_id, tenants[tenant_id]
