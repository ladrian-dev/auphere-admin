"""MCP registry — name → ``ToolBase`` instance, with whitelist + dispatch.

Block C had a simple ``tools/registry.py`` in the worker holding 21 stub
callables. Block D moves the surface here and gives it three concrete jobs:

1. Hold the active set of tool instances (loaded once, in-process).
2. Produce ``ToolDef``s filtered by the active tenant's whitelist so the
   pipeline can hand them to LiteLLM as the ``tools`` param.
3. Dispatch invocations: validate the name against the whitelist (defense
   in depth on top of pre-LLM filtering), enter ``tenant_context``, run
   the tool, count metrics, and return the envelope dict.

The dispatch surface ``async def dispatch(name, args, *, whitelist) -> ToolResult``
is the single integration point the worker depends on. If a server moves
out-of-process in the future, only the registry's internals change — the
caller surface stays.

Tenant context: the dispatch path expects ``require_current_tenant()`` to
already resolve, i.e. the caller (the LangGraph node) opened
``tenant_context`` for this tenant before invoking. The registry does not
re-set the contextvar — it only asserts it is present. This mirrors the
block-C stubs.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import structlog
from nexus_api.core.metrics import (
    ISOLATION_TOOL_WHITELIST_VIOLATION,
    record_isolation_event,
)
from nexus_api.core.tenant_context import require_current_tenant

from nexus_mcp.base import (
    ToolBase,
    ToolDef,
    ToolError,
    ToolNotInWhitelist,
    ToolResult,
    make_envelope,
)
from nexus_mcp.metrics import record_error, record_invocation, record_latency

log = structlog.get_logger(__name__)


# ── internal caller token ───────────────────────────────────────────────────
#
# Bloque E introduce ``MCPRegistry.dispatch_internal`` para que los servers
# Bloque D (en particular booking-server) puedan invocar tools internas
# (``agendapro.*``) sin que el LLM tenga forma de alcanzarlas. Tres capas
# defensivas, cualquiera de las cuales sería suficiente:
#
#   1. ESTRUCTURAL — las internal tools viven en ``_internal_tools``,
#      separado del ``_tools`` público. ``dispatch(name, ...)`` consulta solo
#      ``_tools``; aunque el LLM alucine ``agendapro.create_appointment``,
#      ``_tools.get(name)`` devuelve None.
#
#   2. CATÁLOGO — la migración 0008 + seed marca las 6 ``agendapro.*`` con
#      ``tool_status='internal'``. El endpoint admin que edita
#      ``agent_config.tools`` rechaza nombres con ese status.
#
#   3. SIGNING (cinturón y tirante) — ``dispatch_internal`` requiere
#      ``caller_token`` que es un secret in-memory generado al startup del
#      proceso. Lo conoce solo el código del paquete que se compila junto
#      con booking-server. El LLM nunca lo ve, así que aunque (hipotético)
#      lograra invocar la función Python, no puede pasar el token.
#
# El token rota por proceso (no se persiste). Si alguien lo loggea por
# accidente, queda en disco pero no es reutilizable a través de restarts.

_INTERNAL_CALLER_TOKEN: str = secrets.token_urlsafe(32)


def get_internal_caller_token() -> str:
    """Token in-memory que ``dispatch_internal`` exige.

    Lo importan los servers Bloque D que necesitan delegar a tools
    internas (booking → agendapro). Tests pueden importarlo igual.
    """
    return _INTERNAL_CALLER_TOKEN


class InternalCallerTokenInvalid(ToolError):
    """``dispatch_internal`` rechazó el caller_token."""


DryRunAuditCallback = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[None]]
"""Signature for the side-effect audit hook used by ``dry_run`` mode.

Arguments:
    tool_name           the tool the LLM tried to invoke
    args                the (already-validated) arguments
    synthetic_result    the placeholder result the agent will see

