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

import structlog
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import LLMRouter
from nexus_worker.runtime.qa_pipeline import build_qa_pipeline

log = structlog.get_logger(__name__)


def _build_llm_router() -> LLMRouter:
    """Production LLM router. In dev/test the worker's ``InMemoryProvider``
    is plugged in via override; this default path uses LiteLLM."""
    from nexus_worker.runtime.llm import LiteLLMProvider

    provider = LiteLLMProvider()
    # Los tres identificadores van PINEADOS y verificados contra el
    # proveedor. ``anthropic/claude-sonnet-4-6`` estuvo aquí hasta el
    # 2026-08-28 y no existe: Anthropic responde
    # ``Invalid model name``, así que el playground fallaba para TODOS
    # los tenants — clasificaba bien y reventaba al responder. Un alias
    # sin pinear caduca en silencio; el fallo aparece en producción, no
    # en un test.
    return LLMRouter(
        provider=provider,
        classify_model="anthropic/claude-haiku-4-5-20251001",
        respond_model="anthropic/claude-haiku-4-5-20251001",
        fallback_model="openai/gpt-4o",
    )


# NOTE: no custom checkpointer is passed. langgraph-api 0.8.x rejects
# custom checkpointers at startup ("persistence is handled automatically
# by the platform"). The LangGraph Server runs the graph against its
# managed persistence; ``qa.threads`` (in the API's Postgres) is the
# operator-visible source of truth across restarts. Tests still inject
# ``MemorySaver`` via ``build_qa_pipeline(checkpointer=...)``.
qa_pilot = build_qa_pipeline(
    agent_loader=AgentLoader(),
    llm_router=_build_llm_router(),
)
