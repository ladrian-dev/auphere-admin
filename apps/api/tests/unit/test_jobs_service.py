"""Spec 047, T003 — el servicio de trabajos largos (requisitos 5.3, 17.3, 21.4 y 23.1).

Leer la web, generar un borrador, correr las pruebas y publicar responden
``202 {job_id}`` y dejan su ciclo en la tabla ``jobs``. Aquí se fija ese ciclo:

- **crear** toma el cliente del contexto, nunca del llamante, y **encolar**
  avisa en el stream ``nexus:jobs`` (research D43);
- las **transiciones** ``queued → running → done | failed``, y que ninguna se
  da dos veces ni hacia atrás;
- el **progreso por bloques** (17.3: el borrador se escribe a medida que se
  genera), que además es latido;
- la **caducidad perezosa**: un trabajo vivo sin latido más allá de su plazo se
  da por ``failed`` con ``timeout`` al leerlo, sin cron;
- el aislamiento: un trabajo de otro cliente no existe para este.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import IsolationViolation
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, Job, Tenant, TenantPlan, TenantStatus
from nexus_api.services import jobs


@pytest.fixture
async def two_clients(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    ids = {"a": uuid.uuid4(), "b": uuid.uuid4(), "agent_a": uuid.uuid4()}
    for label in ("a", "b"):
        db_session.add(
            Tenant(
                id=ids[label],
                name=f"Cliente {label}",
                slug=f"jobs-{label}-{ids[label].hex[:8]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
            )
        )
    await db_session.flush()
    db_session.add(Agent(id=ids["agent_a"], tenant_id=ids["a"], name="Recepción"))
    await db_session.commit()
    return ids


@pytest.fixture
async def scoped(db_session: AsyncSession) -> Any:
    """``async with scoped(tenant) as s:`` — one committed, RLS-scoped transaction."""

    def _open(tenant_id: uuid.UUID) -> Any:
        return tenant_scoped_session(db_session, tenant_id)

    return _open


async def _new_job(scoped: Any, tenant_id: uuid.UUID, **kwargs: Any) -> uuid.UUID:
    async with scoped(tenant_id) as s:
        job = await jobs.create_job(s, kind=kwargs.pop("kind", "agent_draft"), **kwargs)
        return job.id


async def _read(scoped: Any, tenant_id: uuid.UUID, job_id: uuid.UUID, **kw: Any) -> Job | None:
    async with scoped(tenant_id) as s:
        return await jobs.get_job(s, job_id, **kw)


async def _running(scoped: Any, tenant_id: uuid.UUID, **kwargs: Any) -> uuid.UUID:
    job_id = await _new_job(scoped, tenant_id, **kwargs)
    async with scoped(tenant_id) as s:
        assert await jobs.start_job(s, job_id) is not None
    return job_id


# ── crear y encolar ────────────────────────────────────────────────────────


async def test_create_takes_the_client_from_the_context(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    async with scoped(two_clients["a"]) as s:
        job = await jobs.create_job(
            s, kind="agent_draft", agent_id=two_clients["agent_a"], created_by="ana@partner.test"
        )
    assert job.tenant_id == two_clients["a"]
    assert job.status == "queued"
    assert job.agent_id == two_clients["agent_a"]
    assert job.created_by == "ana@partner.test"
    assert job.progress == {"step": None, "blocks": []}
    assert job.created_at is not None
    assert job.finished_at is None


async def test_create_outside_a_client_context_is_refused(db_session: AsyncSession) -> None:
    async with db_session.begin():
        with pytest.raises(IsolationViolation):
            await jobs.create_job(db_session, kind="client_read")


async def test_create_refuses_a_kind_outside_the_catalogue(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    async with scoped(two_clients["a"]) as s:
        with pytest.raises(ValueError):
            await jobs.create_job(s, kind="mine")


async def test_enqueue_announces_the_job_on_the_stream(
    scoped: Any, two_clients: dict[str, uuid.UUID], fake_redis: Any
) -> None:
    async with scoped(two_clients["a"]) as s:
        job = await jobs.create_job(s, kind="client_read")
    await jobs.enqueue_job(fake_redis, job)

    entries = await fake_redis.xrange(jobs.JOBS_STREAM)
    assert jobs.JOBS_STREAM == "nexus:jobs"
    assert len(entries) == 1
    _, fields = entries[0]
    # The row is the truth; the stream only says where to look.
    assert fields == {
        "tenant_id": str(two_clients["a"]),
        "job_id": str(job.id),
        "kind": "client_read",
    }


# ── transiciones ───────────────────────────────────────────────────────────


async def test_queued_running_done(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _new_job(scoped, a)

    async with scoped(a) as s:
        started = await jobs.start_job(s, job_id)
    assert started is not None
    assert started.status == "running"
    assert started.started_at is not None

    async with scoped(a) as s:
        assert await jobs.finish_job(s, job_id, result={"draft_revision": 1}, cost_micros=1200)

    job = await _read(scoped, a, job_id)
    assert job is not None
    assert job.status == "done"
    assert job.result == {"draft_revision": 1}
    assert job.cost_micros == 1200
    assert job.finished_at is not None
    assert job.error_code is None


async def test_queued_running_failed(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a, kind="client_read")
    async with scoped(a) as s:
        assert await jobs.fail_job(s, job_id, error_code="unreachable", cost_micros=300)

    job = await _read(scoped, a, job_id)
    assert job is not None
    assert (job.status, job.error_code, job.cost_micros) == ("failed", "unreachable", 300)
    assert job.finished_at is not None


async def test_a_queued_job_can_fail_before_it_starts(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _new_job(scoped, a)
    async with scoped(a) as s:
        assert await jobs.fail_job(s, job_id, error_code="no_handler")
    job = await _read(scoped, a, job_id)
    assert job is not None
    assert job.status == "failed"


async def test_a_job_starts_once(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    # Two consumers delivered the same entry (a reclaim): only one runs it.
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    async with scoped(a) as s:
        assert await jobs.start_job(s, job_id) is None


async def test_a_finished_job_never_changes_again(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    async with scoped(a) as s:
        assert await jobs.finish_job(s, job_id, result={"ok": True})

    async with scoped(a) as s:
        assert await jobs.start_job(s, job_id) is None
        assert await jobs.finish_job(s, job_id, result={"ok": False}) is False
        assert await jobs.fail_job(s, job_id, error_code="internal") is False
        assert await jobs.report_progress(s, job_id, step="late") is False
        assert await jobs.heartbeat(s, job_id) is False

    job = await _read(scoped, a, job_id)
    assert job is not None
    assert (job.status, job.result, job.error_code) == ("done", {"ok": True}, None)


async def test_only_a_running_job_finishes(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _new_job(scoped, a)
    async with scoped(a) as s:
        assert await jobs.finish_job(s, job_id, result={}) is False


async def test_failing_needs_a_code(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    async with scoped(a) as s:
        with pytest.raises(ValueError):
            await jobs.fail_job(s, job_id, error_code="")


# ── progreso por bloques ───────────────────────────────────────────────────


async def test_progress_by_blocks(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)

    async with scoped(a) as s:
        assert await jobs.report_progress(s, job_id, step="purpose")
        assert await jobs.report_progress(
            s, job_id, step="skills", block={"key": "purpose", "value": "Citas"}
        )
        assert await jobs.report_progress(s, job_id, block={"key": "skills", "value": ["book"]})

    job = await _read(scoped, a, job_id)
    assert job is not None
    assert job.progress == {
        "step": "skills",
        "blocks": [
            {"key": "purpose", "value": "Citas"},
            {"key": "skills", "value": ["book"]},
        ],
    }


async def test_a_block_written_again_replaces_itself_in_place(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    async with scoped(a) as s:
        await jobs.report_progress(s, job_id, block={"key": "purpose", "value": "Cit"})
        await jobs.report_progress(s, job_id, block={"key": "tone", "value": "cercano"})
        await jobs.report_progress(s, job_id, block={"key": "purpose", "value": "Citas"})

    job = await _read(scoped, a, job_id)
    assert job is not None
    assert job.progress["blocks"] == [
        {"key": "purpose", "value": "Citas"},
        {"key": "tone", "value": "cercano"},
    ]


async def test_a_block_needs_a_key(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    async with scoped(a) as s:
        with pytest.raises(ValueError):
            await jobs.report_progress(s, job_id, block={"value": "sin clave"})


async def test_progress_and_heartbeat_move_the_heartbeat(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)

    async def _a_minute_ago() -> datetime:
        async with scoped(a) as s:
            return (
                await s.execute(
                    sa.update(Job)
                    .where(Job.id == job_id)
                    .values(updated_at=sa.func.now() - timedelta(minutes=1))
                    .returning(Job.updated_at)
                )
            ).scalar_one()

    old = await _a_minute_ago()
    async with scoped(a) as s:
        assert await jobs.heartbeat(s, job_id)
    job = await _read(scoped, a, job_id)
    assert job is not None
    assert job.updated_at > old

    old = await _a_minute_ago()
    async with scoped(a) as s:
        assert await jobs.report_progress(s, job_id, step="tests")
    job = await _read(scoped, a, job_id)
    assert job is not None
    assert job.updated_at > old


# ── caducidad perezosa ─────────────────────────────────────────────────────


async def test_a_running_job_without_heartbeat_fails_with_timeout_when_read(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)

    later = datetime.now(UTC) + jobs.RUNNING_STALE_AFTER + timedelta(seconds=5)
    job = await _read(scoped, a, job_id, now=later)
    assert job is not None
    assert (job.status, job.error_code) == ("failed", "timeout")
    assert job.finished_at is not None

    # Persisted, not just answered: the next plain read says the same.
    again = await _read(scoped, a, job_id)
    assert again is not None
    assert (again.status, again.error_code) == ("failed", "timeout")


async def test_a_running_job_inside_its_window_is_left_alone(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    soon = datetime.now(UTC) + jobs.RUNNING_STALE_AFTER - timedelta(seconds=30)
    job = await _read(scoped, a, job_id, now=soon)
    assert job is not None
    assert job.status == "running"


async def test_a_queued_job_nobody_picks_up_fails_with_timeout(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    a = two_clients["a"]
    job_id = await _new_job(scoped, a)

    inside = datetime.now(UTC) + jobs.QUEUED_STALE_AFTER - timedelta(seconds=30)
    job = await _read(scoped, a, job_id, now=inside)
    assert job is not None
    assert job.status == "queued"

    later = datetime.now(UTC) + jobs.QUEUED_STALE_AFTER + timedelta(seconds=5)
    job = await _read(scoped, a, job_id, now=later)
    assert job is not None
    assert (job.status, job.error_code) == ("failed", "timeout")


async def test_a_finished_job_never_expires(scoped: Any, two_clients: dict[str, uuid.UUID]) -> None:
    a = two_clients["a"]
    job_id = await _running(scoped, a)
    async with scoped(a) as s:
        await jobs.finish_job(s, job_id, result={})
    much_later = datetime.now(UTC) + timedelta(days=30)
    job = await _read(scoped, a, job_id, now=much_later)
    assert job is not None
    assert job.status == "done"


async def test_an_expired_job_does_not_start(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    # The console already showed «failed»: the worker must not run it late.
    a = two_clients["a"]
    job_id = await _new_job(scoped, a)
    later = datetime.now(UTC) + jobs.QUEUED_STALE_AFTER + timedelta(seconds=5)
    await _read(scoped, a, job_id, now=later)
    async with scoped(a) as s:
        assert await jobs.start_job(s, job_id) is None


def test_is_stale_is_a_pure_reading() -> None:
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

    def _job(status: str, idle: timedelta) -> Job:
        return Job(status=status, updated_at=now - idle)

    assert jobs.is_stale(_job("running", jobs.RUNNING_STALE_AFTER + timedelta(seconds=1)), now=now)
    assert not jobs.is_stale(_job("running", jobs.RUNNING_STALE_AFTER), now=now)
    assert jobs.is_stale(_job("queued", jobs.QUEUED_STALE_AFTER + timedelta(seconds=1)), now=now)
    assert not jobs.is_stale(_job("done", timedelta(days=9)), now=now)
    assert not jobs.is_stale(_job("failed", timedelta(days=9)), now=now)


# ── aislamiento ────────────────────────────────────────────────────────────


async def test_another_clients_job_does_not_exist_here(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    job_id = await _running(scoped, two_clients["a"])
    b = two_clients["b"]

    assert await _read(scoped, b, job_id) is None
    async with scoped(b) as s:
        assert await jobs.start_job(s, job_id) is None
        assert await jobs.report_progress(s, job_id, step="x") is False
        assert await jobs.finish_job(s, job_id, result={}) is False
        assert await jobs.fail_job(s, job_id, error_code="internal") is False

    job = await _read(scoped, two_clients["a"], job_id)
    assert job is not None
    assert job.status == "running"


async def test_an_agent_of_another_client_is_refused(
    scoped: Any, two_clients: dict[str, uuid.UUID]
) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        async with scoped(two_clients["b"]) as s:
            await jobs.create_job(s, kind="agent_draft", agent_id=two_clients["agent_a"])
