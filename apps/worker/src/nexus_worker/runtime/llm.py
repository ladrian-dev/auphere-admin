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
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

import structlog
from nexus_api.core.metrics import (
    ISOLATION_LLM_BATCH_CROSS_TENANT,
    record_isolation_event,
)

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

# Which token-usage fields to surface on ``llm.call_complete``. ``cache_read``
# > 0 means the Anthropic prompt cache HIT (the ~90% input discount + latency
# drop); ``cache_creation`` > 0 means we paid to write the cache this call. If
# every call shows cache_read=0 the caching is not working and that alone
# explains slow turns — the exact question "why are all agents slow" needs.
def _usage_fields(response: Any) -> dict[str, int]:
    """Best-effort extraction of token usage from a LiteLLM response. Tolerates
    both dict- and attribute-shaped responses and missing fields (returns only
    what's present, never raises — instrumentation must not break a turn)."""

    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "get"):
            try:
                return obj.get(key)
            except Exception:
                return None
        return getattr(obj, key, None)

    usage = _get(response, "usage")
    if usage is None:
        return {}
    out: dict[str, int] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        val = _get(usage, key)
        if isinstance(val, int):
            out[key] = val
    # Anthropic sometimes reports the cache hit under ``prompt_tokens_details``.
    if "cache_read_input_tokens" not in out:
        cached = _get(_get(usage, "prompt_tokens_details"), "cached_tokens")
        if isinstance(cached, int):
            out["cache_read_input_tokens"] = cached
    return out

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


def _with_prompt_caching(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        return messages

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
    return [merged, *messages[rest_start:]]


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
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

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
            "messages": _with_prompt_caching(messages),
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
        response = await litellm.acompletion(**kwargs)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        usage_fields = _usage_fields(response)
        log.info(
            "llm.call_complete",
            tenant_id=str(tenant_id),
            role=role,
            model=model,
            elapsed_ms=elapsed_ms,
            has_tools=bool(tools),
            **usage_fields,
        )
        # WP-02: one Langfuse generation per call, with token counts and
        # tenant_id as metadata. Noop when Langfuse is disabled; never raises.
        record_generation(
            tenant_id=tenant_id,
            role=role,
            model=model,
            usage=usage_fields,
            latency_ms=elapsed_ms,
        )
        return response


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
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        # A dead pooled socket fails in ~1ms; retry it on a fresh
                        # connection immediately instead of paying the backoff.
                        # Everything else (rate limits, …) still backs off.
                        if not fast_retry:
                            await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
        assert last_exc is not None  # the loop ran at least once
        log.error(
            "llm.all_attempts_exhausted",
            tenant_id=str(tenant_id),
            role=role,
            models=list(models),
        )
        raise last_exc

    def _model_chain(self, primary: str) -> tuple[str, ...]:
        """Primary model, then the fallback — de-duplicated if they match."""
        if self.fallback_model and self.fallback_model != primary:
            return (primary, self.fallback_model)
        return (primary,)

    async def classify(
        self,
        *,
        tenant_id: uuid.UUID,
        messages: list[dict[str, str]],
    ) -> str:
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
            models=self._model_chain(self.classify_model),
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
            # fallback chain still applies for resilience.
            models=self._model_chain(model_override or self.respond_model),
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
