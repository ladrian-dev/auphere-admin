"""Monthly partner receipt (*recibo*) — one USD document per partner, per month.

A partner (e.g. Facelad) is billed the sum of its tenants' charges. Each
tenant's charge follows its billing model:

- **commission** — 2.5 % of WhatsApp-closed sales. The commission is captured
  per sale in the store's own currency (CLP) by the daily poll; here we sum
  the *unbilled* commissions of the period and convert the total to USD **once**,
  at the observed dollar of the emission day (``mindicador.cl``).
- **subscription** — the tenant's flat monthly plan price in USD
  (``price_override_cents`` wins over the plan's ``monthly_amount_cents``).
- **inactive** — a ``$0`` line, kept so the receipt shows the full roster.

Classification is data-driven so the whole thing is replicable for any future
partner: a tenant with a ``billing_plan_id`` is subscription; a tenant that has
ever recorded an ``agent_sales`` row is commission; anything else is inactive.

Idempotent: the ``(partner_id, period_year, period_month)`` unique index means
re-running an already-issued month returns the existing invoice. The step that
stamps ``agent_sales.invoice_line_id`` is self-healing — a re-run reconciles any
sale that was left unbilled by a partial earlier run, so a commission is never
counted twice and never silently dropped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentSale,
    BillingPlan,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Partner,
    PartnerTenant,
    Tenant,
)
from nexus_api.services.exchange_rate import clp_to_usd, get_clp_per_usd

log = structlog.get_logger(__name__)

# Days the partner has to pay after the receipt is emitted (emitted day 1,
# due day 5). Kept here rather than in a column: it is a fixed policy, not
# per-invoice data, and the due date is always derivable from the period.
PAYMENT_DUE_DAY = 5


class PartnerNotFound(RuntimeError):
    """No partner with the given slug."""


@dataclass(frozen=True)
class ReceiptLine:
    """One tenant's charge on the receipt (USD cents)."""

    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    model: str  # "commission" | "subscription" | "inactive"
    description: str
    amount_cents: int
    # Commission audit trail — CLP summed, rate applied, sales rolled up.
    commission_clp: Decimal | None = None
    sale_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class ReceiptResult:
    invoice_id: uuid.UUID
    partner_id: uuid.UUID
    partner_slug: str
    partner_name: str
    billing_email: str | None
    period_year: int
    period_month: int
    total_cents: int
    currency: str
    status: str
    clp_per_usd: Decimal | None
    issued_at: datetime | None
    due_date: date
    lines: list[ReceiptLine]
    created: bool  # False when the receipt already existed


# --- pure money helpers (unit-tested without a DB) -------------------------


def commission_cents(commission_clp: Decimal, *, clp_per_usd: Decimal) -> int:
    """USD cents owed for a CLP commission total, at the given rate."""
    usd = clp_to_usd(commission_clp, clp_per_usd=clp_per_usd)  # Decimal dollars
    return int((usd * 100).to_integral_value(rounding=ROUND_HALF_UP))


def subscription_cents(*, price_override_cents: int | None, plan_amount_cents: int | None) -> int:
    """Flat monthly price in USD cents — the override wins over the plan."""
    if price_override_cents is not None:
        return price_override_cents
    return plan_amount_cents or 0


