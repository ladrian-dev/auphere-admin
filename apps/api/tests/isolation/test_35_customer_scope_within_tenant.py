"""Garantía 8, en el eje de reservas: dentro de un tenant, cada cliente ve lo suyo.

Las siete primeras garantías de `architecture/agent-isolation.md` cortan **entre
tenants**. Este fichero cubre el eje que ninguna de ellas mira: dos clientes
finales **del mismo negocio**. La RLS no ayuda aquí —las dos citas son del
mismo tenant y son legítimamente suyas—, así que la única frontera es qué
cliente resuelve la herramienta, y de dónde lo saca.

Cuando se escribió, ese eje no estaba declarado en ninguna parte: este fichero
bloqueaba merges sin colgar de ninguna garantía. Desde la spec 014 es **la
octava**, y `test_37_customer_axis_contract.py` la vigila en todos los servidores
a la vez. Aquí se prueba el comportamiento con clientes de verdad; allí, que
ninguna firma deje que el modelo elija persona.

La regla, que ya estaba escrita en dos sitios del código antes de que este
fichero existiera:

* `core/tenant_context.py` fija el cliente del turno en servidor «so
  customer-facing tools can resolve "the person I'm talking to" WITHOUT
  trusting an LLM-supplied identifier … making cross-customer lookups
  impossible»;
* `nexus_mcp/base.py` prohíbe campos extra «so the LLM cannot smuggle
  ``tenant_id`` or other ambient state through arguments».

El cliente **es** ambient state. Una herramienta que lo acepta como argumento
deja que el modelo —o quien logre dictarle una frase— elija a quién mira.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from nexus_mcp.base import ToolError
from nexus_mcp.servers.booking.schemas import (
    CancelAppointmentInput,
    CreateAppointmentInput,
    GetAppointmentsInput,
    ModifyAppointmentInput,
)
from nexus_mcp.servers.booking.tools import (
    CancelAppointment,
    CreateAppointment,
    GetAppointments,
    ModifyAppointment,
)
from pydantic import ValidationError

from nexus_api.core.tenant_context import customer_context, tenant_context
from nexus_api.db.models import Appointment, AppointmentStatus, Customer

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def _seed(db_session, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Dos clientes del **mismo** negocio, una cita futura cada uno."""
    mine = Customer(tenant_id=tenant_id, identifier="+34600000001", name=None, preferences={})
    other = Customer(tenant_id=tenant_id, identifier="+34600000002", name=None, preferences={})
    db_session.add_all([mine, other])
    await db_session.commit()
    await db_session.refresh(mine)
    await db_session.refresh(other)

    start = datetime.now(UTC) + timedelta(days=3)
    appts = {}
    for key, customer, service in (
        ("mine", mine, "Limpieza dental"),
        ("other", other, "Endodoncia"),
    ):
        row = Appointment(
            tenant_id=tenant_id,
            customer_id=customer.id,
            service_name=service,
            service_duration_min=30,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status=AppointmentStatus.BOOKED,
        )
        db_session.add(row)
        await db_session.commit()
        await db_session.refresh(row)
        appts[key] = row.id

    return {
        "mine": mine.id,
        "other": other.id,
        "appt_mine": appts["mine"],
        "appt_other": appts["other"],
    }


# ── leer ───────────────────────────────────────────────────────────────


async def test_get_appointments_only_returns_the_customer_in_context(db_session, tenants_ab):
    """Sin argumento de cliente, la herramienta devolvía el tenant entero."""
    t = tenants_ab["a"]
    w = await _seed(db_session, t)

    with tenant_context(t), customer_context(w["mine"]):
        out = await GetAppointments().run(GetAppointmentsInput())

    ids = {a.appointment_id for a in out.appointments}
    assert ids == {w["appt_mine"]}, "la agenda de otro cliente del mismo negocio no es mía"


