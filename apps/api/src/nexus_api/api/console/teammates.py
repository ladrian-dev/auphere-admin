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
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_allowlist import read_allowlist
from nexus_api.core.partner_context import apply_partner_to_session, partner_context
from nexus_api.db.models import JOB_SEED, AuditLog, PartnerMembership, Teammate
from nexus_api.db.models.companion import (
    RUN_PAUSED,
    RUN_RUNNING,
    CompanionMessage,
    CompanionRun,
    CompanionThread,
    TeammateTask,
)
from nexus_api.repositories.teammate_tasks import TeammateTaskRepository
from nexus_api.repositories.teammates import TeammateChangeRepository, TeammateRepository
from nexus_api.services.local_exec_policy import LocalExecPolicyRepository, resolve
from nexus_api.services.model_choices import model_choices
from nexus_api.services.teammate_catalog import (
    ToolNotInCatalog,
    permissions_to_tool_names,
    validate_tool_names,
)
from nexus_api.services.teammate_inbox import inbox_events, list_inbox

from .schemas_teammates import (
    InboxItemOut,
    JobsOut,
    ModelChoiceOut,
    TaskOut,
    TeammateChangeOut,
    TeammateIn,
    TeammateOut,
    TeammatePatchIn,
    TeammateRefOut,
    TeammatesUsageOut,
    TeammateUsageRowOut,
)
from .schemas_workstation import (
    LocalExecPolicyOut,
    LocalExecPrefIn,
    LocalExecPrefOut,
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
    """La semilla de oficios y los modelos que el partner puede elegir.

    Cada modelo llega con **nota y coste** porque elegir un cerebro sin saber
    qué gasta es elegir a ciegas; el coste es una etiqueta relativa dentro de
    esta misma oferta (``services/model_choices.py``), no un precio.
    """
    models = [
        ModelChoiceOut(id=model_id, note=note, cost_label=cost)
        for model_id, note, cost in await model_choices(scope.session, scope.principal.partner.id)
    ]
    return JobsOut(jobs=list(JOB_SEED), models=models)


def _unknown_teammate() -> HTTPException:
    """404 opaco: un id de otro partner no existe, no «no puedes»."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown teammate")


def _refuse(code: str, **extra: object) -> HTTPException:
    """422 con vocabulario cerrado. La pantalla escribe la frase."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": code, **extra}
    )


async def _catalogue_for(scope: TeammatesScope, permissions: dict[str, Any]) -> list[str]:
    """Los interruptores → el catálogo, validado contra ``ALL_TOOLS``.

    La validación no es ceremonia aunque desde el formulario sea inalcanzable:
    es lo que impide que un cambio del mapeo publique en silencio un teammate
    con menos herramientas de las que su pantalla promete (garantía 2).
    """
    try:
        return validate_tool_names(permissions_to_tool_names(permissions))
    except ToolNotInCatalog as exc:
        raise _refuse("tool_not_in_catalog", names=exc.names) from exc


async def _check_model(scope: TeammatesScope, model: str) -> None:
    """El modelo tiene que estar en la lista del partner (la misma que la
    consola usa para ``respond``): la app no amplía la oferta."""
    allowed = await read_allowlist(scope.session, scope.principal.partner.id)
    if model not in allowed:
        raise _refuse("model_not_allowed", model=model)


