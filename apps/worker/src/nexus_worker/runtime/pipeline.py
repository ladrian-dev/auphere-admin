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

import difflib
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from langgraph.graph import END, START, StateGraph
from nexus_api.core.admin_gate import ROLE_READONLY, sender_role
from nexus_api.core.llm_proxy import current_llm_proxy_partner
from nexus_api.core.tenant_context import (
    customer_context,
    tenant_context,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import TurnSource
from nexus_api.services.activations import ToolPolicy, allowed_names
from nexus_api.services.inbox_stream import publish_inbox_event
from nexus_api.services.router_catalog import CatalogSnapshot, ProfilePolicy, record_anomaly
from nexus_mcp import MCPRegistry, build_default_registry
from nexus_mcp.base import ToolError, ToolNotInWhitelist
from pydantic import ValidationError

from nexus_worker.guardrails import (
    GRADER_FALLBACK_RESPONSE,
    OutcomeGrader,
    load_rubric_text,
    rubric_for_intent,
)
from nexus_worker.guardrails.outcome_grader import MAX_GRADER_RETRIES
from nexus_worker.mcp_connector import build_mcp_extra
from nexus_worker.memory import (
    MEMORY_TOOL_SYSTEM_PROMPT,
    NexusPostgresMemoryTool,
)
from nexus_worker.metering.pricing import cheapest_model
from nexus_worker.persistence.messages import persist_outbound_message
from nexus_worker.runtime.agent_loader import AgentBundle, AgentLoader
from nexus_worker.runtime.console_context import (
    forced_escalation,
    load_gated_tool_names,
    load_knowledge_for_turn,
    render_operating_policy_block,
)
from nexus_worker.runtime.grading_policy import decide as grading_decide
from nexus_worker.runtime.grading_policy import load_read_only_tools, turn_writes
from nexus_worker.runtime.llm import LLMResponse, LLMRouter, ToolCall
from nexus_worker.runtime.model_resolver import (
    PINNED_BASE_PROFILE,
    ClassifyResult,
    EscalationResult,
    ModelPolicy,
    RouteContext,
    RouteDecision,
    RouteFacts,
    TurnBudget,
    TurnLimitReached,
    TurnSignals,
    chain_for,
    could_route,
    escalation_for,
    get_catalog_snapshot,
    load_route_facts,
    model_policy_of,
    pin_after,
    pinned_for,
    record_escalation,
    turn_budget,
    with_pin,
)
from nexus_worker.runtime.state import AgentState, checkpoint_shrink_update
from nexus_worker.runtime.turn_clock import now_note
from nexus_worker.runtime.turn_effects import tool_once
from nexus_worker.runtime.ucm_formatter import (
    format_response_as_ucm,
    shadow_diff_against_legacy,
)
from nexus_worker.streams.grade_consumer import publish_grade_job

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

NodeFn = Callable[[AgentState], Awaitable[Any]]

log = structlog.get_logger(__name__)


def _traced(name: str, fn: NodeFn) -> NodeFn:
    """WP-01: wrap a graph node in an OTel span so a turn's trace shows the
    per-node breakdown (classify → <intent> → grade_outcome → ucm_formatter
    → checkpoint). Zero-cost when no exporter is installed — the default
    provider hands out non-recording spans.
    """
    from opentelemetry import trace as otel_trace

    async def traced(state: AgentState) -> Any:
        tracer = otel_trace.get_tracer("nexus_worker")
        with tracer.start_as_current_span(f"node.{name}") as span:
            tenant_id = state.get("tenant_id")
            if tenant_id:
                span.set_attribute("tenant_id", str(tenant_id))
            return await fn(state)

    return traced


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
    "Disculpa, tuve un inconveniente para completar la respuesta. "
    "¿Puedes intentarlo de nuevo en un momento?"
)

# LiteLLM replaces an empty assistant text block with this sentinel to
# satisfy Anthropic's "content must be non-empty" rule when the model
# emits a tool call with no accompanying text. It is an internal artefact
# and must NEVER reach the customer — treat it as "no text" so the ReAct
# loop keeps going (and the empty-answer safety net applies if it was the
# final turn). Match by prefix to survive wording drift ("satisfy" vs
# "justify", "sanitised" vs "sanitized") across LiteLLM versions.
_LITELLM_EMPTY_SENTINEL_PREFIX = "[System: Empty message content sanit"


def _clean_model_text(text: str | None) -> str:
    """Drop LiteLLM's empty-content sentinel; return '' so callers treat it
    as no text rather than sending it to the customer."""
    if not text:
        return ""
    if text.lstrip().startswith(_LITELLM_EMPTY_SENTINEL_PREFIX):
        return ""
    return text


# Anthropic Memory tool name. The model emits ``tool_call.name == "memory"``
# (set by ``BetaAsyncAbstractMemoryTool.to_dict()``) and the handler routes
# directly to the tool instance, bypassing the MCP registry — built-in
# tools have their own scoping (the tool instance carries tenant_id +
# customer_id) and the ``tool_result`` is a string, not the MCP envelope.
# See architecture/builtin-tools-vs-mcp-tools.md.
_MEMORY_TOOL_NAME = "memory"

# Injected as a system note when the current sender is a READ-ONLY admin, so
# the agent declines write requests gracefully instead of just silently
# lacking the tool. The hard enforcement is the tool-whitelist filtering in
# the handler node (write tools are removed from what the model sees AND from
# what ``registry.dispatch`` will accept); this note is the UX layer on top.
_READONLY_ADMIN_NOTE = (
    "PERMISOS DEL USUARIO ACTUAL: SOLO LECTURA. Este administrador puede "
    "CONSULTAR información (deudas, cuentas, listados, buscar clientes) pero "
    "NO tiene permiso para ejecutar cambios: registrar pagos/abonos, crear "
    "cuentas, agregar cargos, cambiar estados, aplicar descuentos, editar "
    "cuentas ni enviar recordatorios. Si pide una operación de ese tipo, "
    "explicale con amabilidad que no tiene permiso para hacerla y ofrecele "
    "consultar la información que sí puede ver."
)


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
_SKILLS_BETA_HEADER_VALUE: str = "code-execution-2025-08-25,skills-2025-10-02,files-api-2025-04-14"
# Anthropic enforces a hard limit on ``container.skills`` (validation
# error ``container.ContainerParams.skills: List should have at most 8
# items``). When a tenant attaches more than 8 skills, we truncate to
# the first N to keep the request valid — the priority is the order in
# ``agent_config.runtime_skills`` (operator-curated). A warning is
# logged so we can audit which tenants exceed the cap.
_ANTHROPIC_SKILLS_CAP: int = 8


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
    return tuple(s for s in skills if not s.get("channels") or channel_type in s["channels"])


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
                _select(TenantCredentials).where(TenantCredentials.integration == credential_key)
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
# El mapa vive en ``guardrails.rubric_loader`` (lo comparten el nodo
# síncrono y el consumidor diferido de WP-21).


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
        # Spec 043: la agenda propia del negocio (con el módulo Reservas).
        "reservas.services",
        "reservas.find_slots",
        "reservas.create",
        "reservas.list_mine",
        "reservas.reschedule",
        "reservas.cancel",
        "reservas.confirm_attendance",
        "reservas.join_waitlist",
        "reservas.answer_offer",
        "booking.check_availability",
        "booking.create_appointment",
        "booking.modify_appointment",
        "booking.cancel_appointment",
        "booking.get_appointments",
        "client.get_preferences",
        "client.update_preferences",
        "client.get_history",
        # ADR-018 — what the agent cannot do on its own (a booking it may
        # not touch, a price that is not in the catalogue) it asks the
        # owner from this category, so the customer sees an immediate ack
        # while the owner answers asynchronously.
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
        "reservas.services",
        "reservas.list_mine",
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
# ``fallback`` is included so single-purpose agents (e.g. the WooCommerce
# sales agent, whose queries the classifier often lands on ``fallback``)
# can still emit native components / product cards — the connector tools
# already surface on ``fallback`` (``_CONNECTOR_TOOL_INTENTS``), so keeping
# the native output palette aligned avoids a text-only fallback.
for _intent in ("book", "queue", "info", "fallback"):
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

# Namespaced toolkits offered on EVERY intent, ``escalate`` included.
# ``payments`` (spec 025): the payment review is a hand-off to the team, and
# the classifier routinely files a receipt under ``escalate``.
# ``reception`` (spec 047, requisito 53): «quiero hablar con ventas» is as often
# an ``escalate`` as an ``info``; Recepción must be able to hand over on both.
_EVERY_INTENT_TOOLKITS: frozenset[str] = frozenset({"payments", "reception"})

