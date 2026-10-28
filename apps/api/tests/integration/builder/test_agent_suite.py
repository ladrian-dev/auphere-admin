"""Spec 047, T083 — las pruebas del agente (historia 8; requisito 21).

- **Tipos**: del caso (las genera el constructor), del sector y añadidas por
  personas; cada una con sus campos.
- **El estado final** se comprueba, no solo lo que dice el agente (21.3).
- **Pasadas**: 3; pasa con 3 de 3, y con 1 o 2 es «Inestable» (21.4).
- **Fallos**: «Por qué falló», con lo que se comprobó (21.5).
- **«No aplica»**, solo del sector y con su razón; no corre ni cuenta (21.6).
- **Desactualización**: cambiar el borrador las marca; pasarlas las limpia (21.7).
- **Juez**: una dimensión por criterio, con «No sé», y no bloquea sin calibrar (21.8).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models.agent_spec import AgentTest, AgentTestResult, AgentTestRun, AgentTestSuite

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MADRID = ZoneInfo("Europe/Madrid")
WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


@pytest.fixture(autouse=True)
def one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Las pasadas en orden, para que el modelo de mentira sepa cuál es cuál."""
    monkeypatch.setattr(tests_handler, "PARALLEL", 1)


def _monday() -> date:
    today = datetime.now(MADRID).date()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


class Booker:
    """Un agente de mentira que reserva en las pasadas que se le digan."""

    def __init__(self, books_on: set[int]) -> None:
        self.books_on = books_on
        self.attempt = 0
        self.pending: list[ToolCall] = []
        self.provider = InMemoryProvider()
        self.provider.responder = self._respond
        self.provider.tool_caller = self._tools
        self.router = LLMRouter(
            provider=self.provider, classify_model="t/c", respond_model="t/r", fallback_model=""
        )

    def _respond(self, call: Any) -> str:
        if call.role == "classify":
            self.attempt += 1
            if self.attempt in self.books_on:
                self.pending = [
                    ToolCall(
                        id=f"c{self.attempt}",
                        name="reservas.create",
                        arguments={
                            "date": _monday().isoformat(),
                            "time": "10:00",
                            "idempotency_key": f"k{self.attempt}",
                        },
                    )
                ]
            return "book"
        return "Te he reservado el lunes a las 10:00."

    def _tools(self, call: Any) -> list[ToolCall]:
        if call.role == "classify" or not self.pending:
            return []
        return [self.pending.pop(0)]


async def _agent(client: Any, biz: Biz, fake_redis: Any, name: str = "Recepción") -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name=name)
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    return uuid.UUID(body["result"]["agent_id"])


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _only(client: Any, biz: Biz, agent_id: uuid.UUID, body: dict[str, Any]) -> str:
    """Añade una prueba y deja solo esa como aplicable (las del caso, «No aplica»
    no vale para ellas: se archivan aquí para aislar la que se prueba)."""
    resp = await client.post(f"{_url(biz, agent_id)}/tests", json=body, headers=biz.headers())
    assert resp.status_code == 201, resp.text
    suite = resp.json()
    return next(t["id"] for t in suite["tests"] if t["name"] == body["name"])


async def _run(
    client: Any, biz: Biz, agent_id: uuid.UUID, fake_redis: Any, test_id: str, **kw: Any
) -> dict[str, Any]:
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs",
        json={"scope": "one", "test_id": test_id},
        headers=biz.headers(),
    )
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, None, **kw)
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    assert job["status"] == "done", job
    suite = (await client.get(f"{_url(biz, agent_id)}/tests", headers=biz.headers())).json()
    return next(t for t in suite["tests"] if t["id"] == test_id) | {"_suite": suite}


BOOKING_TEST = {
    "name": "Pide cita el lunes",
    "persona": "Cliente habitual",
    "first_message": "¿Me das cita el lunes a las 10?",
    "plan": "Acepta la hora que le ofrecen.",
    "expected_state": {"booking": {"created": True}},
    "criteria": [{"key": "confirms", "text": "Confirma la cita con día y hora."}],
    "critical": True,
}


async def test_the_three_kinds_and_their_fields(client: Any, biz: Biz, fake_redis: Any) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    await _only(client, biz, agent_id, BOOKING_TEST)
    suite = (await client.get(f"{_url(biz, agent_id)}/tests", headers=biz.headers())).json()
    kinds = {t["kind"] for t in suite["tests"]}
    assert {"case", "person"} <= kinds
    mine = next(t for t in suite["tests"] if t["kind"] == "person")
    for key in (
        "name",
        "persona",
        "first_message",
        "plan",
        "expected_state",
        "criteria",
        "critical",
    ):
        assert mine[key] == BOOKING_TEST[key]
    assert mine["status"] == "not_run"
    assert suite["allowed"] == ["add", "edit", "run"]
    assert suite["judge_calibrated"] is False


async def test_three_runs_pass_three_of_three_and_two_of_three_is_flaky(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    test_id = await _only(client, biz, agent_id, BOOKING_TEST)
    passed = await _run(client, biz, agent_id, fake_redis, test_id, router=Booker({1, 2, 3}).router)
    assert (passed["status"], passed["passes"], passed["decided"]) == ("passed", 3, 3)
    assert passed["why_failed"] is None and passed["stale"] is False

    flaky = await _run(client, biz, agent_id, fake_redis, test_id, router=Booker({1, 3}).router)
    assert (flaky["status"], flaky["passes"]) == ("flaky", 2)
    # «Por qué falló»: lo que se comprobó en la pasada que falló.
    assert "booking/created" in (flaky["why_failed"] or "")
    assert "se esperaba true" in (flaky["why_failed"] or "")

    failed = await _run(client, biz, agent_id, fake_redis, test_id, router=Booker(set()).router)
    assert (failed["status"], failed["passes"]) == ("failed", 0)
    assert str(test_id) in failed["_suite"]["summary"]["critical_failed"]

    # Cada pasada guarda el estado final que se comprobó y su conversación.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        results = (
            await db_session.scalars(
                sa.select(AgentTestResult).where(AgentTestResult.test_id == uuid.UUID(test_id))
            )
        ).all()
    assert len(results) == 9
    assert all(r.final_state.get("booking") is not None for r in results)
    assert all(r.transcript[0]["role"] == "customer" for r in results)


