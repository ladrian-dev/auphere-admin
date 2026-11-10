"""Spec 048, T007 — el historial y las comisiones leen Reservas (requisito 4).

Tras pasar a Reservas, las citas de un cliente final viven en dos sitios: las
de ``reservations`` (las nuevas y las importadas) y las de ``appointments`` que
no se importaron. ``client.get_history`` y ``commission.*`` cuentan las dos, y
una cita importada una sola vez: la reserva guarda la cita de origen en su
clave (``appointment:<id>``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.core.tenant_context import customer_context, tenant_context
from nexus_api.db.models import (
    Appointment,
    AppointmentStatus,
    Reservation,
    ReservationService,
    ReservationStaff,
)

from .conftest import all_whitelist, seed_barber, seed_customer

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _appointment(
    tenant_id: uuid.UUID, customer_id: uuid.UUID, barber_id: uuid.UUID, at: datetime
) -> Appointment:
    return Appointment(
        tenant_id=tenant_id,
        customer_id=customer_id,
        barber_id=barber_id,
        service_name="corte",
        service_duration_min=30,
        starts_at=at,
        ends_at=at + timedelta(minutes=30),
        price_cents=10000,
        currency="CLP",
        status=AppointmentStatus.COMPLETED,
        idempotency_key=f"t007-{uuid.uuid4().hex[:12]}",
    )


def _reservation(
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    staff_id: uuid.UUID,
    service_id: uuid.UUID,
    at: datetime,
    *,
    price: int,
    key: str | None,
) -> Reservation:
    return Reservation(
        tenant_id=tenant_id,
        mode="services",
        status="done",
        starts_at=at,
        ends_at=at + timedelta(minutes=30),
        staff_id=staff_id,
        service_id=service_id,
        service_name="Corte",
        price_minor=price,
        currency="CLP",
        customer_id=customer_id,
        origin="agent",
        channel="whatsapp",
        created_by_kind="system",
        idempotency_key=key,
        version=1,
    )


async def test_history_and_commissions_count_both_agendas_once(
    db_session, two_tenants, mcp_registry
) -> None:
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    barber = await seed_barber(db_session, tenant_id=a, name="Luis", commission_pct=0.4)
    staff = ReservationStaff(tenant_id=a, name="Luis")
    service = ReservationService(tenant_id=a, name="Corte", duration_minutes=30)
    db_session.add_all([staff, service])
    await db_session.flush()

    today = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0)
    imported = _appointment(a, cust.id, barber.id, today)
    left = _appointment(a, cust.id, barber.id, today + timedelta(hours=1))
    db_session.add_all([imported, left])
    await db_session.flush()
    copy_of_imported = _reservation(
        a, cust.id, staff.id, service.id, today, price=10000, key=f"appointment:{imported.id}"
    )
    native = _reservation(
        a, cust.id, staff.id, service.id, today + timedelta(hours=2), price=12000, key=None
    )
    db_session.add_all([copy_of_imported, native])
    await db_session.commit()

    with tenant_context(a), customer_context(cust.id):
        history = await mcp_registry.dispatch(
            "client.get_history", {"limit": 10}, whitelist=all_whitelist()
        )
        earnings = await mcp_registry.dispatch(
            "commission.get_barber_earnings",
            {
                "barber_id": str(barber.id),
                "from_date": today.date().isoformat(),
                "to_date": today.date().isoformat(),
            },
            whitelist=all_whitelist(),
        )
        report = await mcp_registry.dispatch(
            "commission.get_daily_report",
            {"on_date": today.date().isoformat()},
            whitelist=all_whitelist(),
        )

    rows = history["result"]["appointments"]
    # La importada, una vez (su reserva); la que se quedó; la nueva.
    assert [r["appointment_id"] for r in rows] == [
        str(native.id),
        str(left.id),
        str(copy_of_imported.id),
    ]
    assert [r["source"] for r in rows] == ["reservas", "appointments", "reservas"]
    assert rows[0]["service_name"] == "Corte" and rows[0]["staff_name"] == "Luis"

    assert earnings["result"]["appointments_count"] == 3
    assert earnings["result"]["gross_revenue_cents"] == 32000
    assert earnings["result"]["commission_cents"] == 12800  # 40 %

    assert report["result"]["appointments_count"] == 3
    assert report["result"]["gross_revenue_cents"] == 32000
    assert report["result"]["total_commission_cents"] == 12800
    (by_barber,) = report["result"]["by_barber"]
    assert by_barber["barber_id"] == str(barber.id)
    assert by_barber["appointments_count"] == 3


async def test_the_history_of_another_person_or_client_never_shows(
    db_session, two_tenants, mcp_registry
) -> None:
    a, b = two_tenants["a"], two_tenants["b"]
    me = await seed_customer(db_session, tenant_id=a, identifier="me")
    other = await seed_customer(db_session, tenant_id=a, identifier="other")
    b_cust = await seed_customer(db_session, tenant_id=b, identifier="me")
    for tenant_id, cust_id in ((a, other.id), (b, b_cust.id)):
        staff = ReservationStaff(tenant_id=tenant_id, name="Luis")
        service = ReservationService(tenant_id=tenant_id, name="Corte", duration_minutes=30)
        db_session.add_all([staff, service])
        await db_session.flush()
        db_session.add(
            _reservation(
                tenant_id, cust_id, staff.id, service.id, datetime.now(UTC), price=1, key=None
            )
        )
    await db_session.commit()

    with tenant_context(a), customer_context(me.id):
        history = await mcp_registry.dispatch(
            "client.get_history", {"limit": 10}, whitelist=all_whitelist()
        )
    assert history["result"]["appointments"] == []
