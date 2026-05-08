"""LangGraph 1.0 pipeline — 8 nodes.

::

    START → classify → route* → {book | queue | info | escalate | fallback}
                                                                 ↓
                                                              respond → checkpoint → END

(*) ``route`` is a conditional edge, not a node, so the node count is exactly
the eight required by the block-C spec: classify, the five handlers, respond
and checkpoint.

Design points:

- The LLM never sees a tool definition in block C — handlers dispatch
  deterministically. This makes garantía 2 trivially safe at runtime: there
  is no "tool surface" to leak. When block D wires real MCP servers and
  function-calling, the AgentLoader's ``tools`` whitelist is the only set of
  definitions that will ever be passed in. The runtime test in
  ``test_2_tool_whitelist_runtime.py`` asserts both that the counter
  ``isolation.tool_whitelist_violation`` increments when a handler hits a
  non-whitelisted tool AND that no whitelisted tool name leaks into the
  respond-phase prompt.

- Each node enters ``tenant_context(tenant_id)`` before touching repos/tools.
  Nodes can run on different threads in some LangGraph backends; the
  contextvar set in the orchestrator is not guaranteed to leak in.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog
from langgraph.graph import END, START, StateGraph
from nexus_api.core.metrics import (
    ISOLATION_TOOL_WHITELIST_VIOLATION,
    counters,
)
from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

from nexus_worker.persistence.messages import persist_outbound_message
from nexus_worker.runtime.agent_loader import AgentBundle, AgentLoader
from nexus_worker.runtime.llm import LLMRouter
from nexus_worker.runtime.state import AgentState
from nexus_worker.tools.registry import ToolError, get_handler

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

# Each node returns a partial state (LangGraph treats the returned dict as a
# diff). Using ``Any`` here keeps the StateGraph.add_node overload selection
# simple — the runtime tests cover correctness end-to-end.
NodeFn = Callable[[AgentState], Awaitable[Any]]

log = structlog.get_logger(__name__)


VALID_INTENTS = ("book", "queue", "info", "escalate", "fallback")


# Intent → tools the handler will attempt, in order. Each is whitelist-checked.
_HANDLER_TOOLS: dict[str, tuple[str, ...]] = {
    "book": ("booking.check_availability", "booking.create_appointment"),
    "queue": ("queue.join_queue", "queue.get_estimated_wait"),
    "info": ("client.get_history",),
    "escalate": ("escalate.escalate_to_human",),
    "fallback": (),
}


def _tenant_uuid(state: AgentState) -> uuid.UUID:
    return uuid.UUID(state["tenant_id"])


# ── Node factories ────────────────────────────────────────────────────────────


def make_classify_node(loader: AgentLoader, llm: LLMRouter) -> NodeFn:
    async def classify(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            await loader.load(tenant_id)  # warms cache; raises if no active config
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Classify the user's message into exactly one of: "
                        + ", ".join(VALID_INTENTS)
                        + ". Respond with the single label."
                    ),
                },
                {"role": "user", "content": state["user_message"]},
            ]
            raw = await llm.classify(tenant_id=tenant_id, messages=messages)
            intent = (raw or "").strip().lower()
            if intent not in VALID_INTENTS:
                log.info("classify.unknown_label_using_fallback", raw=raw)
                intent = "fallback"
            return {"intent": intent, "route": intent}

    return classify


def _route_decider(state: AgentState) -> str:
    return state.get("route") or "fallback"


def make_handler_node(intent: str, loader: AgentLoader) -> NodeFn:
    """Build a node that dispatches the given intent's tool list against the
    active whitelist.

    A non-whitelisted tool:
      - increments ``isolation.tool_whitelist_violation``
      - records a ``skipped:not_in_whitelist`` entry in ``tool_calls``
      - does NOT call the tool stub at all (no side effects)
    """

    async def handler(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            bundle: AgentBundle = await loader.load(tenant_id)
            results: list[dict[str, Any]] = []
            for tool_name in _HANDLER_TOOLS[intent]:
                if tool_name not in bundle.tools:
                    counters.incr(ISOLATION_TOOL_WHITELIST_VIOLATION)
                    log.warning(
                        "tool.whitelist_violation",
                        tenant_id=str(tenant_id),
                        intent=intent,
                        tool=tool_name,
                    )
                    results.append(
                        {
                            "tool": tool_name,
                            "intent": intent,
                            "status": "skipped:not_in_whitelist",
                        }
                    )
                    continue
                try:
                    payload = get_handler(tool_name)({})
                except ToolError as exc:
                    log.warning("tool.error", tool=tool_name, error=str(exc))
                    results.append(
                        {"tool": tool_name, "intent": intent, "status": "error", "error": str(exc)}
                    )
                    continue
                results.append({"intent": intent, "status": "ok", **payload})
            return {"tool_calls": results}

    return handler


def _summarise_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    if not tool_calls:
        return "(no tools invoked)"
    parts = []
    for call in tool_calls:
        status = call.get("status", "ok")
        tool = call.get("tool", "?")
        parts.append(f"- {tool}: {status}")
    return "\n".join(parts)


def make_respond_node(loader: AgentLoader, llm: LLMRouter) -> NodeFn:
    async def respond(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            bundle = await loader.load(tenant_id)
            tool_calls = state.get("tool_calls") or []
            intent = state.get("intent") or "fallback"
            messages = [
                {"role": "system", "content": bundle.system_prompt},
                {
                    "role": "user",
                    "content": state["user_message"],
                },
                {
                    "role": "system",
                    "content": (
                        f"Intent: {intent}\nTool results:\n{_summarise_tool_calls(tool_calls)}\n"
                        "If a tool reported `skipped:not_in_whitelist`, tell the user the "
                        "capability is not available for this account; do not invent results."
                    ),
                },
            ]
            text = await llm.respond(tenant_id=tenant_id, messages=messages)
            return {"response": text, "response_model": llm.respond_model}

    return respond


def make_checkpoint_node() -> NodeFn:
    """Persist the outbound message in the ``messages`` table.

    The LangGraph checkpointer already records pipeline state under
    ``thread_id``. This node persists the *business* artifact — the assistant's
    reply — that downstream features (operator panel, traces) read. The actual
    WhatsApp send lives in block F.
    """

    async def checkpoint(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await persist_outbound_message(
                session,
                conversation_id=uuid.UUID(state["conversation_id"]),
                content=state.get("response", ""),
                intent=state.get("intent"),
                model=state.get("response_model"),
                tool_calls=state.get("tool_calls") or [],
            )
        return {}

    return checkpoint


# ── Builder ───────────────────────────────────────────────────────────────────


def build_pipeline(
    *,
    agent_loader: AgentLoader,
    llm_router: LLMRouter,
    checkpointer: BaseCheckpointSaver[Any],
) -> Any:
    """Compile the StateGraph and return a runnable.

    Block C never lets a non-whitelisted tool definition reach the LLM —
    handlers gate by ``bundle.tools`` and the LLM is invoked with messages
    only, no tool schemas. When block D enables function-calling, the
    whitelist must also drive the tools= argument passed to LiteLLM; the
    runtime isolation test checks both planes.
    """
    g: Any = StateGraph(AgentState)
    g.add_node("classify", make_classify_node(agent_loader, llm_router))
    for intent in VALID_INTENTS:
        g.add_node(intent, make_handler_node(intent, agent_loader))
    g.add_node("respond", make_respond_node(agent_loader, llm_router))
    g.add_node("checkpoint", make_checkpoint_node())

    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        _route_decider,
        {intent: intent for intent in VALID_INTENTS},
    )
    for intent in VALID_INTENTS:
        g.add_edge(intent, "respond")
    g.add_edge("respond", "checkpoint")
    g.add_edge("checkpoint", END)
    return g.compile(checkpointer=checkpointer)
