"""El alta de una rutina y su vida — spec 082, T009 (requisitos 2, 3.3, 8.3,
12.1 y 15).

Contra base real y con la RLS puesta, porque lo que se prueba aquí no es la
aritmética —esa está en las unitarias de ``when.py``— sino lo que el servicio
hace con la base: qué se guarda, qué se rechaza y en qué estado nace cada cosa.

Lo que más importa de este fichero son tres reglas que se olvidan fácil:

- una rutina para un agente que no atiende **nace en pausa**, y se dice en el
  momento;
- la pausa que pone una persona **no la deshace el sistema**;
- restaurar una rutina archivada la deja **en pausa**, nunca ejecutándose: si
  volviera sola, volvería gastando.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Schedule
from nexus_api.services.schedules import service
from nexus_api.services.schedules.service import ScheduleError, ScheduleInput

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MADRID = "Europe/Madrid"


async def _seed(
    session: AsyncSession, *, lifecycle: str = "published"
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, agent_id = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
            "VALUES (:t, 'Muna', :s, 'essential', 'active', :tz)"
        ),
        {"t": str(tenant_id), "s": f"rut-{tenant_id.hex[:10]}", "tz": MADRID},
    )
    await session.execute(
        sa.text(
            "INSERT INTO agents (id, tenant_id, name, lifecycle, pause_reason) "
            "VALUES (:a, :t, 'Soporte', :l, :r)"
        ),
        {
            "a": str(agent_id),
            "t": str(tenant_id),
            "l": lifecycle,
            # La tabla de agentes exige motivo cuando está en pausa, igual que
            # la de rutinas: sembrar sin él revienta el CHECK.
            "r": "manual" if lifecycle == "paused" else None,
        },
    )
    await session.commit()
    return tenant_id, agent_id


def _input(agent_id: uuid.UUID, **over) -> ScheduleInput:
    base = {
        "agent_id": agent_id,
        "name": "Altas de ayer en Notion",
        "instruction": "Revisa la vista «Usuarios» y dime quién se dio de alta ayer.",
        "cadence": "daily",
        "local_time": time(9, 0),
    }
    return ScheduleInput(**{**base, **over})


async def _create(tenant_id: uuid.UUID, data: ScheduleInput, *, by: str = "pedro@auphere.com"):
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        made = await service.create(session, tenant_id=tenant_id, data=data, created_by=by)
        await session.commit()
        return made


# ── el alta ─────────────────────────────────────────────────────────────────


async def test_a_routine_is_born_active_with_its_next_run(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id))

    assert made.state == "active"
    assert made.pause_reason is None
    assert made.next_run_at is not None and made.next_run_at > datetime.now(UTC)
    assert made.created_by == "pedro@auphere.com"


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"name": "   "}, "name_required"),
        ({"instruction": ""}, "instruction_required"),
        ({"instruction": "x" * 2001}, "instruction_too_long"),
        ({"cadence": "weekly", "weekdays": []}, "weekdays_required"),
        ({"cadence": "weekly"}, "weekdays_required"),
        ({"cadence": "monthly", "day_of_month": 29}, "day_of_month_out_of_range"),
        ({"cadence": "monthly", "day_of_month": 0}, "day_of_month_out_of_range"),
        ({"cadence": "monthly"}, "day_of_month_out_of_range"),
        ({"cadence": "once"}, "run_date_required"),
        ({"cadence": "cron"}, "unknown_cadence"),
    ],
)
async def test_what_the_alta_refuses(db_session, over: dict, code: str) -> None:
    tenant_id, agent_id = await _seed(db_session)
    with pytest.raises(ScheduleError) as caught:
        await _create(tenant_id, _input(agent_id, **over))
    assert caught.value.code == code


async def test_a_once_in_the_past_is_refused(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    with pytest.raises(ScheduleError) as caught:
        await _create(tenant_id, _input(agent_id, cadence="once", run_date=yesterday))
    assert caught.value.code == "run_date_in_the_past"


async def test_a_weekly_keeps_its_days(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id, cadence="weekly", weekdays=[0, 3]))
    assert made.weekdays == [0, 3]
    assert made.next_run_at is not None


async def test_the_limit_of_active_routines_per_client(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    for i in range(service.MAX_ACTIVE_PER_TENANT):
        await _create(tenant_id, _input(agent_id, name=f"La {i}"))
    with pytest.raises(ScheduleError) as caught:
        await _create(tenant_id, _input(agent_id, name="La de más"))
    assert caught.value.code == "limit_reached"


async def test_an_archived_one_does_not_count_against_the_limit(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    first = await _create(tenant_id, _input(agent_id, name="La vieja"))
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await service.archive(session, await _get(session, first.id), actor="pedro@auphere.com")
        await session.commit()
    for i in range(service.MAX_ACTIVE_PER_TENANT):
        await _create(tenant_id, _input(agent_id, name=f"La {i}"))


# ── el agente manda ─────────────────────────────────────────────────────────


async def test_a_routine_for_an_agent_that_is_not_attending_is_born_paused(db_session) -> None:
    """Requisito 8.3. Y sin próxima: una rutina en pausa no tiene cuándo."""
    tenant_id, agent_id = await _seed(db_session, lifecycle="paused")
    made = await _create(tenant_id, _input(agent_id))

    assert made.state == "paused"
    assert made.pause_reason == "agent_unavailable"
    assert made.next_run_at is None


async def test_the_effective_state_follows_the_agent(db_session) -> None:
    """La fila guarda la intención del partner. Lo que se ve se calcula."""
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id))
    assert made.state == "active"

    await db_session.execute(
        sa.text("UPDATE agents SET lifecycle = 'paused', pause_reason = 'manual' WHERE id = :a"),
        {"a": str(agent_id)},
    )
    await db_session.commit()

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
        state, reason = await service.effective_state(session, row)
    assert (state, reason) == ("paused", "agent_unavailable")
    # La fila no se ha tocado: la intención del partner sigue siendo que corra.
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        assert (await _get(session, made.id)).state == "active"


# ── cambiar, pausar, archivar ───────────────────────────────────────────────


async def _get(session: AsyncSession, schedule_id: uuid.UUID) -> Schedule:
    return (
        await session.execute(sa.select(Schedule).where(Schedule.id == schedule_id))
    ).scalar_one()


async def test_changing_the_hour_moves_the_next_run(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id))
    before = made.next_run_at

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await service.update(session, await _get(session, made.id), local_time=time(23, 30))
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        after = (await _get(session, made.id)).next_run_at
    assert after != before


async def test_changing_the_instruction_keeps_the_same_next_run(db_session) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id))
    before = made.next_run_at

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await service.update(
            session, await _get(session, made.id), instruction="Otra cosa distinta."
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
    assert row.instruction == "Otra cosa distinta."
    assert row.next_run_at == before


async def test_a_manual_pause_is_not_undone_by_the_system(db_session) -> None:
    """Requisito 15.3, calcado de lo que ya se hace con los agentes."""
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id))

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await service.pause(
            session, await _get(session, made.id), reason="manual", actor="pedro@auphere.com"
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
        assert (row.state, row.pause_reason, row.next_run_at) == ("paused", "manual", None)
        # El sistema intenta reanudar lo suyo: esta no es suya.
        await service.resume(session, row, system_reason="agent_unavailable")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
        assert row.state == "paused"
        # Una persona sí.
        await service.resume(session, row, actor="pedro@auphere.com")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
    assert row.state == "active"
    assert row.next_run_at is not None


async def test_archiving_stops_it_and_restoring_leaves_it_paused(db_session) -> None:
    """Requisito 15.5: si volviera sola, volvería gastando."""
    tenant_id, agent_id = await _seed(db_session)
    made = await _create(tenant_id, _input(agent_id))

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await service.archive(session, await _get(session, made.id), actor="pedro@auphere.com")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
        assert (row.state, row.next_run_at) == ("archived", None)
        await service.restore(session, row, actor="pedro@auphere.com")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await _get(session, made.id)
    assert (row.state, row.pause_reason, row.next_run_at) == ("paused", "manual", None)


async def test_nothing_is_ever_deleted(db_session) -> None:
    """Constitución §IV: borrar no existe. El servicio no expone por dónde."""
    assert not hasattr(service, "delete")
