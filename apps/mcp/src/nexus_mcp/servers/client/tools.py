"""client.* — preferencias e historial **de la persona con la que se habla**.

Quién es esa persona lo decide el servidor, no el modelo: ver
`nexus_mcp/_customer.py` y `tests/isolation/test_35_customer_scope_within_tenant.py`.
"""

from __future__ import annotations

from nexus_api.db.models import Appointment, Customer, Reservation
from sqlalchemy import desc, select

from nexus_mcp._agenda import not_imported, staff_names
from nexus_mcp._customer import current_customer_or_refuse
from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.client.schemas import (
    GetHistoryInput,
    GetHistoryOutput,
    GetPreferencesInput,
    GetPreferencesOutput,
    HistoryAppointment,
    UpdatePreferencesInput,
    UpdatePreferencesOutput,
)


class GetPreferences(ToolBase):
    name = "client.get_preferences"
    description = (
        "Read the stored preferences of the person you are talking to (preferred "
        "barber, favourite service, language, etc.). Returns an empty object if "
        "nothing is stored. There is no way to read anyone else's."
    )
    input_model = GetPreferencesInput
    output_model = GetPreferencesOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetPreferencesInput)
        customer_id = current_customer_or_refuse("leer preferencias")
        async with tool_session() as session:
            customer = await session.get(Customer, customer_id)
            if customer is None:
                raise ToolError(f"customer {customer_id} not found for this tenant")
            return GetPreferencesOutput(
                customer_id=customer.id,
                preferences=dict(customer.preferences or {}),
            )


class UpdatePreferences(ToolBase):
    name = "client.update_preferences"
    description = (
        "Merge a partial preferences dict into the preferences of the person you "
        "are talking to. Existing keys are overwritten by the new values; keys not "
        "in the input are preserved. Returns the resulting full preferences dict."
    )
    input_model = UpdatePreferencesInput
    output_model = UpdatePreferencesOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, UpdatePreferencesInput)
        customer_id = current_customer_or_refuse("guardar preferencias")
        async with tool_session() as session:
            customer = await session.get(Customer, customer_id)
            if customer is None:
                raise ToolError(f"customer {customer_id} not found for this tenant")
            merged = {**(customer.preferences or {}), **payload.preferences}
            customer.preferences = merged
            await session.flush()
            await session.refresh(customer)
            return UpdatePreferencesOutput(
                customer_id=customer.id,
                preferences=dict(customer.preferences or {}),
                status="updated",
            )


class GetHistory(ToolBase):
    name = "client.get_history"
    description = (
        "Return the most recent appointments of the person you are talking to "
        "(default 10, max 50), sorted by start time descending — their Reservas "
        "bookings and any older appointment. Useful for 'lo mismo de siempre' "
        "lookups and for telling a returning customer when they last visited. "
        "There is no way to read anyone else's history."
    )
    input_model = GetHistoryInput
    output_model = GetHistoryOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetHistoryInput)
        customer_id = current_customer_or_refuse("leer el historial")
        async with tool_session() as session:
            # Spec 048 (requisito 4.1): the Reservas bookings, and the older
            # appointments that were not passed over (an imported one counts
            # once, as its booking).
            bookings = (
                (
                    await session.execute(
                        select(Reservation)
                        .where(Reservation.customer_id == customer_id)
                        .order_by(desc(Reservation.starts_at))
                        .limit(payload.limit)
                    )
                )
                .scalars()
                .all()
            )
            older = (
                (
                    await session.execute(
                        select(Appointment)
                        .where(Appointment.customer_id == customer_id, not_imported())
                        .order_by(desc(Appointment.starts_at))
                        .limit(payload.limit)
                    )
                )
                .scalars()
                .all()
            )
            names = await staff_names(session, (r.staff_id for r in bookings))
            items = [
                HistoryAppointment(
                    appointment_id=r.id,
                    starts_at=r.starts_at,
                    service_name=r.service_name or "",
                    barber_id=None,
                    status=r.status,
                    price_cents=int(r.price_minor or 0),
                    currency=r.currency or "CLP",
                    source="reservas",
                    staff_name=names.get(r.staff_id) if r.staff_id else None,
                )
                for r in bookings
            ] + [
                HistoryAppointment(
                    appointment_id=a.id,
                    starts_at=a.starts_at,
                    service_name=a.service_name,
                    barber_id=a.barber_id,
                    status=a.status.value,
                    price_cents=a.price_cents,
                    currency=a.currency,
                    source="appointments",
                )
                for a in older
            ]
            items.sort(key=lambda h: h.starts_at, reverse=True)
        return GetHistoryOutput(customer_id=customer_id, appointments=items[: payload.limit])


CLIENT_TOOLS: tuple[type[ToolBase], ...] = (GetPreferences, UpdatePreferences, GetHistory)
