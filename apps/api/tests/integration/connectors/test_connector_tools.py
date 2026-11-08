"""«Herramientas» de un conector, en la pestaña Conectores de un agente.

- **La lectura** dice, por herramienta, qué hace, si está encendida en el borrador y
  en lo publicado, si no se puede apagar y si le falta permiso. Escribir sigue siendo
  ``PUT …/capabilities``, así que la lista blanca no cambia de forma.
- **Lo que apaga una persona se queda apagado**: ni guardar «Ajustes» ni volver a
  autorizar lo traen de vuelta.
- **Lo que dejaría una promesa sin cumplir se dice al apagarlo**, no al publicar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Connector,
    Partner,
    TenantConnector,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.db.models.agent_spec import AgentTest
from nexus_api.services.connectors import booking_skills
from nexus_api.services.connectors.service import complete_consent_from_webhook
from nexus_api.services.testing.suites import add_test, ensure_suite

from ..business._business_world import Biz, new_business, seed_agent
from ._activation_world import READ, SLUG, SPEC, WRITE, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CAL_FREE = "CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES"
CAL_BOOK = "CALENDLY_POST_INVITEE"
CAL_INVITE = "CALENDLY_POST_INVITEE"
CAL_LINK = "CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK"


def _structured(tools: list[str], *, text: str, procedures: list[Any] | None = None) -> dict:
    return {
        "schema_version": "1",
        "mode": "structured",
        "identity": {"name": "Ventas", "description": "Atiende por WhatsApp."},
        "voice": {"languages": ["es"]},
        "instructions": {"sections": [{"title": "Qué haces", "body": text}]},
        "services": {"mode": "all", "faqs": []},
        "escalation": {},
        "tools": tools,
        "procedures": procedures or [],
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "pinned", "deployment": "nexus/current-binding"},
        "memory": {"scope": "shared"},
    }


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Tienda Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return biz


@pytest.fixture(autouse=True)
def _this_connector_books(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(booking_skills.BOOKING_TOOLS, SLUG, (READ, WRITE))


async def _agent(
    db_session: AsyncSession,
    biz: Biz,
    *,
    tools: list[str],
    text: str = "Responde lo que te preguntan.",
    procedures: list[Any] | None = None,
) -> uuid.UUID:
    agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="Vende.", tools=tools
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.get(AgentConfig, cfg_id)
        assert cfg is not None
        cfg.spec = _structured(tools, text=text, procedures=procedures)
    await db_session.commit()
    return agent_id


async def _catalog_tool(
    db_session: AsyncSession,
    connector: Connector,
    name: str,
    *,
    read_only: bool = False,
    status: ToolStatus = ToolStatus.ACTIVE,
    schema: dict[str, Any] | None = None,
) -> None:
    row = await db_session.scalar(sa.select(ToolCatalog).where(ToolCatalog.name == name))
    if row is None:
        row = ToolCatalog(name=name, description=name, mcp_server=f"internal:{SLUG}")
        db_session.add(row)
    row.connector_id = connector.id
    row.status = status
    row.read_only = read_only
    row.destructive = not read_only
    row.default_mode = "always" if read_only else "blocked"
    row.input_schema = schema or {}
    await db_session.commit()


async def _tools(client: Any, biz: Biz, agent_id: uuid.UUID, **params: str) -> dict[str, Any]:
    res = await client.get(
        f"/console/clients/{biz.ref}/agents/{agent_id}/integrations/{SLUG}/tools",
        params=params,
        headers=biz.headers(),
    )
    assert res.status_code == 200, res.text
    return res.json()


def _named(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in body["tools"]}


async def _switch(client: Any, biz: Biz, agent_id: uuid.UUID, key: str, *, enabled: bool) -> Any:
    return await client.put(
        f"/console/clients/{biz.ref}/capabilities?agent={agent_id}",
        json={"key": key, "kind": "tool", "enabled": enabled},
        headers=biz.headers(),
    )


async def _settings(client: Any, biz: Biz, agent_id: uuid.UUID, permission: str) -> None:
    res = await client.put(
        f"/console/clients/{biz.ref}/agents/{agent_id}/activations/{SLUG}",
        json={"permission": permission, "settings": {}},
        headers=biz.headers(),
    )
    assert res.status_code == 200, res.text


async def _draft_tools(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> set[str]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        draft = await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED)
            .execution_options(populate_existing=True)
        )
        assert draft is not None
        return set(draft.tools or [])


async def _expects_booking(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite = await ensure_suite(db_session, agent_id)
        await add_test(
            db_session,
            suite,
            {
                "name": "Coge una cita",
                "first_message": "Quiero cita",
                "expected_state": {"booking": {"created": True}},
            },
            kind="case",
        )
    await db_session.commit()


# ── la lectura ─────────────────────────────────────────────────────────────


async def test_the_tools_of_a_connector_with_their_state(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, CAL_BOOK)
    await _catalog_tool(db_session, connector, "tienda_test.gone", status=ToolStatus.DEPRECATED)
    agent_id = await _agent(db_session, biz, tools=[READ])
    await _settings(client, biz, agent_id, "ask_before_write")
    assert await _draft_tools(db_session, biz, agent_id) >= {READ, WRITE}
    assert (await _switch(client, biz, agent_id, WRITE, enabled=False)).status_code == 200
    assert (await _switch(client, biz, agent_id, CAL_BOOK, enabled=True)).status_code == 200

    body = await _tools(client, biz, agent_id)

    assert body["slug"] == SLUG and body["permission"] == "ask_before_write"
    tools = _named(body)
    assert set(tools) == {READ, WRITE, CAL_BOOK}, "ni lo retirado ni lo de otro conector"
    assert set(tools[READ]) == {
        "name",
        "title",
        "description",
        "read_only",
        "enabled",
        "enabled_in_active",
        "locked",
        "locked_by",
        "needs_write_permission",
        "suggested",
    }
    assert tools[READ]["enabled"] and tools[READ]["enabled_in_active"] and tools[READ]["read_only"]
    assert not tools[WRITE]["enabled"] and not tools[WRITE]["read_only"]
    assert tools[CAL_BOOK]["enabled"] and not tools[CAL_BOOK]["enabled_in_active"]
    assert tools[READ]["title"] == "List items", "un nombre legible, no el del catálogo"
    assert tools[CAL_BOOK]["title"] == "Reservar una cita en Calendly"
    assert body["tools"][0]["name"] == READ, "lo recomendado primero, en su orden"
    assert tools[READ]["suggested"] and tools[WRITE]["suggested"]
    assert not tools[CAL_BOOK]["suggested"]

    english = _named(await _tools(client, biz, agent_id, lang="en"))
    assert english[CAL_BOOK]["title"] == "Book an appointment in Calendly"


async def test_what_needs_more_than_reading_says_so(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await _agent(db_session, biz, tools=[])
    await _settings(client, biz, agent_id, "read")

    tools = _named(await _tools(client, biz, agent_id))
    assert tools[WRITE]["needs_write_permission"] is True
    assert tools[READ]["needs_write_permission"] is False

    await _settings(client, biz, agent_id, "read_write")
    tools = _named(await _tools(client, biz, agent_id))
    assert tools[WRITE]["needs_write_permission"] is False


async def test_a_delete_already_in_the_catalog_as_reading_is_not_shown_as_reading(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, "TIENDA_LIST_DELETE", read_only=True)
    agent_id = await _agent(db_session, biz, tools=[])
    await _settings(client, biz, agent_id, "read")

    tool = _named(await _tools(client, biz, agent_id))["TIENDA_LIST_DELETE"]
    assert tool["read_only"] is False and tool["needs_write_permission"] is True


async def test_only_inside_the_client(
    client: Any, db_session: AsyncSession, biz: Biz, console_world: dict[str, Any]
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await _agent(db_session, biz, tools=[])
    other = await new_business(client, db_session, console_world, name="Otra", label="b")
    theirs, _cfg = await seed_agent(
        db_session, other.tenant_id, name="Suyo", prompt="Vende.", tools=[]
    )

    foreign_agent = await client.get(
        f"/console/clients/{biz.ref}/agents/{theirs}/integrations/{SLUG}/tools",
        headers=biz.headers(),
    )
    assert foreign_agent.status_code == 404
    foreign_client = await client.get(
        f"/console/clients/{other.ref}/agents/{agent_id}/integrations/{SLUG}/tools",
        headers=biz.headers(),
    )
    assert foreign_client.status_code in (403, 404)
    unknown = await client.get(
        f"/console/clients/{biz.ref}/agents/{agent_id}/integrations/no_existe/tools",
        headers=biz.headers(),
    )
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "unknown_integration"


# ── lo que no se puede apagar ──────────────────────────────────────────────


async def test_a_tool_a_task_uses_says_why_it_cannot_be_switched_off(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await _agent(
        db_session,
        biz,
        tools=[READ, WRITE],
        procedures=[
            {"id": "pedido", "title": "Pedido", "when": "Siempre", "steps": "A", "tools": [WRITE]}
        ],
    )

    tools = _named(await _tools(client, biz, agent_id))
    assert tools[WRITE]["locked"] is True and tools[WRITE]["locked_by"] == "task"
    assert tools[READ]["locked"] is False and tools[READ]["locked_by"] is None

    off = await _switch(client, biz, agent_id, WRITE, enabled=False)
    assert off.status_code == 422, off.text
    assert off.json()["detail"] == {"code": "tool_in_use", "locked_by": "task"}


async def test_the_only_tool_that_books_is_refused_when_a_test_expects_a_booking(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Antes solo lo sabía ``reservas.create``: apagar el del calendario pasaba y la
    puerta de publicar lo bloqueaba después."""
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, CAL_FREE, read_only=True)
    await _catalog_tool(db_session, connector, CAL_BOOK)
    agent_id = await _agent(db_session, biz, tools=[CAL_FREE, CAL_BOOK])
    await _expects_booking(db_session, biz, agent_id)

    tools = _named(await _tools(client, biz, agent_id))
    assert tools[CAL_BOOK]["locked_by"] == "test"
    assert tools[CAL_FREE]["locked"] is False

    off = await _switch(client, biz, agent_id, CAL_BOOK, enabled=False)
    assert off.status_code == 422, off.text
    assert off.json()["detail"] == {"code": "tool_in_use", "locked_by": "test"}
    assert (await _switch(client, biz, agent_id, CAL_FREE, enabled=False)).status_code == 200


