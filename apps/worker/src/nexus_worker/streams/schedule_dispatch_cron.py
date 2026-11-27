"""El disparador de rutinas — spec 082, T024 (requisitos 3.2, 3.8, 7.6 y 8.1).

Un barrido **por vencimiento**, no un recorrido por cliente. Cada rutina lleva
su ``next_run_at`` ya calculado en la fila, así que el tic lee de un índice
parcial lo que venció y despacha. El patrón del cron de cobranza —mirar la hora
local de cada cliente, uno por uno— sirve para un barrido diario, no para tics
por minuto.

Descubrir lo vencido cruza la frontera de todos los clientes a la vez, y con la
RLS una sesión sin cliente puesto no ve nada. Por eso va por la función
``due_schedules``, ``SECURITY DEFINER``, que devuelve identificadores y horas y
nada más: ni instrucción, ni nombre, ni respuesta. A partir de ahí cada
ejecución abre su propia transacción **con su cliente puesto**, como el
consumidor de la cola.

Este tic **no llama al modelo**. Abre la fila de la ejecución, encola el trabajo
y recalcula la próxima. Lo demás es del manejador.

Tres puertas antes de gastar, y las tres dejan rastro en vez de callarse:

- la rutina sigue activa y vencida cuando se la mira con su cliente puesto;
- su agente atiende (si no, la rutina se pausa sola con su motivo, 8.1);
- la hora no se pasó de la ventana de gracia (7.6): nadie quiere a las dos de
  la tarde el informe de las nueve.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, Schedule
from nexus_api.db.models.schedule import GRACE
from nexus_api.services import jobs as jobs_service
from nexus_api.services.schedules import runs as runs_service
from nexus_api.services.schedules import service as schedules_service
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

#: Cada cuánto se mira. La hora de una rutina es un minuto concreto, así que el
#: tic tiene que ser más fino que eso o la ventana de gracia haría el trabajo.
DEFAULT_TICK_SECONDS = 30.0
#: Cuántas se despachan por tic. Un tope evita que una cola represada se lleve
#: todo el proceso en una sola pasada.
BATCH = 100
#: El tipo de trabajo que ejecuta una rutina.
JOB_KIND = "schedule_run"


async def _due(limit: int) -> list[tuple[uuid.UUID, uuid.UUID, datetime]]:
    """Lo vencido, de todos los clientes. Solo identificadores y horas."""
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                sa.text("SELECT tenant_id, schedule_id, scheduled_for FROM due_schedules(:n)"),
                {"n": limit},
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def _fire(tenant_id: uuid.UUID, schedule_id: uuid.UUID, slot: datetime) -> bool:
    """Una ejecución, con el cliente puesto. ``False`` si alguna puerta cerró."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        schedule = await session.get(Schedule, schedule_id)
        if schedule is None or schedule.state != "active" or schedule.next_run_at is None:
            return False

        agent = await session.scalar(sa.select(Agent).where(Agent.id == schedule.agent_id))
        if agent is None or agent.lifecycle != schedules_service.ATTENDING:
            # 8.1: se pausa sola con su motivo, y vuelve cuando el agente vuelva.
            await schedules_service.pause(session, schedule, reason="agent_unavailable")
            return False

        now = datetime.now(UTC)
        if now - slot > GRACE:
            # 7.6: no se ejecuta tarde. Se deja dicho y se espera a la siguiente.
            log.info(
                "schedule_dispatch.too_late",
                tenant_id=str(tenant_id),
                schedule_id=str(schedule_id),
                slot=slot.isoformat(),
            )
            schedule.next_run_at = await _recompute(session, schedule)
            return False

        run = await runs_service.open_run(session, schedule=schedule, scheduled_for=slot)
        if run.job_id is not None:
            # Otra réplica llegó primero: su ejecución ya tiene trabajo.
            return False
        job = await jobs_service.create_job(
            session, kind=JOB_KIND, agent_id=schedule.agent_id, created_by=None
        )
        job.progress = {
            "step": None,
            "blocks": [],
            "input": runs_service.as_input(schedule.id, run.id),
        }
        run.job_id = job.id
        # La próxima se mueve **antes** de soltar la transacción: si se dejara
        # para después, un reinicio entre medias volvería a disparar la misma.
        schedule.next_run_at = await _recompute(session, schedule, fired=True)
        await session.flush()
        jobs_service.enqueue_after_commit(session, job)
        return True


async def _recompute(
    session: AsyncSession, schedule: Schedule, *, fired: bool = False
) -> datetime | None:
    """La próxima después de esta pasada.

    Una rutina de **una sola vez** que ya se ejecutó no tiene siguiente, y eso
    no se deduce del reloj: si se recalculara, un disparo un minuto antes de su
    hora dejaría la fecha todavía en el futuro y volvería a ejecutarse. Se
    apaga por definición, no por aritmética.
    """
    if fired and schedule.cadence == "once":
        return None
    # Anotada a propósito: ``nexus_api`` llega sin tipos a este paquete, así
    # que sin esto el valor entra como ``Any`` y ``--strict`` lo rechaza.
    nxt: datetime | None = await schedules_service.next_run_for(session, schedule)
    return nxt


async def dispatch_due(*, limit: int = BATCH) -> int:
    """Una pasada. Devuelve cuántas ejecuciones se abrieron."""
    fired = 0
    for tenant_id, schedule_id, slot in await _due(limit):
        try:
            if await _fire(tenant_id, schedule_id, slot):
                fired += 1
        except Exception as exc:  # pragma: no cover - defensivo
            # Una rutina que revienta no puede llevarse el tic entero: las demás
            # tienen su hora igual.
            log.warning(
                "schedule_dispatch.failed",
                tenant_id=str(tenant_id),
                schedule_id=str(schedule_id),
                error=type(exc).__name__,
            )
    return fired


async def run_schedule_dispatch_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Tarea de fondo: una pasada por tic."""
    log.info("schedule_dispatch_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            fired = await dispatch_due()
            if fired:
                log.info("schedule_dispatch_cron.fired", count=fired)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensivo
            log.warning("schedule_dispatch_cron.tick_failed", error=type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
        except TimeoutError:
            continue


__all__ = ["BATCH", "DEFAULT_TICK_SECONDS", "dispatch_due", "run_schedule_dispatch_cron"]
