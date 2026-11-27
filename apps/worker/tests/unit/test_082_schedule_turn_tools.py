"""Garantía 2 en un turno de rutina — spec 082, T014 (requisitos 4.2, 4.5, 5.1
y 5.2).

La lista de herramientas de una rutina sale de la misma intersección de
siempre: el techo del agente, acotado por lo que deja la activación de cada
conexión. Nunca una suma.

Y aquí vive **la salida barata**, que es provisional y tiene que notarse: una
conexión puesta en «preguntar antes de escribir» no puede preguntar desde la
consola todavía, así que sus escrituras se quedan fuera y la ejecución lo
escribe. Cuando llegue esa pregunta, este fichero cambia.
"""

from __future__ import annotations

from typing import Any

import pytest
from nexus_api.services.activations import ToolPolicy

from nexus_worker.runtime.schedule_turn import select_tools


class _Def:
    def __init__(self, required: list[str] | None = None, props: dict[str, Any] | None = None):
        self.parameters = {"properties": props or {}, "required": required or []}


class _Registry:
    """Lo justo del registro que mira la selección: nombres y esquemas."""

    def __init__(self, tools: dict[str, _Def]) -> None:
        self._tools = tools

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def get_tool_definitions(self, whitelist):
        return [self._tools[n] for n in sorted(set(whitelist) & set(self._tools))]


@pytest.fixture
def registry() -> _Registry:
    return _Registry(
        {
            "inventory.check_stock": _Def(),
            "inventory.mark_out_of_stock": _Def(props={"sku": {}}),
            "notion.read_view": _Def(props={"view": {}}),
            "escalate.escalate_to_human": _Def(required=["conversation_id"]),
        }
    )


def _names(chosen) -> set[str]:
    return set(chosen.names)


def _why(chosen, tool: str) -> str | None:
    return next((w.why for w in chosen.withheld if w.tool == tool), None)


def test_the_list_is_an_intersection_never_a_sum(registry) -> None:
    chosen = select_tools(registry, ("inventory.check_stock",), ToolPolicy())
    assert _names(chosen) == {"inventory.check_stock"}


def test_read_and_write_lets_it_write(registry) -> None:
    chosen = select_tools(registry, registry.names(), ToolPolicy())
    assert "inventory.mark_out_of_stock" in _names(chosen)


def test_read_only_leaves_the_writes_out(registry) -> None:
    """«Solo leer» ya llega resuelto en ``blocked``: la rutina hereda, no decide."""
    policy = ToolPolicy(blocked=frozenset({"inventory.mark_out_of_stock"}))
    chosen = select_tools(registry, registry.names(), policy)
    assert "inventory.mark_out_of_stock" not in _names(chosen)
    assert _why(chosen, "inventory.mark_out_of_stock") == "not_activated"


def test_ask_before_writing_is_withheld_and_said(registry) -> None:
    """La salida barata (criterio 5.1), con fecha de caducidad."""
    policy = ToolPolicy(needs_approval=frozenset({"inventory.mark_out_of_stock"}))
    chosen = select_tools(registry, registry.names(), policy)
    assert "inventory.mark_out_of_stock" not in _names(chosen)
    assert _why(chosen, "inventory.mark_out_of_stock") == "needs_approval"
    # Y lo de leer de esa misma conexión sigue dentro.
    assert "inventory.check_stock" in _names(chosen)


def test_a_conversation_tool_never_makes_it(registry) -> None:
    chosen = select_tools(registry, registry.names(), ToolPolicy())
    assert "escalate.escalate_to_human" not in _names(chosen)
    assert _why(chosen, "escalate.escalate_to_human") == "needs_a_conversation"


def test_a_policy_that_could_not_be_read_closes(registry) -> None:
    """Falla cerrada, como el turno del canal: sin política, ninguna de conector."""
    chosen = select_tools(registry, registry.names(), ToolPolicy(closed=True))
    assert _why(chosen, "notion.read_view") == "not_activated"


def test_what_is_withheld_is_readable_by_a_person(registry) -> None:
    """``withheld`` acaba en el historial de la ejecución, así que cada entrada
    lleva la herramienta y el porqué, no un código suelto."""
    policy = ToolPolicy(needs_approval=frozenset({"inventory.mark_out_of_stock"}))
    chosen = select_tools(registry, registry.names(), policy)
    rows = [w.as_dict() for w in chosen.withheld]
    assert {"tool", "why"} <= set(rows[0])
