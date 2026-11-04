"""El bug ``pasadas-huerfanas-tras-fallar-el-trabajo``: una suite no se paga dos veces.

- **Ninguna pasada sobrevive a su trabajo**: al fallar una, las demás se cancelan
  antes de que el trabajo quede ``failed``, y la pasada se cierra.
- **Cada productor mira lo mismo**: un cambio de la ficha se junta con la que aún
  no ha empezado, dos a la vez encolan una, y una fila muerta no se traga nada.
- **«Guardar» y «Probar» se ven**: los dos corren la misma suite.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, Job
from nexus_api.db.models.agent_spec import AgentTest, AgentTestRun, AgentTestSuite
from nexus_api.services import jobs as jobs_service
from nexus_api.services.business.writes import drain_after_commit, mark_tests_stale

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
TEST = {
    "name": "Pregunta el horario",
    "persona": "Cliente habitual",
    "first_message": "¿A qué hora abrís?",
    "plan": "Pregunta y se despide.",
    "expected_state": {},
    "criteria": [],
}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await turn_reservas_on(db_session, biz)
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


def _router() -> LLMRouter:
    provider = InMemoryProvider()
    provider.responder = lambda call: "info" if call.role == "classify" else "Abrimos a las 10."
    return LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model=""
    )


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _agent(
    client: Any, biz: Biz, fake_redis: Any, db_session: AsyncSession, *, tests: int = 1
) -> uuid.UUID:
    """Un agente con su borrador y ``tests`` pruebas nuestras."""
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    agent_id = uuid.UUID(body["result"]["agent_id"])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite_id = await db_session.scalar(
            sa.select(AgentTestSuite.id).where(AgentTestSuite.agent_id == agent_id)
        )
        await db_session.execute(
            sa.update(AgentTest)
            .where(AgentTest.suite_id == suite_id)
            .values(archived_at=sa.func.now())
        )
    for n in range(tests):
        added = await client.post(
            f"{_url(biz, agent_id)}/tests",
            json={**TEST, "name": f"{TEST['name']} {n}"},
            headers=biz.headers(),
        )
        assert added.status_code == 201, added.text
    return agent_id


async def _published(client: Any, biz: Biz, fake_redis: Any, db_session: AsyncSession) -> uuid.UUID:
    """Un agente **publicado**: solo esos vuelven a pasar sus pruebas al cambiar la
    ficha (13.7). Publicarlo no deja nada vivo."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        config = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        assert config is not None
        config.status = AgentConfigStatus.ACTIVE
    return agent_id


