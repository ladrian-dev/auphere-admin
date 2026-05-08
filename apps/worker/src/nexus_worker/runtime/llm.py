"""LLM routing — thin wrapper around LiteLLM with the contract from
architecture/agent-isolation.md garantía 7 baked in.

Roles:
- ``classify`` → Haiku 4.5
- ``respond``  → Sonnet 4.6
- ``fallback`` → GPT-4o (used when the primary call errors)

Batching:
- Calls go through ``litellm.acompletion`` one-at-a-time. We never aggregate
  requests across tenants. The contract is published in ``litellm_kwargs_contract``
  so the isolation tests can assert it without reaching into LiteLLM internals.

Tests run with ``InMemoryProvider`` (no HTTP). Production wiring uses
``LiteLLMProvider`` and reads API keys from env via LiteLLM's own loader.
"""

from __future__ import annotations

import asyncio
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


@dataclass(frozen=True)
class LLMCall:
    """Auditable record of a provider invocation."""

    tenant_id: uuid.UUID
    role: str
    model: str
    messages: list[dict[str, str]]


class LLMProvider(Protocol):
    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str: ...


@dataclass
class InMemoryProvider:
    """Test provider. Records every call and returns a canned response per role.

    The default ``responder`` echoes a deterministic string; tests override it
    with a callable that returns whatever payload the test needs.
    """

    calls: list[LLMCall] = field(default_factory=list)
    responder: Callable[[LLMCall], str] | None = None
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
        import litellm  # local import — heavy dep

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "metadata": {"tenant_id": str(tenant_id), "role": role},
            "timeout": self.timeout_s,
            # Per garantía 7: NEVER batch across tenants. LiteLLM batches only
            # when the caller opts in (Router with rpm/tpm, Batch API). We
            # don't, and these flags belong to the contract test surface.
        }
        # Sanity: if a future change ever turns batching on globally, surface it
        # immediately rather than letting it ship.
        global_router = getattr(litellm, "default_router", None)
        if global_router is not None and getattr(global_router, "enable_batching", False):
            counters.incr(ISOLATION_LLM_BATCH_CROSS_TENANT)
            raise RuntimeError(
                "litellm batching is enabled globally; refusing to invoke for "
                f"tenant {tenant_id!s} — see architecture/agent-isolation.md garantía 7"
            )

        response = await litellm.acompletion(**kwargs)
        # LiteLLM returns an OpenAI-shaped envelope.
        choices = response["choices"]
        if not choices:
            raise RuntimeError("provider returned no choices")
        return str(choices[0]["message"]["content"])


# ── Router ────────────────────────────────────────────────────────────────────


@dataclass
class LLMRouter:
    """Picks a model per role and invokes the provider.

    The router is intentionally dumb — no retry policy, no fallback chain in
    block C. ``call_with_fallback`` exists for when block H wants to add a
    GPT-4o failover; currently it just records the model used in ``meta``.
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
    "LLMRouter",
    "LiteLLMProvider",
    "build_default_router",
    "litellm_kwargs_contract",
]


# Re-export a typed callable shape for handlers that pass a plain function:
LLMCallable = Callable[..., Awaitable[str]]
