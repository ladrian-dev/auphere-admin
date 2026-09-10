"""``/console/teammates`` — el roster y lo que cada persona tiene con él (spec 003).

Reglas que se ven en cada ruta:

* Ninguna acepta ``partner_id`` ni ``principal_id``: salen de la sesión. La
  transacción lleva los dos GUC — el roster es de partner, el hilo de persona —
  y la RLS hace el resto (``test_31``, ``test_32``).
* «Archivar» nunca borra (la base revoca ``DELETE``).
* Lo derivado (``my_state``, ``my_unread``, ``last_done``) se calcula al leer,
  nunca se guarda: si el proceso que lo actualizaría muere, no queda mintiendo.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_allowlist import read_allowlist
from nexus_api.core.partner_context import apply_partner_to_session, partner_context
from nexus_api.core.respond_catalog import RESPOND_MODELS
from nexus_api.db.models import JOB_SEED, AuditLog, Teammate
from nexus_api.db.models.companion import (
    RUN_PAUSED,
    RUN_RUNNING,
    CompanionMessage,
    CompanionRun,
    CompanionThread,
    TeammateTask,
)
from nexus_api.repositories.teammate_tasks import TeammateTaskRepository
from nexus_api.repositories.teammates import TeammateRepository
from nexus_api.services.teammate_inbox import inbox_events, list_inbox

from .schemas_teammates import (
    InboxItemOut,
    JobsOut,
    ModelChoiceOut,
    TaskOut,
    TeammateOut,
    TeammateRefOut,
)

router = APIRouter(prefix="/teammates")

#: Spec 003, D3: el run cerrado aparcado. La constante vive aquí hasta la US2,
#: que la mueve al modelo con la tabla de tareas.
RUN_WAITING = "waiting"


@dataclass(frozen=True)
class TeammatesScope:
    principal: ConsolePrincipal
    session: AsyncSession


def teammates_scope(*required: str) -> Callable[..., AsyncIterator[TeammatesScope]]:
    """Transacción con los dos GUC: partner (roster) y persona (hilos)."""
    principal_dep = require_console_principal(*required)

    async def _dependency(
        principal: ConsolePrincipal = Depends(principal_dep),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[TeammatesScope]:
        async with session.begin():
            await apply_partner_to_session(
                session, principal.partner.id, principal_id=principal.user_id
            )
            with partner_context(str(principal.partner.id)):
                yield TeammatesScope(principal=principal, session=session)

    return _dependency


async def _my_view(
    session: AsyncSession, teammate_id: uuid.UUID
) -> tuple[str, bool, uuid.UUID | None]:
    """Lo que la persona tiene con este teammate. RLS por principal ya aplicada."""
    thread = (
        await session.execute(
            sa.select(CompanionThread)
            .where(
                CompanionThread.teammate_id == teammate_id, CompanionThread.archived_at.is_(None)
            )
            .order_by(CompanionThread.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if thread is None:
        return "en_espera", False, None
    last_run = (
        await session.execute(
            sa.select(CompanionRun)
            .where(CompanionRun.thread_id == thread.id)
            .order_by(CompanionRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last_run is None:
        return "en_espera", False, thread.id
    if last_run.status == RUN_RUNNING:
        return "en_marcha", False, thread.id
    if last_run.status == RUN_WAITING:
        return "esperandote", False, thread.id
    if last_run.status == RUN_PAUSED:
        return "en_pausa_por_tope", False, thread.id
    # Terminó: ¿contestó el teammate después del último mensaje de la persona?
    last_user_at = await session.scalar(
        sa.select(sa.func.max(CompanionMessage.created_at)).where(
            CompanionMessage.thread_id == thread.id, CompanionMessage.role == "user"
        )
    )
    unread = bool(
        last_run.ended_at is not None and (last_user_at is None or last_run.ended_at > last_user_at)
    )
    return "en_espera", unread, thread.id


async def _out(session: AsyncSession, row: Teammate) -> TeammateOut:
    my_state, my_unread, thread_id = await _my_view(session, row.id)
    return TeammateOut(
        id=row.id,
        name=row.name,
        job=row.job,
        model=row.model,
        tool_names=list(row.tool_names),
        permissions=dict(row.permissions),
        local_exec=row.local_exec,
        status=row.status,
        created_at=row.created_at,
        archived_at=row.archived_at,
        my_state=my_state,
        my_unread=my_unread,
        my_thread_id=thread_id,
        last_done=None,
    )


@router.get("", response_model=list[TeammateOut])
async def list_teammates(
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
    include_archived: bool = Query(default=False),
) -> list[TeammateOut]:
    rows = await TeammateRepository(scope.session).list_active(include_archived=include_archived)
    return [await _out(scope.session, row) for row in rows]


@router.get("/jobs", response_model=JobsOut)
async def jobs(scope: TeammatesScope = Depends(teammates_scope("teammates:use"))) -> JobsOut:
    """La semilla de oficios y los modelos que el partner puede elegir."""
    allowed = await read_allowlist(scope.session, scope.principal.partner.id)
    models = [
        ModelChoiceOut(id=model_id, note=display, cost_label="")
        for model_id, display in RESPOND_MODELS
        if model_id in allowed
    ]
    return JobsOut(jobs=list(JOB_SEED), models=models)


def _unknown_teammate() -> HTTPException:
    """404 opaco: un id de otro partner no existe, no «no puedes»."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown teammate")


