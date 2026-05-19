"""QA audit writer — persists blocked side-effect dispatches to ``qa.side_effect_audit``.

When the MCP registry is built in dry_run mode (QA Playground), any side-
effecting tool the agent tries to call gets intercepted: the registry
returns a synthetic envelope AND invokes this audit callback so the
operator can later see what the agent *wanted* to do.

The writer opens its own SQLAlchemy session (the agent runtime has no
direct session — it talks to Postgres only via the checkpointer), scopes
it to the current ``operator_id`` + ``tenant_id`` from the contextvars
the QA dispatcher set up, and inserts one row. It NEVER raises into the
agent's run: failures are logged and swallowed so the conversation
keeps flowing while the audit table becomes eventually-consistent.

Reference: ADR-020 Phase 3.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from nexus_api.core.operator_context import (
    apply_operator_to_session,
    get_current_operator,
    get_current_qa_thread,
)
from nexus_api.core.tenant_context import (
    apply_tenant_to_session,
    get_current_tenant,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.qa import QASideEffectAudit
from sqlalchemy import text

log = structlog.get_logger(__name__)


QAAuditCallback = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[None]]


def make_qa_audit_writer(
    *,
    run_id: str | None = None,
    thread_id: uuid.UUID | None = None,
) -> QAAuditCallback:
    """Build a dry-run audit callback for the QA Playground.

    All three scope ids (operator_id, tenant_id, thread_id) are read
    from contextvars at invocation time:

      - ``app.operator_id`` and ``app.tenant_id`` from
        ``operator_context`` / ``tenant_context`` (set by the LangGraph
        Server's auth layer per request).
      - ``current_qa_thread`` from ``qa_thread_context``. Optionally
        ``thread_id`` can be passed at builder time and it wins over
        the contextvar — useful for tests that don't want to wrap
        every dispatch in a ``qa_thread_context``.

    The returned callable matches ``MCPRegistry.DryRunAuditCallback``:
    ``(tool_name, args, synthetic_envelope) -> Awaitable[None]``.

    A single ``MCPRegistry`` instance can be shared across concurrent
    runs from different operators safely — each dispatch sees the
    contextvar values for its own task.
    """

    pinned_thread_id = thread_id

    async def write_audit(
        tool_name: str,
        args: dict[str, Any],
        synthetic: dict[str, Any],
    ) -> None:
        operator_id = get_current_operator()
        tenant_id = get_current_tenant()
        effective_thread = pinned_thread_id or get_current_qa_thread()
        if operator_id is None or tenant_id is None or effective_thread is None:
            # If any scope is missing the audit row would be orphaned
            # (and probably violate the RLS WITH CHECK). Log loudly and
            # skip — the gate (no real call) still holds because that's
            # done by MCPRegistry before we got here.
            log.error(
                "qa_audit.missing_scope",
                tool=tool_name,
                has_operator=operator_id is not None,
                has_tenant=tenant_id is not None,
                has_thread=effective_thread is not None,
            )
            return

        sm = get_sessionmaker()
        try:
            async with sm() as session, session.begin():
                # Apply both scopes inside this tx. ``apply_tenant_to_session``
                # also does the SET LOCAL ROLE nexus_app so RLS is enforced.
                await apply_tenant_to_session(session, tenant_id)
                await apply_operator_to_session(session, operator_id)
                # Defence in depth: confirm the SET ROLE took. If not the
                # WITH CHECK on the policy would reject — that's the
                # actual safety net — but we want a clean error message.
                await session.execute(text("SET LOCAL ROLE nexus_app"))
                session.add(
                    QASideEffectAudit(
                        operator_id=operator_id,
                        tenant_id=tenant_id,
                        thread_id=effective_thread,
                        tool_name=tool_name,
                        tool_args=dict(args),
                        synthetic_result=dict(synthetic),
                        blocked_reason=str(
                            synthetic.get("result", {}).get("blocked_by", "dry_run")
                        ),
                        run_id=run_id,
                    )
                )
        except Exception:
            log.exception(
                "qa_audit.write_failed",
                tool=tool_name,
                thread_id=str(effective_thread),
                operator_id=str(operator_id),
            )

    return write_audit