async def test_not_applicable_only_for_sector_tests_with_a_reason(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    test_id = await _only(client, biz, agent_id, BOOKING_TEST)
    refused = await client.patch(
        f"{_url(biz, agent_id)}/tests/{test_id}",
        json={"not_applicable_reason": "No hacemos citas"},
        headers=biz.headers(),
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "not_applicable_only_sector"
    # Una del sector, sí; sin razón, no.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite = await db_session.scalar(
            sa.select(AgentTestSuite).where(AgentTestSuite.agent_id == agent_id)
        )
        assert suite is not None
        sector = AgentTest(
            tenant_id=biz.tenant_id,
            suite_id=suite.id,
            kind="sector",
            name="Pide factura",
            first_message="¿Me hacéis factura?",
            sector_test_ref="barberia_peluqueria@1#factura",
        )
        db_session.add(sector)
        await db_session.commit()
        sector_id = sector.id
    no_reason = await client.patch(
        f"{_url(biz, agent_id)}/tests/{sector_id}",
        json={"not_applicable_reason": "x"},
        headers=biz.headers(),
    )
    assert no_reason.status_code == 422
    ok = await client.patch(
        f"{_url(biz, agent_id)}/tests/{sector_id}",
        json={"not_applicable_reason": "No emitimos facturas"},
        headers=biz.headers(),
    )
    assert ok.status_code == 200, ok.text
    row = next(t for t in ok.json()["tests"] if t["id"] == str(sector_id))
    assert (
        row["status"] == "not_applicable" and row["not_applicable_reason"] == "No emitimos facturas"
    )
    assert ok.json()["summary"]["not_applicable"] == 1
    # No corre: «todas» no la incluye.
    run = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert run.status_code == 202
    assert run.json()["tests"] == ok.json()["summary"]["total"] - 1


async def test_running_clears_stale_and_editing_marks_it(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    test_id = await _only(client, biz, agent_id, BOOKING_TEST)
    edited = await client.patch(
        f"{_url(biz, agent_id)}/tests/{test_id}",
        json={"plan": "Pide las 11."},
        headers=biz.headers(),
    )
    row = next(t for t in edited.json()["tests"] if t["id"] == test_id)
    assert row["stale"] is True
    after = await _run(client, biz, agent_id, fake_redis, test_id, router=Booker({1, 2, 3}).router)
    assert after["stale"] is False


async def test_the_judge_has_one_dimension_per_criterion_and_does_not_block_uncalibrated(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    body = dict(BOOKING_TEST)
    body["criteria"] = [
        {"key": "confirms", "text": "Confirma la cita con día y hora."},
        {"key": "policy", "text": "Recuerda la política de cancelación."},
    ]
    test_id = await _only(client, biz, agent_id, body)

    async def strict_judge(_messages: list[dict[str, str]]) -> str:
        return (
            '{"dimensions": [{"key": "confirms", "verdict": "pass", "why": "Lo dice."},'
            ' {"key": "policy", "verdict": "fail", "why": "No recuerda la política."}]}'
        )

    lenient = await _run(
        client,
        biz,
        agent_id,
        fake_redis,
        test_id,
        router=Booker({1, 2, 3}).router,
        judge=strict_judge,
    )
    # Sin calibrar, el juez se enseña pero no tumba la prueba: decide el estado.
    assert lenient["status"] == "passed"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        result = await db_session.scalar(
            sa.select(AgentTestResult)
            .where(AgentTestResult.test_id == uuid.UUID(test_id))
            .order_by(AgentTestResult.created_at.desc())
        )
    assert result is not None
    assert [d["key"] for d in result.dimensions] == ["confirms", "policy"]
    assert {d["verdict"] for d in result.dimensions} == {"pass", "fail"}

    # Un juez que no sabe: «No sé» en cada dimensión que no dijo.
    async def silent_judge(_messages: list[dict[str, str]]) -> str:
        return "no lo sé"

    await _run(
        client,
        biz,
        agent_id,
        fake_redis,
        test_id,
        router=Booker({1, 2, 3}).router,
        judge=silent_judge,
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        result = await db_session.scalar(
            sa.select(AgentTestResult)
            .where(AgentTestResult.test_id == uuid.UUID(test_id))
            .order_by(AgentTestResult.created_at.desc())
        )
    assert result is not None and {d["verdict"] for d in result.dimensions} == {"unknown"}

    # Calibrado (certificación de la tarea ``judge``), el mismo juez sí bloquea.
    async with db_session.begin():
        deployment = await db_session.scalar(sa.text("SELECT id FROM model_profiles LIMIT 1"))
        await db_session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "VALUES (:d, 'judge', 1, '{}'::jsonb, 0.9, true)"
            ),
            {"d": deployment},
        )
    strict = await _run(
        client,
        biz,
        agent_id,
        fake_redis,
        test_id,
        router=Booker({1, 2, 3}).router,
        judge=strict_judge,
    )
    assert strict["status"] == "failed"
    assert "policy" in (strict["why_failed"] or "")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        runs = (await db_session.scalars(sa.select(AgentTestRun))).all()
    assert all(r.paid_by == "partner" for r in runs)
