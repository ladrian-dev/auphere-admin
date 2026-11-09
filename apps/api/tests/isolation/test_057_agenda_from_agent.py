"""Garantías 1 y 2 sobre «la agenda desde el agente» — spec 057 (T005 y T006, API).

Una puerta nueva a dos datos sensibles —encender un módulo del cliente y escribir la
lista blanca de herramientas de un agente— se prueba por sus costuras, intentando el
cruce y mirando el dato del otro lado:

**Garantía 1 (RLS, el cliente de la ruta).** El partner A, con el ``ref`` de un cliente
del partner B, llama a ``PUT/GET …/agenda``, ``GET …/agenda/tools`` y ``POST
…/draft-jobs`` con ``agenda=true``. Recibe el 404 opaco, idéntico al de un ``ref`` que no
existe, y en B no queda rastro: ni ``client_access``, ni ``reservation_settings``, ni
auditoría, ni borrador, ni trabajos, ni propuestas. Un cuerpo con ``tenant_id`` o
``partner_id`` no pasa (``extra="forbid"``).

**Garantía 2 (lista blanca por agente).** Encender Reservas desde un agente o desde
Acceso da ``reservas.*`` solo a ese agente y a los que dan citas; el borrador y la
versión activa de un agente que no da citas siguen sin ninguna. Y un barrido estructural:
todo sitio del código que escribe nombres ``reservas.*`` en una versión está en una lista
de permitidos con la prueba que lo cubre; un sitio nuevo pone esto en rojo (constitución
§I: barrer, no enumerar).
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    ClientAccess,
    Job,
    ReservationSettings,
)
from nexus_api.db.models.agent_spec import Proposal

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_ROOT = Path(__file__).resolve().parents[3]  # apps/


def _spec(description: str, tools: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": "Agente", "description": description},
        "instructions": {"legacy_text": description},
        "tools": tools,
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "profile", "profile": "auto"},
        "memory": {"scope": "shared"},
    }


async def _agent(tenant_id: uuid.UUID, name: str, description: str, version: int) -> uuid.UUID:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent = Agent(tenant_id=tenant_id, name=name)
        session.add(agent)
        await session.flush()
        session.add(
            AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=version,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=description,
                channels=[],
                tools=["escalate.escalate_to_human"],
                policies={},
                spec=_spec(description, ["escalate.escalate_to_human"]),
                created_by="test",
            )
        )
        await session.commit()
        return agent.id


async def _count(tenant_id: uuid.UUID, model: Any, *where: Any) -> int:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        stmt = sa.select(sa.func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int(await session.scalar(stmt) or 0)


async def _tools(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> set[str]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.select(AgentConfig.tools).where(AgentConfig.agent_id == agent_id)
            )
        ).scalars()
        return {t for tools in rows for t in (tools or [])}


# ── garantía 1 ─────────────────────────────────────────────────────────────


async def test_another_partner_cannot_turn_on_or_write_anything(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    b_agent = await _agent(b["tenant_id"], "Recepción", "Agendas citas del salón.", 1)
    before = {
        model.__name__: await _count(b["tenant_id"], model)
        for model in (ClientAccess, ReservationSettings, AuditLog, Job, Proposal)
    }
    agenda = f"/console/clients/{b['ref']}/agents/{b_agent}/agenda"
    missing = f"/console/clients/does-not-exist/agents/{b_agent}/agenda"
    body = {"enabled": True, "reservas": {"mode": "services"}}

    for method, url, payload in (
        ("PUT", agenda, body),
        ("GET", agenda, None),
        ("GET", f"{agenda}/tools", None),
    ):
        foreign = await client.request(method, url, headers=a["headers"](), json=payload)
        other = await client.request(
            method, url.replace(agenda, missing), headers=a["headers"](), json=payload
        )
        assert foreign.status_code == 404, f"{method} {url}: {foreign.text}"
        assert foreign.json() == other.json()

    draft = await client.post(
        f"/console/clients/{b['ref']}/agents/draft-jobs",
        json={
            "name": "Robo",
            "description": "Agenda citas del salón ajeno.",
            "agenda": True,
            "reservas": {"mode": "services"},
        },
        headers=a["headers"](),
    )
    assert draft.status_code == 404, draft.text

    after = {
        model.__name__: await _count(b["tenant_id"], model)
        for model in (ClientAccess, ReservationSettings, AuditLog, Job, Proposal)
    }
    assert after == before
    assert not any(t.startswith("reservas.") for t in await _tools(b["tenant_id"], b_agent))
    assert (
        await _count(
            b["tenant_id"],
            AgentConfig,
            AgentConfig.agent_id == b_agent,
            AgentConfig.status == AgentConfigStatus.STAGED,
        )
        == 0
    )


@pytest.mark.parametrize("field", ["tenant_id", "partner_id"])
async def test_a_client_in_the_body_is_refused(client, console_world, field) -> None:
    a = console_world["a"]
    agent_id = await _agent(a["tenant_id"], "Recepción", "Agendas citas del salón.", 1)
    resp = await client.put(
        f"/console/clients/{a['ref']}/agents/{agent_id}/agenda",
        json={"enabled": True, "reservas": {"mode": "services"}, field: str(uuid.uuid4())},
        headers=a["headers"](),
    )
    assert resp.status_code == 422, resp.text
    assert await _count(a["tenant_id"], ReservationSettings) == 0


# ── garantía 2 ─────────────────────────────────────────────────────────────


async def test_turning_on_from_an_agent_gives_the_agenda_to_it_and_the_givers_only(
    client, console_world
) -> None:
    a = console_world["a"]
    origin = await _agent(a["tenant_id"], "Recepción", "Atiendes el WhatsApp del salón.", 1)
    giver = await _agent(a["tenant_id"], "Reservas web", "Reservas citas para las clientas.", 2)
    billing = await _agent(
        a["tenant_id"], "Cobros", "Revisas los comprobantes de pago de las clientas.", 3
    )
    resp = await client.put(
        f"/console/clients/{a['ref']}/agents/{origin}/agenda",
        json={"enabled": True, "reservas": {"mode": "services"}},
        headers=a["headers"](),
    )
    assert resp.status_code == 200, resp.text
    assert "reservas.create" in await _tools(a["tenant_id"], origin)
    assert "reservas.create" in await _tools(a["tenant_id"], giver)
    assert not any(t.startswith("reservas.") for t in await _tools(a["tenant_id"], billing))


async def test_turning_on_from_access_gives_nothing_to_who_does_not_give_appointments(
    client, console_world
) -> None:
    a = console_world["a"]
    billing = await _agent(
        a["tenant_id"], "Cobros", "Revisas los comprobantes de pago de las clientas.", 1
    )
    resp = await client.put(
        f"/console/clients/{a['ref']}/client-access",
        json={"enabled": False, "modules": ["reservas"], "reservas": {"mode": "services"}},
        headers=a["headers"](),
    )
    assert resp.status_code == 200, resp.text
    assert not any(t.startswith("reservas.") for t in await _tools(a["tenant_id"], billing))


#: Quién escribe ``reservas.*`` en una versión, y la prueba que demuestra que solo lo hace
#: en el agente de la ruta o en los que dan citas. Una entrada nueva necesita su prueba.
WRITERS: dict[tuple[str, str], str] = {
    ("api/src/nexus_api/services/reservations/passing.py", "_with_reservas"): (
        "tests/integration/reservas/test_057_turn_on_only_givers.py"
    ),
    ("api/src/nexus_api/services/reservations/passing.py", "_rewritten"): (
        "tests/integration/reservas/test_057_turn_on_only_givers.py"
    ),
    ("api/src/nexus_api/services/builder/agent_draft.py", "sanitize"): (
        "tests/unit/test_057_builder_agenda.py"
    ),
    ("api/src/nexus_api/services/builder/agent_draft.py", "offline_output"): (
        "tests/unit/test_057_builder_agenda.py"
    ),
    ("api/src/nexus_api/api/console/agent_builder.py", "_blank_spec"): (
        "tests/integration/builder/test_057_draft_job_with_agenda.py"
    ),
    ("api/src/nexus_api/api/console/agenda.py", "put_agenda"): (
        "tests/isolation/test_057_agenda_from_agent.py"
    ),
}

#: Lo que nombra ``reservas.*`` sin escribirlo en una versión (catálogo, nombres,
#: validación, el runtime que filtra, el servidor de Reservas).
_READERS = (
    "nexus_api/api/console/capability_names.py",
    "nexus_api/services/agent_spec/",
    "nexus_api/services/reservations/passing.py",  # RESERVAS_TOOLS y lecturas
    "nexus_worker/runtime/",
    "nexus_worker/simulation/",
    "nexus_mcp/",
    "nexus_api/services/testing/",
    "nexus_api/services/evals/",
    "nexus_api/services/templating/",
    "nexus_api/services/builder/guides/",
    "nexus_api/services/connectors/",
    "nexus_api/services/activations.py",
    "nexus_api/api/console/capabilities_client.py",  # escribe lo que le dan (set_agent_tools)
    "nexus_api/services/builder/agenda_text.py",  # solo propone; no escribe versiones
)


def _writes_reservas(func: ast.AST) -> bool:
    """La función construye una lista de herramientas con nombres ``reservas.*`` o con
    ``RESERVAS_TOOLS`` (lo que acaba en ``tools`` de una versión)."""
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and node.id == "RESERVAS_TOOLS":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "RESERVAS_TOOLS":
            return True
    return False


#: Funciones de un archivo con escritores que solo leen ``RESERVAS_TOOLS``.
READS: frozenset[tuple[str, str]] = frozenset(
    {
        ("api/src/nexus_api/api/console/agenda.py", "agenda_out"),
        ("api/src/nexus_api/api/console/agenda.py", "agenda_tools"),
    }
)


def test_every_writer_of_the_agenda_is_known() -> None:
    writer_files = {rel for rel, _ in WRITERS}
    found: set[tuple[str, str]] = set()
    for base in ("api/src", "worker/src"):
        for path in (_ROOT / base).rglob("*.py"):
            rel = str(path.relative_to(_ROOT))
            if rel not in writer_files and any(r in rel for r in _READERS):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _writes_reservas(
                    node
                ):
                    found.add((rel, node.name))
    unknown = found - set(WRITERS) - READS
    assert not unknown, (
        "Escriben reservas.* en una versión sin prueba de aislamiento: "
        f"{sorted(unknown)}. Añádelos a WRITERS con la prueba que demuestra que solo lo "
        "hacen en el agente de la ruta o en los que dan citas (o a READS si solo leen)."
    )
    for (rel, _name), test in WRITERS.items():
        assert (_ROOT / rel).exists(), rel
        assert (_ROOT / "api" / test).exists(), test
