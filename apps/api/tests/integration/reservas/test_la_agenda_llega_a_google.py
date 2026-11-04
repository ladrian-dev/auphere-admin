"""Bug ``la-agenda-no-llega-a-google``: R10 de la spec 043, punto por punto.

Con un doble de la puerta o del cliente del proveedor: nunca la red. Lo que aquí
se comprueba de los nombres de Composio sale de su documentación pública, no de
una llamada de verdad a Google.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
import structlog

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Connector, Reservation, TenantConnector
from nexus_api.services.connectors.composio_client import (
    ComposioAuthExpired,
    ComposioNotFound,
    LiveComposioClient,
)
from nexus_api.services.reservations import calendar_sync
from nexus_api.services.reservations.calendar_sync import (
    Busy,
    ComposioGoogleCalendar,
    Connection,
    GoogleCalendarError,
)
from nexus_api.services.reservations.core import load_ctx
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")
LUCIA_CAL = "lucia@agenda"
MARCOS_CAL = "marcos@agenda"
CONN = Connection("tenant_x", "ca")


class FakeGoogle:
    """La puerta, con lo que escribe apuntado y los fallos que le pida la prueba."""

    def __init__(self, busy: list[Busy] | None = None) -> None:
        self.intervals = list(busy or [])
        self.created: list[dict[str, Any]] = []
        self.deleted: list[tuple[str, str]] = []
        self.reads = 0
        self.read_error: Exception | None = None
        self.create_errors: list[Exception] = []
        self.delete_errors: list[Exception] = []

    async def list_calendars(self, conn: Connection) -> list[dict[str, str]]:
        return [{"id": LUCIA_CAL, "name": "Lucía"}, {"id": MARCOS_CAL, "name": "Marcos"}]

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, *, tz: Any
    ) -> list[Busy]:
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return list(self.intervals)

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str:
        if self.create_errors:
            raise self.create_errors.pop(0)
        self.created.append({"calendar": calendar_id, "start": start, "end": end, "marker": marker})
        return f"ev-{len(self.created)}"

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None:
        if self.delete_errors:
            raise self.delete_errors.pop(0)
        self.deleted.append((calendar_id, event_id))


@pytest.fixture(autouse=True)
def _google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(calendar_sync, "default_gateway", lambda: FakeGoogle())


async def _connect(db_session: Any, tenant_id: uuid.UUID, status: str = "connected") -> None:
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
            status=status,
            credentials_ref={"composio_connection_id": "ca_test"},
        )
    )
    await db_session.commit()


async def _world(client: Any, db_session: Any, w: dict[str, Any]) -> dict[str, Any]:
    """Un negocio conectado, con Lucía asociada a su calendario."""
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _connect(db_session, w["tenant_id"])
    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": LUCIA_CAL},
    )
    assert put.status_code == 200, put.text
    return shop


async def _book(client: Any, shop: dict[str, Any], at: str = "10:00") -> dict[str, Any]:
    made = await client.post(
        f"{BASE}/bookings",
        headers=shop["headers"](),
        json={
            "date": future_day().isoformat(),
            "time": at,
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Ana Pérez", "phone": None},
        },
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


async def _move(
    client: Any, shop: dict[str, Any], booking: dict[str, Any], **body: Any
) -> dict[str, Any]:
    moved = await client.post(
        f"{BASE}/bookings/{booking['id']}/move",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"notify": False, **body},
    )
    assert moved.status_code == 200, moved.text
    out: dict[str, Any] = moved.json()
    return out


async def _pass(tenant_id: uuid.UUID, fake: Any, *, now: datetime | None = None) -> dict[str, int]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        ctx = await load_ctx(session, tenant_id)
        assert ctx is not None
        conn = await calendar_sync.connection_of(session, tenant_id)
        assert conn is not None
        return await calendar_sync.sync_tenant(
            session, ctx, fake, conn, now=now or datetime.now(UTC)
        )


async def _rows(tenant_id: uuid.UUID, sql: str, **params: Any) -> list[Any]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return list((await session.execute(sa.text(sql), params)).all())


async def _stored_event(tenant_id: uuid.UUID, booking_id: str) -> str | None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await session.scalar(
            sa.select(Reservation.external_event_id).where(Reservation.id == uuid.UUID(booking_id))
        )


async def _staff_calendar(client: Any, shop: dict[str, Any]) -> dict[str, Any]:
    items = (await client.get(f"{BASE}/staff", headers=shop["headers"]())).json()["items"]
    found: dict[str, Any] = next(s for s in items if s["id"] == str(shop["lucia"]))["calendar"]
    return found


class _Provider:
    """El cliente del proveedor: apunta cada llamada y responde lo que se le pida."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute_tool(
        self, *, tool_slug: str, user_id: str, connection_id: str, arguments: dict[str, Any]
    ) -> Any:
        self.calls.append((tool_slug, arguments))
        answer = self.answers.pop(0) if self.answers else {"items": []}
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, str):
            return SimpleNamespace(data={}, error=answer)
        return SimpleNamespace(data=answer, error=None)


