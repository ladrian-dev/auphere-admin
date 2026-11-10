"""Spec 043 — Reservas de punta a punta, como lo usará un negocio (enmienda del 2026-11-04).

Luis: «que todo este conectado correctamente para que la funcionalidad realmente funcione
como una app que la usaran los clientes». Aquí no se prueba una pieza: el agente reserva
por sus herramientas, el negocio lo ve por su API, el cron recuerda, y el calendario de
cada profesional recibe lo suyo y solo lo suyo.

Con un doble de Google: lo que este fichero **no** prueba es que Google y Composio
contesten como dice su documentación.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from nexus_worker.streams.reservations_cron import process_tenant

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientPushEvent, Customer, Reservation, ReservationSettings
from nexus_api.services.reservations import calendar_sync
from nexus_api.services.reservations.calendar_sync import Busy, Connection
from nexus_api.services.reservations.core import load_ctx
from tests.conftest import future_day, make_reservas
from tests.integration.reservas._calendars import connected
from tests.integration.reservas._worker import outbox, scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")
LUCIA_CAL = "lucia@gmail.com"
MARCOS_CAL = "marcos@gmail.com"


class TwoCalendars:
    """Dos cuentas de Google. Sabe en qué calendario y con qué conexión se hizo cada cosa."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Busy]] = {LUCIA_CAL: {}, MARCOS_CAL: {}}
        self.theirs: dict[str, list[Busy]] = {LUCIA_CAL: [], MARCOS_CAL: []}
        self.owner_of_calendar: dict[str, str] = {}
        self.text_written: list[str] = []
        self._n = 0

    async def link(self, user_id: str, callback_url: str) -> tuple[str, str]:
        raise AssertionError("nobody connects in this test")

    async def account_state(self, connection_id: str) -> str:
        return "ACTIVE"

    async def revoke(self, connection_id: str) -> None:
        return None

    async def list_calendars(self, conn: Connection) -> list[dict[str, Any]]:
        return []

    def _check(self, conn: Connection, calendar_id: str) -> None:
        expected = self.owner_of_calendar[calendar_id]
        assert conn.connection_id == expected, "a calendar only opens with its owner's connection"

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, *, tz: Any
    ) -> list[Busy]:
        self._check(conn, calendar_id)
        return [*self.theirs[calendar_id], *self.events[calendar_id].values()]

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str:
        self._check(conn, calendar_id)
        self._n += 1
        event_id = f"ev{self._n}"
        self.events[calendar_id][event_id] = Busy(start, end, event_id)
        self.text_written.append(marker)
        return event_id

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None:
        self._check(conn, calendar_id)
        self.events[calendar_id].pop(event_id, None)


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


@pytest.fixture
async def salon(db_session: Any, console_world: dict[str, Any]) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    ana = Customer(
        tenant_id=w["tenant_id"], identifier="56911110000", name="Ana Pérez", preferences={}
    )
    bruno = Customer(
        tenant_id=w["tenant_id"], identifier="56922220000", name="Bruno Díaz", preferences={}
    )
    db_session.add_all([ana, bruno])
    await db_session.commit()
    await connected(w["tenant_id"], shop["lucia"], calendar_id=LUCIA_CAL, name="Lucía")
    await connected(w["tenant_id"], shop["marcos"], calendar_id=MARCOS_CAL, name="Marcos")
    google = TwoCalendars()
    google.owner_of_calendar = {
        LUCIA_CAL: f"ca_{shop['lucia']}",
        MARCOS_CAL: f"ca_{shop['marcos']}",
    }
    return {**shop, "ana": ana.id, "bruno": bruno.id, "google": google, "registry": _registry()}


async def _tool(
    salon: dict[str, Any], name: str, args: dict[str, Any], who: str = "ana"
) -> dict[str, Any]:
    with tenant_context(salon["tenant_id"]), customer_context(salon[who]):
        env = await salon["registry"].dispatch(name, args, whitelist=[name])
    return dict(env["result"])


async def _sync(salon: dict[str, Any]) -> dict[str, int]:
    sm = get_sessionmaker()
    tenant_id = salon["tenant_id"]
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        ctx = await load_ctx(session, tenant_id)
        assert ctx is not None
        return await calendar_sync.sync_tenant(session, ctx, salon["google"], now=datetime.now(UTC))


async def _agenda(client: Any, salon: dict[str, Any]) -> list[dict[str, Any]]:
    day = future_day().isoformat()
    r = await client.get(
        f"{BASE}/bookings", headers=salon["headers"](), params={"from": day, "to": day}
    )
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


def _hours(google: TwoCalendars, calendar: str) -> list[int]:
    return sorted(b.starts_at.astimezone(TZ).hour for b in google.events[calendar].values())


