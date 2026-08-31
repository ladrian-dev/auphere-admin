"""LLM routing — thin wrapper around LiteLLM with the contract from
architecture/agent-isolation.md garantía 7 baked in.

Roles:
- ``classify`` → Haiku 4.5
- ``respond``  → Sonnet 4.6
- ``fallback`` → GPT-4o (used when the primary call errors)

Block D adds function-calling: ``acomplete_with_tools`` accepts a list of
tool definitions filtered by the active tenant's whitelist and returns
both text and a list of tool calls the model wants to make. The pipeline
then dispatches those through ``MCPRegistry`` (which re-checks the
whitelist as defense in depth).

Batching:
- Calls go through ``litellm.acompletion`` one-at-a-time. We never aggregate
  requests across tenants. The contract is published in ``litellm_kwargs_contract``
  so the isolation tests can assert it without reaching into LiteLLM internals.

Context editing (Fase A — claude-platform-integration):
- ``LiteLLMProvider`` accepts a ``context_management`` dict and passes it
  through to ``litellm.acompletion`` *only* when tools are present (the
  classify call carries no tools and would not benefit). LiteLLM's
  Anthropic adapter auto-injects the ``context-management-2025-06-27``
  beta header — we do NOT pass it via ``extra_headers``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

import structlog
from nexus_api.core.llm_proxy import (
    apply_litellm_proxy_kwargs,
    raise_mapped_proxy_failure,
    require_current_llm_proxy_partner,
)
from nexus_api.core.metrics import (
    ISOLATION_LLM_BATCH_CROSS_TENANT,
    record_isolation_event,
)
from nexus_api.core.otel_metrics import record_llm_call
from nexus_api.core.respond_catalog import require_hop_model

from nexus_worker.metering.collector import provider_of, record_llm_usage, usage_fields
from nexus_worker.observability.tracing import record_generation

log = structlog.get_logger(__name__)


# Contract shared with the isolation suite (test_7_*). If anything here changes,
# the runtime test fails too — that's the point.
def litellm_kwargs_contract() -> dict[str, Any]:
    return {
        "enable_batching": False,
        "group_by": None,
    }


# ── resilience knobs ─────────────────────────────────────────────────────────

# Attempts per model before moving on. 1 = first try, 2 = one retry.
_MAX_ATTEMPTS_PER_MODEL = 2
# Linear backoff base, in seconds (attempt 0 → 0.5s, attempt 1 → 1.0s …).
_RETRY_BACKOFF_S = 0.5

# Transient connection/timeout failures where the socket died before the
# request completed — a stale keep-alive connection reused from the pool after
# the server closed it (litellm maps aiohttp ``ServerDisconnected`` / connect
# errors onto ``Timeout`` / ``APIConnectionError``, failing in ~1ms). Retrying
# on a fresh connection succeeds instantly, so these skip the backoff: the
# ``_RETRY_BACKOFF_S`` wait was pure added latency on every post-idle turn.
# Matched by class NAME so the router stays provider-agnostic (no litellm /
# openai import here). Rate-limit / auth / bad-request errors are deliberately
# absent — those must keep backing off, an immediate retry would just re-fail.
_FAST_RETRY_ERROR_NAMES = frozenset(
    {
        "Timeout",
        "APITimeoutError",
        "APIConnectionError",
        "ServiceUnavailableError",
        "InternalServerError",
    }
)


def _is_fast_retry_error(exc: BaseException) -> bool:
    """True for transient connection/timeout errors that should retry with no
    backoff (a dead pooled socket), False for anything else (rate limits, …)."""
    return type(exc).__name__ in _FAST_RETRY_ERROR_NAMES


# ── latency / cache observability ────────────────────────────────────────────


# Which token-usage fields we surface on ``llm.call_complete``. ``cache_read``
# > 0 means the Anthropic prompt cache HIT (the ~90% input discount + latency
# drop); ``cache_creation`` > 0 means we paid to write the cache this call. If
# every call shows cache_read=0 the caching is not working and that alone
# explains slow turns — the exact question "why are all agents slow" needs.
#
# The extractor itself moved to ``metering.collector``: the multimodal
# processor calls litellm directly (vision, transcription) and needs the same
# parsing to bill those calls. Re-exported under the old private name so the
# resilience tests keep importing it from here.
_usage_fields = usage_fields


# Return type of a resilient call — preserved through ``_call_with_resilience``.
_T = TypeVar("_T")


# ── context editing (Fase A — claude-platform-integration) ───────────────────

# Default ``context_management`` payload sent to Anthropic alongside tools.
# ``clear_tool_uses_20250919`` trims older tool_use/tool_result pairs out of
# the messages once the prefix grows past ``trigger.value`` tokens, keeping the
# last ``keep.value`` tool uses verbatim. The Anthropic server applies the
# edit and reports what it cleared in ``response.context_management.applied_edits``.
#
# Numbers picked to match the docs' default and not impact short turns:
# - trigger 30k input_tokens: only fires on long ReAct loops (booking with
#   availability scans, ecommerce catalog searches) — typical chit-chat
#   turns stay below the threshold and pay nothing.
# - keep 3 most recent tool_uses: enough for the model to follow the
#   immediate chain of evidence; older invocations are summarised away.
# - clear_at_least 5k: avoid death by paper cuts (trim only when there is
#   meaningful bloat to remove).
DEFAULT_CONTEXT_MANAGEMENT: dict[str, Any] = {
    "edits": [
        {
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": 30_000},
            "keep": {"type": "tool_uses", "value": 3},
            "clear_at_least": {"type": "input_tokens", "value": 5_000},
            "exclude_tools": [],
        }
    ]
}


def default_context_management_from_env() -> dict[str, Any] | None:
    """Return the default ``context_management`` payload, or ``None`` when
    the feature is disabled via ``NEXUS_CONTEXT_EDITING_ENABLED=0``.

    Read at provider-construction time so a deploy with the env var flipped
    immediately stops emitting the field (rollback per §A.7 of the feature
    spec). Tests pass an explicit ``context_management`` to override.
    """
    flag = os.getenv("NEXUS_CONTEXT_EDITING_ENABLED", "1")
    if flag.strip().lower() in {"0", "false", "no", "off", ""}:
        return None
    return DEFAULT_CONTEXT_MANAGEMENT


def _cache_the_tail(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Segundo punto de corte, móvil, sobre el último mensaje.

    El corte del prefijo cachea el prompt de sistema y las definiciones de
    herramientas. Todo lo que viene después —historial, mensajes del asistente
    y resultados de herramientas— se reenvía **entero y sin cachear** en cada
    pasada del bucle, y en un agente que da doce pasadas eso crece de forma
    cuadrática: medido en el Companion, 42.000 tokens de entrada no cacheada en
    un turno de ocho pasadas frente a los 12.000 que costaría con este corte.

    Anthropic admite cuatro puntos por petición y el prefijo usa uno; este es
    el segundo. Se mueve con la conversación: como cachea *todo lo anterior a
    él*, ponerlo en el último mensaje convierte el historial de la pasada N en
    prefijo cacheado de la pasada N+1.

    Los bloques de texto se convierten a la forma canónica de Anthropic porque
    ``cache_control`` vive en el bloque, no en el mensaje. Un mensaje cuyo
    contenido no sea texto se deja intacto: no es sitio para un punto de corte
    y forzarlo es un 400.
    """
    if not messages:
        return messages
    tail = messages[-1]
    content = tail.get("content")
    if isinstance(content, str):
        if not content:
            return messages
        blocks: list[dict[str, Any]] = [{"type": "text", "text": content}]
    elif isinstance(content, list) and content:
        blocks = [dict(b) for b in content if isinstance(b, dict)]
        if not blocks or blocks[-1].get("type") != "text":
            return messages
    else:
        return messages
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    return [*messages[:-1], {**tail, "content": blocks}]


