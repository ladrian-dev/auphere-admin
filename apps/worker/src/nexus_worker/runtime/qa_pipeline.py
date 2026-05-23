"""QA pipeline builder — wraps ``build_pipeline`` for the QA Playground.

The QA pipeline is the SAME graph the production worker runs (classify →
handlers → respond → ucm_formatter → checkpoint). What changes is the
MCP registry it talks to.

Two modes (ADR-024):

- ``dry_run=True`` (default) — any tool that declares ``side_effects`` is
  intercepted: the registry returns a synthetic envelope so the
  conversation keeps flowing and an audit callback persists each blocked
  attempt to ``qa.side_effect_audit`` keyed to the current QA thread.
  This is the safe default: the Playground never mutates a real
  calendar, WooCommerce order or Composio-backed account by accident.

- ``dry_run=False`` (live) — the registry runs every tool against the
  tenant's real connectors. End-to-end behaviour, no audit hooks, no
  interception. Selected per thread via ``qa.threads.dry_run`` so a
  reckless flip is impossible at the global level.

In **both** modes we build a FRESH registry instance (a view that shares
the populated tool instances of the process singleton) rather than
mutating ``build_default_registry()`` itself — otherwise the two QA
pipelines (dry + live) would share a mutable flag on a single registry
and toggling one would silently change the other.

Reference: ADR-020 Fase 3 · ADR-024.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from nexus_mcp import MCPRegistry, build_default_registry

from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import LLMRouter
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.qa_audit import make_qa_audit_writer

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def _build_qa_registry(*, dry_run: bool) -> MCPRegistry:
    """A fresh ``MCPRegistry`` view for the QA path.

    The view shares the populated tool instances of the process
    singleton but owns its own ``dry_run`` flag + audit callback so the
    dry and live QA pipelines never share mutable state. The same copy
    trick the eval driver uses (and that ``pipeline._view_with_composio``
    uses for per-tenant Composio proxies).
    """
    base = build_default_registry()
    audit_writer = make_qa_audit_writer() if dry_run else None
    view = MCPRegistry(dry_run=dry_run, dry_run_audit=audit_writer)
    for name in base.names():
        view._tools[name] = base._tools[name]
    for name in base.internal_names():
        view._internal_tools[name] = base._internal_tools[name]
    return view


def build_qa_pipeline(
    *,
    agent_loader: AgentLoader,
    llm_router: LLMRouter,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    dry_run: bool = True,
) -> Any:
    """Compile the agent graph in QA mode.

    When ``dry_run`` is True (the default) the returned graph behaves
    like production except:
      - the MCP registry intercepts every tool call with non-empty
        ``side_effects`` and returns a synthetic envelope so the
        conversation keeps flowing.
      - intercepted calls fire an audit callback that opens its own DB
        session, applies the current operator/tenant scope from
        contextvars, and persists one ``qa.side_effect_audit`` row keyed
        to the current ``qa_thread_context``.

    When ``dry_run`` is False (ADR-024 live mode), the registry runs
    every tool against the tenant's real connectors. No audit callback
    is wired — there is nothing blocked to record.

    The ``ucm_formatter`` node is forced on in both modes because the
    Playground frontend consumes the UCM payload directly.

    The caller (the LangGraph Server's auth layer) is responsible for
    setting THREE contextvars before invoking the graph:
      - ``app.operator_id`` (via ``operator_context``)
      - ``app.tenant_id``   (via ``tenant_context``)
      - ``current_qa_thread`` (via ``qa_thread_context``)
    Without all three the audit callback (dry mode only) skips and RLS
    on ``qa.*`` fails closed.

    A single compiled graph can serve concurrent runs from different
    operators — each dispatch reads the contextvar values for its own
    task, so the registry is safe to share.
    """
    registry = _build_qa_registry(dry_run=dry_run)
    return build_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=checkpointer,
        mcp_registry=registry,
        use_ucm_formatter=True,
    )


def qa_run_metadata(
    *,
    operator_id: str,
    tenant_id: uuid.UUID,
    qa_thread_id: uuid.UUID,
) -> dict[str, Any]:
    """Metadata to attach to every QA graph invocation (Langfuse / OTEL).

    The LangGraph Server's request handler MUST pass this dict as the
    ``metadata`` field of the ``RunnableConfig`` it hands to
    ``graph.astream`` / ``graph.ainvoke``. The keys land on every
    Langfuse trace, so the QA dashboard filters cleanly with
    ``qa = true`` and per-tenant/per-operator drill-down works.

    Without this metadata, QA traffic mixes with production traces and
    the alerts in ``docs/qa-playground/alerts.md`` cannot route.

    Reference: ADR-020 Fase 6 (Bloque E.3).
    """
    return {
        "qa": True,
        "qa.operator_id": str(operator_id),
        "qa.tenant_id": str(tenant_id),
        "qa.thread_id": str(qa_thread_id),
    }
