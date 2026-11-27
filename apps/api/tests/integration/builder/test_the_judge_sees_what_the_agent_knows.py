"""Bug «el juez solo mira la ficha» (``.specify/bugs/el-juez-solo-mira-la-ficha``).

El juez comparaba lo que dice el agente solo con la ficha del negocio. Una respuesta tomada
bien de sus preguntas frecuentes propias, de su conocimiento o de sus instrucciones salía
``fail``. Ahora recibe, además de ``<ficha>``, lo que sabía el agente en esa conversación
(``<agente>``): el prompt de la versión probada sin el bloque de la ficha (que ya va en
``<ficha>``) y el conocimiento de cada turno, el mismo que recibió el agente.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models.agent_spec import AgentTest

from ..business._business_world import Biz, new_business, write
from ..knowledge._knowledge_world import add_source
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
WITH_ONE_TEST = {
    **RECEPTION,
    "tests": [
        {
            "name": "Aparcamiento",
            "persona": "Cliente nuevo",
            "first_message": "¿Hay aparcamiento?",
            "plan": "Pregunta y se despide.",
            "expected_state": {},
            "criteria": [{"key": "dato", "text": "Responde con lo que sabe, sin inventar."}],
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


async def test_the_judge_sees_the_agents_faqs_instructions_and_knowledge(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=WITH_ONE_TEST))
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    agent_id = uuid.UUID(job["result"]["agent_id"])
    await add_source(
        db_session,
        biz.tenant_id,
        title="Tintes",
        text="Un tinte completo dura dos horas.",
        agent_id=agent_id,
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(AgentTest)
            .where(AgentTest.name != "Aparcamiento")
            .values(archived_at=sa.func.now())
        )
        await db_session.commit()

    provider = InMemoryProvider()
    provider.responder = lambda call: (
        "info" if call.role == "classify" else "Sí, hay aparcamiento detrás del local."
    )
    router = LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model=""
    )
    seen: list[str] = []

    async def judge(messages: list[dict[str, str]], **_: Any) -> str:
        seen.append(messages[1]["content"])
        return json.dumps({"dimensions": [{"key": "dato", "verdict": "pass", "why": "Su FAQ."}]})

    run = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert run.status_code == 202, run.text
    await run_jobs(fake_redis, None, judge=judge, router=router)

    assert seen, "el juez no se llamó"
    for user in seen:
        ficha = user[user.index("<ficha>") : user.index("</ficha>")]
        agent = user[user.index("<agente>") : user.index("</agente>")]
        assert "10:00" in ficha
        # Su pregunta frecuente propia, sus instrucciones y su conocimiento.
        assert "¿Hay aparcamiento?" in agent and "Sí, detrás del local." in agent
        assert "Pregunta el servicio y el día." in agent
        assert "Un tinte completo dura dos horas." in agent
        # La ficha no va dos veces.
        assert user.count("Datos vigentes del negocio") == 1
