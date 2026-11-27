"""La ejecución de una rutina, abierta y cerrada — spec 082, T017.

La fila de ``schedule_runs`` es la verdad de lo que pasó: la abre quien dispara
—el barrido o «Ejecutar ahora»— y la cierra el manejador de la cola. Entre una
cosa y otra puede morirse una réplica, así que la fila nace ya escrita y nunca
se deduce del trabajo.

Una ejecución **es el conjunto de sus intentos**: por eso ``attempts`` vive aquí
y no en el trabajo, y por eso ``uq_schedule_runs_slot`` es lo que impide que dos
réplicas abran dos ejecuciones para la misma hora.

Y guarda ``instruction``: la de ese momento, no la de ahora. Editar la rutina no
reescribe lo que el agente contestó a otra pregunta.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Schedule, ScheduleRun
from nexus_api.db.models.schedule import FAILURES_BEFORE_PAUSE

__all__ = ["close", "fail", "open_run", "start"]


async def open_run(
    session: AsyncSession,
    *,
    schedule: Schedule,
    scheduled_for: datetime | None = None,
    trigger: str = "schedule",
) -> ScheduleRun:
    """Abre la ejecución de esta rutina para esa hora.

    Si ya existe una para la misma hora, devuelve la que hay: la clave única es
    lo que hace que dos réplicas no disparen dos veces, y aquí se nota como un
    ``None`` que no hace falta tratar más arriba.
    """
    when = scheduled_for or datetime.now(UTC)
    existing = await session.scalar(
        sa.select(ScheduleRun).where(
            ScheduleRun.schedule_id == schedule.id,
            ScheduleRun.scheduled_for == when,
        )
    )
    if existing is not None:
        return existing
    run = ScheduleRun(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        scheduled_for=when,
        trigger=trigger,
        status="running",
        attempts=1,
        instruction=schedule.instruction,
    )
    session.add(run)
    await session.flush()
    return run


async def start(session: AsyncSession, run: ScheduleRun, *, job_id: uuid.UUID) -> ScheduleRun:
    """Un intento empieza: queda apuntado cuál y con qué trabajo."""
    run.job_id = job_id
    run.started_at = datetime.now(UTC)
    await session.flush()
    return run


async def close(
    session: AsyncSession,
    run: ScheduleRun,
    *,
    answer: str,
    tools_used: tuple[str, ...] = (),
    withheld: tuple[dict[str, str], ...] = (),
    partial: bool = False,
    duration_ms: int | None = None,
    cost_micros: int = 0,
) -> ScheduleRun:
    """Cierra la ejecución. ``partial`` cuando le faltó algo, y entonces
    ``withheld`` dice qué: una parcial sin decir qué faltó no se guarda, y el
    ``CHECK`` de la tabla lo impide."""
    run.status = "partial" if partial else "done"
    run.answer = answer
    run.tools_used = list(tools_used)
    run.withheld = [dict(w) for w in withheld] if partial else (list(withheld) or None)
    run.duration_ms = duration_ms
    run.cost_micros = cost_micros
    run.finished_at = datetime.now(UTC)
    await _after(session, run, ok=True)
    return run


async def fail(
    session: AsyncSession,
    run: ScheduleRun,
    *,
    error_code: str,
    detail: str | None = None,
    cost_micros: int = 0,
) -> ScheduleRun:
    """Da la ejecución por fallida, con su código. Tres seguidas pausan la
    rutina: una que falla siempre no puede seguir gastando cada día."""
    run.status = "failed"
    run.error_code = error_code
    run.error_detail = detail
    run.cost_micros = cost_micros
    run.finished_at = datetime.now(UTC)
    await _after(session, run, ok=False)
    return run


async def _after(session: AsyncSession, run: ScheduleRun, *, ok: bool) -> None:
    """Lo que la rutina aprende de su ejecución: el contador de fallos seguidos
    y, si se pasa del tope, su pausa con motivo."""
    schedule = await session.get(Schedule, run.schedule_id)
    if schedule is not None:
        if ok:
            schedule.consecutive_failures = 0
        else:
            schedule.consecutive_failures = (schedule.consecutive_failures or 0) + 1
            if schedule.consecutive_failures >= FAILURES_BEFORE_PAUSE:
                schedule.state = "paused"
                schedule.pause_reason = "failures"
                schedule.next_run_at = None
    await session.flush()


def as_input(schedule_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    """Lo que el trabajo lleva dentro. Nunca la instrucción: ya está en la fila."""
    return {"schedule_id": str(schedule_id), "run_id": str(run_id)}
