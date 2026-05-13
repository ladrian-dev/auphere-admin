"""Transport resolver for ``agendapro_public.*`` internal tools.

Mirrors the pre-0021 ``agendapro_browser`` transport pattern: the
worker startup configures a real ``SubprocessPool`` from env vars,
tests substitute a ``FakeAgendaProPublicTransport``. Indirect on
purpose so the tools module never imports the real Node binary at
import time.

Unlike the admin browser pool (which kept a persistent Browserbase
Context per tenant), the public-link MCP runs in fully stateless mode:
each tool call opens a fresh Browserbase Stealth session. The pool
here exists only to amortise the Node process spawn cost (~250ms) and
the MCP handshake (~500ms) across the bursty async booking cron
ticks. Processes are killed after ``idle_timeout_s`` of inactivity.
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
    """Inject the transport used by the dynamically-built tool classes.

    Worker startup calls this with the real ``SubprocessPool`` once the
    Browserbase env vars are confirmed present; tests pass a
    ``FakeAgendaProPublicTransport``.
    """
    global _default_transport
    _default_transport = transport
    if transport is not None:
        log.info("agendapro_public.transport_set", server=transport.server_name)


def get_default_transport() -> SubprocessTransport:
    if _default_transport is None:
        raise RuntimeError(
            "agendapro_public transport not configured. Either the worker did "
            "not run set_default_transport() at startup, or a test forgot to "
            "inject a FakeAgendaProPublicTransport."
        )
    return _default_transport


def build_default_pool_from_env() -> SubprocessPool:
    """Build the production pool from environment variables.

    Required:
      NEXUS_AGENDAPRO_PUBLIC_NODE_CMD  — full command for the Node bin
        (default: ``node apps/mcp/servers/agendapro_public_mcp/dist/server.js``).
      BROWSERBASE_API_KEY              — forwarded to the Node process.
      BROWSERBASE_PROJECT_ID           — forwarded to the Node process.

    Optional:
      NEXUS_AGENDAPRO_PUBLIC_NODE_CWD  — process cwd.
      NEXUS_AGENDAPRO_PUBLIC_IDLE_S    — idle timeout (default 600s).
    """
    cmd = os.environ.get(
        "NEXUS_AGENDAPRO_PUBLIC_NODE_CMD",
        "node apps/mcp/servers/agendapro_public_mcp/dist/server.js",
    ).split()
    cwd = os.environ.get("NEXUS_AGENDAPRO_PUBLIC_NODE_CWD")
    idle_s = float(os.environ.get("NEXUS_AGENDAPRO_PUBLIC_IDLE_S", "600"))
    # Forward only the Browserbase + log envs the Node side needs; do NOT
    # forward NEXUS_* or AWS_* so the subprocess can't ambient-pickup
    # operator credentials it shouldn't see.
    env = {
        k: v
        for k, v in os.environ.items()
        if k.startswith("BROWSERBASE_") or k in {"LOG_LEVEL", "NODE_OPTIONS"}
    }
    factory = StdioMCPClientFactory(
        command=cmd,
        cwd=cwd,
        env=env,
        server_name="agendapro_public_mcp",
    )
    return SubprocessPool(factory, idle_timeout_s=idle_s)