async def test_the_agent_books_moves_and_cancels_and_everything_follows(
    client: Any, salon: dict[str, Any]
) -> None:
    day = future_day()
    google: TwoCalendars = salon["google"]

    # 1. El agente ofrece huecos reales y reserva con Lucía.
    found = await _tool(
        salon,
        "reservas.find_slots",
        {
            "date": day.isoformat(),
            "service_id": str(salon["corte"]),
            "staff_id": str(salon["lucia"]),
        },
    )
    assert "10:00" in [s["time"] for s in found["slots"]]
    made = await _tool(
        salon,
        "reservas.create",
        {
            "date": day.isoformat(),
            "time": "10:00",
            "service_id": str(salon["corte"]),
            "staff_id": str(salon["lucia"]),
            "idempotency_key": "ana-corte",
        },
    )
    booking = made["booking"]
    assert booking["staff_name"] == "Lucía"

    # 2. Nace en Reservas: el negocio la ve, con su origen y su historial.
    agenda = await _agenda(client, salon)
    assert [(b["id"], b["origin"], b["staff"]["name"]) for b in agenda] == [
        (booking["id"], "agent", "Lucía")
    ]
    detail = (
        await client.get(f"{BASE}/bookings/{booking['id']}", headers=salon["headers"]())
    ).json()
    assert [e["kind"] for e in detail["events"]] == ["created"]
    assert detail["contact"]["name"] == "Ana Pérez"

    # 3. El negocio se entera.
    async with scoped(salon["tenant_id"]) as s:
        pushed = await s.scalars(sa.select(ClientPushEvent.kind))
        assert "reservas.agent_change" in set(pushed)

    # 4. Nadie puede ocupar esa hora: ni desde la consola ni otro cliente.
    taken = await client.post(
        f"{BASE}/bookings",
        headers=salon["headers"](),
        json={
            "date": day.isoformat(),
            "time": "10:00",
            "staff_id": str(salon["lucia"]),
            "service_id": str(salon["corte"]),
            "contact": {"name": "Otra", "phone": None},
        },
    )
    assert taken.status_code == 409
    assert taken.json()["detail"]["code"] == "slot_taken"
    other = await _tool(
        salon,
        "reservas.create",
        {
            "date": day.isoformat(),
            "time": "10:00",
            "service_id": str(salon["corte"]),
            "staff_id": str(salon["lucia"]),
            "idempotency_key": "bruno-corte",
        },
        who="bruno",
    )
    assert other["refused"] == "slot_taken"

    # 5. Lleva su aviso, una vez, a su hora: el negocio pide confirmación, y esa pregunta ya
    # recuerda la cita (spec 043, §Clarifications). Sin confirmación, ver la prueba siguiente.
    start = datetime.combine(day, time(10, 0), tzinfo=TZ)
    async with scoped(salon["tenant_id"]) as s:
        await process_tenant(s, salon["tenant_id"], start - timedelta(hours=23))
    async with scoped(salon["tenant_id"]) as s:
        await process_tenant(s, salon["tenant_id"], start - timedelta(hours=22))
    kinds = [row.kind for row in await outbox(salon["tenant_id"])]
    assert kinds == ["ask_confirmation"]

    # 6. Llega al calendario de Lucía, sin datos del cliente, y solo al suyo.
    await _sync(salon)
    assert _hours(google, LUCIA_CAL) == [10]
    assert _hours(google, MARCOS_CAL) == []
    assert "Ana" not in str(google.text_written) and "Corte" not in str(google.text_written)

    # 7. Moverla la mueve en Google y libera la hora antigua.
    moved = await _tool(
        salon,
        "reservas.reschedule",
        {"booking_id": booking["id"], "date": day.isoformat(), "time": "12:00"},
    )
    assert moved["booking"]["start"] == "12:00"
    await _sync(salon)
    assert _hours(google, LUCIA_CAL) == [12]
    slots = await _tool(
        salon,
        "reservas.find_slots",
        {
            "date": day.isoformat(),
            "service_id": str(salon["corte"]),
            "staff_id": str(salon["lucia"]),
        },
    )
    times = [s["time"] for s in slots["slots"]]
    assert "10:00" in times and "12:00" not in times

    # 8. Cancelarla la quita de Google y de la agenda viva.
    cancelled = await _tool(salon, "reservas.cancel", {"booking_id": booking["id"]})
    assert cancelled["booking"]["status"] == "cancelled"
    await _sync(salon)
    assert _hours(google, LUCIA_CAL) == []
    agenda = await _agenda(client, salon)
    assert [b["status"] for b in agenda] == ["cancelled"]


async def test_without_asking_for_confirmation_the_agents_booking_gets_its_reminder(
    salon: dict[str, Any],
) -> None:
    async with scoped(salon["tenant_id"]) as s:
        await s.execute(sa.update(ReservationSettings).values(confirm_enabled=False))
    day = future_day()
    made = await _tool(
        salon,
        "reservas.create",
        {
            "date": day.isoformat(),
            "time": "10:00",
            "service_id": str(salon["corte"]),
            "staff_id": str(salon["lucia"]),
            "idempotency_key": "con-recordatorio",
        },
    )
    assert made["booking"]["status"] == "confirmed"
    start = datetime.combine(day, time(10, 0), tzinfo=TZ)
    for hours in (23, 22):
        async with scoped(salon["tenant_id"]) as s:
            await process_tenant(s, salon["tenant_id"], start - timedelta(hours=hours))
    assert [row.kind for row in await outbox(salon["tenant_id"])] == ["reminder"]


