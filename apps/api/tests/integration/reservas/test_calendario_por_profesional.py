"""Spec 043, requisitos 12 y 13 — cada profesional conecta su calendario.

Luis, 2026-11-04: «conectar otros calendarios debe hacerse desde el mismo panel ya que
cada profesional tiene su propio calendario con sus propias horas».

Con un doble de la puerta del proveedor, con una cuenta por conexión: nunca la red. **Lo
que aquí se prueba es nuestro lado; contra Google real no se ha probado nada.**
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.api.console.lite import reservas as lite_reservas
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, Connector, Reservation, Tenant, TenantConnector
from nexus_api.services.connectors.composio_client import (
    ComposioUnavailable,
    LiveComposioClient,
)
from nexus_api.services.reservations import calendar_sync
from nexus_api.services.reservations.calendar_sync import (
    TOOLKIT,
    Busy,
    ComposioGoogleCalendar,
    Connection,
    GoogleCalendarError,
)
from nexus_api.services.reservations.core import load_ctx
from tests.conftest import future_day, make_reservas
from tests.integration.reservas._calendars import connected, set_state

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")


class Accounts:
    """Una cuenta de Google por conexión, con sus calendarios y sus eventos."""

    def __init__(self) -> None:
        self.links: list[dict[str, str]] = []
        self.state: dict[str, str] = {}
        self.calendars: dict[str, list[dict[str, Any]]] = {}
        self.events: dict[tuple[str, str], Busy] = {}
        self.foreign: list[Busy] = []
        self.calls: list[tuple[str, str]] = []
        self.revoked: list[str] = []
        self.refused: set[str] = set()
        self.link_error: Exception | None = None
        self.list_error: Exception | None = None
        self.hide_new_events = False
        #: Se crea de verdad y la respuesta no trae el id.
        self.answer_without_id = False
        self.hang = False
        self.read_error: Exception | None = None
        #: Lo que solo se ve con la conexión del negocio.
        self.business_only: list[Busy] = []
        self.by_calendar: dict[str, list[Busy]] = {}
        self.gone: set[str] = set()
        self.delete_error: dict[str, Exception] = {}
        self.state_error: Exception | None = None
        #: Se crea de verdad y la respuesta no llega, una vez.
        self.time_out_after_creating = False
        self._next = 0

    def account(self, connection_id: str, *calendars: str, primary: str | None = None) -> None:
        main = primary or (calendars[0] if calendars else None)
        self.calendars[connection_id] = [
            {"id": c, "name": c, "primary": c == main} for c in calendars
        ]

    async def link(self, user_id: str, callback_url: str) -> tuple[str, str]:
        if self.link_error is not None:
            raise self.link_error
        self._next += 1
        connection_id = f"ca_{self._next}"
        self.links.append(
            {"connection": connection_id, "user_id": user_id, "callback": callback_url}
        )
        self.state[connection_id] = "INITIATED"
        return connection_id, f"https://google.test/auth/{connection_id}"

    async def account_state(self, connection_id: str) -> str:
        if self.state_error is not None:
            raise self.state_error
        return self.state.get(connection_id, "NOT_FOUND")

    async def revoke(self, connection_id: str) -> None:
        self.revoked.append(connection_id)

    async def list_calendars(self, conn: Connection) -> list[dict[str, Any]]:
        if self.list_error is not None:
            raise self.list_error
        return list(self.calendars.get(conn.connection_id, []))

    def _guard(self, conn: Connection) -> None:
        if conn.connection_id in self.refused:
            raise GoogleCalendarError("401 invalid_grant", kind="auth")

    async def busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, *, tz: Any
    ) -> list[Busy]:
        self._guard(conn)
        if self.hang:
            await asyncio.sleep(3600)
        self.calls.append(("read", conn.connection_id))
        if self.read_error is not None:
            raise self.read_error
        if calendar_id in self.gone:
            raise GoogleCalendarError("404 Not Found", kind="not_found")
        if calendar_id in self.by_calendar:
            return list(self.by_calendar[calendar_id])
        if conn.connection_id == "ca_negocio":
            return [*self.foreign, *self.business_only]
        if self.hide_new_events:
            return list(self.foreign)
        ours = [b for (cal, _), b in self.events.items() if cal == calendar_id]
        return [*self.foreign, *ours]

    async def create_busy(
        self, conn: Connection, calendar_id: str, start: datetime, end: datetime, marker: str
    ) -> str:
        self._guard(conn)
        self.calls.append(("create", conn.connection_id))
        event_id = f"ev-{len(self.calls)}"
        self.events[(calendar_id, event_id)] = Busy(
            start, end, event_id, marker.removeprefix(calendar_sync.MARK)
        )
        if self.time_out_after_creating:
            self.time_out_after_creating = False
            raise TimeoutError
        return calendar_sync.UNKNOWN_EVENT if self.answer_without_id else event_id

    async def delete_busy(self, conn: Connection, calendar_id: str, event_id: str) -> None:
        self._guard(conn)
        if conn.connection_id in self.delete_error:
            raise self.delete_error[conn.connection_id]
        self.calls.append(("delete", conn.connection_id))
        self.events.pop((calendar_id, event_id), None)


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> Accounts:
    fake = Accounts()
    monkeypatch.setattr(calendar_sync, "default_gateway", lambda: fake)
    return fake


async def _shop(db_session: Any, w: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], **kw
    )


async def _pass(tenant_id: uuid.UUID, fake: Any, *, now: datetime | None = None) -> dict[str, int]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        ctx = await load_ctx(session, tenant_id)
        assert ctx is not None
        return await calendar_sync.sync_tenant(session, ctx, fake, now=now or datetime.now(UTC))


async def _calendar(client: Any, shop: dict[str, Any], who: str = "lucia") -> dict[str, Any]:
    items = (await client.get(f"{BASE}/staff", headers=shop["headers"]())).json()["items"]
    found: dict[str, Any] = next(s for s in items if s["id"] == str(shop[who]))["calendar"]
    return found


async def _connect(client: Any, shop: dict[str, Any], who: str = "lucia", **body: Any) -> Any:
    return await client.post(
        f"{BASE}/staff/{shop[who]}/calendar/connect", headers=shop["headers"](), json=body
    )


async def _refresh(client: Any, shop: dict[str, Any], who: str = "lucia") -> dict[str, Any]:
    r = await client.post(f"{BASE}/staff/{shop[who]}/calendar/refresh", headers=shop["headers"]())
    assert r.status_code == 200, r.text
    calendar: dict[str, Any] = r.json()["calendar"]
    return calendar


async def _book(client: Any, shop: dict[str, Any], who: str = "lucia", at: str = "10:00") -> Any:
    made = await client.post(
        f"{BASE}/bookings",
        headers=shop["headers"](),
        json={
            "date": future_day().isoformat(),
            "time": at,
            "staff_id": str(shop[who]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Ana Pérez", "phone": None},
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


async def _count(tenant_id: uuid.UUID, sql: str, **params: Any) -> int:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return int(await session.scalar(sa.text(sql), params) or 0)


# ── 12.2 Una identidad por profesional ──────────────────────────────────────


async def test_each_professional_authorizes_with_an_identity_of_their_own(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    tenant = await db_session.get(Tenant, w["tenant_id"])
    assert tenant is not None

    lucia = await _connect(client, shop, "lucia")
    marcos = await _connect(client, shop, "marcos")

    assert lucia.status_code == 200, lucia.text
    assert lucia.json() == {"redirect_url": "https://google.test/auth/ca_1"}
    assert [link["user_id"] for link in google.links] == [
        f"tenant_{tenant.slug}_staff_{shop['lucia']}",
        f"tenant_{tenant.slug}_staff_{shop['marcos']}",
    ]
    assert marcos.json()["redirect_url"] != lucia.json()["redirect_url"]
    staff = await client.get(f"{BASE}/staff", headers=shop["headers"]())
    assert "ca_1" not in staff.text and "tenant_" not in staff.text, "the identity stays inside"


async def test_the_way_back_goes_to_the_panel_or_to_a_page_anyone_can_land_on(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop, "lucia")
    await _connect(client, shop, "marcos", share=True)
    assert f"/reservas?tab=settings&calendar_return={shop['lucia']}" in google.links[0]["callback"]
    assert google.links[1]["callback"].endswith("/connectors/oauth-callback")


# ── 12.1 y 12.3 Cada estado, y cómo se llega a él ───────────────────────────


async def test_from_nothing_to_connected(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    assert (await _calendar(client, shop))["status"] == "none"

    await _connect(client, shop)
    assert (await _calendar(client, shop))["status"] == "pending"

    # Aún no ha autorizado: sigue esperando.
    assert (await _refresh(client, shop))["status"] == "pending"

    # Autorizó: con su calendario principal, sin elegir nada, y se ve qué cuenta es.
    google.account("ca_1", "lucia@gmail.com", "trabajo@group", primary="lucia@gmail.com")
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)
    calendar = await _calendar(client, shop)
    assert calendar["status"] == "connected"
    assert calendar["account"] == "lucia@gmail.com"
    assert calendar["calendar_name"] == "lucia@gmail.com"
    assert calendar["last_error"] is None


async def test_coming_back_from_google_settles_it_at_once(
    client, db_session, console_world, google: Accounts
) -> None:
    """La vuelta del proveedor no espera a la pasada: el panel lo pide y ya está."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.account("ca_1", "lucia@gmail.com")
    google.state["ca_1"] = "ACTIVE"

    calendar = await _refresh(client, shop)

    assert calendar["status"] == "connected"


