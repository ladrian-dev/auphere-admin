"""LangGraph 1.0 pipeline — 8 nodes.

::

    START → classify → route* → {book | queue | info | escalate | fallback}
                                                                 ↓
                                                              respond → checkpoint → END

(*) ``route`` is a conditional edge, not a node, so the node count is exactly
the eight required by the block-C spec: classify, the five handlers, respond
and checkpoint.

Block-D evolution
-----------------

Each handler node became a **tool_loop** (1 iteration). It:

1. Loads the active ``AgentBundle`` and computes ``available =
   whitelist ∩ category_tools[intent]`` — the binding pre-LLM filter for
   garantía 2. The LLM never sees a tool definition outside this set.
2. Calls the LLM with those tool definitions via
   ``LLMRouter.respond_with_tools``. The LLM may emit zero, one or several
   tool calls.
3. Dispatches each emitted call through ``MCPRegistry.dispatch`` which
   re-checks the whitelist (defense in depth — if the LLM hallucinates
   a name out of the filtered set we still refuse and record a
   whitelist violation).
4. Writes the resulting list of envelopes to ``state.tool_calls`` —
   replacing whatever the previous turn left, since the state reducer is
   replace-on-write.

The downstream ``respond`` node summarises the tool results and produces
the final user-visible text. Tools are NOT passed to ``respond`` itself —
the model has already chosen what to invoke.

Tenant context
--------------

Every node enters ``tenant_context(tenant_id)`` before touching repos or
tools. LangGraph backends may move work between threads; the contextvar
set in the orchestrator is not guaranteed to leak in.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog
from langgraph.graph import END, START, StateGraph
from nexus_api.core.metrics import (
    ISOLATION_TOOL_WHITELIST_VIOLATION,
    record_isolation_event,
)
from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_mcp import MCPRegistry, build_default_registry
from nexus_mcp.base import ToolError, ToolNotInWhitelist

from nexus_worker.persistence.messages import persist_outbound_message
from nexus_worker.runtime.agent_loader import AgentBundle, AgentLoader
from nexus_worker.runtime.llm import LLMRouter
from nexus_worker.runtime.state import AgentState
from nexus_worker.runtime.ucm_formatter import (
    format_response_as_ucm,
    shadow_diff_against_legacy,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

NodeFn = Callable[[AgentState], Awaitable[Any]]

log = structlog.get_logger(__name__)


VALID_INTENTS = ("book", "queue", "info", "escalate", "fallback")


# Per-intent tool category. The active whitelist is intersected with this
# set before the LLM ever sees a tool definition. Categories deliberately
# overlap (booking and queue both expose client.* so a returning customer
# can be looked up while booking or queueing).
_INTENT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "book": (
        "booking.check_availability",
        "booking.create_appointment",
        "booking.modify_appointment",
        "booking.cancel_appointment",
        "booking.get_appointments",
        "client.get_preferences",
        "client.update_preferences",
        "client.get_history",
        # ADR-018 — the booking flow on connectors like agendapro_public
        # can't act on cancel / modify without owner approval. The agent
        # consults the owner from this category so the customer sees an
        # immediate ack while the owner answers asynchronously.
        "operator.consult_owner",
    ),
    "queue": (
        "queue.join_queue",
        "queue.get_position",
        "queue.get_estimated_wait",
        "queue.check_in",
        "queue.remove_from_queue",
        "client.get_preferences",
        "client.get_history",
        "operator.consult_owner",
    ),
    "info": (
        "client.get_preferences",
        "client.get_history",
        "booking.get_appointments",
        "commission.get_daily_report",
        # Info questions outside the catalog (custom prices, off-menu
        # services) ask the owner rather than hallucinating.
        "operator.consult_owner",
    ),
    "escalate": (
        "escalate.escalate_to_human",
        "notification.send_template",
        "notification.send_text",
        "operator.consult_owner",
    ),
    "fallback": (),
}


# Notification tools usable from any intent. Phase 1 lets the booking /
# queue / info / escalate handlers send native WhatsApp output (image of
# a price list, audio reply, location pin, reaction). The whitelist
# filtering inside each handler still applies — these names only become
# available when the operator explicitly whitelists them on the tenant's
# agent_config.
_NATIVE_OUTPUT_TOOLS: tuple[str, ...] = (
    "notification.send_image",
    "notification.send_audio",
    "notification.send_video",
    "notification.send_document",
    "notification.send_location",
    "notification.send_reaction",
)
for _intent in ("book", "queue", "info"):
    _INTENT_CATEGORIES[_intent] = _INTENT_CATEGORIES[_intent] + _NATIVE_OUTPUT_TOOLS


def _tenant_uuid(state: AgentState) -> uuid.UUID:
    return uuid.UUID(state["tenant_id"])


def _filter_tools_for_intent(bundle: AgentBundle, intent: str) -> tuple[str, ...]:
    category = _INTENT_CATEGORIES.get(intent, ())
    wl = bundle.tools
    return tuple(t for t in category if t in wl)


def _filter_tools_for_intent_with_composio(bundle: AgentBundle, intent: str) -> tuple[str, ...]:
    """Like :func:`_filter_tools_for_intent` but additionally surfaces
    Composio-backed tools from the whitelist that are not in the static
    category map.

    Composio tools are namespaced by toolkit (``googlecalendar.create_event``,
    ``calendly.list_events``, ``notion.create_page``). We map them onto
    intent buckets by toolkit slug:

    - ``googlecalendar.*`` / ``calendly.*``  → ``book`` + ``info`` (scheduling)
    - ``notion.*`` / ``googledrive.*`` / ``googlesheets.*`` → ``info``
    - ``gmail.*``                            → ``escalate`` (operator email)

    Tools whose slug doesn't match a known prefix default to ``info``
    so the LLM can at least call them in a Q&A context.
    """
    base = _filter_tools_for_intent(bundle, intent)
    base_set = set(base)
    extras: list[str] = []
    for t in bundle.tools:
        if t in base_set:
            continue
        if "." not in t:
            continue
        toolkit, _action = t.split(".", 1)
        if (
            (toolkit in {"googlecalendar", "calendly"} and intent in {"book", "info"})
            or (toolkit in {"notion", "googledrive", "googlesheets"} and intent == "info")
            or (toolkit == "gmail" and intent == "escalate")
        ) or (
            intent == "info"
            and toolkit
            not in {
                "booking",
                "queue",
                "client",
                "commission",
                "escalate",
                "notification",
                "operator",
                "agendapro",
            }
        ):
            extras.append(t)
    return base + tuple(extras)


async def _view_with_composio(
    *,
    registry: MCPRegistry,
    tenant_id: uuid.UUID,
    available_names: tuple[str, ...],
) -> tuple[MCPRegistry, tuple[str, ...]]:
    """Return a (registry view, allowed_names) pair that includes any
    Composio-backed proxies for this tenant.

    The returned MCPRegistry shares the global static tools but layers
    per-turn proxies on top. ``available_names`` is unchanged when no
    proxies exist — most turns hit zero Composio tools.
    """
    # Tools the static registry already knows; we only need to
    # materialise proxies for the *missing* names.
    static_names = set(registry.names())
    candidates = tuple(n for n in available_names if n not in static_names)
    if not candidates:
        return registry, available_names

    from nexus_mcp.servers.composio_proxy import (
        build_composio_proxies_for_tenant,
        load_blueprints_for_tenant,
    )

    blueprints = await load_blueprints_for_tenant(tenant_id, whitelist=frozenset(candidates))
    if not blueprints:
        return registry, available_names

    proxies = build_composio_proxies_for_tenant(blueprints)
    # Materialise a fresh registry view: copy the static tools and add
    # the per-turn proxies. Cheaper than a global registry mutation,
    # which would race with concurrent turns of other tenants.
    view = MCPRegistry()
    for name in registry.names():
        # Re-register the existing instance under the new view.
        view._tools[name] = registry._tools[name]
    for name in registry.internal_names():
        view._internal_tools[name] = registry._internal_tools[name]
    for proxy in proxies:
        view._tools[proxy.name] = proxy
    return view, available_names


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


def make_handler_node(
    intent: str,
    loader: AgentLoader,
    llm: LLMRouter,
    registry: MCPRegistry,
) -> NodeFn:
    """Build the tool_loop node for ``intent``.

    Pre-LLM filter: only tools in ``whitelist ∩ category[intent]`` are
    passed to the LLM. If the LLM hallucinates a name outside that set,
    ``MCPRegistry.dispatch`` raises ``ToolNotInWhitelist`` and the node
    records a ``skipped:not_in_whitelist`` envelope without firing the
    side effects.

    Block N: in addition to the static (in-process) tools we ask the
    Composio runtime for any per-tenant proxies whose names are in the
    whitelist ∩ category[intent]. The proxies are materialised once per
    turn and merged into a tenant-scoped registry view via
    :func:`_view_with_composio` so dispatch can find them.
    """

    async def handler(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            bundle: AgentBundle = await loader.load(tenant_id)
            available_names = _filter_tools_for_intent_with_composio(bundle, intent)
            # The Composio proxies for the tools in ``available_names``.
            # The view merges them with the global static registry.
            scoped_registry, available_names = await _view_with_composio(
                registry=registry,
                tenant_id=tenant_id,
                available_names=available_names,
            )
            available_defs = scoped_registry.get_openai_tools(available_names)

            # Empty intersection (e.g. fallback) → skip the LLM call and
            # leave tool_calls empty. The respond node will produce a
            # "I can't help with that" answer.
            if not available_defs:
                return {"tool_calls": []}

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": bundle.system_prompt},
                {
                    "role": "system",
                    "content": (
                        f"You may invoke ONLY the tools listed in this turn. Intent: "
                        f"{intent}. Pick the tools needed to answer the user, then return."
                    ),
                },
            ]
            addendum = state.get("system_addendum") or ""
            if addendum:
                messages.append({"role": "system", "content": addendum})
            messages.append({"role": "user", "content": state["user_message"]})
            response = await llm.respond_with_tools(
                tenant_id=tenant_id,
                role=intent,
                messages=messages,
                tools=available_defs,
            )

            results: list[dict[str, Any]] = []
            for call in response.tool_calls:
                try:
                    envelope = await scoped_registry.dispatch(
                        call.name,
                        dict(call.arguments),
                        whitelist=available_names,
                    )
                    envelope["intent"] = intent
                    results.append(envelope)
                except ToolNotInWhitelist:
                    # The pre-LLM filter should have prevented this; the
                    # registry already incremented ISOLATION_TOOL_WHITELIST_VIOLATION.
                    results.append(
                        {
                            "tool": call.name,
                            "intent": intent,
                            "status": "skipped:not_in_whitelist",
                        }
                    )
                except ToolError as exc:
                    log.warning(
                        "tool.error",
                        tool=call.name,
                        intent=intent,
                        error=str(exc),
                    )
                    results.append(
                        {
                            "tool": call.name,
                            "intent": intent,
                            "status": "error",
                            "error": str(exc),
                        }
                    )

            # If the LLM emitted no tool_calls but the intent has a
            # category, that's fine — sometimes the model just answers
            # directly. ``respond`` picks up the empty list.
            return {"tool_calls": results}

    return handler


# Sentinel used by tests when the LLM emits a name we WANT to leak through
# in a hostile scenario. The pipeline still rejects via dispatch.
def _record_pre_llm_violation(name: str, tenant_id: uuid.UUID) -> None:  # pragma: no cover
    record_isolation_event(
        ISOLATION_TOOL_WHITELIST_VIOLATION,
        tenant_id,
        {"tool": name, "site": "pre_llm"},
    )
    log.warning(
        "tool.whitelist_violation_pre_llm",
        tenant_id=str(tenant_id),
        tool=name,
    )


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
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": bundle.system_prompt},
            ]
            addendum = state.get("system_addendum") or ""
            if addendum:
                messages.append({"role": "system", "content": addendum})
            messages.extend(
                [
                    {"role": "user", "content": state["user_message"]},
                    {
                        "role": "system",
                        "content": (
                            f"Intent: {intent}\nTool results:\n{_summarise_tool_calls(tool_calls)}\n"
                            "If a tool reported `skipped:not_in_whitelist`, tell the user the "
                            "capability is not available for this account; do not invent results."
                        ),
                    },
                ]
            )
            text = await llm.respond(tenant_id=tenant_id, messages=messages)
            return {"response": text, "response_model": llm.respond_model}

    return respond


def make_ucm_formatter_node(*, enabled: bool) -> NodeFn:
    """Phase 2 (ADR-020): wrap the agent's text response in a UCM payload.

    When the feature flag is off this is a no-op passthrough — that lets us
    ship the node into the graph wiring without changing behaviour, and
    flip the flag per environment when shadow validation is ready.

    When enabled it produces:
      - ``state["ucm"]`` — a validated UCM v1.0.0 dict (today always
        ``type: "text"``; will grow per ADR-020 as the agent emits
        structured replies).
      - ``state["ucm_shadow_diff"]`` — a comparison record between the
        channel-degraded UCM and the legacy ``state["response"]``, used
        to gate promotion to source-of-truth (target: diff_ratio < 0.01
        over 7 days, per the feature spec).
    """

    async def ucm_formatter(state: AgentState) -> dict[str, Any]:
        if not enabled:
            return {}

        response_text = state.get("response", "") or ""
        # Reuse the inbound_message_id as a stable correlation id for the
        # UCM so traces / future shadow tables can join cleanly. If the
        # state shape ever omits it (it shouldn't — ``new_state`` always
        # sets it), the formatter still produces a fresh UUID.
        seed_id = state.get("inbound_message_id") or None
        ucm = format_response_as_ucm(
            response_text=response_text,
            message_id=seed_id,
            metadata={
                "tenant_id": state.get("tenant_id"),
                "conversation_id": state.get("conversation_id"),
                "intent": state.get("intent"),
                "phase": "shadow",  # not source-of-truth yet
            },
        )
        diff = shadow_diff_against_legacy(ucm, response_text, channel="whatsapp")

        if not diff["equivalent"]:
            # Loud structured log so we notice regressions immediately —
            # the formatter is meant to be byte-equivalent to the legacy
            # text path until the agent starts emitting structured content.
            log.warning(
                "ucm_shadow_diff_nonzero",
                tenant_id=state.get("tenant_id"),
                conversation_id=state.get("conversation_id"),
                diff_ratio=diff["diff_ratio"],
                degraded_type=diff["degraded_type"],
                steps=diff["steps"],
            )

        return {
            "ucm": ucm.model_dump(mode="json"),
            "ucm_shadow_diff": diff,
        }

    return ucm_formatter


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
    mcp_registry: MCPRegistry | None = None,
    use_ucm_formatter: bool | None = None,
) -> Any:
    """Compile the StateGraph and return a runnable.

    ``mcp_registry`` defaults to ``nexus_mcp.build_default_registry()``;
    tests can pass a stripped-down registry.

    ``use_ucm_formatter`` controls Phase 2 of ADR-020. When ``None`` (the
    default) the flag is read from ``settings.use_ucm_formatter`` so
    deployment toggles work without code changes; tests pass an explicit
    bool. When True a ``ucm_formatter`` node is inserted between
    ``respond`` and ``checkpoint``.
    """
    registry = mcp_registry or build_default_registry()

    if use_ucm_formatter is None:
        # Read at compile time. Re-importing in the function keeps the
        # config dependency local — pipeline.py stays callable from
        # tests that stub out settings.
        from nexus_api.config import get_settings

        use_ucm_formatter = bool(get_settings().use_ucm_formatter)

    g: Any = StateGraph(AgentState)
    g.add_node("classify", make_classify_node(agent_loader, llm_router))
    for intent in VALID_INTENTS:
        g.add_node(intent, make_handler_node(intent, agent_loader, llm_router, registry))
    g.add_node("respond", make_respond_node(agent_loader, llm_router))
    g.add_node("ucm_formatter", make_ucm_formatter_node(enabled=use_ucm_formatter))
    g.add_node("checkpoint", make_checkpoint_node())

    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        _route_decider,
        {intent: intent for intent in VALID_INTENTS},
    )
    for intent in VALID_INTENTS:
        g.add_edge(intent, "respond")
    g.add_edge("respond", "ucm_formatter")
    g.add_edge("ucm_formatter", "checkpoint")
    g.add_edge("checkpoint", END)
    return g.compile(checkpointer=checkpointer)
