"""Spec 043 Historia 7 (P3) — el Google Calendar de cada persona del equipo.

Con un doble de la puerta del proveedor (nunca la red):

- el «ocupado» de Lucía entra sin título y no se ofrece;
- una reserva viva de Lucía sale como «Ocupado», sin nombre ni servicio;
- al cancelarla, el evento se borra;
- una reserva que pisa un ocupado sale con ``clash``;
- las herramientas de Google Calendar del agente siguen bloqueadas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Connector, Reservation, TenantConnector
from nexus_api.services.reservations import calendar_sync
from nexus_api.services.reservations.calendar_sync import Busy, Connection
from nexus_api.services.reservations.core import load_ctx
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")


class FakeGoogle:
    def __init__(self, busy: list[Busy]) -> None:
        self._busy = busy
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def list_calendars(self, conn: Connection) -> list[dict[str, str]]:
        return [{"id": "lucia@agenda", "name": "Lucía"}]

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime
    ) -> list[Busy]:
        return list(self._busy)

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str:
        self.created.append({"calendar": calendar_id, "start": start, "end": end, "marker": marker})
        return f"ev-{len(self.created)}"

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None:
        self.deleted.append(event_id)


@pytest.fixture(autouse=True)
def _google(monkeypatch: pytest.MonkeyPatch) -> None:
    """La API lista los calendarios de la cuenta con la puerta del proveedor;
    aquí, siempre el doble (nunca la red)."""
    monkeypatch.setattr(calendar_sync, "default_gateway", lambda: FakeGoogle([]))


async def _connect_google(db_session, tenant_id: uuid.UUID) -> None:
    connector = (
        await db_session.execute(
            sa.select(Connector).where(Connector.mcp_server_ref == "composio:googlecalendar")
        )
    ).scalar_one_or_none()
    if connector is None:
        connector = Connector(
            slug="googlecalendar",
            display_name="Google Calendar",
            vendor="Google",
            category="calendar",
            auth_kind="oauth_composio",
            mcp_server_ref="composio:googlecalendar",
        )
        db_session.add(connector)
        await db_session.flush()
    db_session.add(
        TenantConnector(
            tenant_id=tenant_id,
            connector_id=connector.id,
            status="connected",
            credentials_ref={"composio_connection_id": "ca_test"},
        )
    )
    await db_session.commit()


async def test_busy_in_and_ocupado_out(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _connect_google(db_session, w["tenant_id"])
    h = shop["headers"]
    day = future_day()
    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar", headers=h(), json={"calendar_id": "lucia@agenda"}
    )
    assert put.status_code == 200, put.text
    assert put.json()["calendar"]["status"] == "connected"

    booking = await client.post(
        f"{BASE}/bookings",
        headers=h(),
        json={
            "date": day.isoformat(),
            "time": "10:00",
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Ana Pérez", "phone": "+56911112222"},
        },
    )
    assert booking.status_code == 201, booking.text
    busy_start = datetime.combine(day, time(16, 0), tzinfo=TZ)
    fake = FakeGoogle([Busy(busy_start, busy_start + timedelta(hours=1))])

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        ctx = await load_ctx(session, w["tenant_id"])
        assert ctx is not None
        conn = await calendar_sync.connection_of(session, w["tenant_id"])
        assert conn == Connection(user_id=conn.user_id, connection_id="ca_test")
        stats = await calendar_sync.sync_tenant(session, ctx, fake, conn, now=datetime.now(UTC))
    assert stats == {"busy": 1, "written": 1, "deleted": 0}
    out = fake.created[0]
    assert out["marker"].startswith(calendar_sync.MARK)
    assert "Ana" not in str(out) and "Corte" not in str(out)  # hacia fuera, solo «ocupado»

    slots = await client.get(
        f"{BASE}/slots",
        headers=h(),
        params={
            "date": day.isoformat(),
            "service_id": str(shop["corte"]),
            "staff_id": str(shop["lucia"]),
        },
    )
    times = [s["time"] for s in slots.json()["slots"]]
    assert "16:00" not in times and "16:30" not in times and "17:00" in times

    cancel = await client.post(
        f"{BASE}/bookings/{booking.json()['id']}/cancel",
        headers={**h(), "If-Match": str(booking.json()["version"])},
        json={"notify": False},
    )
    assert cancel.status_code == 200
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        ctx = await load_ctx(session, w["tenant_id"])
        assert ctx is not None
        await calendar_sync.sync_tenant(session, ctx, fake, conn, now=datetime.now(UTC))
    assert fake.deleted == ["ev-1"]


async def test_a_booking_on_top_of_busy_shows_a_clash(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    day = future_day()
    starts = datetime.combine(day, time(11, 0), tzinfo=TZ)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        r = Reservation(
            tenant_id=w["tenant_id"],
            mode="services",
            status="confirmed",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            staff_id=shop["lucia"],
            service_id=shop["corte"],
            service_name="Corte",
            origin="person",
            channel="phone",
            created_by_kind="person",
            contact_name="Ana",
        )
        session.add(r)
        await session.flush()
        await session.execute(
            sa.text(
                "INSERT INTO reservation_busy (tenant_id, staff_id, starts_at, ends_at) "
                "VALUES (:t, :s, :a, :b)"
            ),
            {
                "t": w["tenant_id"],
                "s": shop["lucia"],
                "a": starts - timedelta(minutes=15),
                "b": starts + timedelta(minutes=45),
            },
        )
        rid = r.id
    detail = (await client.get(f"{BASE}/bookings/{rid}", headers=shop["headers"]())).json()
    assert detail["clash"]["source"] == "google"
    assert detail["clash"]["local"] == {"start": "10:45", "end": "11:45"}
    summary = (await client.get(f"{BASE}/summary", headers=shop["headers"]())).json()
    assert summary["clashes"] == 1


async def test_agent_google_calendar_writes_stay_blocked() -> None:
    """R10.5: la sincronización es del sistema; para el agente, escribir en
    Google Calendar sigue naciendo bloqueado (spec 023)."""
    from nexus_api.services.connectors.composio_client import ComposioTool
    from nexus_api.services.connectors.service import _default_mode_for, _derive_annotations

    tool = ComposioTool(slug="GOOGLECALENDAR_CREATE_EVENT", description="", input_schema={})
    notes = _derive_annotations(tool)
    assert notes["destructive"] is True
    mode = _default_mode_for(
        read_only=notes["read_only"],
        destructive=notes["destructive"],
        auto_enable_destructive=False,
    )
    assert mode == "blocked"


async def test_the_calendar_cron_only_calls_out_when_there_is_something_to_sync(
    client, db_session, console_world
) -> None:
    """``reservation-calendar-cron``: sin conexión o sin personas asociadas no
    construye la puerta; sin el proveedor de verdad no sincroniza; con todo,
    una pasada de ``sync_tenant``."""
    from nexus_worker.streams import reservation_calendar_cron as cron

    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    fake = FakeGoogle([])
    built: list[str] = []

    def factory() -> FakeGoogle:
        built.append("gateway")
        return fake

    async def one_pass(process: Any) -> object:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
            return await process(session, w["tenant_id"], datetime.now(UTC))

    process = cron.make_process(factory)
    assert await one_pass(process) is None  # sin conexión
    await _connect_google(db_session, w["tenant_id"])
    assert await one_pass(process) is None  # sin nadie asociado
    assert built == []

    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": "lucia@agenda"},
    )
    assert put.status_code == 200, put.text
    assert await one_pass(cron.make_process(lambda: None)) is None  # sin proveedor
    assert await one_pass(process) == {"busy": 0, "written": 0, "deleted": 0}
    assert await one_pass(process) == {"busy": 0, "written": 0, "deleted": 0}
    assert built == ["gateway"]  # una sola vez


class _Result:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.error = None


class _Client:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    async def execute_tool(self, **_: Any) -> _Result:
        return _Result(self._data)


async def test_a_description_cannot_pass_for_one_of_ours() -> None:
    """/cso (apéndice): lo nuestro se reconoce por el id del evento que guardó
    la reserva, no por un texto que cualquiera puede escribir en una
    invitación. Un evento con la marca en la descripción sigue siendo ocupado."""
    start = datetime(2026, 10, 24, 16, 0, tzinfo=TZ)
    gateway = calendar_sync.ComposioGoogleCalendar(
        _Client(
            {
                "items": [
                    {
                        "id": "spoof",
                        "description": f"{calendar_sync.MARK}00000000",
                        "start": {"dateTime": start.isoformat()},
                        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
                    }
                ]
            }
        )
    )
    busy = await gateway.busy(Connection("tenant_x", "ca"), "cal", start, start + timedelta(days=1))
    assert [b.event_id for b in busy] == ["spoof"]


async def test_our_own_ocupado_does_not_come_back_as_busy(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _connect_google(db_session, w["tenant_id"])
    h = shop["headers"]
    day = future_day()
    await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar", headers=h(), json={"calendar_id": "lucia@agenda"}
    )
    made = await client.post(
        f"{BASE}/bookings",
        headers=h(),
        json={
            "date": day.isoformat(),
            "time": "10:00",
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Ana", "phone": None},
        },
    )
    assert made.status_code == 201, made.text
    fake = FakeGoogle([])
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        ctx = await load_ctx(session, w["tenant_id"])
        assert ctx is not None
        conn = await calendar_sync.connection_of(session, w["tenant_id"])
        assert conn is not None
        await calendar_sync.sync_tenant(session, ctx, fake, conn, now=datetime.now(UTC))
    ours = fake.created[0]
    # La pasada siguiente: Google devuelve nuestro «Ocupado» (ev-1) y uno ajeno.
    fake._busy = [
        Busy(ours["start"], ours["end"], "ev-1"),
        Busy(ours["start"] + timedelta(hours=5), ours["end"] + timedelta(hours=5), "other"),
    ]
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        ctx = await load_ctx(session, w["tenant_id"])
        assert ctx is not None
        stats = await calendar_sync.sync_tenant(session, ctx, fake, conn, now=datetime.now(UTC))
    assert stats["busy"] == 1


async def test_only_a_calendar_of_the_connected_account_can_be_chosen(
    client, db_session, console_world
) -> None:
    """/cso (apéndice): el calendario de una persona tiene que ser de la cuenta
    que el cliente conectó; un id cualquiera no se guarda."""
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _connect_google(db_session, w["tenant_id"])
    url = f"{BASE}/staff/{shop['lucia']}/calendar"
    bad = await client.put(url, headers=shop["headers"](), json={"calendar_id": "otro@ajeno"})
    assert bad.status_code == 422, bad.text
    assert bad.json()["detail"]["code"] == "unknown_calendar"
    good = await client.put(url, headers=shop["headers"](), json={"calendar_id": "lucia@agenda"})
    assert good.status_code == 200, good.text
    assert good.json()["calendar"]["calendar_name"] == "Lucía"
