"""LangGraph 1.0 pipeline — the agent runtime.

::

    START → classify → route* → {book | queue | info | escalate | fallback}
                                                         ↓
                                              ucm_formatter → checkpoint → END

(*) ``route`` is a conditional edge, not a node.

ADR-023 — the ReAct loop
------------------------

Before ADR-023 the graph had a separate ``respond`` node that regenerated
the final answer from a *text summary* of the tool calls — it never saw
the actual tool results. That made every read tool decorative: the agent
invoked it, the data came back, and the LLM that wrote to the customer
never saw it.

Now each handler node is a **real ReAct loop**:

1. Load the active ``AgentBundle`` and compute ``available = whitelist ∩
   category[intent]`` — the binding pre-LLM filter for garantía 2. The LLM
   never sees a tool definition outside this set.
2. Build the message thread (system prompt + channel note + KG snapshot +
   conversation history + the user's message).
3. Loop up to ``MAX_TOOL_ITERATIONS``:
   - Call the LLM with the tool definitions.
   - If it requests no tools → that text is the final answer; stop.
   - Otherwise dispatch each call through ``MCPRegistry.dispatch`` (which
     re-checks the whitelist — defense in depth), and append the **real
     result** back into the thread as a ``role: "tool"`` message so the
     next iteration can use it.
   - The last iteration is forced tool-free so the model must produce text.
4. Write the final text to ``state["response"]`` and the accumulated tool
   envelopes to ``state["tool_calls"]``.

There is no longer a blind ``respond`` node — the loop produces the final
user-visible text itself, with every tool result in context.

Tenant context
--------------

Every node enters ``tenant_context(tenant_id)`` before touching repos or
tools. LangGraph backends may move work between threads; the contextvar
set in the orchestrator is not guaranteed to leak in.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog
from langgraph.graph import END, START, StateGraph
from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_mcp import MCPRegistry, build_default_registry
from nexus_mcp.base import ToolError, ToolNotInWhitelist

from nexus_worker.guardrails import (
    GRADER_FALLBACK_RESPONSE,
    OutcomeGrader,
    load_rubric_text,
)
from nexus_worker.guardrails.outcome_grader import MAX_GRADER_RETRIES
from nexus_worker.mcp_connector import build_mcp_extra
from nexus_worker.memory import (
    MEMORY_TOOL_SYSTEM_PROMPT,
    NexusPostgresMemoryTool,
)
from nexus_worker.persistence.messages import persist_outbound_message
from nexus_worker.runtime.agent_loader import AgentBundle, AgentLoader
from nexus_worker.runtime.llm import LLMResponse, LLMRouter, ToolCall
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

# Hard cap on the handler's ReAct loop. Without it a model that keeps
# requesting tools would loop forever and burn cost (Anthropic, OpenAI and
# Vercel all mandate an explicit iteration cap). The final iteration is
# always forced tool-free so the model must produce a user-visible answer.
MAX_TOOL_ITERATIONS = 6

# Tool results are fed back into the LLM context verbatim. A pathological
# result (e.g. a catalog dump of hundreds of products) would blow the
# context window, so we truncate. Anthropic recommends bounding tool
# output; this is the cheap version of that.
_TOOL_RESULT_CHAR_CAP = 8_000

# Safety net: the loop must always yield SOME text. If the model returns an
# empty final answer we surface a neutral message instead of sending the
# customer an empty WhatsApp.
_EMPTY_RESPONSE_FALLBACK = (
    "Disculpá, tuve un inconveniente para completar la respuesta. "
    "¿Podés intentarlo de nuevo en un momento?"
)


# Anthropic Memory tool name. The model emits ``tool_call.name == "memory"``
# (set by ``BetaAsyncAbstractMemoryTool.to_dict()``) and the handler routes
# directly to the tool instance, bypassing the MCP registry — built-in
# tools have their own scoping (the tool instance carries tenant_id +
# customer_id) and the ``tool_result`` is a string, not the MCP envelope.
# See architecture/builtin-tools-vs-mcp-tools.md.
_MEMORY_TOOL_NAME = "memory"


# Fase D — Anthropic custom Skills wiring.
#
# When ``agent_config.runtime_skills`` is non-empty for a turn, the handler:
#   1. Appends the ``code_execution`` tool to ``tools[]`` — required
#      because Skills are loaded into the code-execution container.
#   2. Passes ``container={"skills": [{type, skill_id, version}, …]}``
#      to the provider via the ``extra`` kwarg.
#   3. Adds the three beta headers Anthropic requires for the
#      Skills + code-execution + files-api stack.
#
# These names + versions are the contract Anthropic published; they
# are NOT environment-configurable on purpose — bumping them would be
# a deliberate review-gated change.
_CODE_EXECUTION_TOOL: dict[str, Any] = {
    "type": "code_execution_20250825",
    "name": "code_execution",
}
_SKILLS_BETA_HEADER_VALUE: str = (
    "code-execution-2025-08-25,skills-2025-10-02,files-api-2025-04-14"
)


def _filter_skills_for_channel(
    skills: tuple[dict[str, Any], ...],
    channel_type: str,
) -> tuple[dict[str, Any], ...]:
    """Drop skills whose ``channels`` gate excludes the active channel.

    A skill without ``channels`` (or empty tuple) loads for every
    channel — back-compat with skills uploaded before the gate existed.
    A skill with non-empty ``channels`` only loads when ``channel_type``
    is in the list, so e.g. ``whatsapp-24h-window`` never reaches the
    LLM on the QA Playground ``web`` channel.
    """
    return tuple(
        s
        for s in skills
        if not s.get("channels") or channel_type in s["channels"]
    )


async def _resolve_mcp_token(tenant_id: uuid.UUID, credential_key: str) -> str | None:
    """Read ``tenant_credentials`` and return the decrypted OAuth token.

    ``credential_key`` matches ``tenant_credentials.integration`` for
    the row that holds the OAuth payload. Composio remains the SoT of
    credentials; this resolver only reads the bearer token from the
    table the rest of the worker already trusts.

    Returns ``None`` when the row is missing or flagged
    ``needs_reauth`` — the MCP connector module then skips this
    server and the model continues with whatever else is available.
    """
    if not credential_key:
        return None
    from nexus_api.db.models import TenantCredentials
    from sqlalchemy import select as _select

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                _select(TenantCredentials).where(
                    TenantCredentials.integration == credential_key
                )
            )
        ).scalar_one_or_none()
    if row is None or row.needs_reauth:
        return None
    # ``encrypted_payload`` is Fernet-decoded by the type decorator; the
    # plaintext is either the raw bearer or a JSON envelope. We accept
    # both: a JSON dict with ``access_token`` wins, otherwise we treat
    # the bytes as the token verbatim.
    try:
        payload = row.encrypted_payload.decode("utf-8")
    except Exception:
        return None
    payload = payload.strip()
    if payload.startswith("{"):
        try:
            data = json.loads(payload)
            token = data.get("access_token")
            if isinstance(token, str) and token:
                return token
            return None
        except json.JSONDecodeError:
            return None
    return payload or None


# Map nexus' coarse classifier intent → the rubric-specific intent name.
# The Nexus classifier returns one of VALID_INTENTS (book/queue/info/
# escalate/fallback); rubrics are written per business action
# (booking.confirm, ecommerce.product_recommend, …). For Fase C we
# pick the most likely match per coarse intent — the rubrics
# themselves are forgiving (booking_confirm passes tentative language,
# which is exactly what a "book" turn without a tool result should
# emit). When the pilots reveal we need finer routing we either add a
# secondary classifier OR extend the agent_config to carry a per-intent
# override.
_NEXUS_INTENT_TO_RUBRIC: dict[str, str] = {
    "book": "booking.confirm",
    "queue": "default.general_response",
    "info": "default.general_response",
    "escalate": "default.general_response",
    "fallback": "default.general_response",
}


# Internal system message used to ask the agent for a corrected response
# after the grader fails. Anthropic's pattern is to insert a ``user``
# turn that frames the correction; we go one step further and surface
# the grader feedback explicitly so the agent has actionable guidance.
_RETRY_SYSTEM_TEMPLATE: str = (
    "Your previous reply did not pass output validation. Reason: "
    "{feedback}\n"
    "Rewrite the reply addressing the reason ABOVE. Do not invent "
    "data; if a tool result is missing, say so honestly. Reply with "
    "only the corrected message — no preface, no apology to the QA."
)


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
#
# ``response.send_interactive`` joins the set as the terminal
# component-emitter — it produces native reply buttons / list / CTA URL.
# Surfacing on the same intents keeps the LLM's tool palette consistent:
# wherever it could send media, it can also send a structured component.
_NATIVE_OUTPUT_TOOLS: tuple[str, ...] = (
    "notification.send_image",
    "notification.send_audio",
    "notification.send_video",
    "notification.send_document",
    "notification.send_location",
    "notification.send_reaction",
    "response.send_interactive",
)
for _intent in ("book", "queue", "info"):
    _INTENT_CATEGORIES[_intent] = _INTENT_CATEGORIES[_intent] + _NATIVE_OUTPUT_TOOLS


# Name of the terminal interactive tool — kept as a module constant so
# the handler loop and the tests can share the literal without drifting.
_INTERACTIVE_TOOL_NAME = "response.send_interactive"


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
    """Cheap router: pick the intent and load the conversation history once.

    ``classify`` is intentionally kept as a pre-step (ADR-023): it routes to
    the right handler — and therefore the right tool sub-set, the runtime
    plane of garantía 2 — and it loads ``history`` a single time so the
    handler does not have to re-query the DB.
    """

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
            try:
                raw = await llm.classify(tenant_id=tenant_id, messages=messages)
            except Exception as exc:
                # The router already retried + fell back. If it still
                # failed, route to ``fallback`` so the turn completes with
                # a graceful reply instead of leaving the message stuck.
                log.error("classify.llm_failed", tenant_id=str(tenant_id), error=str(exc))
                raw = ""
            intent = (raw or "").strip().lower()
            if intent not in VALID_INTENTS:
                log.info("classify.unknown_label_using_fallback", raw=raw)
                intent = "fallback"
            return {"intent": intent, "route": intent, "history": history}

    return classify


def _route_decider(state: AgentState) -> str:
    return state.get("route") or "fallback"


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


def _build_handler_messages(
    state: AgentState,
    bundle: AgentBundle,
    *,
    intent: str,
    kg_snapshot: str,
) -> list[dict[str, Any]]:
    """Assemble the base message thread for the handler's ReAct loop.

    Order: system prompt → channel note → KG snapshot → owner addendum →
    a turn directive → conversation history → the user's message. The loop
    appends assistant/tool messages onto this list as it iterates.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": bundle.system_prompt},
        {
            "role": "system",
            "content": _channel_format_note(state.get("channel_type") or "whatsapp"),
        },
    ]
    if kg_snapshot:
        messages.append({"role": "system", "content": kg_snapshot})
    addendum = state.get("system_addendum") or ""
    if addendum:
        messages.append({"role": "system", "content": addendum})
    messages.append(
        {
            "role": "system",
            "content": (
                f"Intent of this turn: {intent}. Use the tools available this turn "
                "to gather any real data you need — availability, prices, products, "
                "the customer's history — BEFORE answering. Never invent data that a "
                "tool can provide. If a tool result reports the capability is "
                "unavailable or failed, tell the customer plainly; do not fabricate "
                "a result."
            ),
        }
    )
    messages.extend(state.get("history") or [])
    messages.append({"role": "user", "content": state["user_message"]})
    return messages


