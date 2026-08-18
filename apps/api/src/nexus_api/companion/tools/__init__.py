"""Catálogo de herramientas del Companion (CO-02).

**La regla que define este paquete**: las herramientas llaman a los routers
``/console/*`` por HTTP en proceso (``httpx`` sobre ``ASGITransport``).
Nunca a ``services/`` ni a ``repositories/``, aunque sea más rápido.

Saltarse el router se salta la validación Pydantic, ``client_scope`` (que
es donde el ``external_client_ref`` se resuelve bajo el principal y donde
se abre la transacción con RLS), el limitador de ráfaga, la cuota de
aprovisionamiento, el vocabulario de auditoría y la cobertura automática de
``tests/isolation/test_console_scope.py``. En seis meses el Companion sería
un camino paralelo con sus propios agujeros. El coste es ~1 ms por llamada.

La invariante es un test bloqueante:
``tests/isolation/test_companion_tools_imports.py``.

En CO-02 **todas las herramientas son de lectura**. Las de propuesta y las
de ejecución llegan en CO-04, y llegan por la única puerta
``console.apply`` — ver ``ADR-033``.
"""

from __future__ import annotations

from nexus_api.companion.tools.catalog import READ_TOOLS, ToolParam, ToolSpec, tool_specs
from nexus_api.companion.tools.errors import ToolError, translate_status
from nexus_api.companion.tools.runner import CompanionToolbelt, ToolOutcome

__all__ = [
    "READ_TOOLS",
    "CompanionToolbelt",
    "ToolError",
    "ToolOutcome",
    "ToolParam",
    "ToolSpec",
    "tool_specs",
    "translate_status",
]