async def test_refreshing_many_times_does_not_call_google_each_time(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@gmail.com")
    await _refresh(client, shop)
    reads = len([c for c in google.calls if c[0] == "read"])
    await _refresh(client, shop)
    assert len([c for c in google.calls if c[0] == "read"]) == reads


async def test_an_account_without_a_calendar_to_write_asks_for_one(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.account("ca_1")
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)
    calendar = await _calendar(client, shop)
    assert calendar["status"] == "needs_calendar"
    assert calendar["last_error"] == "no_calendar"


async def test_an_account_whose_calendars_say_nothing_about_primary_asks_to_choose(
    client, db_session, console_world, google: Accounts
) -> None:
    """No conocemos la respuesta real del proveedor: si no marca el principal, hay calendarios
    y hay que elegir. Decir que no tiene ninguno sería mentira."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.calendars["ca_1"] = [{"id": "uno", "name": "Uno", "primary": False}]
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)
    calendar = await _calendar(client, shop)
    assert calendar["status"] == "needs_calendar"
    assert calendar["last_error"] is None


# ── 12.4 y 12.5 Sin mezclar calendarios ─────────────────────────────────────


async def test_the_same_account_for_two_does_not_mix_their_calendars(
    client, db_session, console_world, google: Accounts
) -> None:
    """Quien pulsa «Conectar» para Marcos con la cuenta de Lucía no le deja el calendario
    de Lucía: hay que elegir otro, y la API dice de quién es."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop, "lucia")
    await _connect(client, shop, "marcos")
    for connection in ("ca_1", "ca_2"):
        google.account(connection, "lucia@gmail.com", "sala@group", primary="lucia@gmail.com")
        google.state[connection] = "ACTIVE"
    await _pass(w["tenant_id"], google)

    assert (await _calendar(client, shop, "lucia"))["status"] == "connected"
    marcos = await _calendar(client, shop, "marcos")
    assert marcos["status"] == "needs_calendar"
    assert marcos["last_error"] == "calendar_in_use"
    assert marcos["account"] == "lucia@gmail.com", "the row says which account it ended up with"

    listed = (
        await client.get(f"{BASE}/staff/{shop['marcos']}/calendars", headers=shop["headers"]())
    ).json()["calendars"]
    assert {c["id"]: c["used_by"] for c in listed} == {
        "lucia@gmail.com": "Lucía",
        "sala@group": None,
    }

    taken = await client.put(
        f"{BASE}/staff/{shop['marcos']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": "lucia@gmail.com"},
    )
    assert taken.status_code == 409
    assert taken.json()["detail"] == {"code": "calendar_in_use", "used_by": "Lucía"}

    chosen = await client.put(
        f"{BASE}/staff/{shop['marcos']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": "sala@group"},
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["calendar"]["status"] == "connected"
    assert chosen.json()["calendar"]["calendar_name"] == "sala@group"


async def test_the_base_refuses_one_calendar_for_two(db_session, console_world) -> None:
    """Dos peticiones a la vez pasarían las dos la comprobación de la API."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="uno@agenda")
    with pytest.raises(IntegrityError):
        await connected(w["tenant_id"], shop["marcos"], calendar_id="uno@agenda")


async def test_two_choosing_the_same_calendar_at_once_get_an_answer_and_not_an_error(
    client, db_session, console_world, google: Accounts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos pasan la comprobación; el índice de la base para a la segunda. Tiene que
    responder lo mismo que si hubiera llegado después."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="sala@group", name="Sala")
    await connected(w["tenant_id"], shop["marcos"])
    google.calendars[f"ca_{shop['marcos']}"] = [
        {"id": "sala@group", "name": "Sala", "primary": False}
    ]

    async def nobody_yet(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(calendar_sync, "_using", nobody_yet)

    taken = await client.put(
        f"{BASE}/staff/{shop['marcos']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": "sala@group"},
    )

    assert taken.status_code == 409, taken.text
    assert taken.json()["detail"]["code"] == "calendar_in_use"


async def test_a_calendar_of_someone_elses_account_cannot_be_chosen(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop, "lucia")
    await _connect(client, shop, "marcos")
    google.account("ca_1", "lucia@gmail.com")
    google.account("ca_2", "marcos@gmail.com")
    google.state.update(ca_1="ACTIVE", ca_2="ACTIVE")
    await _pass(w["tenant_id"], google)

    bad = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": "marcos@gmail.com"},
    )

    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "unknown_calendar"


# ── 12.6 Cada uno con su conexión ───────────────────────────────────────────


async def test_each_calendar_is_read_and_written_with_its_owners_connection(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    await _book(client, shop, "lucia", "10:00")
    await _book(client, shop, "marcos", "11:00")

    await _pass(w["tenant_id"], google)

    lucia, marcos = f"ca_{shop['lucia']}", f"ca_{shop['marcos']}"
    assert sorted(google.calls) == sorted(
        [("create", lucia), ("create", marcos), ("read", lucia), ("read", marcos)]
    )
    assert {cal for cal, _ in google.events} == {"lucia@agenda", "marcos@agenda"}
    starts = {cal: b.starts_at.astimezone(TZ).hour for (cal, _), b in google.events.items()}
    assert starts == {"lucia@agenda": 10, "marcos@agenda": 11}, "nobody gets another's booking"


async def test_a_booking_moved_to_someone_else_leaves_the_first_ones_account(
    client, db_session, console_world, google: Accounts
) -> None:
    """El evento vive en la cuenta de Lucía: con la conexión de Marcos ni se ve."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    booking = await _book(client, shop, "lucia")
    await _pass(w["tenant_id"], google)
    google.calls.clear()

    moved = await client.post(
        f"{BASE}/bookings/{booking['id']}/move",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"staff_id": str(shop["marcos"]), "notify": False},
    )
    assert moved.status_code == 200, moved.text
    await _pass(w["tenant_id"], google)

    assert ("delete", f"ca_{shop['lucia']}") in google.calls
    assert ("create", f"ca_{shop['marcos']}") in google.calls
    assert {cal for cal, _ in google.events} == {"marcos@agenda"}


# ── 12.7 Permiso perdido ────────────────────────────────────────────────────


