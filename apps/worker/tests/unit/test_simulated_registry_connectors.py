"""Fallo ``el-playground-consulta-al-dueno-de-verdad`` — el registro simulado no
toca los sistemas del negocio (requisito 20.1; C8).

En el playground y en las pruebas, una herramienta de un conector (Composio o
cualquiera con ``connector_id`` en el catálogo) **no se ejecuta**, tampoco la que
solo lee: devolvería datos reales de los clientes finales, que el partner no debe
ver. El agente recibe un resultado simulado y vacío, marcado como tal, y la
pantalla, «Lo que habría hecho: Consultar …». Lo interno que solo lee datos del
propio negocio (la ficha, los servicios) sigue corriendo de verdad.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

import pytest
from nexus_api.core.tenant_context import tenant_context
from nexus_mcp import MCPRegistry
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_mcp.servers.composio_proxy.proxy import ComposioProxyTool, ComposioToolBlueprint
from pydantic import Field

from nexus_worker.simulation.registry import SimulatedRegistry
from nexus_worker.simulation.world import World

pytestmark = pytest.mark.asyncio


class _In(InputModel):
    pass


class _Out(OutputModel):
    rows: list[str] = Field(default_factory=list)


class _Recorded(ToolBase):
    """Una herramienta que solo lee y anota si alguien la ejecutó."""

    description: ClassVar[str] = "lee"
    input_model: ClassVar[type[InputModel]] = _In
    output_model: ClassVar[type[OutputModel]] = _Out
    side_effects: ClassVar[tuple[str, ...]] = ()

    def __init__(self, name: str) -> None:
        self.name = name  # type: ignore[misc]
        self.runs = 0

    async def run(self, payload: InputModel) -> OutputModel:
        self.runs += 1
        return _Out(rows=["Lucía Pérez, martes 10:00"])


class _Composio(ComposioProxyTool):
    """Un proxy de Composio que falla si alguien llega al proveedor."""

    calls = 0

    async def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        type(self).calls += 1
        raise AssertionError("the playground reached Composio")


def _world() -> World:
    return World(timezone="Europe/Madrid", now="2026-10-29T09:00:00+00:00", week=None)


def _registry(*tools: ToolBase, connector_tools: dict[str, bool]) -> SimulatedRegistry:
    base = MCPRegistry()
    for tool in tools:
        base._tools[tool.name] = tool
    return SimulatedRegistry(_world(), base=base, connector_tools=connector_tools)


async def test_a_connector_read_is_not_run_and_says_what_it_would_have_read() -> None:
    shop = _Recorded("shop.list_orders")
    registry = _registry(shop, connector_tools={"shop.list_orders": True})
    with tenant_context(uuid.uuid4()):
        envelope = await registry.dispatch("shop.list_orders", {}, whitelist=["shop.list_orders"])

    assert shop.runs == 0, "a connector read never runs in the playground"
    assert envelope["status"] == "ok"
    assert envelope["result"]["simulated"] is True
    assert envelope["result"]["data"] == {}
    assert "Lucía" not in str(envelope)
    assert [(a.tool, a.phrase) for a in registry.world.actions] == [
        ("shop.list_orders", "Consultar shop.list_orders (simulado, sin datos reales)")
    ]


async def test_a_composio_read_never_reaches_the_provider() -> None:
    blueprint = ComposioToolBlueprint(
        tool_name="googlecalendar.list_events",
        description="",
        input_schema={},
        toolkit_slug="googlecalendar",
        connection_id="conn",
        user_id="user",
    )
    proxy = _Composio(blueprint)
    _Composio.calls = 0
    # Ni siquiera hace falta que el catálogo lo diga: un proxy de Composio es
    # siempre de un sistema del negocio.
    registry = _registry(proxy, connector_tools={})
    with tenant_context(uuid.uuid4()):
        envelope = await registry.dispatch(
            "googlecalendar.list_events", {"day": "2026-10-30"}, whitelist=[proxy.name]
        )

    assert _Composio.calls == 0
    assert envelope["status"] == "ok" and envelope["result"]["simulated"] is True


async def test_a_connector_write_is_noted_and_not_run() -> None:
    order = _Recorded("shop.create_order")
    registry = _registry(order, connector_tools={"shop.create_order": False})
    with tenant_context(uuid.uuid4()):
        envelope = await registry.dispatch(
            "shop.create_order", {"qty": 2}, whitelist=["shop.create_order"]
        )

    assert order.runs == 0
    assert envelope["result"]["simulated"] is True
    assert [a.phrase for a in registry.world.actions] == ["Usar shop.create_order"]


async def test_an_internal_read_of_the_business_still_runs() -> None:
    """La ficha y los servicios son datos del propio negocio, no de sus clientes."""
    services = _Recorded("business.services")
    registry = _registry(services, connector_tools={"shop.list_orders": True})
    with tenant_context(uuid.uuid4()):
        envelope = await registry.dispatch("business.services", {}, whitelist=["business.services"])

    assert services.runs == 1
    assert envelope["status"] == "ok"
    assert registry.world.actions == []


async def test_asking_the_owner_is_noted_instead_of_asked() -> None:
    """«Preguntar antes de escribir» en el playground: se cuenta lo que habría
    hecho y la prueba sigue como si el dueño hubiera dicho que sí."""
    registry = _registry(connector_tools={})
    registry.note_simulated_approval("shop.create_order", {"qty": 2})
    assert [(a.tool, a.phrase) for a in registry.world.actions] == [
        ("shop.create_order", "Preguntar al dueño antes de usar shop.create_order")
    ]


async def test_a_turn_view_keeps_the_simulated_world() -> None:
    """La vista por turno que añade los proxies de Composio no puede volver a ser
    un registro de verdad: perdería la agenda simulada y estas reglas."""
    registry = _registry(connector_tools={"shop.list_orders": True})
    view = registry.view()
    assert isinstance(view, SimulatedRegistry)
    assert view is not registry and view.world is registry.world
    assert view.dry_run is True
    view._tools["extra.tool"] = _Recorded("extra.tool")
    assert "extra.tool" not in registry.names(), "the view never touches the shared registry"


async def test_the_agenda_answers_not_active_without_the_reservas_module() -> None:
    """Spec 047, enmienda del 2026-10-29 (D67): como en el turno de verdad, con
    Reservas apagado para el cliente la agenda simulada no reserva; responde lo
    mismo que el servidor de Reservas («no está activo») y no anota nada."""
    from nexus_mcp import ToolError
    from nexus_mcp.servers.reservas.tools import NOT_ACTIVE

    off = SimulatedRegistry(_world(), base=MCPRegistry(), connector_tools={}, reservas_on=False)
    with tenant_context(uuid.uuid4()), pytest.raises(ToolError, match=NOT_ACTIVE):
        await off.dispatch(
            "reservas.find_slots", {"date": "2026-10-30"}, whitelist=["reservas.find_slots"]
        )
    assert off.world.actions == []

    on = SimulatedRegistry(_world(), base=MCPRegistry(), connector_tools={})
    with tenant_context(uuid.uuid4()):
        envelope = await on.dispatch(
            "reservas.find_slots", {"date": "2026-10-30"}, whitelist=["reservas.find_slots"]
        )
    assert envelope["status"] == "ok"
