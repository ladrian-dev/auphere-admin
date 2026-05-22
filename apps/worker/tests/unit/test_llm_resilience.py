"""Unit tests for LLM router resilience + prompt caching (ADR-023 / E4).

Two production-hardening behaviours land in ``runtime/llm.py``:

- ``_with_prompt_caching`` — merges the leading ``system`` messages into a
  single Anthropic-shaped system message and marks the last block with
  ``cache_control`` so the stable prefix is cached.
- ``LLMRouter`` retries each call on the primary model and then falls back
  to the secondary model; a transient provider error no longer kills the
  turn.

Both are pure / provider-level, so they test without a DB.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from nexus_worker.runtime.llm import LLMResponse, LLMRouter, _with_prompt_caching

# ── _with_prompt_caching ─────────────────────────────────────────────────────


class TestPromptCaching:
    def test_merges_leading_system_and_marks_last_block(self) -> None:
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "system", "content": "channel note"},
            {"role": "user", "content": "hola"},
        ]
        out = _with_prompt_caching(messages)

        # The two system messages collapse into one with two text blocks.
        assert len(out) == 2
        assert out[0]["role"] == "system"
        blocks = out[0]["content"]
        assert [b["text"] for b in blocks] == ["system prompt", "channel note"]
        # Only the LAST block carries the breakpoint — it caches the whole
        # prefix up to it.
        assert "cache_control" not in blocks[0]
        assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
        # Non-system messages are untouched and stay after the breakpoint.
        assert out[1] == {"role": "user", "content": "hola"}

    def test_single_system_message_is_marked(self) -> None:
        out = _with_prompt_caching(
            [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
        )
        assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}

    def test_noop_without_leading_system(self) -> None:
        messages = [{"role": "user", "content": "hola"}]
        assert _with_prompt_caching(messages) == messages

    def test_history_after_system_stays_uncached(self) -> None:
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "prev"},
            {"role": "assistant", "content": "prev reply"},
            {"role": "user", "content": "now"},
        ]
        out = _with_prompt_caching(messages)
        # 1 merged system + 3 conversation messages, none of which gained
        # a cache breakpoint.
        assert len(out) == 4
        for m in out[1:]:
            assert isinstance(m["content"], str)


# ── router retry + fallback ──────────────────────────────────────────────────


@dataclass
class _FlakyProvider:
    """Provider that fails a configurable number of times per model.

    ``fail_models`` maps a model name to the count of leading calls that
    should raise before it starts succeeding.
    """

    fail_models: dict[str, int] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)  # (role, model)

    def _maybe_fail(self, role: str, model: str) -> None:
        self.calls.append((role, model))
        remaining = self.fail_models.get(model, 0)
        if remaining > 0:
            self.fail_models[model] = remaining - 1
            raise RuntimeError(f"transient failure on {model}")

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        self._maybe_fail(role, model)
        return f"ok:{model}"

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        self._maybe_fail(role, model)
        return LLMResponse(text=f"ok:{model}", tool_calls=())


def _router(provider: _FlakyProvider) -> LLMRouter:
    return LLMRouter(
        provider=provider,
        classify_model="primary",
        respond_model="primary",
        fallback_model="fallback",
    )


class TestRouterResilience:
    async def test_retry_succeeds_on_second_attempt_same_model(self) -> None:
        """One transient failure on the primary model → retried → success."""
        provider = _FlakyProvider(fail_models={"primary": 1})
        router = _router(provider)

        out = await router.classify(tenant_id=uuid.uuid4(), messages=[])

        assert out == "ok:primary"
        assert provider.calls == [
            ("classify", "primary"),
            ("classify", "primary"),
        ]

    async def test_falls_back_to_secondary_model(self) -> None:
        """Both primary attempts fail → the router moves to the fallback."""
        provider = _FlakyProvider(fail_models={"primary": 2})
        router = _router(provider)

        out = await router.respond_with_tools(
            tenant_id=uuid.uuid4(), role="info", messages=[], tools=[]
        )

        assert out.text == "ok:fallback"
        assert provider.calls == [
            ("info", "primary"),
            ("info", "primary"),
            ("info", "fallback"),
        ]

    async def test_raises_only_when_every_model_exhausted(self) -> None:
        """Primary and fallback both fail every attempt → the error
        propagates so the pipeline node can degrade gracefully."""
        provider = _FlakyProvider(fail_models={"primary": 99, "fallback": 99})
        router = _router(provider)

        with pytest.raises(RuntimeError):
            await router.classify(tenant_id=uuid.uuid4(), messages=[])

        # 2 primary attempts + 2 fallback attempts.
        assert len(provider.calls) == 4
