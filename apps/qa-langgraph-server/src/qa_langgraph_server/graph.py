"""Compiled QA pilot graph — entrypoint for ``langgraph.json``.

The LangGraph CLI imports ``qa_pilot`` from this module at server start.
We construct it once with the production agent loader + LLM router +
checkpointer, and ``build_qa_pipeline`` wires it to a dry-run
MCPRegistry whose audit callback reads its scope from contextvars set
by the auth handler.

The graph is safe to share across concurrent runs — every dispatch
reads its own ``operator_id`` / ``tenant_id`` / ``current_qa_thread``
from contextvars.
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import LLMRouter
from nexus_worker.runtime.qa_pipeline import build_qa_pipeline

log = structlog.get_logger(__name__)


def _build_llm_router() -> LLMRouter:
    """Production LLM router. In dev/test the worker's ``InMemoryProvider``
    is plugged in via override; this default path uses LiteLLM."""
    from nexus_worker.runtime.llm import LiteLLMProvider

    provider = LiteLLMProvider()
    return LLMRouter(
        provider=provider,
        classify_model="anthropic/claude-haiku-4-5-20251001",
        respond_model="anthropic/claude-sonnet-4-6",
        fallback_model="openai/gpt-4o",
    )


def _build_checkpointer() -> Any:
    """In-memory checkpointer for the QA Server.

    QA threads are short-lived (an operator session) and the
    ``qa.threads`` row is what survives across restarts — the LangGraph
    state itself can stay in process memory. If a Railway instance
    restarts mid-thread the operator picks the conversation up from the
    audit + the persisted message history, not from the checkpointer.
    """
    return MemorySaver()


qa_pilot = build_qa_pipeline(
    agent_loader=AgentLoader(),
    llm_router=_build_llm_router(),
    checkpointer=_build_checkpointer(),
)