def _with_prompt_caching(
    messages: list[dict[str, Any]], *, cache_tail: bool = False
) -> list[dict[str, Any]]:
    """Mark the leading system prefix as an Anthropic cache breakpoint.

    Anthropic prompt caching: a ``cache_control`` block caches the entire
    prefix up to it (tools + every earlier system block). The agent's
    system prefix — rendered system prompt + KG snapshot + channel/turn
    notes — is stable across a conversation, so one breakpoint on the last
    system block yields a ~90% input-token discount and a latency drop on
    cache hits. Content below the model minimum (1024 tokens for Sonnet,
    4096 for Haiku) is silently not cached — no error, no cost.

    We merge the contiguous leading ``system`` messages into a single
    system message with text blocks (Anthropic's canonical shape) and put
    ``cache_control`` on the last block. Non-system messages (history, the
    user turn, tool round-trips) stay after the breakpoint, uncached.
    """
    leading: list[dict[str, Any]] = []
    rest_start = 0
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            leading.append(m)
            rest_start = i + 1
        else:
            break
    if not leading:
        return _cache_the_tail(messages) if cache_tail else messages

    blocks: list[dict[str, Any]] = []
    for m in leading:
        content = m.get("content")
        if isinstance(content, str):
            blocks.append({"type": "text", "text": content})
        elif isinstance(content, list):
            blocks.extend(content)
    if not blocks:
        return messages

    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    merged = {"role": "system", "content": blocks}
    rest = messages[rest_start:]
    if cache_tail:
        rest = _cache_the_tail(rest)
    return [merged, *rest]


# ── data shapes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolCall:
    """A function-call request emitted by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """Unified result for both plain ``acomplete`` and ``acomplete_with_tools``."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class LLMCall:
    """Auditable record of a provider invocation."""

    tenant_id: uuid.UUID
    role: str
    model: str
    messages: list[dict[str, str]]
    tools: tuple[dict[str, Any], ...] = ()
    # ``extra`` captures any Anthropic-specific kwargs we pass through
    # to LiteLLM that don't fit the OpenAI shape. Today populated by
    # Fase D (Skills): ``container={"skills": [...]}`` +
    # ``extra_headers={"anthropic-beta": "..."}``. Future betas
    # (mcp_servers for Fase E, dreaming for Fase F) plug in the same way
    # without changing the protocol.
    extra: dict[str, Any] = field(default_factory=dict)


# ── provider protocol ────────────────────────────────────────────────────────


class LLMProvider(Protocol):
    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str: ...

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = ...,
    ) -> LLMResponse: ...

    def astream_complete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        extra: dict[str, Any] | None = ...,
    ) -> AsyncIterator[tuple[str, str]]: ...

    def astream_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = ...,
    ) -> AsyncIterator[tuple[str, str]]: ...


# ── in-memory provider ───────────────────────────────────────────────────────


