"""La vida de una rutina — spec 082, T010 (requisitos 2, 8, 12.1 y 15).

Alta, cambio, pausa, archivo y restauración, más el **estado efectivo**, que es
la pieza con más criterio de este módulo.

La fila guarda ``state``: lo que el partner quiere que pase. Lo que de verdad va
a pasar depende además del agente y del saldo, y eso se calcula al leer
(:func:`effective_state`). Hacerlo así evita el problema de todo estado
replicado: que el agente vuelva a atender y la rutina se quede pegada en pausa
porque nadie corrió el proceso que la despierta.

La pausa que pone una persona es distinta de la que pone el sistema, igual que
en los agentes: ``manual`` solo la quita una persona.

Todo lo de aquí se llama con la sesión ya puesta en su cliente. La RLS hace el
resto: una rutina de otro cliente sencillamente no existe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Agent, AuditLog, Schedule
from nexus_api.db.models.schedule import (
    CADENCES,
    MAX_ACTIVE_PER_TENANT,
    SYSTEM_PAUSE_REASONS,
)
from nexus_api.services.schedules import when

#: El agente atiende cuando su vida dice ``published``. Cualquier otra cosa
#: —borrador, pausa, archivo— deja sus rutinas sin ejecutarse.
ATTENDING: Final = "published"
#: Lo que, al cambiar, mueve la próxima ejecución. Cambiar la instrucción no.
_TIMING: Final = frozenset({"cadence", "local_time", "weekdays", "day_of_month", "run_date"})

__all__ = [
    "MAX_ACTIVE_PER_TENANT",
    "ScheduleError",
    "ScheduleInput",
    "archive",
    "create",
    "effective_state",
    "pause",
    "restore",
    "resume",
    "update",
]


class ScheduleError(Exception):
    """Un error que la consola sabe pintar: el código es el contrato."""

    def __init__(self, code: str, status: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ScheduleInput:
    agent_id: uuid.UUID
    name: str
    instruction: str
    cadence: str
    local_time: time
    weekdays: list[int] | None = None
    day_of_month: int | None = None
    run_date: date | None = None
    email: bool = False


def _validate(
    *,
    name: str,
    instruction: str,
    cadence: str,
    weekdays: list[int] | None,
    day_of_month: int | None,
    run_date: date | None,
) -> None:
    if cadence not in CADENCES:
        raise ScheduleError("unknown_cadence")
    if not name.strip():
        raise ScheduleError("name_required")
    if len(name) > 60:
        raise ScheduleError("name_too_long")
    if not instruction.strip():
        raise ScheduleError("instruction_required")
    if len(instruction) > 2000:
        raise ScheduleError("instruction_too_long")
    if cadence == "weekly" and not weekdays:
        raise ScheduleError("weekdays_required")
    if cadence == "weekly" and any(d not in range(7) for d in weekdays or []):
        raise ScheduleError("weekdays_out_of_range")
    if cadence == "monthly" and (day_of_month is None or not 1 <= day_of_month <= 28):
        raise ScheduleError("day_of_month_out_of_range")
    if cadence == "once" and run_date is None:
        raise ScheduleError("run_date_required")


async def _timezone(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    tz = await session.scalar(
        sa.text("SELECT timezone FROM tenants WHERE id = :t"), {"t": str(tenant_id)}
    )
    return str(tz or "UTC")


async def _agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await session.scalar(sa.select(Agent).where(Agent.id == agent_id))
    if agent is None:
        raise ScheduleError("agent_not_found", 404)
    return agent


async def _next_run(session: AsyncSession, schedule: Schedule) -> datetime | None:
    """La próxima, o ``None`` si la rutina no está para ejecutarse."""
    if schedule.state != "active":
        return None
    agent = await session.scalar(sa.select(Agent).where(Agent.id == schedule.agent_id))
    if agent is None or agent.lifecycle != ATTENDING:
        return None
    return when.next_run(
        cadence=schedule.cadence,
        local_time=schedule.local_time,
        timezone=await _timezone(session, schedule.tenant_id),
        weekdays=schedule.weekdays,
        day_of_month=schedule.day_of_month,
        run_date=schedule.run_date,
    )


def _audit(
    session: AsyncSession,
    schedule: Schedule,
    *,
    actor: str,
    action: str,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=schedule.tenant_id,
            actor=actor,
            action=action,
            target=f"schedule:{schedule.id}",
            after_json={"schedule_id": str(schedule.id), "name": schedule.name, **(after or {})},
        )
    )


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    data: ScheduleInput,
    created_by: str,
) -> Schedule:
    """Crea la rutina. Si su agente no atiende, **nace en pausa** y quien la
    crea tiene que poder decirlo en el momento (requisito 8.3)."""
    _validate(
        name=data.name,
        instruction=data.instruction,
        cadence=data.cadence,
        weekdays=data.weekdays,
        day_of_month=data.day_of_month,
        run_date=data.run_date,
    )
    agent = await _agent(session, data.agent_id)

    active = await session.scalar(
        sa.select(sa.func.count())
        .select_from(Schedule)
        .where(Schedule.tenant_id == tenant_id, Schedule.state == "active")
    )
    if (active or 0) >= MAX_ACTIVE_PER_TENANT:
        raise ScheduleError("limit_reached", 409)

    attending = agent.lifecycle == ATTENDING
    schedule = Schedule(
        tenant_id=tenant_id,
        agent_id=data.agent_id,
        name=data.name.strip(),
        instruction=data.instruction.strip(),
        cadence=data.cadence,
        weekdays=list(data.weekdays) if data.cadence == "weekly" else None,
        day_of_month=data.day_of_month if data.cadence == "monthly" else None,
        run_date=data.run_date if data.cadence == "once" else None,
        local_time=data.local_time,
        email=data.email,
        state="active" if attending else "paused",
        pause_reason=None if attending else "agent_unavailable",
        created_by=created_by,
    )
    session.add(schedule)
    await session.flush()

    schedule.next_run_at = await _next_run(session, schedule)
    if schedule.cadence == "once" and attending and schedule.next_run_at is None:
        # La fecha ya pasó: no se guarda una rutina que no va a ejecutarse nunca.
        raise ScheduleError("run_date_in_the_past")
    _audit(
        session,
        schedule,
        actor=created_by,
        action="schedule.create",
        after={"born": schedule.state},
    )
    await session.flush()
    return schedule


async def update(session: AsyncSession, schedule: Schedule, **changes: Any) -> Schedule:
    """Cambia lo que se puede cambiar. La próxima solo se recalcula si cambió
    algo del cuándo: editar la instrucción no mueve la hora."""
    merged = {
        "name": schedule.name,
        "instruction": schedule.instruction,
        "cadence": schedule.cadence,
        "weekdays": schedule.weekdays,
        "day_of_month": schedule.day_of_month,
        "run_date": schedule.run_date,
        **changes,
    }
    _validate(
        name=merged["name"],
        instruction=merged["instruction"],
        cadence=merged["cadence"],
        weekdays=merged["weekdays"],
        day_of_month=merged["day_of_month"],
        run_date=merged["run_date"],
    )
    for field, value in changes.items():
        setattr(schedule, field, value)
    # Cada periodicidad deja nulo lo que no es suyo, como pide el CHECK.
    schedule.weekdays = schedule.weekdays if schedule.cadence == "weekly" else None
    schedule.day_of_month = schedule.day_of_month if schedule.cadence == "monthly" else None
    schedule.run_date = schedule.run_date if schedule.cadence == "once" else None

    if _TIMING & set(changes):
        schedule.next_run_at = await _next_run(session, schedule)
    await session.flush()
    return schedule


async def pause(
    session: AsyncSession,
    schedule: Schedule,
    *,
    reason: str = "manual",
    actor: str = "system",
) -> Schedule:
    """Para la rutina con su motivo escrito. Una pausa del sistema no pisa la
    de una persona: si alguien la paró a mano, sigue parada a mano."""
    if schedule.state == "archived":
        return schedule
    if schedule.state == "paused" and schedule.pause_reason == "manual" and reason != "manual":
        return schedule
    schedule.state = "paused"
    schedule.pause_reason = reason
    schedule.next_run_at = None
    _audit(session, schedule, actor=actor, action="schedule.pause", after={"reason": reason})
    await session.flush()
    return schedule


async def resume(
    session: AsyncSession,
    schedule: Schedule,
    *,
    system_reason: str | None = None,
    actor: str = "system",
) -> Schedule:
    """Reanuda. ``system_reason`` es la reanudación del sistema: solo deshace
    **su** pausa, nunca la de una persona (requisito 15.3)."""
    if schedule.state != "paused":
        return schedule
    if system_reason is not None and schedule.pause_reason != system_reason:
        return schedule
    if system_reason is None and schedule.pause_reason in SYSTEM_PAUSE_REASONS:
        # Una persona puede reanudar lo que paró el sistema, pero conviene que
        # quede dicho que fue una persona.
        pass
    schedule.state = "active"
    schedule.pause_reason = None
    schedule.consecutive_failures = 0
    schedule.next_run_at = await _next_run(session, schedule)
    _audit(session, schedule, actor=actor, action="schedule.resume")
    await session.flush()
    return schedule


async def archive(session: AsyncSession, schedule: Schedule, *, actor: str) -> Schedule:
    """Retira la rutina. El historial se queda para consultarlo: no se borra
    nada (constitución §IV)."""
    schedule.state = "archived"
    schedule.pause_reason = None
    schedule.next_run_at = None
    _audit(session, schedule, actor=actor, action="schedule.archive")
    await session.flush()
    return schedule


async def restore(session: AsyncSession, schedule: Schedule, *, actor: str) -> Schedule:
    """Saca la rutina del archivo y la deja **en pausa**: si volviera sola,
    volvería gastando, y nadie habría mirado su hora (requisito 15.5)."""
    if schedule.state != "archived":
        return schedule
    schedule.state = "paused"
    schedule.pause_reason = "manual"
    schedule.next_run_at = None
    _audit(session, schedule, actor=actor, action="schedule.restore")
    await session.flush()
    return schedule


async def effective_state(
    session: AsyncSession,
    schedule: Schedule,
    *,
    bag_empty: bool | None = None,
) -> tuple[str, str | None]:
    """Lo que de verdad va a pasar, que es lo que se enseña: la intención del
    partner cruzada con el agente y con el saldo.

    ``bag_empty`` lo pone quien llama, que es el único que tiene el contexto
    del partner para leer la bolsa. Sin él, solo se mira el agente.
    """
    if schedule.state == "archived":
        return "archived", None
    if schedule.state == "paused":
        return "paused", schedule.pause_reason
    agent = await session.scalar(sa.select(Agent).where(Agent.id == schedule.agent_id))
    if agent is None or agent.lifecycle != ATTENDING:
        return "paused", "agent_unavailable"
    if bag_empty:
        return "paused", "no_balance"
    return "active", None


async def due_now(
    session: AsyncSession, schedule: Schedule, *, now: datetime | None = None
) -> bool:
    """Si a esta rutina le toca ya. Lo usa el disparador después de leer la
    fila con su cliente puesto."""
    moment = now or datetime.now(UTC)
    return schedule.next_run_at is not None and schedule.next_run_at <= moment
