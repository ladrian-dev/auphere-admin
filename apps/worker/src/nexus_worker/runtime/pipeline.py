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


# Every tool name the static (vertical) intent map routes — the union of all
# category tuples after the native-output tools are merged in. A tool in the
# agent's whitelist that is NOT in this set belongs to an installed connector
# (WooCommerce, Composio, …), not the vertical. See bug #11.
_NATIVE_TOOL_NAMES: frozenset[str] = frozenset(
    name for names in _INTENT_CATEGORIES.values() for name in names
)

# Intents on which connector tools are offered to the LLM. Connector tools
# are not vertical-specific so the intent map has no opinion on them; they
# surface on every intent that does real work. ``escalate`` is excluded — an
# escalation hands off to a human, it does not browse a catalog.
_CONNECTOR_TOOL_INTENTS: frozenset[str] = frozenset({"book", "queue", "info", "fallback"})


def _tenant_uuid(state: AgentState) -> uuid.UUID:
    return uuid.UUID(state["tenant_id"])


def _filter_tools_for_intent(bundle: AgentBundle, intent: str) -> tuple[str, ...]:
    category = _INTENT_CATEGORIES.get(intent, ())
    wl = bundle.tools
    return tuple(t for t in category if t in wl)


def _filter_tools_for_intent_with_composio(bundle: AgentBundle, intent: str) -> tuple[str, ...]:
    """Tools the LLM may see this turn: the vertical's intent category PLUS
    any connector tools from the agent's whitelist.

    The static ``_INTENT_CATEGORIES`` map only routes the vertical's native
    tools (booking, queue, …). Connector tools belong to an installed
    connector, not the vertical — the operator already authorised them on
    the agent_config, so the intent map must not silently drop them. There
    are two kinds:

    - **Namespaced (Composio)** — ``notion.create_page``, ``gmail.send`` …
      routed by toolkit slug, unchanged from the original behaviour so an
      existing barbershop tenant sees no difference.
    - **Un-namespaced** — the WooCommerce read tools ``list_products`` /
      ``get_product`` etc. carry no toolkit slug. These were silently
      dropped before (bug #11): the agent had them whitelisted but the
      runtime never offered them to the LLM. They now surface on every
      working intent (see ``_CONNECTOR_TOOL_INTENTS``).

    The whitelist (``bundle.tools``) stays the hard ceiling: this only ever
    iterates names already in it, and ``MCPRegistry.dispatch`` re-checks the
    whitelist post-LLM as defence in depth (garantía 2).
    """
    base = _filter_tools_for_intent(bundle, intent)
    base_set = set(base)
    extras: list[str] = []
    for t in bundle.tools:
        if t in base_set or t in _NATIVE_TOOL_NAMES:
            # Already offered, or a native vertical tool the intent map
            # deliberately scoped out of this intent — leave it as is.
            continue
        if "." not in t:
            # Un-namespaced connector tool (WooCommerce ``list_products`` …).
            # No toolkit slug to route by; surface on every working intent.
            if intent in _CONNECTOR_TOOL_INTENTS:
                extras.append(t)
            continue
        # Namespaced (Composio) connector tool — keep the original
        # toolkit-slug routing so existing tenants see no change.
        toolkit = t.split(".", 1)[0]
        if (
            intent == "info"
            or (toolkit in {"googlecalendar", "calendly"} and intent == "book")
            or (toolkit == "gmail" and intent == "escalate")
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
            history = await _load_recent_history(
                tenant_id,
                state.get("conversation_id"),
                exclude_message_id=state.get("inbound_message_id"),
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Classify the LATEST user message into exactly one of: "
                        + ", ".join(VALID_INTENTS)
                        + ". Earlier turns are context only. Respond with the "
                        "single label."
                    ),
                },
                *history,
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

            history = await _load_recent_history(
                tenant_id,
                state.get("conversation_id"),
                exclude_message_id=state.get("inbound_message_id"),
            )
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
            messages.extend(history)
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


