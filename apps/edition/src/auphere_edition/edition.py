"""El punto de extensión: compone la edición Auphere sobre el sustrato.

Requisito 5.1. Registrado en ``pyproject.toml`` bajo el grupo de entry points
``kirocrew.plugins``, que es la vía que el propio fabricante usa para su edición.

**No se hereda: se reemplaza.** ``PlatformContext`` es un dataclass inmutable, así
que la vía es ``dataclasses.replace`` sobre el contexto por defecto. No hay subclase,
no hay monkeypatch y no se toca un solo fichero del núcleo — verificado en el spike 2
de la evaluación y sostenido por ``scripts/verify-composition.py``.

Los proveedores de abajo están **deliberadamente vacíos**: llenarlos es trabajo de la
US4 (el servidor MCP de ``console.*``, tareas T019–T022). Existen ya para que la
composición sea comprobable desde la Phase 1, no para hacer nada todavía.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

EDITION_PROFILE = "enterprise"


#: El servidor MCP de la edición: las herramientas ``console.*`` por API.
#:
#: §VI — un agente opera la plataforma **llamando a herramientas, no navegando**. El
#: navegador de un agente es para lo que no tiene API; nunca para la consola de
#: Auphere, que además metería una sesión autenticada nuestra dentro del ambiente del
#: agente.
CONSOLE_MCP_SERVER = "auphere-console"


class AuphereMcpTooling:
    """Proveedor de herramientas de la edición.

    Declara **un** servidor: el de ``console.*``. Qué herramientas expone ese servidor
    en cada turno lo decide :mod:`auphere_edition.catalog`, que aplica las tres reglas
    —exhaustivo, fail-closed y alcance de red— sobre el catálogo declarativo de
    Auphere. Ninguna de las dos mitades vale sola: declarar el servidor sin las reglas
    dejaría el catálogo a merced de la fuente.
    """

    def __init__(self, command: str = "auphere-console-mcp", args: list[str] | None = None) -> None:
        self._command = command
        self._args = args or []

    def extra_mcp_servers(self) -> dict[str, Any]:
        return {
            CONSOLE_MCP_SERVER: {
                "command": self._command,
                "args": list(self._args),
                "env": {},
            }
        }

    def extra_skills(self) -> list[Any]:
        return []

    def extra_mcp_scopes(self) -> list[Any]:
        return []


class AuphereAgentCatalog:
    """Catálogo de agentes de la edición. Vacío hasta que la US4 lo defina."""

    def builtin_agents(self) -> list[dict[str, str]]:
        return []


def build_enterprise_context(cfg: Any) -> Any:
    """Compone el contexto de la edición sobre el que trae el sustrato.

    El núcleo llama a esto por el entry point cuando el perfil no es ``standalone``.
    """
    from kiro_crew.platform.bootstrap import build_default_context

    base = build_default_context(cfg, profile=EDITION_PROFILE)
    return replace(
        base,
        profile=EDITION_PROFILE,
        mcp_tooling=AuphereMcpTooling(),
        agent_catalog=AuphereAgentCatalog(),
    )
