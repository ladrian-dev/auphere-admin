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
    # Spec 056 (5.1): el horario con la forma de la ficha, el que se edita.
    assert body["hours"]["days"]["mon"] == [{"open": "09:00", "close": "21:00", "overnight": False}]
    assert body["hours"]["revision"] == 0 and body["hours"]["location_id"] is None
    assert body["location_hours"] == []


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
    assert svc.json()["price"] == {"kind": "none"}
    # Spec 056 (5.2): las duraciones de la ficha, de 5 a 480 en pasos de 5.
    bad = await client.post(
        f"{BASE}/services", headers=h(), json={"name": "X", "duration_minutes": 47}
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == {"code": "bad_duration", "field": "duration_min"}


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


# ── spec 056, historia 4: horario y servicios con las reglas de la ficha ────
#
# Los Ajustes de Reservas editan lo mismo que la ficha del partner y con las mismas
# reglas (requisito 5): el horario va por días (solo los tocados) y con la
# revisión de la sección, y los servicios pasan por el catálogo de la ficha.


async def _ficha_week(db_session, tenant_id, days, *, location_id=None) -> None:
    """Un horario guardado como lo guarda la ficha del partner."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.services.business import hours
    from nexus_api.services.business.sections import Actor

    partner = Actor(kind="partner_member", id=str(uuid.uuid4()), origin="console")
    async with tenant_scoped_session(db_session, tenant_id):
        week = hours.week_from_days("daily", days)
        await hours.save_week(db_session, week, actor=partner, location_id=location_id)
    await db_session.commit()


async def _settings(client, shop) -> dict[str, Any]:
    r = await client.get(f"{BASE}/settings", headers=shop["headers"]())
    assert r.status_code == 200, r.text
    return r.json()


MONDAY = [
    {"open": "08:00", "close": "11:00"},
    {"open": "12:00", "close": "15:00"},
    {"open": "16:00", "close": "19:00"},
    {"open": "22:00", "close": "02:00"},
]


async def test_patching_tuesday_keeps_monday_with_its_shifts_and_its_night_one(
    client, db_session, shop
) -> None:
    """Historia 4, escenario 1 (5.1, 5.3): tres turnos y un nocturno, guardados en
    la ficha, sobreviven a guardar el martes desde Reservas."""
    await _ficha_week(db_session, shop["tenant_id"], {"mon": MONDAY, "sat": MONDAY[:1]})
    before = (await _settings(client, shop))["hours"]
    assert [s["overnight"] for s in before["days"]["mon"]] == [False, False, False, True]

    r = await client.patch(
        f"{BASE}/business-hours",
        headers=shop["headers"](),
        json={
            "revision": before["revision"],
            "days": {"tue": [{"open": "10:00", "close": "18:00"}]},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["days"]["tue"] == [{"open": "10:00", "close": "18:00", "overnight": False}]
    after = (await _settings(client, shop))["hours"]
    assert after["days"]["mon"] == before["days"]["mon"]
    assert after["days"]["sat"] == before["days"]["sat"]
    assert after["days"]["tue"] == [{"open": "10:00", "close": "18:00", "overnight": False}]
    assert after["revision"] == before["revision"] + 1
    assert after["layout"] == "daily"


async def test_a_location_with_its_own_hours_is_shown_and_left_alone(
    client, db_session, shop
) -> None:
    """5.1: Reservas edita la semana del negocio; la de una sede se enseña y no cambia."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models.business import BusinessLocation
    from nexus_api.services.business import hours

    async with tenant_scoped_session(db_session, shop["tenant_id"]):
        norte = BusinessLocation(tenant_id=shop["tenant_id"], name="Cultor Norte")
        sur = BusinessLocation(tenant_id=shop["tenant_id"], name="Cultor Sur")
        db_session.add_all([norte, sur])
        await db_session.flush()
        norte_id, sur_id = norte.id, sur.id
    await db_session.commit()
    own = {"mon": [{"open": "11:00", "close": "13:00"}]}
    await _ficha_week(db_session, shop["tenant_id"], own, location_id=norte_id)

    settings = await _settings(client, shop)
    by_name = {loc["location"]["name"]: loc for loc in settings["location_hours"]}
    assert by_name["Cultor Norte"]["has_own_hours"] is True
    assert by_name["Cultor Norte"]["label"]
    assert by_name["Cultor Sur"] == {
        "location": {"id": str(sur_id), "name": "Cultor Sur"},
        "has_own_hours": False,
        "label": None,
    }

    r = await client.patch(
        f"{BASE}/business-hours",
        headers=shop["headers"](),
        json={"revision": settings["hours"]["revision"], "days": {"mon": []}},
    )
    assert r.status_code == 200, r.text
    async with tenant_scoped_session(db_session, shop["tenant_id"]):
        kept = await hours.load_week(db_session, location_id=norte_id)
    assert kept is not None
    assert hours.week_to_days(kept)["mon"] == [
        {"open": "11:00", "close": "13:00", "overnight": False}
    ]


async def test_the_rules_apply_to_the_touched_days_only(client, db_session, shop) -> None:
    """5.1 y 5.5: lo que se toca cumple las reglas de la ficha (6 turnos, pasos de
    5 minutos, sin solapes); lo guardado que no las cumple se queda como está."""
    import sqlalchemy as sa

    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models.business import BusinessShift

    await _ficha_week(db_session, shop["tenant_id"], {"mon": [{"open": "09:00", "close": "14:00"}]})
    # Un turno de antes de la regla de los 5 minutos (la API aceptaba cualquiera).
    async with tenant_scoped_session(db_session, shop["tenant_id"]):
        await db_session.execute(
            sa.update(BusinessShift)
            .where(BusinessShift.tenant_id == shop["tenant_id"], BusinessShift.weekday == 0)
            .values(open_min=9 * 60 + 7)
        )
    await db_session.commit()
    h = shop["headers"]
    revision = (await _settings(client, shop))["hours"]["revision"]

    seven = [{"open": f"{8 + i:02d}:00", "close": f"{8 + i:02d}:30"} for i in range(7)]
    for days, code, day in (
        ({"wed": seven}, "too_many_shifts", "wed"),
        ({"wed": [{"open": "10:07", "close": "12:00"}]}, "bad_step", "wed"),
        (
            {"thu": [{"open": "09:00", "close": "13:00"}, {"open": "12:00", "close": "15:00"}]},
            "overlap",
            "thu",
        ),
        ({"sun": [{"open": "22:00", "close": "10:00"}]}, "overlap_next_day", "sun"),
        ({"funday": []}, "invalid_day", "funday"),
    ):
        r = await client.patch(
            f"{BASE}/business-hours", headers=h(), json={"revision": revision, "days": days}
        )
        assert r.status_code == 422, (days, r.text)
        assert r.json()["detail"]["code"] == code, days
        assert r.json()["detail"]["day"] == day, days

    ok = await client.patch(
        f"{BASE}/business-hours",
        headers=h(),
        json={"revision": revision, "days": {"tue": [{"open": "09:00", "close": "14:00"}]}},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["days"]["mon"] == [{"open": "09:07", "close": "14:00", "overnight": False}]


async def test_a_stale_revision_is_a_conflict(client, shop) -> None:
    """5.3: dos personas a la vez no se pisan; la segunda recibe un 409."""
    h = shop["headers"]
    revision = (await _settings(client, shop))["hours"]["revision"]
    first = await client.patch(
        f"{BASE}/business-hours",
        headers=h(),
        json={"revision": revision, "days": {"mon": [{"open": "10:00", "close": "14:00"}]}},
    )
    assert first.status_code == 200, first.text
    second = await client.patch(
        f"{BASE}/business-hours",
        headers=h(),
        json={"revision": revision, "days": {"tue": [{"open": "10:00", "close": "14:00"}]}},
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == {"code": "revision_conflict", "revision": revision + 1}


async def test_the_hours_project_the_prompt_label(client, db_session, shop) -> None:
    """Spec 047 (T056, research D15): la etiqueta del prompt (``business_hours.label``)
    es la frase «Así lo dirá el agente» del horario que el negocio acaba de guardar."""
    import sqlalchemy as sa

    from nexus_api.db.models import Tenant

    closed = {d: [] for d in ("tue", "wed", "thu", "fri", "sat", "sun")}
    r = await client.patch(
        f"{BASE}/business-hours",
        headers=shop["headers"](),
        json={"revision": 0, "days": {"mon": [{"open": "10:00", "close": "19:00"}], **closed}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "Abrimos lunes de 10:00 a 19:00. Cerramos martes a domingo."
    db_session.expire_all()
    stored = await db_session.scalar(
        sa.select(Tenant.business_hours).where(Tenant.id == shop["tenant_id"])
    )
    assert stored["label"] == "Abrimos lunes de 10:00 a 19:00. Cerramos martes a domingo."
    assert stored["monday"] == [{"from": "10:00", "to": "19:00"}]


async def test_a_fifty_minute_service_changes_its_price_and_free_stays_free(
    client, db_session, shop
) -> None:
    """Historia 4, escenarios 2 y 3 (5.2, 5.3): «Gratis» se conserva, un servicio de
    50 minutos cambia de precio, y lo que no llega no cambia. Queda en el historial
    de la ficha, porque se escribe por su catálogo."""
    import sqlalchemy as sa

    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import BusinessChange

    h = shop["headers"]
    made = await client.post(
        f"{BASE}/services",
        headers=h(),
        json={"name": "Masaje", "duration_minutes": 50, "price": {"kind": "free"}},
    )
    assert made.status_code == 201, made.text
    svc = made.json()
    assert (svc["duration_minutes"], svc["price"], svc["currency"]) == (50, {"kind": "free"}, "CLP")
    url = f"{BASE}/services/{svc['id']}"

    kept = await client.patch(url, headers=h(), json={"category": "Cuerpo"})
    assert kept.status_code == 200, kept.text
    assert (kept.json()["price"], kept.json()["category"]) == ({"kind": "free"}, "Cuerpo")

    paid = await client.patch(
        url, headers=h(), json={"price": {"kind": "amount", "amount_minor": 20000}}
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["price"] == {"kind": "amount", "amount_minor": 20000}
    assert paid.json()["duration_minutes"] == 50

    free = await client.patch(url, headers=h(), json={"price": {"kind": "free"}})
    assert free.json()["price"] == {"kind": "free"}
    listed = (await client.get(f"{BASE}/services", headers=h())).json()["items"]
    assert next(s for s in listed if s["id"] == svc["id"])["price"] == {"kind": "free"}
    corte = next(s for s in listed if s["id"] == str(shop["corte"]))
    assert corte["price"] == {"kind": "amount", "amount_minor": 15000}

    async with tenant_scoped_session(db_session, shop["tenant_id"]):
        changes = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(BusinessChange)
            .where(BusinessChange.section == "services")
        )
    assert changes == 4


async def test_a_service_is_not_renamed_from_reservas(client, shop) -> None:
    """5.4: se crea con su nombre, pero no se renombra."""
    h = shop["headers"]
    url = f"{BASE}/services/{shop['corte']}"
    refused = await client.patch(url, headers=h(), json={"name": "Corte nuevo"})
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == {"code": "rename_not_allowed", "field": "name"}
    same = await client.patch(url, headers=h(), json={"name": " Corte ", "duration_minutes": 35})
    assert same.status_code == 200, same.text
    assert (same.json()["name"], same.json()["duration_minutes"]) == ("Corte", 35)


async def test_the_limits_of_a_service_are_the_ficha_ones(client, shop) -> None:
    """5.2 y 11.2: el importe hasta 10¹², la categoría hasta 40 y la duración de 5
    a 480 en pasos de 5, con el código que dice qué falla."""
    h = shop["headers"]
    url = f"{BASE}/services/{shop['corte']}"
    for body, code, field in (
        ({"price": {"kind": "amount", "amount_minor": 10**12 + 1}}, "amount_too_large", "price"),
        ({"price": {"kind": "amount"}}, "price_amount_required", "price"),
        ({"category": "x" * 41}, "category_too_long", "category"),
        ({"duration_minutes": 485}, "bad_duration", "duration_min"),
        ({"duration_minutes": 0}, "bad_duration", "duration_min"),
    ):
        r = await client.patch(url, headers=h(), json=body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["detail"] == {"code": code, "field": field}, body
    top = await client.patch(
        url,
        headers=h(),
        json={"price": {"kind": "amount", "amount_minor": 10**12}, "category": "c" * 40},
    )
    assert top.status_code == 200, top.text
    assert top.json()["price"] == {"kind": "amount", "amount_minor": 10**12}
    made = await client.post(
        f"{BASE}/services",
        headers=h(),
        json={"name": "Peinado", "duration_minutes": 5, "category": "y" * 41},
    )
    assert made.status_code == 422
    assert made.json()["detail"] == {"code": "category_too_long", "field": "category"}


async def test_a_staff_email_must_be_an_email(client, shop) -> None:
    """11.3: el correo de una persona del equipo tiene formato y 254 como mucho."""
    h = shop["headers"]
    for email in ("no-es-un-correo", "a" * 250 + "@x.co"):
        r = await client.post(f"{BASE}/staff", headers=h(), json={"name": "Nora", "email": email})
        assert r.status_code == 422, (email, r.text)
        patched = await client.patch(
            f"{BASE}/staff/{shop['marcos']}", headers=h(), json={"email": email}
        )
        assert patched.status_code == 422, (email, patched.text)
    ok = await client.post(
        f"{BASE}/staff", headers=h(), json={"name": "Nora", "email": "nora@cultor.cl"}
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["email"] == "nora@cultor.cl"
