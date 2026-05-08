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
from typing import Any, Protocol

import structlog
from nexus_api.core.metrics import ISOLATION_LLM_BATCH_CROSS_TENANT, counters

log = structlog.get_logger(__name__)


# Contract shared with the isolation suite (test_7_*). If anything here changes,
# the runtime test fails too — that's the point.
def litellm_kwargs_contract() -> dict[str, Any]:
    return {
        "enable_batching": False,
        "group_by": None,
    }


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
    """Real provider. Imports LiteLLM lazily so tests don't pay the import."""

    timeout_s: float = 30.0

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
            "messages": messages,
            "metadata": {"tenant_id": str(tenant_id), "role": role},
            "timeout": self.timeout_s,
        }
        if tools:
            kwargs["tools"] = tools

        # Sanity: if a future change ever turns batching on globally, surface it
        # immediately rather than letting it ship.
        global_router = getattr(litellm, "default_router", None)
        if global_router is not None and getattr(global_router, "enable_batching", False):
            counters.incr(ISOLATION_LLM_BATCH_CROSS_TENANT)
            raise RuntimeError(
                "litellm batching is enabled globally; refusing to invoke for "
                f"tenant {tenant_id!s} — see architecture/agent-isolation.md garantía 7"
            )
        return await litellm.acompletion(**kwargs)


# ── Router ────────────────────────────────────────────────────────────────────


@dataclass
class LLMRouter:
    """Picks a model per role and invokes the provider.

    ``classify``, ``respond`` and ``fallback`` are plain text completions.
    ``respond_with_tools`` is the function-calling entry point used by the
    Block-D handler tool_loop nodes.
    """

    provider: LLMProvider
    classify_model: str
    respond_model: str
    fallback_model: str

    async def classify(
        self,
        *,
        tenant_id: uuid.UUID,
        messages: list[dict[str, str]],
    ) -> str:
        return await self.provider.acomplete(
            tenant_id=tenant_id,
            role="classify",
            model=self.classify_model,
            messages=messages,
        )

    async def respond(
        self,
        *,
        tenant_id: uuid.UUID,
        messages: list[dict[str, str]],
    ) -> str:
        return await self.provider.acomplete(
            tenant_id=tenant_id,
            role="respond",
            model=self.respond_model,
            messages=messages,
        )

    async def respond_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Function-calling completion for the tool_loop nodes. ``role`` is
        usually the intent (``book``, ``queue``, …) so traces can attribute
        the tool selection."""
        return await self.provider.acomplete_with_tools(
            tenant_id=tenant_id,
            role=role,
            model=self.respond_model,
            messages=messages,
            tools=tools,
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
