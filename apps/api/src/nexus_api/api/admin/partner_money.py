"""El dinero de un partner en el panel de operador — spec 047, T158 y T172
(requisitos 43.1, 46.5 y 54.5; ``contracts/admin-api.md`` §5).

- ``PUT /admin/partners/{id}/build-budget`` ``{cap: Money, reason}``: el tope mensual
  de «Construcción y pruebas». Cambia el de este mes (subirlo desbloquea al
  momento) y el de los meses que vienen.
- ``GET /admin/partners/{id}/build-budget/requests``: los «Pedir ampliación».
- ``PUT /admin/partners/{id}/account-currency`` ``{currency, reason}``: la moneda
  de la cuenta. Solo Auphere la cambia: convierte lo que queda al cambio del BCE
  del día y deja el asiento (un traspaso ``currency_change``) y la auditoría.

Las tablas del dinero tienen RLS por partner: se escriben con el ``app.partner_id``
del partner; la auditoría de plataforma, después, con el rol de siempre.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AuditLog,
    BuildBudgetRequest,
    OperatorAccount,
    Partner,
    PartnerBuildBudget,
    PartnerWallet,
    WalletTransfer,
)
from nexus_api.services.wallet import fx
from nexus_api.services.wallet.bags import month_of

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])

Currency = Literal["EUR", "USD"]


class MoneyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_micros: int = Field(ge=0)
    currency: Currency


class BuildBudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cap: MoneyIn
    reason: str = Field(min_length=3, max_length=300)


class CurrencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: Currency
    reason: str = Field(min_length=3, max_length=300)


async def _partner(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_partner"})
    return partner


async def _audit(
    session: AsyncSession, *, actor: str, action: str, partner_id: uuid.UUID, data: dict[str, Any]
) -> None:
    async with session.begin():
        session.add(
            AuditLog(
                tenant_id=None,
                actor=actor,
                action=action,
                target=f"partner:{partner_id}",
                after_json=data,
            )
        )


@router.put("/{partner_id}/build-budget")
async def set_build_budget(
    partner_id: uuid.UUID,
    body: BuildBudgetIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    async with session.begin():
        await _partner(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        account = await session.scalar(
            sa.select(PartnerWallet.currency).where(PartnerWallet.partner_id == partner_id)
        )
        if body.cap.currency != (account or "USD"):
            raise HTTPException(status_code=422, detail={"code": "currency_mismatch"})
        await session.execute(
            sa.update(Partner)
            .where(Partner.id == partner_id)
            .values(build_budget_default_micros=body.cap.amount_micros)
        )
        month = month_of()
        row = await session.get(PartnerBuildBudget, (partner_id, month))
        if row is None:
            session.add(
                PartnerBuildBudget(
                    partner_id=partner_id, month=month, cap_micros=body.cap.amount_micros
                )
            )
        else:
            row.cap_micros = body.cap.amount_micros
            # Subir el tope desbloquea; el aviso del 80 % puede volver a salir.
            if row.spent_micros < row.cap_micros:
                row.exhausted_at = None
            if row.spent_micros < 0.8 * row.cap_micros:
                row.warned_at = None
    await _audit(
        session,
        actor=operator_actor(operator),
        action="admin.partner.build_budget",
        partner_id=partner_id,
        data={"cap_micros": body.cap.amount_micros, "reason": body.reason},
    )
    return {"cap": body.cap.model_dump(), "month": month.isoformat()}


@router.get("/{partner_id}/build-budget")
async def get_build_budget(
    partner_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    """La partida del mes y la moneda de la cuenta, para el formulario."""
    from nexus_api.services.wallet import build_budget

    async with session.begin():
        await _partner(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        currency = await session.scalar(
            sa.select(PartnerWallet.currency).where(PartnerWallet.partner_id == partner_id)
        )
        state = await build_budget.read(session, partner_id)
    money = str(currency or "USD")
    return {
        "currency": money,
        "month": month_of().isoformat(),
        "cap": {"amount_micros": state.cap_micros, "currency": money},
        "spent": {"amount_micros": state.spent_micros, "currency": money},
        "state": state.state,
    }


@router.get("/{partner_id}/build-budget/requests")
async def list_build_budget_requests(
    partner_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> list[dict[str, Any]]:
    async with session.begin():
        await _partner(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        rows = (
            await session.scalars(
                sa.select(BuildBudgetRequest)
                .where(BuildBudgetRequest.partner_id == partner_id)
                .order_by(BuildBudgetRequest.created_at.desc())
                .limit(100)
            )
        ).all()
    return [{"requested_by": r.requested_by, "created_at": r.created_at.isoformat()} for r in rows]


@router.put("/{partner_id}/account-currency")
async def set_account_currency(
    partner_id: uuid.UUID,
    body: CurrencyIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    actor = operator_actor(operator)
    async with session.begin():
        await _partner(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        account = await session.scalar(
            sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id).with_for_update()
        )
        if account is None:
            raise HTTPException(status_code=404, detail={"code": "no_account"})
        old = account.currency
        if old == body.currency:
            return {"currency": old, "changed": False}
        try:
            rate, day = await fx.rate_on(session, datetime.now(UTC).date(), old, body.currency)
        except fx.FxUnavailable:
            raise HTTPException(status_code=503, detail={"code": "fx_unavailable"}) from None
        account.purchased_remaining = fx.convert(int(account.purchased_remaining), rate)
        account.included_remaining = fx.convert(int(account.included_remaining), rate)
        account.credit_limit = fx.convert(int(account.credit_limit), rate)
        account.currency = body.currency
        budget = await session.get(PartnerBuildBudget, (partner_id, month_of()))
        if budget is not None:
            budget.cap_micros = fx.convert(budget.cap_micros, rate)
            budget.spent_micros = fx.convert(budget.spent_micros, rate)
        session.add(
            WalletTransfer(
                id=uuid.uuid4(),
                partner_id=partner_id,
                kind="currency_change",
                partner_amount_micros=0,
                partner_currency=body.currency,
                client_amount_micros=0,
                client_currency=body.currency,
                fx_rate=rate,
                fx_date=day,
                idempotency_key=f"account_currency:{partner_id}:{uuid.uuid4()}",
                actor_id=actor,
            )
        )
        result = {
            "currency": body.currency,
            "changed": True,
            "from": old,
            "fx": {"rate": str(rate), "date": day.isoformat() if day else None, "source": "ECB"},
            "purchased_micros": account.purchased_remaining,
        }
    await _audit(
        session,
        actor=actor,
        action="admin.partner.account_currency",
        partner_id=partner_id,
        data={"from": old, "to": body.currency, "rate": str(rate), "reason": body.reason},
    )
    return result


__all__ = ["router"]
