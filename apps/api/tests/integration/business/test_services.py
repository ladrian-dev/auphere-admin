"""Spec 047, T053 — los servicios y quién los ofrece (requisito 11, historia 6).

Los servicios de la ficha son los de Reservas (``reservation_services``, research
D16), con lo que la ficha necesita: descripción, servicios no reservables (sin
duración) y el tipo de precio. Quién los ofrece:

- un agente «Atiende todos los servicios» o tiene una lista (``agent_services``);
- un servicio «Para todos los agentes» lo conocen solo los marcados «Atiende
  todos» (11.3), y cada servicio dice qué agentes lo usan (11.2);
- las herramientas de servicios y de Reservas devuelven solo los servicios del
  agente del turno, el del número de la conversación (11.4, garantía 9).

Y además: eliminar es archivar y las reservas pasadas conservan el nombre (11.5),
duplicar (11.6) y los precios con los decimales de su moneda (11.7).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    ClientAccess,
    Conversation,
    ConversationStatus,
    Customer,
    Reservation,
    ReservationService,
    ReservationSettings,
    ReservationStaff,
)
from nexus_api.services.business import services_catalog
from nexus_api.services.reservations.settings import apply_defaults
from tests.conftest import future_day

from ._business_world import Biz, active_prompt, biz, new_business, read, seed_agent, shifts, write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

__all__ = ["biz"]

EVERY_DAY = {
    d: shifts(("09:00", "20:00")) for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
}


async def _service(client: Any, biz: Biz, body: dict[str, Any], revision: int) -> dict[str, Any]:
    return await write(client, biz, "POST", "/services", body, revision=revision, expect=201)


CORTE = {
    "name": "Corte de pelo",
    "bookable": True,
    "duration_min": 30,
    "price": {"kind": "amount", "amount_minor": 1500},
}


# ── duración y precio ──────────────────────────────────────────────────────


async def test_a_bookable_service_has_a_duration_and_one_that_is_not_has_none(
    client: Any, biz: Biz
) -> None:
    for body, code in (
        ({"name": "Corte", "bookable": True}, "duration_required"),
        ({"name": "Cera", "bookable": False, "duration_min": 30}, "duration_not_allowed"),
        ({"name": "Corte", "bookable": True, "duration_min": 7}, "duration_invalid"),
        ({"name": "Corte", "bookable": True, "duration_min": 485}, "duration_invalid"),
    ):
        refused = await write(client, biz, "POST", "/services", body, revision=0, expect=422)
        assert refused["detail"]["code"] == code, body

    made = await _service(client, biz, CORTE, 0)
    corte = next(s for s in made["items"] if s["id"] == made["created_id"])
    assert (corte["bookable"], corte["duration_min"]) == (True, 30)
    cera = await _service(
        client,
        biz,
        {"name": "Cera", "description": "Fijación fuerte", "bookable": False},
        made["revision"],
    )
    item = next(s for s in cera["items"] if s["id"] == cera["created_id"])
    assert (item["bookable"], item["duration_min"], item["description"]) == (
        False,
        None,
        "Fijación fuerte",
    )


async def test_no_price_free_or_an_amount_in_the_currency_of_the_business(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """Historia 6, escenarios 3 y 5: en CLP, sin decimales."""
    chile = await new_business(
        client,
        db_session,
        console_world,
        name="Flor y Encanto",
        country="CL",
        timezone="America/Santiago",
        price_currency="CLP",
    )
    _agent, cfg = await seed_agent(
        db_session, chile.tenant_id, name="Recepción", prompt="Eres Sofía."
    )
    rev = 0
    for name, price in (
        ("Ramo grande", {"kind": "amount", "amount_minor": 15000}),
        ("Consulta", {"kind": "free"}),
        ("Boda", {"kind": "none"}),
    ):
        out = await _service(client, chile, {"name": name, "bookable": False, "price": price}, rev)
        rev = out["revision"]
    listed = await read(client, chile, "/services")
    assert listed["currency"] == "CLP" and listed["exponent"] == 0
    prices = {s["name"]: (s["price"], s["currency"]) for s in listed["items"]}
    assert prices == {
        "Ramo grande": ({"kind": "amount", "amount_minor": 15000}, "CLP"),
        "Consulta": ({"kind": "free"}, "CLP"),
        "Boda": ({"kind": "none"}, "CLP"),
    }
    refused = await write(
        client,
        chile,
        "POST",
        "/services",
        {"name": "Mal", "bookable": False, "price": {"kind": "amount"}},
        revision=rev,
        expect=422,
    )
    assert refused["detail"]["code"] == "price_amount_required"

    prompt = await active_prompt(db_session, chile.tenant_id, cfg)
    assert "Ramo grande" in prompt and "15.000 CLP" in prompt
    assert "Consulta" in prompt and "gratis" in prompt
    assert "Boda" in prompt and "lo confirma el equipo" in prompt


# ── quién lo ofrece ────────────────────────────────────────────────────────


async def test_a_service_for_all_agents_is_known_only_to_those_that_serve_all(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Historia 6, escenario 1, y «Lo usan» (11.2, 11.3)."""
    recepcion, cfg_r = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Recepción."
    )
    ventas, cfg_v = await seed_agent(
        db_session, biz.tenant_id, name="Ventas mayoristas", prompt="Eres Ventas.", serves_all=False
    )
    made = await _service(client, biz, CORTE, 0)
    corte = made["created_id"]
    assert made["agents"] == [
        {"id": str(recepcion), "name": "Recepción", "serves_all": True},
        {"id": str(ventas), "name": "Ventas mayoristas", "serves_all": False},
    ]
    item = next(s for s in made["items"] if s["id"] == corte)
    assert item["agents"] == {"mode": "all_agents", "agent_ids": []}
    assert item["used_by"] == [{"id": str(recepcion), "name": "Recepción"}]
    assert "Corte de pelo" in await active_prompt(db_session, biz.tenant_id, cfg_r)
    assert "Corte de pelo" not in await active_prompt(db_session, biz.tenant_id, cfg_v)

    mayor = await _service(
        client,
        biz,
        {"name": "Pedido mayorista", "bookable": False, "price": {"kind": "none"}},
        made["revision"],
    )
    listed = await write(
        client,
        biz,
        "PUT",
        f"/services/{mayor['created_id']}/agents",
        {"mode": "list", "agent_ids": [str(ventas)]},
        revision=mayor["revision"],
    )
    item = next(s for s in listed["items"] if s["id"] == mayor["created_id"])
    assert item["agents"] == {"mode": "list", "agent_ids": [str(ventas)]}
    assert item["used_by"] == [
        {"id": str(recepcion), "name": "Recepción"},
        {"id": str(ventas), "name": "Ventas mayoristas"},
    ]
    ventas_prompt = await active_prompt(db_session, biz.tenant_id, cfg_v)
    assert "Pedido mayorista" in ventas_prompt and "Corte de pelo" not in ventas_prompt

    # An agent of another client is not an agent of this one.
    foreign = await write(
        client,
        biz,
        "PUT",
        f"/services/{corte}/agents",
        {"mode": "list", "agent_ids": [str(uuid.uuid4())]},
        revision=listed["revision"],
        expect=422,
    )
    assert foreign["detail"]["code"] == "unknown_agent"