async def test_a_lost_permission_only_touches_that_professional(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    google.foreign = [Busy(start, start + timedelta(hours=1), "theirs")]
    await _pass(w["tenant_id"], google)
    busy = "SELECT count(*) FROM reservation_busy WHERE staff_id = :s"
    assert await _count(w["tenant_id"], busy, s=shop["lucia"]) == 1

    google.refused = {f"ca_{shop['lucia']}"}
    await _pass(w["tenant_id"], google)

    lucia = await _calendar(client, shop, "lucia")
    assert lucia["status"] == "needs_reauth"
    assert lucia["calendar_name"] == "lucia@agenda"
    assert await _count(w["tenant_id"], busy, s=shop["lucia"]) == 0, "stops blocking at once"
    assert (await _calendar(client, shop, "marcos"))["status"] == "connected"
    assert await _count(w["tenant_id"], busy, s=shop["marcos"]) == 1


async def test_connecting_again_keeps_the_calendar_and_lets_the_old_connection_go(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="trabajo@group", name="Trabajo")
    await set_state(w["tenant_id"], shop["lucia"], last_error="auth")
    assert (await _calendar(client, shop))["status"] == "needs_reauth"

    assert (await _connect(client, shop)).status_code == 200
    calendar = await _calendar(client, shop)
    assert calendar["status"] == "pending"
    assert calendar["calendar_name"] == "Trabajo"
    assert google.revoked == [], "the one that works is not let go before the new one exists"

    google.account("ca_1", "lucia@gmail.com", "trabajo@group", primary="lucia@gmail.com")
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)
    assert google.revoked == [f"ca_{shop['lucia']}"]

    calendar = await _calendar(client, shop)
    assert calendar["status"] == "connected"
    assert calendar["calendar_name"] == "trabajo@group"
    assert calendar["account"] == "lucia@gmail.com"


async def test_a_calendar_that_keeps_failing_can_be_connected_again(
    client, db_session, console_world, google: Accounts
) -> None:
    """Un error de lectura se arregla solo muchas veces; cuando no, la salida es esta. Y lo
    que había leído deja de bloquear: nadie va a refrescarlo mientras espera."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda", name="Lucía")
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    google.foreign = [Busy(start, start + timedelta(hours=1), "theirs")]
    await _pass(w["tenant_id"], google)
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 1
    await set_state(w["tenant_id"], shop["lucia"], last_error="read")

    again = await _connect(client, shop)

    assert again.status_code == 200, again.text
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 0


async def test_a_healthy_calendar_does_not_authorize_again(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    again = await _connect(client, shop)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "calendar_already_connected"
    assert google.links == []


# ── 12.8 Desconectar ────────────────────────────────────────────────────────


async def test_disconnecting_stops_blocking_now_and_cleans_up_on_the_next_pass(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    google.foreign = [Busy(start, start + timedelta(hours=1), "theirs")]
    await _pass(w["tenant_id"], google)
    assert len(google.events) == 1

    off = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": None},
    )

    assert off.status_code == 200, off.text
    assert off.json()["calendar"]["status"] == "none"
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 0
    assert google.revoked == [], "its events still need this connection"

    # Mientras tanto, volver a conectar dice que espere, no que falló.
    wait = await _connect(client, shop)
    assert wait.status_code == 409
    assert wait.json()["detail"]["code"] == "calendar_disconnecting"

    await _pass(w["tenant_id"], google)

    assert google.events == {}
    assert google.revoked == [f"ca_{shop['lucia']}"]
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_staff_calendars") == 0
    assert (await _connect(client, shop)).status_code == 200
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        res = await session.get(Reservation, uuid.UUID(booking["id"]))
    assert res is not None and res.external_event_id is None and res.status == "confirmed"


async def test_disconnecting_with_a_lost_permission_lets_go_anyway(
    client, db_session, console_world, google: Accounts
) -> None:
    """Sin permiso no se puede borrar nada: insistir cada dos minutos no arregla nada."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    await _pass(w["tenant_id"], google)
    await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": None},
    )
    google.refused = {f"ca_{shop['lucia']}"}

    await _pass(w["tenant_id"], google)

    assert google.revoked == [f"ca_{shop['lucia']}"]
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_staff_calendars") == 0
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        res = await session.get(Reservation, uuid.UUID(booking["id"]))
    assert res is not None and res.external_event_id is None


