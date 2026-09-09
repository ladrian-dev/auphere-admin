"""El catálogo de la sesión — Requisitos 5, 13 y 14.

Es el corazón de la US4 y lo que T001 dejó verificado a nivel de proceso: aquí se
comprueba la regla, no el envoltorio. Tres familias:

* **Exhaustivo** (R5): lo que sale es exactamente lo que la fuente declara. Nada del
  ambiente de la máquina entra, y si no se puede garantizar, la sesión no abre.
* **Inalcanzable** (R13): las capacidades que el sustrato trae y no usamos no están, y
  tampoco se pueden pedir.
* **Alcance de red** (R14): con dispositivo presente no conviven herramientas que
  alcanzan la web y la ejecución local; lo no declarado cuenta como que alcanza.
"""

from __future__ import annotations

import pytest

from auphere_edition.catalog import (
    CatalogUnavailable,
    DISABLED_CAPABILITIES,
    LOCAL_EXECUTION_TOOL,
    Tool,
    resolve_catalog,
)


def source(*tools: Tool):
    return lambda: list(tools)


def names(tools) -> set[str]:
    return {t.name for t in tools}


# ── R5: exhaustivo ─────────────────────────────────────────────────────


def test_the_catalog_is_exactly_what_the_source_declares():
    declared = (Tool("console.clients.list"), Tool("console.usage.read"))
    assert names(resolve_catalog(source(*declared), device_present=False)) == {
        "console.clients.list",
        "console.usage.read",
    }


def test_an_unavailable_source_refuses_the_session():
    """R5.3 — fail-closed. Una sesión que no puede demostrar su catálogo no abre."""

    def broken():
        raise TimeoutError("la API no contesta")

    with pytest.raises(CatalogUnavailable):
        resolve_catalog(broken, device_present=False)


def test_an_empty_source_is_not_the_same_as_a_broken_one():
    """Cero herramientas es una respuesta legítima; no poder preguntar, no."""
    assert resolve_catalog(source(), device_present=False) == []


# ── R13: inalcanzable ──────────────────────────────────────────────────


@pytest.mark.parametrize("capability", sorted(DISABLED_CAPABILITIES))
def test_disabled_capabilities_never_reach_the_catalog(capability: str):
    """R13.1 — no basta con no listarlas: si la fuente las trae, se caen igual."""
    resolved = resolve_catalog(
        source(Tool(capability), Tool("console.clients.list")), device_present=False
    )
    assert capability not in names(resolved)
    assert "console.clients.list" in names(resolved)


# ── R14: alcance de red ────────────────────────────────────────────────


def test_network_tools_are_dropped_when_a_device_is_present():
    """R14.3 y R14.4 — gana la ejecución local, que es el valor de esta beta."""
    resolved = resolve_catalog(
        source(
            Tool("connector.web.fetch", reaches_network=True),
            Tool(LOCAL_EXECUTION_TOOL),
            Tool("console.clients.list", reaches_network=False),
        ),
        device_present=True,
    )
    assert names(resolved) == {LOCAL_EXECUTION_TOOL, "console.clients.list"}


def test_network_tools_survive_when_no_device_is_present():
    """Sin dispositivo no hay combinación peligrosa que evitar."""
    resolved = resolve_catalog(
        source(Tool("connector.web.fetch", reaches_network=True)), device_present=False
    )
    assert names(resolved) == {"connector.web.fetch"}


def test_an_undeclared_reach_counts_as_network():
    """R14.2 — si no declarar bastara para evadir la regla, la regla no existiría."""
    resolved = resolve_catalog(
        source(Tool("connector.misterioso", reaches_network=None), Tool(LOCAL_EXECUTION_TOOL)),
        device_present=True,
    )
    assert names(resolved) == {LOCAL_EXECUTION_TOOL}


def test_local_execution_is_never_the_one_dropped():
    """Si se cayera la ejecución local, la beta 2 no entregaría su diferencial."""
    resolved = resolve_catalog(
        source(Tool("a", reaches_network=True), Tool(LOCAL_EXECUTION_TOOL)), device_present=True
    )
    assert LOCAL_EXECUTION_TOOL in names(resolved)


# ── R14.4: la exclusión se dice, no se hace en silencio ────────────────


def test_the_exclusion_can_be_explained_to_the_partner():
    """Una ausencia sin explicación es una pantalla que miente por omisión (§V).

    El partner tiene que poder saber por qué le falta una herramienta que sí tiene
    contratada — si no, la conclusión razonable es que el producto está roto.
    """
    from auphere_edition.catalog import excluded_for_network_reach

    src = source(
        Tool("connector.web.fetch", reaches_network=True),
        Tool("connector.misterioso", reaches_network=None),
        Tool(LOCAL_EXECUTION_TOOL),
        Tool("console.clients.list", reaches_network=False),
    )
    assert excluded_for_network_reach(src, device_present=True) == [
        "connector.web.fetch",
        "connector.misterioso",
    ]


def test_nothing_is_excluded_without_a_device():
    from auphere_edition.catalog import excluded_for_network_reach

    src = source(Tool("connector.web.fetch", reaches_network=True))
    assert excluded_for_network_reach(src, device_present=False) == []
