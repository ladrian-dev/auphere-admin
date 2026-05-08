"""booking.* — relational facade over the appointments table.

Cuando el tenant tiene integration AgendaPro activa
(``tenant_credentials WHERE integration='agendapro' AND
needs_reauth=false``), las tools mutativas delegan a ``agendapro.*``
ANTES de persistir local. La fila local pasa a ser shadow cache con
``external_ref`` poblado. Si AgendaPro retorna error o needs_reauth, la
transacción local rollbackea — no creamos filas huérfanas sin ref.

Ver ``agendapro_delegate.py`` para los helpers; ver
``architecture/mcp-registry.md`` para el contrato.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Appointment, AppointmentStatus, Customer, KGNode
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.booking.agendapro_delegate import (
    delegate_cancel,
    delegate_create,
    delegate_modify,
    get_active_credentials,
    write_audit_with_screenshot,
)
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

log = structlog.get_logger(__name__)


async def _resolve_barber_external_id(session: Any, barber_id: Any) -> str | None:
    """Resuelve ``kg_nodes.properties.agendapro_id`` para el barber dado.
    Retorna None si no existe el mapping (caller lo trata como "any
    barber" del lado AgendaPro)."""
    if barber_id is None:
        return None
    node = await session.get(KGNode, barber_id)
    if node is None:
        return None
    props = node.properties or {}
    val = props.get("agendapro_id")
    return str(val) if val else None


async def _resolve_customer_contact(session: Any, customer_id: Any) -> tuple[str, str, str | None]:
    """(name, phone, email). El ``identifier`` del Customer típicamente
    es el phone (canal whatsapp); ``preferences.email`` puede traer el
    email."""
    cust = await session.get(Customer, customer_id)
    if cust is None:
        raise ToolError(f"customer {customer_id} not found")
    name = cust.name or (cust.preferences or {}).get("name") or "Cliente"
    phone = cust.identifier
    email = (cust.preferences or {}).get("email")
    return str(name), str(phone), (str(email) if email else None)


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

            # Bloque E branch: si el tenant tiene integration AgendaPro
            # activa, delegamos primero, capturamos external_ref y
            # screenshot, después persistimos local. Si AgendaPro falla,
            # la transacción local entera rollbackea (no rows huérfanas).
            external_ref: str | None = None
            creds = await get_active_credentials(session)
            if creds is not None:
                barber_external_id = await _resolve_barber_external_id(session, payload.barber_id)
                cust_name, cust_phone, cust_email = await _resolve_customer_contact(
                    session, payload.customer_id
                )
                ap_result = await delegate_create(
                    session,
                    creds=creds,
                    tenant_id=tenant_id,
                    starts_at=payload.starts_at,
                    duration_min=payload.duration_min,
                    service_name=payload.service_name,
                    barber_external_id=barber_external_id,
                    customer_name=cust_name,
                    customer_phone=cust_phone,
                    customer_email=cust_email,
                    notes=payload.notes,
                    idempotency_key=payload.idempotency_key,
                )
                external_ref = (ap_result.get("appointment") or {}).get("external_ref")
                if not external_ref:
                    raise ToolError("agendapro create_appointment returned no external_ref")
                await write_audit_with_screenshot(
                    session,
                    tenant_id=tenant_id,
                    action="booking.create_appointment",
                    target=f"agendapro:{external_ref}",
                    screenshot=ap_result.get("screenshot"),
                    extra={
                        "service_name": payload.service_name,
                        "starts_at": payload.starts_at.isoformat(),
                    },
                )
                log.info(
                    "booking.create.delegated_to_agendapro",
                    tenant_id=str(tenant_id),
                    external_ref=external_ref,
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
                external_ref=external_ref,
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
        tenant_id = require_current_tenant()
        async with tool_session() as session:
            appt = await session.get(Appointment, payload.appointment_id)
            if appt is None:
                raise ToolError(f"appointment {payload.appointment_id} not found for this tenant")
            if appt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
                raise ToolError(f"appointment is {appt.status.value}; cannot be modified")

            # AgendaPro branch: si la cita tiene external_ref, delegamos
            # primero. Si AgendaPro falla, transacción local rollback.
            if appt.external_ref is not None:
                creds = await get_active_credentials(session)
                if creds is not None:
                    new_barber_external_id = await _resolve_barber_external_id(
                        session, payload.new_barber_id
                    )
                    ap_result = await delegate_modify(
                        session,
                        creds=creds,
                        tenant_id=tenant_id,
                        external_ref=appt.external_ref,
                        new_starts_at=payload.new_starts_at,
                        new_duration_min=payload.new_duration_min,
                        new_barber_external_id=new_barber_external_id,
                        new_service_name=payload.new_service_name,
                    )
                    await write_audit_with_screenshot(
                        session,
                        tenant_id=tenant_id,
                        action="booking.modify_appointment",
                        target=f"agendapro:{appt.external_ref}",
                        screenshot=ap_result.get("screenshot"),
                    )

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
        tenant_id = require_current_tenant()
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

            # AgendaPro branch: si la cita tiene external_ref, delegamos.
            # Idempotente — si la cita ya fue cancelada en AgendaPro,
            # el server Node hace no-op.
            if appt.external_ref is not None and appt.status != AppointmentStatus.CANCELLED:
                creds = await get_active_credentials(session)
                if creds is not None:
                    ap_result = await delegate_cancel(
                        session,
                        creds=creds,
                        tenant_id=tenant_id,
                        external_ref=appt.external_ref,
                        reason=payload.reason,
                    )
                    await write_audit_with_screenshot(
                        session,
                        tenant_id=tenant_id,
                        action="booking.cancel_appointment",
                        target=f"agendapro:{appt.external_ref}",
                        screenshot=ap_result.get("screenshot"),
                        extra={"fee_pct": fee_pct},
                    )

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
