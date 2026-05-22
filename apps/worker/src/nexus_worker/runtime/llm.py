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
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

import structlog
from nexus_api.core.metrics import (
    ISOLATION_LLM_BATCH_CROSS_TENANT,
    record_isolation_event,
)

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

# Return type of a resilient call — preserved through ``_call_with_resilience``.
_T = TypeVar("_T")


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
    ) -> LLMResponse:
        call = LLMCall(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=list(messages),
            tools=tuple(tools),
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
    """

    timeout_s: float = 30.0

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
    ) -> LLMResponse:
        response = await self._raw_complete(
            tenant_id=tenant_id,
            role=role,
            model=model,
            messages=messages,
            tools=tools or None,
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
        return await litellm.acompletion(**kwargs)


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
                    log.warning(
                        "llm.attempt_failed",
                        tenant_id=str(tenant_id),
                        role=role,
                        model=model,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
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
    ) -> LLMResponse:
        """Function-calling completion for the handler ReAct loop. ``role``
        is the intent (``book``, ``queue``, …) so traces can attribute the
        tool selection. Retries + falls back like every router call."""

        async def invoke(model: str) -> LLMResponse:
            return await self.provider.acomplete_with_tools(
                tenant_id=tenant_id,
                role=role,
                model=model,
                messages=messages,
                tools=tools,
            )

        return await self._call_with_resilience(
            tenant_id=tenant_id,
            role=role,
            models=self._model_chain(self.respond_model),
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
    "InMemoryProvider",
    "LLMCall",
    "LLMProvider",
    "LLMResponse",
    "LLMRouter",
    "LiteLLMProvider",
    "ToolCall",
    "build_default_router",
    "litellm_kwargs_contract",
]


# Re-export a typed callable shape for handlers that pass a plain function:
LLMCallable = Callable[..., Awaitable[str]]