async def test_each_professionals_google_only_blocks_their_own_hours(
    client: Any, salon: dict[str, Any]
) -> None:
    """Un «ocupado» de Marcos a las 16:00 no toca a Lucía, ni al agente ni a la consola."""
    day = future_day()
    google: TwoCalendars = salon["google"]
    start = datetime.combine(day, time(16, 0), tzinfo=TZ)
    google.theirs[MARCOS_CAL] = [Busy(start, start + timedelta(hours=1), "dentist")]
    await _sync(salon)

    found = await _tool(
        salon,
        "reservas.find_slots",
        {"date": day.isoformat(), "service_id": str(salon["corte"])},
    )
    at = {s["time"]: {p["name"] for p in s["staff"]} for s in found["slots"]}
    assert at["16:00"] == {"Lucía"}
    assert at["16:30"] == {"Lucía"}
    assert at["17:00"] == {"Lucía", "Marcos"}

    refused = await _tool(
        salon,
        "reservas.create",
        {
            "date": day.isoformat(),
            "time": "16:00",
            "service_id": str(salon["corte"]),
            "staff_id": str(salon["marcos"]),
            "idempotency_key": "ana-marcos",
        },
    )
    assert refused["refused"] == "slot_taken"
    fine = await _tool(
        salon,
        "reservas.create",
        {
            "date": day.isoformat(),
            "time": "16:00",
            "service_id": str(salon["corte"]),
            "idempotency_key": "ana-cualquiera",
        },
    )
    assert fine["booking"]["staff_name"] == "Lucía", "whoever is free"


async def test_the_agent_and_the_console_at_once_never_step_on_each_other(
    client: Any, salon: dict[str, Any]
) -> None:
    day = future_day().isoformat()

    async def by_console(i: int) -> int:
        r = await client.post(
            f"{BASE}/bookings",
            headers=salon["headers"](),
            json={
                "date": day,
                "time": "10:00",
                "staff_id": str(salon["lucia"]),
                "service_id": str(salon["color"]),
                "contact": {"name": f"Cliente {i}", "phone": None},
            },
        )
        return r.status_code

    async def by_agent(i: int) -> dict[str, Any]:
        return await _tool(
            salon,
            "reservas.create",
            {
                "date": day,
                "time": "10:00",
                "staff_id": str(salon["lucia"]),
                "service_id": str(salon["color"]),
                "idempotency_key": f"a{i}",
            },
        )

    results = await asyncio.gather(
        *(by_console(i) for i in range(3)), *(by_agent(i) for i in range(3))
    )

    made = [r for r in results if r == 201 or (isinstance(r, dict) and r.get("booking"))]
    assert len(made) == 1, results
    async with scoped(salon["tenant_id"]) as s:
        live = await s.scalar(
            sa.select(sa.func.count())
            .select_from(Reservation)
            .where(Reservation.status.in_(("pending", "confirmed")))
        )
    assert live == 1


async def test_anyone_gives_each_customer_someone_free_until_there_is_nobody(
    salon: dict[str, Any],
) -> None:
    """Dos profesionales, tres peticiones a la vez para «cualquiera»: dos citas, una con cada
    uno, y la tercera dice que no hay hueco. Sin bloqueos cruzados."""
    day = future_day().isoformat()

    async def ask(i: int) -> dict[str, Any]:
        return await _tool(
            salon,
            "reservas.create",
            {
                "date": day,
                "time": "11:00",
                "service_id": str(salon["corte"]),
                "any_staff": True,
                "idempotency_key": f"any{i}",
            },
        )

    results = await asyncio.wait_for(asyncio.gather(*(ask(i) for i in range(3))), timeout=30)

    names = sorted(r["booking"]["staff_name"] for r in results if r.get("booking"))
    assert names == ["Lucía", "Marcos"]
    assert [r["refused"] for r in results if not r.get("booking")] == ["slot_taken"]


async def test_nothing_of_a_customer_reaches_the_other_professionals_calendar(
    client: Any, salon: dict[str, Any]
) -> None:
    """Dos reservas, cada una a su calendario. Ni el id de una aparece en el de la otra."""
    day = future_day()
    google: TwoCalendars = salon["google"]
    for who, at, key in (("lucia", "10:00", "a"), ("marcos", "11:00", "b")):
        made = await _tool(
            salon,
            "reservas.create",
            {
                "date": day.isoformat(),
                "time": at,
                "service_id": str(salon["corte"]),
                "staff_id": str(salon[who]),
                "idempotency_key": key,
            },
        )
        assert made["booking"]
    await _sync(salon)
    assert _hours(google, LUCIA_CAL) == [10]
    assert _hours(google, MARCOS_CAL) == [11]
    agenda = await _agenda(client, salon)
    assert all(b["clash"] is None for b in agenda), "our own events are never busy"
    assert {uuid.UUID(b["id"]) for b in agenda}
