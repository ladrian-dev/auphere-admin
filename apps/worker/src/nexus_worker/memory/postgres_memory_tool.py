"""``NexusPostgresMemoryTool`` — Postgres+RLS backend for ``memory_20250818``.

The Anthropic Memory tool is a *client-side built-in*: the model emits
``tool_use`` blocks against the ``memory`` tool with one of six commands
(``view``, ``create``, ``str_replace``, ``insert``, ``delete``,
``rename``), and the host is responsible for executing them and feeding
back a string ``tool_result``. We back the store with the
``agent_memories`` table created in migration 0032; RLS guarantees the
SQL refuses to read or write rows that belong to other tenants even if
the tool's path validator is somehow bypassed.

Architectural notes:

- We subclass ``BetaAsyncAbstractMemoryTool`` from the Anthropic SDK so
  the command-dispatch (``execute()``), argument validation
  (``BetaMemoryTool20250818*Command`` Pydantic models), and tool spec
  (``to_dict()`` → ``{"type": "memory_20250818", "name": "memory"}``)
  come for free. We do NOT use the SDK for the HTTP transport — LiteLLM
  remains the completion client. The SDK is a *library*; the worker
  never calls ``anthropic.AsyncAnthropic()``.
- The instance is *constructed per turn* in ``pipeline.py`` with the
  current ``tenant_id`` + ``customer_id``. Sharing an instance across
  turns would mean threading the per-turn customer through every call,
  which is exactly what an LLM-driven runtime should not do.
- The instance does NOT pass through ``MCPRegistry`` (see
  [[architecture/builtin-tools-vs-mcp-tools]]). The handler ReAct loop
  detects ``tool_call.name == "memory"`` and dispatches directly to
  ``call(args)``. The registry only sees business tools.

Format invariants enforced by Anthropic's docs:

- ``view`` of a directory returns a tab-separated listing one path per
  line, prefixed by the size in bytes (``\\t``-separated).
- ``view`` of a file returns the content with each line prefixed by a
  6-character right-aligned line number followed by a tab.
- ``create`` is *idempotent-failing*: a second ``create`` on the same
  path errors.
- ``str_replace`` errors if ``old_str`` matches zero or multiple times.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from anthropic.lib.tools import BetaAsyncAbstractMemoryTool
from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentMemory
from sqlalchemy import delete, func, or_, select, update

from nexus_worker.memory.path_validator import (
    PathValidationError,
    validate_and_resolve_path,
)

if TYPE_CHECKING:
    from anthropic.lib.tools._beta_functions import BetaFunctionToolResultType

log = structlog.get_logger(__name__)


# Per-customer storage cap. 100 KB is generous for a chat agent's
# memory (the Anthropic blog post on the memory tool suggests far
# less). The cap is enforced on ``create`` / ``insert`` / ``str_replace``;
# ``delete`` and ``view`` are exempt. Tenant-wide memories (customer_id
# IS NULL) are NOT capped here — operator-curated content.
MAX_MEMORY_BYTES_PER_CUSTOMER: int = 100_000


def _format_line(line_number: int, content: str) -> str:
    """Anthropic format: 6-char right-aligned line number + tab + content."""
    return f"{line_number:>6}\t{content}"


def _format_directory_listing(entries: list[tuple[str, int]]) -> str:
    """Anthropic format for ``view`` on a directory.

    ``entries`` is a sorted list of ``(path, size_bytes)`` pairs. The
    output is one entry per line as ``<size>\\t<path>``.
    """
    if not entries:
        return "(empty)"
    return "\n".join(f"{size}\t{path}" for path, size in entries)


def _path_is_directory(path: str) -> bool:
    """Heuristic: a path with NO trailing extension and no dot in the
    last segment behaves like a directory for the ``view`` command. We
    rely on the actual storage to confirm — if a row exists with this
    exact path, it is a file regardless of the heuristic.
    """
    last = path.rsplit("/", 1)[-1]
    return "." not in last


class _MemoryBackendError(Exception):
    """Raised when the SQL backend rejects the operation.

    The message is surfaced as a ``tool_result`` content — keep it
    LLM-safe (no other customers' UUIDs, no SQL strings).
    """


class NexusPostgresMemoryTool(BetaAsyncAbstractMemoryTool):
    """Per-turn instance, scoped to ``(tenant_id, customer_id)``.

    The class is constructed by ``pipeline.py`` after ``classify`` once
    the customer for the turn is known. ``customer_id`` may be ``None``
    for runs that operate entirely on tenant-wide memories.
    """

    def __init__(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID | None,
    ) -> None:
        super().__init__()
        self._tenant_id = tenant_id
        self._customer_id = customer_id

    # ── helpers ──────────────────────────────────────────────────────

    def _resolve(self, raw_path: str) -> str:
        """Validate and resolve the LLM-provided path.

        Wraps :func:`validate_and_resolve_path` so callers can treat path
        failures the same way as backend failures (a string tool_result).
        """
        try:
            return validate_and_resolve_path(raw_path, customer_id=self._customer_id)
        except PathValidationError as exc:
            raise _MemoryBackendError(str(exc)) from exc

    def _customer_id_for(self, resolved_path: str) -> uuid.UUID | None:
        """Map a resolved path back to the ``customer_id`` column value.

        ``/memories/customer/{uuid}/...`` → that UUID.
        ``/memories/tenant/...`` → ``None`` (tenant-wide).
        """
        if resolved_path.startswith("/memories/customer/"):
            return self._customer_id
        return None

    async def _row_for_path(self, session: object, resolved_path: str) -> AgentMemory | None:
        """SELECT the row matching this resolved path, scoped by RLS.

        Uses RLS for tenant scoping (the ``SET LOCAL app.tenant_id`` is
        set by ``tenant_scoped_session`` in the caller). The customer
        filter is explicit on top — RLS does not know about customers.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)  # narrow type for mypy
        customer_id = self._customer_id_for(resolved_path)
        stmt = select(AgentMemory).where(AgentMemory.path == resolved_path)
        if customer_id is None:
            stmt = stmt.where(AgentMemory.customer_id.is_(None))
        else:
            stmt = stmt.where(AgentMemory.customer_id == customer_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _customer_byte_usage(self, session: object) -> int:
        """Sum of ``size_bytes`` for the current customer's rows.

        Tenant-wide memories (customer_id IS NULL) are not counted —
        the per-customer cap is about the LLM's freedom on a given
        conversation, not about operator content.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
        if self._customer_id is None:
            return 0
        stmt = select(func.coalesce(func.sum(AgentMemory.size_bytes), 0)).where(
            AgentMemory.customer_id == self._customer_id
        )
        return int((await session.execute(stmt)).scalar_one())

    async def _ensure_under_cap(
        self,
        session: object,
        resolved_path: str,
        new_content: str,
        *,
        replacing_existing_size: int = 0,
    ) -> None:
        """Refuse the write if it would push the customer over the cap.

        ``replacing_existing_size`` is the size_bytes of the row that
        will be replaced (for ``str_replace`` / ``insert``); subtract
        that from the projected total so we are not double-counting.
        """
        if self._customer_id_for(resolved_path) is None:
            return  # tenant-wide row, not capped here
        usage = await self._customer_byte_usage(session)
        projected = usage - replacing_existing_size + len(new_content.encode("utf-8"))
        if projected > MAX_MEMORY_BYTES_PER_CUSTOMER:
            raise _MemoryBackendError(
                f"memory full ({projected} bytes would exceed the "
                f"{MAX_MEMORY_BYTES_PER_CUSTOMER}-byte cap); delete or shrink "
                "older files before writing new ones"
            )

    # ── command implementations ─────────────────────────────────────

    async def view(
        self, command: BetaMemoryTool20250818ViewCommand
    ) -> BetaFunctionToolResultType:
        """View a file (line-numbered) or list a directory.

        ``view_range`` (1-indexed inclusive bounds) trims the output to
        the requested lines. Anthropic accepts ``None`` for one end.
        """
        try:
            resolved = self._resolve(command.path)
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, self._tenant_id):
                # Try the file path first: if a row exists, format as file.
                file_row = await self._row_for_path(session, resolved)
                if file_row is not None:
                    lines = file_row.content.split("\n")
                    rng = command.view_range
                    if rng is not None and len(rng) == 2:
                        start, end = rng
                        # 1-indexed → 0-indexed; clamp at bounds.
                        s = max(1, start) - 1
                        e = (len(lines) if end is None else min(end, len(lines)))
                        lines = lines[s:e]
                        offset = s + 1
                    else:
                        offset = 1
                    formatted = "\n".join(
                        _format_line(offset + i, ln) for i, ln in enumerate(lines)
                    )
                    # Touch ``last_accessed_at`` so retention / inspection
                    # can tell hot from cold memories. Doesn't fire the
                    # audit trigger because that only watches INSERT /
                    # UPDATE of the content row's lifecycle; this is a
                    # benign metadata bump.
                    await session.execute(
                        update(AgentMemory)
                        .where(AgentMemory.id == file_row.id)
                        .values(last_accessed_at=datetime.now(UTC))
                    )
                    await session.commit()
                    return formatted

                # Not a file → maybe a directory. List rows whose path
                # is under this prefix.
                if not _path_is_directory(resolved) and resolved != "/memories":
                    return f"path '{command.path}' does not exist"

                prefix = resolved.rstrip("/")
                like = f"{prefix}/%"
                stmt = select(AgentMemory.path, AgentMemory.size_bytes).where(
                    or_(AgentMemory.path == prefix, AgentMemory.path.like(like))
                )
                # Constrain the directory listing by customer scope so
                # tenant-wide listings don't show customer files.
                customer_id = self._customer_id_for(resolved)
                if resolved == "/memories":
                    # Listing root — show both customer-scoped (own) and
                    # tenant-wide entries. RLS still gates tenant.
                    if self._customer_id is not None:
                        stmt = stmt.where(
                            or_(
                                AgentMemory.customer_id == self._customer_id,
                                AgentMemory.customer_id.is_(None),
                            )
                        )
                    else:
                        stmt = stmt.where(AgentMemory.customer_id.is_(None))
                elif customer_id is None:
                    stmt = stmt.where(AgentMemory.customer_id.is_(None))
                else:
                    stmt = stmt.where(AgentMemory.customer_id == customer_id)
                rows = list((await session.execute(stmt.order_by(AgentMemory.path))).all())
                entries = [(p, s) for p, s in rows]
                return _format_directory_listing(entries)
        except _MemoryBackendError as exc:
            return str(exc)

    async def create(
        self, command: BetaMemoryTool20250818CreateCommand
    ) -> BetaFunctionToolResultType:
        """Create a new memory file. Errors if the path already exists."""
        try:
            resolved = self._resolve(command.path)
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, self._tenant_id):
                existing = await self._row_for_path(session, resolved)
                if existing is not None:
                    return (
                        f"path '{command.path}' already exists — use str_replace "
                        "to modify, or delete first and recreate"
                    )
                await self._ensure_under_cap(session, resolved, command.file_text)
                customer_id = self._customer_id_for(resolved)
                session.add(
                    AgentMemory(
                        tenant_id=self._tenant_id,
                        customer_id=customer_id,
                        path=resolved,
                        content=command.file_text,
                    )
                )
                await session.commit()
                return f"created '{command.path}'"
        except _MemoryBackendError as exc:
            return str(exc)

    async def str_replace(
        self, command: BetaMemoryTool20250818StrReplaceCommand
    ) -> BetaFunctionToolResultType:
        """Replace ``old_str`` with ``new_str`` in a memory file.

        Errors when ``old_str`` matches zero or multiple times — this is
        the Anthropic-documented semantics and prevents the LLM from
        making accidental global replacements.
        """
        try:
            resolved = self._resolve(command.path)
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, self._tenant_id):
                row = await self._row_for_path(session, resolved)
                if row is None:
                    return f"path '{command.path}' does not exist"
                occurrences = row.content.count(command.old_str)
                if occurrences == 0:
                    return f"old_str not found in '{command.path}'"
                if occurrences > 1:
                    return (
                        f"old_str matches {occurrences} times in '{command.path}'; "
                        "be more specific so the replacement is unique"
                    )
                new_content = row.content.replace(command.old_str, command.new_str)
                await self._ensure_under_cap(
                    session,
                    resolved,
                    new_content,
                    replacing_existing_size=row.size_bytes,
                )
                await session.execute(
                    update(AgentMemory)
                    .where(AgentMemory.id == row.id)
                    .values(content=new_content)
                )
                await session.commit()
                return f"replaced in '{command.path}'"
        except _MemoryBackendError as exc:
            return str(exc)

    async def insert(
        self, command: BetaMemoryTool20250818InsertCommand
    ) -> BetaFunctionToolResultType:
        """Insert ``insert_text`` at line ``insert_line`` (0-indexed, where
        0 means "at the start"). The Anthropic docs use 0-indexed where 0
        means before line 1; we follow that.
        """
        try:
            resolved = self._resolve(command.path)
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, self._tenant_id):
                row = await self._row_for_path(session, resolved)
                if row is None:
                    return f"path '{command.path}' does not exist"
                lines = row.content.split("\n")
                insert_at = max(0, min(command.insert_line, len(lines)))
                new_lines = [*lines[:insert_at], command.insert_text, *lines[insert_at:]]
                new_content = "\n".join(new_lines)
                await self._ensure_under_cap(
                    session,
                    resolved,
                    new_content,
                    replacing_existing_size=row.size_bytes,
                )
                await session.execute(
                    update(AgentMemory)
                    .where(AgentMemory.id == row.id)
                    .values(content=new_content)
                )
                await session.commit()
                return f"inserted at line {insert_at} of '{command.path}'"
        except _MemoryBackendError as exc:
            return str(exc)

    async def delete(
        self, command: BetaMemoryTool20250818DeleteCommand
    ) -> BetaFunctionToolResultType:
        """Delete the file at ``path``. Refuses directory paths to avoid
        accidental mass deletion — the LLM must use the file path itself.
        """
        try:
            resolved = self._resolve(command.path)
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, self._tenant_id):
                row = await self._row_for_path(session, resolved)
                if row is None:
                    return f"path '{command.path}' does not exist"
                await session.execute(delete(AgentMemory).where(AgentMemory.id == row.id))
                await session.commit()
                return f"deleted '{command.path}'"
        except _MemoryBackendError as exc:
            return str(exc)

    async def rename(
        self, command: BetaMemoryTool20250818RenameCommand
    ) -> BetaFunctionToolResultType:
        """Rename / move a file within the same customer scope.

        Cross-scope renames (customer → tenant-wide or vice versa) are
        rejected: the customer scope is part of the row's identity, not
        a path-level convention.
        """
        try:
            old_resolved = self._resolve(command.old_path)
            new_resolved = self._resolve(command.new_path)
            if self._customer_id_for(old_resolved) != self._customer_id_for(new_resolved):
                return (
                    "rename across customer/tenant scopes is not allowed; "
                    "use create+delete instead"
                )
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, self._tenant_id):
                row = await self._row_for_path(session, old_resolved)
                if row is None:
                    return f"path '{command.old_path}' does not exist"
                # Refuse to overwrite an existing destination — same
                # invariant as ``create``.
                existing_dest = await self._row_for_path(session, new_resolved)
                if existing_dest is not None:
                    return (
                        f"destination '{command.new_path}' already exists; "
                        "delete it first"
                    )
                await session.execute(
                    update(AgentMemory)
                    .where(AgentMemory.id == row.id)
                    .values(path=new_resolved)
                )
                await session.commit()
                return f"renamed '{command.old_path}' to '{command.new_path}'"
        except _MemoryBackendError as exc:
            return str(exc)


__all__ = [
    "MAX_MEMORY_BYTES_PER_CUSTOMER",
    "NexusPostgresMemoryTool",
]