async def test_archiving_a_professional_disconnects_them(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    archived = await client.post(f"{BASE}/staff/{shop['lucia']}/archive", headers=shop["headers"]())
    assert archived.status_code == 204, archived.text
    await _pass(w["tenant_id"], google)
    assert google.revoked == [f"ca_{shop['lucia']}"]
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_staff_calendars") == 0


async def test_deleting_the_client_lets_go_of_each_professionals_google(
    db_session, console_world, google: Accounts
) -> None:
    """La cuenta de Google es de la persona. Borrar el cliente se lleva la fila y con ella el
    único sitio que sabe qué conexión quitar: sin esto, el permiso se queda vivo para siempre."""
    from nexus_api.db.models import TenantStatus
    from nexus_api.services.business.writes import drain_after_commit
    from nexus_api.services.tenant_lifecycle import hard_delete_tenant

    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    neighbour = console_world["b"]
    shop_b = await _shop(db_session, neighbour)
    await connected(neighbour["tenant_id"], shop_b["lucia"], calendar_id="suya@agenda")
    tenant = await db_session.get(Tenant, w["tenant_id"])
    assert tenant is not None
    tenant.status = TenantStatus.ARCHIVED
    await db_session.commit()

    await hard_delete_tenant(db_session, tenant, actor="test")
    assert google.revoked == [], "nothing is revoked until the deletion holds"
    await db_session.commit()
    await drain_after_commit()

    assert sorted(google.revoked) == sorted([f"ca_{shop['lucia']}", f"ca_{shop['marcos']}"])


# ── 12.9 Lo que no se completa ──────────────────────────────────────────────


async def test_a_link_left_unfinished_goes_back_to_how_it_was(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    assert (await _calendar(client, shop))["status"] == "pending"

    # Antes de la hora, sigue esperando.
    await _pass(w["tenant_id"], google, now=datetime.now(UTC) + timedelta(minutes=30))
    assert (await _calendar(client, shop))["status"] == "pending"

    await _pass(
        w["tenant_id"],
        google,
        now=datetime.now(UTC) + calendar_sync.PENDING_EXPIRES_AFTER + timedelta(minutes=1),
    )
    assert (await _calendar(client, shop))["status"] == "none"
    assert google.revoked == ["ca_1"]


async def test_a_failed_authorization_of_someone_with_a_calendar_keeps_it_and_says_so(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(
        w["tenant_id"],
        shop["lucia"],
        calendar_id="lucia@agenda",
        name="Lucía",
        status="needs_reauth",
    )
    await _connect(client, shop)
    google.state["ca_1"] = "FAILED"

    await _pass(w["tenant_id"], google)

    calendar = await _calendar(client, shop)
    assert calendar["status"] == "needs_reauth"
    assert calendar["calendar_name"] == "Lucía"


# ── 12.10 El proveedor no responde ──────────────────────────────────────────


async def test_a_provider_that_does_not_answer_says_so_and_leaves_nothing_behind(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    google.link_error = ComposioUnavailable("down")
    answer = await _connect(client, shop)
    assert answer.status_code == 409
    assert answer.json()["detail"]["code"] == "calendar_unavailable"
    assert (await _calendar(client, shop))["status"] == "none"


async def test_calendars_only_exist_in_appointments_mode(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w, mode="capacity")
    answer = await client.post(
        f"{BASE}/staff/{uuid.uuid4()}/calendar/connect", headers=shop["headers"](), json={}
    )
    assert answer.status_code == 409
    assert answer.json()["detail"]["code"] == "wrong_mode"


# ── 12.12 El SDK, fuera del bucle de eventos ────────────────────────────────


async def test_every_call_to_the_sdk_leaves_the_event_loop() -> None:
    """Era el hueco que quedó tras ``execute_tool``: enlazar, leer y revocar una conexión
    también paraban al worker o a la API entera mientras duraban."""
    seen: list[int] = []

    def noting(answer: Any) -> Any:
        def call(*_: Any, **__: Any) -> Any:
            seen.append(threading.get_ident())
            return answer

        return call

    account = SimpleNamespace(id="ca", user_id="u", toolkit="t", status="ACTIVE", scopes=[])
    client = object.__new__(LiveComposioClient)
    client._client = SimpleNamespace(
        connected_accounts=SimpleNamespace(
            link=noting(SimpleNamespace(id="ca", redirect_url="https://x")),
            get=noting(account),
            delete=noting(None),
        ),
        auth_configs=SimpleNamespace(
            list=noting(SimpleNamespace(items=[SimpleNamespace(id="ac")]))
        ),
        toolkits=SimpleNamespace(get=noting(None)),
        tools=SimpleNamespace(get_raw_composio_tools=noting([])),
    )

    await client.link_account(user_id="u", auth_config_id="ac", allow_multiple=True)
    await client.get_account("ca")
    await client.revoke_account("ca")
    await client.find_auth_config_id("googlecalendar")
    await client.list_auth_configs()
    await client.get_toolkit_metadata("googlecalendar")
    await client.list_tools(user_id="u", toolkit="googlecalendar")

    assert len(seen) == 7
    assert threading.get_ident() not in seen


async def test_a_second_connection_of_the_same_professional_is_allowed_by_the_sdk() -> None:
    """Una conexión vieja activa en el proveedor no puede impedir volver a conectar: la fila
    dice cuál se usa. Sin ``allow_multiple`` el SDK se niega."""
    got: dict[str, Any] = {}

    class Client:
        async def find_auth_config_id(self, toolkit: str) -> str:
            got["toolkit"] = toolkit
            return "ac"

        async def link_account(self, **kwargs: Any) -> Any:
            got.update(kwargs)
            return SimpleNamespace(connection_id="ca", redirect_url="https://x")

    assert await ComposioGoogleCalendar(Client()).link("u", "https://back") == ("ca", "https://x")
    assert got["toolkit"] == "googlecalendar"
    assert got["allow_multiple"] is True
    assert got["user_id"] == "u"


# ── Requisito 13: lo que cambia en Google vuelve bien ───────────────────────


async def test_an_event_of_theirs_blocks_and_marks_a_clash(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    start = datetime.combine(future_day(), time(10, 0), tzinfo=TZ)
    google.foreign = [Busy(start, start + timedelta(hours=1), "dentist")]
    await _pass(w["tenant_id"], google)

    detail = (
        await client.get(f"{BASE}/bookings/{booking['id']}", headers=shop["headers"]())
    ).json()
    assert detail["clash"]["source"] == "google"
    slots = await client.get(
        f"{BASE}/slots",
        headers=shop["headers"](),
        params={
            "date": future_day().isoformat(),
            "service_id": str(shop["corte"]),
            "staff_id": str(shop["lucia"]),
        },
    )
    assert "10:30" not in [s["time"] for s in slots.json()["slots"]]


async def test_our_busy_deleted_by_hand_is_written_again(
    client, db_session, console_world, google: Accounts
) -> None:
    """Reservas manda: la cita sigue, así que su hora sigue ocupada en Google."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    await _pass(w["tenant_id"], google)
    assert len(google.events) == 1

    google.events.clear()  # alguien lo borró en Google
    await _pass(w["tenant_id"], google)
    await _pass(w["tenant_id"], google)

    assert len(google.events) == 1
    event = next(iter(google.events.values()))
    assert event.starts_at.astimezone(TZ).hour == 10
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        res = await session.get(Reservation, uuid.UUID(booking["id"]))
    assert res is not None and res.status == "confirmed", "the booking does not go anywhere"


async def test_our_busy_moved_by_hand_goes_back_to_the_hour_of_the_booking(
    client, db_session, console_world, google: Accounts
) -> None:
    """Mover la cita de un cliente sin avisarle no se hace desde otro calendario."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    await _pass(w["tenant_id"], google)
    key, event = next(iter(google.events.items()))

    google.events[key] = Busy(
        event.starts_at + timedelta(hours=3), event.ends_at + timedelta(hours=3), event.event_id
    )
    await _pass(w["tenant_id"], google)
    await _pass(w["tenant_id"], google)

    assert len(google.events) == 1
    again = next(iter(google.events.values()))
    assert again.starts_at == event.starts_at
    assert again.event_id != event.event_id
    detail = (
        await client.get(f"{BASE}/bookings/{booking['id']}", headers=shop["headers"]())
    ).json()
    assert detail["local"]["start"] == "10:00"
    assert detail["clash"] is None, "its own event never counts as busy"


async def test_what_was_just_written_is_not_written_twice(
    client, db_session, console_world, google: Accounts
) -> None:
    """La lectura de esa misma pasada puede no traerlo aún: no es que alguien lo borrara."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await _book(client, shop)
    google.hide_new_events = True

    stats = await _pass(w["tenant_id"], google)

    assert stats["written"] == 1
    assert (
        await _count(
            w["tenant_id"],
            "SELECT count(*) FROM reservations WHERE external_event_id IS NOT NULL",
        )
        == 1
    )


async def test_a_listing_that_never_brings_ours_does_not_pile_up_events(
    client, db_session, console_world, google: Accounts
) -> None:
    """Lo que no se ha probado contra Google real: si su listado no trajera nuestro evento por
    lo que sea, recrearlo cada dos minutos llenaría el calendario de «Ocupado». Por eso primero
    se borra el que creemos tener: en el peor caso da vueltas, pero no se acumula."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await _book(client, shop)
    google.hide_new_events = True

    for _ in range(6):
        await _pass(w["tenant_id"], google)

    assert len(google.events) == 1
    # Una vuelta cada dos pasadas: se aparta, se borra y se escribe. Nunca una por pasada.
    assert [c[0] for c in google.calls if c[0] != "read"] == [
        "create",
        "delete",
        "create",
        "delete",
        "create",
    ]


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "cancelled"},
        {"transparency": "transparent"},
        {"attendees": [{"self": True, "responseStatus": "declined"}]},
        {"eventType": "birthday"},
        {"eventType": "workingLocation"},
        {"start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}, "eventType": "birthday"},
        {"start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}, "status": "cancelled"},
    ],
)
async def test_what_does_not_really_take_time_does_not_block(extra: dict[str, Any]) -> None:
    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            return SimpleNamespace(
                data={
                    "items": [
                        {
                            "id": "e",
                            "start": {"dateTime": "2026-11-05T10:00:00Z"},
                            "end": {"dateTime": "2026-11-05T11:00:00Z"},
                            **extra,
                        }
                    ]
                },
                error=None,
            )

    window = (datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 6, tzinfo=UTC))
    got = await ComposioGoogleCalendar(Provider()).busy(
        Connection("u", "ca"), "cal", *window, tz=TZ
    )
    assert got == []


async def test_an_invitation_they_accepted_blocks() -> None:
    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            return SimpleNamespace(
                data={
                    "items": [
                        {
                            "id": "e",
                            "start": {"dateTime": "2026-11-05T10:00:00Z"},
                            "end": {"dateTime": "2026-11-05T11:00:00Z"},
                            "attendees": [
                                {"self": True, "responseStatus": "accepted"},
                                {"email": "otro@x", "responseStatus": "declined"},
                            ],
                        }
                    ]
                },
                error=None,
            )

    window = (datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 6, tzinfo=UTC))
    got = await ComposioGoogleCalendar(Provider()).busy(
        Connection("u", "ca"), "cal", *window, tz=TZ
    )
    assert [b.event_id for b in got] == ["e"]


async def test_a_whole_day_counts_though_google_marks_it_free() -> None:
    """Un evento de todo el día nace como ``transparent``, y es como se cierra un día (R13.4)."""

    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            return SimpleNamespace(
                data={
                    "items": [
                        {
                            "id": "vacaciones",
                            "start": {"date": "2026-11-05"},
                            "end": {"date": "2026-11-06"},
                            "transparency": "transparent",
                        },
                        {
                            "id": "fuera",
                            "start": {"date": "2026-11-05"},
                            "end": {"date": "2026-11-06"},
                            "eventType": "outOfOffice",
                        },
                    ]
                },
                error=None,
            )

    window = (datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 6, tzinfo=UTC))
    got = await ComposioGoogleCalendar(Provider()).busy(
        Connection("u", "ca"), "cal", *window, tz=TZ
    )
    assert [b.event_id for b in got] == ["vacaciones", "fuera"]


# ── La pasada no se espera a sí misma ───────────────────────────────────────


async def test_the_pass_does_not_wait_for_itself(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 4: quitar la referencia sin confirmar y apuntar el evento nuevo en otra
    conexión se bloqueaban para siempre, y con ellos todos los clientes del cron."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    booking = await _book(client, shop, "lucia")
    await _pass(w["tenant_id"], google)
    moved = await client.post(
        f"{BASE}/bookings/{booking['id']}/move",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"staff_id": str(shop["marcos"]), "notify": False},
    )
    assert moved.status_code == 200, moved.text
    await set_state(w["tenant_id"], shop["lucia"], connection_status="disconnecting")
    google.refused.add(f"ca_{shop['lucia']}")

    await asyncio.wait_for(_pass(w["tenant_id"], google), timeout=15)

    assert "marcos@agenda" in {cal for cal, _ in google.events}, "the new one gets written"
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_staff_calendars") == 1


async def test_a_row_someone_else_holds_does_not_stop_the_pass(
    client, db_session, console_world, google: Accounts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quien tiene la reserva agarrada no para a nadie: lo escrito de más se quita y se
    vuelve a escribir en la pasada siguiente."""
    monkeypatch.setattr(calendar_sync, "LOCK_TIMEOUT", "200ms")
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop, "lucia")

    sm = get_sessionmaker()
    async with sm() as holder, tenant_scoped_session(holder, w["tenant_id"]):
        await holder.execute(
            sa.select(Reservation.id)
            .where(Reservation.id == uuid.UUID(booking["id"]))
            .with_for_update()
        )
        await asyncio.wait_for(_pass(w["tenant_id"], google), timeout=15)
        assert google.events == {}, "what could not be noted down does not stay"

    await _pass(w["tenant_id"], google)
    assert len(google.events) == 1


# ── Volver a conectar con otra cuenta ───────────────────────────────────────


async def _ref(tenant_id: uuid.UUID, booking_id: str) -> str | None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await session.scalar(
            sa.select(Reservation.external_event_id).where(Reservation.id == uuid.UUID(booking_id))
        )


async def test_another_account_brings_their_future_bookings_with_it(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 5: el evento se queda atrás con la cuenta vieja y la nueva no sabe de la
    cita. Se quita con la conexión vieja, se escribe con la nueva, y solo entonces se suelta."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    old = f"ca_{shop['lucia']}"
    await connected(w["tenant_id"], shop["lucia"], calendar_id="vieja@agenda")
    booking = await _book(client, shop)
    await _pass(w["tenant_id"], google)
    assert {cal for cal, _ in google.events} == {"vieja@agenda"}
    await set_state(w["tenant_id"], shop["lucia"], last_error="auth")

    assert (await _connect(client, shop)).status_code == 200
    google.account("ca_1", "nueva@agenda")
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)

    assert {cal for cal, _ in google.events} == {"nueva@agenda"}
    assert ("delete", old) in google.calls
    assert ("create", "ca_1") in google.calls
    assert google.revoked == [old]
    assert "nueva@agenda" in (await _ref(w["tenant_id"], booking["id"]) or "")


async def test_a_migrated_row_gets_its_bookings_written_in_the_new_account(
    client, db_session, console_world, google: Accounts
) -> None:
    """Una fila de antes no tiene conexión con la que borrar: el evento viejo se queda donde
    estaba, sin bloquear nada, y la cita llega a la cuenta de la persona."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="negocio@agenda")
    await set_state(
        w["tenant_id"],
        shop["lucia"],
        connection_status="needs_reauth",
        connection_id=None,
        connection_user_id=None,
    )
    booking = await _book(client, shop)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
        await session.execute(
            sa.update(Reservation)
            .where(Reservation.id == uuid.UUID(booking["id"]))
            .values(external_event_id=f"{shop['lucia']} negocio@agenda ev-viejo")
        )

    assert (await _connect(client, shop)).status_code == 200
    google.account("ca_1", "lucia@agenda")
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)

    assert {cal for cal, _ in google.events} == {"lucia@agenda"}
    assert "lucia@agenda" in (await _ref(w["tenant_id"], booking["id"]) or "")


async def test_the_same_account_keeps_the_event_it_had(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    await _pass(w["tenant_id"], google)
    before = await _ref(w["tenant_id"], booking["id"])
    await set_state(w["tenant_id"], shop["lucia"], last_error="auth")

    await _connect(client, shop)
    google.account("ca_1", "lucia@agenda")
    google.state["ca_1"] = "ACTIVE"
    google.calls.clear()
    await _pass(w["tenant_id"], google)

    assert await _ref(w["tenant_id"], booking["id"]) == before
    assert not [c for c in google.calls if c[0] in ("create", "delete")]


async def test_a_failed_reconnection_goes_back_to_the_connection_it_had(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await set_state(w["tenant_id"], shop["lucia"], last_error="read")
    await _book(client, shop)

    await _connect(client, shop)
    google.state["ca_1"] = "REVOKED"
    await _pass(w["tenant_id"], google)

    calendar = await _calendar(client, shop)
    assert calendar["status"] == "connected"
    assert google.revoked == ["ca_1"], "the one that did not finish, not the one that works"
    assert ("create", f"ca_{shop['lucia']}") in google.calls


# ── Autorizó y Google no deja leer ──────────────────────────────────────────


async def test_authorizing_without_permission_does_not_wait_forever(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.state["ca_1"] = "ACTIVE"
    google.list_error = GoogleCalendarError("403 insufficient", kind="auth")

    await _pass(w["tenant_id"], google)

    calendar = await _calendar(client, shop)
    assert calendar["status"] == "needs_reauth"
    assert calendar["last_error"] == "auth"


async def test_google_not_answering_after_authorizing_waits_but_not_forever(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.state["ca_1"] = "ACTIVE"
    google.list_error = GoogleCalendarError("500", kind="other")

    await _pass(w["tenant_id"], google)
    assert (await _calendar(client, shop))["status"] == "pending"

    later = datetime.now(UTC) + calendar_sync.PENDING_EXPIRES_AFTER + timedelta(minutes=1)
    await _pass(w["tenant_id"], google, now=later)
    assert (await _calendar(client, shop))["status"] == "none"
    assert google.revoked == ["ca_1"]


# ── Una reserva movida no se queda sin evento ───────────────────────────────


@pytest.mark.parametrize("broken", ["lost_permission", "needs_reauth", "no_connection", "no_row"])
async def test_a_booking_moved_away_from_a_broken_calendar_reaches_the_new_one(
    client, db_session, console_world, google: Accounts, broken: str
) -> None:
    """Revisión, punto 6, y R12.7: lo de uno no toca a los demás."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    booking = await _book(client, shop, "lucia")
    await _pass(w["tenant_id"], google)
    moved = await client.post(
        f"{BASE}/bookings/{booking['id']}/move",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"staff_id": str(shop["marcos"]), "notify": False},
    )
    assert moved.status_code == 200, moved.text
    if broken == "lost_permission":
        google.refused.add(f"ca_{shop['lucia']}")
    elif broken == "needs_reauth":
        await set_state(w["tenant_id"], shop["lucia"], connection_status="needs_reauth")
    elif broken == "no_connection":
        await set_state(
            w["tenant_id"],
            shop["lucia"],
            connection_status="needs_reauth",
            connection_id=None,
            connection_user_id=None,
        )
    else:
        async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
            await session.execute(
                sa.text("DELETE FROM reservation_staff_calendars WHERE staff_id = :s"),
                {"s": shop["lucia"]},
            )

    await _pass(w["tenant_id"], google)

    assert "marcos@agenda" in {cal for cal, _ in google.events}
    assert "marcos@agenda" in (await _ref(w["tenant_id"], booking["id"]) or "")


# ── Lo nuestro se reconoce por su marca ─────────────────────────────────────


async def _forget_ref(tenant_id: uuid.UUID, booking_id: str) -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.update(Reservation)
            .where(Reservation.id == uuid.UUID(booking_id))
            .values(external_event_id=None)
        )


async def test_our_old_busy_does_not_come_back_as_someone_elses(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 7a: permiso perdido, desconectar y volver a conectar. El evento viejo ya no
    es de ninguna referencia: sin la marca serían dos «Ocupado» y la cita chocaría consigo."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    await _pass(w["tenant_id"], google)
    await _forget_ref(w["tenant_id"], booking["id"])

    await _pass(w["tenant_id"], google)

    assert len(google.events) == 1, "one busy per booking"
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 0


async def test_an_event_answered_without_an_id_is_recognised_by_its_mark(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 7b: sin id, la cita chocaba consigo misma y cancelar no liberaba la hora."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    google.answer_without_id = True

    await _pass(w["tenant_id"], google)

    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 0
    ((_, event_id),) = google.events
    assert (await _ref(w["tenant_id"], booking["id"]) or "").endswith(event_id), "it is adopted"

    cancelled = await client.post(
        f"{BASE}/bookings/{booking['id']}/cancel",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"notify": False},
    )
    assert cancelled.status_code == 200, cancelled.text
    google.answer_without_id = False
    await _pass(w["tenant_id"], google)
    assert google.events == {}


async def test_cancelling_a_booking_whose_event_has_no_id_frees_the_hour(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    google.answer_without_id = True
    google.hide_new_events = True
    await _pass(w["tenant_id"], google)
    assert await _ref(w["tenant_id"], booking["id"]) is not None

    cancelled = await client.post(
        f"{BASE}/bookings/{booking['id']}/cancel",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"notify": False},
    )
    assert cancelled.status_code == 200, cancelled.text
    google.hide_new_events = False
    await _pass(w["tenant_id"], google)

    assert google.events == {}, "the orphan goes away by its mark"
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 0


async def test_a_timeout_while_creating_leaves_one_busy(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await _book(client, shop)
    google.time_out_after_creating = True

    await _pass(w["tenant_id"], google)
    await _pass(w["tenant_id"], google)

    assert len(google.events) == 1
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 0


@pytest.mark.parametrize("whose", ["unknown", "other_client"])
async def test_a_mark_that_is_not_of_this_client_still_blocks(
    client, db_session, console_world, google: Accounts, whose: str
) -> None:
    """Cualquiera puede escribir la marca en una invitación: no libera ese hueco."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    marker = str(uuid.uuid4())
    if whose == "other_client":
        other = await _shop(db_session, console_world["b"])
        marker = (await _book(client, other))["id"]
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    google.foreign = [Busy(start, start + timedelta(hours=1), "theirs", marker)]

    await _pass(w["tenant_id"], google)

    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_busy") == 1


async def test_a_mark_only_counts_on_what_they_organize() -> None:
    """Una invitación de fuera con la marca en la descripción se lee como ocupado normal."""
    reservation = str(uuid.uuid4())

    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            common = {
                "start": {"dateTime": "2026-11-05T10:00:00Z"},
                "end": {"dateTime": "2026-11-05T11:00:00Z"},
                "description": f"{calendar_sync.MARK}{reservation}",
            }
            return SimpleNamespace(
                data={
                    "items": [
                        {"id": "ours", **common, "organizer": {"self": True}},
                        {"id": "bare", **common},
                        {"id": "invite", **common, "organizer": {"email": "x@y.z"}},
                        {
                            "id": "ours_free",
                            **common,
                            "organizer": {"self": True},
                            "transparency": "transparent",
                        },
                        {"id": "invented", **common, "description": "auphere:reserva:nada"},
                    ]
                },
                error=None,
            )

    window = (datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 6, tzinfo=UTC))
    got = await ComposioGoogleCalendar(Provider()).busy(
        Connection("u", "ca"), "cal", *window, tz=TZ
    )
    assert {b.event_id: b.marker for b in got} == {
        "ours": reservation,
        "bare": reservation,
        "invite": None,
        "ours_free": reservation,
        "invented": None,
    }


# ── Lo que dice el proveedor ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Invalid Credentials", "auth"),
        ("Request had invalid authentication credentials", "auth"),
        ("Connected account not found", "auth"),
        ("connection ca_1 not found", "auth"),
        ("Auth config not found", "auth"),
        ("Tool GOOGLECALENDAR_DELETE_EVENT not found", "other"),
        ("Toolkit not found", "other"),
        ("404 Not Found", "not_found"),
        ("Event not found", "not_found"),
        ("Resource has been deleted", "not_found"),
        ("403 rateLimitExceeded", "other"),
        ("401 invalid_grant", "auth"),
    ],
)
async def test_what_the_provider_says_means_what_it_means(text: str, kind: str) -> None:
    assert calendar_sync._kind_of_text(text) == kind


@pytest.mark.parametrize(
    ("error", "raises"),
    [
        ("404 Not Found", None),
        ("Connected account not found", "auth"),
        ("Tool GOOGLECALENDAR_DELETE_EVENT not found", "other"),
    ],
)
async def test_only_a_missing_event_counts_as_deleted(error: str, raises: str | None) -> None:
    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            return SimpleNamespace(data=None, error=error)

    gateway = ComposioGoogleCalendar(Provider())
    if raises is None:
        await gateway.delete_busy(Connection("u", "ca"), "cal", "ev")
        return
    with pytest.raises(GoogleCalendarError) as caught:
        await gateway.delete_busy(Connection("u", "ca"), "cal", "ev")
    assert caught.value.kind == raises


@pytest.mark.parametrize("answer", [{}, {"response_data": {}}, {"ok": True}])
async def test_an_answer_without_an_id_does_not_create_again(answer: dict[str, Any]) -> None:
    """Sin error, se creó: se reconoce por su marca en la lectura. Repetirlo daría un evento más
    cada dos minutos."""

    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            return SimpleNamespace(data=answer, error=None)

    start = datetime(2026, 11, 5, 10, tzinfo=UTC)
    got = await ComposioGoogleCalendar(Provider()).create_busy(
        Connection("u", "ca"), "cal", start, start + timedelta(hours=1), "m"
    )
    assert got == calendar_sync.UNKNOWN_EVENT


async def test_a_booking_with_seconds_does_not_loop(
    client, db_session, console_world, google: Accounts
) -> None:
    """Una cita importada con segundos: el evento se crea en minutos y parecía movido a mano."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    booking = await _book(client, shop)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
        await session.execute(
            sa.update(Reservation)
            .where(Reservation.id == uuid.UUID(booking["id"]))
            .values(
                starts_at=Reservation.starts_at + timedelta(seconds=17),
                ends_at=Reservation.ends_at + timedelta(seconds=17),
            )
        )
    await _pass(w["tenant_id"], google)
    ((key, event),) = google.events.items()
    google.events[key] = Busy(
        event.starts_at.replace(second=0, microsecond=0),
        event.ends_at.replace(second=0, microsecond=0),
        event.event_id,
        event.marker,
    )
    google.calls.clear()

    for _ in range(3):
        await _pass(w["tenant_id"], google)

    assert not [c for c in google.calls if c[0] in ("create", "delete")]


async def test_a_very_long_calendar_name_does_not_stop_the_pass(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.calendars["ca_1"] = [{"id": "lucia@agenda", "name": "N" * 400, "primary": True}]
    google.state["ca_1"] = "ACTIVE"

    await _pass(w["tenant_id"], google)

    calendar = await _calendar(client, shop)
    assert calendar["status"] == "connected"
    assert len(calendar["calendar_name"]) == 255


async def test_a_calendar_id_that_does_not_fit_is_not_offered() -> None:
    class Provider:
        async def execute_tool(self, **_: Any) -> Any:
            return SimpleNamespace(
                data={
                    "items": [
                        {"id": "x" * 256, "summary": "Largo", "primary": True},
                        {"id": "corto", "summary": "Corto"},
                    ]
                },
                error=None,
            )

    got = await ComposioGoogleCalendar(Provider()).list_calendars(Connection("u", "ca"))
    assert [c["id"] for c in got] == ["corto"]


async def test_each_call_to_the_provider_is_tried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un reintento tras un timeout crearía el evento dos veces."""
    import composio

    made: list[dict[str, Any]] = []
    monkeypatch.setattr(composio, "Composio", lambda **kw: made.append(kw))
    LiveComposioClient(api_key="k")
    assert made == [{"api_key": "k", "max_retries": 0}]


async def test_a_provider_that_hangs_answers_instead_of_hanging_the_request(
    client, db_session, console_world, google: Accounts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lite_reservas, "REFRESH_TIMEOUT_SECONDS", 0.05)
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    google.hang = True

    r = await client.post(
        f"{BASE}/staff/{shop['lucia']}/calendar/refresh", headers=shop["headers"]()
    )

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "calendar_unavailable"


# ── Lo que ya está en el Google del negocio sigue bloqueando ────────────────


async def _business_google(
    db_session: Any, tenant_id: uuid.UUID, *, status: str = "connected"
) -> None:
    """La conexión de Google del negocio de antes (spec 023), como la deja el consentimiento."""
    connector = await db_session.scalar(sa.select(Connector).where(Connector.slug == TOOLKIT))
    if connector is None:
        connector = Connector(
            slug=TOOLKIT,
            display_name="Google Calendar",
            vendor="Google",
            category="calendar",
            auth_kind="oauth_composio",
            mcp_server_ref=f"composio:{TOOLKIT}",
            auto_enable_on_connect=True,
        )
        db_session.add(connector)
        await db_session.flush()
    connector_id = connector.id
    await db_session.commit()
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            TenantConnector(
                tenant_id=tenant_id,
                connector_id=connector_id,
                status=status,
                credentials_ref={"composio_connection_id": "ca_negocio", "user_id": "tenant_x"},
            )
        )
    await db_session.commit()


def _at_four() -> tuple[datetime, datetime]:
    start = datetime.combine(future_day(), time(16, 0), tzinfo=TZ)
    return start, start + timedelta(hours=1)


async def _business_rows(tenant_id: uuid.UUID) -> set[uuid.UUID]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.execute(
            sa.text("SELECT staff_id FROM reservation_busy WHERE source = 'business'")
        )
        return {r.staff_id for r in rows.all()}


async def test_what_is_in_the_business_google_keeps_blocking_until_each_one_connects(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 3: al pasar, las citas tomadas en Google no se importan (no dicen de qué
    cliente son), pero esa hora no se vuelve a dar."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]

    await _pass(w["tenant_id"], google)

    assert await _business_rows(w["tenant_id"]) == {shop["lucia"], shop["marcos"]}
    slots = await client.get(
        f"{BASE}/slots",
        headers=shop["headers"](),
        params={"date": future_day().isoformat(), "service_id": str(shop["corte"])},
    )
    assert slots.status_code == 200, slots.text
    assert "16:00" not in str(slots.json())
    row = await _calendar(client, shop, "marcos")
    assert row["status"] == "none"
    assert row["business_busy"] is True

    # Lucía conecta el suyo: lo del negocio deja de ser de ella.
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    google.foreign = []
    google.business_only = [Busy(*_at_four(), "cita-de-antes")]
    await _pass(w["tenant_id"], google)
    assert await _business_rows(w["tenant_id"]) == {shop["marcos"]}
    assert (await _calendar(client, shop, "lucia")).get("business_busy") is False

    # Marcos también: ya nadie mira el calendario del negocio.
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    google.calls.clear()
    await _pass(w["tenant_id"], google)
    assert await _business_rows(w["tenant_id"]) == set()
    assert ("read", "ca_negocio") not in google.calls


async def test_the_row_of_someone_migrated_reads_their_calendar_with_the_business_connection(
    client, db_session, console_world, google: Accounts
) -> None:
    """Una fila de antes dice de quién es ese calendario: solo le bloquea a esa persona."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@negocio")
    await set_state(
        w["tenant_id"],
        shop["lucia"],
        connection_status="needs_reauth",
        connection_id=None,
        connection_user_id=None,
    )
    google.by_calendar["lucia@negocio"] = [Busy(*_at_four(), "suya")]

    await _pass(w["tenant_id"], google)

    assert await _business_rows(w["tenant_id"]) == {shop["lucia"]}
    assert ("read", "ca_negocio") in google.calls


async def test_a_calendar_the_business_cannot_see_falls_back_to_its_own(
    db_session, console_world, google: Accounts
) -> None:
    """Quien perdió su propia cuenta conserva en la fila un calendario que el negocio no ve."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@propia")
    await set_state(
        w["tenant_id"],
        shop["lucia"],
        connection_status="needs_reauth",
        connection_id=None,
        connection_user_id=None,
    )
    google.gone.add("lucia@propia")
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]

    await _pass(w["tenant_id"], google)

    assert await _business_rows(w["tenant_id"]) == {shop["lucia"], shop["marcos"]}


