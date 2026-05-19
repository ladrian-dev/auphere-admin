"""Nexus QA Playground — LangGraph Server (self-hosted).

This package is what the QA Playground frontend (assistant-ui +
react-langgraph) talks to. It serves the production agent graph in
``dry_run`` mode so an Auphere operator can chat with a tenant's agent
without any real-world side effects landing on the tenant.

Three things make this server "QA mode":

1. ``MCPRegistry`` is constructed with ``dry_run=True`` and an audit
   callback that persists every intercepted dispatch to
   ``qa.side_effect_audit``.
2. The auth handler (``auth.py``) validates the same Bearer +
   ``X-Operator-Id`` combination the ``/qa/*`` HTTP endpoints use, then
   sets three contextvars per request: ``app.operator_id``,
   ``app.tenant_id``, ``current_qa_thread``. Without them the audit
   writer skips and RLS on qa.* fails closed.
3. ``ucm_formatter`` is forced ON — the Playground frontend reads
   ``state["ucm"]`` to render the agent's reply across channels.

Reference: ADR-020 (Phase 3).
"""

from qa_langgraph_server.graph import qa_pilot

__all__ = ["qa_pilot"]