WINDOW = (datetime(2026, 11, 5, 12, 0, tzinfo=UTC), datetime(2026, 11, 6, 12, 0, tzinfo=UTC))


# ── 1. El nombre y los argumentos de cada acción ────────────────────────────


async def test_the_listing_uses_the_slug_and_the_arguments_of_the_provider() -> None:
    """``GOOGLECALENDAR_LIST_EVENTS`` no existe en el catálogo público de Composio:
    es ``GOOGLECALENDAR_EVENTS_LIST``, con los argumentos de Google en camelCase."""
    provider = _Provider({"items": []})
    await ComposioGoogleCalendar(provider).busy(CONN, "cal", *WINDOW, tz=TZ)
    slug, args = provider.calls[0]
    assert slug == "GOOGLECALENDAR_EVENTS_LIST"
    assert args["calendarId"] == "cal"
    assert args["singleEvents"] is True
    # RFC 3339 con zona obligatoria, y sin un «+» que pueda perderse por el camino.
    assert args["timeMin"] == "2026-11-05T12:00:00Z"
    assert args["timeMax"] == "2026-11-06T12:00:00Z"


async def test_creating_speaks_the_arguments_of_the_provider() -> None:
    """``send_updates`` es un texto («all», «externalOnly», «none») y
    ``start_datetime`` va sin desfase, con ``timezone`` aparte."""
    provider = _Provider({"id": "ev"})
    start = datetime(2026, 11, 5, 10, 0, tzinfo=TZ)
    got = await ComposioGoogleCalendar(provider).create_busy(
        CONN, "cal", start, start + timedelta(minutes=90), "auphere:reserva:1"
    )
    assert got == "ev"
    slug, args = provider.calls[0]
    assert slug == "GOOGLECALENDAR_CREATE_EVENT"
    assert args == {
        "calendar_id": "cal",
        "summary": "Ocupado",
        "description": "auphere:reserva:1",
        "start_datetime": "2026-11-05T13:00:00",
        "timezone": "UTC",
        "event_duration_hour": 1,
        "event_duration_minutes": 30,
        "transparency": "opaque",
        "send_updates": "none",
    }


async def test_deleting_speaks_the_arguments_of_the_provider() -> None:
    provider = _Provider({})
    await ComposioGoogleCalendar(provider).delete_busy(CONN, "cal", "ev")
    assert provider.calls == [
        ("GOOGLECALENDAR_DELETE_EVENT", {"calendar_id": "cal", "event_id": "ev"})
    ]


async def test_an_answer_that_is_not_a_listing_is_not_an_empty_calendar() -> None:
    """Leerlo como vacío borraría el ocupado de verdad, sin que nadie lo sepa."""
    with pytest.raises(GoogleCalendarError):
        await ComposioGoogleCalendar(_Provider({"something": "else"})).busy(
            CONN, "cal", *WINDOW, tz=TZ
        )


