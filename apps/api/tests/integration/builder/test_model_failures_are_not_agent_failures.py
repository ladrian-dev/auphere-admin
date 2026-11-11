"""El bug ``el-probador-tapa-los-fallos-del-modelo``: si un modelo no responde, el
chat de prueba y las pruebas lo dicen, y no se lo apuntan al agente.

- **El chat**: el turno trae ``failure`` con el motivo, la burbuja sigue siendo lo
  que recibiría un cliente y el error del proveedor no sale de la API.
- **Una pasada**: si falla el modelo del agente, el del cliente simulado o el del
  juez que decide, queda ``stop = model_failed`` y sin decidir.
- **La prueba**: «No se pudo probar», ni «Falla» ni en la nota, y desactualizada.
- **La pasada entera**: sin nada probado, el trabajo falla con ``model_unavailable``;
  con algo probado, termina y dice cuántas no.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

import litellm
import pytest
import sqlalchemy as sa
from nexus_worker.config import get_worker_settings
from nexus_worker.jobs import DbJobStore, default_registry, drain_once
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from nexus_worker.simulation.runner import set_simulation_router
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.db.models.agent_spec import AgentTest, AgentTestResult, AgentTestRun, AgentTestSuite

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
DECIDED = {"decided": True, "mode": "first_message", "text": "Soy el asistente virtual."}
SECRET = "proxy said: sk-should-not-leave-the-worker"

ONE_TEST = {
    "name": "Pregunta el horario",
    "persona": "Cliente habitual",
    "first_message": "¿A qué hora abrís?",
    "plan": "Pregunta y se despide.",
    "expected_state": {},
    "criteria": [{"key": "answers", "text": "Dice el horario."}],
}


@pytest.fixture(autouse=True)
def one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tests_handler, "PARALLEL", 1)


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await turn_reservas_on(db_session, biz)
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


def _router(answer: Callable[[Any], str]) -> LLMRouter:
    provider = InMemoryProvider()
    provider.responder = answer
    return LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model=""
    )


def _down() -> LLMRouter:
    """Un modelo caído, como un partner sin clave en el proxy."""

    def boom(_call: Any) -> str:
        raise RuntimeError(SECRET)

    return _router(boom)


def _healthy(text: str = "Abrimos a las 10.") -> LLMRouter:
    return _router(lambda call: "info" if call.role == "classify" else text)


def _down_on_pass(numbers: set[int]) -> LLMRouter:
    """Sano, salvo en las pasadas ``numbers`` (la 1 es la primera), reintentos incluidos."""
    passes = [0]

    def answer(call: Any) -> str:
        if call.role == "classify":
            passes[0] += 1
            return "info"
        if passes[0] in numbers:
            raise RuntimeError(SECRET)
        return "Abrimos a las 10."

    return _router(answer)


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _agent(client: Any, biz: Biz, fake_redis: Any, db_session: AsyncSession) -> uuid.UUID:
    """Un agente con su borrador y sin las pruebas del constructor."""
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
    return agent_id


async def _add(client: Any, biz: Biz, agent_id: uuid.UUID, **changes: Any) -> str:
    body = {**ONE_TEST, **changes}
    resp = await client.post(f"{_url(biz, agent_id)}/tests", json=body, headers=biz.headers())
    assert resp.status_code == 201, resp.text
    return str(next(t["id"] for t in resp.json()["tests"] if t["name"] == body["name"]))


async def _run_all(client: Any, biz: Biz, agent_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert resp.status_code == 202, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _job(client: Any, biz: Biz, job_id: str) -> dict[str, Any]:
    resp = await client.get(f"/console/jobs/{job_id}", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _suite(client: Any, biz: Biz, agent_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.get(f"{_url(biz, agent_id)}/tests", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _test(suite: dict[str, Any], test_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(t for t in suite["tests"] if t["id"] == test_id)
    return found


async def _results(
    db_session: AsyncSession, biz: Biz, run_id: str
) -> tuple[AgentTestRun, list[AgentTestResult]]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        run = await db_session.scalar(
            sa.select(AgentTestRun)
            .where(AgentTestRun.id == uuid.UUID(run_id))
            .execution_options(populate_existing=True)
        )
        rows = list(
            (
                await db_session.scalars(
                    sa.select(AgentTestResult).where(AgentTestResult.run_id == uuid.UUID(run_id))
                )
            ).all()
        )
    assert run is not None
    return run, rows


# ── el chat de prueba ──────────────────────────────────────────────────────


async def _open_chat(client: Any, biz: Biz, agent_id: uuid.UUID) -> str:
    resp = await client.post(
        f"{_url(biz, agent_id)}/playground/sessions", json={}, headers=biz.headers()
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["session_id"])


async def _say(client: Any, biz: Biz, agent_id: uuid.UUID, session: str) -> dict[str, Any]:
    resp = await client.post(
        f"{_url(biz, agent_id)}/playground/sessions/{session}/messages",
        json={"text": "¿A qué hora abrís?"},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def test_the_chat_says_the_model_failed_and_keeps_what_a_customer_would_get(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    session = await _open_chat(client, biz, agent_id)
    set_simulation_router(_down())
    try:
        reply = await _say(client, biz, agent_id, session)
    finally:
        set_simulation_router(None)

    turn = reply["turn"]
    assert turn["failure"] == {"reason": "llm_failed"}
    assert turn["bubbles"], "la burbuja sigue: es lo que recibiría un cliente"
    # El error del proveedor se queda en el registro.
    assert SECRET not in str(reply)

    # Vuelve a leerse igual: el motivo se guarda con la conversación.
    again = await client.get(
        f"{_url(biz, agent_id)}/playground/sessions/{session}", headers=biz.headers()
    )
    assert again.status_code == 200, again.text
    assert again.json()["transcript"][-1]["failure"] == {"reason": "llm_failed"}


async def test_the_chat_says_when_the_model_answered_nothing(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    session = await _open_chat(client, biz, agent_id)
    set_simulation_router(_healthy(text="   "))
    try:
        reply = await _say(client, biz, agent_id, session)
    finally:
        set_simulation_router(None)
    assert reply["turn"]["failure"] == {"reason": "empty_response"}


async def test_a_healthy_turn_has_no_failure(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    session = await _open_chat(client, biz, agent_id)
    set_simulation_router(_healthy())
    try:
        reply = await _say(client, biz, agent_id, session)
    finally:
        set_simulation_router(None)
    assert reply["turn"]["failure"] is None
    assert reply["turn"]["bubbles"] == ["Abrimos a las 10."]


# ── las pruebas ────────────────────────────────────────────────────────────


async def test_with_no_model_the_run_fails_and_says_why_without_blaming_the_agent(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Lo de staging: 0 de 17 en un trabajo ``done``."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id)
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_down())

    job = await _job(client, biz, accepted["job_id"])
    assert (job["status"], job["error_code"]) == ("failed", "model_unavailable"), job

    run, rows = await _results(db_session, biz, accepted["run_id"])
    assert run.status == "failed"
    assert run.summary["stopped"] == "model_unavailable"
    assert [(r.passed, r.stop) for r in rows] == [(None, "model_failed")] * 3

    suite = await _suite(client, biz, agent_id)
    test = _test(suite, test_id)
    assert test["status"] == "model_failed"
    assert test["why_failed"] is None, "no hay nada que arreglar en el agente"
    assert test["why_untested"]
    assert SECRET not in str(suite)
    assert test["stale"] is True, "sigue pendiente de probarse"
    assert suite["summary"]["model_failed"] == 1
    assert suite["summary"]["failed"] == 0
    assert suite["summary"]["rate"] is None, "no entra en la nota"


async def test_when_the_simulated_customer_has_no_model_it_is_not_the_agent(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """El agente contesta y falla el modelo del cliente simulado. En staging esto se
    apuntaba como «El agente no terminó el turno»."""

    async def customer(_messages: list[dict[str, str]], *, avoid_model: str | None = None) -> str:
        raise RuntimeError(SECRET)

    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id)
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_healthy(), customer=customer)

    job = await _job(client, biz, accepted["job_id"])
    assert (job["status"], job["error_code"]) == ("failed", "model_unavailable"), job
    test = _test(await _suite(client, biz, agent_id), test_id)
    assert test["status"] == "model_failed"
    assert "agente no terminó" not in (test["why_untested"] or "")


async def test_a_judge_without_a_model_is_not_a_failure_of_the_agent(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calibrado, el juez decide: sin él no se sabe. El trabajo no revienta.

    Spec 059 (5.4, T031): se pregunta por la calibración del juez del registro, no
    por la de cualquier despliegue."""
    from nexus_worker.platform_models import default_models

    async def judge(_messages: list[dict[str, str]]) -> str:
        raise RuntimeError(SECRET)

    asked: list[str] = []

    async def calibrated(_session: Any, *, model: str) -> bool:
        asked.append(model)
        return True

    monkeypatch.setenv("NEXUS_LLM_JUDGE_MODEL", "mistral/juez-de-prueba")
    monkeypatch.setattr(tests_handler.judge_service, "judge_calibrated", calibrated)
    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id)
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_healthy(), judge=judge)

    job = await _job(client, biz, accepted["job_id"])
    assert (job["status"], job["error_code"]) == ("failed", "model_unavailable"), job
    assert _test(await _suite(client, biz, agent_id), test_id)["status"] == "model_failed"
    assert asked and set(asked) == {default_models()["judge"]} == {"mistral/juez-de-prueba"}


