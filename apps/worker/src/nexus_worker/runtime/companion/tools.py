"""El contrato de herramientas visto desde el grafo (CO-02).

El grafo **no sabe** que detrás hay HTTP. Solo pide el catálogo y ejecuta
nombres. La implementación real vive en ``nexus_api.companion.tools``,
donde llama a los routers ``/console/*`` por ASGI en proceso; los tests
pasan un doble.

Esa asimetría es deliberada: el runtime no conoce la CAPA HTTP de la API y
conviene que siga siendo así — el worker ejecuta los agentes de cliente y no
tiene por qué saber de la superficie de la consola.

(Ojo: ``apps/worker`` **sí** depende de ``nexus_api`` —es su primera
dependencia declarada en ``pyproject.toml``, y ``bootstrap.py`` importa de
ella—. La regla que existe y se aplica es más estrecha: el paquete de
herramientas no importa ``services`` ni ``repositories``, con test de AST en
``test_companion_tools_imports.py``.)
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolResult(Protocol):
    """Lo que devuelve una llamada. Coincide con
    ``nexus_api.companion.tools.ToolOutcome``."""

    name: str
    #: Etiqueta humana ("Consumo del partner"), no el nombre técnico.
    label: str
    ok: bool
    #: Lo que se le devuelve al modelo como resultado.
    content: str
    latency_ms: int
    error_code: str | None
    #: ``None`` si la llamada falló. Con ``as_payload()``.
    citation: Any


@runtime_checkable
class Toolbelt(Protocol):
    """El juego de herramientas de un turno."""

    #: Llamadas que quedan antes del tope duro.
    calls_left: int
    #: Lecturas con éxito hasta ahora. Es el numerador de la regla R1.
    reads_done: int

    def specs(self) -> list[dict[str, Any]]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


@runtime_checkable
class ActionPort(Protocol):
    """El camino de escritura, visto desde el grafo (CO-04).

    El grafo **no sabe** que detrás hay HTTP ni Postgres: pide poner una
    acción en espera, aplicarla y verificarla. Lo implementa
    ``nexus_api.companion.tools.CompanionToolbelt``; los tests pasan un
    doble.

    La asimetría es la misma que la de :class:`Toolbelt` y por la misma
    razón: el runtime no conoce la capa HTTP de la API, y el
    worker es el runtime de los agentes de cliente — no tiene por qué
    conocer la superficie HTTP de la consola.
    """

    #: Propuestas calculadas en este turno y todavía sin persistir.
    pending: list[Any]
    #: Lo que falta para poder proponer (§7.1). El grafo lo emite como
    #: ``intake.missing`` y el turno termina preguntando.
    missing_slots: list[dict[str, Any]]

    def plan_steps(self) -> list[dict[str, Any]]: ...

    def plan_risk(self) -> str: ...

    async def stage(self, step_index: int) -> dict[str, Any] | None: ...

    async def apply_confirmed(self, action_id: Any) -> ToolResult: ...

    async def verify(self, action_id: Any) -> dict[str, Any] | None: ...


# ── el nombre de cable (§17 del contrato v2.1) ─────────────────────────
#
# Anthropic rechaza el punto en ``tools[].name``:
#
#     tools.0.custom.name: String should match pattern '^[a-zA-Z0-9_-]{1,128}$'
#
# Las 28 herramientas del catálogo se llaman con punto (``console.get_usage``),
# así que **ningún turno que ofreciera herramientas funcionó nunca contra el
# proveedor real**; un proveedor guionizado acepta cualquier nombre y por eso
# ninguna suite lo vio.
#
# El catálogo **no se renombra**: el nombre con punto ya es contrato en los
# eventos que pinta la interfaz, en la línea de i18n de la consola, en el
# dataset de evals, en las claves de ``APPLY_ROUTES`` y en el ``kind`` de cada
# ``propose_*``. La restricción es del transporte y se resuelve en el
# transporte.

#: Punto → doble guion bajo. Biyectivo por construcción: ningún nombre del
#: catálogo contiene ``__`` (son ``console.`` más snake_case con guiones bajos
#: simples), y :func:`wire_tools` lo comprueba al construir la tabla.
WIRE_SEPARATOR = "__"

#: Lo que el proveedor admite. Se comprueba, no se supone.
WIRE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class WireNameCollision(RuntimeError):
    """Dos herramientas del catálogo caerían en el mismo nombre de cable.

    Rompe **al construir la tabla**, que es al arrancar el turno, y no en
    producción con un 400 del proveedor o —peor— con una llamada
    despachada a la herramienta equivocada.
    """


def to_wire(name: str) -> str:
    """Nombre de catálogo → nombre de cable."""
    return name.replace(".", WIRE_SEPARATOR)


def wire_tools(specs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """El catálogo listo para el proveedor, y cómo deshacer la traducción.

    Devuelve ``(specs, catálogo_por_nombre_de_cable)``. La tabla de vuelta se
    construye **desde el catálogo** —no se recalcula invirtiendo la cadena—
    para que la vuelta atrás sea exacta aunque un nombre futuro traiga algo
    raro.
    """
    translated: list[dict[str, Any]] = []
    back: dict[str, str] = {}
    for spec in specs:
        function = spec.get("function")
        if not isinstance(function, dict):  # pragma: no cover - defensivo
            translated.append(spec)
            continue
        name = str(function.get("name") or "")
        wire = to_wire(name)
        if not WIRE_NAME_PATTERN.match(wire):
            raise WireNameCollision(
                f"el nombre de cable de {name!r} sigue sin ser válido para el proveedor: {wire!r}"
            )
        if back.setdefault(wire, name) != name:
            raise WireNameCollision(
                f"{name!r} y {back[wire]!r} caen en el mismo nombre de cable {wire!r}"
            )
        translated.append({**spec, "function": {**function, "name": wire}})
    return translated, back


def supports_actions(toolbelt: Any) -> bool:
    """¿Este juego de herramientas sabe escribir?

    Se comprueba por capacidad y no por tipo: en CO-01 y CO-02 el grafo se
    compila con juegos que solo leen, y esos tienen que seguir funcionando
    exactamente igual — sin nodos de HITL y sin un ``interrupt()`` que
    nadie va a reanudar.
    """
    return all(
        hasattr(toolbelt, attr) for attr in ("pending", "stage", "apply_confirmed", "verify")
    )


__all__ = [
    "WIRE_NAME_PATTERN",
    "WIRE_SEPARATOR",
    "ActionPort",
    "ToolResult",
    "Toolbelt",
    "WireNameCollision",
    "supports_actions",
    "to_wire",
    "wire_tools",
]