def period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, end) UTC datetimes spanning a calendar month."""
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=UTC)
    )
    return start, end


def due_date_for(year: int, month: int) -> date:
    """The receipt for month M is emitted at the start of M+1 and due the 5th."""
    return (
        date(year + 1, 1, PAYMENT_DUE_DAY)
        if month == 12
        else date(year, month + 1, PAYMENT_DUE_DAY)
    )


# --- classification --------------------------------------------------------


@dataclass
class _TenantPlan:
    tenant: Tenant
    link: PartnerTenant
    plan: BillingPlan | None


async def _has_any_sales(sm: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> bool:
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        found = await session.execute(sa.select(AgentSale.id).limit(1))
        return found.first() is not None


async def _unbilled_period_commission(
    sm: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> tuple[Decimal, list[uuid.UUID]]:
    """Sum of unbilled commission (CLP) for the period + the sale ids rolled up.

    A sale counts when it was *paid* within the period (money actually
    collected) and has not yet been attached to an invoice line.
    """
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.select(AgentSale.id, AgentSale.commission_amount).where(
                    AgentSale.invoice_line_id.is_(None),
                    AgentSale.date_paid >= start,
                    AgentSale.date_paid < end,
                    AgentSale.commission_amount > 0,
                )
            )
        ).all()
    total = sum((r.commission_amount for r in rows), Decimal("0"))
    return total, [r.id for r in rows]


async def _mark_sales_billed(
    sm: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    sale_ids: list[uuid.UUID],
    invoice_line_id: uuid.UUID,
) -> None:
    if not sale_ids:
        return
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.update(AgentSale)
            .where(AgentSale.id.in_(sale_ids), AgentSale.invoice_line_id.is_(None))
            .values(invoice_line_id=invoice_line_id)
        )


# --- orchestration ---------------------------------------------------------


async def generate_partner_receipt(
    sm: async_sessionmaker[AsyncSession],
    *,
    partner_slug: str,
    period_year: int,
    period_month: int,
    emission_date: date | None = None,
    mark_billed: bool = True,
) -> ReceiptResult:
    """Create (or return) the partner's receipt for a period. Idempotent."""
    emission_date = emission_date or datetime.now(UTC).date()

    # 1. Load partner + roster (platform tables, no tenant scope).
    async with sm() as session:
        partner = (
            await session.execute(sa.select(Partner).where(Partner.slug == partner_slug))
        ).scalar_one_or_none()
        if partner is None:
            raise PartnerNotFound(partner_slug)
        roster = await _load_roster(session, partner.id)
        existing = (
            await session.execute(
                sa.select(Invoice).where(
                    Invoice.partner_id == partner.id,
                    Invoice.period_year == period_year,
                    Invoice.period_month == period_month,
                )
            )
        ).scalar_one_or_none()

    if existing is not None:
        return await _reconcile_existing(
            sm, partner, roster, existing, period_year, period_month, mark_billed
        )

    start, end = period_bounds(period_year, period_month)

    # 2. Classify every tenant and gather commission sums (tenant-scoped reads).
    planned: list[tuple[_TenantPlan, str, int, Decimal | None, list[uuid.UUID]]] = []
    any_commission_clp = Decimal("0")
    for tp in roster:
        if tp.tenant.billing_plan_id is not None:
            cents = subscription_cents(
                price_override_cents=tp.tenant.price_override_cents,
                plan_amount_cents=tp.plan.monthly_amount_cents if tp.plan else None,
            )
            planned.append((tp, "subscription", cents, None, []))
        elif await _has_any_sales(sm, tp.tenant.id):
            clp, ids = await _unbilled_period_commission(sm, tp.tenant.id, start, end)
            any_commission_clp += clp
            planned.append((tp, "commission", 0, clp, ids))  # cents filled after FX
        else:
            planned.append((tp, "inactive", 0, None, []))

    # 3. One FX read for the whole receipt, only if there is CLP to convert.
    clp_per_usd: Decimal | None = None
    if any_commission_clp > 0:
        clp_per_usd = await get_clp_per_usd(on=emission_date)

    # 4. Build the final lines with USD cents.
    lines: list[ReceiptLine] = []
    for tp, model, base_cents, line_clp, ids in planned:
        cents = base_cents
        if model == "commission":
            cents = (
                commission_cents(line_clp, clp_per_usd=clp_per_usd)
                if line_clp and line_clp > 0 and clp_per_usd is not None
                else 0
            )
        lines.append(
            ReceiptLine(
                tenant_id=tp.tenant.id,
                tenant_slug=tp.tenant.slug,
                tenant_name=tp.tenant.name,
                model=model,
                description=_line_description(tp, model, line_clp, clp_per_usd),
                amount_cents=cents,
                commission_clp=line_clp,
                sale_ids=tuple(ids),
            )
        )

    total_cents = sum(line.amount_cents for line in lines)
    issued_at = datetime.now(UTC)

    # 5. Persist invoice + lines (platform), then stamp sales (tenant-scoped).
    async with sm() as session:
        invoice = Invoice(
            partner_id=partner.id,
            tenant_id=None,
            period_year=period_year,
            period_month=period_month,
            status=InvoiceStatus.ISSUED.value,
            total_cents=total_cents,
            currency="USD",
            issued_at=issued_at,
        )
        session.add(invoice)
        await session.flush()
        line_id_by_tenant: dict[uuid.UUID, uuid.UUID] = {}
        for line in lines:
            row = InvoiceLine(
                invoice_id=invoice.id,
                tenant_id=line.tenant_id,
                description=line.description,
                amount_cents=line.amount_cents,
            )
            session.add(row)
            await session.flush()
            line_id_by_tenant[line.tenant_id] = row.id
        await session.commit()
        invoice_id = invoice.id

    if mark_billed:
        for line in lines:
            if line.model == "commission" and line.sale_ids:
                await _mark_sales_billed(
                    sm, line.tenant_id, list(line.sale_ids), line_id_by_tenant[line.tenant_id]
                )

    log.info(
        "partner_receipt.generated",
        partner=partner.slug,
        period=f"{period_year}-{period_month:02d}",
        total_usd=f"{total_cents / 100:.2f}",
        clp_per_usd=str(clp_per_usd) if clp_per_usd else None,
    )

    return ReceiptResult(
        invoice_id=invoice_id,
        partner_id=partner.id,
        partner_slug=partner.slug,
        partner_name=partner.name,
        billing_email=partner.billing_email,
        period_year=period_year,
        period_month=period_month,
        total_cents=total_cents,
        currency="USD",
        status=InvoiceStatus.ISSUED.value,
        clp_per_usd=clp_per_usd,
        issued_at=issued_at,
        due_date=due_date_for(period_year, period_month),
        lines=lines,
        created=True,
    )


