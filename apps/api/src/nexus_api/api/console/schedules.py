"""Las rutinas en la consola — spec 082, T012 (requisitos 1.2, 2, 3.6, 11 y 14;
``contracts/console-api.md``).

- ``GET    /console/clients/{ref}/schedules`` [``schedules:read``] — la lista con
  sus filtros (``?agent=``, ``?state=``) y las cuentas de cada uno;
- ``POST   …/schedules`` [``schedules:write``] — el alta;
- ``POST   …/schedules/preview`` [``schedules:read``] — las próximas ejecuciones
  antes de guardar, sin escribir nada;
- ``GET    …/schedules/{id}`` · ``PATCH …/schedules/{id}``;
- ``POST   …/schedules/{id}/pause`` · ``/resume`` · ``/archive`` · ``/restore``;
- ``GET    …/schedules/{id}/runs`` [``schedules:read``] — el hilo, paginado por
  cursor y la más reciente arriba.

**No hay ``DELETE``**, y no es un olvido: borrar no existe, se archiva
(constitución §IV). La ruta del detalle responde 405 a quien lo intente.

El estado que viaja es **el efectivo**: la intención del partner ya cruzada con
el agente, que es lo que la pantalla tiene que pintar. La fila sigue guardando
la intención, y por eso una rutina de un agente en pausa vuelve sola cuando el
agente vuelve.

Lo que gasta cada rutina viaja en crudo (``month.cost_micros``, cien milésimas
de USD, como las guarda la ejecución). La conversión a la moneda de la bolsa y
la partida de Consumo llegan con su propia tarea, y hasta entonces ``spend`` va
en ``null`` antes que mentir con un cero.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime, time
from typing import Annotated, Any, Literal, cast

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.db.models import Agent, ClientWalletEntry, Schedule, ScheduleRun
from nexus_api.services import jobs as jobs_service
from nexus_api.services.schedules import runs as runs_service
from nexus_api.services.schedules import service, when
from nexus_api.services.wallet.schedules import ENTRY_KIND, usage_ref_for

from .deps import ClientScope, client_scope

router = APIRouter(prefix="/clients/{ref}/schedules")
#: «Probar ahora» cuelga del agente, no de una rutina: todavía no hay ninguna.
try_router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}/schedules/try")
#: El tipo de trabajo que ejecuta una rutina.
SCHEDULE_JOB = "schedule_run"

Cadence = Literal["daily", "weekly", "monthly", "once"]
State = Literal["active", "paused", "archived"]


class ScheduleWhenOut(BaseModel):
    cadence: Cadence
    local_time: time
    weekdays: list[int] | None = None
    day_of_month: int | None = None
    run_date: date | None = None


class ScheduleAgentOut(BaseModel):
    id: uuid.UUID
    name: str
    #: ``attending`` o la vida del agente tal cual: la pantalla lo traduce.
    state: str


class ScheduleMonthOut(BaseModel):
    """Lo que la rutina lleva hecho este mes.

    **Sin cifra de dinero todavía, y a propósito.** El partner ve precios,
    nunca costes (C9): lo que puede ver es lo que salió de la bolsa de su
    cliente, que es un asiento, no lo que nos costó el modelo. Llega como
    ``{amount_micros, currency}`` con la tarea del cobro.
    """

    runs: int


class ScheduleOut(BaseModel):
    id: uuid.UUID
    name: str
    instruction: str
    agent: ScheduleAgentOut
    when: ScheduleWhenOut
    next_run_at: datetime | None
    state: State
    pause_reason: str | None
    email: bool
    created_by: str
    created_at: datetime
    month: ScheduleMonthOut


class ScheduleCountsOut(BaseModel):
    all: int
    active: int
    paused: int
    archived: int


class ScheduleListOut(BaseModel):
    timezone: str
    counts: ScheduleCountsOut
    #: El reparto de la bolsa llega con la partida de Consumo.
    spend: None = None
    schedules: list[ScheduleOut]


class ScheduleMoneyOut(BaseModel):
    """Lo que salió de la bolsa del cliente, en su moneda.

    Es un **precio**, no un coste: el asiento de la bolsa, el mismo que suma la
    partida de Consumo. Lo que nos costó el modelo no sale de aquí (C9).
    """

    amount_micros: int
    currency: str


class ScheduleRunOut(BaseModel):
    id: uuid.UUID
    scheduled_for: datetime
    trigger: str
    status: str
    attempts: int
    duration_ms: int | None
    #: ``None`` mientras no se haya cobrado: un cero diría que fue gratis.
    spend: ScheduleMoneyOut | None
    answer: str | None
    tools_used: list[Any]
    withheld: list[Any] | None
    error_code: str | None
    #: La de ese momento, no la de ahora: editar la rutina no reescribe lo
    #: ya contestado (requisito 15.2).
    instruction: str


class ScheduleRunsOut(BaseModel):
    runs: list[ScheduleRunOut]
    next_cursor: str | None = None


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: uuid.UUID
    name: str = Field(max_length=60)
    instruction: str = Field(max_length=2000)
    cadence: Cadence
    local_time: time
    weekdays: list[int] | None = None
    day_of_month: int | None = None
    run_date: date | None = None
    email: bool = False


class SchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=60)
    instruction: str | None = Field(default=None, max_length=2000)
    cadence: Cadence | None = None
    local_time: time | None = None
    weekdays: list[int] | None = None
    day_of_month: int | None = None
    run_date: date | None = None
    email: bool | None = None


class SchedulePreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cadence: Cadence
    local_time: time
    weekdays: list[int] | None = None
    day_of_month: int | None = None
    run_date: date | None = None


class SchedulePreviewOut(BaseModel):
    next: list[datetime]
    timezone: str


def _encode_cursor(scheduled_for: datetime, id_: uuid.UUID) -> str:
    raw = f"{scheduled_for.isoformat()}|{id_}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Un cursor que no se entiende es un 422, no una página vacía: lo segundo
    le diría al partner que no hay historial cuando sí lo hay."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        text = base64.urlsafe_b64decode(padded.encode()).decode()
        ts, id_ = text.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except Exception:
        raise HTTPException(status_code=422, detail="bad_cursor") from None


def _refused(exc: service.ScheduleError) -> HTTPException:
    """El código del servicio es el contrato con la consola, no una frase."""
    return HTTPException(status_code=exc.status, detail=exc.code)


async def _month_of(scope: ClientScope, schedule_id: uuid.UUID) -> ScheduleMonthOut:
    since = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    runs = await scope.session.scalar(
        sa.select(sa.func.count()).where(
            ScheduleRun.schedule_id == schedule_id,
            ScheduleRun.scheduled_for >= since,
        )
    )
    return ScheduleMonthOut(runs=int(runs or 0))


async def _out(scope: ClientScope, schedule: Schedule) -> ScheduleOut:
    agent = await scope.session.get(Agent, schedule.agent_id)
    state, reason = await service.effective_state(scope.session, schedule)
    return ScheduleOut(
        id=schedule.id,
        name=schedule.name,
        instruction=schedule.instruction,
        agent=ScheduleAgentOut(
            id=schedule.agent_id,
            name=agent.name if agent else "",
            state="attending" if agent and agent.lifecycle == service.ATTENDING else "paused",
        ),
        when=ScheduleWhenOut(
            # La base guarda texto con su CHECK: el vocabulario es el mismo que
            # el del tipo, y el ``cast`` dice que aquí termina esa frontera.
            cadence=cast(Cadence, schedule.cadence),
            local_time=schedule.local_time,
            weekdays=schedule.weekdays,
            day_of_month=schedule.day_of_month,
            run_date=schedule.run_date,
        ),
        next_run_at=schedule.next_run_at,
        state=cast(State, state),
        pause_reason=reason,
        email=schedule.email,
        created_by=schedule.created_by,
        created_at=schedule.created_at,
        month=await _month_of(scope, schedule.id),
    )


async def _find(scope: ClientScope, schedule_id: uuid.UUID) -> Schedule:
    schedule = await scope.session.scalar(sa.select(Schedule).where(Schedule.id == schedule_id))
    if schedule is None:
        raise HTTPException(status_code=404, detail="not_found")
    return schedule


@router.get("", response_model=ScheduleListOut)
async def list_schedules(
    agent: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[State | None, Query()] = None,
    scope: ClientScope = Depends(client_scope("schedules:read")),
) -> ScheduleListOut:
    rows = (
        await scope.session.scalars(
            sa.select(Schedule)
            .where(*([Schedule.agent_id == agent] if agent else []))
            .order_by(Schedule.created_at.desc())
        )
    ).all()
    out = [await _out(scope, row) for row in rows]
    counts = ScheduleCountsOut(
        all=len(out),
        active=sum(1 for s in out if s.state == "active"),
        paused=sum(1 for s in out if s.state == "paused"),
        archived=sum(1 for s in out if s.state == "archived"),
    )
    if state is not None:
        out = [s for s in out if s.state == state]
    return ScheduleListOut(timezone=scope.tenant.timezone, counts=counts, schedules=out)


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleIn,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> ScheduleOut:
    try:
        made = await service.create(
            scope.session,
            tenant_id=scope.tenant.id,
            data=service.ScheduleInput(**body.model_dump()),
            created_by=scope.principal.user_id,
        )
    except service.ScheduleError as exc:
        raise _refused(exc) from exc
    return await _out(scope, made)


@router.post("/preview", response_model=SchedulePreviewOut)
async def preview(
    body: SchedulePreviewIn,
    scope: ClientScope = Depends(client_scope("schedules:read")),
) -> SchedulePreviewOut:
    """Las próximas tres, ya resueltas en la zona del negocio. No escribe."""
    try:
        runs = when.next_runs(
            cadence=body.cadence,
            local_time=body.local_time,
            timezone=scope.tenant.timezone,
            weekdays=body.weekdays,
            day_of_month=body.day_of_month,
            run_date=body.run_date,
            count=3,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="unknown_cadence") from exc
    return SchedulePreviewOut(next=runs, timezone=scope.tenant.timezone)


@router.get("/{schedule_id}", response_model=ScheduleOut)
async def read_schedule(
    schedule_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("schedules:read")),
) -> ScheduleOut:
    return await _out(scope, await _find(scope, schedule_id))


@router.get("/{schedule_id}/runs", response_model=ScheduleRunsOut)
async def list_runs(
    schedule_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query()] = None,
    scope: ClientScope = Depends(client_scope("schedules:read")),
) -> ScheduleRunsOut:
    """El hilo de una rutina, la más reciente arriba.

    La rutina se busca primero: así el historial de otro cliente no existe, en
    vez de existir vacío.
    """
    await _find(scope, schedule_id)
    stmt = (
        sa.select(ScheduleRun)
        .where(ScheduleRun.schedule_id == schedule_id)
        .order_by(ScheduleRun.scheduled_for.desc(), ScheduleRun.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        c_at, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            sa.or_(
                ScheduleRun.scheduled_for < c_at,
                sa.and_(ScheduleRun.scheduled_for == c_at, ScheduleRun.id < c_id),
            )
        )
    rows = list((await scope.session.scalars(stmt)).all())
    page, has_more = rows[:limit], len(rows) > limit
    spent = await _spend_of(scope, [row.id for row in page])
    return ScheduleRunsOut(
        runs=[_run_out(row, spent.get(row.id)) for row in page],
        next_cursor=_encode_cursor(page[-1].scheduled_for, page[-1].id)
        if has_more and page
        else None,
    )


async def _spend_of(
    scope: ClientScope, run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ScheduleMoneyOut]:
    """Lo cobrado por cada ejecución, del libro de la bolsa.

    No se guarda en la fila de la ejecución a propósito: el cobro lo hace el
    medidor después de cerrarla, y dos sitios con la misma cifra terminan
    siendo dos cifras distintas.
    """
    if not run_ids:
        return {}
    by_ref = {usage_ref_for(run_id): run_id for run_id in run_ids}
    rows = (
        await scope.session.execute(
            sa.select(
                ClientWalletEntry.usage_ref,
                sa.func.sum(-ClientWalletEntry.amount_micros),
                ClientWalletEntry.currency,
            )
            .where(
                ClientWalletEntry.kind == ENTRY_KIND,
                ClientWalletEntry.usage_ref.in_(list(by_ref)),
            )
            .group_by(ClientWalletEntry.usage_ref, ClientWalletEntry.currency)
        )
    ).all()
    return {
        by_ref[str(ref)]: ScheduleMoneyOut(amount_micros=int(total or 0), currency=str(currency))
        for ref, total, currency in rows
        if str(ref) in by_ref
    }


def _run_out(row: ScheduleRun, spend: ScheduleMoneyOut | None) -> ScheduleRunOut:
    return ScheduleRunOut(
        id=row.id,
        scheduled_for=row.scheduled_for,
        trigger=row.trigger,
        status=row.status,
        attempts=row.attempts,
        duration_ms=row.duration_ms,
        spend=spend,
        answer=row.answer,
        tools_used=list(row.tools_used or []),
        withheld=row.withheld,
        error_code=row.error_code,
        instruction=row.instruction,
    )


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def patch_schedule(
    schedule_id: uuid.UUID,
    body: SchedulePatch,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> ScheduleOut:
    schedule = await _find(scope, schedule_id)
    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    if not changes:
        return await _out(scope, schedule)
    try:
        await service.update(scope.session, schedule, **changes)
    except service.ScheduleError as exc:
        raise _refused(exc) from exc
    return await _out(scope, schedule)


class RunQueuedOut(BaseModel):
    """Una ejecución encolada. ``schedule_id`` va a ``null`` en «Probar ahora»:
    ahí no hay rutina, y decirlo con un nulo es más honesto que inventar un id."""

    run_id: uuid.UUID | None
    job_id: uuid.UUID
    schedule_id: uuid.UUID | None


class TryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(max_length=2000)


async def _bag_has_money(scope: ClientScope) -> bool:
    from nexus_api.services.wallet.bags import balance_left

    left = await balance_left(scope.principal.partner.id, scope.tenant.id)
    return left is not None


@router.post(
    "/{schedule_id}/run", response_model=RunQueuedOut, status_code=status.HTTP_202_ACCEPTED
)
async def run_now(
    schedule_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> RunQueuedOut:
    """«Ejecutar ahora»: la misma ejecución que correría a su hora, con las
    mismas herramientas y el mismo cobro. Queda marcada como manual."""
    schedule = await _find(scope, schedule_id)
    if not await _bag_has_money(scope):
        raise HTTPException(status_code=409, detail="bag_empty")

    run = await runs_service.open_run(scope.session, schedule=schedule, trigger="manual")
    job = await jobs_service.create_job(
        scope.session,
        kind=SCHEDULE_JOB,
        agent_id=schedule.agent_id,
        created_by=scope.principal.user_id,
    )
    job.progress = {
        "step": None,
        "blocks": [],
        "input": runs_service.as_input(schedule.id, run.id),
    }
    run.job_id = job.id
    await scope.session.flush()
    jobs_service.enqueue_after_commit(scope.session, job)
    return RunQueuedOut(run_id=run.id, job_id=job.id, schedule_id=schedule.id)


@try_router.post("", response_model=RunQueuedOut, status_code=status.HTTP_202_ACCEPTED)
async def try_now(
    agent_id: uuid.UUID,
    body: TryIn,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> RunQueuedOut:
    """«Probar ahora» desde el alta, sin haber guardado (requisito 6.3).

    No crea rutina **ni ejecución**: la instrucción viaja en el trabajo y la
    respuesta vuelve en su resultado. El historial es de las rutinas que
    existen, y una prueba no es una de ellas.
    """
    if not body.instruction.strip():
        raise HTTPException(status_code=422, detail="instruction_required")
    if not await _bag_has_money(scope):
        raise HTTPException(status_code=409, detail="bag_empty")

    job = await jobs_service.create_job(
        scope.session,
        kind=SCHEDULE_JOB,
        agent_id=agent_id,
        created_by=scope.principal.user_id,
    )
    job.progress = {
        "step": None,
        "blocks": [],
        "input": {"agent_id": str(agent_id), "instruction": body.instruction.strip()},
    }
    await scope.session.flush()
    jobs_service.enqueue_after_commit(scope.session, job)
    return RunQueuedOut(run_id=None, job_id=job.id, schedule_id=None)


@router.post("/{schedule_id}/pause", response_model=ScheduleOut)
async def pause_schedule(
    schedule_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> ScheduleOut:
    schedule = await _find(scope, schedule_id)
    await service.pause(scope.session, schedule, reason="manual", actor=scope.principal.user_id)
    return await _out(scope, schedule)


@router.post("/{schedule_id}/resume", response_model=ScheduleOut)
async def resume_schedule(
    schedule_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> ScheduleOut:
    schedule = await _find(scope, schedule_id)
    await service.resume(scope.session, schedule, actor=scope.principal.user_id)
    return await _out(scope, schedule)


@router.post("/{schedule_id}/archive", response_model=ScheduleOut)
async def archive_schedule(
    schedule_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> ScheduleOut:
    schedule = await _find(scope, schedule_id)
    await service.archive(scope.session, schedule, actor=scope.principal.user_id)
    return await _out(scope, schedule)


@router.post("/{schedule_id}/restore", response_model=ScheduleOut)
async def restore_schedule(
    schedule_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("schedules:write")),
) -> ScheduleOut:
    schedule = await _find(scope, schedule_id)
    await service.restore(scope.session, schedule, actor=scope.principal.user_id)
    return await _out(scope, schedule)