async def test_an_empty_calendar_is_an_empty_calendar() -> None:
    """Google puede omitir ``items``: el sobre de la respuesta dice que es un listado."""
    gateway = ComposioGoogleCalendar(_Provider({"kind": "calendar#events", "timeZone": "UTC"}))
    assert await gateway.busy(CONN, "cal", *WINDOW, tz=TZ) == []


async def test_a_read_failure_does_not_skip_the_writes(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    keeps = await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)
    cancelled = await client.post(
        f"{BASE}/bookings/{keeps['id']}/cancel",
        headers={**shop["headers"](), "If-Match": str(keeps["version"])},
        json={"notify": False},
    )
    assert cancelled.status_code == 200, cancelled.text
    await _book(client, shop, "12:00")

    fake.read_error = RuntimeError("provider down")
    stats = await _pass(w["tenant_id"], fake)

    assert stats["written"] == 1
    assert stats["deleted"] == 1
    assert fake.deleted == [(LUCIA_CAL, "ev-1")]
    assert len(fake.created) == 2


async def test_a_write_failure_does_not_skip_the_read(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    await _book(client, shop)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    fake = FakeGoogle([Busy(start, start + timedelta(hours=1))])
    fake.create_errors = [RuntimeError("provider down")]

    stats = await _pass(w["tenant_id"], fake)

    assert stats["busy"] == 1
    assert (await _rows(w["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 1


# ── 2. Mover la reserva mueve el evento ─────────────────────────────────────


async def test_moving_a_booking_moves_its_event(client, db_session, console_world) -> None:
    """R10.3: de 10:00 a 16:00, Google deja de bloquear las 10:00 y bloquea las 16:00."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    booking = await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)
    assert fake.created[0]["start"].astimezone(TZ).hour == 10

    await _move(client, shop, booking, time="16:00")
    await _pass(w["tenant_id"], fake)

    assert fake.deleted == [(LUCIA_CAL, "ev-1")]
    assert len(fake.created) == 2
    assert fake.created[1]["start"].astimezone(TZ).hour == 16
    assert fake.created[1]["calendar"] == LUCIA_CAL

    await _pass(w["tenant_id"], fake)
    assert len(fake.created) == 2  # y no vuelve a escribirlo
    assert len(fake.deleted) == 1


async def test_moving_to_another_person_deletes_it_from_where_it_lives(
    client, db_session, console_world
) -> None:
    """El evento sigue en el calendario de Lucía: no vale buscarlo en el de Marcos."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    put = await client.put(
        f"{BASE}/staff/{shop['marcos']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": MARCOS_CAL},
    )
    assert put.status_code == 200, put.text
    booking = await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)

    await _move(client, shop, booking, staff_id=str(shop["marcos"]))
    await _pass(w["tenant_id"], fake)

    assert fake.deleted == [(LUCIA_CAL, "ev-1")]
    assert fake.created[1]["calendar"] == MARCOS_CAL


async def test_a_move_whose_delete_fails_does_not_duplicate_nor_block_itself(
    client, db_session, console_world
) -> None:
    """Hasta borrar el viejo no se escribe el nuevo, y mientras tanto el viejo sigue
    siendo nuestro: no entra como un ocupado ajeno."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    booking = await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)
    old = fake.created[0]
    await _move(client, shop, booking, time="16:00")

    fake.delete_errors = [RuntimeError("provider down")]
    fake.intervals = [Busy(old["start"], old["end"], "ev-1")]
    stats = await _pass(w["tenant_id"], fake)
    assert stats == {"busy": 0, "written": 0, "deleted": 0}
    assert len(fake.created) == 1

    fake.intervals = []
    await _pass(w["tenant_id"], fake)
    assert fake.deleted == [(LUCIA_CAL, "ev-1")]
    assert len(fake.created) == 2


async def test_a_move_that_changes_nothing_does_not_touch_the_event(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    booking = await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)
    await _move(client, shop, booking, note="Trae el pelo limpio")
    await _pass(w["tenant_id"], fake)
    assert fake.deleted == []
    assert len(fake.created) == 1


async def test_another_calendar_takes_the_events_out_of_the_old_one(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)

    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": MARCOS_CAL},
    )
    assert put.status_code == 200, put.text
    await _pass(w["tenant_id"], fake)

    assert fake.deleted == [(LUCIA_CAL, "ev-1")]
    assert fake.created[1]["calendar"] == MARCOS_CAL


async def test_saving_the_same_calendar_again_leaves_the_events_alone(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)
    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": LUCIA_CAL},
    )
    assert put.status_code == 200, put.text
    await _pass(w["tenant_id"], fake)
    assert fake.deleted == []
    assert len(fake.created) == 1


async def test_disconnecting_takes_the_events_out_and_writes_no_more(
    client, db_session, console_world
) -> None:
    """Sin nadie asociado el cron sigue teniendo trabajo: lo que dejó en el calendario
    no se puede quedar ahí, bloqueando a una persona que ya no se sincroniza."""
    from nexus_worker.streams import reservation_calendar_cron as cron

    w = console_world["a"]
    shop = await _world(client, db_session, w)
    booking = await _book(client, shop)
    fake = FakeGoogle()
    await _pass(w["tenant_id"], fake)

    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": None},
    )
    assert put.status_code == 200, put.text
    assert put.json()["calendar"]["status"] == "none"

    sm = get_sessionmaker()
    process = cron.make_process(lambda: fake)
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        await process(session, w["tenant_id"], datetime.now(UTC))

    assert fake.deleted == [(LUCIA_CAL, "ev-1")]
    assert len(fake.created) == 1
    assert await _stored_event(w["tenant_id"], booking["id"]) is None


# ── 3. Sin duplicados ───────────────────────────────────────────────────────


async def test_an_event_deleted_by_hand_counts_as_deleted() -> None:
    """Quien borró el «Ocupado» a mano ya hizo el trabajo: 404 o 410 no es un fallo."""
    for answer in ("404 Client Error: Not Found for url", "410 Resource has been deleted"):
        await ComposioGoogleCalendar(_Provider(answer)).delete_busy(CONN, "cal", "ev")


async def test_an_unknown_connection_is_not_an_event_deleted_by_hand() -> None:
    """``ComposioNotFound`` es que Composio no conoce la conexión. Darlo por borrado perdería
    el id en cada pasada, y el evento se quedaría en Google bloqueando para siempre."""
    gateway = ComposioGoogleCalendar(_Provider(ComposioNotFound("no connection")))
    with pytest.raises(GoogleCalendarError) as caught:
        await gateway.delete_busy(CONN, "cal", "ev")
    assert caught.value.kind == "auth"


async def test_any_other_delete_failure_is_a_failure() -> None:
    with pytest.raises(GoogleCalendarError):
        await ComposioGoogleCalendar(_Provider("503 backend error")).delete_busy(CONN, "cal", "ev")


async def test_what_was_written_survives_the_pass_that_breaks_afterwards(
    client, db_session, console_world
) -> None:
    """La causa de los «Ocupado» repetidos cada dos minutos: Google ya los tiene, y la
    transacción de toda la pasada se llevaba los ids al deshacerse."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    await _book(client, shop)
    fake = FakeGoogle()

    class Boom(Exception):
        pass

    sm = get_sessionmaker()
    with pytest.raises(Boom):
        async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
            ctx = await load_ctx(session, w["tenant_id"])
            assert ctx is not None
            conn = await calendar_sync.connection_of(session, w["tenant_id"])
            assert conn is not None
            await calendar_sync.sync_tenant(session, ctx, fake, conn, now=datetime.now(UTC))
            raise Boom

    await _pass(w["tenant_id"], fake)
    assert len(fake.created) == 1


async def test_a_failing_write_does_not_take_the_others_with_it(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    first = await _book(client, shop, "10:00")
    second = await _book(client, shop, "12:00")
    fake = FakeGoogle()
    fake.create_errors = [RuntimeError("provider down")]

    stats = await _pass(w["tenant_id"], fake)
    assert stats["written"] == 1
    assert len(fake.created) == 1

    await _pass(w["tenant_id"], fake)
    assert len(fake.created) == 2
    assert await _stored_event(w["tenant_id"], first["id"]) is not None
    assert await _stored_event(w["tenant_id"], second["id"]) is not None


async def test_an_answer_without_an_id_does_not_write_it_again(
    client, db_session, console_world
) -> None:
    """El evento existe en Google y no sabemos cómo se llama: volver a crearlo sería
    un «Ocupado» más cada dos minutos."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    await _book(client, shop)
    provider = _Provider({"event": {"summary": "Ocupado"}})
    gateway = ComposioGoogleCalendar(provider)

    await _pass(w["tenant_id"], gateway)
    await _pass(w["tenant_id"], gateway)

    created = [c for c in provider.calls if c[0] == "GOOGLECALENDAR_CREATE_EVENT"]
    assert len(created) == 1


# ── 4. Los fallos se dicen ──────────────────────────────────────────────────


async def test_a_connection_that_needs_reauth_stops_blocking_and_says_so(
    client, db_session, console_world
) -> None:
    from nexus_worker.streams import reservation_calendar_cron as cron

    w = console_world["a"]
    shop = await _world(client, db_session, w)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    fake = FakeGoogle([Busy(start, start + timedelta(hours=1))])
    await _pass(w["tenant_id"], fake)
    assert (await _rows(w["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 1

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        await session.execute(sa.update(TenantConnector).values(status="needs_reauth"))

    process = cron.make_process(lambda: fake)
    with structlog.testing.capture_logs() as logs:
        async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
            assert await process(session, w["tenant_id"], datetime.now(UTC)) is None
        async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
            assert await process(session, w["tenant_id"], datetime.now(UTC)) is None

    assert (await _rows(w["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 0
    lost = [e for e in logs if e["event"] == "reservation_calendar.connection_unhealthy"]
    assert len(lost) == 1  # una vez, no cada dos minutos
    assert lost[0]["tenant_id"] == str(w["tenant_id"])
    assert lost[0]["dropped"] == 1

    calendar = await _staff_calendar(client, shop)
    assert calendar["status"] == "needs_reauth"
    assert calendar["last_error"] == "connection"
    assert calendar["calendar_name"] == "Lucía"

    account = (await client.get(f"{BASE}/calendar", headers=shop["headers"]())).json()
    assert account["connection"] == "needs_reauth"
    assert account["connected"] is False


async def test_a_reconnected_calendar_is_healthy_again(client, db_session, console_world) -> None:
    from nexus_worker.streams import reservation_calendar_cron as cron

    w = console_world["a"]
    shop = await _world(client, db_session, w)
    fake = FakeGoogle()
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        await session.execute(sa.update(TenantConnector).values(status="needs_reauth"))
    process = cron.make_process(lambda: fake)
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        await process(session, w["tenant_id"], datetime.now(UTC))
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        await session.execute(sa.update(TenantConnector).values(status="connected"))

    # La pantalla no espera al cron para dejar de pedir que se vuelva a conectar.
    assert (await _staff_calendar(client, shop))["status"] == "connected"

    await _pass(w["tenant_id"], fake)

    calendar = await _staff_calendar(client, shop)
    assert calendar["status"] == "connected"
    assert calendar["last_error"] is None
    assert calendar["last_sync_at"] is not None


async def test_a_read_that_fails_keeps_the_busy_for_a_while_and_then_drops_it(
    client, db_session, console_world
) -> None:
    """Un corte breve no libera huecos de golpe; uno largo no bloquea con datos viejos."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    fake = FakeGoogle([Busy(start, start + timedelta(hours=1))])
    t0 = datetime.now(UTC)
    await _pass(w["tenant_id"], fake, now=t0)
    synced = (await _staff_calendar(client, shop))["last_sync_at"]

    fake.read_error = RuntimeError("provider down")
    await _pass(w["tenant_id"], fake, now=t0 + timedelta(minutes=10))
    assert (await _rows(w["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 1
    calendar = await _staff_calendar(client, shop)
    assert calendar["status"] == "error"
    assert calendar["last_error"] == "read"
    assert calendar["last_sync_at"] == synced

    await _pass(
        w["tenant_id"],
        fake,
        now=t0 + calendar_sync.BUSY_STALE_AFTER + timedelta(minutes=1),
    )
    assert (await _rows(w["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 0


async def test_a_refused_read_drops_the_busy_at_once(client, db_session, console_world) -> None:
    """Sin permiso no va a arreglarse solo: esperar solo bloquea huecos con datos viejos."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    fake = FakeGoogle([Busy(start, start + timedelta(hours=1))])
    t0 = datetime.now(UTC)
    await _pass(w["tenant_id"], fake, now=t0)

    fake.read_error = GoogleCalendarError("401 invalid_grant", kind="auth")
    await _pass(w["tenant_id"], fake, now=t0 + timedelta(minutes=2))

    assert (await _rows(w["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 0
    calendar = await _staff_calendar(client, shop)
    assert calendar["status"] == "needs_reauth"
    assert calendar["last_error"] == "auth"


async def test_the_text_of_the_provider_reaches_neither_the_logs_nor_the_screen(
    client, db_session, console_world
) -> None:
    """Puede traer un token o el título de una cita de otra persona."""
    secret = "token=abc123 Reunión con Ana Pérez"
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    await _book(client, shop)
    fake = FakeGoogle()
    fake.read_error = RuntimeError(secret)
    fake.create_errors = [RuntimeError(secret)]

    with structlog.testing.capture_logs() as logs:
        await _pass(w["tenant_id"], fake)

    read = next(e for e in logs if e["event"] == "reservation_calendar.read_failed")
    write = next(e for e in logs if e["event"] == "reservation_calendar.write_failed")
    for entry in (read, write):
        assert entry["tenant_id"] == str(w["tenant_id"])
        assert entry["staff_id"] == str(shop["lucia"])
        assert entry["error_type"] == "RuntimeError"
    assert write["operation"] == "create"
    assert "abc123" not in str(logs) and "Ana" not in str(logs)

    calendar = await _staff_calendar(client, shop)
    assert calendar["status"] == "error"
    assert calendar["last_error"] in {"read", "write"}
    assert "abc123" not in str(calendar)
    stored = await _rows(w["tenant_id"], "SELECT last_error FROM reservation_staff_calendars")
    assert "abc123" not in str(stored)


async def test_a_provider_that_is_down_does_not_look_like_an_account_without_calendars(
    client, db_session, console_world, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)

    class Down(FakeGoogle):
        async def list_calendars(self, conn: Connection) -> list[dict[str, str]]:
            raise RuntimeError("provider down")

    monkeypatch.setattr(calendar_sync, "default_gateway", lambda: Down())
    account = (await client.get(f"{BASE}/calendar", headers=shop["headers"]())).json()
    assert account["connected"] is True
    assert account["connection"] == "connected"
    assert account["unavailable"] is True
    assert account["calendars"] == []


async def test_an_account_that_never_connected_says_so(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    account = (await client.get(f"{BASE}/calendar", headers=shop["headers"]())).json()
    assert account == {
        "provider": "google",
        "connected": False,
        "connection": "none",
        "unavailable": False,
        "calendars": [],
    }


async def test_a_client_only_touches_what_is_its_own(client, db_session, console_world) -> None:
    """Garantía 1 (RLS): la pasada escribe en una sesión aparte y varias sentencias no
    filtran por cliente: lo hace la RLS. Ni la conexión perdida de A toca el ocupado de
    B, ni la pasada de A sus reservas, ni A ve la conexión de B."""
    from nexus_worker.streams import reservation_calendar_cron as cron

    a, b = console_world["a"], console_world["b"]
    shop_a = await make_reservas(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    shop_b = await _world(client, db_session, b)
    booked = await _book(client, shop_b)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    fake_b = FakeGoogle([Busy(start, start + timedelta(hours=1))])
    await _pass(b["tenant_id"], fake_b)
    stored = await _stored_event(b["tenant_id"], booked["id"])

    assert (await client.get(f"{BASE}/calendar", headers=shop_a["headers"]())).json()[
        "connection"
    ] == "none"

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, a["tenant_id"]):
        await session.execute(
            sa.text(
                "INSERT INTO reservation_staff_calendars (tenant_id, staff_id, calendar_id) "
                "VALUES (:t, :s, 'a@agenda')"
            ),
            {"t": a["tenant_id"], "s": shop_a["lucia"]},
        )
    fake_a = FakeGoogle()
    process = cron.make_process(lambda: fake_a)
    async with sm() as session, tenant_scoped_session(session, a["tenant_id"]):
        await process(session, a["tenant_id"], datetime.now(UTC))

    assert fake_a.created == [] and fake_a.deleted == []
    assert (await _rows(b["tenant_id"], "SELECT count(*) FROM reservation_busy"))[0][0] == 1
    assert await _stored_event(b["tenant_id"], booked["id"]) == stored
    assert (await _staff_calendar(client, shop_b))["last_error"] is None


# ── 5. Todo el día, páginas y el bucle de eventos ───────────────────────────


async def test_an_all_day_event_blocks_the_day_in_the_zone_of_the_business() -> None:
    """El fin de Google es exclusivo: 5 al 6 es el día 5 entero."""
    provider = _Provider(
        {"items": [{"id": "off", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}}]}
    )
    got = await ComposioGoogleCalendar(provider).busy(CONN, "cal", *WINDOW, tz=TZ)
    assert got == [
        Busy(
            datetime(2026, 11, 5, 0, 0, tzinfo=TZ),
            datetime(2026, 11, 6, 0, 0, tzinfo=TZ),
            "off",
        )
    ]


async def test_an_all_day_event_marked_free_blocks_nothing() -> None:
    """Un cumpleaños o un festivo del calendario: Google los crea como «disponible»."""
    provider = _Provider(
        {
            "items": [
                {
                    "id": "birthday",
                    "transparency": "transparent",
                    "start": {"date": "2026-11-05"},
                    "end": {"date": "2026-11-06"},
                }
            ]
        }
    )
    assert await ComposioGoogleCalendar(provider).busy(CONN, "cal", *WINDOW, tz=TZ) == []


async def test_an_all_day_block_takes_the_slots_of_the_day(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    day = future_day()
    next_day = day + timedelta(days=1)
    fake = FakeGoogle(
        [
            Busy(
                datetime.combine(day, time(0, 0), tzinfo=TZ),
                datetime.combine(next_day, time(0, 0), tzinfo=TZ),
                "off",
            )
        ]
    )
    await _pass(w["tenant_id"], fake)
    params = {"service_id": str(shop["corte"]), "staff_id": str(shop["lucia"])}
    blocked = await client.get(
        f"{BASE}/slots", headers=shop["headers"](), params={"date": day.isoformat(), **params}
    )
    free = await client.get(
        f"{BASE}/slots", headers=shop["headers"](), params={"date": next_day.isoformat(), **params}
    )
    assert blocked.json()["slots"] == []
    assert free.json()["slots"] != []


async def test_an_event_of_no_length_does_not_break_the_pass(
    client, db_session, console_world
) -> None:
    """``reservation_busy`` exige un fin posterior al inicio, y Google permite estos."""
    w = console_world["a"]
    shop = await _world(client, db_session, w)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    fake = FakeGoogle([Busy(start, start), Busy(start, start + timedelta(hours=1))])
    stats = await _pass(w["tenant_id"], fake)
    assert stats["busy"] == 1
    assert (await _staff_calendar(client, shop))["status"] == "connected"


async def test_the_listing_follows_every_page() -> None:
    def event(n: int) -> dict[str, Any]:
        hour = f"{10 + n}:00:00"
        return {
            "id": f"e{n}",
            "start": {"dateTime": f"2026-11-05T{hour}Z"},
            "end": {"dateTime": f"2026-11-05T{hour.replace(':00:00', ':30:00')}Z"},
        }

    provider = _Provider(
        {"items": [event(0)], "nextPageToken": "p2"},
        {"items": [event(1)], "nextPageToken": "p3"},
        {"items": [event(2)]},
    )
    got = await ComposioGoogleCalendar(provider).busy(CONN, "cal", *WINDOW, tz=TZ)
    assert [b.event_id for b in got] == ["e0", "e1", "e2"]
    assert [args.get("pageToken") for _, args in provider.calls] == [None, "p2", "p3"]


async def test_a_listing_that_never_ends_is_a_failure() -> None:
    class Endless(_Provider):
        async def execute_tool(self, **kwargs: Any) -> Any:
            self.calls.append((kwargs["tool_slug"], kwargs["arguments"]))
            return SimpleNamespace(data={"items": [], "nextPageToken": "again"}, error=None)

    provider = Endless()
    with pytest.raises(GoogleCalendarError):
        await ComposioGoogleCalendar(provider).busy(CONN, "cal", *WINDOW, tz=TZ)
    assert len(provider.calls) == calendar_sync.MAX_PAGES


async def test_only_calendars_that_can_be_written_are_offered() -> None:
    """El de festivos o uno compartido para leer no puede recibir el «Ocupado»: cada
    escritura fallaría para siempre. Y una cuenta con muchos pasa de una página."""
    provider = _Provider(
        {
            "items": [
                {"id": "mine", "summary": "Lucía", "accessRole": "owner"},
                {"id": "holidays", "summary": "Festivos", "accessRole": "reader"},
                {"id": "shared", "summary": "Sala", "accessRole": "freeBusyReader"},
            ],
            "nextPageToken": "p2",
        },
        {"items": [{"id": "team", "summary": "Equipo", "accessRole": "writer"}]},
    )
    got = await ComposioGoogleCalendar(provider).list_calendars(CONN)
    assert got == [{"id": "mine", "name": "Lucía"}, {"id": "team", "name": "Equipo"}]
    assert provider.calls[1] == ("GOOGLECALENDAR_LIST_CALENDARS", {"page_token": "p2"})


async def test_a_refusal_of_the_provider_says_it_is_about_permission() -> None:
    for answer in (ComposioAuthExpired("expired"), "401 invalid_grant"):
        with pytest.raises(GoogleCalendarError) as caught:
            await ComposioGoogleCalendar(_Provider(answer)).busy(CONN, "cal", *WINDOW, tz=TZ)
        assert caught.value.kind == "auth"


async def test_a_rate_limit_is_not_a_lost_permission() -> None:
    """Google responde 403 también al pasarse de cuota, y eso se arregla solo."""
    with pytest.raises(GoogleCalendarError) as caught:
        await ComposioGoogleCalendar(_Provider("403 rateLimitExceeded")).busy(
            CONN, "cal", *WINDOW, tz=TZ
        )
    assert caught.value.kind == "other"


async def test_the_call_to_the_sdk_leaves_the_event_loop() -> None:
    """El SDK es síncrono: en el bucle de eventos, cada llamada a Google paraba al
    worker o a la API entera mientras durase."""
    seen: list[int] = []

    def execute(slug: str, **_: Any) -> dict[str, Any]:
        seen.append(threading.get_ident())
        return {"data": {"items": []}, "error": None, "successful": True}

    client = object.__new__(LiveComposioClient)
    client._client = SimpleNamespace(tools=SimpleNamespace(execute=execute))
    got = await client.execute_tool(
        tool_slug="GOOGLECALENDAR_EVENTS_LIST", user_id="u", connection_id="c", arguments={}
    )
    assert got.data == {"items": []}
    assert seen and seen[0] != threading.get_ident()
