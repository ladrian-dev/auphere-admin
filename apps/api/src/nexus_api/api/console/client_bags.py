"""El dinero de la consola nueva — spec 047, T158 (requisitos 43, 45 y 46;
``contracts/console-api.md`` §7).

- ``GET /console/wallet/bags``: la bolsa de cada cliente (saldo, gastado del mes,
  días, relleno, estado);
- ``GET /console/wallet/fx?from=&to=``: el cambio BCE del día y su fecha;
- ``POST /console/clients/{ref}/bag/assign`` [``usage:write``] ``{amount,
  refill_up_to?, alert_low?}`` + ``Idempotency-Key`` → el recibo;
- ``POST /console/clients/{ref}/bag/lower`` · ``POST /console/wallet/bags/move``;
- ``PUT /console/clients/{ref}/bag/refill`` · ``PUT /console/clients/{ref}/bag/currency``;
- ``POST /console/clients/{ref}/bag/request``: «Pedir saldo» (una al día; 429);
- ``PUT /console/clients/{ref}/agents/{agent_id}/cap``: el tope mensual del agente;
- ``GET /console/usage/build-budget`` · ``POST …/extension-request``;
- ``GET /console/wallet/migration`` · ``POST /console/wallet/migration/confirm``.

Dinero: ``{amount_micros, currency}`` en cien milésimas de la moneda. Los errores
llevan su código (``insufficient_account``, ``bag_below_spent``…).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import (
    Agent,
    AgentMonthlySpend,
    AuditLog,
    BalanceRequest,
    ClientWallet,
    PartnerAllocation,
    PartnerTenant,
    PartnerWallet,
    WalletMigrationProposal,
)
from nexus_api.services import agent_states
from nexus_api.services.wallet import alerts as wallet_alerts
from nexus_api.services.wallet import bags, build_budget, fx
from nexus_api.services.wallet.turns import after_balance_up

from .agent_draft_routes import agent_in_path
from .deps import ClientScope

router = APIRouter()

Currency = Literal["EUR", "USD"]


class Money(BaseModel):
    amount_micros: int
    currency: Currency


class BagOut(BaseModel):
    ref: str
    balance: Money
    month_spent: Money
    month_base: Money
    days_left: int | None
    state: Literal["ok", "low", "not_enough", "empty"]
    refill_up_to: Money | None = None
    alert_low: bool
    #: «Pedir saldo» ya enviado hoy para este cliente: «Pedido hace…» (45.7).
    requested_at: datetime | None = None


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Money
    refill_up_to: Money | None = None
    alert_low: bool | None = None


class LowerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Money


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_ref: str
    to_ref: str
    amount: Money


class RefillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    up_to: Money | None


class CurrencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: Currency
    confirm: bool = False


class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=280)


class CapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_cap: Money | None


class FxOut(BaseModel):
    rate: str
    date: date | None
    source: Literal["ECB"] = "ECB"


class ReceiptOut(BaseModel):
    client_balance_before: Money
    assigned: Money
    debited_from_account: Money
    fx: FxOut
    client_balance_after: Money
    account_left: Money
    #: Queda poco en la cuenta tras asignar (45.4): un aviso ámbar.
    warn_low_account: bool


async def _audit(
    tenant_id: uuid.UUID | None,
    actor: str,
    action: str,
    data: dict[str, Any],
    *,
    partner_id: uuid.UUID,
) -> None:
    """La fila de Auditoría (49.1, events.md §4), después de confirmar: el dinero
    se escribe con el ``app.partner_id`` y la auditoría del cliente, con el suyo."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    row = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target=f"tenant:{tenant_id}" if tenant_id else f"partner:{partner_id}",
        after_json={**data, "origin": "console"},
    )
    async with get_sessionmaker()() as session:
        if tenant_id is None:
            async with session.begin():
                session.add(row)
        else:
            async with tenant_scoped_session(session, tenant_id):
                session.add(row)


def _error(exc: bags.WalletError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.extra})


async def _partner_session(session: AsyncSession, principal: ConsolePrincipal) -> uuid.UUID:
    await apply_partner_to_session(session, principal.partner.id)
    return principal.partner.id


async def _tenant_of(session: AsyncSession, partner_id: uuid.UUID, ref: str) -> uuid.UUID:
    tenant_id = await session.scalar(
        sa.select(PartnerTenant.tenant_id).where(
            PartnerTenant.partner_id == partner_id, PartnerTenant.external_client_ref == ref
        )
    )
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Unknown client reference")
    return tenant_id


