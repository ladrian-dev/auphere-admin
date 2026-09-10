"""La tarea de un teammate — spec 003, Requisitos 3.2 y 6.

Todo método exige el GUC del principal ya aplicado (``apply_principal_to_session``):
la RLS de ``companion.teammate_tasks`` cuelga del hilo, así que sin él no entra
ni sale nada — que es lo que se quiere.

La única excepción es ``expire_due``, que es el barrido y corre **sin persona**:
va por la tabla entera con el rol de la aplicación, porque nadie tiene sesión a
las tres de la mañana. Por eso vive aquí y no en una ruta.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.companion.tools.actions import STATUS_EXPIRED, STATUS_PROPOSED
from nexus_api.db.models.companion import (
    TASK_CADUCADA,
    TASK_CANCELADA,
    TASK_EN_MARCHA,
    TASK_ESPERANDOTE,
    TASK_PAUSADA,
    TASK_TERMINADA,
    TERMINAL_TASK_STATES,
    CompanionAction,
    CompanionThread,
    TeammateTask,
)

#: Lo que se enseña como título cuando el encargo es muy largo.
TITLE_MAX = 120


def title_from(prompt: str) -> str:
    """La primera línea del encargo. Es lo que la persona escribió, recortado."""
    first = next((line.strip() for line in prompt.splitlines() if line.strip()), "")
    return (first[: TITLE_MAX - 1] + "…") if len(first) > TITLE_MAX else (first or "Tarea")


class TeammateTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open_or_continue(
        self,
        *,
        thread_id: uuid.UUID,
        teammate_id: uuid.UUID,
        principal_id: str,
        prompt: str,
        ttl_days: int,
    ) -> TeammateTask:
        """La tarea viva del hilo, o una nueva.

        Un hilo tiene **como mucho una tarea viva**: encargar algo mientras el
        teammate sigue con lo anterior es seguir la misma tarea, no abrir otra.
        Lo contrario dejaría dos cosas «esperándote» sobre la misma
        conversación y la bandeja mentiría sobre cuánto falta.
        """
        live = await self.live_of_thread(thread_id)
        now = datetime.now(UTC)
        if live is not None:
            live.expires_at = now + timedelta(days=ttl_days)
            live.updated_at = now
            await self._session.flush()
            return live
        task = TeammateTask(
            id=uuid.uuid4(),
            thread_id=thread_id,
            teammate_id=teammate_id,
            principal_id=principal_id,
            title=title_from(prompt),
            state=TASK_EN_MARCHA,
            expires_at=now + timedelta(days=ttl_days),
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def live_of_thread(self, thread_id: uuid.UUID) -> TeammateTask | None:
        return (
            await self._session.execute(
                sa.select(TeammateTask)
                .where(
                    TeammateTask.thread_id == thread_id,
                    TeammateTask.state.notin_(sorted(TERMINAL_TASK_STATES)),
                )
                .order_by(TeammateTask.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get(self, task_id: uuid.UUID) -> TeammateTask | None:
        return await self._session.get(TeammateTask, task_id)

    async def mine(self, *, state: str | None = None) -> Sequence[TeammateTask]:
        stmt = sa.select(TeammateTask).order_by(TeammateTask.updated_at.desc())
        if state is not None:
            stmt = stmt.where(TeammateTask.state == state)
        return (await self._session.execute(stmt)).scalars().all()

    # ── el ciclo de vida ───────────────────────────────────────────────

    async def running(
        self, task: TeammateTask, *, run_id: uuid.UUID, ttl_days: int
    ) -> TeammateTask:
        return await self._move(
            task, TASK_EN_MARCHA, run_id=run_id, pending=None, ttl_days=ttl_days
        )

    async def waiting(
        self, task: TeammateTask, *, action_id: uuid.UUID, ttl_days: int
    ) -> TeammateTask:
        """El turno cerró aparcado: la tarea es la que espera (Requisito 6.2)."""
        return await self._move(task, TASK_ESPERANDOTE, pending=action_id, ttl_days=ttl_days)

    async def paused(self, task: TeammateTask, *, ttl_days: int) -> TeammateTask:
        return await self._move(task, TASK_PAUSADA, pending=None, ttl_days=ttl_days)

    async def finished(self, task: TeammateTask, *, ttl_days: int) -> TeammateTask:
        return await self._move(task, TASK_TERMINADA, pending=None, ttl_days=ttl_days, ended=True)

    async def cancel(self, task: TeammateTask) -> TeammateTask:
        await self._close_pending_action(task, cause="cancelled")
        return await self._move(task, TASK_CANCELADA, pending=None, ended=True)

    async def cancel_for_teammate(self, teammate_id: uuid.UUID) -> int:
        """Archivar un teammate cierra lo suyo que esperaba (Requisito 2.6)."""
        tasks = (
            (
                await self._session.execute(
                    sa.select(TeammateTask).where(
                        TeammateTask.teammate_id == teammate_id,
                        TeammateTask.state.notin_(sorted(TERMINAL_TASK_STATES)),
                    )
                )
            )
            .scalars()
            .all()
        )
        for task in tasks:
            await self._close_pending_action(task, cause="teammate_archived")
            await self._move(task, TASK_CANCELADA, pending=None, ended=True)
        return len(tasks)

    async def expire_due(self, *, now: datetime | None = None, limit: int = 200) -> int:
        """El barrido: tareas vencidas → ``caducada``, y su acción cerrada.

        Corre **sin persona** (lo llama el cron del worker), así que no se apoya
        en la RLS: se hace con el rol de la aplicación, que ve la tabla entera.
        Cada acción cerrada dice por qué, para que el hilo pueda contarlo.
        """
        reference = now or datetime.now(UTC)
        tasks = (
            (
                await self._session.execute(
                    sa.select(TeammateTask)
                    .where(
                        TeammateTask.expires_at <= reference,
                        TeammateTask.state.notin_(sorted(TERMINAL_TASK_STATES)),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for task in tasks:
            await self._close_pending_action(task, cause="task_expired")
            task.state = TASK_CADUCADA
            task.pending_action_id = None
            task.ended_at = reference
            task.updated_at = reference
        await self._session.flush()
        return len(tasks)

    # ── interno ────────────────────────────────────────────────────────

    async def _move(
        self,
        task: TeammateTask,
        state: str,
        *,
        run_id: uuid.UUID | None = None,
        pending: uuid.UUID | None = None,
        ttl_days: int | None = None,
        ended: bool = False,
    ) -> TeammateTask:
        now = datetime.now(UTC)
        task.state = state
        task.pending_action_id = pending
        if run_id is not None:
            task.current_run_id = run_id
        if ttl_days is not None:
            # La vida se desplaza con cada run que termina y con cada decisión:
            # una tarea que avanza no caduca por llevar días abierta.
            task.expires_at = now + timedelta(days=ttl_days)
        if ended:
            task.ended_at = now
        task.updated_at = now
        await self._session.flush()
        return task

    async def _close_pending_action(self, task: TeammateTask, *, cause: str) -> None:
        if task.pending_action_id is None:
            return
        await self._session.execute(
            sa.update(CompanionAction)
            .where(
                CompanionAction.id == task.pending_action_id,
                CompanionAction.status == STATUS_PROPOSED,
            )
            .values(status=STATUS_EXPIRED, decided_at=sa.func.now(), result={"cause": cause})
        )


async def thread_is_mine(session: AsyncSession, thread_id: uuid.UUID, principal_id: str) -> bool:
    """Comprobación explícita para lo que corre sin RLS (el barrido)."""
    owner = await session.scalar(
        sa.select(CompanionThread.principal_id).where(CompanionThread.id == thread_id)
    )
    return owner == principal_id


__all__ = ["TITLE_MAX", "TeammateTaskRepository", "thread_is_mine", "title_from"]
