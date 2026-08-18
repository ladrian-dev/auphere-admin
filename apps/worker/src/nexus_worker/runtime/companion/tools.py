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


__all__ = ["ToolResult", "Toolbelt"]
