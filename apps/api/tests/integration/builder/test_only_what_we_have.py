"""Spec 047, enmienda del 2026-10-30, fase 28 — solo lo que tenemos (requisito 65).

De punta a punta, por la consola y el trabajo del constructor:

- **T221** (65.3, 65.4): una integración inventada y Reservas apagado salen como
  capacidades que faltan en el resultado del trabajo y en el borrador; ninguna
  acaba en «Conectar {X}».
- **T222** (65.5): una promesa sin herramienta bloquea la puerta.
- **T224** (65.8, 65.9): en una barbería, un agente sin agenda recibe las pruebas
  de cita como «No aplica», con razón, y la puerta no bloquea por ellas; un agente
  estructurado sin ninguna prueba aplicable no se publica.
- **T225** (65.10, 65.12): ``PUT …/tools`` y ``PATCH …/draft`` con ``tools`` dan 409
  a un agente estructurado; las rutas de plantillas de la consola de antes se
  cierran para la consola nueva; una ficha que no carga, o un modelo sin
  instrucciones, dan su código y ningún borrador.
- **T226** (65.7): el copiloto y el constructor del cliente reciben las
  herramientas disponibles con lo que hace cada una; el copiloto no propone lo que
  no tenemos; no se sugiere un agente que necesite lo que falta.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.console.agent_copilot import set_copilot_model
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, Partner
from nexus_api.db.models.agent_spec import AgentTest
from nexus_api.db.models.business import BusinessProfile, SuggestedAgent

from ..business._business_world import Biz, new_business
from ._builder_world import RECEPTION, FakeBuilder, job_row, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        profile = await db_session.get(BusinessProfile, biz.tenant_id)
        assert profile is not None
        profile.sector = {
            "key": "barberia_peluqueria",
            "label": "Barbería",
            "confidence": 0.9,
            "source": "niche",
            "decided_by": "system",
        }
    return biz


def _agents_url(biz: Biz) -> str:
    return f"/console/clients/{biz.ref}"


async def _job(
    client: Any, biz: Biz, fake_redis: Any, builder: FakeBuilder | None, **body: Any
) -> dict[str, Any]:
    resp = await start_draft(client, _agents_url(biz), biz.headers(), **body)
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, builder)
    got = await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    out: dict[str, Any] = got.json()
    return out


async def _draft(client: Any, biz: Biz, agent_id: str) -> dict[str, Any]:
    resp = await client.get(f"{_agents_url(biz)}/agents/{agent_id}/draft", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _keys(items: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {(m["kind"], m["key"], m["reason"]) for m in items}


async def _gate(db_session: AsyncSession, biz: Biz, agent_id: str) -> Any:
    from nexus_api.services.publishing import evaluate_gate

    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = await db_session.get(Agent, uuid.UUID(agent_id), populate_existing=True)
        version = await db_session.scalar(
            sa.select(AgentConfig)
            .where(
                AgentConfig.agent_id == uuid.UUID(agent_id),
                AgentConfig.status == AgentConfigStatus.STAGED,
            )
            .execution_options(populate_existing=True)
        )
        assert agent is not None and version is not None
        return await evaluate_gate(
            db_session, agent=agent, version=version, active=None, partner_id=biz.partner_id
        )


async def _agent_count(db_session: AsyncSession, biz: Biz) -> int:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        return int(await db_session.scalar(sa.select(sa.func.count()).select_from(Agent)) or 0)


# ── T221: lo que no tenemos, dicho, y sin «Conectar» ───────────────────────


async def test_an_invented_integration_and_reservas_off_are_missing_capabilities(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    reply = copy.deepcopy(RECEPTION)
    reply["tools"] = ["reservas.find_slots", "reservas.create", "escalate.escalate_to_human"]
    reply["skills"] = [
        {"key": "facturar", "enabled": True, "integration": "quickbooks"},
        {"key": "agenda", "enabled": True, "integration": "reservas"},
    ]
    reply["connection_requests"] = [
        {"integration": "quickbooks", "reason": "Para emitir facturas"},
        {"integration": "reservas", "reason": "Para la agenda"},
    ]
    reply["instructions"].append(
        {"title": "Facturas", "body": "Emite la factura al terminar cada visita."}
    )
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=reply), name="Recepción")
    assert body["status"] == "done", body
    result = body["result"]
    assert result["connect"] == [], "ni «Conectar quickbooks» ni «Conectar reservas»"
    assert {
        ("integration", "quickbooks", "integration_unknown"),
        ("module", "reservas", "module_off"),
        ("action", "invoice", "no_tool"),
    } <= _keys(result["missing_capabilities"])

    draft = await _draft(client, biz, result["agent_id"])
    assert {
        ("integration", "quickbooks", "integration_unknown"),
        ("module", "reservas", "module_off"),
        ("action", "invoice", "no_tool"),
    } <= _keys(draft["missing_capabilities"])
    spec = draft["spec"]
    assert not spec.get("connection_requests")
    assert not [s for s in spec.get("skills") or [] if s.get("integration")]


async def test_a_draft_with_nothing_missing_says_so(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await turn_reservas_on(db_session, biz)
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Recepción")
    assert body["result"]["missing_capabilities"] == []
    draft = await _draft(client, biz, body["result"]["agent_id"])
    assert draft["missing_capabilities"] == []


# ── T222: la promesa sin herramienta bloquea ───────────────────────────────


async def test_a_promise_without_a_tool_blocks_the_gate(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await turn_reservas_on(db_session, biz)
    reply = copy.deepcopy(RECEPTION)
    reply["tools"] = ["reservas.services", "payments.request_review"]
    reply["procedures"] = []
    reply["instructions"] = [
        {"title": "Citas", "body": "Reserva una cita a quien la pida."},
        {"title": "Pagos", "body": "Cobra con tarjeta la señal de cada cita."},
    ]
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=reply), name="Recepción")
    gate = await _gate(db_session, biz, body["result"]["agent_id"])
    blocking = [i for i in gate.overridable if i["code"] == "promises_without_tool"]
    assert len(blocking) >= 2, gate.to_json()
    assert all(i["condition"] == "review" for i in blocking)
    # «Arreglar en el borrador» lleva al texto que promete.
    assert {i["pointer"] for i in blocking} == {
        "/instructions/sections/0/body",
        "/instructions/sections/1/body",
    }


# ── T224: las pruebas del sector y la puerta ───────────────────────────────


async def _sector_tests(db_session: AsyncSession, biz: Biz) -> dict[str, AgentTest]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(AgentTest)
                .where(AgentTest.kind == "sector", AgentTest.archived_at.is_(None))
                .execution_options(populate_existing=True)
            )
        ).all()
    return {str(r.sector_test_ref).split("#", 1)[1]: r for r in rows}


async def test_without_the_agenda_the_booking_tests_do_not_apply_and_do_not_block(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Atención")
    tests = await _sector_tests(db_session, biz)
    assert len(tests) == 12
    for key in ("book", "closed_day"):
        reason = tests[key].not_applicable_reason
        assert reason == "Este agente no tiene herramienta para reservar citas.", key
    assert tests["hours"].not_applicable_reason is None
    assert tests["human"].not_applicable_reason is None
    gate = await _gate(db_session, biz, body["result"]["agent_id"])
    said = json.dumps(gate.to_json(), ensure_ascii=False)
    assert "Pide cita para mañana" not in said
    assert "no_applicable_tests" not in said
    listed = await client.get(
        f"{_agents_url(biz)}/agents/{body['result']['agent_id']}/tests", headers=biz.headers()
    )
    by_name = {t["name"]: t for t in listed.json()["tests"]}
    assert by_name["Pide cita para mañana"]["not_applicable_reason"]


async def test_with_the_agenda_the_booking_tests_apply(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await turn_reservas_on(db_session, biz)
    await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Recepción")
    tests = await _sector_tests(db_session, biz)
    assert tests["book"].not_applicable_reason is None
    assert tests["closed_day"].not_applicable_reason is None


async def test_a_structured_agent_without_any_applicable_test_is_not_published(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    resp = await start_draft(
        client, _agents_url(biz), biz.headers(), name="En blanco", start="blank"
    )
    assert resp.status_code == 202, resp.text
    gate = await _gate(db_session, biz, resp.json()["agent_id"])
    assert {"condition": "critical_tests", "code": "no_applicable_tests"}.items() <= next(
        i for i in gate.hard if i["code"] == "no_applicable_tests"
    ).items()


# ── T225: las herramientas solo por el AgentSpec ───────────────────────────


async def test_the_tools_of_a_structured_agent_change_only_through_its_spec(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await turn_reservas_on(db_session, biz)
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Recepción")
    agent_id = body["result"]["agent_id"]
    put = await client.put(
        f"{_agents_url(biz)}/tools?agent={agent_id}",
        json={"tools": ["reservas.create", "billing.find_client"]},
        headers=biz.headers(),
    )
    assert put.status_code == 409, put.text
    assert put.json()["detail"]["code"] == "structured_agent"
    draft = await _draft(client, biz, agent_id)
    patch = await client.patch(
        f"{_agents_url(biz)}/agents/{agent_id}/draft",
        json={"tools": ["reservas.create", "billing.find_client"]},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert patch.status_code == 409, patch.text
    assert patch.json()["detail"]["code"] == "structured_agent"
    after = await _draft(client, biz, agent_id)
    assert "billing.find_client" not in after["tools"]


async def test_staging_a_version_with_tools_is_not_a_way_around_the_spec(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Spec 047, T217 (revisión de seguridad del 2026-10-30; 65.10): ``POST
    …/agent/versions`` escribía ``draft.tools`` de un agente estructurado sin pasar
    por su AgentSpec ni por el validador. Con herramientas, ``409 structured_agent``
    como ``PUT …/tools``. Sin ellas (lo único que manda la consola) sigue igual."""
    await turn_reservas_on(db_session, biz)
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Recepción")
    agent_id = body["result"]["agent_id"]
    before = await _draft(client, biz, agent_id)
    staged = await client.post(
        f"{_agents_url(biz)}/agent/versions?agent={agent_id}",
        json={"system_prompt": "Hola.", "tools": ["reservas.create", "reservas.cancel"]},
        headers=biz.headers(),
    )
    assert staged.status_code == 409, staged.text
    assert staged.json()["detail"]["code"] == "structured_agent"
    after = await _draft(client, biz, agent_id)
    assert after["tools"] == before["tools"] and after["revision"] == before["revision"]


