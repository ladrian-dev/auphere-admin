"""Spec 047, T003 — ``jobs-consumer``, el consumidor base de los trabajos largos.

La API escribe el trabajo y avisa en ``nexus:jobs`` (research D43); este
consumidor, de la familia runner, despacha por ``kind`` al manejador registrado
y deja el final en la fila. Aquí, sin base (la fila es un almacén en memoria):

- **el ciclo**: empieza, late mientras trabaja, anota el progreso y termina o
  falla con su código; siempre acusa la entrada al dejar la fila terminada;
- **la caducidad**: un manejador que no termina en su plazo deja el trabajo
  ``failed``/``timeout``;
- **una vez**: una entrada repetida o reclamada no corre otra vez un trabajo
  que ya empezó;
- **el reintento por reclamación**: lo que una réplica muerta dejó en su PEL lo
  recoge otra, como hace ``stream-claimer`` con los mensajes;
- **el bucle**: varios trabajos a la vez —uno largo no retiene a uno corto— y,
  al parar, lo que sigue en marcha queda ``failed``/``interrupted``;
- **el partner**: el manejador corre con la clave del partner del cliente atada
  (fallo ``el-constructor-no-llega-al-modelo-en-staging``): con el proxy
  obligatorio, sin ella ninguna llamada a un modelo sale.

La misma ronda contra Postgres está en ``apps/api/tests/integration/test_jobs_consumer.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fakeredis import aioredis as fakeaioredis
from nexus_api.core.llm_proxy import current_llm_proxy_partner
from nexus_api.db.models import Job
from nexus_api.services.jobs import JOBS_STREAM, enqueue_job

from nexus_worker.jobs import (
    INTERNAL,
    INTERRUPTED,
    JOBS_GROUP,
    NO_HANDLER,
    TIMEOUT,
    JobContext,
    JobFailed,
    JobOutcome,
    JobRegistry,
    StartedJob,
    drain_once,
    reclaim_once,
    run_jobs_consumer,
)

pytestmark = pytest.mark.asyncio


# ── a job store in memory ─────────────────────────────────────────────────


@dataclass
class _Row:
    tenant_id: uuid.UUID
    kind: str
    partner_id: uuid.UUID | None = None
    status: str = "queued"
    progress: dict[str, Any] = field(default_factory=lambda: {"step": None, "blocks": []})
    result: dict[str, Any] | None = None
    error_code: str | None = None
    cost_micros: int = 0
    beats: int = 0
    settled: int = 0


class FakeStore:
    """The ``JobStore`` contract over a dict: the same transitions as the
    service, each one once, and only for the job's own client."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, _Row] = {}
        self.fail_finish = False

    def add(
        self,
        kind: str = "client_read",
        status: str = "queued",
        partner_id: uuid.UUID | None = None,
    ) -> Job:
        job = Job(id=uuid.uuid4(), tenant_id=uuid.uuid4(), kind=kind)
        self.rows[job.id] = _Row(
            tenant_id=job.tenant_id, kind=kind, status=status, partner_id=partner_id
        )
        return job

    def _row(self, tenant_id: uuid.UUID, job_id: uuid.UUID, *statuses: str) -> _Row | None:
        row = self.rows.get(job_id)
        if row is None or row.tenant_id != tenant_id or row.status not in statuses:
            return None
        return row

    async def start(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> StartedJob | None:
        row = self._row(tenant_id, job_id, "queued")
        if row is None:
            return None
        row.status = "running"
        return StartedJob(
            job_id=job_id, tenant_id=tenant_id, kind=row.kind, partner_id=row.partner_id
        )

    async def heartbeat(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool:
        row = self._row(tenant_id, job_id, "running")
        if row is not None:
            row.beats += 1
        return row is not None

    async def progress(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        step: str | None = None,
        block: dict[str, Any] | None = None,
    ) -> bool:
        row = self._row(tenant_id, job_id, "running")
        if row is None:
            return False
        if step is not None:
            row.progress["step"] = step
        if block is not None:
            row.progress["blocks"].append(block)
        return True

    async def finish(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, *, result: dict[str, Any], cost_micros: int
    ) -> bool:
        if self.fail_finish:
            raise ConnectionError("database unavailable")
        row = self._row(tenant_id, job_id, "running")
        if row is None:
            return False
        row.status, row.result, row.cost_micros = "done", result, row.cost_micros + cost_micros
        return True

    async def fail(
        self, tenant_id: uuid.UUID, job_id: uuid.UUID, *, error_code: str, cost_micros: int = 0
    ) -> bool:
        row = self._row(tenant_id, job_id, "queued", "running")
        if row is None:
            return False
        row.status, row.error_code = "failed", error_code
        row.cost_micros += cost_micros
        return True

    async def settle(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> str | None:
        row = self.rows.get(job_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        row.settled += 1
        return row.status


async def _setup(
    kind: str = "client_read", partner_id: uuid.UUID | None = None
) -> tuple[Any, FakeStore, Job]:
    redis = fakeaioredis.FakeRedis()
    store = FakeStore()
    job = store.add(kind, partner_id=partner_id)
    await enqueue_job(redis, job)
    return redis, store, job


async def _pending(redis: Any) -> int:
    summary = await redis.xpending(JOBS_STREAM, JOBS_GROUP)
    return int(summary["pending"])


def _registry(kind: str, handler: Any, *, timeout_s: float = 5.0) -> JobRegistry:
    registry = JobRegistry()
    registry.register(kind, handler, timeout_s=timeout_s)
    return registry


# ── el registro ────────────────────────────────────────────────────────────


async def test_the_registry_only_takes_kinds_of_the_catalogue_once() -> None:
    async def handler(ctx: JobContext) -> None:
        return None

    registry = JobRegistry()
    registry.register("tests", handler, timeout_s=60)
    assert registry.get("tests") is not None
    assert registry.get("publish") is None
    with pytest.raises(ValueError):
        registry.register("tests", handler, timeout_s=60)
    with pytest.raises(ValueError):
        registry.register("mine", handler, timeout_s=60)
    with pytest.raises(ValueError):
        registry.register("publish", handler, timeout_s=0)


async def test_the_decorator_registers_in_its_registry() -> None:
    registry = JobRegistry()

    @registry.handler("fix", timeout_s=30)
    async def fix(ctx: JobContext) -> None:
        return None

    spec = registry.get("fix")
    assert spec is not None
    assert (spec.handler, spec.timeout_s) == (fix, 30)


# ── el ciclo de una entrada ────────────────────────────────────────────────


async def test_a_queued_job_runs_and_finishes() -> None:
    redis, store, job = await _setup()
    seen: list[JobContext] = []

    async def handler(ctx: JobContext) -> dict[str, Any]:
        seen.append(ctx)
        return {"pages": 3}

    assert await drain_once(redis, registry=_registry("client_read", handler), store=store) == 1

    row = store.rows[job.id]
    assert (row.status, row.result) == ("done", {"pages": 3})
    assert (seen[0].job_id, seen[0].tenant_id, seen[0].kind) == (job.id, job.tenant_id, job.kind)
    assert await _pending(redis) == 0


async def test_an_outcome_carries_its_cost() -> None:
    redis, store, job = await _setup()

    async def handler(ctx: JobContext) -> JobOutcome:
        return JobOutcome(result={"ok": True}, cost_micros=4_200)

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    assert (store.rows[job.id].result, store.rows[job.id].cost_micros) == ({"ok": True}, 4_200)


async def test_a_handler_without_a_result_finishes_with_an_empty_one() -> None:
    redis, store, job = await _setup()

    async def handler(ctx: JobContext) -> None:
        return None

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    assert (store.rows[job.id].status, store.rows[job.id].result) == ("done", {})


async def test_a_named_failure_keeps_its_code_and_its_cost() -> None:
    redis, store, job = await _setup()

    async def handler(ctx: JobContext) -> None:
        raise JobFailed("unreachable", cost_micros=150)

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    row = store.rows[job.id]
    assert (row.status, row.error_code, row.cost_micros) == ("failed", "unreachable", 150)
    assert await _pending(redis) == 0


async def test_an_unexpected_error_fails_as_internal() -> None:
    redis, store, job = await _setup()

    async def handler(ctx: JobContext) -> None:
        raise RuntimeError("boom")

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    assert (store.rows[job.id].status, store.rows[job.id].error_code) == ("failed", INTERNAL)
    assert await _pending(redis) == 0


async def test_a_handler_past_its_deadline_fails_with_timeout() -> None:
    redis, store, job = await _setup()
    cancelled = asyncio.Event()

    async def handler(ctx: JobContext) -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    registry = _registry("client_read", handler, timeout_s=0.05)
    await drain_once(redis, registry=registry, store=store)

    assert (store.rows[job.id].status, store.rows[job.id].error_code) == ("failed", TIMEOUT)
    assert TIMEOUT == "timeout"
    assert cancelled.is_set()  # the handler is stopped, not left running
    assert await _pending(redis) == 0


async def test_a_kind_without_a_handler_fails_at_once() -> None:
    redis, store, job = await _setup(kind="quality_check")

    async def handler(ctx: JobContext) -> None:  # pragma: no cover - never called
        raise AssertionError

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    assert (store.rows[job.id].status, store.rows[job.id].error_code) == ("failed", NO_HANDLER)
    assert await _pending(redis) == 0


async def test_a_job_that_is_not_queued_is_not_run_again() -> None:
    redis, store, job = await _setup()
    store.rows[job.id].status = "running"  # another consumer has it
    calls: list[int] = []

    async def handler(ctx: JobContext) -> None:
        calls.append(1)

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    assert calls == []
    assert store.rows[job.id].status == "running"
    # The row decided: it was read once more, so a dead replica's job expires.
    assert store.rows[job.id].settled == 1
    assert await _pending(redis) == 0


async def test_an_unparseable_entry_is_acknowledged_and_ignored() -> None:
    redis = fakeaioredis.FakeRedis()
    from nexus_api.core.streams import xadd_capped

    await xadd_capped(redis, JOBS_STREAM, {"tenant_id": "nope", "kind": "tests"})
    store = FakeStore()

    async def handler(ctx: JobContext) -> None:  # pragma: no cover - never called
        raise AssertionError

    assert await drain_once(redis, registry=_registry("tests", handler), store=store) == 1
    assert await _pending(redis) == 0


async def test_the_consumer_beats_while_the_handler_works() -> None:
    redis, store, job = await _setup()

    async def handler(ctx: JobContext) -> None:
        await asyncio.sleep(0.08)

    await drain_once(
        redis, registry=_registry("client_read", handler), store=store, heartbeat_s=0.01
    )
    beats = store.rows[job.id].beats
    assert beats >= 3
    await asyncio.sleep(0.05)
    assert store.rows[job.id].beats == beats  # and stops when the job ends


async def test_the_handler_reports_progress_by_blocks() -> None:
    redis, store, job = await _setup(kind="agent_draft")

    async def handler(ctx: JobContext) -> None:
        assert await ctx.progress(step="purpose")
        assert await ctx.progress(block={"key": "purpose", "value": "Citas"})

    await drain_once(redis, registry=_registry("agent_draft", handler), store=store)
    assert store.rows[job.id].progress == {
        "step": "purpose",
        "blocks": [{"key": "purpose", "value": "Citas"}],
    }


# ── el partner del trabajo ─────────────────────────────────────────────────


async def test_a_job_runs_with_its_clients_partner_bound() -> None:
    """Con el proxy obligatorio (staging), cada llamada a un modelo sale con la
    clave virtual del partner. El consumidor la ata antes del manejador, para
    todos los tipos, y llega también a lo que el manejador lanza en paralelo."""
    partner = uuid.uuid4()
    redis, store, job = await _setup(kind="agent_draft", partner_id=partner)
    seen: list[uuid.UUID | None] = []

    async def _now() -> uuid.UUID | None:
        return current_llm_proxy_partner()

    async def handler(ctx: JobContext) -> None:
        seen.append(current_llm_proxy_partner())
        seen.extend(await asyncio.gather(_now(), asyncio.create_task(_now())))

    await drain_once(redis, registry=_registry("agent_draft", handler), store=store)

    assert store.rows[job.id].status == "done"
    assert seen == [partner, partner, partner]
    assert current_llm_proxy_partner() is None, "the scope does not outlive the job"


async def test_two_jobs_side_by_side_keep_their_own_partner() -> None:
    """Garantía 7: dos trabajos a la vez de dos partners nunca cruzan claves."""
    redis = fakeaioredis.FakeRedis()
    store = FakeStore()
    partner_a, partner_b = uuid.uuid4(), uuid.uuid4()
    job_a = store.add("tests", partner_id=partner_a)
    job_b = store.add("tests", partner_id=partner_b)
    await enqueue_job(redis, job_a)
    await enqueue_job(redis, job_b)
    seen: dict[uuid.UUID, uuid.UUID | None] = {}

    async def handler(ctx: JobContext) -> None:
        await asyncio.sleep(0.01)
        seen[ctx.job_id] = current_llm_proxy_partner()

    await drain_once(redis, registry=_registry("tests", handler), store=store)
    assert seen == {job_a.id: partner_a, job_b.id: partner_b}


async def test_a_job_of_a_client_without_partner_runs_without_a_key() -> None:
    """Un cliente sin partner (Demo Farmacia) no hereda ninguna clave: sin
    proxy obligatorio va al vendor, y con él falla ruidoso, como hasta ahora."""
    redis, store, job = await _setup()
    seen: list[uuid.UUID | None] = []

    async def handler(ctx: JobContext) -> None:
        seen.append(current_llm_proxy_partner())

    await drain_once(redis, registry=_registry("client_read", handler), store=store)
    assert store.rows[job.id].status == "done"
    assert seen == [None]


# ── el reintento por reclamación ───────────────────────────────────────────


async def test_an_entry_whose_ending_could_not_be_written_stays_pending() -> None:
    redis, store, job = await _setup()
    store.fail_finish = True

    async def handler(ctx: JobContext) -> dict[str, Any]:
        return {"ok": True}

    registry = _registry("client_read", handler)
    # Logged, not raised: one entry that cannot be closed never stops the rest.
    assert await drain_once(redis, registry=registry, store=store) == 1
    assert await _pending(redis) == 1  # not acked: nothing was recorded

    # Another replica reclaims it later. The job is still «running» in the row,
    # so it is not run twice: the row is read (and expires when stale) and the
    # entry leaves the PEL.
    store.fail_finish = False
    assert await reclaim_once(redis, registry=registry, store=store, min_idle_ms=0) == 1
    assert store.rows[job.id].settled == 1
    assert await _pending(redis) == 0


async def test_a_dead_replicas_queued_entry_is_reclaimed_and_run() -> None:
    redis, store, job = await _setup()
    await redis.xgroup_create(JOBS_STREAM, JOBS_GROUP, id="0", mkstream=True)
    # c-dead read it and died before starting it.
    await redis.xreadgroup(
        groupname=JOBS_GROUP, consumername="c-dead", streams={JOBS_STREAM: ">"}, count=1
    )

    async def handler(ctx: JobContext) -> dict[str, Any]:
        return {"ok": True}

    registry = _registry("client_read", handler)
    # Fresh entries are not stolen.
    assert await reclaim_once(redis, registry=registry, store=store, min_idle_ms=60_000) == 0
    assert await reclaim_once(redis, registry=registry, store=store, min_idle_ms=0) == 1
    assert store.rows[job.id].status == "done"
    assert await _pending(redis) == 0


# ── el bucle ───────────────────────────────────────────────────────────────


async def _until(predicate: Any, timeout: float = 3.0) -> None:
    async def _wait() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_wait(), timeout=timeout)


async def test_the_loop_runs_jobs_side_by_side_and_stops() -> None:
    redis = fakeaioredis.FakeRedis()
    store = FakeStore()
    slow, quick = store.add("tests"), store.add("client_read")
    release = asyncio.Event()

    async def long_handler(ctx: JobContext) -> None:
        await release.wait()

    async def short_handler(ctx: JobContext) -> None:
        return None

    registry = JobRegistry()
    registry.register("tests", long_handler, timeout_s=10)
    registry.register("client_read", short_handler, timeout_s=10)

    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_jobs_consumer(
            redis,
            stop=stop,
            consumer_name="c-1",
            registry=registry,
            store=store,
            concurrency=2,
            idle_seconds=0.01,
        )
    )
    await enqueue_job(redis, slow)
    await enqueue_job(redis, quick)

    # The short job ends while the long one is still running.
    await _until(lambda: store.rows[quick.id].status == "done")
    assert store.rows[slow.id].status == "running"

    release.set()
    await _until(lambda: store.rows[slow.id].status == "done")
    stop.set()
    await asyncio.wait_for(loop, timeout=3)
    assert await _pending(redis) == 0


async def test_stopping_interrupts_what_is_still_running() -> None:
    redis = fakeaioredis.FakeRedis()
    store = FakeStore()
    job = store.add("tests")

    async def handler(ctx: JobContext) -> None:
        await asyncio.sleep(30)

    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_jobs_consumer(
            redis,
            stop=stop,
            consumer_name="c-1",
            registry=_registry("tests", handler, timeout_s=60),
            store=store,
            idle_seconds=0.01,
            shutdown_grace_s=0.05,
        )
    )
    await enqueue_job(redis, job)
    await _until(lambda: store.rows[job.id].status == "running")

    stop.set()
    await asyncio.wait_for(loop, timeout=3)
    assert (store.rows[job.id].status, store.rows[job.id].error_code) == ("failed", INTERRUPTED)
    assert await _pending(redis) == 0


async def test_without_work_the_loop_exits_on_stop() -> None:
    redis = fakeaioredis.FakeRedis()
    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_jobs_consumer(
            redis, stop=stop, consumer_name="c-1", registry=JobRegistry(), store=FakeStore()
        )
    )
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(loop, timeout=3)
