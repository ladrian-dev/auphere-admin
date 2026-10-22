"""Spec 043 — la ocupación en modo Aforo por ``/console/lite/reservas/*``.

Restaurante: aforo 64, 6 guardadas para llegadas sin reserva, 90 min por mesa,
10 por reserva para el agente. Franjas cada 30 min de 10:00 a 20:00.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Reservation
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")
ALL_DAY = {
    d: [{"from": "00:00", "to": "23:59"}]
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


@pytest.fixture
async def resto(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], mode="capacity"
    )


def _new(day: Any, at: str, n: int, **kw: Any) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "time": at,
        "party_size": n,
        "contact": {"name": "Mesa", "phone": None},
        **kw,
    }


async def test_settings_bring_the_restaurant(client, resto) -> None:
    body = (await client.get(f"{BASE}/settings", headers=resto["headers"]())).json()
    assert body["mode"] == "capacity"
    assert body["capacity_kind"] == "restaurant"
    assert body["capacity"]["seats"] == 64
    assert body["capacity"]["walkin_hold"] == 6
    assert body["release_unconfirmed"] is True


async def test_a_full_hour_says_how_much_is_left_and_where_there_is_room(client, resto) -> None:
    day = future_day()
    h = resto["headers"]
    big = await client.post(f"{BASE}/bookings", headers=h(), json=_new(day, "15:00", 50))
    assert big.status_code == 201, big.text  # el negocio sí puede pasar del máximo
    slots = await client.get(
        f"{BASE}/slots", headers=h(), params={"date": day.isoformat(), "party_size": 10}
    )
    by_time = {s["time"]: s for s in slots.json()["slots"]}
    assert by_time["15:00"]["fits"] is False
    assert by_time["15:00"]["left"] == 8  # 64 - 6 - 50
    assert by_time["15:00"]["why"] == "full"
    refused = await client.post(f"{BASE}/bookings", headers=h(), json=_new(day, "15:00", 10))
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "slot_taken"
    assert detail["first_fit"] == {"date": day.isoformat(), "time": "16:30"}


async def test_blocks_stop_new_bookings_but_keep_the_old(client, resto) -> None:
    day = future_day()
    h = resto["headers"]
    await client.post(f"{BASE}/bookings", headers=h(), json=_new(day, "12:00", 4))
    created = await client.post(
        f"{BASE}/blocks",
        headers=h(),
        json={
            "date": day.isoformat(),
            "from": "12:00",
            "until": "13:00",
            "label": "Evento privado",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["overlapping_bookings"] == 1
    assert created.json()["block"]["label"] == "Evento privado"
    slots = await client.get(
        f"{BASE}/slots", headers=h(), params={"date": day.isoformat(), "party_size": 2}
    )
    by_time = {s["time"]: s for s in slots.json()["slots"]}
    assert by_time["12:30"]["why"] == "blocked"
    assert by_time["11:30"]["why"] == "block_overlap"  # la estancia pisa el bloqueo
    occ = await client.get(
        f"{BASE}/occupancy", headers=h(), params={"from": day.isoformat(), "to": day.isoformat()}
    )
    cell = next(s for s in occ.json()["days"][0]["slots"] if s["time"] == "12:00")
    assert cell["blocked"]["label"] == "Evento privado"
    assert cell["arriving"] == 4 and cell["present"] == 4

    block_id = created.json()["block"]["id"]
    assert (await client.post(f"{BASE}/blocks/{block_id}/remove", headers=h())).status_code == 204
    again = await client.get(
        f"{BASE}/slots", headers=h(), params={"date": day.isoformat(), "party_size": 2}
    )
    assert {s["time"]: s for s in again.json()["slots"]}["12:30"]["fits"] is True


async def test_walkins_use_the_held_seats(client, db_session, console_world) -> None:
    w = console_world["a"]
    resto = await make_reservas(
        db_session,
        partner_id=w["partner_id"],
        tenant_id=w["tenant_id"],
        mode="capacity",
        hours=ALL_DAY,
    )
    from nexus_api.db.models import ReservationSettings

    s = await db_session.get(ReservationSettings, w["tenant_id"])
    s.schedule = {"model": "slots", "step_minutes": 30, "from": "00:00", "to": "23:30"}
    await db_session.commit()
    h = resto["headers"]
    # 58 sitios ocupados ahora: para reservar no queda nada; para quien llega, 6.
    now_local = datetime.now(TZ)
    slot = now_local.replace(minute=0 if now_local.minute < 30 else 30, second=0, microsecond=0)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        session.add(
            Reservation(
                tenant_id=w["tenant_id"],
                mode="capacity",
                status="arrived",
                starts_at=slot,
                ends_at=slot + timedelta(minutes=90),
                party_size=58,
                origin="person",
                channel="phone",
                created_by_kind="person",
                contact_name="Grupo",
            )
        )
    walkin = await client.post(f"{BASE}/walkins", headers=h(), json={"party_size": 6, "name": None})
    assert walkin.status_code == 201, walkin.text
    body = walkin.json()
    assert body["status"] == "arrived" and body["origin"] == "walkin"
    assert body["allowed"] == []  # una llegada sin reserva no se deshace
    full = await client.post(f"{BASE}/walkins", headers=h(), json={"party_size": 1})
    assert full.status_code == 409


async def test_arrive_noshow_and_undo_today(client, resto, console_world) -> None:
    tid = console_world["a"]["tenant_id"]
    now = datetime.now(UTC)
    sm = get_sessionmaker()
    ids: list[uuid.UUID] = []
    async with sm() as session, tenant_scoped_session(session, tid):
        for minutes in (10, -10):  # empieza en 10 min · empezó hace 10 min
            r = Reservation(
                tenant_id=tid,
                mode="capacity",
                status="confirmed",
                starts_at=now + timedelta(minutes=minutes),
                ends_at=now + timedelta(minutes=minutes + 90),
                party_size=4,
                origin="person",
                channel="phone",
                created_by_kind="person",
                contact_name="Mesa",
            )
            session.add(r)
            await session.flush()
            ids.append(r.id)
    soon, started = ids
    h = resto["headers"]
    one = (await client.get(f"{BASE}/bookings/{soon}", headers=h())).json()
    if datetime.now(TZ).date() == (datetime.now(TZ) + timedelta(minutes=10)).date():
        assert "arrive" in one["allowed"] and "noshow" not in one["allowed"]
    two = (await client.get(f"{BASE}/bookings/{started}", headers=h())).json()
    assert {"arrive", "noshow"} <= set(two["allowed"])
    arrived = await client.post(
        f"{BASE}/bookings/{started}/arrive", headers={**h(), "If-Match": str(two["version"])}
    )
    assert arrived.status_code == 200, arrived.text
    assert arrived.json()["status"] == "arrived"
    undone = await client.post(
        f"{BASE}/bookings/{started}/undo",
        headers={**h(), "If-Match": str(arrived.json()["version"])},
    )
    assert undone.json()["status"] == "confirmed"
    noshow = await client.post(
        f"{BASE}/bookings/{started}/noshow",
        headers={**h(), "If-Match": str(undone.json()["version"])},
    )
    assert noshow.json()["status"] == "noshow"


async def test_waitlist_and_a_manual_offer(client, resto) -> None:
    day = future_day()
    h = resto["headers"]
    entry = await client.post(
        f"{BASE}/waitlist",
        headers=h(),
        json={
            "name": "Marta",
            "phone": "+56955556666",
            "party_size": 4,
            "date": day.isoformat(),
            "time": "19:00",
        },
    )
    assert entry.status_code == 201, entry.text
    assert entry.json()["fits_now"] is True
    offer = await client.post(f"{BASE}/waitlist/{entry.json()['id']}/offer", headers=h())
    assert offer.status_code == 200, offer.text
    assert offer.json()["window_minutes"] == 15
    assert offer.json()["candidates"][0]["status"] == "waiting"
    listed = (await client.get(f"{BASE}/waitlist", headers=h())).json()
    assert listed["items"][0]["status"] == "offered"
    assert listed["items"][0]["offer"]["deadline_at"] is not None


async def test_summary_for_capacity(client, resto) -> None:
    body = (await client.get(f"{BASE}/summary", headers=resto["headers"]())).json()
    assert body["mode"] == "capacity"
    assert body["today"]["people"] == 0
    assert body["today"]["inside_now"] == 0
    # «Dentro ahora: N de 64»: el aforo viaja con el resumen.
    assert body["today"]["seats"] == 64
    assert body["clashes"] == 0


async def test_services_routes_say_wrong_mode(client, resto) -> None:
    r = await client.get(f"{BASE}/staff", headers=resto["headers"]())
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "wrong_mode"


async def test_a_move_keeps_what_it_does_not_send(client, resto) -> None:
    """Contrato: en ``move`` lo que no cambia se omite."""
    day = future_day()
    h = resto["headers"]
    made = (await client.post(f"{BASE}/bookings", headers=h(), json=_new(day, "19:00", 2))).json()
    moved = await client.post(
        f"{BASE}/bookings/{made['id']}/move",
        headers={**h(), "If-Match": str(made["version"])},
        json={"party_size": 4, "notify": False},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["party_size"] == 4
    assert moved.json()["local"]["date"] == day.isoformat()
    assert moved.json()["local"]["start"] == "19:00"


async def test_recent_offers_are_the_closed_ones(client, resto) -> None:
    """Contrato: ``recent`` = cerradas en las últimas 24 h; la que corre sale en
    ``running`` y no dos veces."""
    day = future_day()
    h = resto["headers"]
    entry = await client.post(
        f"{BASE}/waitlist",
        headers=h(),
        json={
            "name": "Marta",
            "phone": "+56955556666",
            "party_size": 4,
            "date": day.isoformat(),
            "time": "19:00",
        },
    )
    offer = (await client.post(f"{BASE}/waitlist/{entry.json()['id']}/offer", headers=h())).json()

    def ids(r: Any) -> list[str]:
        return [o["id"] for o in r.json()["items"]]

    assert ids(await client.get(f"{BASE}/offers", headers=h(), params={"status": "running"})) == [
        offer["id"]
    ]
    assert ids(await client.get(f"{BASE}/offers", headers=h(), params={"status": "recent"})) == []
    stopped = await client.post(f"{BASE}/offers/{offer['id']}/stop", headers=h())
    assert stopped.status_code == 200, stopped.text
    assert ids(await client.get(f"{BASE}/offers", headers=h(), params={"status": "running"})) == []
    assert ids(await client.get(f"{BASE}/offers", headers=h(), params={"status": "recent"})) == [
        offer["id"]
    ]