async def _load_kg_snapshot_text(tenant_id: uuid.UUID) -> str:
    """Render a compact, LLM-friendly snapshot of the tenant's KG.

    The agent's system_prompt repeatedly says "use the knowledge graph"
    and "never invent prices / barbers / services". Without the snapshot
    in context the model has no choice — it hallucinates. We load
    ``kg_nodes`` once per turn (cheap, tenant-scoped, ≤ a few hundred
    rows) and serialise as a Markdown-ish block grouped by label.

    Returns an empty string when the KG is empty so the respond node
    can skip the system message entirely.

    Tradeoff: this scales linearly with the KG. For tenants with >>200
    nodes we'll graduate to a real ``kg.lookup`` tool (filter by
    label + free-text). Cheap enough for the pilot.
    """
    from nexus_api.db.models import KGNode
    from sqlalchemy import select as _select

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            (
                await session.execute(
                    _select(KGNode).order_by(KGNode.label.asc(), KGNode.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return ""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault(r.label, []).append(r.properties or {})

    parts: list[str] = ["Knowledge graph (current facts — never contradict these):"]
    for label, items in sorted(grouped.items()):
        parts.append(f"\n[{label}]")
        for it in items:
            # Each node = its properties as `key: value` pairs. Skip
            # null / empty / private-looking keys.
            keys = [
                f"{k}={_format_kg_value(v)}"
                for k, v in it.items()
                if v not in (None, "", [], {}) and not str(k).startswith("_")
            ]
            if keys:
                parts.append("- " + " · ".join(keys))
    return "\n".join(parts)


def _format_kg_value(v: Any) -> str:
    """Compact value formatter — keeps the snapshot under control."""
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}:{vv}" for k, vv in v.items()) + "}"
    return str(v)


async def _load_recent_history(
    tenant_id: uuid.UUID,
    conversation_id: str | None,
    *,
    exclude_message_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Load the recent turns of a conversation as LLM ``messages``.

    Without this the agent's nodes see only the current ``user_message`` —
    the agent has no memory: it re-greets every turn and loses context
    across turns (bug #10). We read the last ``limit`` rows of ``messages``
    for the conversation (tenant-scoped, RLS-enforced), oldest-first,
    mapping inbound → ``user`` and outbound → ``assistant``.

    ``exclude_message_id`` drops the current inbound row — it is persisted
    before the graph runs, and the caller appends the live ``user_message``
    itself. Returns ``[]`` when there is no conversation yet (first turn),
    so the single-turn path is unchanged.
    """
    if not conversation_id:
        return []
    from nexus_api.db.models import Message, MessageDirection
    from sqlalchemy import select as _select

    conv_uuid = uuid.UUID(conversation_id)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            (
                await session.execute(
                    _select(Message)
                    .where(Message.conversation_id == conv_uuid)
                    .order_by(Message.created_at.desc())
                    .limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )

    history: list[dict[str, str]] = []
    for m in reversed(rows):  # DB gave newest-first; replay oldest-first
        if exclude_message_id and str(m.id) == exclude_message_id:
            continue
        content = (m.content or "").strip()
        if not content:
            continue
        role = "user" if m.direction == MessageDirection.INBOUND else "assistant"
        history.append({"role": role, "content": content})
    return history[-limit:]


def _channel_format_note(channel: str) -> str:
    """A system instruction telling the model how to format for the channel.

    The agent's system_prompt should not hardcode channel-specific markup
    (bug #12). The turn carries ``channel_type`` in state; this note is
    appended so the same agent renders correctly on WhatsApp and on the web
    QA chat without a prompt rewrite per channel.
    """
    if channel == "whatsapp":
        return (
            "Output channel: WhatsApp. Use WhatsApp formatting only — "
            "*bold*, _italic_, ~strikethrough~. Never use Markdown headers, "
            "tables, or **double-asterisk** bold."
        )
    return (
        "Output channel: web chat. Use standard Markdown — **bold**, "
        "_italic_, `-` bullet lists. Do NOT use WhatsApp-style single-"
        "asterisk *bold*; it renders as literal asterisks here."
    )


def make_respond_node(loader: AgentLoader, llm: LLMRouter) -> NodeFn:
    async def respond(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            bundle = await loader.load(tenant_id)
            tool_calls = state.get("tool_calls") or []
            intent = state.get("intent") or "fallback"
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": bundle.system_prompt},
                {
                    "role": "system",
                    "content": _channel_format_note(state.get("channel_type") or "whatsapp"),
                },
            ]
            kg_snapshot = await _load_kg_snapshot_text(tenant_id)
            if kg_snapshot:
                messages.append({"role": "system", "content": kg_snapshot})
            addendum = state.get("system_addendum") or ""
            if addendum:
                messages.append({"role": "system", "content": addendum})
            history = await _load_recent_history(
                tenant_id,
                state.get("conversation_id"),
                exclude_message_id=state.get("inbound_message_id"),
            )
            messages.extend(history)
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
        # Degrade for the channel this turn actually runs on. Production
        # turns are WhatsApp; QA Playground turns run on a "web" channel.
        # Falls back to "whatsapp" for callers that predate ``channel_type``.
        channel = state.get("channel_type") or "whatsapp"
        diff = shadow_diff_against_legacy(ucm, response_text, channel=channel)

        if not diff["equivalent"]:
            # Loud structured log so we notice regressions immediately —
            # the formatter is meant to be byte-equivalent to the legacy
            # text path until the agent starts emitting structured content.
            log.warning(
                "ucm_shadow_diff_nonzero",
                tenant_id=state.get("tenant_id"),
                conversation_id=state.get("conversation_id"),
                channel=channel,
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
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    mcp_registry: MCPRegistry | None = None,
    use_ucm_formatter: bool | None = None,
) -> Any:
    """Compile the StateGraph and return a runnable.

    ``checkpointer`` is optional: when ``None`` the compiled graph leaves
    persistence to whichever host runs it. Tests pass ``MemorySaver`` for
    deterministic state. The LangGraph Server (apps/qa-langgraph-server/)
    must pass ``None`` because the platform manages persistence and
    rejects custom checkpointers at startup since langgraph-api 0.8.x.

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
    if checkpointer is None:
        return g.compile()
    return g.compile(checkpointer=checkpointer)