async def test_a_read_that_fails_keeps_the_business_busy(
    db_session, console_world, google: Accounts
) -> None:
    """Son citas ya dadas: dejar de leerlas no las cancela."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]
    await _pass(w["tenant_id"], google)
    assert shop["lucia"] in await _business_rows(w["tenant_id"])

    google.read_error = GoogleCalendarError("500", kind="other")
    later = datetime.now(UTC) + calendar_sync.BUSY_STALE_AFTER + timedelta(minutes=1)
    await _pass(w["tenant_id"], google, now=later)

    assert shop["lucia"] in await _business_rows(w["tenant_id"])


async def test_a_refused_business_connection_keeps_blocking(
    db_session, console_world, google: Accounts
) -> None:
    """Revisión, D4: si no, esas horas se vuelven a dar."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]
    await _pass(w["tenant_id"], google)

    google.refused.add("ca_negocio")
    await _pass(w["tenant_id"], google)

    assert shop["lucia"] in await _business_rows(w["tenant_id"])


async def test_a_business_connection_that_fell_keeps_blocking_without_reading(
    db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]
    await _pass(w["tenant_id"], google)
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        await db_session.execute(
            sa.update(TenantConnector)
            .where(TenantConnector.tenant_id == w["tenant_id"])
            .values(status="needs_reauth")
        )
    await db_session.commit()
    google.calls.clear()

    await _pass(w["tenant_id"], google)

    assert shop["lucia"] in await _business_rows(w["tenant_id"])
    assert ("read", "ca_negocio") not in google.calls