The callback is awaited inside dispatch, BEFORE the synthetic envelope is
returned. It must be idempotent against partial failures (the registry
does NOT retry on callback errors — see ``dispatch`` below).
"""


class MCPRegistry:
    def __init__(
        self,
        tools: Iterable[ToolBase] | None = None,
        internal_tools: Iterable[ToolBase] | None = None,
        *,
        dry_run: bool = False,
        dry_run_audit: DryRunAuditCallback | None = None,
    ) -> None:
        self._tools: dict[str, ToolBase] = {}
        self._internal_tools: dict[str, ToolBase] = {}
        self._dry_run = dry_run
        self._dry_run_audit = dry_run_audit
        if tools is not None:
            for t in tools:
                self.register(t)
        if internal_tools is not None:
            for t in internal_tools:
                self.register_internal(t)

    @property
    def dry_run(self) -> bool:
        """When True, dispatches of side-effecting tools are blocked.

        The check uses ``ToolBase.side_effects`` — any non-empty tuple
        marks the tool as side-effecting. Read-only tools (empty tuple)
        run normally so the operator gets real data while the agent
        explores. The audit callback records every blocked attempt.
        """
        return self._dry_run

    # ── registration ─────────────────────────────────────────────────────

    def register(self, tool: ToolBase) -> None:
        if tool.name in self._tools:
            raise RuntimeError(f"tool {tool.name!r} is already registered")
        if tool.name in self._internal_tools:
            raise RuntimeError(
                f"tool {tool.name!r} already registered as internal — cannot also be public"
            )
        self._tools[tool.name] = tool

    def register_internal(self, tool: ToolBase) -> None:
        """Registra una tool en el espacio interno (no LLM-facing).

        Solo invocable vía ``dispatch_internal`` con caller_token. NO
        aparece en ``names()``, ``get_tool_definitions()``, ni
        ``dispatch()``.
        """
        if tool.name in self._internal_tools:
            raise RuntimeError(f"internal tool {tool.name!r} is already registered")
        if tool.name in self._tools:
            raise RuntimeError(
                f"tool {tool.name!r} already registered as public — cannot also be internal"
            )
        self._internal_tools[tool.name] = tool

    def is_side_effecting(self, name: str) -> bool:
        """True when the public tool ``name`` declares side effects
        (non-empty ``ToolBase.side_effects`` — e.g. ``mutates_db``). Unknown
        names are False. Used to gate write tools for read-only admins."""
        tool = self._tools.get(name)
        return bool(tool and tool.side_effects)

    def has(self, name: str) -> bool:
        return name in self._tools

    def has_internal(self, name: str) -> bool:
        return name in self._internal_tools

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools.keys())

    def internal_names(self) -> tuple[str, ...]:
        return tuple(self._internal_tools.keys())

    # ── LLM-facing definitions ───────────────────────────────────────────

    def get_tool_definitions(self, whitelist: Iterable[str]) -> list[ToolDef]:
        """Return the ``ToolDef`` for every tool name in ``whitelist`` that
        is also registered. Order is stable — sorted by name — so the LLM
        sees a deterministic prompt."""
        wl = set(whitelist)
        out: list[ToolDef] = []
        for name in sorted(self._tools.keys()):
            if name in wl:
                out.append(self._tools[name].to_tool_def())
        return out

    def get_openai_tools(self, whitelist: Iterable[str]) -> list[dict[str, Any]]:
        return [d.to_openai_tool() for d in self.get_tool_definitions(whitelist)]

    # ── dispatch ─────────────────────────────────────────────────────────

    async def dispatch(
        self,
        name: str,
        args: dict[str, Any],
        *,
        whitelist: Iterable[str],
    ) -> ToolResult:
        """Run ``name`` with ``args``, after asserting:

        - The active tenant context is set (else ``IsolationViolation``).
        - The tool name is in the active tenant's ``whitelist``. If not,
          increment ``isolation.tool_whitelist_violation`` and raise
          ``ToolNotInWhitelist``. The pipeline catches this and records a
          ``skipped:not_in_whitelist`` entry — same behaviour as block C.
        - The tool is registered. If a name is in the whitelist but not in
          the registry (e.g. tool removed mid-deploy), raise ``ToolError``
          so it's loud — silently skipping would mask a misconfiguration.
        """
        tenant_id = require_current_tenant()
        wl = set(whitelist)
        if name not in wl:
            record_isolation_event(
                ISOLATION_TOOL_WHITELIST_VIOLATION,
                tenant_id,
                {"tool": name, "whitelist": sorted(wl)},
            )
            log.warning(
                "tool.whitelist_violation",
                tenant_id=str(tenant_id),
                tool=name,
            )
            raise ToolNotInWhitelist(
                f"tool {name!r} is not in the active whitelist for tenant {tenant_id}"
            )

        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"tool {name!r} is not registered in the MCP runtime")

        # ── dry_run gate (ADR-020 Phase 3) ───────────────────────────────
        # When the registry is in dry_run mode (QA Playground) and the
        # tool declares any side_effects, we MUST NOT actually invoke it.
        # The agent receives a synthetic envelope that lets the
        # conversation continue, and the operator-side audit table gets
        # one row per blocked attempt so the QA UI can show what would
        # have happened in a real run.
        if self._dry_run and tool.side_effects:
            synthetic = make_envelope(
                tool=name,
                tenant_id=tenant_id,
                args=dict(args),
                result={
                    "ok": True,
                    "blocked_by": "dry_run",
                    "side_effects_declared": list(tool.side_effects),
                    "note": (
                        "QA Playground intercepted this tool call. No real "
                        "side effect was performed."
                    ),
                },
                status="skipped:dry_run",
            )
            if self._dry_run_audit is not None:
                # Audit before returning so the operator sees the row even
                # if the agent's run errors out later in the turn.
                try:
                    await self._dry_run_audit(name, dict(args), synthetic)
                except Exception:
                    # Audit MUST NOT take down the conversation — log
                    # loudly and move on. The contract is best-effort
                    # persistence; the gate itself (no real call) holds
                    # regardless.
                    log.exception(
                        "dry_run_audit_callback_failed",
                        tool=name,
                        tenant_id=str(tenant_id),
                    )
            record_invocation(name)
            return synthetic

        record_invocation(name)
        started = time.perf_counter()
        try:
            envelope = await tool.invoke(args)
        except ToolError:
            record_error(name, "ToolError")
            raise
        except Exception as exc:
            record_error(name, type(exc).__name__)
            log.exception("tool.run_failed", tool=name, tenant_id=str(tenant_id))
            raise ToolError(f"tool {name!r} failed: {exc}") from exc
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            record_latency(name, elapsed_ms)
        return envelope

    async def dispatch_internal(
        self,
        name: str,
        args: dict[str, Any],
        *,
        caller_token: str,
    ) -> ToolResult:
        """Invoca una tool del espacio interno. NO chequea whitelist
        (las internal tools están fuera de cualquier whitelist por
        construcción), pero exige ``caller_token`` válido.

        Bloque E uso primario: ``booking.create_appointment.run`` detecta
        que el tenant tiene integration='agendapro' activa y llama
        ``dispatch_internal('agendapro.create_appointment', ...)`` para
        delegar al server subprocess. El external_ref devuelto se persiste
        en la fila local de ``appointments``.
        """
        if not secrets.compare_digest(caller_token, _INTERNAL_CALLER_TOKEN):
            log.warning("dispatch_internal.invalid_caller_token", tool=name)
            raise InternalCallerTokenInvalid(f"caller_token rejected for internal tool {name!r}")
        tenant_id = require_current_tenant()
        tool = self._internal_tools.get(name)
        if tool is None:
            raise ToolError(f"internal tool {name!r} is not registered")

        # dry_run also gates internal dispatches — otherwise the public
        # ``booking.create_appointment`` tool would be blocked but its
        # subprocess delegate (``agendapro.create_appointment``) would
        # still hit the real provider. Same audit hook fires.
        if self._dry_run and tool.side_effects:
            synthetic = make_envelope(
                tool=name,
                tenant_id=tenant_id,
                args=dict(args),
                result={
                    "ok": True,
                    "blocked_by": "dry_run",
                    "side_effects_declared": list(tool.side_effects),
                    "note": "QA Playground intercepted this internal tool call.",
                },
                status="skipped:dry_run",
            )
            if self._dry_run_audit is not None:
                try:
                    await self._dry_run_audit(name, dict(args), synthetic)
                except Exception:
                    log.exception(
                        "dry_run_audit_callback_failed",
                        tool=name,
                        tenant_id=str(tenant_id),
                    )
            record_invocation(name)
            return synthetic

        record_invocation(name)
        started = time.perf_counter()
        try:
            envelope = await tool.invoke(args)
        except ToolError:
            record_error(name, "ToolError")
            raise
        except Exception as exc:
            record_error(name, type(exc).__name__)
            log.exception("internal_tool.run_failed", tool=name, tenant_id=str(tenant_id))
            raise ToolError(f"internal tool {name!r} failed: {exc}") from exc
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            record_latency(name, elapsed_ms)
        return envelope

    async def safe_dispatch(
        self,
        name: str,
        args: dict[str, Any],
        *,
        whitelist: Iterable[str],
    ) -> ToolResult:
        """Variant that returns a ``skipped:not_in_whitelist`` envelope
        instead of raising when the whitelist rejects. Used by the pipeline
        when the LLM hallucinates a tool name outside the filtered set —
        the conversation can continue with a graceful "tool unavailable"
        rather than blowing up the turn.
        """
        try:
            return await self.dispatch(name, args, whitelist=whitelist)
        except ToolNotInWhitelist:
            tenant_id = require_current_tenant()
            return make_envelope(
                tool=name,
                tenant_id=tenant_id,
                args=dict(args),
                result={},
                status="skipped:not_in_whitelist",
            )


# ── default registry built lazily ────────────────────────────────────────────


_default_registry: MCPRegistry | None = None


def build_default_registry() -> MCPRegistry:
    """Construct the registry with the public Block-D servers.

    Block O (ADR-017): the public-link AgendaPro MCP lands here as
    INTERNAL tools (``agendapro_public.*``). The booking facade and
    the async booking cron reach them via ``dispatch_internal`` with
    the in-process caller token; the LLM never sees them.
    """
    global _default_registry
    if _default_registry is not None:
        return _default_registry

    # Local imports to avoid circular deps (each server's tools.py can
    # import from nexus_mcp.base safely).
    from nexus_mcp.servers.agendapro_public.tools import (
        build_agendapro_public_tools,
    )
    from nexus_mcp.servers.amigable_cobro.tools import AMIGABLE_COBRO_TOOLS
    from nexus_mcp.servers.booking.tools import BOOKING_TOOLS
    from nexus_mcp.servers.client.tools import CLIENT_TOOLS
    from nexus_mcp.servers.commission.tools import COMMISSION_TOOLS
    from nexus_mcp.servers.escalate.tools import ESCALATE_TOOLS
    from nexus_mcp.servers.notification.tools import NOTIFICATION_TOOLS
    from nexus_mcp.servers.operator.tools import OPERATOR_TOOLS
    from nexus_mcp.servers.queue.tools import QUEUE_TOOLS
    from nexus_mcp.servers.woocommerce.tools import WOOCOMMERCE_TOOLS

    registry = MCPRegistry()
    for tool_cls in (
        *ESCALATE_TOOLS,
        *CLIENT_TOOLS,
        *BOOKING_TOOLS,
        *QUEUE_TOOLS,
        *COMMISSION_TOOLS,
        *NOTIFICATION_TOOLS,
        *OPERATOR_TOOLS,
        *WOOCOMMERCE_TOOLS,
        *AMIGABLE_COBRO_TOOLS,
    ):
        registry.register(tool_cls())
    # Block O: agendapro_public.* are INTERNAL — the transport is
    # resolved at dispatch time (set_default_transport must run at
    # worker startup, or tests must inject a FakeAgendaProPublicTransport).
    for internal_tool in build_agendapro_public_tools():
        registry.register_internal(internal_tool)
    _default_registry = registry
    return registry


def reset_default_registry() -> None:
    global _default_registry
    _default_registry = None
