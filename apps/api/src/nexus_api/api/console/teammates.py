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
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_allowlist import read_allowlist
from nexus_api.core.partner_context import apply_partner_to_session, partner_context
from nexus_api.core.respond_catalog import RESPOND_MODELS
from nexus_api.db.models import JOB_SEED, Teammate
from nexus_api.db.models.companion import (
    RUN_PAUSED,
    RUN_RUNNING,
    CompanionMessage,
    CompanionRun,
    CompanionThread,
)
from nexus_api.repositories.teammates import TeammateRepository

from .schemas_teammates import JobsOut, ModelChoiceOut, TeammateOut

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