async def test_removing_the_business_connection_stops_blocking(
    db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]
    await _pass(w["tenant_id"], google)
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        await db_session.execute(
            sa.update(TenantConnector)
            .where(TenantConnector.tenant_id == w["tenant_id"])
            .values(status="disconnected")
        )
    await db_session.commit()

    await _pass(w["tenant_id"], google)

    assert await _business_rows(w["tenant_id"]) == set()


async def test_what_is_left_after_removing_the_connection_still_gives_work_to_the_cron(
    db_session, console_world, google: Accounts
) -> None:
    """Sin esto, nadie volvería a pasar por ese cliente y seguiría bloqueado."""
    w = console_world["a"]
    await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    google.foreign = [Busy(*_at_four(), "cita-de-antes")]
    await _pass(w["tenant_id"], google)
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        await db_session.execute(
            sa.update(TenantConnector)
            .where(TenantConnector.tenant_id == w["tenant_id"])
            .values(status="disconnected")
        )
    await db_session.commit()

    async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
        assert await calendar_sync.has_work(session, now=datetime.now(UTC)) is True


async def test_what_we_wrote_in_the_business_calendar_does_not_block(
    client, db_session, console_world, google: Accounts
) -> None:
    """Las reservas de antes dejaron su «Ocupado» en el calendario del negocio."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    booking = await _book(client, shop)
    google.foreign = [Busy(*_at_four(), "nuestro", booking["id"])]

    await _pass(w["tenant_id"], google)

    assert await _business_rows(w["tenant_id"]) == set()


async def test_the_business_calendar_is_only_read_when_the_cron_passes(
    client, db_session, console_world, google: Accounts
) -> None:
    """Un botón de una persona no lee por todos."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _business_google(db_session, w["tenant_id"])
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")

    await _refresh(client, shop)

    assert ("read", "ca_negocio") not in google.calls