def _assistant_tool_message(response: LLMResponse) -> dict[str, Any]:
    """The assistant message recording the tool calls the model just made,
    in the OpenAI/LiteLLM shape, so the next request shows the model its own
    previous output before the tool results."""
    return {
        "role": "assistant",
        "content": response.text or "",
        "tool_calls": [
            {
                "id": tc.id or tc.name,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in response.tool_calls
        ],
    }


def _tool_result_content(envelope: dict[str, Any]) -> str:
    """Render a tool envelope as the ``content`` of a ``role: "tool"``
    message. The whole point of ADR-023: the real result reaches the LLM."""
    status = envelope.get("status", "ok")
    if status == "skipped:not_in_whitelist":
        return (
            "ERROR: this capability is not enabled for this account. Do NOT "
            "invent a result — tell the customer the capability is unavailable."
        )
    if status == "error":
        return (
            f"ERROR: the tool failed ({envelope.get('error', 'unknown error')}). "
            "Do NOT invent a result — tell the customer it could not be completed."
        )
    result = envelope.get("result", {})
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(result)
    if len(text) > _TOOL_RESULT_CHAR_CAP:
        text = text[:_TOOL_RESULT_CHAR_CAP] + " …[truncated]"
    return text


async def _dispatch_memory_tool(
    memory_tool: NexusPostgresMemoryTool,
    call: ToolCall,
    intent: str,
) -> tuple[dict[str, Any], str]:
    """Dispatch a ``memory`` tool_call to the built-in handler.

    Returns ``(envelope, tool_message_content)``:

    - ``envelope`` is the trace record we accumulate in
      ``state["tool_calls"]`` so observability / shadow diff still see
      the operation. The shape mirrors the MCP envelope so downstream
      consumers don't need a special case.
    - ``tool_message_content`` is the string the LLM expects as
      ``tool_result`` content — Anthropic's documented format.

    The tool's own error handling already returns a string in BOTH
    success and recoverable-error cases (path traversal, "does not
    exist", "memory full"); only an unexpected exception ends up here
    as ``status="error"``.
    """
    try:
        result_content = await memory_tool.call(call.arguments)
    except Exception as exc:  # pragma: no cover — defence in depth
        log.exception(
            "memory.unhandled_exception",
            intent=intent,
            error=str(exc),
        )
        message = (
            "Memory operation failed unexpectedly. Tell the customer the "
            "operation could not be completed; do NOT invent a result."
        )
        envelope = {
            "tool": _MEMORY_TOOL_NAME,
            "intent": intent,
            "status": "error",
            "error": str(exc),
            "result": {},
        }
        return envelope, message

    # Memory tool result content is a string by contract (the SDK type is
    # ``str | list[content blocks]``; our subclass always returns str).
    text = result_content if isinstance(result_content, str) else str(result_content)
    envelope = {
        "tool": _MEMORY_TOOL_NAME,
        "intent": intent,
        "status": "ok",
        # Persist the command for traceability — the operator panel and
        # Langfuse traces can show what the agent did with memory.
        "result": {
            "command": call.arguments.get("command") if isinstance(call.arguments, dict) else None,
            "path": call.arguments.get("path") if isinstance(call.arguments, dict) else None,
            "summary": text[:200],  # avoid blowing up traces with long files
        },
    }
    return envelope, text


async def _dispatch_tool(
    registry: MCPRegistry,
    call: ToolCall,
    available_names: tuple[str, ...],
    intent: str,
) -> dict[str, Any]:
    """Dispatch one tool call, returning an envelope no matter what.

    The pre-LLM filter should have prevented a non-whitelisted name, but the
    registry re-checks (defense in depth — garantía 2). A whitelist
    violation or a tool error becomes an envelope with a non-``ok`` status
    so the loop can feed the failure back to the model instead of crashing
    the turn.
    """
    try:
        envelope: dict[str, Any] = await registry.dispatch(
            call.name, dict(call.arguments), whitelist=available_names
        )
        envelope["intent"] = intent
        return envelope
    except ToolNotInWhitelist:
        # The registry already incremented ISOLATION_TOOL_WHITELIST_VIOLATION.
        return {
            "tool": call.name,
            "intent": intent,
            "status": "skipped:not_in_whitelist",
            "result": {},
        }
    except ToolError as exc:
        log.warning("tool.error", tool=call.name, intent=intent, error=str(exc))
        return {
            "tool": call.name,
            "intent": intent,
            "status": "error",
            "error": str(exc),
            "result": {},
        }


def make_handler_node(
    intent: str,
    loader: AgentLoader,
    llm: LLMRouter,
    registry: MCPRegistry,
) -> NodeFn:
    """Build the ReAct-loop node for ``intent`` (ADR-023).

    The node loops: call the LLM with the whitelist-filtered tools, dispatch
    whatever it requests, feed the real results back into the thread, and
    repeat until the model answers without requesting a tool — or the
    ``MAX_TOOL_ITERATIONS`` cap is hit. The final iteration is forced
    tool-free so the model must produce text. The node writes the final
    text to ``state["response"]`` directly; there is no separate respond
    node anymore.

    Block N: in addition to the static (in-process) tools we ask the
    Composio runtime for any per-tenant proxies whose names are in the
    whitelist ∩ category[intent], merged into a tenant-scoped registry view.
    """

    async def handler(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            bundle: AgentBundle = await loader.load(tenant_id)
            available_names = _filter_tools_for_intent_with_composio(bundle, intent)
            scoped_registry, available_names = await _view_with_composio(
                registry=registry,
                tenant_id=tenant_id,
                available_names=available_names,
            )
            available_defs = scoped_registry.get_openai_tools(available_names)
            kg_snapshot = await _load_kg_snapshot_text(tenant_id)
            messages = _build_handler_messages(
                state, bundle, intent=intent, kg_snapshot=kg_snapshot
            )

            # Built-in Anthropic Memory tool (Fase B). Opt-in per
            # agent_config via the ``runtime_memory_tool`` boolean —
            # activation travels with the config through STAGED →
            # ACTIVE, so turning it on is auditable and rollback is
            # atomic. The instance carries this turn's (tenant_id,
            # customer_id); the LLM sees a tool spec
            # ``{"type": "memory_20250818", "name": "memory"}`` but
            # never the customer_id itself (paths use the "me" alias).
            memory_tool: NexusPostgresMemoryTool | None = None
            if bundle.runtime_memory_tool:
                customer_id_raw = state.get("customer_id")
                memory_tool = NexusPostgresMemoryTool(
                    tenant_id=tenant_id,
                    customer_id=uuid.UUID(customer_id_raw) if customer_id_raw else None,
                )
                # Insert the system addendum BEFORE the conversation
                # history so it stays inside the cached prefix (see
                # llm.py::_with_prompt_caching).
                messages.insert(
                    -1 if not state.get("history") else -(len(state["history"]) + 1),
                    {"role": "system", "content": MEMORY_TOOL_SYSTEM_PROMPT},
                )

            envelopes: list[dict[str, Any]] = []
            final_text = ""
            # Populated when the LLM calls ``response.send_interactive``.
            # Holds the validated tool args (body, header/footer, exactly
            # one of buttons/list/cta_url) minus the routing fields the
            # ucm_formatter does not need. When non-None the handler
            # breaks the ReAct loop after the current tool batch:
            # send_interactive is a terminal action, asking the LLM for
            # another iteration only burns tokens.
            interactive_payload: dict[str, Any] | None = None

            # Fase D — Anthropic Skills attached to this agent_config.
            # Build the ``container`` payload + ``extra_headers`` once,
            # outside the loop, so the same dict is passed on every
            # iteration. ``extra`` stays empty when no skills are
            # attached (the common case for tenants not opted in).
            #
            # Channel gating: a skill can declare ``channels=[...]`` in
            # its agent_config entry to limit injection to specific
            # channels (whatsapp-only skills should NOT load on the
            # web/QA channel). Filter once, then use the filtered list
            # for both ``container.skills`` and the ``code_execution``
            # tool append below — if every skill got filtered out, we
            # skip Skills wiring entirely as if no skills existed.
            applicable_skills = _filter_skills_for_channel(
                bundle.runtime_skills,
                state.get("channel_type") or "whatsapp",
            )
            skills_extra: dict[str, Any] = {}
            if applicable_skills:
                skills_extra = {
                    "container": {
                        "skills": [
                            {
                                "type": "custom",
                                "skill_id": s["skill_id"],
                                "version": s["version"],
                            }
                            for s in applicable_skills
                        ]
                    },
                    "extra_headers": {"anthropic-beta": _SKILLS_BETA_HEADER_VALUE},
                }

            # Fase E — Anthropic MCP connector. Stacks on top of the
            # Skills extra so a config opted into BOTH gets the right
            # beta header CSV without either feature clobbering the
            # other. Both gates required: ``runtime_mcp_connector`` is
            # the kill switch (defence in depth), ``runtime_mcp_servers``
            # lists which servers to attach. ``mcp_extra`` is the final
            # ``extra`` passed to the LLM each loop iteration.
            mcp_extra: dict[str, Any] | None = skills_extra or None
            if bundle.runtime_mcp_connector and bundle.runtime_mcp_servers:

                async def _resolver(key: str) -> str | None:
                    return await _resolve_mcp_token(tenant_id, key)

                mcp_extra = await build_mcp_extra(
                    servers=bundle.runtime_mcp_servers,
                    token_resolver=_resolver,
                    base_extra=skills_extra or None,
                )

            for iteration in range(MAX_TOOL_ITERATIONS):
                # The last iteration is tool-free: the model MUST answer.
                last = iteration == MAX_TOOL_ITERATIONS - 1
                if last:
                    tools_arg: list[dict[str, Any]] = []
                else:
                    tools_arg = list(available_defs)
                    if memory_tool is not None:
                        # ``to_dict()`` is the Anthropic TypedDict
                        # ``BetaMemoryTool20250818Param`` ({"type":
                        # "memory_20250818", "name": "memory"}); LiteLLM
                        # only cares about the dict shape so we widen.
                        tools_arg.append(dict(memory_tool.to_dict()))
                    if applicable_skills:
                        # code_execution is the container the Skills run
                        # inside. Anthropic requires it to be in tools[]
                        # whenever ``container.skills`` is set. Gated on
                        # the channel-filtered list — when every skill
                        # is excluded for the current channel, we must
                        # NOT add code_execution either (Anthropic
                        # rejects code_execution + empty container).
                        tools_arg.append(dict(_CODE_EXECUTION_TOOL))

                try:
                    response = await llm.respond_with_tools(
                        tenant_id=tenant_id,
                        role=intent,
                        messages=messages,
                        tools=tools_arg,
                        extra=mcp_extra,
                    )
                except Exception as exc:
                    # The router exhausted retries + fallback. Rather than
                    # let the exception kill the turn (the customer would
                    # get nothing and the message would stick), answer with
                    # a neutral message and stop the loop.
                    log.error(
                        "handler.llm_failed",
                        tenant_id=str(tenant_id),
                        intent=intent,
                        iteration=iteration,
                        error=str(exc),
                    )
                    final_text = _EMPTY_RESPONSE_FALLBACK
                    break

                if response.text:
                    final_text = response.text

                # No tools offered, or the model chose not to call any →
                # this text is the final answer.
                if not tools_arg or not response.tool_calls:
                    break

                # Record the model's tool request, then dispatch each call
                # and feed the REAL result back into the thread.
                messages.append(_assistant_tool_message(response))
                for call in response.tool_calls:
                    if call.name == _MEMORY_TOOL_NAME and memory_tool is not None:
                        # Built-in dispatch: the memory tool result is a
                        # string by Anthropic contract; we wrap it in an
                        # MCP-shaped envelope for traces but feed the LLM
                        # the raw string.
                        envelope, tool_msg = await _dispatch_memory_tool(
                            memory_tool, call, intent
                        )
                        envelopes.append(envelope)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id or call.name,
                                "content": tool_msg,
                            }
                        )
                        continue
                    envelope = await _dispatch_tool(
                        scoped_registry, call, available_names, intent
                    )
                    envelopes.append(envelope)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id or call.name,
                            "content": _tool_result_content(envelope),
                        }
                    )
                    # ``response.send_interactive`` is terminal — capture
                    # its validated args so the ucm_formatter + checkpoint
                    # nodes can render the WhatsApp interactive component.
                    # The 24h-window check + whitelist enforcement already
                    # ran inside the regular dispatch above (the tool
                    # behaves like any other notification.* tool); we just
                    # additionally stash the payload here. A non-``ok``
                    # status means the dispatcher rejected the call
                    # (window expired, payload malformed, not in
                    # whitelist) — in that case we leave the payload
                    # unset so the agent falls back to plain text in the
                    # next iteration.
                    if (
                        call.name == _INTERACTIVE_TOOL_NAME
                        and envelope.get("status") == "ok"
                    ):
                        raw_args = dict(call.arguments or {})
                        # Drop the routing fields the formatter doesn't
                        # need. ``context_message_id`` IS still useful
                        # downstream (quoted reply on the outbound), so
                        # keep it.
                        raw_args.pop("conversation_id", None)
                        interactive_payload = raw_args

                # Terminal-tool early exit: when ``response.send_interactive``
                # landed cleanly there is no value in another LLM round
                # — the response is already complete (text in
                # ``final_text``, structured payload in
                # ``interactive_payload``).
                if interactive_payload is not None:
                    break

            if not final_text.strip() and interactive_payload is None:
                log.warning(
                    "handler.empty_response",
                    tenant_id=str(tenant_id),
                    intent=intent,
                    iterations=iteration + 1,
                )
                final_text = _EMPTY_RESPONSE_FALLBACK

            return {
                "tool_calls": envelopes,
                "response": final_text,
                "response_model": llm.respond_model,
                # Empty dict (not ``None``) for state-merge stability:
                # LangGraph keeps the field present on every turn and
                # downstream nodes ``if state.get("interactive_payload")``
                # work uniformly.
                "interactive_payload": interactive_payload or {},
                # Forward the per-config flags so downstream nodes
                # (grade_outcome) gate on the bundle without re-loading
                # it from DB.
                "agent_runtime_flags": {
                    "memory_tool": bundle.runtime_memory_tool,
                    "outcome_grader": bundle.runtime_outcome_grader,
                    "mcp_connector": bundle.runtime_mcp_connector,
                },
            }

    return handler


