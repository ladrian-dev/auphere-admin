"""Spec 043, requisito 14 — los datos que dejan reservar (enmienda del 2026-11-04).

Luis: «verificar que los datos de los servicios, equipo, que integrante del equipo hace
que y que todo este conectado correctamente». Lo que falla aquí no da un error: da un
cliente al que el agente no sabe atender. Por eso, además de negarse bien, se dice en
Ajustes antes de que pase.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Customer,
    ReservationService,
    ReservationServiceStaff,
    ReservationStaff,
)
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


async def _world(db_session: Any, console_world: dict[str, Any]) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()
    return {**shop, "ana": ana.id, "registry": _registry()}


async def _tool(world: dict[str, Any], name: str, args: dict[str, Any]) -> dict[str, Any]:
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(name, args, whitelist=[name])
    return dict(env["result"])


async def _service(
    world: dict[str, Any], *, minutes: int = 30, staff: list[uuid.UUID] | None = None
) -> uuid.UUID:
    """Un servicio para ``staff``; ``[]``, nadie; ``None``, todo el equipo."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, world["tenant_id"]):
        svc = ReservationService(
            tenant_id=world["tenant_id"],
            name="Masaje",
            duration_minutes=minutes,
            all_staff=staff is None,
            position=9,
        )
        session.add(svc)
        await session.flush()
        for sid in staff or []:
            session.add(
                ReservationServiceStaff(
                    tenant_id=world["tenant_id"], service_id=svc.id, staff_id=sid
                )
            )
        return svc.id


async def _archive_all(world: dict[str, Any]) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, world["tenant_id"]):
        await session.execute(sa.update(ReservationStaff).values(archived_at=sa.func.now()))


