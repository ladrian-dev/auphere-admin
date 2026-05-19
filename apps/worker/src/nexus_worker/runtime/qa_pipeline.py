"""QA pipeline builder — wraps ``build_pipeline`` for the QA Playground.

The QA pipeline is the SAME graph the production worker runs (classify →
handlers → respond → ucm_formatter → checkpoint). What changes is the
MCP registry it talks to: a registry built with ``dry_run=True`` so any
side-effecting tool is intercepted before it can hit a real provider,
and an audit callback that persists each intercepted call to
``qa.side_effect_audit`` keyed to the current QA thread.

This is what the LangGraph Server (``apps/qa-langgraph-server/``) uses
internally. Production deployment never instantiates it.

Reference: ADR-020 Phase 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nexus_mcp import build_default_registry

from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import LLMRouter
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.qa_audit import make_qa_audit_writer

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def build_qa_pipeline(
    *,
    agent_loader: AgentLoader,
    llm_router: LLMRouter,
    checkpointer: BaseCheckpointSaver[Any],
) -> Any:
    """Compile the agent graph in QA mode.

    The returned graph behaves like the production one except:
      - the MCP registry has ``dry_run=True``, so any tool call with a
        non-empty ``side_effects`` declaration is intercepted (the
        synthetic envelope is returned to the agent so the conversation
        keeps flowing).
      - intercepted calls fire an audit callback that opens its own
        DB session, applies the current operator/tenant scope from
        contextvars, and persists one ``qa.side_effect_audit`` row
        keyed to the current ``qa_thread_context``.
      - the ucm_formatter node is forced on regardless of the global
        feature flag, because the QA Playground frontend consumes the
        UCM payload directly (Fase 0/Fase 2 contract).

    The caller (the LangGraph Server's auth layer) is responsible for
    setting THREE contextvars before invoking the graph:
      - ``app.operator_id`` (via ``operator_context``)
      - ``app.tenant_id``   (via ``tenant_context``)
      - ``current_qa_thread`` (via ``qa_thread_context``)
    Without all three the audit callback skips (logged error) and RLS
    on qa.* fails closed.

    A single compiled graph can serve concurrent runs from different
    operators — each dispatch reads the contextvar values for its own
    task, so the registry is safe to share.
    """
    audit_writer = make_qa_audit_writer()
    registry = build_default_registry()
    # Swap the registry into dry_run mode after construction so we don't
    # need to fork ``build_default_registry``. ``MCPRegistry`` exposes
    # both knobs as instance state for this exact use case.
    registry._dry_run = True
    registry._dry_run_audit = audit_writer

    return build_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=checkpointer,
        mcp_registry=registry,
        use_ucm_formatter=True,
    )