async def test_a_paused_or_absent_connection_gives_no_work_to_the_cron(
    db_session, console_world
) -> None:
    w = console_world["a"]
    await _shop(db_session, w)

    async def work() -> bool:
        async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
            return await calendar_sync.has_work(session, now=datetime.now(UTC))

    assert await work() is False
    await _business_google(db_session, w["tenant_id"], status="paused")
    assert await work() is False
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        await db_session.execute(sa.update(TenantConnector).values(status="connected"))
    await db_session.commit()
    assert await work() is True


# ── Salir de Servicios o apagar el módulo ───────────────────────────────────


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> dict[str, str]:
    from nexus_api.services import operator_identity

    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def test_leaving_services_lets_go_of_everyone(
    client, db_session, console_world, google: Accounts, admin_headers: dict[str, str]
) -> None:
    """En Aforo no hay panel de profesionales: nadie podría desconectarlas."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await _book(client, shop)
    await _pass(w["tenant_id"], google)
    assert len(google.events) == 1
    h = await _operator(db_session, admin_headers)

    r = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=h,
        json={
            "enabled": True,
            "modules": ["panel", "reservas"],
            "reservas": {
                "mode": "capacity",
                "capacity_kind": "restaurant",
                "on_live": "cancel_and_notify",
            },
        },
    )
    assert r.status_code == 200, r.text

    await _pass(w["tenant_id"], google)

    assert google.events == {}
    assert google.revoked == [f"ca_{shop['lucia']}"]
    assert await _count(w["tenant_id"], "SELECT count(*) FROM reservation_staff_calendars") == 0


async def test_turning_the_module_off_keeps_the_calendars_in_sync(
    client, db_session, console_world, google: Accounts, admin_headers: dict[str, str]
) -> None:
    """Decisión: las reservas por venir y sus avisos siguen vivos con el módulo apagado, y la
    persona sigue teniendo esa cita. Soltar su calendario se la borraría de Google."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await _book(client, shop)
    h = await _operator(db_session, admin_headers)
    r = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=h,
        json={"enabled": True, "modules": ["panel"]},
    )
    assert r.status_code == 200, r.text

    await _pass(w["tenant_id"], google)

    assert len(google.events) == 1
    assert google.revoked == []
    assert (
        await _count(
            w["tenant_id"],
            "SELECT count(*) FROM reservation_staff_calendars WHERE connection_status = 'connected'",
        )
        == 1
    )


