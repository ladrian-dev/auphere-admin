"""Fallo ``la-reserva-del-turno-siguiente-pierde-los-ids`` — spec 043, requisito 6.

Por WhatsApp se reserva en varios mensajes: el cliente pregunta por huecos en uno
y elige la hora en el siguiente. Entre turnos el agente solo conserva el texto, y
la nota de lo que hizo con sus herramientas no lleva argumentos ni resultados, así
que en el segundo turno ``service_id`` y ``staff_id`` ya no están. En staging el
modelo llamó a ``reservas.create`` con lo que tenía y el agente le dijo al cliente
«Ese horario ya no está disponible» con la hora libre.

Ahora las herramientas aceptan también el nombre (``service_name`` /
``staff_name``) y lo resuelven contra lo que **este agente** ofrece y el equipo
activo que hace el servicio. Lo que no se resuelve no es un error ni «ocupado»: es
``unknown_*`` o ``ambiguous_*`` con las opciones, para reintentar en el mismo turno.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    Customer,
    Reservation,
    ReservationService,
    ReservationServiceStaff,
    ReservationStaff,
    ReservationWaitlist,
)
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TOOLS = (
    "reservas.find_slots",
    "reservas.create",
    "reservas.reschedule",
    "reservas.join_waitlist",
)


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


async def _world(db_session: Any, console_world: dict[str, Any]) -> dict[str, Any]:
    """Corte y Color (Color solo lo hace Lucía), Lucía y Marcos, y Ana."""
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w["tenant_id"]):
        color = await s.get(ReservationService, shop["color"])
        assert color is not None
        color.all_staff = False
        s.add(
            ReservationServiceStaff(
                tenant_id=w["tenant_id"], service_id=shop["color"], staff_id=shop["lucia"]
            )
        )
        await s.commit()
    return {**shop, "ana": ana.id, "registry": _registry(), "day": future_day()}


async def _crowd(world: dict[str, Any]) -> dict[str, uuid.UUID]:
    """Para empatar: «Corte niño» junto a «Corte» y «Lucas» junto a «Lucía»."""
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world["tenant_id"]):
        kid = ReservationService(
            tenant_id=world["tenant_id"], name="Corte niño", duration_minutes=30, currency="CLP"
        )
        lucas = ReservationStaff(tenant_id=world["tenant_id"], name="Lucas", position=3)
        s.add_all([kid, lucas])
        await s.commit()
        return {"kid": kid.id, "lucas": lucas.id}


async def _tool(world: dict[str, Any], name: str, args: dict[str, Any]) -> dict[str, Any]:
    """El sobre de la herramienta de verdad. Un ``ToolError`` sube: ninguna de estas
    llamadas debe acabar en uno."""
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(name, args, whitelist=list(TOOLS))
    assert env["status"] == "ok", env
    return dict(env["result"])


def _slots(world: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"date": world["day"].isoformat(), **kw}


def _book(world: dict[str, Any], key: str, time: str = "10:00", **kw: Any) -> dict[str, Any]:
    return {"date": world["day"].isoformat(), "time": time, "idempotency_key": key, **kw}


def _ids(options: list[dict[str, Any]]) -> set[str]:
    return {o["id"] for o in options}


async def _rows(world: dict[str, Any]) -> list[Reservation]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world["tenant_id"]):
        rows = list((await s.execute(sa.select(Reservation))).scalars().all())
        for r in rows:
            s.expunge(r)
        return rows


# ── por nombre ──────────────────────────────────────────────────────────────


async def test_find_slots_by_name_gives_the_same_times_as_by_id(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    by_id = await _tool(
        world,
        "reservas.find_slots",
        _slots(world, service_id=str(world["corte"]), staff_id=str(world["lucia"])),
    )
    # Mayúsculas, sin la tilde y con espacios de más: lo que escribe un cliente.
    by_name = await _tool(
        world, "reservas.find_slots", _slots(world, service_name="  CORTE ", staff_name="lucia")
    )
    assert by_name["refused"] is None
    assert by_name["slots"] and by_name["slots"] == by_id["slots"]
    assert {s["id"] for slot in by_name["slots"] for s in slot["staff"]} == {str(world["lucia"])}


async def test_create_with_only_the_names_books_that_service_with_that_person(
    db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    out = await _tool(
        world, "reservas.create", _book(world, "nombre", service_name="Corte", staff_name="LUCÍA")
    )
    assert out["refused"] is None
    assert (out["booking"]["service_name"], out["booking"]["staff_name"]) == ("Corte", "Lucía")
    [row] = await _rows(world)
    assert (row.service_id, row.staff_id) == (world["corte"], world["lucia"])


async def test_a_unique_prefix_is_enough(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    out = await _tool(
        world, "reservas.create", _book(world, "prefijo", service_name="col", staff_name="Lu")
    )
    assert out["refused"] is None, out
    [row] = await _rows(world)
    assert (row.service_id, row.staff_id) == (world["color"], world["lucia"])


async def test_the_id_still_wins_over_the_name(db_session, console_world) -> None:
    """Con el id, todo como antes: el nombre no lo pisa."""
    world = await _world(db_session, console_world)
    out = await _tool(
        world,
        "reservas.create",
        _book(world, "id", service_id=str(world["corte"]), service_name="Color"),
    )
    assert out["booking"]["service_name"] == "Corte"


# ── lo que no se resuelve: un rechazo con opciones, nunca un error ──────────


async def test_an_unknown_service_is_refused_with_the_options(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    offered = {str(world["corte"]), str(world["color"])}
    for args in (
        {"service_name": "Masaje"},
        {"service_id": str(uuid.uuid4())},  # un id inventado
        {},  # sin servicio: antes un 422 ``service_required``
    ):
        made = await _tool(world, "reservas.create", _book(world, f"k{len(args)}", **args))
        assert made["refused"] == "unknown_service", (args, made)
        assert made["booking"] is None
        assert _ids(made["services"]) == offered
        assert {o["name"] for o in made["services"]} == {"Corte", "Color"}

        found = await _tool(world, "reservas.find_slots", _slots(world, **args))
        assert found["refused"] == "unknown_service", (args, found)
        assert found["slots"] == [] and found["closed"] is False
        assert _ids(found["services"]) == offered
    assert await _rows(world) == []


async def test_an_unknown_person_is_refused_with_who_does_the_service(
    db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    for args in ({"staff_name": "Pedro"}, {"staff_id": str(uuid.uuid4())}):
        made = await _tool(
            world, "reservas.create", _book(world, "p", service_name="Corte", **args)
        )
        assert made["refused"] == "unknown_staff", (args, made)
        assert _ids(made["staff"]) == {str(world["lucia"]), str(world["marcos"])}

        found = await _tool(
            world, "reservas.find_slots", _slots(world, service_name="Corte", **args)
        )
        assert found["refused"] == "unknown_staff", (args, found)
        assert found["slots"] == []
    # Color solo lo hace Lucía: las opciones son las de ese servicio.
    color = await _tool(
        world, "reservas.create", _book(world, "c", service_name="Color", staff_name="Pedro")
    )
    assert color["refused"] == "unknown_staff"
    assert _ids(color["staff"]) == {str(world["lucia"])}
    assert await _rows(world) == []


async def test_a_name_that_fits_several_is_ambiguous(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    more = await _crowd(world)
    service = await _tool(world, "reservas.create", _book(world, "a", service_name="cor"))
    assert service["refused"] == "ambiguous_service"
    assert _ids(service["services"]) == {str(world["corte"]), str(more["kid"])}

    staff = await _tool(
        world, "reservas.find_slots", _slots(world, service_name="corte", staff_name="luc")
    )
    assert staff["refused"] == "ambiguous_staff"
    assert _ids(staff["staff"]) == {str(world["lucia"]), str(more["lucas"])}

    # El nombre exacto desempata: «Corte» es Corte, aunque exista «Corte niño».
    exact = await _tool(world, "reservas.create", _book(world, "e", service_name="corte"))
    assert exact["booking"]["service_name"] == "Corte"


async def test_a_person_who_does_not_do_the_service_is_not_offered(
    db_session, console_world
) -> None:
    """R14.4: Marcos no hace Color. Por nombre, como por id: ``not_offered``, y quien
    sí lo hace, para ofrecerlo."""
    world = await _world(db_session, console_world)
    for args in ({"staff_name": "Marcos"}, {"staff_id": str(world["marcos"])}):
        made = await _tool(
            world, "reservas.create", _book(world, "m", service_name="Color", **args)
        )
        assert made["refused"] == "not_offered", (args, made)
        assert _ids(made["staff"]) == {str(world["lucia"])}
    assert await _rows(world) == []


# ── mover y apuntarse a la espera ───────────────────────────────────────────


async def test_reschedule_takes_the_persons_name(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    made = await _tool(
        world, "reservas.create", _book(world, "r", service_name="Corte", staff_name="Lucía")
    )
    booking_id = made["booking"]["id"]
    moved = await _tool(
        world,
        "reservas.reschedule",
        {
            "booking_id": booking_id,
            "date": world["day"].isoformat(),
            "time": "11:00",
            "staff_name": "marcos",
        },
    )
    assert moved["refused"] is None, moved
    assert (moved["booking"]["start"], moved["booking"]["staff_name"]) == ("11:00", "Marcos")

    ghost = await _tool(
        world,
        "reservas.reschedule",
        {
            "booking_id": booking_id,
            "date": world["day"].isoformat(),
            "time": "12:00",
            "staff_name": "Pedro",
        },
    )
    assert ghost["refused"] == "unknown_staff" and ghost["booking"] is None
    assert _ids(ghost["staff"]) == {str(world["lucia"]), str(world["marcos"])}
    [row] = await _rows(world)
    assert row.staff_id == world["marcos"], "el rechazo no movió nada"


async def test_join_waitlist_takes_the_names(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    joined = await _tool(
        world,
        "reservas.join_waitlist",
        {"service_name": "corte", "staff_name": "lucía", "date": world["day"].isoformat()},
    )
    assert joined["refused"] is None and joined["status"] == "waiting"
    unknown = await _tool(
        world,
        "reservas.join_waitlist",
        {"service_name": "Masaje", "date": world["day"].isoformat()},
    )
    assert unknown["refused"] == "unknown_service" and unknown["entry_id"] is None
    assert _ids(unknown["services"]) == {str(world["corte"]), str(world["color"])}
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world["tenant_id"]):
        rows = list((await s.execute(sa.select(ReservationWaitlist))).scalars().all())
    assert [(r.service_id, r.staff_id) for r in rows] == [(world["corte"], world["lucia"])]


# ── el turno de verdad: el segundo mensaje reserva sin los ids ──────────────


async def test_the_next_turn_books_with_the_names_without_the_ids(
    db_session, console_world, monkeypatch
) -> None:
    """El caso de staging, por el despachador, el grafo y el servidor MCP de verdad.
    Turno 1: el modelo busca huecos con los ids (los tenía de ``reservas.services``)
    y ofrece horas. Turno 2: «A las 10». El modelo no ve los ids —el historial solo
    trae el texto— y reserva con los nombres que dijo el cliente."""
    from langgraph.checkpoint.memory import MemorySaver
    from nexus_worker.runtime.agent_loader import AgentLoader
    from nexus_worker.runtime.booking_brake import CLASSIFY_PROMPT
    from nexus_worker.runtime.dispatcher import process_inbound
    from nexus_worker.runtime.llm import InMemoryProvider, LLMCall, LLMRouter, ToolCall
    from nexus_worker.runtime.pipeline import build_pipeline

    from tests.integration._turn_world import (
        conversation_of,
        make_world,
        outbound_rows,
        wallet_closed,
    )

    wallet_closed(monkeypatch, closed=False)  # el cliente del partner tiene saldo
    world = await _world(db_session, console_world)
    turn = await make_world(db_session, tenant_id=world["tenant_id"])
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world["tenant_id"]):
        await s.execute(
            sa.update(AgentConfig)
            .where(AgentConfig.agent_id == turn.agent_id)
            .values(tools=["reservas.services", "reservas.find_slots", "reservas.create"])
        )
        await s.commit()
    day = world["day"].isoformat()
    offer = "El jueves tengo libre a las 10:00 y a las 10:30 con Lucía. ¿Cuál prefieres?"
    done = "Listo, te reservé a las 10:00 con Lucía."
    secret = {str(world["corte"]), str(world["lucia"])}
    seen_in_turn_two: list[str] = []

    def _last_user(call: LLMCall) -> str:
        return next(
            (str(m.get("content")) for m in reversed(call.messages) if m.get("role") == "user"),
            "",
        )

    def _tool_seen(call: LLMCall) -> bool:
        return any(m.get("role") == "tool" for m in call.messages)

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if call.role != "book" or _tool_seen(call):
            return []
        if "A las 10" in _last_user(call):
            seen_in_turn_two.append("\n".join(str(m.get("content")) for m in call.messages))
            return [
                ToolCall(
                    id="c2",
                    name="reservas.create",
                    arguments={
                        "date": day,
                        "time": "10:00",
                        "service_name": "corte",
                        "staff_name": "Lucía",
                        "idempotency_key": f"reserva:{day}:10:00",
                    },
                )
            ]
        return [
            ToolCall(
                id="c1",
                name="reservas.find_slots",
                arguments={
                    "date": day,
                    "service_id": str(world["corte"]),
                    "staff_id": str(world["lucia"]),
                },
            )
        ]

    def responder(call: LLMCall) -> str:
        if call.role == "classify":
            system = "\n".join(str(m.get("content")) for m in call.messages)
            return "YES" if CLASSIFY_PROMPT in system else "book"
        if not _tool_seen(call):
            return ""
        return done if "A las 10" in _last_user(call) else offer

    router = LLMRouter(
        provider=InMemoryProvider(responder=responder, tool_caller=tool_caller),
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
    )
    pipeline = build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
        mcp_registry=world["registry"],
        use_ucm_formatter=False,
    )

    first = await process_inbound(
        turn.event("¿Tienes hora el jueves para un corte con Lucía?"), pipeline=pipeline
    )
    assert first["response"] == offer, first
    second = await process_inbound(turn.event("A las 10"), pipeline=pipeline)

    [prompt] = seen_in_turn_two
    assert not any(s in prompt for s in secret), "el turno 2 no tiene los ids del turno 1"
    assert second["response"] == done, second
    assert [m.content for m in await outbound_rows(turn)] == [offer, done]
    conv = await conversation_of(turn)
    [row] = await _rows(world)
    assert (row.service_id, row.staff_id) == (world["corte"], world["lucia"])
    assert (row.origin, row.conversation_id, row.agent_id) == ("agent", conv.id, turn.agent_id)