async def _load_roster(session: AsyncSession, partner_id: uuid.UUID) -> list[_TenantPlan]:
    rows = (
        await session.execute(
            sa.select(PartnerTenant, Tenant, BillingPlan)
            .join(Tenant, PartnerTenant.tenant_id == Tenant.id)
            .outerjoin(BillingPlan, Tenant.billing_plan_id == BillingPlan.id)
            .where(PartnerTenant.partner_id == partner_id)
            .order_by(Tenant.slug)
        )
    ).all()
    return [_TenantPlan(tenant=t, link=pt, plan=bp) for pt, t, bp in rows]


def _line_description(
    tp: _TenantPlan, model: str, clp: Decimal | None, clp_per_usd: Decimal | None
) -> str:
    name = tp.tenant.name
    if model == "subscription":
        return f"{name} — suscripción mensual"
    if model == "commission":
        if clp and clp > 0 and clp_per_usd:
            return f"{name} — comisión 2,5% ventas WhatsApp (CLP {clp:,.0f} @ {clp_per_usd})"
        return f"{name} — comisión 2,5% ventas WhatsApp (sin ventas en el periodo)"
    return f"{name} — sin cargos"


async def _reconcile_existing(
    sm: async_sessionmaker[AsyncSession],
    partner: Partner,
    roster: list[_TenantPlan],
    invoice: Invoice,
    period_year: int,
    period_month: int,
    mark_billed: bool,
) -> ReceiptResult:
    """Load an already-issued receipt; self-heal any unbilled commission sales."""
    async with sm() as session:
        line_rows = (
            (
                await session.execute(
                    sa.select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                )
            )
            .scalars()
            .all()
        )
    name_by_tenant = {tp.tenant.id: (tp.tenant.slug, tp.tenant.name) for tp in roster}
    start, end = period_bounds(period_year, period_month)

    lines: list[ReceiptLine] = []
    for ln in line_rows:
        slug, name = name_by_tenant.get(ln.tenant_id, ("?", ln.description))
        model = _model_from_description(ln.description)
        if mark_billed and model == "commission":
            _clp, ids = await _unbilled_period_commission(sm, ln.tenant_id, start, end)
            if ids:  # a prior partial run left sales unstamped — fix it
                await _mark_sales_billed(sm, ln.tenant_id, ids, ln.id)
        lines.append(
            ReceiptLine(
                tenant_id=ln.tenant_id,
                tenant_slug=slug,
                tenant_name=name,
                model=model,
                description=ln.description,
                amount_cents=ln.amount_cents,
            )
        )

    return ReceiptResult(
        invoice_id=invoice.id,
        partner_id=partner.id,
        partner_slug=partner.slug,
        partner_name=partner.name,
        billing_email=partner.billing_email,
        period_year=period_year,
        period_month=period_month,
        total_cents=invoice.total_cents,
        currency=invoice.currency,
        status=invoice.status,
        clp_per_usd=None,
        issued_at=invoice.issued_at,
        due_date=due_date_for(period_year, period_month),
        lines=lines,
        created=False,
    )


def _model_from_description(description: str) -> str:
    if "suscripción" in description:
        return "subscription"
    if "comisión" in description:
        return "commission"
    return "inactive"
