"""El bug ``pasadas-huerfanas-tras-fallar-el-trabajo``: una suite no se paga dos veces.

- **Ninguna pasada sobrevive a su trabajo**: al fallar una, las demás se cancelan
  antes de que el trabajo quede ``failed``, y la pasada se cierra.
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
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job
from nexus_api.db.models.agent_spec import AgentTest, AgentTestRun, AgentTestSuite
from nexus_api.services import jobs as jobs_service

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


async def _tests_jobs(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> list[Job]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = await db_session.scalars(
            sa.select(Job)
            .where(Job.kind == "tests", Job.agent_id == agent_id)
            .order_by(Job.created_at)
            .execution_options(populate_existing=True)
        )
        return list(rows.all())


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


# ── «Guardar» y «Probar» ──────────────────────────────────────────────────────


async def test_saving_with_a_live_run_says_so_instead_of_paying_twice(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    # Con lo que ninguna prueba arregla, la puerta para antes (68.13): este borrador puede salir.
    draft = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    decided = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={
            "spec": {
                **draft["spec"],
                "ai_disclosure": {
                    "decided": True,
                    "mode": "first_message",
                    "text": "Soy el asistente virtual.",
                },
            }
        },
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert decided.status_code == 200, decided.text
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
