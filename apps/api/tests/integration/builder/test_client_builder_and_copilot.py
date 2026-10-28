"""Spec 047, T096 y T097 — el constructor del cliente y el copiloto (historia 18;
requisitos 18 y 19).

Constructor del cliente:
- propone la ficha por secciones, con su procedencia, al pedirlo;
- cada dato se acepta, se edita o se descarta;
- las preguntas frecuentes y las políticas llegan «Sugerido · confirma» y no se
  dan por ciertas;
- propone agentes sin crearlos; lo ya escrito no se pisa.

Copiloto:
- las peticiones dan propuestas revisables;
- «¿por qué dijo…?» cita sus fuentes con enlace;
- una regla llega con su diff y una prueba nueva;
- «Arreglar» un dato pide el alcance y aplica solo tras confirmar;
- a un analyst solo le explica.
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.console.agent_copilot import set_copilot_model
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite, Proposal
from nexus_api.db.models.business import BusinessFaq, BusinessProfile, BusinessSuggestion
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


async def _client_builder(client: Any, biz: Biz, fake_redis: Any) -> dict[str, Any]:
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_builder import make_client_builder_handler

    resp = await client.post(f"{biz.url}/builder", headers=biz.headers())
    assert resp.status_code == 202, resp.text
    registry = JobRegistry()
    registry.register(
        "client_builder",
        make_client_builder_handler(complete_factory=lambda _t: None),
        timeout_s=60,
    )
    await drain_once(fake_redis, registry=registry, store=DbJobStore())
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    assert job["status"] == "done", job
    return job


async def test_the_client_builder_proposes_sections_and_agents_without_writing(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        agents_before = await db_session.scalar(sa.select(sa.func.count()).select_from(Agent))
    job = await _client_builder(client, biz, fake_redis)
    result = job["result"]
    assert result["sections"]["policies"] and result["sections"]["faqs"]
    assert result["agents"][0]["name"] == "Recepción"
    # 18.4: propone agentes sin crearlos.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        assert (
            await db_session.scalar(sa.select(sa.func.count()).select_from(Agent)) == agents_before
        )
        suggestions = (await db_session.scalars(sa.select(BusinessSuggestion))).all()
        profile = await db_session.get(BusinessProfile, biz.tenant_id, populate_existing=True)
        faqs = (await db_session.scalars(sa.select(BusinessFaq))).all()
    # 18.3: nada se da por cierto: todo son sugerencias del constructor.
    assert {s.source for s in suggestions} == {"builder"}
    assert not (profile.policies or {}).get("cancellation") and faqs == []
    faq_suggestions = [s for s in suggestions if s.pointer == "/faqs/-"]
    assert all(s.proposed_value["suggested"] is True for s in faq_suggestions)

    # 18.2: aceptar, editar o descartar, dato a dato.
    policy = next(s for s in suggestions if s.pointer == "/policies/cancellation")
    accepted = await client.post(
        f"{biz.url}/suggestions/{policy.id}/decide",
        json={"decision": "accept"},
        headers=biz.headers(),
    )
    assert accepted.status_code == 200, accepted.text
    first, *rest = faq_suggestions
    edited = await client.post(
        f"{biz.url}/suggestions/{first.id}/decide",
        json={
            "decision": "edit",
            "value": {"q": first.proposed_value["q"], "a": "Sí, siempre con cita."},
        },
        headers=biz.headers(),
    )
    assert edited.status_code == 200, edited.text
    for other in rest:
        dropped = await client.post(
            f"{biz.url}/suggestions/{other.id}/decide",
            json={"decision": "discard"},
            headers=biz.headers(),
        )
        assert dropped.status_code == 200
    async with tenant_scoped_session(db_session, biz.tenant_id):
        profile = await db_session.get(BusinessProfile, biz.tenant_id, populate_existing=True)
        faqs = (await db_session.scalars(sa.select(BusinessFaq))).all()
    assert profile.policies["cancellation"].startswith("Si no puedes venir")
    assert [f.a for f in faqs] == ["Sí, siempre con cita."]

    # Lo ya escrito no se vuelve a proponer.
    again = await _client_builder(client, biz, fake_redis)
    assert again["result"]["sections"]["policies"] == []
    assert any("ya" in reason for reason in again["result"]["discarded"])


# ── el copiloto ────────────────────────────────────────────────────────────


async def _agent(client: Any, biz: Biz, fake_redis: Any) -> uuid.UUID:
    reply = copy.deepcopy(RECEPTION)
    reply["rules"] = ["El corte de pelo cuesta lo que diga la ficha."]
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=reply))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    return uuid.UUID(body["result"]["agent_id"])


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def test_why_did_it_say_cites_its_sources_with_links(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    resp = await client.post(
        f"{_url(biz, agent_id)}/copilot",
        json={
            "message": "¿Por qué dijo eso?",
            "context": {
                "answer": "Abrimos de lunes a viernes de 10:00 a 20:00. Hay aparcamiento detrás del local.",
                "actions": [{"tool": "reservas.find_slots", "phrase": "Buscar huecos"}],
            },
        },
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    kinds = {c["kind"] for c in out["citations"]}
    assert {"business", "knowledge", "tool"} <= kinds
    hours = next(c for c in out["citations"] if c["kind"] == "business")
    assert hours["link"] == {"target": "business/hours"}
    assert out["proposals"] == []


async def test_a_rule_comes_with_its_diff_and_a_test_and_is_applied_by_a_person(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    resp = await client.post(
        f"{_url(biz, agent_id)}/copilot",
        json={"message": "No ofrezcas descuentos"},
        headers=biz.headers(),
    )
    out = resp.json()
    kinds = [p["kind"] for p in out["proposals"]]
    assert kinds == ["agent_spec_patch", "test_add"]
    rule, test = out["proposals"]
    assert rule["diff"]["ops"] == [
        {"op": "add", "path": "/rules/-", "value": "No ofrezcas descuentos."}
    ]
    assert test["diff"]["test"]["criteria"] == [{"key": "rule", "text": "No ofrezcas descuentos."}]
    assert "descuento" in test["diff"]["test"]["first_message"]
    # Nada cambió hasta que una persona aplica.
    draft = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    assert "No ofrezcas descuentos." not in draft["spec"].get("rules", [])
    for proposal in (rule, test):
        applied = await client.post(
            f"{_url(biz, agent_id)}/proposals/{proposal['id']}/apply", headers=biz.headers()
        )
        assert applied.status_code in (200, 409), applied.text
    async with tenant_scoped_session(db_session, biz.tenant_id):
        authors = {p.author for p in (await db_session.scalars(sa.select(Proposal))).all()}
    assert authors == {"copilot"}


async def test_fixing_a_data_asks_the_scope_and_applies_after_confirming(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        test = await db_session.scalar(
            sa.select(AgentTest)
            .join(AgentTestSuite, AgentTestSuite.id == AgentTest.suite_id)
            .where(AgentTestSuite.agent_id == agent_id, AgentTest.archived_at.is_(None))
            .limit(1)
        )
        assert test is not None
        test_id = test.id
    asked = await client.post(
        f"{_url(biz, agent_id)}/copilot",
        json={"message": "Arréglalo", "context": {"test_id": str(test_id)}},
        headers=biz.headers(),
    )
    out = asked.json()
    assert out["fix"] == {"test_id": str(test_id), "scopes": ["business", "agent"]}
    async with tenant_scoped_session(db_session, biz.tenant_id):
        assert await db_session.scalar(sa.select(sa.func.count()).select_from(BusinessFaq)) == 0
    agent_only = await client.post(
        f"{_url(biz, agent_id)}/copilot/fix",
        json={"test_id": str(test_id), "scope": "agent", "value": "Sí, hay aparcamiento detrás."},
        headers=biz.headers(),
    )
    assert agent_only.status_code == 200, agent_only.text
    draft = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    assert any(f["a"] == "Sí, hay aparcamiento detrás." for f in draft["spec"]["services"]["faqs"])
    business = await client.post(
        f"{_url(biz, agent_id)}/copilot/fix",
        json={"test_id": str(test_id), "scope": "business", "value": "Abrimos de 10 a 20."},
        headers=biz.headers(),
    )
    assert business.status_code == 200, business.text
    async with tenant_scoped_session(db_session, biz.tenant_id):
        faqs = (await db_session.scalars(sa.select(BusinessFaq))).all()
    assert [f.a for f in faqs] == ["Abrimos de 10 a 20."]


async def test_an_analyst_gets_explanations_not_proposals(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    asked = await client.post(
        f"{_url(biz, agent_id)}/copilot",
        json={"message": "No ofrezcas descuentos"},
        headers=analyst["headers"](),
    )
    assert asked.status_code == 200
    assert asked.json()["proposals"] == []
    why = await client.post(
        f"{_url(biz, agent_id)}/copilot",
        json={"message": "¿por qué?", "context": {"answer": "Abrimos de 10:00 a 20:00."}},
        headers=analyst["headers"](),
    )
    assert why.json()["citations"]
    fix = await client.post(
        f"{_url(biz, agent_id)}/copilot/fix",
        json={"test_id": str(uuid.uuid4()), "scope": "agent", "value": "x"},
        headers=analyst["headers"](),
    )
    assert fix.status_code == 403


async def test_a_free_request_goes_through_the_model_and_the_validator(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)

    async def model(messages: list[dict[str, str]]) -> str:
        assert "<peticion>" in messages[1]["content"]
        return json.dumps(
            {
                "answer": "Te propongo un saludo más corto.",
                "summary": "Saludo más corto",
                "ops": [{"op": "replace", "path": "/voice/greeting", "value": "¡Hola!"}],
            }
        )

    async def sneaky(_messages: list[dict[str, str]]) -> str:
        return json.dumps(
            {
                "answer": "Listo",
                "ops": [{"op": "add", "path": "/tools/-", "value": "billing.find_client"}],
            }
        )

    try:
        set_copilot_model(model)
        ok = await client.post(
            f"{_url(biz, agent_id)}/copilot",
            json={"message": "Que salude más corto"},
            headers=biz.headers(),
        )
        assert ok.json()["proposals"][0]["diff"]["ops"][0]["path"] == "/voice/greeting"
        set_copilot_model(sneaky)
        refused = await client.post(
            f"{_url(biz, agent_id)}/copilot",
            json={"message": "Activa la facturación"},
            headers=biz.headers(),
        )
        assert refused.json()["proposals"] == []
    finally:
        set_copilot_model(None)
