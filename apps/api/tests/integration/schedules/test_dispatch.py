"""El disparador de rutinas — spec 082, T022 (requisitos 3.2, 3.8 y 7.7).

Una pasada del barrido, sin reloj de verdad: se adelanta el vencimiento y se
mira lo que deja escrito. Lo que importa aquí no es que llame al modelo —de eso
se encarga el manejador— sino que **abra la ejecución y encole el trabajo una
sola vez**, y que mueva la próxima.

El caso que más duele si falla es el de una rutina de una sola vez: si el
barrido no la dejara sin próxima, se ejecutaría cada minuto para siempre.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Job, Schedule, ScheduleRun
from nexus_api.services.schedules import service
from nexus_api.services.schedules.service import ScheduleInput

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MADRID = "Europe/Madrid"


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, agent_id = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
            "VALUES (:t, 'Muna', :s, 'essential', 'active', :tz)"
        ),
        {"t": str(tenant_id), "s": f"disp-{tenant_id.hex[:10]}", "tz": MADRID},
    )
    await session.execute(
        sa.text(
            "INSERT INTO agents (id, tenant_id, name, lifecycle) "
            "VALUES (:a, :t, 'Soporte', 'published')"
        ),
        {"a": str(agent_id), "t": str(tenant_id)},
    )
    await session.commit()
    return tenant_id, agent_id


async def _make(tenant_id: uuid.UUID, agent_id: uuid.UUID, **over) -> Schedule:
    fields = {
        "agent_id": agent_id,
        "name": "Altas de ayer",
        "instruction": "Dime cuántos pedidos entraron ayer.",
        "cadence": "daily",
        "local_time": time(9, 0),
        **over,
    }
    data = ScheduleInput(**fields)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return await service.create(
            session, tenant_id=tenant_id, data=data, created_by="pedro@auphere.com"
        )


async def _make_due(db_session: AsyncSession, schedule_id: uuid.UUID) -> None:
    """Le adelanta la hora: es lo que hace el reloj, sin esperar a mañana."""
    await db_session.execute(
        sa.text("UPDATE schedules SET next_run_at = now() - interval '1 minute' WHERE id = :i"),
        {"i": str(schedule_id)},
    )
    await db_session.commit()


async def _sweep(limit: int = 50) -> int:
    from nexus_worker.streams.schedule_dispatch_cron import dispatch_due

    return await dispatch_due(limit=limit)


async def test_a_due_routine_opens_a_run_and_queues_a_job(db_session: AsyncSession) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _make(tenant_id, agent_id)
    await _make_due(db_session, made.id)

    assert await _sweep() == 1

    run = await db_session.scalar(sa.select(ScheduleRun).where(ScheduleRun.schedule_id == made.id))
    assert run is not None
    assert run.trigger == "schedule"
    assert run.instruction == "Dime cuántos pedidos entraron ayer."
    job = await db_session.scalar(sa.select(Job).where(Job.id == run.job_id))
    assert job is not None and job.kind == "schedule_run"


async def test_the_next_run_moves_forward(db_session: AsyncSession) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _make(tenant_id, agent_id)
    await _make_due(db_session, made.id)
    await _sweep()

    moved = await db_session.scalar(sa.select(Schedule.next_run_at).where(Schedule.id == made.id))
    assert moved is not None and moved > datetime.now(UTC)


async def test_a_second_sweep_does_not_fire_it_again(db_session: AsyncSession) -> None:
    """La hora ya se movió, así que no vence. Y si venciera, la clave única de
    la ranura lo impediría igual."""
    tenant_id, agent_id = await _seed(db_session)
    made = await _make(tenant_id, agent_id)
    await _make_due(db_session, made.id)

    assert await _sweep() == 1
    assert await _sweep() == 0
    runs = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ScheduleRun)
        .where(ScheduleRun.schedule_id == made.id)
    )
    assert runs == 1


async def test_a_once_routine_is_left_without_a_next_run(db_session: AsyncSession) -> None:
    """Si no se quedara sin próxima, se ejecutaría cada minuto para siempre."""
    tenant_id, agent_id = await _seed(db_session)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
    made = await _make(tenant_id, agent_id, cadence="once", run_date=tomorrow)
    await _make_due(db_session, made.id)

    assert await _sweep() == 1
    left = await db_session.scalar(sa.select(Schedule.next_run_at).where(Schedule.id == made.id))
    assert left is None


async def test_a_paused_routine_is_not_swept(db_session: AsyncSession) -> None:
    tenant_id, agent_id = await _seed(db_session)
    made = await _make(tenant_id, agent_id)
    await db_session.execute(
        sa.text(
            "UPDATE schedules SET state = 'paused', pause_reason = 'manual', "
            "next_run_at = now() - interval '1 minute' WHERE id = :i"
        ),
        {"i": str(made.id)},
    )
    await db_session.commit()

    assert await _sweep() == 0


async def test_an_agent_that_stopped_attending_stops_its_routine(
    db_session: AsyncSession,
) -> None:
    """Requisito 8.1: el barrido no la ejecuta, y además deja escrito el motivo
    para que la lista pueda decirlo sin abrirla."""
    tenant_id, agent_id = await _seed(db_session)
    made = await _make(tenant_id, agent_id)
    await _make_due(db_session, made.id)
    await db_session.execute(
        sa.text("UPDATE agents SET lifecycle = 'paused', pause_reason = 'manual' WHERE id = :a"),
        {"a": str(agent_id)},
    )
    await db_session.commit()

    assert await _sweep() == 0
    row = await db_session.scalar(sa.select(Schedule).where(Schedule.id == made.id))
    assert row is not None
    assert (row.state, row.pause_reason, row.next_run_at) == ("paused", "agent_unavailable", None)


async def test_moving_the_business_timezone_moves_its_routines(db_session: AsyncSession) -> None:
    """Requisito 3.7: la hora es local, así que mudarse de huso mueve el
    instante. Sin esto seguiría disparándose a la hora de la zona vieja."""
    from nexus_api.services.schedules.service import recompute_for_tenant

    tenant_id, agent_id = await _seed(db_session)
    made = await _make(tenant_id, agent_id)
    before = made.next_run_at

    await db_session.execute(
        sa.text("UPDATE tenants SET timezone = 'America/Santiago' WHERE id = :t"),
        {"t": str(tenant_id)},
    )
    await db_session.commit()

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        moved = await recompute_for_tenant(session, tenant_id)
    assert moved == 1

    after = await db_session.scalar(sa.select(Schedule.next_run_at).where(Schedule.id == made.id))
    assert after != before