async def _two_agents_on_two_numbers(
    client: Any, db_session: AsyncSession, biz: Biz
) -> dict[str, Any]:
    """Recepción (atiende todos) y Ventas (solo «Pedido mayorista»), cada uno con
    su número, una persona que escribe a cada número y Reservas encendido."""
    recepcion, _ = await seed_agent(db_session, biz.tenant_id, name="Recepción", prompt="R.")
    ventas, _ = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="V.", serves_all=False
    )
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": EVERY_DAY}, revision=0)
    corte = await _service(client, biz, CORTE, 0)
    mayor = await _service(
        client,
        biz,
        {"name": "Pedido mayorista", "bookable": True, "duration_min": 60},
        corte["revision"],
    )
    await write(
        client,
        biz,
        "PUT",
        f"/services/{mayor['created_id']}/agents",
        {"mode": "list", "agent_ids": [str(ventas)]},
        revision=mayor["revision"],
    )
    out: dict[str, Any] = {
        "corte": uuid.UUID(corte["created_id"]),
        "mayor": uuid.UUID(mayor["created_id"]),
    }
    async with tenant_scoped_session(db_session, biz.tenant_id):
        settings = ReservationSettings(tenant_id=biz.tenant_id, version=1, updated_by="tests")
        apply_defaults(settings, "services", None)
        db_session.add(settings)
        db_session.add(ReservationStaff(tenant_id=biz.tenant_id, name="Lucía", position=1))
    db_session.add(
        ClientAccess(
            tenant_id=biz.tenant_id,
            partner_id=biz.partner_id,
            enabled=True,
            modules=["panel", "inbox", "reservas"],
            updated_by="operator:tests",
        )
    )
    await db_session.commit()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        for key, agent_id in (("recepcion", recepcion), ("ventas", ventas)):
            channel = Channel(
                tenant_id=biz.tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"svc-{key}-{uuid.uuid4().hex[:6]}",
                config={},
                status=ChannelStatus.ACTIVE,
                agent_id=agent_id,
            )
            customer = Customer(
                tenant_id=biz.tenant_id,
                identifier=f"3460{uuid.uuid4().int % 10**7:07d}",
                name=key,
                preferences={},
            )
            db_session.add_all([channel, customer])
            await db_session.flush()
            db_session.add(
                Conversation(
                    tenant_id=biz.tenant_id,
                    channel_id=channel.id,
                    customer_id=customer.id,
                    status=ConversationStatus.OPEN,
                )
            )
            out[key] = customer.id
    return out


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