def _audit(scope: TeammatesScope, action: str, teammate: Teammate, **after: object) -> None:
    """La persona es el actor. Un teammate nunca lo es (Requisito 13.1)."""
    scope.session.add(
        AuditLog(
            tenant_id=None,
            actor=scope.principal.actor,
            action=action,
            target=f"teammate:{teammate.id}",
            after_json={"teammate": teammate.name, "teammate_id": str(teammate.id), **after},
        )
    )


@router.delete("/{teammate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_teammate(
    teammate_id: uuid.UUID,
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> None:
    """Archiva un teammate. **Nunca borra** (Requisito 2.6): sus hilos quedan
    legibles y lo que estaba esperando se cierra diciendo por qué."""
    repo = TeammateRepository(scope.session)
    teammate = await repo.get_active(teammate_id)
    if teammate is None:
        raise _unknown_teammate()
    await TeammateTaskRepository(scope.session).cancel_for_teammate(teammate_id)
    await repo.archive(teammate)
    _audit(scope, "teammate.archived", teammate)


# ── la tarea (Requisitos 3.2 y 6) ──────────────────────────────────────


def _task_out(task: TeammateTask) -> TaskOut:
    return TaskOut(
        id=task.id,
        thread_id=task.thread_id,
        teammate_id=task.teammate_id,
        title=task.title,
        state=task.state,
        expires_at=task.expires_at,
        current_run_id=task.current_run_id,
        pending_action_id=task.pending_action_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
        ended_at=task.ended_at,
    )


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
    state: str | None = Query(default=None),
) -> list[TaskOut]:
    """Las tareas de **esta** persona. La RLS cuelga del hilo (0090 + 0111)."""
    rows = await TeammateTaskRepository(scope.session).mine(state=state)
    return [_task_out(task) for task in rows]


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(
    task_id: uuid.UUID,
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> TaskOut:
    """Cancela una tarea propia. Lo que esperaba se cierra con su motivo."""
    repo = TeammateTaskRepository(scope.session)
    task = await repo.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown task")
    if task.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "task_terminal", "detail": f"This task is already {task.state}."},
        )
    return _task_out(await repo.cancel(task))


# ── Pendientes (Requisito 5) ───────────────────────────────────────────


@router.get("/inbox", response_model=list[InboxItemOut])
async def inbox(
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> list[InboxItemOut]:
    """Lo que los teammates de esta persona esperan de ella.

    **No** incluye lo que el Companion de la consola propone: son dos
    superficies y la persona decide cada una donde está (supuesto cerrado).
    """
    items = await list_inbox(
        scope.session,
        partner_id=scope.principal.partner.id,
        permissions=scope.principal.permissions,
    )
    return [
        InboxItemOut(
            action_id=item.action_id,
            task_id=item.task_id,
            thread_id=item.thread_id,
            run_id=item.run_id,
            teammate=TeammateRefOut(id=uuid.UUID(item.teammate["id"]), name=item.teammate["name"]),
            title=item.title,
            kind=item.kind,
            level=item.level,
            client_ref=item.client_ref,
            proposed_at=item.proposed_at,
            can_decide=item.can_decide,
        )
        for item in items
    ]


@router.get("/inbox/stream")
async def inbox_stream(
    principal: ConsolePrincipal = Depends(require_console_principal("teammates:use")),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """El aviso de que algo dejó de esperar. La lógica vive en el servicio,
    que se prueba sin HTTP: un flujo infinito no cabe en un cliente de test."""
    return StreamingResponse(
        inbox_events(redis, principal.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
