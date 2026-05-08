"""booking.* — relational facade over the appointments table."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Appointment, AppointmentStatus
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.booking.availability import find_free_slots
from nexus_mcp.servers.booking.schemas import (
    AppointmentBrief,
    AvailableSlot,
    CancelAppointmentInput,
    CancelAppointmentOutput,
    CheckAvailabilityInput,
    CheckAvailabilityOutput,
    CreateAppointmentInput,
    CreateAppointmentOutput,
    GetAppointmentsInput,
    GetAppointmentsOutput,
    ModifyAppointmentInput,
    ModifyAppointmentOutput,
)


def _to_brief(a: Appointment) -> AppointmentBrief:
    return AppointmentBrief(
        appointment_id=a.id,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        service_name=a.service_name,
        barber_id=a.barber_id,
        status=a.status.value,
        price_cents=a.price_cents,
        currency=a.currency,
    )


# ── check_availability ───────────────────────────────────────────────────────


class CheckAvailability(ToolBase):
    name = "booking.check_availability"
    description = (
        "List free time slots on a given date for a service. Optionally restrict "
        "to a preferred barber. Returns slots aligned to 30-minute boundaries that "
        "fit the requested duration without colliding with existing appointments. "
        "Use the slots verbatim as the candidate times to offer the customer."
    )
    input_model = CheckAvailabilityInput
    output_model = CheckAvailabilityOutput
    side_effects = ("external_api",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CheckAvailabilityInput)
        tenant_id = require_current_tenant()
        async with tool_session() as session:
            slots = await find_free_slots(
                session,
                tenant_id=tenant_id,
                on_date=payload.on_date,
                duration_min=payload.duration_min,
                barber_id=payload.barber_id,
            )
        return CheckAvailabilityOutput(
            on_date=payload.on_date,
            service_name=payload.service_name,
            slots=[AvailableSlot(starts_at=s, ends_at=e, barber_id=b) for (s, e, b) in slots],
        )


# ── create_appointment ───────────────────────────────────────────────────────


class CreateAppointment(ToolBase):
    name = "booking.create_appointment"
    description = (
        "Book an appointment. Idempotent: a second call with the same "
        "``idempotency_key`` returns the original row without creating a duplicate "
        "(required because the YCloud webhook may retry on transient errors). The "
        "caller should derive a stable key from the conversation turn — for "
        "example, ``conv:{conversation_id}:create_appt:{intent_hash}``."
    )
    input_model = CreateAppointmentInput
    output_model = CreateAppointmentOutput
    side_effects = ("external_api", "mutates_db")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CreateAppointmentInput)
        tenant_id = require_current_tenant()
        ends_at = payload.starts_at + timedelta(minutes=payload.duration_min)

        async with tool_session() as session:
            # Idempotent path: replay if (tenant_id, idempotency_key) is taken.
            stmt = select(Appointment).where(Appointment.idempotency_key == payload.idempotency_key)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return CreateAppointmentOutput(
                    appointment=_to_brief(existing), idempotent_replay=True
                )

            row = Appointment(
                tenant_id=tenant_id,
                customer_id=payload.customer_id,
                barber_id=payload.barber_id,
                service_name=payload.service_name,
                service_duration_min=payload.duration_min,
                starts_at=payload.starts_at,
                ends_at=ends_at,
                price_cents=payload.price_cents,
                currency=payload.currency,
                status=AppointmentStatus.BOOKED,
                idempotency_key=payload.idempotency_key,
                notes=payload.notes,
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                # Lost the race: a concurrent caller already inserted the
                # idempotent row. Re-select and return that one.
                await session.rollback()
                # session is now closed by the context manager's rollback; we
                # cannot re-use it. Open a new session in the same scope.
                async with tool_session() as session2:
                    again = (
                        await session2.execute(
                            select(Appointment).where(
                                Appointment.idempotency_key == payload.idempotency_key
                            )
                        )
                    ).scalar_one_or_none()
                    if again is None:
                        raise ToolError(
                            "idempotency_key collision with no replay row — "
                            "transactional anomaly, refusing to retry"
                        ) from None
                    return CreateAppointmentOutput(
                        appointment=_to_brief(again), idempotent_replay=True
                    )
            await session.refresh(row)
            return CreateAppointmentOutput(appointment=_to_brief(row), idempotent_replay=False)


# ── modify_appointment ───────────────────────────────────────────────────────


class ModifyAppointment(ToolBase):
    name = "booking.modify_appointment"
    description = (
        "Change time, duration, barber or service of an existing appointment. "
        "All fields are optional — only the fields you pass are changed. Cancelled "
        "or completed appointments cannot be modified."
    )
    input_model = ModifyAppointmentInput
    output_model = ModifyAppointmentOutput
    side_effects = ("external_api", "mutates_db")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, ModifyAppointmentInput)
        async with tool_session() as session:
            appt = await session.get(Appointment, payload.appointment_id)
            if appt is None:
                raise ToolError(f"appointment {payload.appointment_id} not found for this tenant")
            if appt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
                raise ToolError(f"appointment is {appt.status.value}; cannot be modified")

            changed = False
            if payload.new_starts_at is not None:
                appt.starts_at = payload.new_starts_at
                changed = True
            if payload.new_duration_min is not None:
                appt.service_duration_min = payload.new_duration_min
                changed = True
            if (payload.new_starts_at is not None) or (payload.new_duration_min is not None):
                appt.ends_at = appt.starts_at + timedelta(minutes=appt.service_duration_min)
                changed = True
            if payload.new_barber_id is not None:
                appt.barber_id = payload.new_barber_id
                changed = True
            if payload.new_service_name is not None:
                appt.service_name = payload.new_service_name
                changed = True

            if changed:
                await session.flush()
                await session.refresh(appt)

        return ModifyAppointmentOutput(
            appointment=_to_brief(appt),
            status="modified" if changed else "no_changes",
        )


# ── cancel_appointment ───────────────────────────────────────────────────────


class CancelAppointment(ToolBase):
    name = "booking.cancel_appointment"
    description = (
        "Cancel an appointment. Applies the cancellation fee from the tenant's "
        "policies if the appointment is within the no-fee window. Idempotent: "
        "cancelling an already-cancelled appointment is a no-op (returns same fee)."
    )
    input_model = CancelAppointmentInput
    output_model = CancelAppointmentOutput
    side_effects = ("external_api", "mutates_db")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CancelAppointmentInput)
        async with tool_session() as session:
            appt = await session.get(Appointment, payload.appointment_id)
            if appt is None:
                raise ToolError(f"appointment {payload.appointment_id} not found for this tenant")

            now = datetime.now(UTC)
            hours_to = (appt.starts_at - now).total_seconds() / 3600.0
            # Block D placeholder policy: <24h = 50% fee, otherwise 0%.
            # The real policy will be read from agent_config.policies in
            # Block F (it's per-tenant). The schema is stable.
            fee_pct = 0 if hours_to >= 24 else 50

            if appt.status != AppointmentStatus.CANCELLED:
                appt.status = AppointmentStatus.CANCELLED
                appt.cancellation_fee_pct = fee_pct
                if payload.reason:
                    existing = appt.notes or ""
                    appt.notes = f"{existing}\n[cancel] {payload.reason}".strip()
                await session.flush()

        return CancelAppointmentOutput(
            appointment_id=appt.id,
            status="cancelled",
            fee_pct=appt.cancellation_fee_pct,
        )


# ── get_appointments ─────────────────────────────────────────────────────────


class GetAppointments(ToolBase):
    name = "booking.get_appointments"
    description = (
        "List appointments for the tenant, optionally restricted to a customer or a "
        "date range. Default returns the 20 most recent. Use ``only_upcoming=true`` "
        "to get future appointments for the customer (most useful for reschedule and "
        "cancellation flows)."
    )
    input_model = GetAppointmentsInput
    output_model = GetAppointmentsOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetAppointmentsInput)
        async with tool_session() as session:
            stmt = select(Appointment)
            if payload.customer_id is not None:
                stmt = stmt.where(Appointment.customer_id == payload.customer_id)
            if payload.only_upcoming:
                stmt = stmt.where(Appointment.starts_at >= datetime.now(UTC))
            else:
                if payload.from_date is not None:
                    stmt = stmt.where(
                        Appointment.starts_at
                        >= datetime.combine(payload.from_date, datetime.min.time(), tzinfo=UTC)
                    )
                if payload.to_date is not None:
                    stmt = stmt.where(
                        Appointment.starts_at
                        <= datetime.combine(payload.to_date, datetime.max.time(), tzinfo=UTC)
                    )
            stmt = stmt.order_by(desc(Appointment.starts_at)).limit(payload.limit)
            rows = (await session.execute(stmt)).scalars().all()
            briefs = [_to_brief(r) for r in rows]
        return GetAppointmentsOutput(appointments=briefs)


BOOKING_TOOLS: tuple[type[ToolBase], ...] = (
    CheckAvailability,
    CreateAppointment,
    ModifyAppointment,
    CancelAppointment,
    GetAppointments,
)
