"""Garantías 2 y 9 — un agente solo ve lo que tiene activado (spec 047, T013).

Requisitos 56.2 y 35.6: un agente no ve las herramientas ni las credenciales de
una conexión que no tiene activada, aunque su cliente sí la tenga; lo mismo con
las herramientas dinámicas de ``composio_proxy``.

**Lo que es «activado» hoy.** Hasta el bloque F no existe la activación por
agente sobre una conexión del cliente: lo activado es lo que nombra la versión
del agente (``agent_configs.tools`` y sus ``runtime_*``), y la conexión es del
cliente (``tenant_connectors``, ``tenant_credentials``). El barrido se escribe
contra eso y está preparado para crecer:

1. **Toda herramienta del registro MCP**, una a una: fuera de la lista del
   agente no llega al modelo ni se ejecuta (``test_every_registry_tool_…``).
2. **Todo el registro repartido entre dos agentes hermanos, en cada intención**:
   ninguno recibe una herramienta del otro.
3. **Las herramientas dinámicas de Composio**: solo las de conexiones
   conectadas del cliente, filtradas por la lista del agente, y con la
   credencial del cliente; un agente que no las nombra no recibe ni el proxy ni
   la credencial.
4. **Toda fuente de herramientas del ``AgentBundle``**: cada campo del bundle
   está clasificado —fuente de herramientas con su caso, o no— y un campo nuevo
   (las activaciones del bloque F) lo pone en rojo hasta tener su caso.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest
from nexus_mcp import ToolNotInWhitelist, build_default_registry
from nexus_mcp.servers.composio_proxy import load_blueprints_for_tenant
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.pipeline import (
    VALID_INTENTS,
    _filter_tools_for_intent_with_composio,
    _resolve_mcp_token,
    _view_with_composio,
)
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Connector,
    Tenant,
    TenantConnector,
    TenantCredentials,
    ToolCatalog,
    ToolStatus,
)

from .conftest import seed_active_agent_config

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

_REGISTRY_NAMES = sorted(build_default_registry().names())


# ── 1. cada herramienta del registro, fuera de la lista ─────────────────────


@pytest.mark.parametrize("tool", _REGISTRY_NAMES)
async def test_every_registry_tool_stays_out_unless_it_is_on_the_list(tool: str) -> None:
    """La lista del agente es el techo: sin ``tool`` en ella, ni su definición
    llega al modelo ni el registro la ejecuta aunque el modelo la invente."""
    registry = build_default_registry()
    everything_else = [n for n in registry.names() if n != tool]
    offered = {d.name for d in registry.get_tool_definitions(everything_else)}
    assert tool not in offered
    assert offered == set(everything_else)
    with tenant_context(uuid.uuid4()), pytest.raises(ToolNotInWhitelist):
        await registry.dispatch(tool, {}, whitelist=everything_else)


def test_the_sweep_covers_the_whole_registry() -> None:
    assert len(_REGISTRY_NAMES) >= 50, _REGISTRY_NAMES


# ── 2. dos hermanos con el registro repartido ──────────────────────────────


async def _sibling(db_session, tenant_id: uuid.UUID, *, version: int, tools: list[str], **runtime):
    agent = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name=f"Hermano {version}")
    db_session.add(agent)
    await db_session.commit()
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=version,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered=f"agente {version}",
            channels=[],
            tools=tools,
            policies={},
            seed_template_ref=None,
            **runtime,
        )
    )
    await db_session.commit()
    return agent.id


async def test_siblings_never_see_each_others_tools_on_any_intent(
    db_session, tenants_ab, agent_loader
) -> None:
    a = tenants_ab["a"]
    principal = await seed_active_agent_config(db_session, tenant_id=a, system_prompt="p", tools=[])
    half_x, half_y = _REGISTRY_NAMES[0::2], _REGISTRY_NAMES[1::2]
    x = await _sibling(db_session, a, version=principal.version + 1, tools=half_x)
    y = await _sibling(db_session, a, version=principal.version + 2, tools=half_y)

    for me, mine, theirs in ((x, set(half_x), set(half_y)), (y, set(half_y), set(half_x))):
        bundle = await agent_loader.load(a, me)
        assert set(bundle.tools) == mine
        for intent in VALID_INTENTS:
            offered = set(_filter_tools_for_intent_with_composio(bundle, intent))
            assert offered <= mine, f"{intent}: fuera de su lista {sorted(offered - mine)}"
            assert not offered & theirs, f"{intent}: herramientas del hermano {offered & theirs}"


# ── 3. las herramientas dinámicas de Composio ──────────────────────────────

CAL_LIST, CAL_CREATE, MAIL_SEND = (
    "googlecalendar.list_events",
    "googlecalendar.create_event",
    "gmail.send_email",
)


async def _composio_world(db_session, tenants_ab) -> dict[str, object]:
    """El cliente A tiene Calendar conectado y Gmail desconectado; el B, Calendar
    conectado con su propia conexión."""
    calendar = Connector(
        slug=f"g2-cal-{uuid.uuid4().hex[:6]}",
        display_name="Calendar",
        vendor="Google",
        category="calendar",
        capabilities=[],
        auth_kind="oauth_composio",
        mcp_server_ref="composio:googlecalendar",
        provider_meta={},
    )
    gmail = Connector(
        slug=f"g2-mail-{uuid.uuid4().hex[:6]}",
        display_name="Gmail",
        vendor="Google",
        category="email",
        capabilities=[],
        auth_kind="oauth_composio",
        mcp_server_ref="composio:gmail",
        provider_meta={},
    )
    db_session.add_all([calendar, gmail])
    await db_session.flush()
    for name, connector in ((CAL_LIST, calendar), (CAL_CREATE, calendar), (MAIL_SEND, gmail)):
        db_session.add(
            ToolCatalog(
                name=name,
                description=name,
                mcp_server="composio:" + connector.mcp_server_ref.split(":", 1)[1],
                input_schema={"type": "object", "properties": {}},
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
            )
        )
    a, b = tenants_ab["a"], tenants_ab["b"]
    db_session.add_all(
        [
            TenantConnector(
                tenant_id=a,
                connector_id=calendar.id,
                status="connected",
                credentials_ref={"composio_connection_id": "conn-A-cal"},
            ),
            TenantConnector(
                tenant_id=a,
                connector_id=gmail.id,
                status="disconnected",
                credentials_ref={"composio_connection_id": "conn-A-mail"},
            ),
            TenantConnector(
                tenant_id=b,
                connector_id=calendar.id,
                status="connected",
                credentials_ref={"composio_connection_id": "conn-B-cal"},
            ),
        ]
    )
    await db_session.commit()
    slug_a = await db_session.scalar(select(Tenant.slug).where(Tenant.id == a))
    return {"a": a, "b": b, "user_a": f"tenant_{slug_a}"}


async def test_composio_tools_come_only_from_the_clients_live_connections(
    db_session, tenants_ab
) -> None:
    world = await _composio_world(db_session, tenants_ab)
    blueprints = await load_blueprints_for_tenant(world["a"])
    assert {bp.tool_name for bp in blueprints} == {CAL_LIST, CAL_CREATE}, (
        "un conector desconectado no aporta herramientas"
    )
    assert {bp.connection_id for bp in blueprints} == {"conn-A-cal"}, "credencial de otro cliente"
    assert {bp.user_id for bp in blueprints} == {world["user_a"]}

    narrowed = await load_blueprints_for_tenant(world["a"], whitelist=frozenset({CAL_LIST}))
    assert [bp.tool_name for bp in narrowed] == [CAL_LIST]


async def test_an_agent_that_does_not_name_a_composio_tool_gets_no_proxy_nor_credential(
    db_session, tenants_ab
) -> None:
    """El cliente tiene Calendar; el agente que no lo nombra no recibe nada de
    Calendar, y el que nombra una herramienta recibe esa sola."""
    world = await _composio_world(db_session, tenants_ab)
    base = build_default_registry()

    without = ("client.get_history",)
    view, names = await _view_with_composio(
        registry=base, tenant_id=world["a"], available_names=without
    )
    assert view is base and names == without, "sin nombrarla, el agente recibió un proxy"

    with_one = ("client.get_history", CAL_LIST)
    view, names = await _view_with_composio(
        registry=base, tenant_id=world["a"], available_names=with_one
    )
    proxies = {n: view._tools[n] for n in view.names() if n not in base.names()}
    assert set(proxies) == {CAL_LIST}, f"proxies de más: {sorted(proxies)}"
    assert proxies[CAL_LIST]._blueprint.connection_id == "conn-A-cal"


# ── 4. toda fuente de herramientas del bundle ──────────────────────────────

#: Campo del ``AgentBundle`` → el caso que prueba que sale de la versión del
#: propio agente. Un campo que añada herramientas al turno va aquí.
TOOL_SOURCES: dict[str, str] = {
    "tools": "test_siblings_never_see_each_others_tools_on_any_intent",
    "runtime_skills": "test_hosted_tools_come_from_the_agents_own_version",
    "runtime_mcp_servers": "test_hosted_tools_come_from_the_agents_own_version",
    "runtime_mcp_connector": "test_hosted_tools_come_from_the_agents_own_version",
    "runtime_memory_tool": "test_hosted_tools_come_from_the_agents_own_version",
}

#: Campos que no ponen herramientas delante del modelo, con su razón.
NOT_TOOL_SOURCES: dict[str, str] = {
    "tenant_id": "Identidad del cliente del bundle.",
    "agent_id": "Identidad del agente del bundle.",
    "version": "Número de la versión cargada.",
    "version_id": "Id de la versión cargada.",
    "system_prompt": "Texto del system; la garantía 5 (test_48) cubre lo que lleva.",
    "policies": (
        "Pueden QUITAR herramientas (lectura de un admin de solo lectura, CP-13), "
        "nunca añadirlas: el filtro del handler solo itera nombres de ``tools``."
    ),
    "timezone": "La zona horaria del negocio, para la nota de la hora.",
    "runtime_outcome_grader": "Activa el grader, que no expone herramientas al modelo.",
    "grader_mode": "Cuándo corre el grader.",
    "grader_sample_rate": "Con qué muestreo corre el grader.",
    "model_bindings": "Qué modelo responde; no qué herramientas tiene (garantía 7).",
}


def test_every_bundle_field_is_classified() -> None:
    fields = {f.name for f in dataclasses.fields(AgentBundle)}
    classified = TOOL_SOURCES.keys() | NOT_TOOL_SOURCES.keys()
    unknown = sorted(fields - classified)
    assert not unknown, (
        f"campos nuevos del AgentBundle sin clasificar: {unknown}. Si ponen "
        "herramientas o credenciales delante del modelo (las activaciones del "
        "bloque F), van a TOOL_SOURCES con su caso adversarial."
    )
    assert not classified - fields, f"campos que ya no existen: {sorted(classified - fields)}"
    for case in set(TOOL_SOURCES.values()):
        assert callable(globals().get(case)), f"caso que no existe: {case}"


async def test_hosted_tools_come_from_the_agents_own_version(
    db_session, tenants_ab, agent_loader
) -> None:
    """Skills, servidores MCP y la herramienta de memoria vienen de la versión
    del agente: el hermano que no los tiene no los recibe. La credencial del
    servidor MCP se resuelve bajo la RLS del cliente: la del vecino con la misma
    clave no aparece."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    principal = await seed_active_agent_config(db_session, tenant_id=a, system_prompt="p", tools=[])
    x = await _sibling(
        db_session,
        a,
        version=principal.version + 1,
        tools=[],
        runtime_skills=[{"skill_id": "skill-x", "version": "latest"}],
        runtime_mcp_servers=[
            {"name": "crm", "url": "https://mcp.example/x", "credential_key": "mcp-crm"}
        ],
        runtime_mcp_connector=True,
        runtime_memory_tool=True,
    )
    y = await _sibling(db_session, a, version=principal.version + 2, tools=[])
    db_session.add_all(
        [
            TenantCredentials(tenant_id=a, integration="mcp-crm", encrypted_payload=b"tok-A"),
            TenantCredentials(tenant_id=b, integration="mcp-crm", encrypted_payload=b"tok-B"),
        ]
    )
    await db_session.commit()

    bx = await agent_loader.load(a, x)
    by = await agent_loader.load(a, y)
    assert [s["skill_id"] for s in bx.runtime_skills] == ["skill-x"]
    assert [s["name"] for s in bx.runtime_mcp_servers] == ["crm"]
    assert bx.runtime_mcp_connector and bx.runtime_memory_tool
    assert by.runtime_skills == () and by.runtime_mcp_servers == ()
    assert not by.runtime_mcp_connector and not by.runtime_memory_tool

    assert await _resolve_mcp_token(a, "mcp-crm") == "tok-A"
    assert await _resolve_mcp_token(b, "mcp-crm") == "tok-B"
    assert await _resolve_mcp_token(uuid.uuid4(), "mcp-crm") is None
