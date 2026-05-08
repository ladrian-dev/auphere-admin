"""Resolution del transport para las internal tools agendapro.*.

El ``SubprocessPool`` real se construye al startup del worker (o del
admin endpoint que invoca bootstrap) leyendo el comando del env var
``NEXUS_AGENDAPRO_NODE_CMD``. Tests inyectan un ``FakeAgendaProTransport``
vía ``set_default_transport``.

Esto evita que las tools resuelvan el transport al import-time (lo cual
forzaría a tener el server Node disponible en cualquier entorno que
importe ``nexus_mcp.servers.agendapro_browser.tools``).
"""

from __future__ import annotations

import os

import structlog

from nexus_mcp.subprocess_tool import SubprocessTransport
from nexus_mcp.transports import (
    StdioMCPClientFactory,
    SubprocessPool,
)

log = structlog.get_logger(__name__)

_default_transport: SubprocessTransport | None = None


def set_default_transport(transport: SubprocessTransport | None) -> None:
    """Sustituye el transport global. Usado por:
    - Worker startup (configura el SubprocessPool real).
    - Tests (inyecta FakeAgendaProTransport).
    Pasar ``None`` resetea — útil entre tests.
    """
    global _default_transport
    _default_transport = transport
    if transport is not None:
        log.info("agendapro.transport_set", server=transport.server_name)


def get_default_transport() -> SubprocessTransport:
    if _default_transport is None:
        raise RuntimeError(
            "AgendaPro transport not configured. Did you forget to call "
            "set_default_transport() at worker startup, or to inject a fake "
            "in tests?"
        )
    return _default_transport


def build_default_pool_from_env() -> SubprocessPool:
    """Helper opcional para arrancar el pool real desde env vars.

    Vars:
      NEXUS_AGENDAPRO_NODE_CMD  — comando completo (default:
        ``node apps/mcp/servers/agendapro_browser_mcp/dist/server.js``)
      NEXUS_AGENDAPRO_NODE_CWD  — cwd del proceso
      NEXUS_AGENDAPRO_IDLE_S    — idle timeout en segundos (default 1800)
    """
    cmd = os.environ.get(
        "NEXUS_AGENDAPRO_NODE_CMD",
        "node apps/mcp/servers/agendapro_browser_mcp/dist/server.js",
    ).split()
    cwd = os.environ.get("NEXUS_AGENDAPRO_NODE_CWD")
    idle_s = float(os.environ.get("NEXUS_AGENDAPRO_IDLE_S", "1800"))
    factory = StdioMCPClientFactory(
        command=cmd,
        cwd=cwd,
        env={},
        server_name="agendapro_browser_mcp",
    )
    return SubprocessPool(factory, idle_timeout_s=idle_s)