@dataclass
class InMemoryProvider:
    """Test provider. Records every call (including the ``tools`` argument)
    and returns a canned response per role.

    Two configurable hooks:

    - ``responder``: ``LLMCall -> str``. Plain text response. Default echoes
      a deterministic string.
    - ``tool_caller``: ``LLMCall -> list[ToolCall]``. Optional. Used by
      ``acomplete_with_tools`` to script the tool calls the LLM emits — the
      defining feature of function-calling tests. Default: no tool calls.
    """

    calls: list[LLMCall] = field(default_factory=list)
    responder: Callable[[LLMCall], str] | None = None
    tool_caller: Callable[[LLMCall], list[ToolCall]] | None = None
    # Scripted extras for ``astream_complete``: what the summarised
    # thinking looks like, and the usage the provider would report.
    thinking_text: str = ""
    stream_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 100, "completion_tokens": 20}
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def _record_like_the_canal(self, *, role: str, model: str) -> dict[str, int]:
        """Same choke point as ``LiteLLMProvider._record_call`` for OTel.

        The Companion graph (and every other caller) talks to this double in
        tests. Without this, ``record_llm_call`` only ran on the real
        provider and a Companion turn with ``cache_read > 0`` never appeared
        on ``llm_tokens_total`` — the P5 ratio would look like the cache
        was dead. Native keys, existing ``role`` label (``companion`` when
        the graph asks for it). No partner dimension (WP-15).
        """
        usage = {k: int(v) for k, v in dict(self.stream_usage).items()}
        record_llm_call(model=model, role=role, duration_ms=0.0, usage=usage)
        return usage

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        call = LLMCall(tenant_id=tenant_id, role=role, model=model, messages=list(messages))
        async with self._lock:
            self.calls.append(call)
        if self.responder is None:
            return f"[{role}:{model}] ok"
        return self.responder(call)

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        call = LLMCall(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=list(messages),
            tools=tuple(tools),
            extra=dict(extra) if extra else {},
        )
        async with self._lock:
            self.calls.append(call)
        emitted: list[ToolCall] = []
        if self.tool_caller is not None:
            emitted = list(self.tool_caller(call))
        text = self.responder(call) if self.responder else f"[{role}:{model}] ok"
        return LLMResponse(text=text, tool_calls=tuple(emitted))

    async def astream_complete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Streaming stand-in: records the call (``extra`` included, so a
        test can assert the ``thinking`` parameter is really being sent) and
        chops the canned answer into word-sized deltas."""
        call = LLMCall(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=list(messages),
            extra=dict(extra) if extra else {},
        )
        async with self._lock:
            self.calls.append(call)
        if self.thinking_text:
            yield ("thinking", self.thinking_text)
        text = self.responder(call) if self.responder else f"[{role}:{model}] ok"
        for i, word in enumerate(text.split(" ")):
            yield ("text", word if i == 0 else f" {word}")
        yield ("usage", json.dumps(self._record_like_the_canal(role=role, model=model)))

    async def astream_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Doble del bucle de herramientas: ``tool_caller`` guiona lo que
        el modelo pide en cada paso, y ``responder`` lo que escribe.

        Recibe el número de paso en ``LLMCall`` a través de la longitud de
        ``messages``, así que un ``tool_caller`` puede devolver llamadas en
        el primer paso y ninguna en el segundo — que es exactamente la
        forma de un bucle real.
        """
        call = LLMCall(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=list(messages),
            tools=tuple(tools),
            extra=dict(extra) if extra else {},
        )
        async with self._lock:
            self.calls.append(call)
        if self.thinking_text:
            yield ("thinking", self.thinking_text)

        emitted = list(self.tool_caller(call)) if self.tool_caller else []
        text = (
            "" if emitted else (self.responder(call) if self.responder else f"[{role}:{model}] ok")
        )
        for i, word in enumerate(text.split(" ")) if text else ():
            yield ("text", word if i == 0 else f" {word}")
        for tc in emitted:
            yield (
                "tool_call",
                json.dumps({"id": tc.id, "name": tc.name, "arguments": tc.arguments}),
            )
        yield (
            "assistant",
            json.dumps(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in emitted
                    ]
                    or None,
                }
            ),
        )
        yield ("usage", json.dumps(self._record_like_the_canal(role=role, model=model)))


