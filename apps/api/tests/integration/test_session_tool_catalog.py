"""El documento del catálogo de sesión — Requisitos 5.1 y 14.1.

Es la otra mitad de T025: la edición ya lo consume y lo prueba contra un abridor
falso; esto es quien lo sirve.

La decisión que gobierna el endpoint: **solo declara `reaches_network: false` de
lo que puede avalar**. Las herramientas `console.*` llaman a nuestra propia API,
no leen contenido externo, y eso se sabe. De cualquier otra cosa se calla — y
callarse significa «alcanza la red», porque así lo define el Requisito 14.2. Un
`false` por defecto convertiría el desconocimiento en permiso.
"""

from __future__ import annotations

from nexus_api.services.session_tool_catalog import (
    build_session_catalog,
    declared_reach,
)


def test_console_tools_are_vouched_for_as_not_reaching_the_web():
    assert declared_reach("console.clients.list") is False
    assert declared_reach("console.usage.read") is False


def test_anything_we_cannot_vouch_for_stays_undeclared():
    """No declarado ≠ inocuo. La edición lo tratará como que alcanza la red."""
    assert declared_reach("connector.web.fetch") is None
    assert declared_reach("mcp__tercero__lo_que_sea") is None
    assert declared_reach("") is None


def test_the_document_has_the_shape_the_edition_expects():
    doc = build_session_catalog()
    assert set(doc) == {"tools"}
    assert isinstance(doc["tools"], list)
    for entry in doc["tools"]:
        assert set(entry) <= {"name", "reaches_network"}
        assert entry["name"]


def test_every_entry_comes_from_the_declarative_catalog():
    """El catálogo del teammate es código de Auphere, no un campo editable."""
    from nexus_api.companion.tools.catalog import ALL_TOOLS

    declared = {spec.name for spec in ALL_TOOLS}
    served = {entry["name"] for entry in build_session_catalog()["tools"]}
    assert served <= declared
    assert served, "servir un catálogo vacío diría «no tienes nada», que es otra cosa"


def test_no_entry_omits_its_name():
    """Una entrada sin nombre invalida el documento entero del lado del consumidor."""
    assert all(entry.get("name") for entry in build_session_catalog()["tools"])