@router.post("", response_model=TeammateOut, status_code=status.HTTP_201_CREATED)
async def create_teammate(
    body: TeammateIn,
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> TeammateOut:
    """Crea un teammate del partner (Requisitos 2.1 y 2.2).

    Lo crea **cualquiera** que pueda usar teammates: no hay roles de agente
    (decisión 7). Y el catálogo lo deriva la API de los cinco interruptores —
    el cuerpo no tiene dónde traer una herramienta, y si la trajera no se
    miraría.
    """
    permissions = body.permissions.model_dump()
    await _check_model(scope, body.model)
    tool_names = await _catalogue_for(scope, permissions)
    teammate = await TeammateRepository(scope.session).create(
        partner_id=scope.principal.partner.id,
        name=body.name,
        job=body.job,
        model=body.model,
        tool_names=tool_names,
        permissions=permissions,
        local_exec=body.local_exec,
        created_by=scope.principal.user_id,
    )
    _audit(scope, "teammate.created", teammate, job=teammate.job, model=teammate.model)
    return await _out(scope.session, teammate)


@router.patch("/{teammate_id}", response_model=TeammateOut)
async def update_teammate(
    teammate_id: uuid.UUID,
    body: TeammatePatchIn,
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> TeammateOut:
    """Cambia un teammate y **anota el cambio** (Requisitos 2.3 y 2.4).

    Un archivado no se cambia: dejar editarlo sugeriría que puede volver, y
    volver no es cambiar sino crear. Los cambios que tocan lo que el teammate
    *puede hacer* dejan una nota que el hilo de cada persona pinta al cargar —
    derivada, no copiada, porque escribirla en el hilo de otra persona exigiría
    romper la RLS que lo hace privado (0090).
    """
    repo = TeammateRepository(scope.session)
    teammate = await repo.get_active(teammate_id)
    if teammate is None:
        raise _unknown_teammate()

    changes: dict[str, Any] = {}
    if body.name is not None and body.name != teammate.name:
        changes["name"] = body.name
    if body.job is not None and body.job != teammate.job:
        changes["job"] = body.job
    if body.model is not None and body.model != teammate.model:
        await _check_model(scope, body.model)
        changes["model"] = body.model
    if body.local_exec is not None and body.local_exec != teammate.local_exec:
        changes["local_exec"] = body.local_exec
    if body.permissions is not None:
        permissions = body.permissions.model_dump()
        if permissions != dict(teammate.permissions):
            changes["permissions"] = permissions
            changes["tool_names"] = await _catalogue_for(scope, permissions)

    if changes:
        await repo.update(teammate, **changes)
        noted = await TeammateChangeRepository(scope.session).add(
            partner_id=scope.principal.partner.id,
            teammate_id=teammate.id,
            fields=list(changes),
            changed_by=scope.principal.user_id,
            changed_by_label=scope.principal.membership.display_name,
        )
        _audit(
            scope,
            "teammate.updated",
            teammate,
            fields=sorted(changes),
            noted=noted is not None,
        )
    return await _out(scope.session, teammate)


@router.get("/{teammate_id}/changes", response_model=list[TeammateChangeOut])
async def teammate_changes(
    teammate_id: uuid.UUID,
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> list[TeammateChangeOut]:
    """Las notas de este teammate, del partner (Requisito 2.4).

    El hilo las intercala por hora con sus runs, así que quien no estaba
    mirando ve el cambio donde ocurrió. Solo dice **qué campos** cambiaron y
    quién: los valores viejos no se guardan, y la pantalla ya enseña los de hoy.
    """
    if await TeammateRepository(scope.session).get(teammate_id) is None:
        raise _unknown_teammate()
    rows = await TeammateChangeRepository(scope.session).for_teammate(teammate_id)
    return [
        TeammateChangeOut(
            id=row.id,
            fields=list(row.fields),
            by=row.changed_by_label,
            at=row.changed_at,
        )
        for row in rows
    ]


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


# ── el consumo (Requisitos 8.1 y 9.1) ──────────────────────────────────


@router.get("/usage", response_model=TeammatesUsageOut)
async def usage(
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> TeammatesUsageOut:
    """El consumo del mes: el medidor del partner y el reparto por teammate.

    ``budget`` se calcula con **la misma función** que ``/console/companion/budget``
    —no con una copia parecida— porque R9.1 dice un medidor y dos implementaciones
    empiezan iguales y acaban discrepando en un redondeo.

    El reparto suma los runs de **todas** las personas del partner, como el
    medidor: el roster es del partner, así que «lo que gastó Sofía» es lo que
    gastó el equipo con Sofía. La RLS de ``companion.runs`` cuelga de la persona,
    de modo que se recorre membresía a membresía reapuntando ``app.principal_id``
    dentro de la misma transacción; no hay atajo que valga aquí, porque saltarse
    la RLS para «ver todo» es exactamente lo que la garantía impide.
    """
    from nexus_api.api.console.companion import budget_out, sum_partner_companion_tokens

    # ``month_window`` vive en el playground, que fue quien primero necesitó un
    # mes natural; el Companion lo importa de allí. Se toma de su casa y no de
    # rebote, que es lo que mypy pide con razón: un re-export implícito se
    # rompe el día que el intermediario deja de usarlo.
    from nexus_api.api.console.playground import month_window
    from nexus_api.core.principal_context import apply_principal_to_session

    partner = scope.principal.partner
    window = month_window()

    names = {
        row.id: row.name
        for row in await TeammateRepository(scope.session).list_active(include_archived=True)
    }
    members = list(
        (
            await scope.session.execute(
                sa.select(PartnerMembership.user_id).where(
                    PartnerMembership.partner_id == partner.id
                )
            )
        ).scalars()
    )
    totals: dict[uuid.UUID, list[int]] = {}
    stmt = (
        sa.select(
            CompanionRun.teammate_id,
            sa.func.coalesce(sa.func.sum(sa.func.coalesce(CompanionRun.input_tokens, 0)), 0),
            sa.func.coalesce(sa.func.sum(sa.func.coalesce(CompanionRun.output_tokens, 0)), 0),
            sa.func.count(),
        )
        .where(
            CompanionRun.teammate_id.is_not(None),
            CompanionRun.started_at >= window.start,
            CompanionRun.started_at < window.next_start,
        )
        .group_by(CompanionRun.teammate_id)
    )
    for user_id in members:
        await apply_principal_to_session(scope.session, user_id)
        for teammate_id, tokens_in, tokens_out, runs in (await scope.session.execute(stmt)).all():
            row = totals.setdefault(teammate_id, [0, 0, 0])
            row[0] += int(tokens_in or 0)
            row[1] += int(tokens_out or 0)
            row[2] += int(runs or 0)
    # La transacción se deja como estaba: los dos GUC de esta petición.
    await apply_partner_to_session(scope.session, partner.id, principal_id=scope.principal.user_id)

    used = await sum_partner_companion_tokens(scope.session, partner.id, window)
    return TeammatesUsageOut(
        budget=budget_out(used, partner.companion_monthly_token_cap, window),
        by_teammate=[
            TeammateUsageRowOut(
                teammate_id=teammate_id,
                # Un teammate archivado sigue habiendo gastado: se le nombra.
                name=names.get(teammate_id, "—"),
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                runs=runs,
            )
            for teammate_id, (tokens_in, tokens_out, runs) in sorted(
                totals.items(), key=lambda item: -(item[1][0] + item[1][1])
            )
        ],
    )


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


# ── la política de ejecución local, del lado de la persona (R10.1, 10.3) ─
#
# El **techo** vive en la página de equipo de la consola (`/console/team/...`):
# es una decisión de seguridad del partner. Aquí solo está lo que cada persona
# decide para sí misma, y solo puede restringir lo que el techo permite.


def _policy_out(ceiling: str, rows: list[object]) -> LocalExecPolicyOut:
    by_key = {getattr(row, "executable", None): getattr(row, "mode", "ask") for row in rows}
    global_mode = by_key.get(None, "ask")
    overall = resolve(ceiling=ceiling, global_pref=global_mode, executable_pref=None)
    per_executable = []
    for executable, mode in sorted(by_key.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        if executable is None:
            continue
        one = resolve(ceiling=ceiling, global_pref=global_mode, executable_pref=mode)
        per_executable.append(
            LocalExecPrefOut(
                executable=executable, mode=mode, effective=one.mode, capped=one.capped
            )
        )
    return LocalExecPolicyOut(
        ceiling=ceiling,
        global_mode=global_mode,
        per_executable=per_executable,
        effective=overall.mode,
        capped=overall.capped,
    )


@router.get("/local-exec-prefs", response_model=LocalExecPolicyOut)
async def local_exec_prefs(
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> LocalExecPolicyOut:
    """Lo que esta persona prefiere y **cómo queda** con el techo del partner."""
    repo = LocalExecPolicyRepository(scope.session)
    # Ausente = sin restricción (ver `local_exec_policy.resolve`).
    ceiling = await repo.ceiling(scope.principal.partner.id) or "always"
    rows = await repo.prefs(principal_id=scope.principal.user_id)
    return _policy_out(ceiling, list(rows))


@router.put("/local-exec-prefs", response_model=LocalExecPolicyOut)
async def set_local_exec_pref(
    body: LocalExecPrefIn,
    scope: TeammatesScope = Depends(teammates_scope("teammates:use")),
) -> LocalExecPolicyOut:
    """Guarda la preferencia. **Se guarda tal cual**, aunque el techo la baje.

    Bajarla al guardar sería perder lo que la persona quiso: si mañana el
    partner sube el techo, su elección tiene que seguir ahí. Lo que la pantalla
    enseña es ``effective`` y ``capped`` (Requisito 10.4).
    """
    repo = LocalExecPolicyRepository(scope.session)
    await repo.set_pref(
        partner_id=scope.principal.partner.id,
        principal_id=scope.principal.user_id,
        executable=body.executable,
        mode=body.mode,
    )
    scope.session.add(
        AuditLog(
            tenant_id=None,
            actor=scope.principal.actor,
            action="local_policy.pref_changed",
            target=f"partner:{scope.principal.partner.id}",
            after_json={"executable": body.executable or "*", "mode": body.mode},
        )
    )
    # Ausente = sin restricción (ver `local_exec_policy.resolve`).
    ceiling = await repo.ceiling(scope.principal.partner.id) or "always"
    rows = await repo.prefs(principal_id=scope.principal.user_id)
    return _policy_out(ceiling, list(rows))
