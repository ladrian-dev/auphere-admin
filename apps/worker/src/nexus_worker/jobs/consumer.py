"""``jobs-consumer`` — corre los trabajos largos de la consola (spec 047, research D43).

La API escribe el trabajo en ``jobs`` y avisa en el stream ``nexus:jobs`` con
su cliente, su id y su tipo. Este consumidor lee el aviso con un grupo de
Redis, despacha por ``kind`` al manejador registrado y deja el final en la
fila. **La fila es la verdad; el stream solo avisa**: por eso cada paso
pregunta a la fila y no al aviso.

Por cada entrada:

1. un aviso inservible se acusa y se olvida (no hay nada que reintentar);
2. un tipo sin manejador deja el trabajo ``failed``/``no_handler`` al momento;
3. ``start`` pasa ``queued → running``. Si no puede —otro consumidor ya lo
   empezó, terminó, caducó o no existe— no se corre: se lee la fila (con su
   caducidad perezosa, que da por ``timeout`` el de una réplica muerta) y se
   acusa;
4. el manejador corre con **su plazo**; mientras, el consumidor late cada
   ``heartbeat_s`` para que la caducidad de la API no lo dé por muerto. Si no
   termina a tiempo se cancela y el trabajo queda ``failed``/``timeout``;
5. se escribe el final —``done`` con su resultado, o ``failed`` con su código—
   y **solo entonces** se acusa. Si escribirlo falla, la entrada se queda en
   el PEL y la recoge la reclamación.

**El reintento es por reclamación**, como ``stream-claimer`` con los mensajes:
cada ``reclaim_interval_s`` el bucle toma con ``XAUTOCLAIM`` lo que lleva más de
``reclaim_min_idle_ms`` sin acusar en el PEL de otro consumidor (una réplica que
murió) y lo pasa por el mismo camino. No hay reintentos ciegos de un manejador
que falló: un trabajo cuesta dinero y su fallo suele repetirse; la consola
ofrece «Reintentar», que es un trabajo nuevo.

**Varios a la vez.** Un trabajo de pruebas puede durar minutos y un borrador
tiene que salir en menos de 30 s (17.3): el bucle mantiene hasta
``concurrency`` trabajos en marcha y lee más en cuanto queda un hueco, así que
uno largo no retiene a uno corto.

**Al parar**, lo que sigue en marcha tiene ``shutdown_grace_s`` para terminar;
después se cancela y queda ``failed``/``interrupted``, para que la consola lo
diga ya y no dos minutos después.

Familia **runner**: no es un cron, escala en horizontal y el grupo de Redis
reparte (``bootstrap.py``).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from nexus_api.services.jobs import JOBS_STREAM
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from nexus_worker.jobs.registry import (
    INTERNAL,
    INTERRUPTED,
    NO_HANDLER,
    TIMEOUT,
    HandlerSpec,
    JobContext,
    JobFailed,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.jobs.store import DbJobStore, JobStore

log = structlog.get_logger(__name__)

JOBS_GROUP = "nexus-jobs"

#: Cuántos trabajos corre a la vez una réplica.
MAX_IN_FLIGHT = 8
#: Cuánto espera el bucle sin trabajo. Corto: un borrador tiene 30 s en total.
IDLE_SECONDS = 1.0
#: Cada cuánto late un trabajo en marcha. Muy por debajo del plazo sin latido
#: de la API (``RUNNING_STALE_AFTER``, 2 min).
HEARTBEAT_SECONDS = 15.0
#: La reclamación: cada cuánto mira y desde cuánto tiempo sin acusar una
#: entrada se da por huérfana (el mismo umbral que ``stream-claimer``).
RECLAIM_INTERVAL_S = 30.0
RECLAIM_MIN_IDLE_MS = 120_000
#: Lo que se espera a los trabajos en marcha al parar antes de interrumpirlos.
SHUTDOWN_GRACE_S = 10.0

_Entry = tuple[str, dict[str, str]]


def default_consumer_name() -> str:
    return f"jobs:{socket.gethostname()}:{os.getpid()}"


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(JOBS_STREAM, JOBS_GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _entries(raw_entries: Any) -> list[_Entry]:
    out: list[_Entry] = []
    for raw_id, raw_fields in raw_entries or []:
        # XAUTOCLAIM puede devolver lápidas (la entrada se recortó): ya no están.
        if raw_fields is None:
            continue
        out.append((_text(raw_id), {_text(k): _text(v) for k, v in raw_fields.items()}))
    return out


async def read_new(redis: Redis, *, consumer_name: str, count: int) -> list[_Entry]:
    response: Any = await redis.xreadgroup(
        JOBS_GROUP, consumer_name, {JOBS_STREAM: ">"}, count=count, block=None
    )
    out: list[_Entry] = []
    for _stream, raw_entries in response or []:
        out.extend(_entries(raw_entries))
    return out


async def claim_stale(
    redis: Redis, *, consumer_name: str, count: int, min_idle_ms: int
) -> list[_Entry]:
    reply = await redis.xautoclaim(
        JOBS_STREAM,
        JOBS_GROUP,
        consumer_name,
        min_idle_time=min_idle_ms,
        start_id="0-0",
        count=count,
    )
    entries = _entries(reply[1])
    for entry_id, _ in entries:
        log.info("jobs.reclaimed", entry_id=entry_id)
    return entries


async def _ack(redis: Redis, entry_id: str) -> None:
    await redis.xack(JOBS_STREAM, JOBS_GROUP, entry_id)


@dataclass(frozen=True)
class _Ending:
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    cost_micros: int = 0


def _parse(fields: dict[str, str]) -> tuple[uuid.UUID, uuid.UUID, str] | None:
    try:
        return uuid.UUID(fields["tenant_id"]), uuid.UUID(fields["job_id"]), fields["kind"]
    except (KeyError, ValueError):
        return None


async def _beat(store: JobStore, ctx: JobContext, every: float) -> None:
    while True:
        await asyncio.sleep(every)
        # Un latido perdido no es una avería: el siguiente llega a tiempo, y si
        # la base sigue caída el plazo de la API dirá lo que pasó.
        with contextlib.suppress(Exception):
            await store.heartbeat(ctx.tenant_id, ctx.job_id)


async def _run(spec: HandlerSpec, ctx: JobContext, store: JobStore, heartbeat_s: float) -> _Ending:
    beat = asyncio.create_task(_beat(store, ctx, heartbeat_s))
    try:
        raw = await asyncio.wait_for(spec.handler(ctx), timeout=spec.timeout_s)
    except TimeoutError:
        return _Ending(error_code=TIMEOUT)
    except JobFailed as failure:
        return _Ending(error_code=failure.code, cost_micros=failure.cost_micros)
    except Exception as exc:
        log.error(
            "jobs.handler_failed",
            tenant_id=str(ctx.tenant_id),
            job_id=str(ctx.job_id),
            kind=ctx.kind,
            error=str(exc)[:200],
        )
        return _Ending(error_code=INTERNAL)
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
    outcome = raw if isinstance(raw, JobOutcome) else JobOutcome(result=dict(raw or {}))
    return _Ending(result=outcome.result, cost_micros=outcome.cost_micros)


async def process_entry(
    redis: Redis,
    *,
    entry_id: str,
    fields: dict[str, str],
    registry: JobRegistry,
    store: JobStore,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> None:
    """Una entrada, de principio a fin. Acusa solo con la fila terminada (o
    cuando no hay nada que hacer); si escribir el final falla, lanza y la
    entrada se queda en el PEL para la reclamación."""
    parsed = _parse(fields)
    if parsed is None:
        log.warning("jobs.unparseable_entry", entry_id=entry_id)
        await _ack(redis, entry_id)
        return
    tenant_id, job_id, kind = parsed
    bound = {"tenant_id": str(tenant_id), "job_id": str(job_id), "kind": kind}

    spec = registry.get(kind)
    if spec is None:
        log.error("jobs.no_handler", **bound)
        await store.fail(tenant_id, job_id, error_code=NO_HANDLER)
        await _ack(redis, entry_id)
        return

    started = await store.start(tenant_id, job_id)
    if started is None:
        status = await store.settle(tenant_id, job_id)
        log.info("jobs.not_startable", status=status, **bound)
        await _ack(redis, entry_id)
        return

    ctx = JobContext(job=started, _sink=store)
    began = time.perf_counter()
    try:
        ending = await _run(spec, ctx, store, heartbeat_s)
    except asyncio.CancelledError:
        # Al parar: la consola lo dice ya, no cuando caduque.
        with contextlib.suppress(Exception):
            await asyncio.shield(store.fail(tenant_id, job_id, error_code=INTERRUPTED))
            await _ack(redis, entry_id)
        log.warning("jobs.interrupted", **bound)
        raise

    if ending.error_code is None:
        await store.finish(tenant_id, job_id, result=ending.result, cost_micros=ending.cost_micros)
    else:
        await store.fail(
            tenant_id, job_id, error_code=ending.error_code, cost_micros=ending.cost_micros
        )
    await _ack(redis, entry_id)
    log.info(
        "jobs.finished",
        status="done" if ending.error_code is None else "failed",
        error_code=ending.error_code,
        duration_ms=int((time.perf_counter() - began) * 1000),
        cost_micros=ending.cost_micros,
        **bound,
    )


async def _guarded(redis: Redis, entry: _Entry, **kwargs: Any) -> None:
    entry_id, fields = entry
    try:
        await process_entry(redis, entry_id=entry_id, fields=fields, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # La fila no pudo cerrarse: la entrada sigue en el PEL y otra pasada la
        # reclama. Una entrada así nunca para a las demás.
        log.error("jobs.entry_failed", entry_id=entry_id, error=str(exc)[:200])


async def drain_once(
    redis: Redis,
    *,
    registry: JobRegistry | None = None,
    store: JobStore | None = None,
    consumer_name: str = "jobs",
    count: int = MAX_IN_FLIGHT,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> int:
    """Una pasada: lee hasta ``count`` avisos nuevos y los corre a la vez hasta
    el final. Devuelve cuántos atendió. Para las pruebas y los runbooks; el
    servicio usa :func:`run_jobs_consumer`."""
    await ensure_group(redis)
    entries = await read_new(redis, consumer_name=consumer_name, count=count)
    await _run_all(redis, entries, registry, store, heartbeat_s)
    return len(entries)


async def reclaim_once(
    redis: Redis,
    *,
    registry: JobRegistry | None = None,
    store: JobStore | None = None,
    consumer_name: str = "jobs",
    count: int = MAX_IN_FLIGHT,
    min_idle_ms: int = RECLAIM_MIN_IDLE_MS,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> int:
    """Una reclamación: toma lo huérfano del PEL y lo pasa por el mismo camino."""
    await ensure_group(redis)
    entries = await claim_stale(
        redis, consumer_name=consumer_name, count=count, min_idle_ms=min_idle_ms
    )
    await _run_all(redis, entries, registry, store, heartbeat_s)
    return len(entries)


async def _run_all(
    redis: Redis,
    entries: list[_Entry],
    registry: JobRegistry | None,
    store: JobStore | None,
    heartbeat_s: float,
) -> None:
    kwargs: dict[str, Any] = {
        "registry": registry or default_registry,
        "store": store or DbJobStore(),
        "heartbeat_s": heartbeat_s,
    }
    await asyncio.gather(*(_guarded(redis, entry, **kwargs) for entry in entries))


async def _pause(stop: asyncio.Event, running: set[asyncio.Task[None]], timeout: float) -> None:
    """Espera a ``stop``, a que termine un trabajo (queda un hueco) o a ``timeout``."""
    stopper = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait(
            {stopper, *running}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        stopper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stopper


async def run_jobs_consumer(
    redis: Redis,
    *,
    stop: asyncio.Event,
    consumer_name: str | None = None,
    registry: JobRegistry | None = None,
    store: JobStore | None = None,
    concurrency: int = MAX_IN_FLIGHT,
    idle_seconds: float = IDLE_SECONDS,
    heartbeat_s: float = HEARTBEAT_SECONDS,
    reclaim_interval_s: float = RECLAIM_INTERVAL_S,
    reclaim_min_idle_ms: int = RECLAIM_MIN_IDLE_MS,
    shutdown_grace_s: float = SHUTDOWN_GRACE_S,
) -> None:
    """Bucle del servicio (tarea ``jobs-consumer``). Sale cuando ``stop`` se activa."""
    name = consumer_name or default_consumer_name()
    kwargs: dict[str, Any] = {
        "registry": registry or default_registry,
        "store": store or DbJobStore(),
        "heartbeat_s": heartbeat_s,
    }
    running: set[asyncio.Task[None]] = set()
    loop = asyncio.get_running_loop()
    next_reclaim = loop.time()
    group_ready = False
    log.info("jobs.consumer.start", stream=JOBS_STREAM, group=JOBS_GROUP, consumer=name)
    try:
        while not stop.is_set():
            try:
                if not group_ready:
                    await ensure_group(redis)
                    group_ready = True
                free = concurrency - len(running)
                entries: list[_Entry] = []
                if free > 0 and loop.time() >= next_reclaim:
                    next_reclaim = loop.time() + reclaim_interval_s
                    entries += await claim_stale(
                        redis, consumer_name=name, count=free, min_idle_ms=reclaim_min_idle_ms
                    )
                if free - len(entries) > 0:
                    entries += await read_new(redis, consumer_name=name, count=free - len(entries))
                for entry in entries:
                    task = asyncio.create_task(_guarded(redis, entry, **kwargs))
                    running.add(task)
                    task.add_done_callback(running.discard)
                if not entries:
                    await _pause(stop, running, idle_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # El bucle no muere: un trabajo sin consumidor es lo que esta
                # tarea existe para evitar. El grupo se vuelve a asegurar por si
                # lo que falló es que el stream desapareció (``NOGROUP``).
                group_ready = False
                log.error("jobs.consumer.tick_failed", error=str(exc)[:200])
                await _pause(stop, set(), 1.0)
    finally:
        # Parar con ``stop`` o con una cancelación: lo que sigue en marcha tiene
        # su gracia y después queda ``interrupted``, nunca huérfano.
        if running:
            _, late = await asyncio.wait(set(running), timeout=shutdown_grace_s)
            for task in late:
                task.cancel()
            await asyncio.gather(*late, return_exceptions=True)
        log.info("jobs.consumer.stopped", consumer=name)


__all__ = [
    "HEARTBEAT_SECONDS",
    "IDLE_SECONDS",
    "JOBS_GROUP",
    "MAX_IN_FLIGHT",
    "RECLAIM_INTERVAL_S",
    "RECLAIM_MIN_IDLE_MS",
    "SHUTDOWN_GRACE_S",
    "claim_stale",
    "default_consumer_name",
    "drain_once",
    "ensure_group",
    "process_entry",
    "read_new",
    "reclaim_once",
    "run_jobs_consumer",
]