# Spec 047 (requisito 53): Recepción's hand-over is terminal, like the
# interactive component — once it lands, the target answers, not Recepción.
_HANDOFF_TOOL_NAME = "reception.handoff"


def _reception_note(bundle: AgentBundle) -> str:
    """What Recepción reads about its targets, in the order of its list: who they
    are (name and id, the id is what the tool takes) and when to hand over. Only
    the agents of its list; their own instructions and knowledge never."""
    lines = [
        "## Derivar a otro agente",
        "Eres la recepción de este negocio. Cuando lo que pide el cliente es de uno "
        f"de estos agentes, pásale la conversación con la herramienta {_HANDOFF_TOOL_NAME} "
        "y un resumen breve del motivo; él contesta enseguida, en este mismo chat. "
        "No contestes tú lo que es suyo. Si no es de ninguno, atiéndelo tú.",
    ]
    for target in bundle.reception_targets:
        lines.append(f"- {target.name} (to_agent_id: {target.agent_id}): {target.when}")
    return "\n".join(lines)


def _handed_off(envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    """The successful hand-over among ``envelopes``, if any: ``{to_agent_id, hop}``."""
    for envelope in envelopes:
        result = envelope.get("result") or {}
        if (
            envelope.get("tool") == _HANDOFF_TOOL_NAME
            and envelope.get("status") == "ok"
            and isinstance(result, dict)
            and result.get("handed_off") is True
        ):
            args = envelope.get("args") or {}
            return {"to_agent_id": args.get("to_agent_id"), "hop": result.get("hop")}
    return {}


def _agent_uuid(state: AgentState) -> uuid.UUID | None:
    """Spec 030: the agent the dispatcher chose for this number, if any."""
    raw = state.get("agent_id")
    return uuid.UUID(raw) if raw else None


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
        # Namespaced connector tool. Composio toolkits with a natural intent
        # affinity keep their original narrow routing so existing tenants see
        # no change (calendar→book, gmail→escalate, and everything on 'info').
        # Every OTHER namespaced connector toolkit (e.g. the cobranza
        # ``billing.*`` tools) has no such affinity: surface it on all working
        # intents, exactly like the un-namespaced connector tools above.
        # Otherwise an admin whose message classifies as ``fallback`` (or
        # ``queue``/``book``) never gets its tools bound and the model emits
        # the tool call as plain text instead of invoking it.
        toolkit = t.split(".", 1)[0]
        if toolkit in _EVERY_INTENT_TOOLKITS:
            # Spec 025: a receipt is often classified ``escalate`` (the
            # customer "wants a person to check the payment"). The payment
            # review is exactly that hand-off, so it must be offered there
            # too — on every intent, never dropped by the classifier's guess.
            extras.append(t)
        elif intent == "info":
            extras.append(t)
        elif toolkit in {"googlecalendar", "calendly"}:
            if intent == "book":
                extras.append(t)
        elif toolkit == "gmail":
            if intent == "escalate":
                extras.append(t)
        elif intent in _CONNECTOR_TOOL_INTENTS:
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
    # The view MUST inherit ``dry_run`` and its audit hook: the QA
    # Playground relies on the registry gate to block side effects, and a
    # bare ``MCPRegistry()`` would let a Composio proxy write to the
    # client's real CRM/calendar from a test conversation. It also keeps the
    # registry's class: the agent playground's ``SimulatedRegistry`` (spec
    # 047) must keep its simulated world and its rules for connector tools.
    view = registry.view()
    for proxy in proxies:
        view._tools[proxy.name] = proxy
    return view, available_names


# ── Spec 047: the router in the graph (T140) ─────────────────────────────────
#
# Who goes through the router, decided per version of the agent
# (``model_resolver.ModelPolicy``, kept in ``agent_configs.policies`` until the
# AgentSpec):
#
# - **an agent of today** (no ``model_policy``) stays fixed on its model of today
#   by the path of today — ``respond_with_tools`` with its override, binding and
#   global fallback, byte for byte (research D24 and D44, story 13). Only its
#   classifier moves, and only when a deployment certified for ``classify``
#   passes the filter (D24, T145); while none does — today — the classifier is
#   the one of today too, and the turn pays no extra read;
# - **an agent with a profile or a pinned model** routes every conversation call
#   (``answer`` / ``tool_turn``), its classifier and its escalations through
#   ``chain_for``. Without a chain inside the client's residency the turn does
#   not leave it: the conversation goes to the Inbox with ``no_model`` (40.7).
#
# The affinity (``pinned_model``) lives in the client's thread checkpoint, per
# agent (garantía 4); every decision carries the client and the agent and no
# text (garantía 6); the transport sends every routed call with its zero
# retention and one request per call (garantía 7).

#: What the customer reads when the router hands the conversation to a person
#: («Económico» on a signal, the escalation or turn ceiling). The Inbox has the
#: reason; this only says what happens next.
_HANDOFF_RESPONSE = (
    "Voy a pasar tu consulta a una persona del equipo para que te ayude. "
    "Te escribiremos por aquí en cuanto podamos."
)

#: The typed classifier (40.5): an object, never a bare label.
_CLASSIFY_TYPED_PROMPT = (
    "Classify the LATEST user message. Earlier turns are context only. Reply with a "
    "JSON object with exactly these keys: intent (one of: "
    + ", ".join(VALID_INTENTS)
    + "), needs_tools (true if answering needs to look up or change data), risk "
    "(low, medium or high: how bad a wrong answer would be), complexity (low, medium "
    "or high), language (the ISO 639-1 code of the message) and intents (how many "
    "distinct requests the message makes, 1 to 5)."
)

#: The isolated escalation subcall (40.4): a summary in, a typed result out.
_ESCALATION_SYSTEM = (
    "Eres el asesor de un agente que atiende a los clientes de un negocio. El agente "
    "tiene dificultades en este turno; te paso un resumen. Devuelve un objeto JSON con "
    "dos claves: guidance (cómo debe seguir el agente, en pocas frases y en el idioma "
    "del cliente; sin inventar datos que una herramienta debe dar) y handoff (true si "
    "debe atenderlo una persona del equipo, false si el agente puede seguir)."
)
_ESCALATION_NOTE = (
    "Nota interna de un asesor, solo para ti: no la cites ni la menciones al cliente. {guidance}"
)

#: The router's reasons a turn ends in the Inbox (``contracts/events.md`` §2).
_ROUTER_REASONS = frozenset({"no_model", "provider_failure", "turn_limit", "escalated"})


async def _catalog() -> CatalogSnapshot | None:
    """The platform catalog, or None if it cannot be read (then nobody routes:
    an agent of today keeps its path; a profiled one gets ``no_model``)."""
    try:
        return await get_catalog_snapshot()
    except Exception as exc:
        log.warning("router.catalog_unavailable", error=type(exc).__name__)
        return None


async def _route_facts(state: AgentState, agent_id: uuid.UUID | None) -> RouteFacts:
    return await load_route_facts(
        _tenant_uuid(state), agent_id, partner_id=current_llm_proxy_partner()
    )


async def _record_router_anomaly(decision: RouteDecision) -> None:
    """``router_anomalies`` (40.7, 40.8): the reserve model or no model at all,
    under the client's RLS. Best effort: Auphere seeing it late beats a turn
    lost to a bookkeeping hiccup."""
    kind = decision.anomaly
    if kind is None:
        return
    log.warning(
        "router.anomaly",
        tenant_id=str(decision.tenant_id),
        agent_id=None if decision.agent_id is None else str(decision.agent_id),
        decision_id=str(decision.id),
        task=decision.task,
        kind=kind,
    )
    try:
        async with (
            get_sessionmaker()() as session,
            tenant_scoped_session(session, decision.tenant_id),
        ):
            await record_anomaly(
                session,
                tenant_id=decision.tenant_id,
                task=decision.task,
                kind=kind,
                decision_id=decision.id,
            )
    except Exception as exc:
        log.warning(
            "router.anomaly_not_recorded",
            tenant_id=str(decision.tenant_id),
            error=type(exc).__name__,
        )


def _route_context(
    state: AgentState,
    bundle: AgentBundle,
    snapshot: CatalogSnapshot,
    facts: RouteFacts,
    *,
    llm: LLMRouter,
    policy: ModelPolicy | None,
    conversation: bool,
) -> RouteContext:
    """What the router knows of this turn — ids, constraints, the affinity —
    and no text. The partner's allowlist is the ceiling of the conversation
    tasks (39.7); the other tasks follow the platform's catalog."""
    agent_id = bundle.agent_id or _agent_uuid(state)
    return RouteContext(
        tenant_id=_tenant_uuid(state),
        catalog=snapshot,
        agent_id=agent_id,
        agent_version=str(bundle.version_id),
        turn_id=state.get("inbound_message_id"),
        conversation_id=state.get("conversation_id"),
        allowed=facts.partner_allowed if conversation else None,
        eu_only=facts.eu_only,
        sovereign=facts.sovereign,
        agent_certified=facts.agent_certified,
        pinned=pinned_for(state, agent_id) if conversation else None,
        agent_pinned_deployment=(
            policy.deployment if policy is not None and policy.kind == "pinned" else None
        ),
        cooled=llm.cooldowns.active(),
        now=time.time(),
    )


def _turn_budget(profile: ProfilePolicy, state: AgentState) -> TurnBudget:
    """The turn's ceilings, with what the earlier nodes of this turn spent."""
    spent = state.get("router_turn") or {}
    return TurnBudget(
        max_calls=profile.max_calls_per_turn,
        cost_ceiling_micros=profile.turn_cost_ceiling_micros,
        calls=int(spent.get("calls") or 0),
        cost_micros=int(spent.get("cost_micros") or 0),
    )


def _router_reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    return reason if isinstance(reason, str) and reason in _ROUTER_REASONS else "provider_failure"


async def _classify_routed(
    state: AgentState,
    bundle: AgentBundle,
    history: list[dict[str, str]],
    llm: LLMRouter,
) -> tuple[str, dict[str, Any]] | None:
    """The typed classifier through the router (40.5), apart from the answer
    model. None = classify as today (see the block comment above)."""
    policy = model_policy_of(bundle.policies)
    snapshot = await _catalog()
    profile = (
        snapshot.profile(policy.profile if policy is not None else PINNED_BASE_PROFILE)
        if snapshot is not None
        else None
    )
    if snapshot is None or profile is None or profile.task("classify") is None:
        if policy is None:
            return None
        # A profiled agent never falls back to today's models: they need not be
        # in its residency. No classification; the handler routes its own task.
        log.error("router.profile_missing", tenant_id=state.get("tenant_id"), task="classify")
        return "fallback", {"classification": {}, "router_turn": {}}
    if policy is None and not could_route(snapshot, "classify"):
        return None
    agent_id = bundle.agent_id or _agent_uuid(state)
    facts = await _route_facts(state, agent_id)
    ctx = _route_context(state, bundle, snapshot, facts, llm=llm, policy=policy, conversation=False)
    decision = chain_for("classify", profile, ctx)
    if policy is None and decision.outcome != "routed":
        # T145 (research D24): the classifier of every agent moves to the
        # cheapest certified one — only to one that passed the battery.
        return None
    await _record_router_anomaly(decision)
    budget = _turn_budget(profile, state)
    classification: dict[str, Any] = {}
    intent = "fallback"
    if decision.outcome == "no_model":
        # Nothing leaves the client's residency; the handler routes its own task.
        log.warning("classify.no_model", tenant_id=state.get("tenant_id"))
    else:
        messages = [
            {"role": "system", "content": _CLASSIFY_TYPED_PROMPT},
            *history,
            {"role": "user", "content": state["user_message"]},
        ]
        try:
            with turn_budget(budget):
                result = await llm.complete_structured(
                    decision=decision,
                    tenant_id=_tenant_uuid(state),
                    messages=messages,
                    output=ClassifyResult,
                    role="classify",
                )
            budget.add_cost(result.cost_micros)
            classification = result.value.model_dump()
            intent = result.value.intent.strip().lower()
        except Exception as exc:
            # Like today's classifier: a failed classification is a ``fallback``
            # turn, never a stuck message.
            log.warning(
                "classify.routed_failed",
                tenant_id=state.get("tenant_id"),
                error=type(exc).__name__,
            )
    if intent not in VALID_INTENTS:
        intent = "fallback"
    return intent, {
        "classification": classification,
        "router_turn": {"calls": budget.calls, "cost_micros": budget.cost_micros},
    }


@dataclass
class _ConversationRoute:
    """The router's plan for the handler's conversation calls in this turn.

    One decision for the whole ReAct loop: the main loop does not change model
    (40.3, 40.4). ``decision`` is None when the catalog or the profile cannot be
    read — a profiled agent then has no model, never today's."""

    policy: ModelPolicy
    budget: TurnBudget
    escalations: list[float]
    decision: RouteDecision | None = None
    profile: ProfilePolicy | None = None
    snapshot: CatalogSnapshot | None = None
    ctx: RouteContext | None = None
    served: str | None = None
    escalated: bool = False
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def no_model(self) -> bool:
        return self.decision is None or self.decision.outcome == "no_model"

    def tier(self) -> str | None:
        if self.snapshot is None:
            return None
        key = self.served or (self.decision.chosen if self.decision is not None else None)
        deployment = self.snapshot.deployments.get(key or "")
        return None if deployment is None else deployment.capabilities.tier

    def family(self) -> str | None:
        if self.snapshot is None or self.served is None:
            return None
        deployment = self.snapshot.deployments.get(self.served)
        return None if deployment is None else deployment.family


async def _conversation_route(
    state: AgentState,
    bundle: AgentBundle,
    llm: LLMRouter,
    *,
    with_tools: bool,
) -> _ConversationRoute | None:
    """None for an agent of today: the handler runs exactly as before."""
    policy = model_policy_of(bundle.policies)
    if policy is None:
        return None
    task = "tool_turn" if with_tools else "answer"
    escalations = list(state.get("router_escalations") or [])
    snapshot = await _catalog()
    profile = snapshot.profile(policy.profile) if snapshot is not None else None
    if snapshot is None or profile is None or profile.task(task) is None:
        log.error("router.profile_missing", tenant_id=state.get("tenant_id"), task=task)
        return _ConversationRoute(
            policy=policy,
            budget=TurnBudget(max_calls=0, cost_ceiling_micros=None),
            escalations=escalations,
        )
    agent_id = bundle.agent_id or _agent_uuid(state)
    facts = await _route_facts(state, agent_id)
    ctx = _route_context(state, bundle, snapshot, facts, llm=llm, policy=policy, conversation=True)
    decision = chain_for(task, profile, ctx)
    await _record_router_anomaly(decision)
    return _ConversationRoute(
        policy=policy,
        budget=_turn_budget(profile, state),
        escalations=escalations,
        decision=decision,
        profile=profile,
        snapshot=snapshot,
        ctx=ctx,
    )


def _escalation_messages(
    state: AgentState,
    *,
    intent: str,
    signals: tuple[str, ...],
    envelopes: list[dict[str, Any]],
    draft: str,
) -> list[dict[str, str]]:
    """What the escalation subcall sees: a **summary** of the turn — never the
    agent's prompt, its knowledge or the history (40.4)."""
    summary = {
        "intent": intent,
        "signals": list(signals),
        "customer_message": (state.get("user_message") or "")[:4000],
        "draft_answer": draft[:2000],
        "tool_outcomes": [
            {
                "tool": e.get("tool"),
                "status": e.get("status"),
                "error": str(e.get("error"))[:300] if e.get("error") else None,
            }
            for e in envelopes[-6:]
        ],
    }
    return [
        {"role": "system", "content": _ESCALATION_SYSTEM},
        {"role": "user", "content": json.dumps(summary, ensure_ascii=False, sort_keys=True)},
    ]


async def _escalate_if_signalled(
    route: _ConversationRoute,
    signals: TurnSignals,
    *,
    llm: LLMRouter,
    state: AgentState,
    intent: str,
    messages: list[dict[str, Any]],
    envelopes: list[dict[str, Any]],
    draft: str,
) -> str | None:
    """The escalation of 40.4, at most once per turn. Returns the reason to hand
    the conversation to a person (``escalated``, ``turn_limit``, ``no_model``),
    or None to go on — with the adviser's guidance appended to the thread when
    the isolated subcall answered. The main loop keeps its model and affinity."""
    if route.escalated or route.decision is None or route.profile is None or route.ctx is None:
        return None
    now = time.time()
    verdict = escalation_for(
        signals,
        origin_task=route.decision.task,
        profile=route.profile,
        ctx=route.ctx,
        current_tier=route.tier(),
        escalations_at=route.escalations,
        now=now,
    )
    if verdict.action == "none":
        return None
    route.escalated = True
    route.signals = verdict.signals
    log.info(
        "router.escalation",
        tenant_id=state.get("tenant_id"),
        agent_id=None if route.ctx.agent_id is None else str(route.ctx.agent_id),
        action=verdict.action,
        signals=list(verdict.signals),
        reason=verdict.reason,
    )
    if verdict.action == "handoff" or verdict.decision is None:
        if verdict.decision is not None:
            await _record_router_anomaly(verdict.decision)
        return verdict.reason or "escalated"
    route.escalations = record_escalation(route.escalations, now=now)
    await _record_router_anomaly(verdict.decision)
    try:
        with turn_budget(route.budget):
            advice = await llm.complete_structured(
                decision=verdict.decision,
                tenant_id=_tenant_uuid(state),
                messages=_escalation_messages(
                    state, intent=intent, signals=verdict.signals, envelopes=envelopes, draft=draft
                ),
                output=EscalationResult,
                role="escalation",
            )
    except TurnLimitReached:
        return "turn_limit"
    except Exception as exc:
        # The subcall is help, not the turn: without it the loop goes on as it was.
        log.warning(
            "router.escalation_failed",
            tenant_id=state.get("tenant_id"),
            error=type(exc).__name__,
        )
        return None
    route.budget.add_cost(advice.cost_micros)
    if advice.value.handoff:
        return "escalated"
    messages.append(
        {"role": "system", "content": _ESCALATION_NOTE.format(guidance=advice.value.guidance)}
    )
    return None


def _intents(state: AgentState) -> int:
    raw = (state.get("classification") or {}).get("intents")
    return raw if isinstance(raw, int) and raw > 0 else 1


def _route_state_update(route: _ConversationRoute, state: AgentState) -> dict[str, Any]:
    """What the handler leaves in the thread: the affinity (per agent), the
    escalations of the hour and what the turn spent."""
    update: dict[str, Any] = {
        "router_turn": {
            "calls": route.budget.calls,
            "cost_micros": route.budget.cost_micros,
            "profile": route.profile.profile if route.profile is not None else None,
            "task": route.decision.task if route.decision is not None else None,
            "served": route.served,
            "family": route.family(),
        },
        "router_escalations": route.escalations,
    }
    decision, ctx = route.decision, route.ctx
    if decision is None or ctx is None:
        return update
    if route.served and decision.outcome in ("routed", "pinned"):
        pin = pin_after(decision, served=route.served, now=time.time(), previous=ctx.pinned)
        update["pinned_model"] = with_pin(state.get("pinned_model"), ctx.agent_id, pin)
    elif decision.pin_broken:
        update["pinned_model"] = with_pin(state.get("pinned_model"), ctx.agent_id, None)
    return update


# ── Node factories ────────────────────────────────────────────────────────────


def make_classify_node(loader: AgentLoader, llm: LLMRouter) -> NodeFn:
    """Cheap router: pick the intent and load the conversation history once.

    ``classify`` is intentionally kept as a pre-step (ADR-023): it routes to
    the right handler — and therefore the right tool sub-set, the runtime
    plane of garantía 2 — and it loads ``history`` a single time so the
    handler does not have to re-query the DB.

    Spec 047 (T140, requisito 40.5): through the router it is the **typed**
    classifier — the cheapest deployment certified for ``classify``, apart from
    the answer model — and it leaves ``classification`` in the state. An agent
    of today keeps the classifier of today until such a deployment exists
    (``_classify_routed``).
    """

    async def classify(state: AgentState) -> dict[str, Any]:
        tenant_id = _tenant_uuid(state)
        with tenant_context(tenant_id):
            # Warms the cache and raises if there is no active config. The
            # bundle also carries this tenant's model bindings (WP-19).
            bundle = await loader.load(tenant_id, _agent_uuid(state))
            history = await _load_recent_history(
                tenant_id,
                state.get("conversation_id"),
                exclude_message_id=state.get("inbound_message_id"),
            )
            routed = await _classify_routed(state, bundle, history, llm)
            if routed is not None:
                intent, routed_update = routed
                if intent != "escalate" and forced_escalation(bundle.policies, history):
                    log.info("classify.turn_cap_escalation", tenant_id=str(tenant_id), was=intent)
                    intent = "escalate"
                return {"intent": intent, "route": intent, "history": history, **routed_update}
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
                raw = await llm.classify(
                    tenant_id=tenant_id,
                    messages=messages,
                    models=chain_for(
                        bundle.model_bindings,
                        "classify",
                        default_model=llm.classify_model,
                        global_fallback=llm.fallback_model,
                    ),
                )
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
            # CP-11: the console's "hand off after N turns" rule is a routing
            # decision, not a prompt hint — override the classifier.
            if intent != "escalate" and forced_escalation(bundle.policies, history):
                log.info("classify.turn_cap_escalation", tenant_id=str(tenant_id), was=intent)
                intent = "escalate"
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


# Cross-tenant conduct rule, injected on every turn like the channel note
# (so it applies to already-rendered agent_configs, not just future seeds).
# The model defaults to feminine greetings in Spanish ("¡Bienvenida!") and
# improvises a generic greeting that assumes the customer's gender — flagged
# on Clínica Boreal. We never know the customer's gender from a phone number
# or an opening "Hola", so the agent must stay neutral until the customer
# reveals it.
# La fecha y la hora del turno **viven en `runtime/turn_clock.py`** desde la
# spec 015: las usan dos agentes —éste y el teammate— y dejarlas aquí obligaba
# al companion a importar el grafo entero del canal. El porqué, con la fecha del
# incidente de 2026-08-19, se movió con ellas.
#
# Se re-exporta con el nombre privado de siempre para que nada de fuera se
# entere: `_now_note` sigue importable desde este módulo, y su test tampoco se
# tocó (spec 015, T005 — si hubiera habido que tocarlo, el movimiento estaba
# mal).
_now_note = now_note


_GENDER_NEUTRAL_NOTE = (
    "Never assume the customer's gender. You do not know it from their "
    "phone number, name, or an opening greeting. Until the customer makes "
    "it explicit, avoid gendered greetings, honorifics and adjectives. In "
    "Spanish: do NOT use '¡Bienvenida!'/'¡Bienvenido!', 'señora'/'señor', "
    "or gendered adjectives directed at the customer — greet with a neutral "
    "'¡Hola!' and phrase things in a gender-neutral way. Mirror a gendered "
    "form only after the customer has clearly revealed their gender."
)


def _build_handler_messages(
    state: AgentState,
    bundle: AgentBundle,
    *,
    intent: str,
    kg_snapshot: str,
    knowledge: str = "",
) -> list[dict[str, Any]]:
    """Assemble the base message thread for the handler's ReAct loop.

    Order: system prompt → channel note → operating policy (console,
    CP-11/31) → KG snapshot → knowledge base (console, CP-15) → owner
    addendum → a turn directive → conversation history → the user's
    message. The loop appends assistant/tool messages onto this list as
    it iterates.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": bundle.system_prompt},
        {
            "role": "system",
            "content": _channel_format_note(state.get("channel_type") or "whatsapp"),
        },
        {"role": "system", "content": _now_note(bundle.timezone)},
        {"role": "system", "content": _GENDER_NEUTRAL_NOTE},
    ]
    operating_policy = render_operating_policy_block(bundle.policies)
    if operating_policy:
        messages.append({"role": "system", "content": operating_policy})
    if kg_snapshot:
        messages.append({"role": "system", "content": kg_snapshot})
    if knowledge:
        messages.append({"role": "system", "content": knowledge})
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


# Anthropic server-side / hosted tools execute inside Anthropic's own
# container (``code_execution`` and the skills ``text_editor``, plus
# ``web_search`` etc.) and carry a ``srvtoolu_`` id prefix. Anthropic
# resolves both the tool_use AND its tool_result internally — they never
# round-trip to us. The worker must NOT dispatch them nor inject a
# ``tool_result`` for them: doing so leaves an orphan ``tool_result``
# whose ``tool_use`` has no client-side pair, which Anthropic rejects on
# the next request with ``unexpected tool_use_id found in tool_result
# blocks`` (incident 2026-05-28, Boreal — the aesthetic-procedures-kb
# skill runs inside code_execution). We passthrough: drop server-side
# calls from our message bookkeeping entirely; they already did their job
# inside the response that produced ``response.text``.
_SERVER_SIDE_TOOL_ID_PREFIX = "srvtoolu_"
_SERVER_SIDE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "code_execution",
        "text_editor_code_execution",
        "bash_code_execution",
        "web_search",
    }
)


def _is_server_side_tool_call(call: ToolCall) -> bool:
    """True when the call is an Anthropic hosted tool the worker must not
    dispatch — identified by the ``srvtoolu_`` id prefix or a known hosted
    tool name. See ``_SERVER_SIDE_TOOL_NAMES`` for the rationale."""
    return (call.id or "").startswith(_SERVER_SIDE_TOOL_ID_PREFIX) or (
        call.name in _SERVER_SIDE_TOOL_NAMES
    )


def _assistant_tool_message(response: LLMResponse, calls: list[ToolCall]) -> dict[str, Any]:
    """The assistant message recording the tool calls the model just made,
    in the OpenAI/LiteLLM shape, so the next request shows the model its own
    previous output before the tool results.

    ``calls`` is the CLIENT-SIDE subset only — server-side calls are
    excluded so we never echo a ``srvtoolu_`` tool_use we won't pair with
    a tool_result (Anthropic rejects the orphan)."""
    return {
        "role": "assistant",
        "content": response.text or "",
        "tool_calls": [
            {
                "id": tc.id or tc.name,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in calls
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
    if str(status).startswith("approval_"):
        # Spec 047 (35.5): the action did NOT run; the message says why and what
        # to tell the customer.
        return "NOT DONE: " + str((envelope.get("result") or {}).get("message") or status)
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
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Dispatch one tool call, returning an envelope no matter what.

    The pre-LLM filter should have prevented a non-whitelisted name, but the
    registry re-checks (defense in depth — garantía 2). A whitelist
    violation or a tool error becomes an envelope with a non-``ok`` status
    so the loop can feed the failure back to the model instead of crashing
    the turn.

    ``conversation_id`` is the turn's real conversation. Tools like
    ``response.send_interactive`` / ``notification.*`` require it, but it is
    an internal UUID the LLM cannot know — it hallucinates one, which then
    fails ``_load_conversation`` ("conversation not found"). We inject the
    real value whenever the tool declares the field, so the model never has
    to (and cannot corrupt) it.
    """
    args = dict(call.arguments or {})
    if conversation_id and "conversation_id" in args:
        args["conversation_id"] = conversation_id
    try:
        envelope: dict[str, Any] = await registry.dispatch(
            call.name, args, whitelist=available_names
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
        failed: dict[str, Any] = {
            "tool": call.name,
            "intent": intent,
            "status": "error",
            "error": str(exc),
            "result": {},
        }
        if isinstance(exc.__cause__, ValidationError):
            # Spec 047 (40.4): the tool refused its arguments when validating
            # them — a signal of difficulty of the graph, not of the text. What
            # the model reads (``_tool_result_content``) does not change.
            failed["error_kind"] = "invalid_arguments"
        return failed


#: Spec 047 (requisito 1.4): what the closing iteration of the ReAct loop asks.
#: The customer gets an answer with what the turn has, never nothing.
FINAL_ANSWER_NOTE = (
    "Es tu última respuesta de este turno: no puedes usar más herramientas. "
    "Contesta ahora al cliente con lo que ya tienes. Si te falta algo, dile qué "
    "y qué vas a hacer; no prometas nada que no hayas hecho."
)


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
        _customer_raw = state.get("customer_id")
        _customer_id = uuid.UUID(_customer_raw) if _customer_raw else None
        with tenant_context(tenant_id), customer_context(_customer_id):
            bundle: AgentBundle = await loader.load(tenant_id, _agent_uuid(state))
            available_names = _filter_tools_for_intent_with_composio(bundle, intent)
            scoped_registry, available_names = await _view_with_composio(
                registry=registry,
                tenant_id=tenant_id,
                available_names=available_names,
            )
            # Per-admin role gate (cobranza): a READ-ONLY admin never gets the
            # write tools. Dropping them from the whitelist means the model
            # never sees them AND ``registry.dispatch`` refuses them
            # (ToolNotInWhitelist) if the model hallucinates one — real
            # enforcement, not just hiding. ``None``/``full`` = no change.
            # Console per-tool gating (CP-13): explicit tenant overrides
            # (blocked / needs_approval) leave the whitelist. A gate that cannot
            # be read is closed (T217): no tool this turn.
            gated = await _load_gated_tools(tenant_id)
            available_names = without_gated(available_names, gated)
            # Spec 047 (35.5, 35.6): the agent's activation of each connection —
            # without one, none of its tools; «Solo leer» drops the writes;
            # «Preguntar antes de escribir» keeps them behind a durable approval.
            # Spec 047, enmienda del 2026-10-30 (65.11): a policy that cannot be
            # read is closed — no connector tool at all, only the house's.
            tool_policy = await _load_tool_policy(tenant_id, _agent_uuid(state))
            available_names = allowed_names(available_names, tool_policy)
            admin_role = sender_role(bundle.policies, state.get("user_id"))
            if admin_role == ROLE_READONLY:
                available_names = tuple(
                    n for n in available_names if not scoped_registry.is_side_effecting(n)
                )
            available_defs = scoped_registry.get_openai_tools(available_names)
            kg_snapshot = await _load_kg_snapshot_text(tenant_id)
            knowledge, knowledge_sources = await _load_knowledge(
                tenant_id, _agent_uuid(state), str(state.get("user_message") or "")
            )
            messages = _build_handler_messages(
                state, bundle, intent=intent, kg_snapshot=kg_snapshot, knowledge=knowledge
            )
            if admin_role == ROLE_READONLY:
                # System prompt is messages[0]; keep the note right after it.
                messages.insert(1, {"role": "system", "content": _READONLY_ADMIN_NOTE})
            if bundle.reception_targets and _HANDOFF_TOOL_NAME in available_names:
                # Spec 047 (53.1): Recepción's list, right after its own prompt.
                messages.insert(1, {"role": "system", "content": _reception_note(bundle)})

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
                    agent_id=bundle.agent_id if bundle.memory_scope == "own" else None,
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
            # Spec 047 (requisito 53): Recepción handed the conversation over in
            # this turn. Terminal too: the target answers (the dispatcher runs
            # it next), so Recepción says nothing more — not even the fallback.
            # (``handoff`` below is the router's, to a person: another thing.)
            reception_handoff: dict[str, Any] = {}

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
            if len(applicable_skills) > _ANTHROPIC_SKILLS_CAP:
                log.warning(
                    "skills.cap_exceeded",
                    tenant_id=str(tenant_id),
                    requested=len(applicable_skills),
                    cap=_ANTHROPIC_SKILLS_CAP,
                    dropped=[s["skill_id"] for s in applicable_skills[_ANTHROPIC_SKILLS_CAP:]],
                )
                applicable_skills = applicable_skills[:_ANTHROPIC_SKILLS_CAP]
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

            # Per-tenant respond-model override (agent_config
            # ``policies.llm.respond_model``): lets a latency-sensitive agent
            # (e.g. the WooCommerce sales agent) run on a faster model like
            # Haiku without changing the global default (Mouna stays on
            # Sonnet). Empty / missing → the router's global respond model.
            _llm_pol = bundle.policies.get("llm")
            respond_model_override = (
                _llm_pol.get("respond_model") if isinstance(_llm_pol, dict) else None
            )
            if not isinstance(respond_model_override, str) or not respond_model_override:
                respond_model_override = None

            # WP-19 — ``tenant_model_bindings`` gana sobre la policy del
            # agent_config: la tabla es la fuente de verdad de la elección
            # de modelo, la policy es el mecanismo antiguo que sobrevive
            # para los tenants que aún no tienen binding.
            _respond_binding = bundle.model_bindings.get("respond")
            respond_fallbacks: tuple[str, ...] = ()
            if _respond_binding is not None:
                respond_model_override = _respond_binding.model_id
                respond_fallbacks = _respond_binding.fallback_chain

            # WP-20 — presupuesto blando con acción ``downgrade``: se pasa
            # al modelo más barato del catálogo (WP-19) por encima de
            # cualquier elección. Es explícitamente peor calidad a cambio
            # de seguir atendiendo, y esa es la decisión correcta cuando
            # la alternativa es acercarse al corte duro.
            if state.get("budget_degrade_model"):
                cheapest = await cheapest_model()
                if cheapest:
                    respond_model_override = cheapest
                    respond_fallbacks = ()

            _turn_started = time.perf_counter()
            # Why the fallback text was used, if it was. See ``AgentState.turn_failure``.
            turn_failure: dict[str, Any] | None = None

            # Spec 047 (T140): an agent with a profile or a pinned model goes
            # through the router; an agent of today (``route is None``) runs
            # exactly the loop of today.
            route = await _conversation_route(
                state,
                bundle,
                llm,
                with_tools=bool(available_defs)
                or memory_tool is not None
                or bool(applicable_skills),
            )
            iterations = MAX_TOOL_ITERATIONS
            if route is not None and route.no_model:
                # Without a chain inside the client's residency the turn does
                # not leave it (40.7): no call, the neutral reply, the Inbox.
                iterations = 0
                final_text = _EMPTY_RESPONSE_FALLBACK
                turn_failure = {"kind": "llm_failed", "reason": "no_model", "detail": None}
            elif route is not None and _intents(state) > 1:
                handoff = await _escalate_if_signalled(
                    route,
                    TurnSignals(intents=_intents(state)),
                    llm=llm,
                    state=state,
                    intent=intent,
                    messages=messages,
                    envelopes=envelopes,
                    draft=final_text,
                )
                if handoff is not None:
                    iterations = 0
                    final_text = _HANDOFF_RESPONSE
                    turn_failure = {"kind": "handoff", "reason": handoff, "detail": None}
            iteration = -1
            for iteration in range(iterations):
                # The last iteration is tool-free: the model MUST answer.
                last = iteration == MAX_TOOL_ITERATIONS - 1
                tools_arg: list[dict[str, Any]] = list(available_defs)
                if memory_tool is not None:
                    # ``to_dict()`` is the Anthropic TypedDict
                    # ``BetaMemoryTool20250818Param`` ({"type":
                    # "memory_20250818", "name": "memory"}); LiteLLM
                    # only cares about the dict shape so we widen.
                    tools_arg.append(dict(memory_tool.to_dict()))
                call_extra = None if last else mcp_extra
                if last:
                    # Spec 047 (requisito 1.4, bug B3 of the 2026-09-19
                    # audit): the closing call still DECLARES the catalogue —
                    # without ``tools`` a thread carrying ``tool_calls`` is a
                    # 400 from Anthropic via LiteLLM — and forbids it with
                    # ``tool_choice: "none"``, like the Companion's close. The
                    # note asks for the answer with what the turn has. No
                    # ``code_execution`` here: with the skills container gone
                    # Anthropic rejects it.
                    if tools_arg:
                        call_extra = {"tool_choice": "none"}
                    messages.append({"role": "system", "content": FINAL_ANSWER_NOTE})
                else:
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
                    # The closing iteration drops ``code_execution`` from
                    # ``tools`` — so it must ALSO drop the skills
                    # ``container`` from ``extra``, or Anthropic rejects the
                    # call ("container: skills can only be used when a code
                    # execution tool is enabled"). No tools this turn means
                    # skills/MCP aren't usable anyway.
                    if route is None:
                        response = await llm.respond_with_tools(
                            tenant_id=tenant_id,
                            role=intent,
                            messages=messages,
                            tools=tools_arg,
                            extra=call_extra,
                            model_override=respond_model_override,
                            fallback_override=respond_fallbacks,
                        )
                    else:
                        assert route.decision is not None
                        with turn_budget(route.budget):
                            routed_call = await llm.respond_routed(
                                decision=route.decision,
                                tenant_id=tenant_id,
                                role=intent,
                                messages=messages,
                                tools=tools_arg,
                                extra=call_extra,
                            )
                        route.budget.add_cost(routed_call.cost_micros)
                        route.served = routed_call.served
                        response = routed_call.value
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
                    turn_failure = {"kind": "llm_failed", "detail": str(exc)}
                    if route is not None:
                        # Spec 047: the Inbox reason of the router (``no_model``,
                        # ``provider_failure``, ``turn_limit``).
                        turn_failure["reason"] = _router_reason(exc)
                        if turn_failure["reason"] == "turn_limit":
                            final_text = _HANDOFF_RESPONSE
                    break

                cleaned_text = _clean_model_text(response.text)
                if cleaned_text:
                    final_text = cleaned_text

                # Anthropic resolves server-side tools (code_execution, the
                # skills text_editor, web_search) inside its own container
                # before returning — they're already done. Partition them
                # out so we never dispatch them nor record an orphan
                # tool_result for a ``srvtoolu_`` id (incident 2026-05-28).
                client_calls = [c for c in response.tool_calls if not _is_server_side_tool_call(c)]

                # No tools offered, the closing call, or the model only made
                # server-side calls (already resolved by Anthropic) → this
                # text is the final answer. A tool call on the closing call
                # (``tool_choice: "none"`` should prevent it) is not run.
                if last or not tools_arg or not client_calls:
                    break

                # Record the model's tool request, then dispatch each call
                # and feed the REAL result back into the thread.
                messages.append(_assistant_tool_message(response, client_calls))
                batch_start = len(envelopes)
                for call in client_calls:
                    if call.name == _MEMORY_TOOL_NAME and memory_tool is not None:
                        # Built-in dispatch: the memory tool result is a
                        # string by Anthropic contract; we wrap it in an
                        # MCP-shaped envelope for traces but feed the LLM
                        # the raw string.
                        envelope, tool_msg = await _dispatch_memory_tool(memory_tool, call, intent)
                        envelopes.append(envelope)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id or call.name,
                                "content": tool_msg,
                            }
                        )
                        continue

                    async def _run(call: ToolCall = call) -> dict[str, Any]:
                        if call.name in tool_policy.needs_approval:
                            if scoped_registry.dry_run:
                                # The playground and the tests (20.1): nobody
                                # is asked. The turn says it would have asked
                                # and goes on as if the owner said yes, so the
                                # rest can be checked; the dispatch below is
                                # the dry run's, which never writes.
                                scoped_registry.note_simulated_approval(
                                    call.name, dict(call.arguments or {})
                                )
                            else:
                                asked = await _approval_envelope(state, call, intent)
                                if asked is not None:
                                    return asked
                        return await _dispatch_tool(
                            scoped_registry,
                            call,
                            available_names,
                            intent,
                            conversation_id=state.get("conversation_id"),
                        )

                    if scoped_registry.is_side_effecting(call.name) and not scoped_registry.dry_run:
                        # Spec 047 (T035, requisito 1.3): reserve, charge,
                        # send a link… at most once per turn. A retried turn
                        # gets the first attempt's answer back.
                        envelope = await tool_once(tool=call.name, run=_run)
                    else:
                        envelope = await _run()
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
                    # next iteration. ``skipped:dry_run`` is NOT a rejection:
                    # the QA Playground intercepts the real send but must still
                    # render the interactive component in the preview, so we
                    # capture the payload in that case too.
                    if call.name == _INTERACTIVE_TOOL_NAME and envelope.get("status") in (
                        "ok",
                        "skipped:dry_run",
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
                # Spec 047 (requisito 53): the conversation is the target's now.
                # No further round: the dispatcher runs the target in this turn.
                reception_handoff = _handed_off(envelopes[batch_start:])
                if reception_handoff:
                    break

                # Spec 047 (40.4): the graph's signals of difficulty — a tool
                # that refused its arguments, a long tool loop, several
                # requests in one message — ask for an isolated subcall to a
                # higher tier. The loop keeps its model; «Económico» and the
                # hourly ceiling hand the conversation to a person instead.
                if route is not None:
                    handoff = await _escalate_if_signalled(
                        route,
                        TurnSignals(
                            tool_args_rejected=any(
                                e.get("error_kind") == "invalid_arguments"
                                for e in envelopes[batch_start:]
                            ),
                            intents=_intents(state),
                            tool_iterations=iteration + 1,
                        ),
                        llm=llm,
                        state=state,
                        intent=intent,
                        messages=messages,
                        envelopes=envelopes,
                        draft=final_text,
                    )
                    if handoff is not None:
                        final_text = _HANDOFF_RESPONSE
                        turn_failure = {"kind": "handoff", "reason": handoff, "detail": None}
                        break

            if not final_text.strip() and interactive_payload is None and not reception_handoff:
                log.warning(
                    "handler.empty_response",
                    tenant_id=str(tenant_id),
                    intent=intent,
                    iterations=iteration + 1,
                )
                final_text = _EMPTY_RESPONSE_FALLBACK
                turn_failure = turn_failure or {"kind": "empty_response", "detail": None}

            # Per-turn latency summary. ``iterations`` x per-call latency (see
            # ``llm.call_complete``) is the whole story of a slow turn: a turn
            # that hit the ``MAX_TOOL_ITERATIONS`` cap with N sequential Sonnet
            # calls is structurally different from one slow single call, and we
            # could not tell them apart before this event existed.
            log.info(
                "handler.turn_complete",
                tenant_id=str(tenant_id),
                intent=intent,
                iterations=iteration + 1,
                elapsed_ms=round((time.perf_counter() - _turn_started) * 1000),
                respond_model=(
                    (route.served if route is not None else None)
                    or respond_model_override
                    or llm.respond_model
                ),
                tool_calls=len(envelopes),
            )

            route_update = _route_state_update(route, state) if route is not None else {}
            return {
                **route_update,
                "tool_calls": envelopes,
                "response": final_text,
                "response_model": (
                    route.served if route is not None and route.served else llm.respond_model
                ),
                "turn_failure": turn_failure,
                # Empty dict (not ``None``) for state-merge stability:
                # LangGraph keeps the field present on every turn and
                # downstream nodes ``if state.get("interactive_payload")``
                # work uniformly.
                "interactive_payload": interactive_payload or {},
                # Spec 047 (requisito 53): Recepción derivó; vacío si no.
                "reception_handoff": reception_handoff,
                # Spec 047 (38.3): lo que se usó para contestar; se guarda con
                # la respuesta en ``turn_sources``.
                "knowledge_sources": knowledge_sources,
                # Forward the per-config flags so downstream nodes
                # (grade_outcome) gate on the bundle without re-loading
                # it from DB.
                "agent_runtime_flags": {
                    "memory_tool": bundle.runtime_memory_tool,
                    "outcome_grader": bundle.runtime_outcome_grader,
                    "mcp_connector": bundle.runtime_mcp_connector,
                    # WP-21 — el grader decide con esto si corre ahora o
                    # después. Viaja por el estado para no releer el
                    # bundle en el nodo siguiente.
                    "grader_mode": bundle.grader_mode,
                    "grader_sample_rate": bundle.grader_sample_rate,
                },
            }

    return handler


async def _load_tool_policy(tenant_id: uuid.UUID, agent_id: uuid.UUID | None) -> ToolPolicy:
    """Spec 047 (T128): the connector activations of this agent. Fails closed
    (spec 047, amendment of 2026-10-30, 65.11; guarantee 2): when the policy
    cannot be read, the turn offers no connector tool at all
    (``ToolPolicy.closed``), only the house's; the registry still refuses what is
    not whitelisted."""
    from nexus_api.services import activations

    try:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            return await activations.tool_policy(session, tenant_id, agent_id)
    except Exception as exc:
        log.warning("tool_policy.load_failed", tenant_id=str(tenant_id), error=type(exc).__name__)
        return ToolPolicy(closed=True)


async def _approval_envelope(
    state: AgentState, call: ToolCall, intent: str
) -> dict[str, Any] | None:
    """«Preguntar antes de escribir» (35.5): ``None`` when the owner already
    approved this very action (it runs now, once); otherwise the envelope the
    model reads — the request went out, is pending, or was denied."""
    import sqlalchemy as sa
    from nexus_api.db.models import Agent, Tenant
    from nexus_api.services.tool_approvals import MESSAGES, gate

    tenant_id = _tenant_uuid(state)
    conversation = state.get("conversation_id")
    if not conversation:
        return {"tool": call.name, "intent": intent, "status": "approval_unavailable", "result": {}}
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        tenant_name = await session.scalar(sa.select(Tenant.name).where(Tenant.id == tenant_id))
        agent_id = _agent_uuid(state)
        agent_name = (
            await session.scalar(sa.select(Agent.name).where(Agent.id == agent_id))
            if agent_id
            else None
        )
        verdict = await gate(
            session,
            conversation_id=uuid.UUID(str(conversation)),
            tool=call.name,
            args=dict(call.arguments or {}),
            tenant_name=str(tenant_name or ""),
            agent_name=agent_name,
        )
    if verdict == "allowed":
        return None
    log.info("tool.approval", tool=call.name, verdict=verdict, tenant_id=str(tenant_id))
    return {
        "tool": call.name,
        "intent": intent,
        "status": f"approval_{verdict}",
        "result": {"message": MESSAGES[verdict]},
    }


async def _load_gated_tools(tenant_id: uuid.UUID) -> frozenset[str] | None:
    """The tools the tenant gated off (CP-13), or ``None`` if they cannot be read.

    Fails closed (spec 047, T217, security review of 2026-10-30; guarantee 2), as
    :func:`_load_tool_policy` does: the gate is a deny-list that any catalogued
    tool can be on, the house's included, so a gate that cannot be read leaves
    the turn without tools (:func:`without_gated`)."""
    try:
        return await load_gated_tool_names(tenant_id)
    except Exception as exc:
        log.warning("tool_gating.load_failed", tenant_id=str(tenant_id), error=type(exc).__name__)
        return None


def without_gated(names: tuple[str, ...], gated: frozenset[str] | None) -> tuple[str, ...]:
    """The tools a turn may offer after the tenant's gate. ``None`` (the gate could
    not be read): none at all."""
    if gated is None:
        return ()
    return tuple(n for n in names if n not in gated)


async def _load_knowledge(
    tenant_id: uuid.UUID, agent_id: uuid.UUID | None, query: str
) -> tuple[str, list[dict[str, Any]]]:
    """CP-15 knowledge block, by layer (spec 047, D14): the business's and this
    agent's own, never a sibling's — whole if it fits, else the hybrid search.
    Returns the block and its sources. Best-effort: a failure to read degrades
    to "no knowledge block" and the turn goes on."""
    try:
        return await load_knowledge_for_turn(tenant_id, agent_id, query)
    except Exception as exc:
        log.warning("knowledge.load_failed", tenant_id=str(tenant_id), error=type(exc).__name__)
        return "", []


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
        if grader is None or state.get("reception_handoff"):
            # Spec 047 (requisito 53): Recepción derivó y no contestó; contesta
            # el destino en su propia pasada, y esa sí se gradúa.
            return {"outcome_overall": "skipped", "outcome_retries": 0, "outcome_feedback": ""}

        # The handler forwarded the per-config flags via state. Gate
        # the grader on ``runtime_outcome_grader`` from the agent_config,
        # NOT on an env var — activation rides STAGED → ACTIVE.
        flags = state.get("agent_runtime_flags") or {}
        tenant_id = _tenant_uuid(state)
        # Spec 047 (T143): a routed turn grades with its profile's sampling,
        # its typed risk and a judge of another family. A turn of today: None,
        # None, None — everything as before.
        routed_turn = state.get("router_turn") or {}
        judged_family = routed_turn.get("family") if routed_turn.get("served") else None
        judge_sampling = await _judge_sampling(routed_turn)
        risk = (state.get("classification") or {}).get("risk") if routed_turn else None

        # WP-21 — ¿ahora o después? El grader es la mayor partida de coste
        # y latencia que no produce la respuesta; graduarlo todo en el
        # camino crítico paga ese precio también en el turno que solo dice
        # "gracias".
        decision = grading_decide(
            # WP-20 — el presupuesto blando apaga el grader igual que si
            # el agent_config lo tuviera desactivado: es una de las dos
            # palancas de coste que no degradan lo que el cliente percibe.
            grader_enabled=bool(flags.get("outcome_grader"))
            and not state.get("budget_disable_grader"),
            grader_mode=str(flags.get("grader_mode") or "sampled"),
            sample_rate=float(flags.get("grader_sample_rate") or 0),
            intent=state.get("intent"),
            wrote=turn_writes(
                state.get("tool_calls") or [],
                await load_read_only_tools(),
            ),
            # El id del mensaje entrante identifica el turno de forma
            # estable: reintentarlo toma la MISMA decisión de muestreo.
            turn_key=str(state.get("inbound_message_id") or state.get("conversation_id") or ""),
            judge_sampling=judge_sampling,
            risk=risk if isinstance(risk, str) else None,
        )
        if decision.mode == "off":
            return {"outcome_overall": "skipped", "outcome_retries": 0, "outcome_feedback": ""}
        if decision.is_deferred:
            log.info(
                "outcome_grader.deferred",
                tenant_id=str(tenant_id),
                intent=state.get("intent"),
                reason=decision.reason,
            )
            # ``deferred`` no es ``skipped``: el checkpoint lo distingue
            # para publicar el trabajo, y el panel puede mostrar "pendiente
            # de graduar" en vez de "sin graduar", que significan cosas
            # distintas para quien audita una conversación.
            return {"outcome_overall": "deferred", "outcome_retries": 0, "outcome_feedback": ""}

        intent = state.get("intent") or "fallback"
        rubric_intent = rubric_for_intent(intent)
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

        # Spec 047 (42.5): the judge is of another family than the model that
        # wrote the draft. Only said when the turn was routed — a grader of
        # today does not take the argument.
        family_kw: dict[str, Any] = (
            {"judged_family": judged_family} if judged_family is not None else {}
        )

        # First grading attempt against the original draft.
        verdict = await grader.grade(
            tenant_id=tenant_id,
            intent=rubric_intent,
            rubric_body=rubric_body,
            draft_response=draft,
            tool_envelopes=envelopes,
            **family_kw,
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
                **family_kw,
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


async def _judge_sampling(routed_turn: dict[str, Any]) -> str | float | None:
    """The judge sampling the profile sets for the turn's conversation task
    (``router-and-catalog.md`` §3), or None for a turn that was not routed."""
    profile_name, task = routed_turn.get("profile"), routed_turn.get("task")
    if not routed_turn.get("served") or not isinstance(profile_name, str) or not task:
        return None
    snapshot = await _catalog()
    profile = snapshot.profile(profile_name) if snapshot is not None else None
    policy = profile.task(str(task)) if profile is not None else None
    return None if policy is None else policy.judge_sampling


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
        if state.get("reception_handoff") and not str(state.get("response") or "").strip():
            # Spec 047 (requisito 53): Recepción derivó sin decir nada; no hay
            # respuesta que envolver (la da el destino en su pasada).
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


# Threshold above which the plain-text answer is treated as a duplicate of
# the interactive component's ``body`` and therefore NOT sent as its own
# message. The model routinely paraphrases the same sentence into both the
# free text AND the interactive body (e.g. "Completa tu compra acá 👉" as
# text plus "¡Listo! Completa tu compra en el siguiente enlace" as the
# button body), which reaches the customer as two near-identical messages.
# 0.6 catches paraphrases while leaving genuinely distinct explanations
# (a product summary before an actionable button) as their own message.
_TEXT_BODY_DUP_RATIO = 0.6


def _normalise_for_dup(text: str) -> str:
    """Lowercase, drop emojis/punctuation, collapse whitespace — so the
    duplicate check compares meaning, not decoration."""
    lowered = text.lower()
    # Keep letters (incl. accented), digits and spaces; drop the rest.
    stripped = re.sub(r"[^0-9a-záéíóúñü ]+", " ", lowered)
    return re.sub(r"\s+", " ", stripped).strip()


def _text_duplicates_body(text: str, body: str) -> bool:
    """True when the free-text answer is redundant with the interactive
    body and should be suppressed to avoid a double send.

    Redundant when, after normalisation, one contains the other or the
    two are at least ``_TEXT_BODY_DUP_RATIO`` similar. Empty inputs are
    never duplicates (nothing to suppress)."""
    a = _normalise_for_dup(text)
    b = _normalise_for_dup(body)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= _TEXT_BODY_DUP_RATIO


# How far back to look for an already-sent identical checkout link. Scopes
# the resend guard to the active buying session — a customer returning days
# later with a genuinely new cart gets a fresh link (the URL differs anyway
# once the cart changes).
_CHECKOUT_RESEND_WINDOW = timedelta(hours=12)

# Short human reply sent instead of re-pushing an identical payment link
# when the customer just acknowledges ("gracias", "voy en camino"). Keeps
# the conversation alive without spamming the "Pagar ahora" card again.
_LINK_ALREADY_SENT_ACK = (
    "Quedo atento por acá. El link para completar tu pedido te lo dejé más arriba. 🙌"
)


def _checkout_url_from_interactive(interactive: dict[str, Any] | None) -> str | None:
    """Return the checkout/payment URL when the interactive component is a
    ``cta_url`` link, else None. Only ``cta_url`` components carry a link we
    guard against re-sending; buttons / lists / product cards are untouched."""
    if not interactive:
        return None
    cta = interactive.get("cta_url")
    if isinstance(cta, dict):
        url = str(cta.get("url") or "").strip()
        return url or None
    return None


async def _checkout_link_already_sent(session: Any, conversation_id: uuid.UUID, url: str) -> bool:
    """True when an identical checkout link was already sent on this
    conversation within ``_CHECKOUT_RESEND_WINDOW``.

    Guards the cross-turn resend loop: after the link is out, a customer
    "gracias" / "voy en camino" must not trigger the same "Pagar ahora"
    card again. Scoped to a recent window so a genuinely new order (whose
    URL differs once the cart changes) is never blocked. Runs inside the
    caller's tenant-scoped session (RLS limits it to this tenant)."""
    from nexus_api.db.models import Message, MessageDirection
    from sqlalchemy import func, select

    cutoff = datetime.now(UTC) - _CHECKOUT_RESEND_WINDOW
    stmt = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.interactive_payload["cta_url"]["url"].astext == url,
            Message.created_at >= cutoff,
        )
    )
    count = await session.scalar(stmt)
    return bool(count and count > 0)


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

        # Same-turn duplicate guard (G-1): when the turn carries an
        # interactive component whose ``body`` already says what the free
        # text says, suppress the separate text row so the customer gets ONE
        # message, not two paraphrases (barbersupply "Pagar ahora" incident).
        interactive_body = str((interactive or {}).get("body") or "") if interactive else ""
        text_is_redundant = bool(
            interactive_body and _text_duplicates_body(response_text, interactive_body)
        )

        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            # Cross-turn resend guard (G-1): if the interactive is a payment
            # link we already sent on this conversation recently, don't push
            # the same "Pagar ahora" card again — the customer is just
            # acknowledging. Drop the interactive; keep a reply so they are
            # not ghosted.
            checkout_url = _checkout_url_from_interactive(interactive)
            suppress_interactive = bool(checkout_url) and await _checkout_link_already_sent(
                session, conv_id, checkout_url or ""
            )

            # Decide the text row. Normally: write the free text unless it is
            # a duplicate of the interactive body. But when we are dropping a
            # duplicate payment link AND have no distinct text to send, fall
            # back to a short human ack so the customer still gets a reply.
            write_text = bool(response_text.strip()) and not text_is_redundant
            text_to_write = response_text
            if suppress_interactive and not write_text:
                text_to_write = _LINK_ALREADY_SENT_ACK
                write_text = True

            # Row 1: plain-text answer, written first so the outbound
            # dispatcher (ordered by created_at / sequence) drains text
            # before any interactive component.
            graded_message_id: uuid.UUID | None = None
            if write_text:
                text_row = await persist_outbound_message(
                    session,
                    conversation_id=conv_id,
                    agent_id=_agent_uuid(state),
                    content=text_to_write,
                    intent=intent,
                    model=model,
                    tool_calls=tool_calls,
                    outcome_overall=outcome_overall,
                    outcome_retries=outcome_retries,
                    outcome_feedback=outcome_feedback,
                )
                graded_message_id = text_row.id
                sources = list(state.get("knowledge_sources") or [])
                if sources:
                    session.add(
                        TurnSource(
                            tenant_id=tenant_id,
                            message_id=text_row.id,
                            agent_id=_agent_uuid(state),
                            sources=sources,
                        )
                    )

            # Row 2: interactive component, when the agent called
            # ``response.send_interactive`` this turn AND it is not a
            # duplicate payment link. The dispatcher detects
            # ``interactive_payload IS NOT NULL`` and routes through
            # ``adapter.send_interactive``; ``content`` is the body so the
            # operator panel renders a sensible preview.
            if interactive and not suppress_interactive:
                body = str(interactive.get("body") or response_text or "[interactive]")
                await persist_outbound_message(
                    session,
                    conversation_id=conv_id,
                    agent_id=_agent_uuid(state),
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
        # Spec 030: the agent's reply shows up live in the Inbox (after the
        # commit above, without a body).
        await publish_inbox_event(
            None,
            tenant_id=tenant_id,
            event="message.new",
            conversation_id=conv_id,
            message_id=str(graded_message_id) if graded_message_id else None,
            direction="outbound",
        )
        # WP-21 — el turno salió sin graduar. Se publica AQUÍ y no en el
        # nodo del grader porque solo aquí existe ya la fila del mensaje:
        # el veredicto diferido se escribe encima de ella, y sin su id el
        # consumidor tendría que adivinar cuál era "el último saliente"
        # de la conversación — que con dos filas por turno (texto +
        # interactivo) o con turnos solapados es exactamente el tipo de
        # suposición que acaba escribiendo el veredicto en el mensaje
        # equivocado.
        if outcome_overall == "deferred" and graded_message_id is not None:
            await publish_grade_job(
                tenant_id=tenant_id,
                conversation_id=conv_id,
                message_id=graded_message_id,
                intent=intent or "fallback",
                user_message=str(state.get("user_message") or ""),
                response=response_text,
                tool_calls=tool_calls,
            )

        # WP-13: the end-of-turn checkpoint is the one that persists until
        # retention prunes it — shrink it (history reloads from Postgres
        # next turn; oversized tool dumps get clamped with a marker).
        return checkpoint_shrink_update(state)

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
    g.add_node("classify", _traced("classify", make_classify_node(agent_loader, llm_router)))
    for intent in VALID_INTENTS:
        g.add_node(
            intent,
            _traced(intent, make_handler_node(intent, agent_loader, llm_router, registry)),
        )
    g.add_node(
        "grade_outcome",
        _traced(
            "grade_outcome",
            make_grade_outcome_node(grader=outcome_grader, llm_router=llm_router),
        ),
    )
    g.add_node(
        "ucm_formatter",
        _traced("ucm_formatter", make_ucm_formatter_node(enabled=use_ucm_formatter)),
    )
    g.add_node("checkpoint", _traced("checkpoint", make_checkpoint_node()))

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