async def _tests_jobs(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> list[Job]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = await db_session.scalars(
            sa.select(Job)
            .where(Job.kind == "tests", Job.agent_id == agent_id)
            .order_by(Job.created_at)
            .execution_options(populate_existing=True)
        )
        return list(rows.all())


async def _change_the_ficha(tenant_id: uuid.UUID) -> int:
    """Lo que hace cada escritura de la ficha, en su propia transacción."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        queued = await mark_tests_stale(session, sections=["hours"])
    await drain_after_commit()
    return queued


# ── ninguna pasada sobrevive a su trabajo ──────────────────────────────────────


async def test_when_a_pass_blows_up_the_others_die_with_the_job(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lo de staging: el trabajo ``347e1301`` quedó ``failed`` en 283 ms y sus 51
    pasadas siguieron llamando al modelo. Aquí la pasada lanza mientras otras están
    a medias: cuando el trabajo termina, ninguna sigue."""
    agent_id = await _agent(client, biz, fake_redis, db_session, tests=4)
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert resp.status_code == 202, resp.text

    real_open = tests_handler.open_conversation
    opened: list[int] = []
    in_flight = 0
    all_in = asyncio.Event()
    never = asyncio.Event()
    cancelled: list[int] = []

    async def open_or_blow_up(tenant_id: uuid.UUID) -> Any:
        opened.append(1)
        if len(opened) == tests_handler.PARALLEL:
            await all_in.wait()
            raise RuntimeError("la base se fue")
        return await real_open(tenant_id)

    async def stuck_turn(**_: Any) -> Any:
        nonlocal in_flight
        in_flight += 1
        if in_flight == tests_handler.PARALLEL - 1:
            all_in.set()
        try:
            await never.wait()
        except asyncio.CancelledError:
            cancelled.append(1)
            raise

    monkeypatch.setattr(tests_handler, "open_conversation", open_or_blow_up)
    monkeypatch.setattr(tests_handler, "run_turn", stuck_turn)
    try:
        await asyncio.wait_for(run_jobs(fake_redis, None, router=_router()), timeout=60)
        job = (
            await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
        ).json()
        assert (job["status"], job["error_code"]) == ("failed", "internal"), job
        assert len(cancelled) == in_flight == tests_handler.PARALLEL - 1, "ninguna sigue viva"
        assert len(opened) == tests_handler.PARALLEL, "y ninguna otra empieza"
    finally:
        # Sin esto, las huérfanas de un fallo seguirían corriendo en la prueba siguiente.
        never.set()

    async with tenant_scoped_session(db_session, biz.tenant_id):
        run = await db_session.scalar(
            sa.select(AgentTestRun)
            .where(AgentTestRun.id == uuid.UUID(resp.json()["run_id"]))
            .execution_options(populate_existing=True)
        )
    assert run is not None
    assert run.status == "failed", "la fila no se queda en marcha para siempre"
    assert run.summary["stopped"] == "internal"

    # Y «Reintentar» es otro trabajo, sin nada corriendo por debajo.
    monkeypatch.setattr(tests_handler, "open_conversation", real_open)
    again = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert again.status_code == 202, again.text
    assert again.json()["job_id"] != resp.json()["job_id"]


# ── un cambio de la ficha ─────────────────────────────────────────────────────


async def test_a_change_of_the_ficha_joins_a_manual_run_that_has_not_started(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _published(client, biz, fake_redis, db_session)
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert resp.status_code == 202, resp.text

    assert await _change_the_ficha(biz.tenant_id) == 0
    jobs = await _tests_jobs(db_session, biz, agent_id)
    assert [str(j.id) for j in jobs] == [resp.json()["job_id"]], "la que aún no empezó lo cubre"


async def test_two_changes_at_once_queue_one(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _published(client, biz, fake_redis, db_session)
    # Ya desactualizadas: marcarlas no escribe nada, así que tampoco se bloquean filas.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.update(AgentTest).values(stale=True))
    await asyncio.gather(*(_change_the_ficha(biz.tenant_id) for _ in range(4)))
    jobs = await _tests_jobs(db_session, biz, agent_id)
    assert len(jobs) == 1, [str(j.id) for j in jobs]


async def test_a_dead_queued_row_does_not_swallow_the_next_change(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """La fila de la pasada no se entera de que su trabajo caducó: se queda
    ``queued``. Quien manda es el trabajo."""
    agent_id = await _published(client, biz, fake_redis, db_session)
    assert await _change_the_ficha(biz.tenant_id) == 1
    (dead,) = await _tests_jobs(db_session, biz, agent_id)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        assert await jobs_service.fail_job(db_session, dead.id, error_code="timeout")

    assert await _change_the_ficha(biz.tenant_id) == 1
    jobs = await _tests_jobs(db_session, biz, agent_id)
    assert len(jobs) == 2
    assert jobs[-1].status == "queued"


async def test_a_change_during_a_running_pass_queues_one_more_and_only_one(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """La que corre empezó antes del cambio y no lo cubre: hace falta otra. La
    siguiente se junta con esa."""
    agent_id = await _published(client, biz, fake_redis, db_session)
    assert await _change_the_ficha(biz.tenant_id) == 1
    (first,) = await _tests_jobs(db_session, biz, agent_id)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        started = await jobs_service.start_job(db_session, first.id)
        assert started is not None
        await db_session.execute(
            sa.update(AgentTestRun).where(AgentTestRun.job_id == first.id).values(status="running")
        )

    assert await _change_the_ficha(biz.tenant_id) == 1
    assert await _change_the_ficha(biz.tenant_id) == 0
    assert len(await _tests_jobs(db_session, biz, agent_id)) == 2


# ── «Guardar» y «Probar» ──────────────────────────────────────────────────────


async def test_saving_with_a_live_run_says_so_instead_of_paying_twice(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    run = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert run.status_code == 202, run.text

    # El trabajo de «Guardar» corre; el de las pruebas sigue vivo, sin empezar.
    entries = await fake_redis.xrange("nexus:jobs")
    for entry_id, fields in entries:
        if fields.get("job_id") == run.json()["job_id"]:
            await fake_redis.xdel("nexus:jobs", entry_id)
    save = await client.post(f"{_url(biz, agent_id)}/publish", json={}, headers=biz.headers())
    assert save.status_code == 202, save.text
    await run_jobs(fake_redis, None, router=_router())

    job = (await client.get(f"/console/jobs/{save.json()['job_id']}", headers=biz.headers())).json()
    assert (job["status"], job["error_code"]) == ("failed", "suite_running"), job


async def test_asking_for_a_run_while_saving_runs_the_same_suite_says_so(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """La suite de «Guardar» no es de un trabajo ``tests``, y se paga igual. No se
    devuelve su trabajo: si la puerta lo para, «La pasada no terminó» sería falso."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        job = await jobs_service.create_job(db_session, kind="publish", agent_id=agent_id)
        started = await jobs_service.start_job(db_session, job.id)
        assert started is not None
        db_session.add(
            AgentTestRun(
                id=uuid.uuid4(),
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                scope="all",
                reason="publish",
                status="running",
                paid_by="partner",
                job_id=job.id,
            )
        )

    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "suite_running"
    assert await _tests_jobs(db_session, biz, agent_id) == []


async def test_the_lock_does_not_block_what_only_checks_the_agent_exists(
    db_session: AsyncSession, client: Any, biz: Biz, fake_redis: Any
) -> None:
    """``mark_tests_stale`` corre dentro de una escritura de la ficha: no puede frenar
    a quien inserta filas con FK a ``agents``, como los turnos de un canal."""
    agent_id = await _published(client, biz, fake_redis, db_session)
    sm = get_sessionmaker()
    async with sm() as holder, tenant_scoped_session(holder, biz.tenant_id):
        await mark_tests_stale(holder, sections=["hours"])
        async with sm() as other, tenant_scoped_session(other, biz.tenant_id):
            await other.execute(sa.text("SET LOCAL lock_timeout = '500ms'"))
            found = await other.scalar(
                sa.select(Agent.id)
                .where(Agent.id == agent_id)
                .with_for_update(read=True, key_share=True)
            )
            assert found == agent_id
            # Y entre lanzadores sí choca: ``start_run`` pide ``FOR UPDATE``.
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                async with other.begin_nested():
                    await other.execute(
                        sa.select(Agent.id).where(Agent.id == agent_id).with_for_update(nowait=True)
                    )
    await drain_after_commit()
