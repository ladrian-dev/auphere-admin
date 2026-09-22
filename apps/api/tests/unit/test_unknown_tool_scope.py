"""Cuando el modelo se inventa una herramienta — spec 015, Requisito 2.6.

Pasa, y está documentado que pasa: hay un caso reproducible en la industria de
un modelo que alucinó acceso a una herramienta que no le habían dado, se inventó
los parámetros y **la llamó**, probado contra cuatro proveedores. Nexus ya lo
para en el motor (``not_in_catalog``), y eso **no se toca aquí**.

Lo que sí se arregla es qué se le enseña al fallar. Se le enumeraban **las 44
del catálogo de la plataforma**: fuga de superficie, y una invitación a
reintentar con otra que tampoco tiene.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _mensaje(runner_cls, allowed: frozenset[str] | None) -> str:
    import asyncio

    runner = runner_cls.__new__(runner_cls)
    runner.allowed_tools = allowed
    runner.calls_made = 0
    runner.max_calls = 10
    runner.mode = "build"
    runner.citations = []

    captured: dict[str, object] = {}

    def _failed(name, label, error, started):
        captured["error"] = error
        return None

    runner._failed = _failed  # type: ignore[method-assign]
    asyncio.run(runner.call("console.inventada", {}))
    return str(captured["error"].message)  # type: ignore[attr-defined]


def test_it_lists_only_the_tools_this_teammate_has() -> None:
    from nexus_api.companion.tools.runner import CompanionToolbelt

    mias = frozenset({"console.whoami", "console.list_clients"})
    mensaje = _mensaje(CompanionToolbelt, mias)

    assert "console.whoami" in mensaje
    assert "console.list_clients" in mensaje
    assert "console.propose_publish" not in mensaje, (
        "le está enseñando herramientas que este teammate no tiene"
    )


def test_it_never_leaks_the_whole_platform_catalogue() -> None:
    from nexus_api.companion.tools.catalog import ALL_TOOLS
    from nexus_api.companion.tools.runner import CompanionToolbelt

    mias = frozenset({"console.whoami"})
    mensaje = _mensaje(CompanionToolbelt, mias)
    ajenas = [t.name for t in ALL_TOOLS if t.name not in mias]

    coladas = [n for n in ajenas if n in mensaje]
    assert not coladas, f"se colaron {len(coladas)} herramientas ajenas: {coladas[:5]}"


def test_with_no_tools_it_says_so_instead_of_an_empty_list() -> None:
    """Publicar-en-consulta entrega cero. Una lista vacía no explica nada."""
    from nexus_api.companion.tools.runner import CompanionToolbelt

    mensaje = _mensaje(CompanionToolbelt, frozenset())

    assert "No tienes ninguna herramienta" in mensaje
    assert "Las que tienes son:" not in mensaje