async def _tool(biz: Biz, customer: uuid.UUID, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Como el turno: un no de la herramienta (``ToolError``) es un sobre de error."""
    from nexus_mcp.base import ToolError

    with tenant_context(biz.tenant_id), customer_context(customer):
        try:
            env: dict[str, Any] = await _registry().dispatch(name, args, whitelist=[name])
        except ToolError as exc:
            return {"status": "error", "error": str(exc)}
    return env


async def test_the_tools_return_only_the_services_of_the_agent_of_the_turn(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Requisito 11.4, garantía 9; historia 6, escenario 2."""
    world = await _two_agents_on_two_numbers(client, db_session, biz)
    day = future_day(5).isoformat()

    seen = {}
    for who in ("recepcion", "ventas"):
        env = await _tool(biz, world[who], "reservas.services", {})
        assert env["status"] == "ok", env
        seen[who] = {s["name"] for s in env["result"]["services"]}
    assert seen == {
        "recepcion": {"Corte de pelo", "Pedido mayorista"},
        "ventas": {"Pedido mayorista"},
    }

    # Ventas cannot look for, nor book, Recepción's service — even by its id.
    env = await _tool(
        biz,
        world["ventas"],
        "reservas.find_slots",
        {"date": day, "service_id": str(world["corte"])},
    )
    assert env["status"] != "ok" or env["result"]["why_closed"] == "not_offered", env
    env = await _tool(
        biz,
        world["ventas"],
        "reservas.create",
        {"date": day, "time": "10:00", "service_id": str(world["corte"]), "idempotency_key": "x"},
    )
    assert env["status"] == "ok" and env["result"]["refused"] == "not_offered", env
    async with tenant_scoped_session(db_session, biz.tenant_id):
        booked = await db_session.scalar(sa.select(sa.func.count()).select_from(Reservation))
    assert booked == 0

    # Recepción can.
    env = await _tool(
        biz,
        world["recepcion"],
        "reservas.find_slots",
        {"date": day, "service_id": str(world["corte"])},
    )
    assert env["status"] == "ok" and env["result"]["slots"], env

    # booking.* (the legacy appointments) names services by their name.
    env = await _tool(
        biz,
        world["ventas"],
        "booking.check_availability",
        {"service_name": "Corte de pelo", "on_date": day, "duration_min": 30},
    )
    assert env["status"] != "ok", env
    env = await _tool(
        biz,
        world["recepcion"],
        "booking.check_availability",
        {"service_name": "Corte de pelo", "on_date": day, "duration_min": 30},
    )
    assert env["status"] == "ok", env


async def test_a_service_that_is_not_bookable_offers_no_time(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Caso límite: «Servicio sin duración que alguien quiere reservar»."""
    world = await _two_agents_on_two_numbers(client, db_session, biz)
    listed = await read(client, biz, "/services")
    cera = await _service(
        client,
        biz,
        {"name": "Cera", "bookable": False, "price": {"kind": "free"}},
        listed["revision"],
    )
    day = future_day(5).isoformat()
    env = await _tool(
        biz,
        world["recepcion"],
        "reservas.find_slots",
        {"date": day, "service_id": cera["created_id"]},
    )
    assert env["status"] == "ok", env
    assert env["result"]["closed"] is True and env["result"]["why_closed"] == "not_bookable"
    env = await _tool(biz, world["recepcion"], "reservas.services", {})
    items = {s["name"]: s for s in env["result"]["services"]}
    assert items["Cera"]["bookable"] is False and items["Cera"]["duration_minutes"] is None


# ── archivar y duplicar ────────────────────────────────────────────────────


async def test_deleting_archives_and_past_bookings_keep_the_name(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Historia 6, escenario 4."""
    _agent, cfg = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Sofía."
    )
    made = await _service(client, biz, CORTE, 0)
    corte = uuid.UUID(made["created_id"])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        svc = await db_session.get(ReservationService, corte)
        assert svc is not None
        start = svc.created_at - timedelta(days=7)
        lucia = ReservationStaff(tenant_id=biz.tenant_id, name="Lucía", position=1)
        db_session.add(lucia)
        await db_session.flush()
        db_session.add(
            Reservation(
                tenant_id=biz.tenant_id,
                mode="services",
                origin="person",
                channel="phone",
                created_by_kind="person",
                status="done",
                service_id=corte,
                staff_id=lucia.id,
                service_name=svc.name,
                party_size=1,
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                version=1,
            )
        )
    archived = await write(
        client, biz, "POST", f"/services/{corte}/archive", revision=made["revision"]
    )
    assert archived["items"] == []
    with_archived = await read(client, biz, "/services?archived=true")
    assert [(s["name"], s["archived"]) for s in with_archived["items"]] == [("Corte de pelo", True)]
    async with tenant_scoped_session(db_session, biz.tenant_id):
        past = await db_session.scalar(sa.select(Reservation.service_name))
    assert past == "Corte de pelo"
    assert "Corte de pelo" not in await active_prompt(db_session, biz.tenant_id, cfg)


async def test_duplicating_a_service_copies_it_with_its_agents(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Requisito 11.6."""
    ventas, _ = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="V.", serves_all=False
    )
    made = await _service(client, biz, {**CORTE, "description": "Con lavado"}, 0)
    listed = await write(
        client,
        biz,
        "PUT",
        f"/services/{made['created_id']}/agents",
        {"mode": "list", "agent_ids": [str(ventas)]},
        revision=made["revision"],
    )
    copy = await write(
        client,
        biz,
        "POST",
        f"/services/{made['created_id']}/duplicate",
        revision=listed["revision"],
        expect=201,
    )
    dup = next(s for s in copy["items"] if s["id"] == copy["created_id"])
    assert dup["id"] != made["created_id"]
    assert dup["name"] == "Corte de pelo (copia)"
    assert (dup["description"], dup["duration_min"], dup["price"]) == (
        "Con lavado",
        30,
        {"kind": "amount", "amount_minor": 1500},
    )
    assert dup["agents"] == {"mode": "list", "agent_ids": [str(ventas)]}


async def test_an_agent_with_a_list_serves_only_its_list(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """«Atiende todos» o una lista, desde el agente (requisito 11.2)."""
    ventas, cfg = await seed_agent(db_session, biz.tenant_id, name="Ventas", prompt="V.")
    made = await _service(client, biz, CORTE, 0)
    second = await _service(
        client, biz, {"name": "Barba", "bookable": True, "duration_min": 20}, made["revision"]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await services_catalog.set_agent_services(
            db_session,
            ventas,
            serves_all=False,
            service_ids=[uuid.UUID(second["created_id"])],
            actor=services_catalog.SYSTEM_ACTOR,
        )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        names = [s.name for s in await services_catalog.services_for_agent(db_session, ventas)]
    assert names == ["Barba"]
    prompt = await active_prompt(db_session, biz.tenant_id, cfg)
    assert "Barba" in prompt and "Corte de pelo" not in prompt
