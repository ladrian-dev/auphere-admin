"""Anthropic Memory tool backend — Fase B of claude-platform-integration.

The Memory tool (``memory_20250818``) is a client-side built-in: Anthropic
exposes a stable command schema (view / create / str_replace / insert /
delete / rename) and the host (us) implements the backing store. We back
it with Postgres + RLS so the same per-tenant isolation guarantees that
gate the rest of the runtime gate memory access too.

Public surface:

- :class:`PathValidationError` — raised by the validator on traversal,
  bad prefix, or alias of a missing turn.
- :func:`validate_and_resolve_path` — pure function; rejects bad paths
  and rewrites ``/memories/customer/me/...`` → ``/memories/customer/{id}/...``.
- :class:`NexusPostgresMemoryTool` — async subclass of
  ``BetaAsyncAbstractMemoryTool`` driven from ``pipeline.py`` once per turn.

Built-in tools NEVER pass through the MCP registry — see
[[architecture/builtin-tools-vs-mcp-tools]].
"""

from __future__ import annotations

import os
import uuid

from nexus_worker.memory.path_validator import (
    PathValidationError,
    validate_and_resolve_path,
)
from nexus_worker.memory.postgres_memory_tool import (
    MAX_MEMORY_BYTES_PER_CUSTOMER,
    NexusPostgresMemoryTool,
)

# System message the handler injects when the memory tool is active for a
# tenant. Kept short — Anthropic's docs warn that long memory instructions
# crowd out task instructions. The "use sparingly" framing is deliberate:
# we want the agent to actually leverage memory, not treat it as scratch.
MEMORY_TOOL_SYSTEM_PROMPT: str = (
    "You have a persistent memory under /memories/. "
    "Use /memories/customer/me/ for facts about THIS customer (preferences, "
    "context). Use /memories/tenant/ for shared policies the operator "
    "curated. "
    "At the start of a turn, briefly check /memories for relevant files. "
    "When you learn something useful — a stable preference, a constraint, "
    "context from earlier conversations — save it concisely. "
    "Never store passwords, payment numbers, or other sensitive data."
)


def memory_tool_enabled_tenants() -> frozenset[uuid.UUID]:
    """Parse the ``NEXUS_MEMORY_TOOL_ENABLED_TENANTS`` env var.

    Comma-separated UUIDs (whitespace ignored). Returns an empty set
    when unset, which keeps the feature OFF by default and the production
    runtime unchanged for any tenant that has not been opted in.

    Read fresh on every call — operations can flip the var without
    redeploy and the next turn picks it up. A bad UUID is logged and
    skipped, NOT raised, so a typo in the env does not break the worker.
    """
    raw = os.getenv("NEXUS_MEMORY_TOOL_ENABLED_TENANTS", "")
    if not raw:
        return frozenset()
    out: set[uuid.UUID] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(uuid.UUID(token))
        except ValueError:
            # Keep going — a misconfigured env shouldn't blow up the
            # turn for OTHER tenants on the same worker.
            continue
    return frozenset(out)


def is_memory_tool_enabled_for(tenant_id: uuid.UUID) -> bool:
    """Whether the memory tool is active for this tenant right now."""
    return tenant_id in memory_tool_enabled_tenants()


__all__ = [
    "MAX_MEMORY_BYTES_PER_CUSTOMER",
    "MEMORY_TOOL_SYSTEM_PROMPT",
    "NexusPostgresMemoryTool",
    "PathValidationError",
    "is_memory_tool_enabled_for",
    "memory_tool_enabled_tenants",
    "validate_and_resolve_path",
]