async def test_only_upcoming_does_not_widen_the_scope(db_session, tenants_ab):
    t = tenants_ab["a"]
    w = await _seed(db_session, t)

    with tenant_context(t), customer_context(w["mine"]):
        out = await GetAppointments().run(GetAppointmentsInput(only_upcoming=True))

    assert {a.appointment_id for a in out.appointments} == {w["appt_mine"]}


async def test_the_model_cannot_name_a_customer():
    """El cliente es ambient state: no viaja como argumento en ninguna entrada."""
    for model in (
        GetAppointmentsInput,
        CreateAppointmentInput,
        CancelAppointmentInput,
        ModifyAppointmentInput,
    ):
        assert "customer_id" not in model.model_fields, (
            f"{model.__name__} deja que el modelo elija a quién mira"
        )

    with pytest.raises(ValidationError):  # extra="forbid"
        GetAppointmentsInput(customer_id=uuid.uuid4())


# ── escribir ───────────────────────────────────────────────────────────


async def test_cancelling_someone_elses_appointment_is_refused(db_session, tenants_ab):
    t = tenants_ab["a"]
    w = await _seed(db_session, t)

    with (
        tenant_context(t),
        customer_context(w["mine"]),
        pytest.raises(ToolError),
    ):
        await CancelAppointment().run(CancelAppointmentInput(appointment_id=w["appt_other"]))

    still = await db_session.get(Appointment, w["appt_other"])
    await db_session.refresh(still)
    assert still.status is AppointmentStatus.BOOKED, "la cita ajena siguió en pie"


async def test_modifying_someone_elses_appointment_is_refused(db_session, tenants_ab):
    t = tenants_ab["a"]
    w = await _seed(db_session, t)
    moved_to = datetime.now(UTC) + timedelta(days=9)

    with (
        tenant_context(t),
        customer_context(w["mine"]),
        pytest.raises(ToolError),
    ):
        await ModifyAppointment().run(
            ModifyAppointmentInput(appointment_id=w["appt_other"], new_starts_at=moved_to)
        )

    untouched = await db_session.get(Appointment, w["appt_other"])
    await db_session.refresh(untouched)
    assert untouched.starts_at != moved_to


async def test_a_booking_belongs_to_the_customer_in_context(db_session, tenants_ab):
    t = tenants_ab["a"]
    w = await _seed(db_session, t)
    when = datetime.now(UTC) + timedelta(days=5)

    with tenant_context(t), customer_context(w["mine"]):
        out = await CreateAppointment().run(
            CreateAppointmentInput(
                service_name="Revisión",
                starts_at=when,
                duration_min=30,
                idempotency_key=f"iso35:{uuid.uuid4().hex}",
            )
        )

    row = await db_session.get(Appointment, out.appointment.appointment_id)
    await db_session.refresh(row)
    assert row.customer_id == w["mine"]


# ── sin cliente en contexto, no se atiende a nadie ─────────────────────


async def test_without_a_customer_in_context_the_tools_refuse(db_session, tenants_ab):
    """Mismo guardia que ``billing.get_my_debt``: sin cliente, no hay datos.

    Un turno sin cliente resuelto es un turno de operador o una regresión del
    runtime. En los dos casos, devolver «todo el negocio» es la respuesta
    equivocada.
    """
    t = tenants_ab["a"]
    w = await _seed(db_session, t)

    with tenant_context(t), customer_context(None):
        out = await GetAppointments().run(GetAppointmentsInput())
        assert out.appointments == []

        with pytest.raises(ToolError):
            await CreateAppointment().run(
                CreateAppointmentInput(
                    service_name="Revisión",
                    starts_at=datetime.now(UTC) + timedelta(days=5),
                    idempotency_key=f"iso35:{uuid.uuid4().hex}",
                )
            )

        with pytest.raises(ToolError):
            await CancelAppointment().run(CancelAppointmentInput(appointment_id=w["appt_mine"]))
