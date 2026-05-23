"""Anthropic Memory tool backend — Fase B of claude-platform-integration.

The Memory tool (``memory_20250818``) is a client-side built-in: Anthropic
exposes a stable command schema (view / create / str_replace / insert /
delete / rename) and the host (us) implements the backing store. We back
it with Postgres + RLS so the same per-tenant isolation guarantees that
gate the rest of the runtime gate memory access too.

Activation is per ``agent_config`` via ``runtime_memory_tool BOOLEAN``
(migration 0035) — the handler checks ``bundle.runtime_memory_tool``.
No env vars per-tenant.

Public surface:

- :class:`PathValidationError` — raised by the validator on traversal,
  bad prefix, or alias of a missing turn.
- :func:`validate_and_resolve_path` — pure function; rejects bad paths
  and rewrites ``/memories/customer/me/...`` → ``/memories/customer/{id}/...``.
- :class:`NexusPostgresMemoryTool` — async subclass of
  ``BetaAsyncAbstractMemoryTool`` driven from ``pipeline.py`` once per turn.
- :data:`MEMORY_TOOL_SYSTEM_PROMPT` — the system addendum the handler
  injects before the conversation history when the tool is enabled.

Built-in tools NEVER pass through the MCP registry — see
[[architecture/builtin-tools-vs-mcp-tools]].
"""

from __future__ import annotations

from nexus_worker.memory.path_validator import (
    PathValidationError,
    validate_and_resolve_path,
)
from nexus_worker.memory.postgres_memory_tool import (
    MAX_MEMORY_BYTES_PER_CUSTOMER,
    NexusPostgresMemoryTool,
)

# System message the handler injects when the memory tool is active for
# this turn's agent_config. Kept short — Anthropic's docs warn that long
# memory instructions crowd out task instructions. The "use sparingly"
# framing is deliberate: we want the agent to actually leverage memory,
# not treat it as scratch.
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


__all__ = [
    "MAX_MEMORY_BYTES_PER_CUSTOMER",
    "MEMORY_TOOL_SYSTEM_PROMPT",
    "NexusPostgresMemoryTool",
    "PathValidationError",
    "validate_and_resolve_path",
]
