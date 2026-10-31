"""Spec 043 — la agenda en modo Servicios por ``/console/lite/reservas/*``.

R2 a R5 con un cliente de peluquería: Lucía (pausa de 14 a 15) y Marcos;
Corte (30 min) y Color (90 min).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest

from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"


@pytest.fixture
async def shop(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


def _new(shop: dict[str, Any], day: Any, at: str, **kw: Any) -> dict[str, Any]:
    body = {
        "date": day.isoformat(),
        "time": at,
        "staff_id": str(shop["lucia"]),
        "service_id": str(shop["corte"]),
        "contact": {"name": "Ana Pérez", "phone": "+56911112222"},
    }
    body.update(kw)
    return body


async def test_settings_say_the_mode_and_the_hours(client, shop) -> None:
    r = await client.get(f"{BASE}/settings", headers=shop["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "services"
    assert body["capacity"] is None
    assert body["hours_missing"] is False
    assert body["waitlist"] == {"enabled": True, "lead_minutes": 120}
    assert body["business_hours"]["monday"] == [{"from": "09:00", "to": "21:00"}]


async def test_the_business_cannot_change_the_mode(client, shop) -> None:
    r = await client.patch(f"{BASE}/settings", headers=shop["headers"](), json={"mode": "capacity"})
    assert r.status_code == 422


async def test_settings_patch_needs_the_current_version(client, shop) -> None:
    h = shop["headers"]
    ok = await client.patch(
        f"{BASE}/settings",
        headers={**h(), "If-Match": "1"},
        json={"waitlist": {"lead_minutes": 240}},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["waitlist"]["lead_minutes"] == 240
    stale = await client.patch(
        f"{BASE}/settings", headers={**h(), "If-Match": "1"}, json={"reminder_enabled": False}
    )
    assert stale.status_code == 412


async def test_slots_respect_the_persons_pause(client, shop) -> None:
    day = future_day()
    r = await client.get(
        f"{BASE}/slots",
        headers=shop["headers"](),
        params={
            "date": day.isoformat(),
            "service_id": str(shop["color"]),
            "staff_id": str(shop["lucia"]),
        },
    )
    assert r.status_code == 200, r.text
    times = [s["time"] for s in r.json()["slots"]]
    assert "12:30" in times  # 12:30 a 14:00 cabe antes de la pausa
    assert "13:00" not in times  # 13:00 a 14:30 pisa la pausa
    assert "15:00" in times


async def test_a_booking_takes_the_slot_and_a_second_one_is_refused(client, shop) -> None:
    day = future_day()
    h = shop["headers"]
    first = await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))
    assert first.status_code == 201, first.text
    b = first.json()
    assert b["status"] == "confirmed"
    assert b["origin"] == "person" and b["channel"] == "phone"
    assert b["created_by"] == {"kind": "person", "name": "Valeria Ríos"}
    assert b["local"]["start"] == "10:00" and b["local"]["end"] == "10:30"
    assert b["price"] == {"amount_minor": 15000, "currency": "CLP"}
    assert set(b["allowed"]) >= {"move", "cancel"}

    again = await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "slot_taken"

    slots = await client.get(
        f"{BASE}/slots",
        headers=h(),
        params={
            "date": day.isoformat(),
            "service_id": str(shop["corte"]),
            "staff_id": str(shop["lucia"]),
        },
    )
    assert "10:00" not in [s["time"] for s in slots.json()["slots"]]


async def test_the_same_key_never_books_twice(client, shop) -> None:
    day = future_day()
    key = str(uuid.uuid4())
    one = await client.post(
        f"{BASE}/bookings",
        headers={**shop["headers"](), "Idempotency-Key": key},
        json=_new(shop, day, "11:00"),
    )
    two = await client.post(
        f"{BASE}/bookings",
        headers={**shop["headers"](), "Idempotency-Key": key},
        json=_new(shop, day, "11:00"),
    )
    assert one.status_code == two.status_code == 201, two.text
    assert one.json()["id"] == two.json()["id"]


async def test_move_needs_the_version_and_leaves_history(client, shop) -> None:
    day = future_day()
    h = shop["headers"]
    b = (await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))).json()
    url = f"{BASE}/bookings/{b['id']}/move"
    stale = await client.post(
        url, headers={**h(), "If-Match": "99"}, json={"date": day.isoformat(), "time": "11:30"}
    )
    assert stale.status_code == 412
    moved = await client.post(
        url,
        headers={**h(), "If-Match": str(b["version"])},
        json={"date": day.isoformat(), "time": "11:30"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["local"]["start"] == "11:30"
    detail = (await client.get(f"{BASE}/bookings/{b['id']}", headers=h())).json()
    kinds = [e["kind"] for e in detail["events"]]
    assert kinds[:1] == ["created"] and "moved" in kinds
    move_event = next(e for e in detail["events"] if e["kind"] == "moved")
    assert move_event["data"]["from"]["start"] == "10:00"
    assert move_event["data"]["to"]["start"] == "11:30"
    assert move_event["data"]["notified"] is True
    assert move_event["actor"] == {"kind": "person", "name": "Valeria Ríos"}


async def test_list_filters_and_closed_days(client, db_session, console_world) -> None:
    w = console_world["a"]
    closed_sundays = {
        **{
            d: [{"from": "09:00", "to": "21:00"}]
            for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
        },
        "sunday": [],
    }
    shop = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], hours=closed_sundays
    )
    start = future_day(1)
    end = future_day(8)
    h = shop["headers"]
    day = future_day(2) if future_day(2).weekday() != 6 else future_day(3)
    await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))
    r = await client.get(
        f"{BASE}/bookings", headers=h(), params={"from": start.isoformat(), "to": end.isoformat()}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1
    # Los domingos de esos ocho días: uno, o dos si mañana es domingo.
    sundays = sum((start + timedelta(days=i)).weekday() == 6 for i in range((end - start).days + 1))
    assert len(body["closed_days"]) == sundays
    none = await client.get(
        f"{BASE}/bookings",
        headers=h(),
        params={"from": start.isoformat(), "to": end.isoformat(), "status": "cancelled"},
    )
    assert none.json()["items"] == []


async def test_cancel_preview_and_offer_to_the_waitlist(client, shop) -> None:
    day = future_day()
    h = shop["headers"]
    early = (
        await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))
    ).json()
    # Marta tiene Corte más tarde y quiere adelantar.
    later = await client.post(
        f"{BASE}/bookings",
        headers=h(),
        json=_new(
            shop,
            day,
            "17:00",
            join_waitlist=True,
            contact={"name": "Marta Gil", "phone": "+56933334444"},
        ),
    )
    assert later.status_code == 201, later.text
    assert later.json()["wants_earlier"] is True

    preview = await client.get(f"{BASE}/bookings/{early['id']}/cancel-preview", headers=h())
    assert preview.json() == {"can_offer": True, "candidates": 1, "why_not": None}

    cancelled = await client.post(
        f"{BASE}/bookings/{early['id']}/cancel",
        headers={**h(), "If-Match": str(early["version"])},
        json={"notify": True, "offer_slot": True},
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["cancelled"]["by"] == "business"
    assert body["offer"]["candidates"] == 1

    offers = (await client.get(f"{BASE}/offers", headers=h())).json()["items"]
    assert len(offers) == 1
    assert offers[0]["candidates"][0]["status"] == "waiting"
    assert offers[0]["candidates"][0]["name"] == "Marta Gil"
    # Mientras se ofrece, el hueco está retenido.
    slots = await client.get(
        f"{BASE}/slots",
        headers=h(),
        params={
            "date": day.isoformat(),
            "service_id": str(shop["corte"]),
            "staff_id": str(shop["lucia"]),
        },
    )
    assert "10:00" not in [s["time"] for s in slots.json()["slots"]]

    stopped = await client.post(f"{BASE}/offers/{offers[0]['id']}/stop", headers=h())
    assert stopped.json()["status"] == "stopped"


async def test_invalid_transitions_say_so(client, shop) -> None:
    day = future_day()
    h = shop["headers"]
    b = (await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))).json()
    for action in ("arrive", "noshow", "undo", "confirm"):
        r = await client.post(
            f"{BASE}/bookings/{b['id']}/{action}", headers={**h(), "If-Match": str(b["version"])}
        )
        assert r.status_code == 409, (action, r.text)
        assert r.json()["detail"]["code"] == "invalid_transition"


async def test_archiving_someone_with_bookings_is_refused(client, shop) -> None:
    day = future_day()
    h = shop["headers"]
    await client.post(f"{BASE}/bookings", headers=h(), json=_new(shop, day, "10:00"))
    r = await client.post(f"{BASE}/staff/{shop['lucia']}/archive", headers=h())
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "live_reservations", "count": 1}
    ok = await client.post(f"{BASE}/staff/{shop['marcos']}/archive", headers=h())
    assert ok.status_code == 204
    staff = (await client.get(f"{BASE}/staff", headers=h())).json()["items"]
    assert [s["name"] for s in staff] == ["Lucía"]


async def test_team_and_services_crud(client, shop) -> None:
    h = shop["headers"]
    nora = await client.post(f"{BASE}/staff", headers=h(), json={"name": "Nora"})
    assert nora.status_code == 201, nora.text
    assert nora.json()["effective_hours"]["monday"] == [{"from": "09:00", "to": "21:00"}]
    svc = await client.post(
        f"{BASE}/services",
        headers=h(),
        json={"name": "Barba", "duration_minutes": 45, "staff_ids": [nora.json()["id"]]},
    )
    assert svc.status_code == 201, svc.text
    assert svc.json()["staff"] == "some"
    assert svc.json()["price"] is None
    bad = await client.post(
        f"{BASE}/services", headers=h(), json={"name": "X", "duration_minutes": 50}
    )
    assert bad.status_code == 422


async def test_without_hours_nothing_is_bookable(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], hours=None
    )
    settings = (await client.get(f"{BASE}/settings", headers=shop["headers"]())).json()
    assert settings["hours_missing"] is True
    r = await client.post(
        f"{BASE}/bookings", headers=shop["headers"](), json=_new(shop, future_day(), "10:00")
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "hours_missing"


async def test_capacity_routes_say_wrong_mode(client, shop) -> None:
    day = future_day()
    r = await client.get(
        f"{BASE}/occupancy",
        headers=shop["headers"](),
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "wrong_mode"


async def test_summary_for_the_panel(client, shop) -> None:
    r = await client.get(f"{BASE}/summary", headers=shop["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "services"
    assert body["today"]["people"] is None
    assert body["today"]["seats"] is None
    assert body["errors"] == []
    assert body["waitlist"] == {"waiting": 0}


async def test_business_hours_edit_canonical(client, shop) -> None:
    h = shop["headers"]
    r = await client.put(
        f"{BASE}/business-hours",
        headers=h(),
        json={
            "hours": {
                "monday": [{"from": "13:00", "to": "16:00"}, {"from": "20:00", "to": "23:00"}],
                "sunday": [],
            }
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["business_hours"]["monday"][1] == {"from": "20:00", "to": "23:00"}
    assert r.json()["business_hours"]["tuesday"] == []
    three = await client.put(
        f"{BASE}/business-hours",
        headers=h(),
        json={
            "hours": {
                "monday": [
                    {"from": "08:00", "to": "09:00"},
                    {"from": "10:00", "to": "11:00"},
                    {"from": "12:00", "to": "13:00"},
                ]
            }
        },
    )
    assert three.status_code == 422


async def test_editing_the_hours_derives_the_prompt_label(client, db_session, shop) -> None:
    """Spec 047 (T056, research D15) sustituye la regla de la 043: el horario es
    uno solo, el de la ficha, y la etiqueta del prompt (``business_hours.label``,
    la lee ``agent_configs``) deja de ser una copia escrita a mano: es la frase
    «Así lo dirá el agente» del horario que el negocio acaba de guardar."""
    import sqlalchemy as sa

    from nexus_api.db.models import Tenant

    await db_session.execute(
        sa.update(Tenant)
        .where(Tenant.id == shop["tenant_id"])
        .values(business_hours={"monday": [{"from": "09:00", "to": "18:00"}], "label": "L 9-18"})
    )
    await db_session.commit()
    r = await client.put(
        f"{BASE}/business-hours",
        headers=shop["headers"](),
        json={"hours": {"monday": [{"from": "10:00", "to": "19:00"}]}},
    )
    assert r.status_code == 200, r.text
    assert "label" not in r.json()["business_hours"]
    db_session.expire_all()
    stored = await db_session.scalar(
        sa.select(Tenant.business_hours).where(Tenant.id == shop["tenant_id"])
    )
    assert stored["label"] == "Abrimos lunes de 10:00 a 19:00. Cerramos martes a domingo."
    assert stored["monday"] == [{"from": "10:00", "to": "19:00"}]


async def test_a_waitlist_entry_with_an_unknown_service_or_person_is_a_404(client, shop) -> None:
    """/cso (apéndice): un ``service_id`` o ``staff_id`` que no es del negocio
    (de la vecina o inventado) es el 404 de siempre, no un 500 de la base."""
    h = shop["headers"]
    for body in (
        {"name": "Marta", "service_id": str(uuid.uuid4())},
        {"name": "Marta", "service_id": str(shop["corte"]), "staff_id": str(uuid.uuid4())},
    ):
        r = await client.post(f"{BASE}/waitlist", headers=h(), json=body)
        assert r.status_code == 404, (body, r.status_code, r.text)