async def test_the_only_tool_that_keeps_a_promise_of_the_text_is_refused(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, CAL_BOOK)
    agent_id = await _agent(db_session, biz, tools=[CAL_BOOK], text="Da cita a los clientes.")

    assert _named(await _tools(client, biz, agent_id))[CAL_BOOK]["locked_by"] == "promise"
    off = await _switch(client, biz, agent_id, CAL_BOOK, enabled=False)
    assert off.status_code == 422, off.text
    assert off.json()["detail"] == {"code": "tool_in_use", "locked_by": "promise"}


async def test_with_two_tools_that_book_one_can_go_and_the_last_cannot(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, CAL_INVITE)
    await _catalog_tool(db_session, connector, CAL_LINK)
    agent_id = await _agent(
        db_session, biz, tools=[CAL_INVITE, CAL_LINK], text="Da cita a los clientes."
    )
    await _expects_booking(db_session, biz, agent_id)

    tools = _named(await _tools(client, biz, agent_id))
    assert not tools[CAL_INVITE]["locked"] and not tools[CAL_LINK]["locked"]
    assert (await _switch(client, biz, agent_id, CAL_LINK, enabled=False)).status_code == 200

    assert _named(await _tools(client, biz, agent_id))[CAL_INVITE]["locked"] is True
    off = await _switch(client, biz, agent_id, CAL_INVITE, enabled=False)
    assert off.status_code == 422 and off.json()["detail"]["code"] == "tool_in_use"


