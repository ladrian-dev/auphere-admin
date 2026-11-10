"""Los trabajos largos — spec 047, T003 (requisitos 5.3, 17.3, 21.4 y 23.1).

Leer la web, generar un borrador, correr las pruebas, publicar y certificar
tardan más que una petición: la ruta responde ``202 {job_id}`` y el trabajo
deja aquí su ciclo de vida, en la tabla ``jobs`` (migración 0175).

El ciclo es uno para los nueve tipos::

    queued ──start──▶ running ──finish──▶ done
       │                 │
       └─────fail────────┴──────fail────▶ failed (con su ``error_code``)

- **Crear y encolar** (research D43). ``create_job`` escribe la fila con el
  cliente del contexto —nunca del llamante— y ``enqueue_job`` avisa en el
  stream ``nexus:jobs``, que consume ``jobs-consumer`` en el worker. Se encola
  **después** de confirmar la transacción: el aviso no puede llegar antes que
  la fila. La fila es la verdad; el stream solo dice dónde mirar.
- **Cada transición se da una vez.** Las escrituras son ``UPDATE … WHERE
  status = …``: dos consumidores con la misma entrada (una reentrega) no corren
  el trabajo dos veces, y uno terminado no vuelve a cambiar.
- **El progreso es por bloques** (17.3: el borrador se escribe a medida que se
  genera) y cada avance es también **latido**: mueve ``updated_at``.
- **La caducidad es perezosa** y no necesita cron: un trabajo vivo sin latido
  más allá de su plazo se da por ``failed`` con ``timeout`` al leerlo. El
  consumidor marca igual el que su manejador no termina a tiempo.

Todo corre dentro de una transacción con el cliente puesto (RLS); ninguna
función confirma, la transacción es del llamante. El coste (``cost_micros``) se
guarda para la partida «Construcción y pruebas» y no sale nunca hacia la
consola (C9).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.streams import xadd_capped
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.jobs import JOB_KINDS, LIVE_JOB_STATUSES, Job

#: El stream que avisa al worker (research D43).
JOBS_STREAM = "nexus:jobs"
#: Los trabajos son pocos y cada aviso es diminuto; el tope solo acota Redis
#: si el consumidor pasa mucho tiempo caído (y entonces los trabajos ya habrán
#: caducado: la fila manda).
MAX_STREAM_LEN = 50_000

#: Un trabajo en cola que nadie empieza en este plazo se da por perdido: el
#: worker no está o va muy atrasado, y la consola no puede esperar sin fin.
QUEUED_STALE_AFTER = timedelta(minutes=10)
#: Un trabajo en marcha sin latido en este plazo se da por muerto. El
#: consumidor late cada pocos segundos mientras el manejador trabaja, así que
#: solo lo cruza una réplica que se cayó a medias.
RUNNING_STALE_AFTER = timedelta(minutes=2)

#: El código de un trabajo que caducó o no terminó en su plazo.
TIMEOUT = "timeout"

_STALE_AFTER: dict[str, timedelta] = {
    "queued": QUEUED_STALE_AFTER,
    "running": RUNNING_STALE_AFTER,
}


def _scoped(*conditions: sa.ColumnElement[bool]) -> list[sa.ColumnElement[bool]]:
    # La RLS ya esconde los trabajos de otro cliente; el filtro explícito hace
    # que la garantía no descanse en una sola capa.
    return [Job.tenant_id == require_current_tenant(), *conditions]


async def create_job(
    session: AsyncSession,
    *,
    kind: str,
    agent_id: uuid.UUID | None = None,
    created_by: str | None = None,
    draft_revision: int | None = None,
) -> Job:
    """Escribe el trabajo en cola, del cliente del contexto.

    ``agent_id`` es de ese mismo cliente o la FK compuesta lo rechaza.
    ``created_by`` es la persona que lo lanzó (``None`` si fue el sistema).
    """
    if kind not in JOB_KINDS:
        raise ValueError(f"unknown job kind: {kind!r}")
    job = Job(
        tenant_id=require_current_tenant(),
        agent_id=agent_id,
        kind=kind,
        status="queued",
        progress={"step": None, "blocks": []},
        created_by=created_by,
        draft_revision=draft_revision,
    )
    session.add(job)
    await session.flush()
    # Los defectos del servidor (``created_at``, ``updated_at``), ya cargados:
    # leerlos después sería E/S implícita fuera de la transacción.
    await session.refresh(job)
    return job


async def enqueue_job(redis: Redis, job: Job) -> None:
    """Avisa al worker. Llámalo **después** de confirmar la transacción que
    creó el trabajo. Si falla, el trabajo se queda en cola y caduca a su plazo:
    quien lo lanzó decide si lo dice o lo reintenta."""
    await xadd_capped(
        redis,
        JOBS_STREAM,
        {"tenant_id": str(job.tenant_id), "job_id": str(job.id), "kind": job.kind},
        maxlen=MAX_STREAM_LEN,
    )


def enqueue_after_commit(session: AsyncSession, job: Job) -> None:
    """Avisa al worker de ``job`` cuando la transacción **exterior** de ``session``
    se confirme, y nunca si hace rollback (``business.writes.after_commit``). Para
    los trabajos que lanza el sistema desde un servicio (el sector, la relectura,
    el constructor del cliente): quien escribe no tiene que acordarse de encolar."""
    from nexus_api.services.business.writes import after_commit

    fields = {"tenant_id": str(job.tenant_id), "job_id": str(job.id), "kind": job.kind}

    async def push() -> None:
        from nexus_api.core import redis_client

        await xadd_capped(redis_client.get_redis(), JOBS_STREAM, fields, maxlen=MAX_STREAM_LEN)

    after_commit(session, push)


async def _transition(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    from_statuses: tuple[str, ...],
    values: dict[str, Any],
    also: tuple[sa.ColumnElement[bool], ...] = (),
) -> Job | None:
    """``UPDATE … WHERE status IN from_statuses RETURNING``: la transición se
    da una vez o ninguna, sin leer antes."""
    stmt = (
        sa.update(Job)
        .where(*_scoped(Job.id == job_id, Job.status.in_(from_statuses), *also))
        .values(**values, updated_at=sa.func.now())
        .returning(Job)
        .execution_options(populate_existing=True, synchronize_session=False)
    )
    job: Job | None = (await session.execute(stmt)).scalar_one_or_none()
    return job


async def start_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """``queued → running``. ``None`` si ya no está en cola: otro consumidor
    lo empezó, terminó, caducó o no es de este cliente. Un trabajo que la
    consola ya vio caducar no se corre tarde."""
    return await _transition(
        session,
        job_id,
        from_statuses=("queued",),
        values={"status": "running", "started_at": sa.func.now()},
    )


async def heartbeat(session: AsyncSession, job_id: uuid.UUID) -> bool:
    """El latido de un trabajo en marcha. ``False`` si ya no lo está."""
    return await _transition(session, job_id, from_statuses=("running",), values={}) is not None


async def report_progress(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    step: str | None = None,
    block: dict[str, Any] | None = None,
) -> bool:
    """Anota el paso actual y un bloque terminado; también es latido.

    Un bloque es un objeto con ``key``. Si ya hay uno con la misma clave se
    sustituye en su sitio —el constructor reescribe un bloque a medida que lo
    genera—; si no, se añade al final. ``False`` si el trabajo no está en marcha.
    """
    if block is not None and not isinstance(block.get("key"), str):
        raise ValueError("a progress block needs a string 'key'")
    current = await session.scalar(
        sa.select(Job)
        .where(*_scoped(Job.id == job_id, Job.status == "running"))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None:
        return False
    progress = dict(current.progress or {})
    blocks: list[dict[str, Any]] = list(progress.get("blocks") or [])
    if block is not None:
        at = next((i for i, b in enumerate(blocks) if b.get("key") == block["key"]), None)
        if at is None:
            blocks.append(block)
        else:
            blocks[at] = block
    progress["blocks"] = blocks
    if step is not None:
        progress["step"] = step
    progress.setdefault("step", None)
    return (
        await _transition(
            session, job_id, from_statuses=("running",), values={"progress": progress}
        )
        is not None
    )


async def finish_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    result: dict[str, Any],
    cost_micros: int = 0,
) -> bool:
    """``running → done`` con su resultado. El coste se suma al que llevaba."""
    return (
        await _transition(
            session,
            job_id,
            from_statuses=("running",),
            values={
                "status": "done",
                "result": result,
                "finished_at": sa.func.now(),
                "cost_micros": Job.cost_micros + max(0, cost_micros),
            },
        )
        is not None
    )


async def fail_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    error_code: str,
    cost_micros: int = 0,
) -> bool:
    """``queued | running → failed`` con su código (la consola pone las
    palabras). ``False`` si ya había terminado."""
    if not error_code:
        raise ValueError("a failed job needs an error_code")
    return (
        await _transition(
            session,
            job_id,
            from_statuses=LIVE_JOB_STATUSES,
            values={
                "status": "failed",
                "error_code": error_code,
                "finished_at": sa.func.now(),
                "cost_micros": Job.cost_micros + max(0, cost_micros),
            },
        )
        is not None
    )


def is_stale(job: Job, *, now: datetime) -> bool:
    """¿Un trabajo vivo lleva sin latido más que su plazo? Pura."""
    window = _STALE_AFTER.get(job.status)
    return window is not None and now - job.updated_at > window


async def get_job(
    session: AsyncSession, job_id: uuid.UUID, *, now: datetime | None = None
) -> Job | None:
    """Lee el trabajo, con la caducidad perezosa: si sigue vivo y sin latido
    más allá de su plazo, se escribe ``failed``/``timeout`` y se devuelve así.
    ``None`` si no existe para este cliente."""
    now = now or datetime.now(UTC)
    job: Job | None = await session.scalar(
        sa.select(Job).where(*_scoped(Job.id == job_id)).execution_options(populate_existing=True)
    )
    if job is None or not is_stale(job, now=now):
        return job
    expired = await _transition(
        session,
        job_id,
        from_statuses=(job.status,),
        values={"status": "failed", "error_code": TIMEOUT, "finished_at": sa.func.now()},
        # Solo si sigue sin latido: si el consumidor latió o terminó entre la
        # lectura y aquí, gana él y se devuelve lo que escribió.
        also=(Job.updated_at < now - _STALE_AFTER[job.status],),
    )
    if expired is not None:
        return expired
    fresh: Job | None = await session.scalar(
        sa.select(Job).where(*_scoped(Job.id == job_id)).execution_options(populate_existing=True)
    )
    return fresh


__all__ = [
    "JOBS_STREAM",
    "MAX_STREAM_LEN",
    "QUEUED_STALE_AFTER",
    "RUNNING_STALE_AFTER",
    "TIMEOUT",
    "create_job",
    "enqueue_after_commit",
    "enqueue_job",
    "fail_job",
    "finish_job",
    "get_job",
    "heartbeat",
    "is_stale",
    "report_progress",
    "start_job",
]