async def _require_bags(session: AsyncSession, partner_id: uuid.UUID) -> None:
    if not await bags.bags_active(session, partner_id):
        raise HTTPException(status_code=409, detail={"code": "bags_not_active"})


def _money(amount: int, currency: str) -> Money:
    return Money(amount_micros=int(amount), currency=currency)  # type: ignore[arg-type]


async def _bag_out(session: AsyncSession, bag: ClientWallet, ref: str) -> BagOut:
    pace = await wallet_alerts.pace_per_day(session, bag, datetime.now(UTC).date())
    return BagOut(
        ref=ref,
        balance=_money(bag.balance_micros, bag.currency),
        month_spent=_money(bag.month_spent_micros, bag.currency),
        month_base=_money(bag.month_base_micros, bag.currency),
        days_left=wallet_alerts.days_left(bag.balance_micros, pace),
        state=await wallet_alerts.bag_state(session, bag),  # type: ignore[arg-type]
        refill_up_to=_money(bag.refill_up_to_micros, bag.currency)
        if bag.refill_up_to_micros
        else None,
        alert_low=bag.alert_low_enabled,
    )


@router.get("/wallet/bags", response_model=list[BagOut])
async def list_bags(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[BagOut]:
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        refs = (
            await session.execute(
                sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref)
                .where(PartnerTenant.partner_id == partner_id)
                .order_by(PartnerTenant.external_client_ref)
            )
        ).all()
        today = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), UTC)
        out = []
        # La bolsa y sus peticiones son del cliente: una a una, con su contexto.
        for tenant_id, ref in refs:
            await bags.as_client(session, tenant_id)
            bag = await session.get(ClientWallet, tenant_id)
            if bag is None:
                continue
            item = await _bag_out(session, bag, ref)
            item.requested_at = await session.scalar(
                sa.select(sa.func.max(BalanceRequest.created_at)).where(
                    BalanceRequest.tenant_id == tenant_id, BalanceRequest.created_at >= today
                )
            )
            out.append(item)
        return out