async def test_the_old_template_routes_are_closed_for_the_new_console(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    before = await _agent_count(db_session, biz)
    seed = await client.post(
        f"{_agents_url(biz)}/agent/from-seed",
        json={"seed_template": "barbershop_v1", "placeholders": {}},
        headers=biz.headers(),
    )
    assert seed.status_code == 410, seed.text
    created = await client.post(
        f"{_agents_url(biz)}/agents",
        json={"name": "Desde semilla", "seed_template": "barbershop_v1", "placeholders": {}},
        headers=biz.headers(),
    )
    assert created.status_code == 410, created.text
    assert await _agent_count(db_session, biz) == before
    client_with_seed = await client.post(
        "/console/clients",
        json={
            "external_client_ref": f"semilla-{uuid.uuid4().hex[:8]}",
            "name": "Con semilla",
            "seed_template": "barbershop_v1",
        },
        headers=biz.headers(),
    )
    assert client_with_seed.status_code == 422, client_with_seed.text
    assert "seed_template_retired" in client_with_seed.text


# ── T225: sin ficha o sin instrucciones, ningún borrador ───────────────────


async def test_a_profile_that_does_not_load_gives_facts_unavailable_and_no_draft(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, monkeypatch: Any
) -> None:
    from nexus_api.services.business import compilation

    async def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("the profile is unreadable")

    monkeypatch.setattr(compilation, "load_facts", broken)
    before = await _agent_count(db_session, biz)
    resp = await start_draft(client, _agents_url(biz), biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    job = await job_row(db_session, biz.tenant_id, resp.json()["job_id"])
    assert job.status == "failed"
    assert job.error_code == "facts_unavailable"
    template = await start_draft(
        client,
        _agents_url(biz),
        biz.headers(),
        name="Plantilla",
        start="template",
        template_id="barbershop_v1",
    )
    assert template.status_code == 503, template.text
    assert "facts_unavailable" in template.text
    assert await _agent_count(db_session, biz) == before


async def test_a_model_without_instructions_is_a_builder_failure_and_no_draft(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    reply = copy.deepcopy(RECEPTION)
    reply["instructions"] = []
    before = await _agent_count(db_session, biz)
    resp = await start_draft(client, _agents_url(biz), biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=reply))
    job = await job_row(db_session, biz.tenant_id, resp.json()["job_id"])
    assert job.status == "failed" and job.error_code == "builder_unavailable"
    assert await _agent_count(db_session, biz) == before


# ── T226: el copiloto y el constructor del cliente ─────────────────────────


async def _agent(client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any) -> str:
    await turn_reservas_on(db_session, biz)
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Recepción")
    return str(body["result"]["agent_id"])


async def test_the_copilot_model_gets_the_tools_and_never_proposes_what_we_lack(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis)
    seen: list[list[dict[str, str]]] = []

    async def model(messages: list[dict[str, str]]) -> str:
        seen.append(messages)
        return json.dumps(
            {
                "answer": "Te propongo facturar con QuickBooks y un saludo más corto.",
                "summary": "Facturas y saludo",
                "ops": [
                    {
                        "op": "add",
                        "path": "/skills/-",
                        "value": {"key": "facturar", "enabled": True, "integration": "quickbooks"},
                    },
                    {
                        "op": "add",
                        "path": "/connection_requests",
                        "value": [{"integration": "quickbooks", "reason": "Para facturar"}],
                    },
                    {"op": "replace", "path": "/voice/greeting", "value": "¡Buenas!"},
                ],
            }
        )

    try:
        set_copilot_model(model)
        resp = await client.post(
            f"{_agents_url(biz)}/agents/{agent_id}/copilot",
            json={"message": "Que emita facturas con QuickBooks y salude más corto"},
            headers=biz.headers(),
        )
    finally:
        set_copilot_model(None)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    prompt = "\n".join(m["content"] for m in seen[-1])
    assert "reservas.create" in prompt and "Deja la reserva en la agenda" in prompt
    assert ("integration", "quickbooks", "integration_unknown") in _keys(
        out["missing_capabilities"]
    )
    ops = [op for p in out["proposals"] for op in p["diff"]["ops"]]
    assert ops, "lo que sí se puede, se propone"
    assert "quickbooks" not in json.dumps(ops)


async def test_a_rule_that_promises_what_we_lack_is_not_proposed(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis)
    resp = await client.post(
        f"{_agents_url(biz)}/agents/{agent_id}/copilot",
        json={"message": "Siempre emite la factura al terminar"},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["proposals"] == []
    assert ("action", "invoice", "no_tool") in _keys(out["missing_capabilities"])
    assert "No tenemos herramienta para" in out["text"]
    ok = await client.post(
        f"{_agents_url(biz)}/agents/{agent_id}/copilot",
        json={"message": "Nunca prometas un barbero concreto"},
        headers=biz.headers(),
    )
    assert ok.json()["missing_capabilities"] == []
    assert len(ok.json()["proposals"]) == 2


async def _client_builder(
    client: Any, biz: Biz, fake_redis: Any, complete: Any | None
) -> dict[str, Any]:
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_builder import make_client_builder_handler

    resp = await client.post(f"{biz.url}/builder", headers=biz.headers())
    assert resp.status_code == 202, resp.text
    registry = JobRegistry()
    registry.register(
        "client_builder",
        make_client_builder_handler(complete_factory=lambda _t: complete),
        timeout_s=60,
    )
    await drain_once(fake_redis, registry=registry, store=DbJobStore())
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    assert job["status"] == "done", job
    out: dict[str, Any] = job
    return out


async def test_no_suggested_agent_needs_what_the_client_lacks(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    job = await _client_builder(client, biz, fake_redis, None)
    names = [a["name"] for a in job["result"]["agents"]]
    assert "Recepción" not in names, "da citas, y Reservas está apagado"
    assert names == ["Atención"]


async def test_the_client_builder_gets_the_tools_and_takes_any_role_or_none(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    seen: list[list[dict[str, str]]] = []

    async def model(messages: list[dict[str, str]]) -> str:
        seen.append(messages)
        return json.dumps(
            {
                "policies": {},
                "faqs": [],
                "agents": [
                    {
                        "name": "Seguimiento",
                        "description": "Pregunta qué tal fue la visita y anota lo que cuentan.",
                        "role": "logistica",
                    },
                    {
                        "name": "Sin papel",
                        "description": "Responde dudas del negocio con la ficha y pasa al equipo.",
                    },
                    {
                        "name": "Facturación",
                        "description": "Emite las facturas de cada servicio y las envía.",
                        "role": "billing",
                    },
                ],
            }
        )

    job = await _client_builder(client, biz, fake_redis, model)
    system = seen[-1][0]["content"]
    prompt = "\n".join(m["content"] for m in seen[-1])
    assert '"role"?' in system or "role (opcional" in system or "sin papel" in system.lower()
    assert "escalate.escalate_to_human" in prompt and "<herramientas>" in prompt
    names = [a["name"] for a in job["result"]["agents"]]
    assert names == ["Seguimiento", "Sin papel"], "nada que necesite facturar"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = {
            r.name: r.role
            for r in (
                await db_session.scalars(
                    sa.select(SuggestedAgent).execution_options(populate_existing=True)
                )
            ).all()
        }
    assert rows == {"Seguimiento": None, "Sin papel": None}


# ── D72: un borrador de antes de la enmienda ───────────────────────────────


async def test_an_old_draft_with_what_we_lack_is_cleaned_not_refused(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """La consola nueva no edita habilidades ni peticiones de conexión: un agente
    estructurado de antes con una integración que no tenemos se lee sin ella, se
    edita sin 422 y la puerta no bloquea por ella. Queda en
    ``missing_capabilities``."""
    await turn_reservas_on(db_session, biz)
    body = await _job(client, biz, fake_redis, FakeBuilder(reply=RECEPTION), name="Recepción")
    agent_id = body["result"]["agent_id"]
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == uuid.UUID(agent_id),
                AgentConfig.status == AgentConfigStatus.STAGED,
            )
        )
        assert cfg is not None
        cfg.spec = {
            **cfg.spec,
            "skills": [
                *(cfg.spec.get("skills") or []),
                {"key": "facturar", "enabled": True, "integration": "quickbooks"},
            ],
            "connection_requests": [{"integration": "quickbooks", "reason": "Para facturar"}],
        }
        cfg.policies = {k: v for k, v in (cfg.policies or {}).items() if k != "builder"}

    read = await _draft(client, biz, agent_id)
    assert "quickbooks" not in json.dumps(read["spec"]), "se lee sin ella"
    assert ("integration", "quickbooks", "integration_unknown") in _keys(
        read["missing_capabilities"]
    )
    gate = await _gate(db_session, biz, agent_id)
    assert "integration_unknown" not in json.dumps(gate.to_json())

    # La consola manda el documento que leyó, con un cambio cualquiera.
    edited = copy.deepcopy(read["spec"])
    edited["voice"]["greeting"] = "¡Buenas!"
    patch = await client.patch(
        f"{_agents_url(biz)}/agents/{agent_id}/draft",
        json={"spec": edited},
        headers={**biz.headers(), "If-Match": f'"{read["revision"]}"'},
    )
    assert patch.status_code == 200, patch.text
    # Y un cliente que todavía manda la integración: tampoco se rechaza.
    stale = copy.deepcopy(edited)
    stale["connection_requests"] = [{"integration": "quickbooks", "reason": "Para facturar"}]
    again = await client.patch(
        f"{_agents_url(biz)}/agents/{agent_id}/draft",
        json={"spec": stale},
        headers={**biz.headers(), "If-Match": f'"{patch.json()["revision"]}"'},
    )
    assert again.status_code == 200, again.text
    out = again.json()
    assert "quickbooks" not in json.dumps(out["spec"])
    assert ("integration", "quickbooks", "integration_unknown") in _keys(
        out["missing_capabilities"]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        stored = await db_session.scalar(
            sa.select(AgentConfig)
            .where(
                AgentConfig.agent_id == uuid.UUID(agent_id),
                AgentConfig.status == AgentConfigStatus.STAGED,
            )
            .execution_options(populate_existing=True)
        )
    assert stored is not None and "quickbooks" not in json.dumps(stored.spec)
    assert "quickbooks" in json.dumps(stored.policies["builder"])
