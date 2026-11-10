"""commission.* — read-only earnings + commission math.

The reports count the bookings of both agendas (spec 048, requisito 4.2): the
Reservas ones (``reservations``, matched to the barber by the staff member's
name) and the ``appointments`` from before that were not passed over — an
imported one counts once, as its booking. The compensation MODEL per barber is stored as a ``kg_nodes`` row with
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
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from nexus_api.db.models import Appointment, AppointmentStatus, KGNode, Reservation
from nexus_api.services.reservations.passing import name_key
from sqlalchemy import select

from nexus_mcp._agenda import COUNTED, barbers_by_name, not_imported, staff_names, staff_of_barber
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


@dataclass(frozen=True)
class _Line:
    """One counted booking, whichever agenda it lives in."""

    barber_id: uuid.UUID | None
    staff_id: uuid.UUID | None
    price_cents: int
    currency: str


_DONE = (AppointmentStatus.COMPLETED, AppointmentStatus.CONFIRMED)


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

            lo = datetime.combine(payload.from_date, time.min, tzinfo=UTC)
            hi = datetime.combine(payload.to_date, time.max, tzinfo=UTC)
            stmt = (
                select(Appointment)
                .where(Appointment.barber_id == payload.barber_id)
                .where(Appointment.starts_at >= lo, Appointment.starts_at <= hi)
                .where(Appointment.status.in_(_DONE), not_imported())
            )
            rows = [
                _Line(r.barber_id, None, r.price_cents, r.currency)
                for r in (await session.execute(stmt)).scalars().all()
            ]
            staff = await staff_of_barber(session, barber)
            if staff:
                booked = await session.execute(
                    select(Reservation).where(
                        Reservation.staff_id.in_(staff),
                        Reservation.starts_at >= lo,
                        Reservation.starts_at <= hi,
                        Reservation.status.in_(COUNTED),
                    )
                )
                rows += [
                    _Line(
                        payload.barber_id, r.staff_id, int(r.price_minor or 0), r.currency or "CLP"
                    )
                    for r in booked.scalars().all()
                ]

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
        "confirmed/completed appointments and bookings (excludes cancellations "
        "and no-shows)."
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
                .where(Appointment.status.in_(_DONE), not_imported())
            )
            rows = [
                _Line(r.barber_id, None, r.price_cents, r.currency)
                for r in (await session.execute(stmt)).scalars().all()
            ]
            booked = (
                (
                    await session.execute(
                        select(Reservation).where(
                            Reservation.starts_at >= day_start,
                            Reservation.starts_at <= day_end,
                            Reservation.status.in_(COUNTED),
                        )
                    )
                )
                .scalars()
                .all()
            )
            names = await staff_names(session, (r.staff_id for r in booked))
            by_name = await barbers_by_name(session) if booked else {}
            for r in booked:
                node = by_name.get(name_key(names.get(r.staff_id))) if r.staff_id else None
                rows.append(
                    _Line(
                        node.id if node is not None else None,
                        None if node is not None else r.staff_id,
                        int(r.price_minor or 0),
                        r.currency or "CLP",
                    )
                )

            barber_ids = sorted({r.barber_id for r in rows if r.barber_id is not None})
            barbers: dict[uuid.UUID, KGNode] = {}
            if barber_ids:
                bstmt = select(KGNode).where(KGNode.id.in_(barber_ids))
                for node in (await session.execute(bstmt)).scalars().all():
                    barbers[node.id] = node

        # Aggregate: by barber, or by the Reservas staff member nobody in the
        # graph matches (then the model is the default one).
        per_barber: dict[tuple[uuid.UUID | None, uuid.UUID | None], dict[str, int]] = defaultdict(
            lambda: {"count": 0, "gross": 0, "commission": 0}
        )
        total_gross = 0
        total_commission = 0
        for r in rows:
            _, fraction = _model_for_barber(barbers.get(r.barber_id) if r.barber_id else None)
            commission = round(r.price_cents * fraction)
            bucket = per_barber[(r.barber_id, r.staff_id)]
            bucket["count"] += 1
            bucket["gross"] += r.price_cents
            bucket["commission"] += commission
            total_gross += r.price_cents
            total_commission += commission

        currency = rows[0].currency if rows else "CLP"
        by_barber = [
            BarberDailyTotal(
                barber_id=b_id,
                name=(
                    str((barbers[b_id].properties or {}).get("name") or "") or None
                    if b_id is not None and b_id in barbers
                    else names.get(s_id)
                    if s_id is not None
                    else None
                ),
                appointments_count=bucket["count"],
                gross_revenue_cents=bucket["gross"],
                commission_cents=bucket["commission"],
            )
            for (b_id, s_id), bucket in per_barber.items()
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
