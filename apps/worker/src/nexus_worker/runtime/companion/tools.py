"""El contrato de herramientas visto desde el grafo (CO-02).

El grafo **no sabe** que detrás hay HTTP. Solo pide el catálogo y ejecuta
nombres. La implementación real vive en ``nexus_api.companion.tools``,
donde llama a los routers ``/console/*`` por ASGI en proceso; los tests
pasan un doble.

Esa asimetría es deliberada: ``apps/worker`` no importa ``nexus_api`` en
ninguna parte, y conviene que siga siendo así — el worker es el runtime de
los agentes de cliente y no tiene por qué conocer la superficie HTTP de la
consola.
"""

from __future__ import annotations

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
    razón: ``apps/worker`` no importa ``nexus_api`` en ninguna parte, y el
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


__all__ = ["ActionPort", "ToolResult", "Toolbelt", "supports_actions"]