async def _load_kg_snapshot_text(tenant_id: uuid.UUID) -> str:
    """Render a compact, LLM-friendly snapshot of the tenant's KG.

    The agent's system_prompt repeatedly says "use the knowledge graph"
    and "never invent prices / barbers / services". Without the snapshot
    in context the model has no choice — it hallucinates. We load
    ``kg_nodes`` once per turn (cheap, tenant-scoped, ≤ a few hundred
    rows) and serialise as a Markdown-ish block grouped by label.

    Returns an empty string when the KG is empty so the handler can skip
    the system message entirely.

    Tradeoff: this scales linearly with the KG. For tenants with >>200
    nodes we'll graduate to a real ``kg.lookup`` tool (filter by
    label + free-text) — see D1 in the agent-quality-roadmap.
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

    Called ONCE per turn by ``classify`` (ADR-023); the result travels in
    ``state["history"]`` so the handler does not re-query.

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


def make_grade_outcome_node(
    *,
    grader: OutcomeGrader | None,
    llm_router: LLMRouter,
) -> NodeFn:
    """Build the outcome-grader node.

    Sits between the intent handler and the UCM formatter. When the
    tenant has the grader enabled, runs Claude Haiku 4.5 against the
    handler's draft response (per [[architecture/outcome-grader]]):

    1. Look up the rubric for the turn's intent. If none, mark as
       skipped and pass through.
    2. Grade. If pass, mark and pass through.
    3. If fail and we have retries left, ask the AGENT'S model (the
       respond_model from the router) to rewrite the response using the
       grader feedback. Re-grade. Repeat up to ``MAX_GRADER_RETRIES``.
    4. If we exhaust retries, replace the response with
       :data:`GRADER_FALLBACK_RESPONSE` and emit a structured log so
       operators see the degradation in their alerting pipe.

    The whole retry loop is contained INSIDE the node — no LangGraph
    conditional edge back to the handler. That keeps the graph simple
    and avoids re-running the ReAct loop (which already executed its
    tools); the grader only needs the LLM to rephrase, not to redo
    the work.

    ``grader`` is ``None`` when the worker boots without API keys
    (tests, dev with ``NEXUS_LLM_USE_INMEMORY=1``); in that case the
    node passes through with ``outcome_overall='skipped'`` so the
    pipeline still composes correctly.
    """

    async def grade_outcome(state: AgentState) -> dict[str, Any]:
        if grader is None:
            return {"outcome_overall": "skipped", "outcome_retries": 0, "outcome_feedback": ""}

        # The handler forwarded the per-config flags via state. Gate
        # the grader on ``runtime_outcome_grader`` from the agent_config,
        # NOT on an env var — activation rides STAGED → ACTIVE.
        flags = state.get("agent_runtime_flags") or {}
        if not flags.get("outcome_grader"):
            return {"outcome_overall": "skipped", "outcome_retries": 0, "outcome_feedback": ""}

        tenant_id = _tenant_uuid(state)

        intent = state.get("intent") or "fallback"
        rubric_intent = _NEXUS_INTENT_TO_RUBRIC.get(intent, "default.general_response")
        rubric_body = load_rubric_text(rubric_intent)
        if rubric_body is None:
            # No rubric on disk — operator opted in but we have nothing
            # to grade against. Better to pass through (skipped) than
            # to silently fail every turn.
            log.warning(
                "outcome_grader.rubric_missing",
                tenant_id=str(tenant_id),
                intent=intent,
                rubric_intent=rubric_intent,
            )
            return {
                "outcome_overall": "skipped",
                "outcome_retries": 0,
                "outcome_feedback": "",
            }

        draft = state.get("response", "") or ""
        envelopes = state.get("tool_calls") or []

        # First grading attempt against the original draft.
        verdict = await grader.grade(
            tenant_id=tenant_id,
            intent=rubric_intent,
            rubric_body=rubric_body,
            draft_response=draft,
            tool_envelopes=envelopes,
        )

        retries = 0
        last_feedback = verdict.feedback

        # Retry loop. On each fail, ask the AGENT's primary model to
        # rewrite using the grader's feedback. Re-grade. Stop on pass
        # or on MAX_GRADER_RETRIES.
        while verdict.overall == "fail" and retries < MAX_GRADER_RETRIES:
            retries += 1
            new_draft = await _ask_agent_to_rewrite(
                llm_router=llm_router,
                tenant_id=tenant_id,
                intent=intent,
                original=draft,
                feedback=verdict.feedback,
            )
            if not new_draft.strip():
                # Model refused or produced empty — accept the last
                # verdict as final fail and bail to the fallback path.
                last_feedback = verdict.feedback
                break
            draft = new_draft
            verdict = await grader.grade(
                tenant_id=tenant_id,
                intent=rubric_intent,
                rubric_body=rubric_body,
                draft_response=draft,
                tool_envelopes=envelopes,
            )
            last_feedback = verdict.feedback

        if verdict.overall == "pass":
            return {
                "response": draft,
                "outcome_overall": "pass",
                "outcome_retries": retries,
                "outcome_feedback": "",
            }

        # All retries exhausted — degrade to the neutral fallback and
        # alert. Operations picks the structured log up through the
        # standard log shipper (block H tracing). The audit_log row
        # that the operator alerter watches is written by the
        # checkpoint node downstream; this node only needs to log.
        log.error(
            "outcome_grader.max_retries_exhausted",
            tenant_id=str(tenant_id),
            intent=intent,
            rubric_intent=rubric_intent,
            retries=retries,
            feedback=last_feedback,
        )
        return {
            "response": GRADER_FALLBACK_RESPONSE,
            "outcome_overall": "fail",
            "outcome_retries": retries,
            "outcome_feedback": last_feedback,
        }

    return grade_outcome


async def _ask_agent_to_rewrite(
    *,
    llm_router: LLMRouter,
    tenant_id: uuid.UUID,
    intent: str,
    original: str,
    feedback: str,
) -> str:
    """Ask the agent's primary model to rewrite ``original`` using
    ``feedback``. Used by the outcome grader retry loop.

    This is a one-shot call — no tools, no ReAct loop. The intent is
    only used for tracing; the routing is via the router's normal
    ``respond`` path so the same retry / fallback semantics apply.
    """
    messages = [
        {"role": "system", "content": _RETRY_SYSTEM_TEMPLATE.format(feedback=feedback)},
        {"role": "user", "content": original},
    ]
    try:
        return await llm_router.respond(tenant_id=tenant_id, messages=messages)
    except Exception as exc:
        log.warning(
            "outcome_grader.rewrite_failed",
            tenant_id=str(tenant_id),
            intent=intent,
            error=str(exc),
        )
        return ""


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
        interactive_payload = state.get("interactive_payload") or None
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
            interactive_payload=interactive_payload,
        )
        # Degrade for the channel this turn actually runs on. Production
        # turns are WhatsApp; QA Playground turns run on a "web" channel.
        # Falls back to "whatsapp" for callers that predate ``channel_type``.
        channel = state.get("channel_type") or "whatsapp"
        diff = shadow_diff_against_legacy(ucm, response_text, channel=channel)

        # The byte-equivalence shadow check only applies when the agent
        # produced text alone. Once an interactive component is in play
        # the UCM is intentionally richer than the legacy text path —
        # logging a divergence as a regression would create false
        # alerts. The diff record still travels for traces.
        if not diff["equivalent"] and interactive_payload is None:
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
    """Persist the outbound message(s) in the ``messages`` table.

    The LangGraph checkpointer already records pipeline state under
    ``thread_id``. This node persists the *business* artifact — the
    assistant's reply — that downstream features (operator panel,
    traces) read. The actual WhatsApp send lives in block F.

    When the turn produced an ``interactive_payload`` (the LLM called
    ``response.send_interactive``), two rows may be written in order:

    1. The text answer the LLM produced alongside the tool call (when
       non-empty). Sent first by the outbound dispatcher so the
       customer sees the explanation before the buttons / list.
    2. The interactive component row, with ``content`` set to the
       component's ``body`` for fallback rendering on operator panels
       and Langfuse, plus ``interactive_payload`` carrying the
       structured shape the dispatcher routes through
       ``adapter.send_interactive``.

    Turns without an interactive payload keep the historical single-
    row behaviour.
    """

    async def checkpoint(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        conv_id = uuid.UUID(state["conversation_id"])
        response_text = state.get("response", "") or ""
        interactive = state.get("interactive_payload") or None
        tool_calls = state.get("tool_calls") or []
        intent = state.get("intent")
        model = state.get("response_model")
        # Outcome grader verdict for this turn. ``skipped`` when the
        # feature is off for this agent_config; ``pass`` / ``fail`` /
        # ``error`` after grade_outcome ran. Both outbound rows (text +
        # interactive) inherit the same verdict — it's a turn-level
        # signal, not a per-row one. The columns are nullable so callers
        # that bypass the grader (test fixtures, manual sends) skip the
        # writes implicitly via the ``None`` defaults.
        outcome_overall = state.get("outcome_overall")
        outcome_retries = state.get("outcome_retries")
        outcome_feedback = state.get("outcome_feedback") or None

        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            # Row 1: plain-text answer. Always written when response is
            # non-empty so the operator panel + ucm shadow diff stay
            # aligned. The interactive row, when present, is written
            # AFTER so the dispatcher (which orders by created_at /
            # sequence) drains text first.
            if response_text.strip():
                await persist_outbound_message(
                    session,
                    conversation_id=conv_id,
                    content=response_text,
                    intent=intent,
                    model=model,
                    tool_calls=tool_calls,
                    outcome_overall=outcome_overall,
                    outcome_retries=outcome_retries,
                    outcome_feedback=outcome_feedback,
                )

            # Row 2: interactive component, when the agent called
            # ``response.send_interactive`` this turn. The dispatcher
            # detects ``interactive_payload IS NOT NULL`` and routes
            # through ``adapter.send_interactive``; ``content`` is the
            # body so the operator panel renders a sensible preview.
            if interactive:
                body = str(interactive.get("body") or response_text or "[interactive]")
                await persist_outbound_message(
                    session,
                    conversation_id=conv_id,
                    content=body,
                    intent=intent,
                    model=model,
                    # Tool envelopes already include the send_interactive
                    # call; don't re-add. Empty list keeps the row
                    # self-contained.
                    tool_calls=[],
                    interactive_payload=interactive,
                    outcome_overall=outcome_overall,
                    outcome_retries=outcome_retries,
                    outcome_feedback=outcome_feedback,
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
    outcome_grader: OutcomeGrader | None = None,
) -> Any:
    """Compile the StateGraph and return a runnable.

    ``checkpointer`` is optional: when ``None`` the compiled graph leaves
    persistence to whichever host runs it. Tests pass ``MemorySaver`` for
    deterministic state.

    ``mcp_registry`` defaults to ``nexus_mcp.build_default_registry()``;
    tests can pass a stripped-down registry.

    ``use_ucm_formatter`` controls Phase 2 of ADR-020. When ``None`` (the
    default) the flag is read from ``settings.use_ucm_formatter``; tests
    pass an explicit bool.

    ``outcome_grader`` is the Fase C output guardrail. When ``None``
    (tests, in-memory dev) the grader node passes through with
    ``outcome_overall='skipped'``. Production builds construct one in
    ``main.py`` from a ``LiteLLMProvider``.

    Graph (ADR-023 + Fase C): ``classify → {intent handler} →
    grade_outcome → ucm_formatter → checkpoint``. Each handler is a
    ReAct loop that produces a draft response; ``grade_outcome``
    validates it against the per-intent rubric and may rewrite it
    before the formatter ships it.
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
    g.add_node(
        "grade_outcome",
        make_grade_outcome_node(grader=outcome_grader, llm_router=llm_router),
    )
    g.add_node("ucm_formatter", make_ucm_formatter_node(enabled=use_ucm_formatter))
    g.add_node("checkpoint", make_checkpoint_node())

    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        _route_decider,
        {intent: intent for intent in VALID_INTENTS},
    )
    for intent in VALID_INTENTS:
        g.add_edge(intent, "grade_outcome")
    g.add_edge("grade_outcome", "ucm_formatter")
    g.add_edge("ucm_formatter", "checkpoint")
    g.add_edge("checkpoint", END)
    if checkpointer is None:
        return g.compile()
    return g.compile(checkpointer=checkpointer)