async def test_a_judge_without_a_model_does_not_undo_what_the_final_state_decided(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Sin calibrar el juez no bloquea (21.8): la pasada la decide el estado final,
    y un estado en rojo es culpa del agente con o sin juez."""

    async def judge(_messages: list[dict[str, str]]) -> str:
        raise RuntimeError(SECRET)

    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id, expected_state={"booking": {"created": True}})
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_healthy(), judge=judge)

    job = await _job(client, biz, accepted["job_id"])
    assert job["status"] == "done", job
    assert _test(await _suite(client, biz, agent_id), test_id)["status"] == "failed"


async def test_if_something_was_tested_the_job_ends_and_says_how_many_were_not(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Dos pasadas buenas y una sin modelo: ni «Pasa» ni «Inestable»."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id, expected_state={"booking": {"created": False}})
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_down_on_pass({3}))

    job = await _job(client, biz, accepted["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["summary"]["model_failed"] == 1

    run, _rows = await _results(db_session, biz, accepted["run_id"])
    assert run.status == "done"
    suite = await _suite(client, biz, agent_id)
    test = _test(suite, test_id)
    assert test["status"] == "model_failed"
    assert (test["passes"], test["decided"]) == (2, 2)
    assert test["stale"] is True


async def test_a_real_failure_stays_a_failure_next_to_one_without_a_model(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Una pasada en rojo es del agente, aunque otra no haya tenido modelo."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id, expected_state={"booking": {"created": True}})
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_down_on_pass({3}))

    assert (await _job(client, biz, accepted["job_id"]))["status"] == "done"
    assert _test(await _suite(client, biz, agent_id), test_id)["status"] == "failed"


async def test_running_again_with_the_model_back_clears_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id)
    await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_down())
    assert _test(await _suite(client, biz, agent_id), test_id)["status"] == "model_failed"

    # La pasada que falló no estorba: «Reintentar» es un trabajo nuevo.
    accepted = await _run_all(client, biz, agent_id)
    await run_jobs(fake_redis, None, router=_healthy())
    assert (await _job(client, biz, accepted["job_id"]))["status"] == "done"
    test = _test(await _suite(client, biz, agent_id), test_id)
    assert test["status"] != "model_failed"
    assert test["stale"] is False


# ── lo que pasó en staging ─────────────────────────────────────────────────


def _proxy_without_a_key_for_this_partner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin modelos de mentira: el proveedor de verdad, con el proxy obligatorio y sin
    la clave de este partner. Nada llega a salir del proceso."""

    async def never(**_: Any) -> dict[str, Any]:
        raise AssertionError("sin clave no sale ninguna llamada")

    monkeypatch.setenv("NEXUS_LLM_PROXY_REQUIRED", "true")
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", "http://litellm.staging.test")
    monkeypatch.setenv("LITELLM_PROXY_VIRTUAL_KEYS", json.dumps({str(uuid.uuid4()): "sk-otro"}))
    monkeypatch.setattr(get_worker_settings(), "llm_use_inmemory", False)
    monkeypatch.setattr(litellm, "acompletion", never)


async def test_the_case_of_staging_a_partner_without_a_key_in_the_proxy(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Missing partner virtual key»: 0 de 17 y ``done``, un ``200`` con la disculpa."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    test_id = await _add(client, biz, agent_id)
    session = await _open_chat(client, biz, agent_id)
    accepted = await _run_all(client, biz, agent_id)
    _proxy_without_a_key_for_this_partner(monkeypatch)

    await drain_once(fake_redis, registry=default_registry, store=DbJobStore())

    job = await _job(client, biz, accepted["job_id"])
    assert (job["status"], job["error_code"]) == ("failed", "model_unavailable"), job
    test = _test(await _suite(client, biz, agent_id), test_id)
    assert test["status"] == "model_failed"
    assert test["why_failed"] is None

    reply = await _say(client, biz, agent_id, session)
    assert reply["turn"]["failure"] == {"reason": "llm_failed"}
    assert reply["turn"]["bubbles"], "la burbuja es lo que recibiría un cliente"
    assert "virtual key" not in str(reply)

    # La alerta propia, y nada para la que avisa al negocio.
    window = int(time.time()) // 600
    counted = await fake_redis.get(f"nexus:alert:simulated_model_failures:{biz.tenant_id}:{window}")
    assert int(counted) >= 4, "las 3 pasadas y el turno del chat"
    assert await fake_redis.keys("nexus:alert:turn_errors:*") == []


# ── «Guardar» ───────────────────────────────────────────────────────────────


async def _spec(client: Any, biz: Biz, agent_id: uuid.UUID, **changes: Any) -> None:
    draft = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    spec = draft["spec"]
    spec.update(changes)
    resp = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={"spec": spec},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert resp.status_code == 200, resp.text


async def _save(
    client: Any, biz: Biz, agent_id: uuid.UUID, fake_redis: Any, router: Any
) -> dict[str, Any]:
    resp = await client.post(f"{_url(biz, agent_id)}/publish", json={}, headers=biz.headers())
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, None, router=router)
    return await _job(client, biz, resp.json()["job_id"])


async def test_saving_with_no_model_says_the_model_failed(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _add(client, biz, agent_id, critical=True)
    await _spec(client, biz, agent_id, ai_disclosure=DECIDED)

    job = await _save(client, biz, agent_id, fake_redis, _down())
    assert (job["status"], job["error_code"]) == ("failed", "model_unavailable"), job
    async with tenant_scoped_session(db_session, biz.tenant_id):
        published = await db_session.scalar(
            sa.select(AgentConfig.id).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
    assert published is None


async def test_a_critical_test_that_could_not_be_tested_blocks_with_its_own_words(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """«No se probó» no es «pasa», y tampoco es «no pasa 3 de 3»."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _add(client, biz, agent_id, critical=True, name="La crítica")
    await _spec(client, biz, agent_id, ai_disclosure=DECIDED)

    job = await _save(client, biz, agent_id, fake_redis, _down_on_pass({3}))
    assert (job["status"], job["error_code"]) == ("failed", "gate_blocked"), job
    gate = next(b for b in job["progress"]["blocks"] if b.get("key") == "gate")
    assert [i["code"] for i in gate["overridable"]] == ["critical_test_untested"]
    assert "La crítica" in gate["overridable"][0]["message"]
