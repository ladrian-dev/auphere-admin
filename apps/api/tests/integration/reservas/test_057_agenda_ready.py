"""Spec 057, requisito 4: «¿la agenda está lista?», barato, para cada turno.

``agenda_ready`` responde lo mismo que ``not_ready`` sin recorrer días: el módulo
encendido con su modo, horario, y en Servicios alguien en activo y algún servicio
reservable; en Aforo, plazas y franjas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ClientAccess,
    ReservationService,
    ReservationSettings,
    ReservationStaff,
)
from nexus_api.services.reservations.passing import agenda_ready, not_ready
from tests.conftest import make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _ready(tenant_id: Any) -> tuple[bool, list[str]]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return (
            await agenda_ready(session, tenant_id),
            await not_ready(session, tenant_id, now=datetime.now(UTC)),
        )


async def _run(tenant_id: Any, stmt: Any) -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(stmt)
        await session.commit()


async def test_a_ready_agenda_is_ready(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    assert await _ready(w["tenant_id"]) == (True, [])


async def test_without_the_module_it_is_not(db_session, console_world) -> None:
    w = console_world["a"]
    assert (await _ready(w["tenant_id"]))[0] is False


async def test_the_module_off_the_list_is_not(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _run(
        w["tenant_id"],
        sa.update(ClientAccess)
        .where(ClientAccess.tenant_id == w["tenant_id"])
        .values(modules=["panel"]),
    )
    ready, reasons = await _ready(w["tenant_id"])
    assert ready is False and reasons == ["reservas_off"]


async def test_without_hours_it_is_not(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], hours=None
    )
    ready, reasons = await _ready(w["tenant_id"])
    assert ready is False and "hours_missing" in reasons


async def test_without_anyone_on_the_team_it_is_not(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _run(w["tenant_id"], sa.update(ReservationStaff).values(archived_at=sa.func.now()))
    ready, reasons = await _ready(w["tenant_id"])
    assert ready is False and "no_staff" in reasons


async def test_without_a_bookable_service_it_is_not(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _run(w["tenant_id"], sa.update(ReservationService).values(archived_at=sa.func.now()))
    ready, reasons = await _ready(w["tenant_id"])
    assert ready is False and "no_services" in reasons


async def test_capacity_without_seats_is_not(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], mode="capacity"
    )
    assert (await _ready(w["tenant_id"]))[0] is True
    await _run(w["tenant_id"], sa.update(ReservationSettings).values(seats=None))
    ready, reasons = await _ready(w["tenant_id"])
    assert ready is False and "no_capacity" in reasons


async def _statements(tenant_id: Any) -> int:
    statements: list[str] = []
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        sync_engine = session.bind.sync_engine if session.bind is not None else None
        assert sync_engine is not None

        def _count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            statements.append(statement)

        sa.event.listen(sync_engine, "before_cursor_execute", _count)
        try:
            assert await agenda_ready(session, tenant_id) is True
        finally:
            sa.event.remove(sync_engine, "before_cursor_execute", _count)
    return len(statements)


async def test_it_is_cheap(db_session, console_world) -> None:
    """Se llama en cada turno: el número de consultas no crece con los servicios ni con
    el equipo (``not_ready`` recorre 7 días por persona y servicio)."""
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    before = await _statements(w["tenant_id"])
    async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
        for i in range(10):
            session.add(
                ReservationService(
                    tenant_id=w["tenant_id"],
                    name=f"Servicio {i}",
                    duration_minutes=30,
                    all_staff=True,
                    position=20 + i,
                )
            )
            session.add(ReservationStaff(tenant_id=w["tenant_id"], name=f"Persona {i}"))
        await session.commit()
    assert await _statements(w["tenant_id"]) == before