@router.get("/wallet/fx", response_model=FxOut)
async def get_fx(
    from_: Currency = Query(alias="from"),
    to: Currency = Query(),
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> FxOut:
    async with session.begin():
        try:
            rate, day = await fx.rate_on(session, datetime.now(UTC).date(), from_, to)
        except fx.FxUnavailable:
            raise HTTPException(status_code=503, detail={"code": "fx_unavailable"}) from None
    return FxOut(rate=str(rate.quantize(Decimal("0.00000001"))), date=day)


@router.post("/clients/{ref}/bag/assign", response_model=ReceiptOut)
async def assign(
    ref: str,
    body: AssignIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptOut:
    """Asignar saldo (43.4, 45): un traspaso con su recibo."""
    key = idempotency_key or f"assign:{uuid.uuid4()}"
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        tenant_id = await _tenant_of(session, partner_id, ref)
        await _require_bags(session, partner_id)
        bag = await bags.bag_for_update(session, tenant_id, partner_id=partner_id)
        if body.amount.currency != bag.currency:
            raise HTTPException(status_code=422, detail={"code": "currency_mismatch"})
        before = bag.balance_micros
        try:
            transfer = await bags.assign(
                session,
                partner_id=partner_id,
                tenant_id=tenant_id,
                amount=body.amount.amount_micros,
                idempotency_key=key,
                actor=principal.actor,
                in_bag_currency=True,
            )
        except (bags.WalletError, fx.FxUnavailable) as exc:
            if isinstance(exc, fx.FxUnavailable):
                raise HTTPException(status_code=503, detail={"code": "fx_unavailable"}) from None
            raise _error(exc) from None
        if body.refill_up_to is not None:
            bag.refill_up_to_micros = body.refill_up_to.amount_micros or None
        if body.alert_low is not None:
            bag.alert_low_enabled = body.alert_low
        account = await session.get(PartnerWallet, partner_id)
        assert account is not None
        left = bags.assignable(account)
        receipt = ReceiptOut(
            client_balance_before=_money(before, bag.currency),
            assigned=_money(transfer.client_amount_micros, transfer.client_currency),
            debited_from_account=_money(transfer.partner_amount_micros, transfer.partner_currency),
            fx=FxOut(rate=str(transfer.fx_rate), date=transfer.fx_date),
            client_balance_after=_money(bag.balance_micros, bag.currency),
            account_left=_money(left, account.currency),
            # «Si queda poco en la cuenta» (45.4): por debajo del 20 % de lo que
            # había antes de asignar.
            warn_low_account=left < 0.2 * (left + transfer.partner_amount_micros),
        )
    await _audit(
        tenant_id,
        principal.actor,
        "wallet.assigned",
        {"amount": receipt.assigned.model_dump(), "transfer_id": str(transfer.id)},
        partner_id=principal.partner.id,
    )
    if before == 0 and receipt.client_balance_after.amount_micros > 0:
        await after_balance_up(tenant_id)
    return receipt


@router.post("/clients/{ref}/bag/lower", response_model=BagOut)
async def lower(
    ref: str,
    body: LowerIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> BagOut:
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        tenant_id = await _tenant_of(session, partner_id, ref)
        await _require_bags(session, partner_id)
        try:
            await bags.lower(
                session,
                partner_id=partner_id,
                tenant_id=tenant_id,
                amount=body.amount.amount_micros,
                idempotency_key=idempotency_key or f"lower:{uuid.uuid4()}",
                actor=principal.actor,
            )
        except bags.WalletError as exc:
            raise _error(exc) from None
        bag = await bags.bag_for_update(session, tenant_id)
        out = await _bag_out(session, bag, ref)
    await _audit(
        tenant_id,
        principal.actor,
        "wallet.lowered",
        {"amount": body.amount.model_dump()},
        partner_id=principal.partner.id,
    )
    return out


@router.post("/wallet/bags/move", response_model=list[BagOut])
async def move(
    body: MoveIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> list[BagOut]:
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        source = await _tenant_of(session, partner_id, body.from_ref)
        target = await _tenant_of(session, partner_id, body.to_ref)
        await _require_bags(session, partner_id)
        target_bag = await bags.bag_for_update(session, target, partner_id=partner_id)
        target_before = target_bag.balance_micros
        try:
            await bags.move(
                session,
                partner_id=partner_id,
                from_tenant_id=source,
                to_tenant_id=target,
                amount=body.amount.amount_micros,
                idempotency_key=idempotency_key or f"move:{uuid.uuid4()}",
                actor=principal.actor,
            )
        except bags.WalletError as exc:
            raise _error(exc) from None
        out = [
            await _bag_out(session, await bags.bag_for_update(session, source), body.from_ref),
            await _bag_out(session, await bags.bag_for_update(session, target), body.to_ref),
        ]
    await _audit(
        source,
        principal.actor,
        "wallet.moved",
        {"amount": body.amount.model_dump(), "from_ref": body.from_ref, "to_ref": body.to_ref},
        partner_id=principal.partner.id,
    )
    if target_before == 0 and out[1].balance.amount_micros > 0:
        await after_balance_up(target)
    return out


@router.put("/clients/{ref}/bag/refill", response_model=BagOut)
async def set_refill(
    ref: str,
    body: RefillIn,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> BagOut:
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        tenant_id = await _tenant_of(session, partner_id, ref)
        await _require_bags(session, partner_id)
        bag = await bags.bag_for_update(session, tenant_id, partner_id=partner_id)
        if body.up_to is not None and body.up_to.currency != bag.currency:
            raise HTTPException(status_code=422, detail={"code": "currency_mismatch"})
        bag.refill_up_to_micros = (body.up_to.amount_micros or None) if body.up_to else None
        bag.revision += 1
        out = await _bag_out(session, bag, ref)
    await _audit(
        tenant_id,
        principal.actor,
        "wallet.refill_set",
        {"up_to": body.up_to.model_dump() if body.up_to else None},
        partner_id=principal.partner.id,
    )
    return out


@router.put("/clients/{ref}/bag/currency", response_model=BagOut)
async def set_currency(
    ref: str,
    body: CurrencyIn,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> BagOut:
    """Cambiar la moneda convierte el saldo: sin ``confirm`` dice cuánto quedaría."""
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        tenant_id = await _tenant_of(session, partner_id, ref)
        await _require_bags(session, partner_id)
        bag = await bags.bag_for_update(session, tenant_id, partner_id=partner_id)
        if not body.confirm and bag.balance_micros > 0 and bag.currency != body.currency:
            rate, day = await fx.rate_on(
                session, datetime.now(UTC).date(), bag.currency, body.currency
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "confirm_required",
                    "would_be": {
                        "amount_micros": fx.convert(bag.balance_micros, rate),
                        "currency": body.currency,
                    },
                    "fx": {
                        "rate": str(rate),
                        "date": day.isoformat() if day else None,
                        "source": "ECB",
                    },
                },
            )
        try:
            bag = await bags.change_currency(
                session,
                partner_id=partner_id,
                tenant_id=tenant_id,
                currency=body.currency,
                actor=principal.actor,
            )
        except bags.WalletError as exc:
            raise _error(exc) from None
        out = await _bag_out(session, bag, ref)
    await _audit(
        tenant_id,
        principal.actor,
        "wallet.currency_changed",
        {"currency": body.currency},
        partner_id=principal.partner.id,
    )
    return out


@router.post("/clients/{ref}/bag/request", status_code=status.HTTP_201_CREATED)
async def request_balance(
    ref: str,
    body: RequestIn,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """«Pedir saldo» (45.7): para quien no puede asignar; avisa a owners y admins,
    como mucho una vez al día por cliente."""
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        tenant_id = await _tenant_of(session, partner_id, ref)
        if "usage:write" in principal.permissions:
            raise HTTPException(status_code=409, detail={"code": "can_assign"})
        await bags.as_client(session, tenant_id)
        try:
            async with session.begin_nested():
                session.add(
                    BalanceRequest(
                        tenant_id=tenant_id,
                        partner_id=partner_id,
                        requested_by=principal.actor,
                        note=(body.note or "").strip() or None,
                    )
                )
                await session.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=429,
                detail={"code": "request_already_sent_today", "retry_after": "tomorrow"},
            ) from None
    from nexus_api.services.channel_config import announce

    await _audit(
        tenant_id,
        principal.actor,
        "balance.requested",
        {"note": (body.note or "")[:280]},
        partner_id=principal.partner.id,
    )
    await announce(
        tenant_id=tenant_id,
        kind="client.balance_request",
        severity="info",
        data={
            "external_client_ref": ref,
            "by": principal.actor,
            "by_name": principal.membership.display_name or principal.membership.email,
            "note": (body.note or "")[:280],
        },
        dedupe_key=f"balance_request:{tenant_id}:{datetime.now(UTC).date().isoformat()}",
    )
    return {"status": "requested"}


@router.put("/clients/{ref}/agents/{agent_id}/cap")
async def set_agent_cap(
    body: CapIn, scope: ClientScope = Depends(agent_in_path("usage:write"))
) -> dict[str, Any]:
    """El tope mensual del agente, en la moneda de la bolsa (44.1). Puede quedar
    por encima de la bolsa (44.4)."""
    agent = await scope.session.get(Agent, scope.agent_id)
    assert agent is not None
    if body.monthly_cap is not None and body.monthly_cap.amount_micros < 0:
        raise HTTPException(status_code=422, detail={"code": "invalid_amount"})
    agent.monthly_cap_micros = body.monthly_cap.amount_micros if body.monthly_cap else None
    # Subir (o quitar) el tope por encima de lo gastado reanuda al agente que el
    # tope pausó, y los avisos vuelven a poder salir con el tope nuevo (44.3).
    month = bags.month_of()
    spend = await scope.session.get(
        AgentMonthlySpend, (scope.tenant.id, agent.id, month), populate_existing=True
    )
    spent = spend.spent_micros if spend is not None else 0
    cap = agent.monthly_cap_micros
    if cap is None or spent < cap:
        if spend is not None:
            spend.reached_at = None
            if cap is None or spent < wallet_alerts.CAP_WARN_SHARE * cap:
                spend.warned_at = None
        await agent_states.resume_after_cap(scope.session, agent_id=agent.id)
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action="agent.cap_changed",
            target=f"agent:{agent.id}",
            after_json={"monthly_cap_micros": cap, "origin": "console"},
        )
    )
    await scope.session.flush()
    return {
        "agent_id": str(agent.id),
        "monthly_cap_micros": agent.monthly_cap_micros,
        "lifecycle": agent.lifecycle,
    }


@router.get("/usage/build-budget")
async def get_build_budget(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        state = await build_budget.read(session, partner_id)
        account = await session.get(PartnerWallet, partner_id)
    currency = account.currency if account is not None else "USD"
    return {
        "cap": {"amount_micros": state.cap_micros, "currency": currency},
        "spent": {"amount_micros": state.spent_micros, "currency": currency},
        "remaining": {"amount_micros": state.remaining_micros, "currency": currency},
        "state": state.state,
        "paid_by": "auphere",
    }


@router.post("/usage/build-budget/extension-request", status_code=status.HTTP_201_CREATED)
async def request_build_budget(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        try:
            await build_budget.request_more(session, partner_id, principal.actor)
        except bags.WalletError as exc:
            raise _error(exc) from None
    await _audit(
        None, principal.actor, "build_budget.extension_requested", {}, partner_id=partner_id
    )
    return {"status": "requested"}


@router.get("/wallet/migration")
async def get_migration(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """«Repartir tu saldo en bolsas» (55.3): lo que le queda a cada cliente este
    mes en su asignación de hoy, como propuesta."""
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        confirmed = await session.scalar(
            sa.select(WalletMigrationProposal.confirmed_at)
            .where(
                WalletMigrationProposal.partner_id == partner_id,
                WalletMigrationProposal.confirmed_at.is_not(None),
            )
            .limit(1)
        )
        rows = (
            await session.execute(
                sa.select(PartnerTenant.external_client_ref, PartnerAllocation.remaining)
                .join(
                    PartnerTenant,
                    sa.and_(
                        PartnerTenant.tenant_id == PartnerAllocation.tenant_id,
                        PartnerTenant.partner_id == partner_id,
                    ),
                )
                .where(PartnerAllocation.partner_id == partner_id)
                .order_by(PartnerTenant.external_client_ref)
            )
        ).all()
    return {
        "confirmed_at": confirmed.isoformat() if confirmed else None,
        "clients": [
            {
                "ref": ref,
                "amount": {"amount_micros": max(0, int(remaining or 0)), "currency": "USD"},
            }
            for ref, remaining in rows
        ],
    }


class MigrationConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: «Confirmar o ajustar» (55.3): lo que va a cada cliente, en la moneda de la
    #: cuenta, si el partner lo cambió. Lo que no viene, como la propuesta.
    adjust: dict[str, int] = Field(default_factory=dict)


@router.post("/wallet/migration/confirm")
async def confirm_migration(
    body: MigrationConfirmIn | None = None,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Confirmar el reparto: lo que le queda a cada cliente (o lo ajustado) pasa a
    su bolsa, convertido a su moneda, y el partner deja ``partner_allocations``.
    Una sola vez."""
    async with session.begin():
        partner_id = await _partner_session(session, principal)
        done = await session.scalar(
            sa.select(WalletMigrationProposal.id).where(
                WalletMigrationProposal.partner_id == partner_id,
                WalletMigrationProposal.confirmed_at.is_not(None),
            )
        )
        if done is not None:
            raise HTTPException(status_code=409, detail={"code": "already_confirmed"})
        allocations = (
            await session.scalars(
                sa.select(PartnerAllocation).where(PartnerAllocation.partner_id == partner_id)
            )
        ).all()
        proposal = {str(a.tenant_id): max(0, int(a.remaining or 0)) for a in allocations}
        if body is not None and body.adjust:
            refs: dict[str, uuid.UUID] = {
                ref: tid
                for ref, tid in (
                    await session.execute(
                        sa.select(PartnerTenant.external_client_ref, PartnerTenant.tenant_id).where(
                            PartnerTenant.partner_id == partner_id
                        )
                    )
                ).all()
            }
            for ref, amount in body.adjust.items():
                if ref not in refs or amount < 0:
                    raise HTTPException(
                        status_code=422, detail={"code": "invalid_adjust", "ref": ref}
                    )
                proposal[str(refs[ref])] = int(amount)
        session.add(
            WalletMigrationProposal(
                partner_id=partner_id,
                proposal=proposal,
                confirmed_at=datetime.now(UTC),
                confirmed_by=principal.actor,
            )
        )
        await session.flush()
        moved = 0
        for tenant, amount in proposal.items():
            bag = await bags.bag_for_update(session, uuid.UUID(tenant), partner_id=partner_id)
            if amount <= 0:
                continue
            try:
                await bags.assign(
                    session,
                    partner_id=partner_id,
                    tenant_id=bag.tenant_id,
                    amount=amount,
                    idempotency_key=f"migration:{tenant}",
                    actor=principal.actor,
                    kind="migration",
                )
            except bags.WalletError as exc:
                raise _error(exc) from None
            moved += 1
    return {"status": "confirmed", "clients": moved}


__all__ = ["router"]
