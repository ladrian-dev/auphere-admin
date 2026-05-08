"""commission.* — read-only earnings + commission math.

Block D ships the reports computed from the local ``appointments`` table.
The compensation MODEL per barber is stored as a ``kg_nodes`` row with
``label='Barber'`` and ``properties.commission_model`` matching one of
``employee``, ``commission`` or ``chair_rental`` plus the relevant
parameters. If a barber has no model, we fall back to ``employee`` (0%
commission per service — the agent should not ad-lib commission terms).

Outstanding for Block F / future:
- ``payments`` table: today the ``price_cents`` on the appointment is the
  proxy for what the customer paid. When Block F introduces the payment
  capture (POS / Mercado Pago), the report should use the captured amount
  instead. This is documented as a TODO in nexus-state.md.
- Tip handling: ``calculate_commission`` accepts tips, but ``get_daily_report``
  doesn't have a source for them yet — same future-payment dependency.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, time
from typing import Any

from nexus_api.db.models import Appointment, AppointmentStatus, KGNode
from sqlalchemy import select

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_mcp.servers.commission.schemas import (
    BarberDailyTotal,
    CalculateCommissionInput,
    CalculateCommissionOutput,
    GetBarberEarningsInput,
    GetBarberEarningsOutput,
    GetDailyReportInput,
    GetDailyReportOutput,
)


def _model_for_barber(barber: KGNode | None) -> tuple[str, float]:
    """Return ``(model_name, commission_pct_as_fraction)``.

    Defaults to ``employee`` (0% commission) if the barber row has no
    ``commission_model`` property. The fraction is in 0..1 (0.40 = 40%).
    """
    if barber is None:
        return ("employee", 0.0)
    props: dict[str, Any] = barber.properties or {}
    model = str(props.get("commission_model") or "employee")
    pct_raw = props.get("commission_pct")
    if pct_raw is None:
        return (model, 0.0 if model == "employee" else 0.4)
    try:
        pct = float(pct_raw)
    except (TypeError, ValueError):
        return (model, 0.0)
    if pct > 1.0:  # accept either 40 or 0.4
        pct = pct / 100.0
    return (model, max(0.0, min(1.0, pct)))


# ── calculate_commission ─────────────────────────────────────────────────────


class CalculateCommission(ToolBase):
    name = "commission.calculate_commission"
    description = (
        "Compute the commission a barber earns on a service amount. Returns the "
        "commission portion plus tip (passed through 1:1) and a total. Uses the "
        "barber's commission model from the KG; falls back to employee (0%) if "
        "not set."
    )
    input_model = CalculateCommissionInput
    output_model = CalculateCommissionOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CalculateCommissionInput)
        async with tool_session() as session:
            barber = await session.get(KGNode, payload.barber_id)
            model, fraction = _model_for_barber(barber)
        commission = round(payload.service_amount_cents * fraction)
        return CalculateCommissionOutput(
            barber_id=payload.barber_id,
            model=model,
            commission_cents=commission,
            tip_cents=payload.tip_amount_cents,
            total_cents=commission + payload.tip_amount_cents,
            currency=payload.currency,
        )


# ── get_barber_earnings ──────────────────────────────────────────────────────


class GetBarberEarnings(ToolBase):
    name = "commission.get_barber_earnings"
    description = (
        "Aggregate completed-or-confirmed appointments for one barber over a date "
        "range and return appointment count, gross revenue and commission earned."
    )
    input_model = GetBarberEarningsInput
    output_model = GetBarberEarningsOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetBarberEarningsInput)
        async with tool_session() as session:
            barber = await session.get(KGNode, payload.barber_id)
            _, fraction = _model_for_barber(barber)

            stmt = (
                select(Appointment)
                .where(Appointment.barber_id == payload.barber_id)
                .where(
                    Appointment.starts_at
                    >= datetime.combine(payload.from_date, time.min, tzinfo=UTC)
                )
                .where(
                    Appointment.starts_at <= datetime.combine(payload.to_date, time.max, tzinfo=UTC)
                )
                .where(
                    Appointment.status.in_(
                        (AppointmentStatus.COMPLETED, AppointmentStatus.CONFIRMED)
                    )
                )
            )
            rows = list((await session.execute(stmt)).scalars().all())

        gross = sum(r.price_cents for r in rows)
        currency = rows[0].currency if rows else "CLP"
        commission = round(gross * fraction)
        return GetBarberEarningsOutput(
            barber_id=payload.barber_id,
            appointments_count=len(rows),
            gross_revenue_cents=gross,
            commission_cents=commission,
            currency=currency,
        )


# ── get_daily_report ─────────────────────────────────────────────────────────


class GetDailyReport(ToolBase):
    name = "commission.get_daily_report"
    description = (
        "Daily consolidated report: total appointments, gross revenue, total "
        "commission and a per-barber breakdown for the given date. Counts only "
        "confirmed/completed appointments (excludes cancellations and no-shows)."
    )
    input_model = GetDailyReportInput
    output_model = GetDailyReportOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetDailyReportInput)
        day_start = datetime.combine(payload.on_date, time.min, tzinfo=UTC)
        day_end = datetime.combine(payload.on_date, time.max, tzinfo=UTC)

        async with tool_session() as session:
            stmt = (
                select(Appointment)
                .where(Appointment.starts_at >= day_start)
                .where(Appointment.starts_at <= day_end)
                .where(
                    Appointment.status.in_(
                        (AppointmentStatus.COMPLETED, AppointmentStatus.CONFIRMED)
                    )
                )
            )
            rows = list((await session.execute(stmt)).scalars().all())

            barber_ids = sorted({r.barber_id for r in rows if r.barber_id is not None})
            barbers: dict[uuid.UUID, KGNode] = {}
            if barber_ids:
                bstmt = select(KGNode).where(KGNode.id.in_(barber_ids))
                for node in (await session.execute(bstmt)).scalars().all():
                    barbers[node.id] = node

        # Aggregate.
        per_barber: dict[uuid.UUID | None, dict[str, int]] = defaultdict(
            lambda: {"count": 0, "gross": 0, "commission": 0}
        )
        total_gross = 0
        total_commission = 0
        for r in rows:
            _, fraction = _model_for_barber(barbers.get(r.barber_id) if r.barber_id else None)
            commission = round(r.price_cents * fraction)
            bucket = per_barber[r.barber_id]
            bucket["count"] += 1
            bucket["gross"] += r.price_cents
            bucket["commission"] += commission
            total_gross += r.price_cents
            total_commission += commission

        currency = rows[0].currency if rows else "CLP"
        by_barber = [
            BarberDailyTotal(
                barber_id=b_id,
                appointments_count=bucket["count"],
                gross_revenue_cents=bucket["gross"],
                commission_cents=bucket["commission"],
            )
            for b_id, bucket in per_barber.items()
        ]
        return GetDailyReportOutput(
            on_date=payload.on_date,
            appointments_count=len(rows),
            gross_revenue_cents=total_gross,
            total_commission_cents=total_commission,
            currency=currency,
            by_barber=by_barber,
        )


COMMISSION_TOOLS: tuple[type[ToolBase], ...] = (
    CalculateCommission,
    GetBarberEarnings,
    GetDailyReport,
)