def _thinking_pieces(delta: Any) -> list[tuple[str, dict[str, Any] | None]]:
    """Trozos de pensamiento de un ``delta``, con su bloque crudo si lo hay.

    LiteLLM entrega el pensamiento de dos formas según el proveedor y la
    versión: como cadena en ``reasoning_content`` o como lista de bloques en
    ``thinking_blocks``. El bloque crudo importa porque lleva la ``signature``
    que Anthropic exige de vuelta.
    """
    out: list[tuple[str, dict[str, Any] | None]] = []
    blocks = getattr(delta, "thinking_blocks", None)
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict):
                piece = block.get("thinking") or block.get("text") or ""
                out.append((str(piece), block))
    reasoning = getattr(delta, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning and not out:
        out.append((reasoning, None))
    return out


def _accumulate_tool_call(pending: dict[int, dict[str, Any]], raw: Any) -> None:
    """Junta los fragmentos de una llamada a herramienta.

    El proveedor manda el ``id`` y el nombre en el primer fragmento y los
    argumentos a cachos de JSON en los siguientes. El único identificador
    estable entre ellos es el ``index``.
    """
    index = getattr(raw, "index", None)
    if index is None:
        index = len(pending)
    slot = pending.setdefault(int(index), {"id": "", "name": "", "arguments": ""})
    call_id = getattr(raw, "id", None)
    if call_id:
        slot["id"] = str(call_id)
    function = getattr(raw, "function", None)
    if function is None:
        return
    name = getattr(function, "name", None)
    if name:
        slot["name"] = str(slot["name"]) + str(name)
    args = getattr(function, "arguments", None)
    if args:
        slot["arguments"] = str(slot["arguments"]) + str(args)


def _finish_tool_call(slot: dict[str, Any]) -> dict[str, Any]:
    """Cierra una llamada acumulada. Unos argumentos que no parsean se
    entregan vacíos: el ejecutor los rechazará con un mensaje que el modelo
    puede corregir, que es mejor que tirar el turno entero."""
    raw = str(slot.get("arguments") or "")
    try:
        arguments = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return {
        "id": str(slot.get("id") or uuid.uuid4().hex[:12]),
        "name": str(slot.get("name") or ""),
        "arguments": arguments,
    }


_ANTHROPIC_ONLY_ON_OPENAI = ("thinking", "context_management")


def _drop_openai_unsupported(kwargs: dict[str, Any]) -> dict[str, Any]:
    """LiteLLM 1.83 raises UnsupportedParamsError in-process for Anthropic-only
    kwargs on openai hops (drop_params=False). Companion always sends thinking;
    the handler also sends context_management when there are tools. Strip them
    here so the hop reaches the proxy.

    GPT-5.4+/5.6 Chat Completions reject function tools unless
    ``reasoning_effort`` is exactly ``none``. Sol/Terra/Luna default is
    ``medium``; omitting the field is still not none. Set it explicitly
    when tools are present. Stay on ``acompletion`` — no Responses API.

    The staging proxy (LiteLLM 1.74.15) registers Sol/Terra/Luna as bare
    OpenAI aliases, so its param validator 400s ``reasoning_effort``
    unless the TOP-LEVEL HTTP body also carries
    ``allowed_openai_params=["reasoning_effort"]`` (probed 2026-08-30:
    both keys top-level → 200 with tool_calls).

    Both keys go through ``extra_body``, NOT as litellm kwargs, on
    purpose: the OpenAI SDK merges ``extra_body`` into the top level of
    the outgoing JSON, which reproduces the verified probe exactly. As
    kwargs, litellm ≥1.83 does two different things instead
    (``responses_api_bridge_check``): ``reasoning_effort`` + tools on a
    gpt-5.4+ model silently reroutes the call to ``/responses``, and
    ``allowed_openai_params`` is consumed client-side and never
    forwarded. Verified against this venv's litellm with an HTTP echo
    server (2026-08-30).
    """
    model = kwargs.get("model")
    if isinstance(model, str) and model.startswith("openai/"):
        for key in _ANTHROPIC_ONLY_ON_OPENAI:
            kwargs.pop(key, None)
        tools = kwargs.get("tools")
        if isinstance(tools, list) and tools:
            # A top-level kwarg would trigger the Responses-API bridge.
            kwargs.pop("reasoning_effort", None)
            extra_body = kwargs.get("extra_body")
            if not isinstance(extra_body, dict):
                extra_body = {}
                kwargs["extra_body"] = extra_body
            extra_body["reasoning_effort"] = "none"
            extra_body["allowed_openai_params"] = ["reasoning_effort"]
    return kwargs


def _proxy_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Stamp the partner virtual key. Console-injected auth is dropped."""
    require_current_llm_proxy_partner()
    apply_litellm_proxy_kwargs(kwargs)
    return kwargs


#: Dot → double underscore, same transport contract as
#: ``runtime/companion/tools.py``. GPT-5.6 rejects dots in function names
#: (``Invalid 'tools[0].function.name': string does not match pattern`` —
#: probed 2026-08-31 against the staging proxy), and the whole tool catalog
#: uses dotted names (``booking.check_availability``). The catalog is NOT
#: renamed — dotted names are contract in the UI, evals and audit — so the
#: restriction is solved at the transport, exactly like the Companion does.
_WIRE_SEPARATOR = "__"
_OPENAI_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _wire_openai_tool_names(kwargs: dict[str, Any]) -> dict[str, str]:
    """Rewrite dotted tool names to their wire form for openai/ hops.

    Touches ``tools[]`` and the assistant ``tool_calls`` echoes in the
    message history (OpenAI validates those against the same pattern, and
    the tool-free final iteration still carries the history). Non-streaming
    only: the streaming paths are Companion-only and already send wire
    names. Returns the wire→catalog back-map; empty when nothing changed.
    """
    model = kwargs.get("model")
    if not (isinstance(model, str) and model.startswith("openai/")) or kwargs.get("stream"):
        return {}

    back: dict[str, str] = {}
    tools = kwargs.get("tools")
    if isinstance(tools, list) and tools:
        seen: dict[str, str] = {}
        wired_tools: list[Any] = []
        for spec in tools:
            function = spec.get("function") if isinstance(spec, dict) else None
            if isinstance(function, dict):
                name = str(function.get("name") or "")
                wire = name.replace(".", _WIRE_SEPARATOR)
                if seen.setdefault(wire, name) != name:
                    raise RuntimeError(f"{name!r} and {seen[wire]!r} collide on wire name {wire!r}")
                if wire != name:
                    if not _OPENAI_TOOL_NAME.match(wire):
                        raise RuntimeError(
                            f"tool name {name!r} is invalid on the wire even as {wire!r}"
                        )
                    back[wire] = name
                    spec = {**spec, "function": {**function, "name": wire}}
            wired_tools.append(spec)
        if back:
            kwargs["tools"] = wired_tools

    messages = kwargs.get("messages")
    if isinstance(messages, list):
        rewritten: list[Any] = []
        changed = False
        for message in messages:
            calls = message.get("tool_calls") if isinstance(message, dict) else None
            if isinstance(calls, list) and calls:
                new_calls: list[Any] = []
                for call in calls:
                    function = call.get("function") if isinstance(call, dict) else None
                    if isinstance(function, dict):
                        name = str(function.get("name") or "")
                        wire = name.replace(".", _WIRE_SEPARATOR)
                        if wire != name:
                            call = {**call, "function": {**function, "name": wire}}
                            changed = True
                    new_calls.append(call)
                message = {**message, "tool_calls": new_calls}
            rewritten.append(message)
        if changed:
            kwargs["messages"] = rewritten

    return back


def _unwire_response_tool_calls(response: Any, back: dict[str, str]) -> None:
    """Map the provider's wire tool names back to catalog names, in place.
    Handles both dict-shaped responses (tests) and litellm ModelResponse."""
    try:
        choices = response["choices"]
    except (TypeError, KeyError, IndexError):
        choices = getattr(response, "choices", None)
    for choice in choices or []:
        message = (
            choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        )
        calls = (
            message.get("tool_calls")
            if isinstance(message, dict)
            else getattr(message, "tool_calls", None)
        )
        for call in calls or []:
            function = (
                call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
            )
            if function is None:
                continue
            name = (
                function.get("name")
                if isinstance(function, dict)
                else getattr(function, "name", None)
            )
            if isinstance(name, str) and name in back:
                if isinstance(function, dict):
                    function["name"] = back[name]
                else:
                    function.name = back[name]


async def _proxied_acompletion(litellm: Any, kwargs: dict[str, Any]) -> Any:
    """Single hop: catalog id, same api_base, no vendor fallback."""
    model = kwargs.get("model")
    require_hop_model(model if isinstance(model, str) else "")
    _proxy_kwargs(kwargs)
    _drop_openai_unsupported(kwargs)
    back = _wire_openai_tool_names(kwargs)
    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:
        raise_mapped_proxy_failure(exc)
        raise
    if back:
        _unwire_response_tool_calls(response, back)
    return response


# ── litellm provider ─────────────────────────────────────────────────────────


@dataclass
class LiteLLMProvider:
    """Real provider. Imports LiteLLM eagerly in ``__post_init__`` so the
    sync ``sys.path.append(os.getcwd())`` LiteLLM does on first import
    happens at construction (server startup, off the event loop) — not
    inside the first ASGI request, where blockbuster (LangGraph dev)
    rejects it. Tests use ``InMemoryProvider`` and never instantiate
    this class, so the heavy import stays out of the unit-test path.

    ``context_management`` controls the Anthropic context-editing feature
    (Fase A — claude-platform-integration). When set, the dict is forwarded
    to ``litellm.acompletion`` on every call that carries tools (handler
    ReAct loops). LiteLLM's Anthropic adapter takes care of adding the
    ``context-management-2025-06-27`` beta header automatically — see
    ``litellm/llms/anthropic/chat/transformation.py::_ensure_context_management_beta_header``.

    Pass ``context_management=None`` (e.g. tests, or via
    ``NEXUS_CONTEXT_EDITING_ENABLED=0``) to disable the feature without
    code changes. The classify call never carries tools, so context
    editing is a no-op for it regardless.
    """

    timeout_s: float = 30.0
    context_management: dict[str, Any] | None = field(
        default_factory=default_context_management_from_env
    )
    #: Segundo punto de corte de caché, móvil, sobre el último mensaje
    #: (:func:`_cache_the_tail`). **Apagado por defecto**: el agente de cliente
    #: y los dos playgrounds usan este mismo proveedor y son carga viva, así
    #: que cambiarles el comportamiento para arreglar un problema del Companion
    #: es exactamente cómo se rompe algo que funcionaba.
    #:
    #: Lo enciende quien tenga un bucle agéntico largo, que es donde el
    #: historial sin cachear crece de forma cuadrática. Se generaliza —o no—
    #: cuando haya semanas de ``cache_read`` medido en producción.
    cache_tail: bool = False

    def __post_init__(self) -> None:
        # Pre-import litellm so the first acomplete() doesn't pay the
        # synchronous ``sys.path.append(os.getcwd())`` at import time
        # during a request. Cached in module-level state thereafter.
        import litellm  # noqa: F401

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        response = await self._raw_complete(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=messages,
            tools=None,
        )
        choices = response["choices"]
        if not choices:
            raise RuntimeError("provider returned no choices")
        return str(choices[0]["message"]["content"] or "")

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        response = await self._raw_complete(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=messages,
            tools=tools or None,
            extra=extra,
        )
        choices = response["choices"]
        if not choices:
            raise RuntimeError("provider returned no choices")
        msg = choices[0]["message"]
        text = str(msg.get("content") or "")
        emitted: list[ToolCall] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or {}
            args_raw = fn.get("arguments")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except json.JSONDecodeError:
                args = {}
            emitted.append(
                ToolCall(
                    id=str(raw.get("id") or ""),
                    name=str(fn.get("name") or ""),
                    arguments=args,
                )
            )
        return LLMResponse(text=text, tool_calls=tuple(emitted))

    async def _raw_complete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None,
        extra: dict[str, Any] | None = None,
    ) -> Any:
        import litellm  # local import — heavy dep

        kwargs: dict[str, Any] = {
            "model": model,
            # Prompt caching: mark the stable system prefix as a cache
            # breakpoint so repeated turns / loop iterations reuse it.
            "messages": _with_prompt_caching(messages, cache_tail=self.cache_tail),
            "metadata": {"tenant_id": str(tenant_id), "role": role},
            "timeout": self.timeout_s,
        }
        if tools:
            kwargs["tools"] = tools
            # Context editing only makes sense for calls that carry tools —
            # ``clear_tool_uses_20250919`` operates on the tool_use /
            # tool_result pairs in messages. classify() carries no tools so
            # we skip the field there entirely (no beta header, no edits).
            if self.context_management is not None:
                kwargs["context_management"] = self.context_management
        # Per-call passthrough for Anthropic-specific kwargs (Fase D
        # Skills: ``container``, ``extra_headers``; future Fase E/F can
        # plug ``mcp_servers`` here without touching the protocol). We
        # MERGE rather than overwrite so cache_control / context_management
        # set above survive; if the caller intentionally wants to replace
        # them they pass the same key in ``extra`` and that wins.
        if extra:
            for key, value in extra.items():
                if key == "extra_headers" and "extra_headers" in kwargs:
                    # Anthropic headers — combine instead of clobber so a
                    # caller that adds Skills betas doesn't drop the
                    # context-management beta LiteLLM injected itself.
                    merged = dict(kwargs.get("extra_headers") or {})
                    merged.update(value or {})
                    kwargs["extra_headers"] = merged
                else:
                    kwargs[key] = value

        # Sanity: if a future change ever turns batching on globally, surface it
        # immediately rather than letting it ship.
        global_router = getattr(litellm, "default_router", None)
        if global_router is not None and getattr(global_router, "enable_batching", False):
            record_isolation_event(
                ISOLATION_LLM_BATCH_CROSS_TENANT,
                tenant_id,
                {"role": role, "model": model},
            )
            raise RuntimeError(
                "litellm batching is enabled globally; refusing to invoke for "
                f"tenant {tenant_id!s} — see architecture/agent-isolation.md garantía 7"
            )

        # Per-call latency + token/cache telemetry. This is the single choke
        # point every litellm call (classify, respond, grader, multimodal) of
        # every agent flows through, so one INFO event here gives us the whole
        # latency picture we were missing — where turn time goes and whether
        # the Anthropic prompt cache is actually hitting (cache_read > 0).
        started = time.perf_counter()
        response = await _proxied_acompletion(litellm, kwargs)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        await self._record_call(
            tenant_id=tenant_id,
            role=role,
            model=model,
            elapsed_ms=elapsed_ms,
            has_tools=bool(tools),
            usage_counts=usage_fields(response),
        )
        return response

    async def astream_complete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Streaming completion — yields ``(kind, text)`` with ``kind`` in
        ``{"text", "thinking"}``, then a final ``("usage", json)`` chunk.

        Built for the Companion (CO-01): its drawer has to show words
        appearing, and the honest context-window meter needs the
        ``input_tokens`` the provider reports for THIS call — an estimate
        from characters would miss the system prompt, the tool definitions
        and the tool results, which are most of the prefix in this agent.

        The post-call telemetry is the SAME ``_record_call`` the buffered
        path uses. That matters more than it looks: ``record_llm_usage`` is
        the single choke point every LLM call in the system flows through,
        and a second streaming path with its own copy would silently stop
        billing the Companion the first time one of the two drifted.
        """
        import litellm  # local import — heavy dep

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _with_prompt_caching(messages, cache_tail=self.cache_tail),
            "metadata": {"tenant_id": str(tenant_id), "role": role},
            "timeout": self.timeout_s,
            "stream": True,
            # Without this the final chunk carries no usage and both the
            # cost meter and the context-window meter go blind.
            "stream_options": {"include_usage": True},
        }
        for key, value in (extra or {}).items():
            kwargs[key] = value

        started = time.perf_counter()
        usage_counts: dict[str, int] = {}
        try:
            stream = await _proxied_acompletion(litellm, kwargs)
            async for chunk in stream:
                chunk_usage = usage_fields(chunk)
                if any(chunk_usage.values()):
                    usage_counts = chunk_usage
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue
                    thinking = getattr(delta, "thinking_blocks", None) or getattr(
                        delta, "reasoning_content", None
                    )
                    if isinstance(thinking, str) and thinking:
                        yield ("thinking", thinking)
                    elif isinstance(thinking, list):
                        for block in thinking:
                            piece = (
                                block.get("thinking") or block.get("text") or ""
                                if isinstance(block, dict)
                                else ""
                            )
                            if piece:
                                yield ("thinking", str(piece))
                    content = getattr(delta, "content", None)
                    if isinstance(content, str) and content:
                        yield ("text", content)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            await self._record_call(
                tenant_id=tenant_id,
                role=role,
                model=model,
                elapsed_ms=elapsed_ms,
                has_tools=False,
                usage_counts=usage_counts,
            )
        yield ("usage", json.dumps(usage_counts))

    async def astream_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Un paso del bucle de herramientas del Companion, en streaming.

        Hermano de :meth:`astream_complete` y con la misma telemetría —el
        mismo ``_record_call``—, porque el punto de estrangulamiento del
        consumo tiene que seguir siendo uno solo. Un tercer camino con su
        propia copia dejaría de facturar el Companion en cuanto uno de los
        tres se moviera, y sin error que lo delate.

        Cede ``(kind, payload)``:

        - ``text`` / ``thinking`` — trozos, tal cual llegan;
        - ``tool_call`` — una llamada YA COMPLETA (``{id, name,
          arguments}``), no fragmentos: el proveedor manda los argumentos a
          cachos de JSON y entregarlos a medias no le sirve a nadie;
        - ``assistant`` — el mensaje del asistente reconstruido, listo para
          volver a ``messages``. Lleva los ``thinking_blocks`` con su firma:
          con pensamiento activo, Anthropic **exige** que vuelvan tal cual
          junto a los resultados de herramienta, y perderlos es un 400, no
          un detalle estético;
        - ``usage`` — el recuento final del proveedor.
        """
        import litellm  # local import — heavy dep

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _with_prompt_caching(messages, cache_tail=self.cache_tail),
            "tools": tools,
            "metadata": {"tenant_id": str(tenant_id), "role": role},
            "timeout": self.timeout_s,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        for key, value in (extra or {}).items():
            kwargs[key] = value

        started = time.perf_counter()
        usage_counts: dict[str, int] = {}
        text_parts: list[str] = []
        thinking_blocks: list[dict[str, Any]] = []
        # índice del proveedor → llamada a medio montar. El índice es el
        # único identificador estable entre fragmentos: el ``id`` llega solo
        # en el primero y el nombre puede llegar troceado.
        pending: dict[int, dict[str, Any]] = {}
        try:
            stream = await _proxied_acompletion(litellm, kwargs)
            async for chunk in stream:
                chunk_usage = usage_fields(chunk)
                if any(chunk_usage.values()):
                    usage_counts = chunk_usage
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue
                    for piece, block in _thinking_pieces(delta):
                        if block is not None:
                            thinking_blocks.append(block)
                        if piece:
                            yield ("thinking", piece)
                    content = getattr(delta, "content", None)
                    if isinstance(content, str) and content:
                        text_parts.append(content)
                        yield ("text", content)
                    for raw in getattr(delta, "tool_calls", None) or []:
                        _accumulate_tool_call(pending, raw)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            await self._record_call(
                tenant_id=tenant_id,
                role=role,
                model=model,
                elapsed_ms=elapsed_ms,
                has_tools=True,
                usage_counts=usage_counts,
            )

        emitted = [_finish_tool_call(c) for _idx, c in sorted(pending.items())]
        for call in emitted:
            yield ("tool_call", json.dumps(call))
        text = "".join(text_parts)
        assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
        if thinking_blocks:
            assistant["thinking_blocks"] = thinking_blocks
        if emitted:
            assistant["tool_calls"] = [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                }
                for c in emitted
            ]
        yield ("assistant", json.dumps(assistant))
        yield ("usage", json.dumps(usage_counts))

    async def _record_call(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        elapsed_ms: int,
        has_tools: bool,
        usage_counts: dict[str, int],
    ) -> None:
        """Telemetry + metering of one provider invocation.

        Shared by the buffered and the streaming path. One INFO event here
        gives the whole latency picture — where turn time goes and whether
        the Anthropic prompt cache is actually hitting (``cache_read`` > 0;
        if it is always zero, caching is not working and that alone
        explains slow turns).
        """
        log.info(
            "llm.call_complete",
            tenant_id=str(tenant_id),
            role=role,
            model=model,
            elapsed_ms=elapsed_ms,
            has_tools=has_tools,
            **usage_counts,
        )
        # WP-05: llm_call_ms + llm_tokens_total (the cache-read ratio panel
        # derives from these counters). Never raises.
        record_llm_call(model=model, role=role, duration_ms=elapsed_ms, usage=usage_counts)
        # WP-17: los mismos tokens, pero para FACTURAR. Las métricas de
        # arriba son agregados de observabilidad; esto es el hecho contable
        # por tenant. Mismo sitio porque es el único por el que pasan todas
        # las llamadas del sistema. Solo cuenta cantidades — el precio lo
        # pone el consumidor desde ``model_profiles``. Fuera de un turno
        # (evals, scripts) es no-op.
        record_llm_usage(
            model=model,
            provider=provider_of(model),
            usage=usage_counts,
        )
        # WP-06: hourly token counters for the cache-ratio alert. Best-effort.
        with contextlib.suppress(Exception):
            from nexus_api.core.redis_client import get_redis

            redis = get_redis()
            hour_window = int(time.time()) // 3600
            for usage_key, label in (
                ("prompt_tokens", "input"),
                ("cache_read_input_tokens", "cache_read"),
            ):
                value = usage_counts.get(usage_key)
                if value:
                    token_key = f"nexus:alert:llmtok:{label}:{hour_window}"
                    await redis.incrby(token_key, value)
                    await redis.expire(token_key, 7_200)
        # WP-02: one Langfuse generation per call, with token counts and
        # tenant_id as metadata. Noop when Langfuse is disabled; never raises.
        record_generation(
            tenant_id=tenant_id,
            role=role,
            model=model,
            usage=usage_counts,
            latency_ms=elapsed_ms,
        )


# ── Router ────────────────────────────────────────────────────────────────────


@dataclass
class LLMRouter:
    """Picks a model per role and invokes the provider — with retry and
    cross-model fallback baked in (ADR-023 / agent-quality-roadmap E4).

    Every call tries the primary model up to ``_MAX_ATTEMPTS_PER_MODEL``
    times, then the ``fallback_model``. A transient provider error
    (timeout, 5xx, quota) no longer kills the turn. The error only
    propagates if EVERY model and retry is exhausted — the caller (the
    pipeline node) then degrades gracefully.

    ``classify`` and ``respond`` are plain text completions.
    ``respond_with_tools`` is the function-calling entry point used by the
    handler ReAct loop.
    """

    provider: LLMProvider
    classify_model: str
    respond_model: str
    fallback_model: str

    async def _call_with_resilience(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        models: tuple[str, ...],
        invoke: Callable[[str], Awaitable[_T]],
    ) -> _T:
        """Run ``invoke(model)`` across ``models`` with per-model retries.

        ``invoke`` is the actual provider call, parametrised by model name.
        Returns the first success; raises the last exception only when
        every model and retry has failed.
        """
        last_exc: Exception | None = None
        for model in models:
            for attempt in range(_MAX_ATTEMPTS_PER_MODEL):
                try:
                    return await invoke(model)
                except Exception as exc:
                    last_exc = exc
                    fast_retry = _is_fast_retry_error(exc)
                    log.warning(
                        "llm.attempt_failed",
                        tenant_id=str(tenant_id),
                        role=role,
                        model=model,
                        attempt=attempt,
                        error=str(exc),
                        fast_retry=fast_retry,
                    )
                    # A dead pooled socket fails in ~1ms; retry it on a fresh
                    # connection immediately instead of paying the backoff.
                    # Everything else (rate limits, …) still backs off.
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL and not fast_retry:
                        await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
        assert last_exc is not None  # the loop ran at least once
        log.error(
            "llm.all_attempts_exhausted",
            tenant_id=str(tenant_id),
            role=role,
            models=list(models),
        )
        raise last_exc

    def _model_chain(self, primary: str, extra: Sequence[str] = ()) -> tuple[str, ...]:
        """Primary model, then the tenant's own fallbacks (WP-19), then the
        global fallback. De-duplicated, order preserved: a model repeated in
        the chain would be retried twice for nothing but latency."""
        chain = [primary, *extra]
        if self.fallback_model:
            chain.append(self.fallback_model)
        return tuple(dict.fromkeys(m for m in chain if m))

    async def classify(
        self,
        *,
        tenant_id: uuid.UUID,
        messages: list[dict[str, str]],
        models: Sequence[str] = (),
    ) -> str:
        """``models`` is the tenant's resolved chain (WP-19). Empty = the
        global classify model."""

        async def invoke(model: str) -> str:
            return await self.provider.acomplete(
                tenant_id=tenant_id,
                role="classify",
                model=model,
                messages=messages,
            )

        return await self._call_with_resilience(
            tenant_id=tenant_id,
            role="classify",
            models=tuple(models) or self._model_chain(self.classify_model),
            invoke=invoke,
        )

    async def respond(
        self,
        *,
        tenant_id: uuid.UUID,
        messages: list[dict[str, str]],
    ) -> str:
        async def invoke(model: str) -> str:
            return await self.provider.acomplete(
                tenant_id=tenant_id,
                role="respond",
                model=model,
                messages=messages,
            )

        return await self._call_with_resilience(
            tenant_id=tenant_id,
            role="respond",
            models=self._model_chain(self.respond_model),
            invoke=invoke,
        )

    async def respond_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
        model_override: str | None = None,
        fallback_override: Sequence[str] = (),
    ) -> LLMResponse:
        """Function-calling completion for the handler ReAct loop. ``role``
        is the intent (``book``, ``queue``, …) so traces can attribute the
        tool selection. Retries + falls back like every router call.

        ``extra`` carries Anthropic-specific kwargs (container, extra_headers,
        mcp_servers) the caller wants the provider to passthrough — Fase D
        Skills uses it, future Fase E (MCP connector) will too.
        """

        async def invoke(model: str) -> LLMResponse:
            return await self.provider.acomplete_with_tools(
                tenant_id=tenant_id,
                role=role,
                model=model,
                messages=messages,
                tools=tools,
                extra=extra,
            )

        return await self._call_with_resilience(
            tenant_id=tenant_id,
            role=role,
            # Per-tenant override (e.g. a latency-sensitive sales agent pinned
            # to a faster model) wins over the global respond model; the
            # tenant's own fallbacks (WP-19) go next, and the global fallback
            # always closes the chain so resilience never depends on config.
            models=self._model_chain(model_override or self.respond_model, fallback_override),
            invoke=invoke,
        )

    async def call_with_fallback(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        primary_model: str,
        messages: list[dict[str, str]],
    ) -> tuple[str, str]:
        try:
            text = await self.provider.acomplete(
                tenant_id=tenant_id,
                role=role,
                model=primary_model,
                messages=messages,
            )
            return text, primary_model
        except Exception as exc:
            log.warning(
                "llm.primary_failed_using_fallback",
                tenant_id=str(tenant_id),
                role=role,
                primary_model=primary_model,
                fallback_model=self.fallback_model,
                error=str(exc),
            )
            text = await self.provider.acomplete(
                tenant_id=tenant_id,
                role=role,
                model=self.fallback_model,
                messages=messages,
            )
            return text, self.fallback_model


def build_default_router(
    *,
    classify_model: str,
    respond_model: str,
    fallback_model: str,
    use_inmemory: bool,
) -> LLMRouter:
    provider: LLMProvider = InMemoryProvider() if use_inmemory else LiteLLMProvider()
    return LLMRouter(
        provider=provider,
        classify_model=classify_model,
        respond_model=respond_model,
        fallback_model=fallback_model,
    )


__all__ = [
    "DEFAULT_CONTEXT_MANAGEMENT",
    "InMemoryProvider",
    "LLMCall",
    "LLMProvider",
    "LLMResponse",
    "LLMRouter",
    "LiteLLMProvider",
    "ToolCall",
    "build_default_router",
    "default_context_management_from_env",
    "litellm_kwargs_contract",
]


# Re-export a typed callable shape for handlers that pass a plain function:
LLMCallable = Callable[..., Awaitable[str]]
