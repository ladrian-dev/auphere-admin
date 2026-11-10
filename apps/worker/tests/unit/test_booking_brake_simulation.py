"""Fallo ``el-freno-no-reconoce-la-agenda-simulada`` — spec 056, requisito 1.

El freno de citas decide con los sobres del turno (``booking_brake.backs``), con la
forma de las herramientas de verdad: ``reservas.create`` respalda con ``booking``
y sin ``refused``. La agenda simulada del Playground y de las pruebas del agente
contestaba con una forma suya (``booking_id``, ``when``, ``service``), así que
toda reserva simulada parecía no hecha: «te reservé» se paraba, se reintentaba y
acababa en «Voy a pasar tu consulta a una persona del equipo…».

Aquí los sobres los produce el propio registro simulado, por el mismo camino que
el grafo (``pipeline._dispatch_tool``), y no un diccionario escrito a mano: si la
simulación o la herramienta de verdad cambian de forma, esto se pone en rojo.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from nexus_api.core.tenant_context import tenant_context
from nexus_mcp import MCPRegistry
from nexus_mcp.base import OutputModel
from nexus_mcp.servers.reservas.tools import RESERVAS_TOOLS

from nexus_worker.runtime import booking_brake
from nexus_worker.runtime.llm import ToolCall
from nexus_worker.runtime.pipeline import _dispatch_tool
from nexus_worker.simulation.registry import SimulatedRegistry
from nexus_worker.simulation.world import SimService, World

pytestmark = pytest.mark.asyncio

#: Lunes 9 de noviembre de 2026, 09:00 en Madrid; abre todos los días de 10 a 20.
NOW = "2026-11-09T08:00:00+00:00"
OPEN = [[[600, 1200]] for _ in range(7)]
TUESDAY = "2026-11-10"
AGENDA = (
    "reservas.find_slots",
    "reservas.join_waitlist",
    "reservas.create",
    "reservas.reschedule",
    "reservas.cancel",
    "reservas.list_mine",
    "reservas.confirm_attendance",
    "reservas.answer_offer",
    "booking.create_appointment",
    "booking.modify_appointment",
)
#: La salida que declara cada herramienta de Reservas de verdad.
REAL_OUTPUT: dict[str, type[OutputModel]] = {t.name: t.output_model for t in RESERVAS_TOOLS}


@pytest.fixture(autouse=True)
def tenant() -> Iterator[uuid.UUID]:
    with tenant_context(uuid.uuid4()) as tenant_id:
        yield tenant_id


#: Un servicio de una hora: cambiarlo media hora lo solapa consigo mismo.
LONG = SimService(id=str(uuid.uuid4()), name="Color", duration_min=60, bookable=True)


def _registry(
    *, week: list[list[list[int]]] | None = OPEN, services: list[SimService] | None = None
) -> SimulatedRegistry:
    world = World(timezone="Europe/Madrid", now=NOW, week=week, services=services or [LONG])
    return SimulatedRegistry(world, base=MCPRegistry())


async def _call(registry: SimulatedRegistry, name: str, **args: Any) -> dict[str, Any]:
    """El sobre que ve el freno: el del grafo, que convierte un ``ToolError`` en
    ``status: error``."""
    return await _dispatch_tool(
        registry, ToolCall(id="c", name=name, arguments=args), AGENDA, "book"
    )


def _is_the_real_shape(envelope: dict[str, Any]) -> None:
    result = {k: v for k, v in envelope["result"].items() if k != "simulated"}
    # ``extra="forbid"``: una clave de más o de menos no valida.
    REAL_OUTPUT[envelope["tool"]].model_validate(result)
    assert envelope["result"]["simulated"] is True


async def _book(
    registry: SimulatedRegistry, time: str = "10:00", *, day: str = TUESDAY, key: str = ""
) -> dict[str, Any]:
    return await _call(
        registry, "reservas.create", date=day, time=time, idempotency_key=key or f"k-{time}"
    )


async def test_a_simulated_booking_backs_the_reply_with_the_real_shape() -> None:
    registry = _registry()
    envelope = await _book(registry)

    assert envelope["status"] == "ok"
    _is_the_real_shape(envelope)
    booking = envelope["result"]["booking"]
    assert (booking["date"], booking["start"], booking["end"]) == (TUESDAY, "10:00", "10:30")
    assert envelope["result"]["refused"] is None
    assert booking_brake.backs(envelope)
    assert not booking_brake.attempted([envelope])
    assert [a.tool for a in registry.world.actions] == ["reservas.create"]


async def test_the_brake_lets_a_simulated_booking_leave_without_asking_the_classifier() -> None:
    """Escenario 3 de la historia 1: una reserva hecha en este turno sale sin
    llamadas. En el Playground también."""
    registry = _registry()
    envelope = await _book(registry)

    class NoClassifier:
        async def classify(self, **_kw: Any) -> str:
            raise AssertionError("a booked reply never reaches the classifier")

    turn = booking_brake.BrakeTurn(uuid.uuid4(), None, None, None)
    claimed = await booking_brake.unbacked_claim(
        NoClassifier(),  # type: ignore[arg-type]
        None,
        turn,
        text="Listo, te reservé el martes a las 10:00.",
        envelopes=[envelope],
        simulated_agenda=registry.simulated_booking_stands(),
    )
    assert claimed is False


async def test_a_simulated_refusal_does_not_back_and_counts_as_a_failed_attempt() -> None:
    registry = _registry()
    taken = await _book(registry)
    again = await _book(registry, key="otra")  # el mismo hueco, ya ocupado

    assert booking_brake.backs(taken)
    assert again["status"] == "ok", "como la de verdad: rechaza con status ok"
    _is_the_real_shape(again)
    assert again["result"]["booking"] is None
    assert again["result"]["refused"] == "slot_taken"
    assert again["result"]["first_fit"] == "10:30"
    assert not booking_brake.backs(again)
    assert booking_brake.attempted([again])

    night = await _book(registry, "21:00")
    assert night["result"]["refused"] == "slot_taken" and not booking_brake.backs(night)
    assert night["result"]["first_fit"] is None
    past = await _book(registry, "08:00", day="2026-11-09")
    assert past["result"]["refused"] == "too_soon" and not booking_brake.backs(past)

    no_hours = await _book(_registry(week=None))
    assert no_hours["result"]["refused"] == "hours_missing"
    assert not booking_brake.backs(no_hours)


async def test_the_same_idempotency_key_gives_back_the_same_booking() -> None:
    """Como ``reservas.create`` de verdad: repetir la clave no rechaza su propia
    reserva por ocupada, la devuelve (``idempotent_replay``) y respalda."""
    registry = _registry()
    first = await _book(registry)
    replay = await _book(registry)

    _is_the_real_shape(replay)
    assert replay["result"]["idempotent_replay"] is True
    assert replay["result"]["booking"]["id"] == first["result"]["booking"]["id"]
    assert booking_brake.backs(replay)
    assert len(registry.world.bookings) == 1 and len(registry.world.actions) == 1


async def test_what_the_real_tool_rejects_is_an_error() -> None:
    registry = _registry()
    bad = await _call(registry, "reservas.create", date="mañana", time="10", idempotency_key="k")
    assert bad["status"] == "error" and not booking_brake.backs(bad)
    assert booking_brake.attempted([bad])

    unknown = await _call(
        registry, "reservas.reschedule", booking_id=str(uuid.uuid4()), date=TUESDAY, time="11:00"
    )
    assert unknown["status"] == "error" and not booking_brake.backs(unknown)


async def test_a_simulated_reschedule_backs_and_moves_the_same_booking() -> None:
    registry = _registry()
    made = await _call(
        registry,
        "reservas.create",
        date=TUESDAY,
        time="10:00",
        service_id=LONG.id,
        idempotency_key="k-color",
    )
    booking_id = made["result"]["booking"]["id"]
    assert made["result"]["booking"]["end"] == "11:00"

    moved = await _call(
        registry, "reservas.reschedule", booking_id=booking_id, date=TUESDAY, time="10:30"
    )
    assert moved["status"] == "ok"
    _is_the_real_shape(moved)
    assert moved["result"]["booking"]["id"] == booking_id
    assert moved["result"]["booking"]["start"] == "10:30", "su propio hueco no la estorba"
    assert booking_brake.backs(moved)
    assert [b.status for b in registry.world.bookings] == ["confirmed"]

    await _book(registry, "12:00")
    clash = await _call(
        registry, "reservas.reschedule", booking_id=booking_id, date=TUESDAY, time="12:00"
    )
    _is_the_real_shape(clash)
    assert clash["result"]["refused"] == "slot_taken" and not booking_brake.backs(clash)


async def test_a_booking_that_stands_backs_and_a_cancelled_one_does_not() -> None:
    registry = _registry()
    booking_id = (await _book(registry))["result"]["booking"]["id"]

    mine = await _call(registry, "reservas.list_mine")
    _is_the_real_shape(mine)
    assert booking_brake.backs(mine)
    kept = await _call(registry, "reservas.confirm_attendance", attending=True)
    _is_the_real_shape(kept)
    assert booking_brake.backs(kept)

    cancelled = await _call(registry, "reservas.cancel", booking_id=booking_id)
    _is_the_real_shape(cancelled)
    assert not booking_brake.backs(cancelled)
    assert not registry.simulated_booking_stands()

    empty = await _call(registry, "reservas.list_mine")
    assert empty["result"]["bookings"] == [] and not booking_brake.backs(empty)
    nothing_to_confirm = await _call(registry, "reservas.confirm_attendance", attending=True)
    assert nothing_to_confirm["status"] == "error"
    assert not booking_brake.backs(nothing_to_confirm)


async def test_without_a_waitlist_an_offer_answer_never_books() -> None:
    answer = await _call(_registry(), "reservas.answer_offer", accept=True)
    _is_the_real_shape(answer)
    assert answer["result"]["result"] == "no_offer"
    assert not booking_brake.backs(answer)


async def test_a_retired_booking_tool_fails_with_an_error_as_the_real_one() -> None:
    """Las ``booking.*`` respaldan con ``status: ok``: un rechazo con ese estado
    habría dejado salir una cita que no se hizo."""
    registry = _registry()
    starts_at = f"{TUESDAY}T10:00:00+01:00"
    made = await _call(
        registry, "booking.create_appointment", starts_at=starts_at, service_name="Corte"
    )
    assert made["status"] == "ok" and booking_brake.backs(made)

    taken = await _call(
        registry, "booking.create_appointment", starts_at=starts_at, service_name="Corte"
    )
    assert taken["status"] == "error", taken
    assert not booking_brake.backs(taken) and booking_brake.attempted([taken])


async def test_a_booking_of_an_earlier_turn_backs_the_next_reply() -> None:
    """Segundo turno del Playground: «te esperamos el martes» sin herramientas. Su
    reserva está en la agenda simulada y no en ``reservations``."""
    registry = _registry()
    await _book(registry)
    assert registry.simulated_booking_stands()
    assert not MCPRegistry().simulated_booking_stands(), "fuera de la simulación manda la base"

    class NoClassifier:
        async def classify(self, **_kw: Any) -> str:
            raise AssertionError("a booking that stands never reaches the classifier")

    turn = booking_brake.BrakeTurn(uuid.uuid4(), None, None, None)
    claimed = await booking_brake.unbacked_claim(
        NoClassifier(),  # type: ignore[arg-type]
        None,
        turn,
        text="Perfecto, te esperamos el martes a las 10:00.",
        envelopes=[],
        simulated_agenda=registry.simulated_booking_stands(),
    )
    assert claimed is False


# ── fallo ``la-reserva-del-turno-siguiente-pierde-los-ids`` ──────────────────
#
# En el turno siguiente el modelo no tiene los ids: reserva con el nombre que dijo el
# cliente. La agenda simulada acepta los mismos campos que la de verdad y contesta
# con sus mismos códigos y su misma forma, también al buscar huecos y al apuntarse a
# la espera, para que el Playground enseñe lo que pasaría en el canal.

#: Para empatar con «cor»: «Corte» y «Corte niño».
CUT = SimService(id=str(uuid.uuid4()), name="Corte", duration_min=30, bookable=True)
KID = SimService(id=str(uuid.uuid4()), name="Corte niño", duration_min=30, bookable=True)


async def test_a_simulated_booking_by_name_books_that_service() -> None:
    registry = _registry()
    envelope = await _call(
        registry,
        "reservas.create",
        date=TUESDAY,
        time="10:00",
        service_name="  COLOR ",
        staff_name="Lucía",  # la agenda simulada no tiene equipo: no lo comprueba
        idempotency_key="k",
    )
    _is_the_real_shape(envelope)
    booking = envelope["result"]["booking"]
    assert (booking["service_name"], booking["end"]) == ("Color", "11:00")
    assert booking_brake.backs(envelope)


async def test_an_unknown_simulated_service_is_refused_with_the_options() -> None:
    registry = _registry()
    for args in ({"service_name": "Masaje"}, {"service_id": str(uuid.uuid4())}):
        made = await _call(
            registry, "reservas.create", date=TUESDAY, time="10:00", idempotency_key="k", **args
        )
        assert made["status"] == "ok", "como la de verdad: un rechazo, no un error"
        _is_the_real_shape(made)
        assert made["result"]["refused"] == "unknown_service"
        assert made["result"]["services"] == [{"id": LONG.id, "name": "Color"}]
        assert not booking_brake.backs(made) and booking_brake.attempted([made])

        found = await _call(registry, "reservas.find_slots", date=TUESDAY, **args)
        _is_the_real_shape(found)
        assert found["result"]["refused"] == "unknown_service"
        assert found["result"]["slots"] == []

        waiting = await _call(registry, "reservas.join_waitlist", date=TUESDAY, **args)
        _is_the_real_shape(waiting)
        assert waiting["result"]["refused"] == "unknown_service"
        assert waiting["result"]["entry_id"] is None
    assert registry.world.bookings == [] and registry.world.actions == []


async def test_a_simulated_name_that_fits_several_is_ambiguous() -> None:
    registry = _registry(services=[CUT, KID])
    made = await _call(
        registry,
        "reservas.create",
        date=TUESDAY,
        time="10:00",
        service_name="cor",
        idempotency_key="k",
    )
    _is_the_real_shape(made)
    assert made["result"]["refused"] == "ambiguous_service"
    assert {o["name"] for o in made["result"]["services"]} == {"Corte", "Corte niño"}
    exact = await _call(
        registry,
        "reservas.create",
        date=TUESDAY,
        time="10:00",
        service_name="corte",
        idempotency_key="k2",
    )
    assert exact["result"]["booking"]["service_name"] == "Corte"


async def test_simulated_slots_and_waitlist_have_the_real_shape() -> None:
    registry = _registry()
    found = await _call(registry, "reservas.find_slots", date=TUESDAY, service_name="color")
    assert found["status"] == "ok"
    _is_the_real_shape(found)
    assert found["result"]["refused"] is None and found["result"]["closed"] is False
    times = [s["time"] for s in found["result"]["slots"]]
    assert times[0] == "10:00" and "19:30" not in times, "una hora de Color no cabe a las 19:30"

    closed = await _call(_registry(week=None), "reservas.find_slots", date=TUESDAY)
    _is_the_real_shape(closed)
    assert closed["result"]["closed"] is True and closed["result"]["slots"] == []

    waiting = await _call(registry, "reservas.join_waitlist", date=TUESDAY, service_name="Color")
    _is_the_real_shape(waiting)
    assert waiting["result"]["status"] == "waiting" and waiting["result"]["entry_id"]
    assert [a.tool for a in registry.world.actions] == ["reservas.join_waitlist"]