# ── Queda escrito ───────────────────────────────────────────────────────────


async def _trail(tenant_id: uuid.UUID) -> list[Any]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.action.like("reservations.calendar_%"))
            .order_by(AuditLog.created_at)
        )
        return list(rows)


async def test_touching_someones_calendar_leaves_a_trail(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 22: una persona del negocio puede tocar el calendario de otra."""
    w = console_world["a"]
    shop = await _shop(db_session, w)

    assert (await _connect(client, shop)).status_code == 200
    google.account("ca_1", "lucia@agenda", "otro@agenda", primary="lucia@agenda")
    google.state["ca_1"] = "ACTIVE"
    await _pass(w["tenant_id"], google)
    put = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": "otro@agenda"},
    )
    assert put.status_code == 200, put.text
    off = await client.put(
        f"{BASE}/staff/{shop['lucia']}/calendar",
        headers=shop["headers"](),
        json={"calendar_id": None},
    )
    assert off.status_code == 200, off.text

    trail = await _trail(w["tenant_id"])
    assert [t.action for t in trail] == [
        "reservations.calendar_connect_started",
        "reservations.calendar_changed",
        "reservations.calendar_disconnected",
    ]
    assert {t.target for t in trail} == {f"reservation_staff:{shop['lucia']}"}
    for t in trail:
        assert t.actor
        assert "@" not in str(t.after_json), "no account of anyone in the trail"
        assert t.after_json["staff"] == "Lucía"


# ── Lo que quedó a medias ───────────────────────────────────────────────────


async def test_a_calendar_that_keeps_failing_does_not_keep_a_moved_booking_out_for_ever(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 6: un fallo que no es de permiso dejaba la referencia y nunca se escribía
    en el nuevo. Un rato se espera, para no duplicar; después, la marca limpia lo que quede."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await connected(w["tenant_id"], shop["marcos"], calendar_id="marcos@agenda")
    booking = await _book(client, shop, "lucia")
    await _pass(w["tenant_id"], google)
    moved = await client.post(
        f"{BASE}/bookings/{booking['id']}/move",
        headers={**shop["headers"](), "If-Match": str(booking["version"])},
        json={"staff_id": str(shop["marcos"]), "notify": False},
    )
    assert moved.status_code == 200, moved.text
    google.delete_error[f"ca_{shop['lucia']}"] = GoogleCalendarError("500", kind="other")

    await _pass(w["tenant_id"], google)
    assert "marcos@agenda" not in {cal for cal, _ in google.events}, "a short failure just waits"

    later = datetime.now(UTC) + calendar_sync.REMOVE_WAITS_AT_MOST + timedelta(minutes=1)
    await _pass(w["tenant_id"], google, now=later)

    assert "marcos@agenda" in {cal for cal, _ in google.events}
    assert "marcos@agenda" in (await _ref(w["tenant_id"], booking["id"]) or "")


async def test_a_refused_new_account_does_not_read_as_connected(
    client, db_session, console_world, google: Accounts
) -> None:
    """Revisión, punto 14: la anterior sigue, y la persona tiene que saber que la nueva no entró."""
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await connected(w["tenant_id"], shop["lucia"], calendar_id="lucia@agenda")
    await set_state(w["tenant_id"], shop["lucia"], last_error="read")
    await _book(client, shop)
    await _connect(client, shop)
    google.state["ca_1"] = "ACTIVE"
    google.list_error = GoogleCalendarError("403 insufficient", kind="auth")

    await _pass(w["tenant_id"], google)

    calendar = await _calendar(client, shop)
    assert calendar["status"] == "error"
    assert calendar["last_error"] == "new_account_refused"
    assert google.revoked == ["ca_1"]
    assert ("create", f"ca_{shop['lucia']}") in google.calls, "the old one keeps working"

    google.list_error = None
    await _pass(w["tenant_id"], google)
    assert (await _calendar(client, shop))["last_error"] == "new_account_refused"

    later = datetime.now(UTC) + calendar_sync.PENDING_EXPIRES_AFTER + timedelta(minutes=1)
    await _pass(w["tenant_id"], google, now=later)
    assert (await _calendar(client, shop))["status"] == "connected"


async def test_a_provider_that_never_says_how_it_ended_does_not_wait_for_ever(
    client, db_session, console_world, google: Accounts
) -> None:
    w = console_world["a"]
    shop = await _shop(db_session, w)
    await _connect(client, shop)
    google.state_error = GoogleCalendarError("500", kind="other")

    await _pass(w["tenant_id"], google)
    assert (await _calendar(client, shop))["status"] == "pending"

    later = datetime.now(UTC) + calendar_sync.PENDING_EXPIRES_AFTER + timedelta(minutes=1)
    await _pass(w["tenant_id"], google, now=later)
    assert (await _calendar(client, shop))["status"] == "none"
