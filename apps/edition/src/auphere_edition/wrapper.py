"""El envoltorio del harness — Requisitos 5.1 y 5.2. Es T001 hecho producto.

**Qué resuelve.** El backend hereda los servidores MCP del usuario que ejecuta el
gateway: el CLI lee el ``~/.claude.json`` de la máquina y **suma** los suyos a los que
Crew pasa. En la beta 2 esa máquina es la del partner, así que ese fichero es suyo y
puede contener cualquier cosa. Sin esto, el teammate acabaría con herramientas que
nadie puso en la lista blanca del tenant — que es lo que §I prohíbe con todas las
letras.

**Por qué funciona**, medido en T001 y no supuesto: el SDK serializa los
``mcpServers`` que Crew envía en ``session/new`` a ``--mcp-config`` (``sdk.mjs``), así
que ``--strict-mcp-config`` restringe **a** ese conjunto en vez de vaciarlo. Si fuera
al revés, el flag habría matado también las de Crew y la edición habría tenido que
intervenir el lanzamiento del harness — que es lo primero que obligaría a tocar el
núcleo.

**Resultado de T001**, para que nadie lo tenga que volver a medir: tres servidores
ajenos en el catálogo → cero, y cuatro procesos ajenos vivos bajo el gateway → cero,
conservando las 74 herramientas propias de Crew.

Anotado para cuando toque: el seam tiene un slot ``agent_executable``
(``AgentExecutableResolver``). Inyectar el envoltorio por ahí lo haría parte de la
edición en vez de una variable de entorno que alguien puede no poner. Sin explorar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

#: *«Only use MCP servers from --mcp-config, ignoring all other MCP configurations».*
STRICT_FLAG = "--strict-mcp-config"


def wrapper_argv(real_binary: str, argv: Sequence[str]) -> list[str]:
    """El ``argv`` con el que se invoca el binario real.

    El flag va delante y **una sola vez**: el SDK sabe empujarlo por su cuenta cuando
    se le pide, y duplicarlo no aporta nada salvo ruido en el log de diagnóstico.
    """
    rest = [a for a in argv if a != STRICT_FLAG]
    return [real_binary, STRICT_FLAG, *rest]


def render_wrapper_script(real_binary: str, *, wrapper_path: str | None = None) -> str:
    """El envoltorio, como script, para apuntar ``CLAUDE_CODE_EXECUTABLE`` a él."""
    if wrapper_path is not None and wrapper_path == real_binary:
        raise ValueError(
            "el envoltorio no puede apuntar a sí mismo: sería una recursión silenciosa"
        )
    return f"""#!/usr/bin/env bash
# Envoltorio de la edición Auphere. Ver auphere_edition/wrapper.py.
# Sin esto, el harness hereda los servidores MCP del ~/.claude.json del partner.
set -euo pipefail
exec {real_binary} {STRICT_FLAG} "$@"
"""


def foreign_servers(user_config: Any) -> list[str]:
    """Nombres de los servidores que la máquina declara, para **dejar constancia**.

    Requisito 5.2: no basta con no exponerlos; hay que poder decir qué se intentó
    colar. El fichero es del partner, así que aquí no se confía en su forma — una
    config con basura dentro no es motivo para romper una sesión.
    """
    if not isinstance(user_config, dict):
        return []
    servers = user_config.get("mcpServers")
    if not isinstance(servers, dict):
        return []
    return sorted(str(name) for name in servers)


__all__ = ["STRICT_FLAG", "foreign_servers", "render_wrapper_script", "wrapper_argv"]
