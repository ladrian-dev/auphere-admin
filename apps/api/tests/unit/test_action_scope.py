"""Requisito 7.1 y 7.2 — dónde vive cada acción, y quién la aprueba.

La frontera es la que §IV dibuja: lo que se queda **dentro de la máquina** del
partner lo resuelve la escalera local; todo lo que **toca a un cliente final**
pasa por la aprobación durable de la plataforma, con la persona nombrada.

Lo que hace segura a esta clasificación no es la lista, es el defecto: **lo que
no se reconoce cae del lado durable**. Una lista de «esto es peligroso» olvida;
una de «esto es inocuo» falla hacia el lado caro pero correcto.
"""

from __future__ import annotations

import pytest

from nexus_api.services.action_scope import (
    MACHINE_SCOPED_TOOLS,
    ActionScope,
    classify_tool,
    requires_durable_approval,
)


@pytest.mark.parametrize("tool", sorted(MACHINE_SCOPED_TOOLS))
def test_machine_scoped_tools_use_the_local_ladder(tool: str) -> None:
    assert classify_tool(tool) is ActionScope.MACHINE
    assert requires_durable_approval(tool) is False


@pytest.mark.parametrize(
    "tool",
    [
        "console.clients.archive",
        "console.channels.rotate_key",
        "console.agent.publish",
        "connector.whatsapp.send",
    ],
)
def test_anything_touching_an_end_client_needs_the_durable_ladder(tool: str) -> None:
    assert classify_tool(tool) is ActionScope.END_CLIENT
    assert requires_durable_approval(tool) is True


@pytest.mark.parametrize("tool", ["", "herramienta.que.nadie.ha.visto", "shell", "shell_remote"])
def test_the_unknown_falls_on_the_durable_side(tool: str) -> None:
    """El defecto es el que decide si esto es seguro dentro de un año."""
    assert classify_tool(tool) is ActionScope.END_CLIENT


def test_the_machine_list_is_small_on_purpose():
    """Si esta lista crece, alguien está moviendo la frontera sin decirlo."""
    assert len(MACHINE_SCOPED_TOOLS) <= 3
    assert "shell_local" in MACHINE_SCOPED_TOOLS