async def _services(client: Any, world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = (await client.get(f"{BASE}/services", headers=world["headers"]())).json()["items"]
    return {s["id"]: s for s in items}


async def _staff(client: Any, world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = (await client.get(f"{BASE}/staff", headers=world["headers"]())).json()["items"]
    return {s["id"]: s for s in items}


async def _slots(client: Any, world: dict[str, Any], **params: Any) -> list[str]:
    r = await client.get(
        f"{BASE}/slots",
        headers=world["headers"](),
        params={"date": future_day().isoformat(), **params},
    )
    assert r.status_code == 200, r.text
    return [s["time"] for s in r.json()["slots"]]


# ── 14.1 Un servicio que no hace nadie ──────────────────────────────────────


async def test_a_service_nobody_does_is_told_to_the_agent_and_to_the_business(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    orphan = await _service(world, staff=[])
    day = future_day().isoformat()

    # En Ajustes, antes de que un cliente lo pida.
    assert (await _services(client, world))[str(orphan)]["warnings"] == ["no_staff"]
    assert (await _services(client, world))[str(world["corte"])]["warnings"] == []

    # El agente lo sabe al listar, y no promete una hora.
    listed = await _tool(world, "reservas.services", {})
    item = next(s for s in listed["services"] if s["id"] == str(orphan))
    assert item["bookable"] is False
    assert item["why_not"] == "no_staff"

    found = await _tool(world, "reservas.find_slots", {"date": day, "service_id": str(orphan)})
    assert found["closed"] is True and found["why_closed"] == "no_staff"
    made = await _tool(
        world,
        "reservas.create",
        {"date": day, "time": "10:00", "service_id": str(orphan), "idempotency_key": "x"},
    )
    assert made["refused"] == "no_staff"

    # Y la consola dice por qué, no «ocupado».
    r = await client.post(
        f"{BASE}/bookings",
        headers=world["headers"](),
        json={
            "date": day,
            "time": "10:00",
            "service_id": str(orphan),
            "contact": {"name": "Ana", "phone": None},
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "no_staff"


async def test_a_team_with_nobody_left_is_the_same_as_nobody_doing_it(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    await _archive_all(world)
    assert (await _services(client, world))[str(world["corte"])]["warnings"] == ["no_staff"]
    found = await _tool(
        world,
        "reservas.find_slots",
        {"date": future_day().isoformat(), "service_id": str(world["corte"])},
    )
    assert found["why_closed"] == "no_staff"


# ── 14.2 Una duración que no cabe ───────────────────────────────────────────


async def test_a_duration_that_fits_nowhere_is_told_before_anyone_asks(
    client, db_session, console_world
) -> None:
    """Lucía trabaja hasta 5 h seguidas y 6 h después de comer; el negocio abre 12 h. Un
    servicio de 7 h cabe con Marcos, que usa el horario del negocio; solo con Lucía, no."""
    world = await _world(db_session, console_world)
    only_lucia = await _service(world, minutes=420, staff=[world["lucia"]])
    with_marcos = await _service(world, minutes=420, staff=[world["marcos"]])
    longest = await _service(world, minutes=480, staff=None)
    assert await _slots(client, world, service_id=str(only_lucia)) == []
    assert await _slots(client, world, service_id=str(with_marcos)) != []

    services = await _services(client, world)
    assert services[str(only_lucia)]["warnings"] == ["does_not_fit"]
    assert services[str(with_marcos)]["warnings"] == []
    assert services[str(longest)]["warnings"] == []

    r = await client.post(
        f"{BASE}/bookings",
        headers=world["headers"](),
        json={
            "date": future_day().isoformat(),
            "time": "09:00",
            "service_id": str(only_lucia),
            "contact": {"name": "Ana", "phone": None},
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "slot_taken"


# ── 14.3 El horario de cada uno ─────────────────────────────────────────────


async def test_someone_without_their_own_hours_works_the_hours_of_the_business(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    marcos = (await _staff(client, world))[str(world["marcos"])]
    assert marcos["hours"] is None
    assert marcos["effective_hours"] is not None
    assert marcos["warnings"] == []
    slots = await _slots(
        client, world, service_id=str(world["corte"]), staff_id=str(world["marcos"])
    )
    assert slots[0] == "09:00" and slots[-1] == "20:30"


async def test_a_week_with_no_hours_at_all_has_no_slots_and_is_told(
    client, db_session, console_world
) -> None:
    """Es distinto de no tener horario propio: esta persona no trabaja ningún día."""
    world = await _world(db_session, console_world)
    patched = await client.patch(
        f"{BASE}/staff/{world['marcos']}",
        headers=world["headers"](),
        json={"hours": {d: [] for d in WEEK}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["warnings"] == ["no_hours"]
    assert (
        await _slots(client, world, service_id=str(world["corte"]), staff_id=str(world["marcos"]))
        == []
    )
    # Y lo que solo hacía esa persona ya no lo hace nadie a ninguna hora.
    only_marcos = await _service(world, staff=[world["marcos"]])
    assert (await _services(client, world))[str(only_marcos)]["warnings"] == ["does_not_fit"]


async def test_hours_of_a_person_never_go_beyond_the_hours_of_the_business(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    patched = await client.patch(
        f"{BASE}/staff/{world['marcos']}",
        headers=world["headers"](),
        json={"hours": {d: [{"from": "07:00", "to": "10:00"}] for d in WEEK}},
    )
    assert patched.status_code == 200, patched.text
    assert await _slots(
        client, world, service_id=str(world["corte"]), staff_id=str(world["marcos"])
    ) == ["09:00", "09:30"]


async def test_the_break_between_two_stretches_is_not_offered(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    slots = await _slots(
        client, world, service_id=str(world["color"]), staff_id=str(world["lucia"])
    )
    # 90 min: la última que cabe antes de comer es 12:30; después, desde las 15:00.
    assert "12:30" in slots
    assert "13:00" not in slots and "14:00" not in slots
    assert "15:00" in slots
    assert slots[-1] == "19:30"


# ── 14.4 Quién hace qué ─────────────────────────────────────────────────────


async def test_a_service_for_some_only_gives_slots_of_those(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    svc = await _service(world, staff=[world["marcos"]])
    day = future_day().isoformat()

    free = (
        await client.get(
            f"{BASE}/slots",
            headers=world["headers"](),
            params={"date": day, "service_id": str(svc)},
        )
    ).json()["slots"]
    assert {sid for s in free for sid in s["staff_ids"]} == {str(world["marcos"])}
    assert await _slots(client, world, service_id=str(svc), staff_id=str(world["lucia"])) == []

    console = await client.post(
        f"{BASE}/bookings",
        headers=world["headers"](),
        json={
            "date": day,
            "time": "10:00",
            "staff_id": str(world["lucia"]),
            "service_id": str(svc),
            "contact": {"name": "Ana", "phone": None},
        },
    )
    assert console.status_code == 404

    agent = await _tool(
        world,
        "reservas.create",
        {
            "date": day,
            "time": "10:00",
            "staff_id": str(world["lucia"]),
            "service_id": str(svc),
            "idempotency_key": "other-one",
        },
    )
    assert agent["refused"] == "not_offered"

    # Sin decir con quién, le toca a quien lo hace.
    anyone = await _tool(
        world,
        "reservas.create",
        {"date": day, "time": "10:00", "service_id": str(svc), "idempotency_key": "whoever"},
    )
    assert anyone["booking"]["staff_name"] == "Marcos"


async def test_a_service_cannot_be_given_to_someone_archived(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    archived = await client.post(
        f"{BASE}/staff/{world['marcos']}/archive", headers=world["headers"]()
    )
    assert archived.status_code == 204, archived.text
    r = await client.post(
        f"{BASE}/services",
        headers=world["headers"](),
        json={"name": "Barba", "duration_minutes": 30, "staff_ids": [str(world["marcos"])]},
    )
    assert r.status_code == 404


# ── 14.5 Archivado ──────────────────────────────────────────────────────────


async def test_someone_archived_offers_nothing_and_counts_for_nothing(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    only_marcos = await _service(world, staff=[world["marcos"]])
    r = await client.post(f"{BASE}/staff/{world['marcos']}/archive", headers=world["headers"]())
    assert r.status_code == 204, r.text

    assert await _slots(client, world, service_id=str(only_marcos)) == []
    free = (
        await client.get(
            f"{BASE}/slots",
            headers=world["headers"](),
            params={"date": future_day().isoformat(), "service_id": str(world["corte"])},
        )
    ).json()["slots"]
    assert str(world["marcos"]) not in {sid for s in free for sid in s["staff_ids"]}
    assert (await _services(client, world))[str(only_marcos)]["warnings"] == ["no_staff"]


async def test_someone_with_future_bookings_cannot_be_archived(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    made = await client.post(
        f"{BASE}/bookings",
        headers=world["headers"](),
        json={
            "date": future_day().isoformat(),
            "time": "10:00",
            "staff_id": str(world["marcos"]),
            "service_id": str(world["corte"]),
            "contact": {"name": "Ana", "phone": None},
        },
    )
    assert made.status_code == 201, made.text
    r = await client.post(f"{BASE}/staff/{world['marcos']}/archive", headers=world["headers"]())
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "live_reservations", "count": 1}


# ── 14.6 Las fechas especiales mandan ───────────────────────────────────────


async def test_a_closed_special_date_gives_no_slots_to_anyone(
    client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    day = future_day()
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, world["tenant_id"]):
        await session.execute(
            sa.text(
                "INSERT INTO business_special_dates (tenant_id, name, date_from, date_to) "
                "VALUES (:t, 'Festivo', :d, :d)"
            ),
            {"t": world["tenant_id"], "d": day},
        )
    r = await client.get(
        f"{BASE}/slots",
        headers=world["headers"](),
        params={"date": day.isoformat(), "service_id": str(world["corte"])},
    )
    assert r.json()["closed"] is True and r.json()["slots"] == []
    found = await _tool(
        world,
        "reservas.find_slots",
        {"date": day.isoformat(), "service_id": str(world["corte"])},
    )
    assert found["closed"] is True and found["slots"] == []
    made = await _tool(
        world,
        "reservas.create",
        {
            "date": day.isoformat(),
            "time": "10:00",
            "service_id": str(world["corte"]),
            "idempotency_key": "festivo",
        },
    )
    assert made["refused"] == "slot_taken"


async def test_a_service_stays_editable_after_archiving_someone_on_its_list(
    client, db_session, console_world
) -> None:
    """Revisión, punto 15: la lista traía a la persona archivada, y al guardarla, un 404."""
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    made = await client.post(
        "/console/lite/reservas/services",
        headers=shop["headers"](),
        json={
            "name": "Tinte",
            "duration_minutes": 60,
            "staff_ids": [str(shop["lucia"]), str(shop["marcos"])],
        },
    )
    assert made.status_code == 201, made.text
    service = made.json()

    archived = await client.post(
        f"/console/lite/reservas/staff/{shop['marcos']}/archive", headers=shop["headers"]()
    )
    assert archived.status_code == 204, archived.text

    listed = await client.get("/console/lite/reservas/services", headers=shop["headers"]())
    found = next(s for s in listed.json()["items"] if s["id"] == service["id"])
    assert found["staff_ids"] == [str(shop["lucia"])]
    # Desde Reservas un servicio no se renombra (spec 056, requisito 5): se guarda la
    # lista que trajo, con otra duración, y eso es lo que antes daba el 404.
    saved = await client.patch(
        f"/console/lite/reservas/services/{service['id']}",
        headers=shop["headers"](),
        json={"name": "Tinte", "duration_minutes": 90, "staff_ids": found["staff_ids"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["staff_ids"] == [str(shop["lucia"])]

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        left = await session.scalar(
            sa.select(sa.func.count())
            .select_from(ReservationServiceStaff)
            .where(ReservationServiceStaff.staff_id == shop["marcos"])
        )
    assert left == 0


async def test_the_business_card_does_not_take_someone_archived(db_session, console_world) -> None:
    """Revisión, punto 15: la ficha del negocio escribe la misma lista por otra puerta."""
    from nexus_api.core.tenant_context import tenant_context
    from nexus_api.services.business.services_catalog import ServiceError, _set_staff

    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        await session.execute(
            sa.update(ReservationStaff)
            .where(ReservationStaff.id == shop["marcos"])
            .values(archived_at=sa.func.now())
        )
        service = await session.get(ReservationService, shop["corte"])
        assert service is not None
        with tenant_context(w["tenant_id"]), pytest.raises(ServiceError) as caught:
            await _set_staff(session, service, [shop["marcos"]])
        assert caught.value.code == "unknown_staff"