async def test_what_lets_the_agent_pick_a_customer_is_refused_with_its_code(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(
        db_session,
        connector,
        "TIENDA_GET_CUSTOMER",
        read_only=True,
        schema={"type": "object", "properties": {"customer_email": {"type": "string"}}},
    )
    agent_id = await _agent(db_session, biz, tools=[])

    on = await _switch(client, biz, agent_id, "TIENDA_GET_CUSTOMER", enabled=True)

    assert on.status_code == 422, on.text
    detail = on.json()["detail"]
    assert detail["code"] == "spec_invalid"
    assert [p["code"] for p in detail["problems"]] == ["end_customer_argument"]


async def test_an_agent_of_before_keeps_the_same_promises(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Sin AgentSpec estructurado no pasaba ni por ``tool_in_use`` ni por las pruebas:
    la pantalla no puede decir «deja las pruebas desactualizadas» y no hacerlo."""
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="Vende.", tools=[READ, WRITE]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.get(AgentConfig, cfg_id)
        assert cfg is not None
        cfg.spec = {
            **SPEC,
            "identity": {"name": "Ventas", "description": "Atiende y vende por WhatsApp."},
        }
        suite = await ensure_suite(db_session, agent_id)
        await add_test(db_session, suite, {"name": "Hola", "first_message": "Hola"}, kind="case")
    await db_session.commit()

    assert _named(await _tools(client, biz, agent_id))[WRITE]["locked_by"] == "task"
    off = await _switch(client, biz, agent_id, WRITE, enabled=False)
    assert off.status_code == 422 and off.json()["detail"]["code"] == "tool_in_use"
    assert (await _switch(client, biz, agent_id, READ, enabled=False)).status_code == 200

    async with tenant_scoped_session(db_session, biz.tenant_id):
        stale = await db_session.scalars(
            sa.select(AgentTest.stale)
            .where(AgentTest.suite_id == suite.id)
            .execution_options(populate_existing=True)
        )
        assert all(stale.all()), "apagar algo deja las pruebas desactualizadas"


async def test_what_connecting_listed_outside_the_document_follows_the_switch(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Encender al conectar escribe la lista del borrador y no el documento. Para la
    pantalla está encendida: apagarla la apaga, y apagar otra no se la lleva."""
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, CAL_FREE, read_only=True)
    agent_id = await _agent(db_session, biz, tools=[READ])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id)
        )
        assert cfg is not None
        cfg.tools = [READ, WRITE, CAL_FREE]
    await db_session.commit()

    assert (await _switch(client, biz, agent_id, READ, enabled=False)).status_code == 200
    assert await _draft_tools(db_session, biz, agent_id) == {WRITE, CAL_FREE}

    assert (await _switch(client, biz, agent_id, WRITE, enabled=False)).status_code == 200
    assert await _draft_tools(db_session, biz, agent_id) == {CAL_FREE}


