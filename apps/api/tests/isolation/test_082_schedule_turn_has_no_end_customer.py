"""Garantía 8 en un turno de rutina — spec 082, T013 (requisitos 4.3 y 4.4).

Una rutina no tiene conversación y no tiene cliente final. Eso no es una
promesa del código que la escribe: se comprueba barriendo **el registro
entero** de herramientas, no una lista.

Dos reglas, y las dos salen del esquema de cada herramienta, no de un criterio
nuestro:

1. **La que exige ``conversation_id``** no se puede ofrecer: en el canal la
   pone el servidor con la conversación del turno, y en una rutina no hay
   ninguna. Son, hoy, justo las que hablan con un cliente final.
2. **La que deja al modelo elegir a una persona** (``end_customer_picks``, el
   inventario cerrado de la garantía 8) tampoco. En el canal el servidor ata la
   herramienta al cliente final del turno. Aquí no hay a quién atarla.

Una herramienta nueva con cualquiera de las dos formas pone esto en rojo antes
de llegar a producción, que es exactamente para lo que está.

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import pytest
from nexus_mcp import build_default_registry
from nexus_worker.runtime.schedule_turn import select_tools

from nexus_api.services.activations import ToolPolicy
from nexus_api.services.agent_spec.validator import end_customer_picks


@pytest.fixture(scope="module")
def registry():
    return build_default_registry()


def _everything(registry) -> tuple[str, ...]:
    """El techo más ancho imaginable: un agente con TODAS las herramientas."""
    return tuple(registry.names())


def _args(registry, name: str) -> frozenset[str]:
    defs = registry.get_tool_definitions((name,))
    return frozenset((defs[0].parameters.get("properties") or {}) if defs else {})


def test_no_offered_tool_needs_a_conversation(registry) -> None:
    chosen = select_tools(registry, _everything(registry), ToolPolicy())
    for name in chosen.names:
        defs = registry.get_tool_definitions((name,))
        required = (defs[0].parameters.get("required") or []) if defs else []
        assert "conversation_id" not in required, name


def test_no_offered_tool_lets_the_model_pick_a_person(registry) -> None:
    chosen = select_tools(registry, _everything(registry), ToolPolicy())
    offenders = {
        name: end_customer_picks(name, _args(registry, name))
        for name in chosen.names
        if end_customer_picks(name, _args(registry, name))
    }
    assert offenders == {}


def test_everything_left_out_says_why(registry) -> None:
    chosen = select_tools(registry, _everything(registry), ToolPolicy())
    assert chosen.withheld, "con el registro entero algo tiene que quedarse fuera"
    for item in chosen.withheld:
        assert item.why in {
            "needs_a_conversation",
            "picks_an_end_customer",
            "needs_approval",
            "not_activated",
        }
    # Nada se pierde por el camino: lo ofrecido más lo retenido es el techo.
    assert len(chosen.names) + len(chosen.withheld) == len(_everything(registry))


def test_the_ones_that_talk_to_a_customer_are_named(registry) -> None:
    """Las de hoy, por su nombre. Si alguna dejara de estar en el registro, este
    caso se cae y hay que mirar por qué, en vez de seguir con una lista que ya
    no dice nada."""
    chosen = select_tools(registry, _everything(registry), ToolPolicy())
    out = {item.tool for item in chosen.withheld}
    for name in ("escalate.escalate_to_human", "notification.send_text"):
        if name in registry.names():
            assert name in out, name


def test_the_ceiling_is_the_agents_list_never_more(registry) -> None:
    """Garantía 2: la lista del turno es una intersección, nunca una suma. Un
    agente con dos herramientas no recibe una tercera por ser una rutina."""
    two = ("inventory.check_stock", "inventory.low_stock")
    present = tuple(n for n in two if n in registry.names())
    chosen = select_tools(registry, present, ToolPolicy())
    assert set(chosen.names) <= set(present)
