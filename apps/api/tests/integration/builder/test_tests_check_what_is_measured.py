"""Bug ``las-pruebas-esperan-lo-que-no-se-mide``, con el constructor y el juez de verdad."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
INVENTED = {
    **RECEPTION,
    "escalation": {
        "triggers": ["Cuando haya una reclamación", "complaint"],
        "failed_attempts": 2,
        "message": "Te paso con el equipo.",
    },
    "tests": [
        {
            "name": "Atiende a hombres",
            "persona": "Cliente nuevo",
            "first_message": "¿También hacen cortes para hombres?",
            "plan": "Pregunta y se despide.",
            "expected_state": {"status": "answered", "handoff": False, "escalated": False},
            "criteria": [{"key": "dato", "text": "Dice lo que hay en la ficha."}],
            "critical": True,
        }
    ],
}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await turn_reservas_on(db_session, biz)
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _draft(client: Any, biz: Biz, fake_redis: Any, reply: Any) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=reply))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    assert body["status"] == "done", body
    return uuid.UUID(body["result"]["agent_id"])


async def test_the_builder_keeps_only_what_can_be_measured(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _draft(client, biz, fake_redis, INVENTED)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite_id = await db_session.scalar(
            sa.select(AgentTestSuite.id).where(AgentTestSuite.agent_id == agent_id)
        )
        test = await db_session.scalar(
            sa.select(AgentTest).where(
                AgentTest.suite_id == suite_id, AgentTest.name == "Atiende a hombres"
            )
        )
    assert test is not None
    assert test.expected_state == {"escalated": False}


async def test_an_escalation_in_free_words_is_not_lost(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    """Se perdía, y la pantalla decía «Nunca pasa a una persona por su cuenta»."""
    agent_id = await _draft(client, biz, fake_redis, INVENTED)
    read = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    assert read["spec"]["escalation"]["triggers"] == [
        {"custom": "Cuando haya una reclamación"},
        "complaint",
    ]


async def test_a_builder_that_says_nothing_about_it_still_hands_over(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _draft(
        client, biz, fake_redis, {**INVENTED, "escalation": {"triggers": ["", 3]}}
    )
    read = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    assert read["spec"]["escalation"]["triggers"] == [
        "asks_for_human",
        "failed_attempts",
        "complaint",
    ]


async def test_a_person_is_told_when_a_state_cannot_be_measured(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _draft(client, biz, fake_redis, INVENTED)
    resp = await client.post(
        f"{_url(biz, agent_id)}/tests",
        json={
            "name": "Mía",
            "first_message": "Hola",
            "expected_state": {"status": "answered"},
        },
        headers=biz.headers(),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == {"code": "unknown_state_key", "keys": ["status"]}


async def test_an_old_test_with_invented_keys_does_not_fail_and_the_judge_sees_the_ficha(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Las que ya están guardadas: se deciden por lo que se puede saber."""
    agent_id = await _draft(client, biz, fake_redis, INVENTED)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(AgentTest)
            .where(AgentTest.name == "Atiende a hombres")
            .values(expected_state={"status": "answered", "handoff": False})
        )
        await db_session.execute(
            sa.update(AgentTest)
            .where(AgentTest.name != "Atiende a hombres")
            .values(archived_at=sa.func.now())
        )

    provider = InMemoryProvider()
    provider.responder = lambda call: "info" if call.role == "classify" else "Sí, también."
    router = LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model=""
    )
    seen: list[str] = []

    async def judge(messages: list[dict[str, str]], **_: Any) -> str:
        seen.append(messages[1]["content"])
        return json.dumps({"dimensions": [{"key": "dato", "verdict": "pass", "why": "Coincide."}]})

    run = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert run.status_code == 202, run.text
    await run_jobs(fake_redis, None, judge=judge, router=router)

    suite = (await client.get(f"{_url(biz, agent_id)}/tests", headers=biz.headers())).json()
    (test,) = [t for t in suite["tests"] if t["name"] == "Atiende a hombres"]
    assert (test["status"], test["passes"]) == ("passed", 3), test
    assert seen and all("<ficha>" in s and "Barbería Cultor" in s for s in seen)
    assert all("10:00" in s for s in seen), "con el horario de verdad para comprobarlo"
