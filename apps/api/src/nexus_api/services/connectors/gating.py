"""Per-(tenant, tool) gating mode resolution.

This is the "second layer" of tool isolation. The first layer is the
``agent_config.tools`` whitelist (Block C, garantía 2) — a tool not in the
whitelist is never offered to the LLM.

This layer applies AFTER the LLM emits a tool call: even a whitelisted tool
may be ``blocked`` for a specific tenant via an override row, and a
``destructive=true`` tool from a connector with ``auto_enable_destructive=false``
defaults to ``blocked`` at sync time.

Resolution order for a tool ``T`` in tenant ``X``:

1. If ``tenant_connector_tool_overrides`` has a row for (X, T) → use its mode.
2. Else if ``tool_catalog.default_mode`` is non-null → use that.
3. Else fall back to ``ConnectorToolMode.ALWAYS`` (legacy / internal tools).

Phase 1 runtime treats ``needs_approval`` as ``blocked`` with a dedicated
counter, so Phase 4+ can flip the semantics without a data migration.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    ConnectorToolMode,
    TenantConnectorToolOverride,
    ToolCatalog,
)


class ToolNotInCatalog(LookupError):
    """No tool_catalog row for the given name."""


@dataclass(frozen=True)
class GatingResolution:
    tool_name: str
    mode: ConnectorToolMode
    source: str  # "override" | "default" | "fallback"
    override_reason: str | None = None


async def resolve_mode(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    tool_name: str,
) -> GatingResolution:
    """Resolve gating mode for a single (tenant, tool) pair.

    Caller must already be inside a tenant-scoped session (RLS bound to
    ``tenant_id``). Selecting the override row depends on RLS to filter
    by tenant, so passing a different ``tenant_id`` than the bound one
    has no effect — defense in depth.
    """
    override = await session.scalar(
        select(TenantConnectorToolOverride).where(
            TenantConnectorToolOverride.tool_name == tool_name
        )
    )
    if override is not None:
        return GatingResolution(
            tool_name=tool_name,
            mode=ConnectorToolMode(override.mode),
            source="override",
            override_reason=override.reason,
        )
    tool = await session.scalar(select(ToolCatalog).where(ToolCatalog.name == tool_name))
    if tool is None:
        msg = f"tool not in tool_catalog: {tool_name!r}"
        raise ToolNotInCatalog(msg)
    return GatingResolution(
        tool_name=tool_name,
        mode=ConnectorToolMode(tool.default_mode),
        source="default",
    )


def is_executable_phase1(resolution: GatingResolution) -> bool:
    """True iff the runtime should execute the tool in Phase 1.

    Phase 1: only ``always`` is executable. ``blocked`` AND
    ``needs_approval`` both stop execution; the LLM gets a canonical
    "let me consult and get back to you" message and the call is logged
    in audit_log + counter.
    """
    return resolution.mode is ConnectorToolMode.ALWAYS


def canonical_blocked_message_es() -> str:
    """The user-facing reply when a tool is gated off in Phase 1."""
    return (
        "Déjame consultar con el equipo y te confirmo en breve. "
        "Te escribo cuando tenga la respuesta."
    )


__all__ = [
    "GatingResolution",
    "ToolNotInCatalog",
    "canonical_blocked_message_es",
    "is_executable_phase1",
    "resolve_mode",
]