async def test_a_full_list_is_refused_with_its_code(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    many = [f"TIENDA_LIST_{i}" for i in range(60)]
    for name in many:
        await _catalog_tool(db_session, connector, name, read_only=True)
    agent_id = await _agent(db_session, biz, tools=many)
    assert (await _tools(client, biz, agent_id))["tools"], "60 sí caben"

    on = await _switch(client, biz, agent_id, READ, enabled=True)

    assert on.status_code == 422, on.text
    assert on.json()["detail"] == {"code": "too_many_tools", "max": 60}


# ── lo que apaga una persona se queda apagado ──────────────────────────────


async def test_saving_the_settings_does_not_bring_back_what_a_person_switched_off(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await _agent(db_session, biz, tools=[])

    await _settings(client, biz, agent_id, "read_write")
    assert await _draft_tools(db_session, biz, agent_id) >= {READ, WRITE}, "la primera vez, sí"

    assert (await _switch(client, biz, agent_id, WRITE, enabled=False)).status_code == 200
    await _settings(client, biz, agent_id, "read_write")

    assert WRITE not in await _draft_tools(db_session, biz, agent_id)


async def test_asking_for_more_permission_does_not_bring_it_back_either(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """El camino que abre la propia pantalla: «necesita Leer y escribir» → Ajustes.
    Aquí la lista automática todavía no había corrido nunca."""
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await _agent(db_session, biz, tools=[READ, WRITE])
    await _settings(client, biz, agent_id, "read")

    assert (await _switch(client, biz, agent_id, WRITE, enabled=False)).status_code == 200
    await _settings(client, biz, agent_id, "read_write")

    assert WRITE not in await _draft_tools(db_session, biz, agent_id)


async def test_authorizing_again_does_not_bring_back_what_a_person_switched_off(
    client: Any, db_session: AsyncSession, biz: Biz, fake_composio: Any
) -> None:
    """La autorización corre dos encendidos: el de lo que se enciende al conectar y el
    de reservar. Ninguno de los dos pasa por encima de una persona."""
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    agent_id = await _agent(db_session, biz, tools=[])

    async def authorize() -> None:
        async with tenant_scoped_session(db_session, biz.tenant_id):
            install = await db_session.get(TenantConnector, install_id)
            assert install is not None
            install.credentials_ref = {
                **dict(install.credentials_ref or {}),
                "composio_connection_id": "ca_again",
            }
            install.config = {
                "pending_activation": {
                    "agent_id": str(agent_id),
                    "permission": "read_write",
                    "by": "test",
                }
            }
            await complete_consent_from_webhook(
                db_session,
                composio_connection_id="ca_again",
                upstream_status="ACTIVE",
                granted_scopes=[],
                composio=fake_composio,
            )
        await db_session.commit()

    await authorize()
    assert await _draft_tools(db_session, biz, agent_id) >= {READ, WRITE}, "la primera vez, sí"

    assert (await _switch(client, biz, agent_id, WRITE, enabled=False)).status_code == 200
    assert (await _switch(client, biz, agent_id, READ, enabled=False)).status_code == 200
    await authorize()

    assert not {READ, WRITE} & await _draft_tools(db_session, biz, agent_id)


# ── lo que encontró la revisión ─────────────────────────────────────────────


async def test_a_sector_test_does_not_lock_the_only_tool_that_books(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Las del sector aplican según las herramientas: contarlas sería un candado circular.
    Encender lo único que reserva volvería aplicables sus pruebas, que impedirían apagarlo."""
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, CAL_BOOK)
    agent_id = await _agent(db_session, biz, tools=[CAL_BOOK])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite = await ensure_suite(db_session, agent_id)
        await add_test(
            db_session,
            suite,
            {
                "name": "Pide cita para mañana",
                "first_message": "¿Tienes hueco mañana?",
                "expected_state": {"booking": {"created": True}},
            },
            kind="sector",
            by="system",
        )
    await db_session.commit()

    assert _named(await _tools(client, biz, agent_id))[CAL_BOOK]["locked_by"] != "test"


async def test_reading_only_stops_an_old_row_whose_name_says_it_writes(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Una fila sincronizada antes del arreglo sigue diciendo «solo lee». El turno no se
    fía: con el permiso «Solo leer», lo que borra no pasa."""
    from nexus_api.services import activations

    deletes = "TIENDA_TEST_CALENDAR_LIST_DELETE"
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    await _catalog_tool(db_session, connector, deletes, read_only=True)
    agent_id = await _agent(db_session, biz, tools=[deletes])
    await _settings(client, biz, agent_id, "read")

    async with tenant_scoped_session(db_session, biz.tenant_id):
        policy = await activations.tool_policy(db_session, biz.tenant_id, agent_id)
    assert deletes in policy.blocked
