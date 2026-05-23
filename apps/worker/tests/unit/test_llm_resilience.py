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

from nexus_worker.runtime.llm import (
    DEFAULT_CONTEXT_MANAGEMENT,
    LiteLLMProvider,
    LLMResponse,
    LLMRouter,
    _with_prompt_caching,
    default_context_management_from_env,
)

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


# ── context editing (Fase A — claude-platform-integration) ───────────────────


class _RecordingAcompletion:
    """Captures kwargs passed to ``litellm.acompletion`` and returns a stub.

    Replaces ``litellm.acompletion`` via monkeypatch so the test never hits
    the wire. The stub response shape mirrors the bits ``LiteLLMProvider``
    actually reads — ``choices[0]["message"]`` for text + tool_calls.
    """

    def __init__(self, *, text: str = "ok", tool_calls: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._text = text
        self._tool_calls = tool_calls or []

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        message: dict[str, Any] = {"content": self._text}
        if self._tool_calls:
            message["tool_calls"] = self._tool_calls
        return {"choices": [{"message": message}]}


@pytest.fixture
def patched_litellm(monkeypatch: pytest.MonkeyPatch) -> _RecordingAcompletion:
    """Patch ``litellm.acompletion`` with a recording stub for this test.

    Imports happen inside ``LiteLLMProvider._raw_complete`` via
    ``import litellm`` — a local import that re-binds to the module's
    ``acompletion`` attribute on each call. Patching the attribute on the
    module is therefore sufficient.
    """
    import litellm  # heavy dep but tests/conftest already loads it indirectly

    stub = _RecordingAcompletion()
    monkeypatch.setattr(litellm, "acompletion", stub)
    return stub


class TestContextEditing:
    async def test_context_management_emitted_with_tools(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        """Provider attached to a default config emits ``context_management``
        in the litellm payload whenever the call carries tools. LiteLLM then
        auto-injects the ``context-management-2025-06-27`` beta header."""
        provider = LiteLLMProvider(context_management=DEFAULT_CONTEXT_MANAGEMENT)
        tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]

        await provider.acomplete_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            model="anthropic/claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "S"},
                {"role": "user", "content": "u"},
            ],
            tools=tools,
        )

        assert len(patched_litellm.calls) == 1
        kw = patched_litellm.calls[0]
        assert "context_management" in kw, (
            "tools call must carry context_management for clear_tool_uses_20250919"
        )
        assert kw["context_management"] == DEFAULT_CONTEXT_MANAGEMENT
        edit = kw["context_management"]["edits"][0]
        assert edit["type"] == "clear_tool_uses_20250919"

    async def test_context_management_omitted_without_tools(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        """The classify call carries no tools — context editing operates on
        tool_use/tool_result pairs and would be a no-op. Provider must NOT
        emit ``context_management`` so the beta header is not added either."""
        provider = LiteLLMProvider(context_management=DEFAULT_CONTEXT_MANAGEMENT)

        await provider.acomplete(
            tenant_id=uuid.uuid4(),
            role="classify",
            model="anthropic/claude-haiku-4-5",
            messages=[
                {"role": "system", "content": "S"},
                {"role": "user", "content": "u"},
            ],
        )

        assert len(patched_litellm.calls) == 1
        assert "context_management" not in patched_litellm.calls[0]

    async def test_context_management_disabled_per_provider(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        """``context_management=None`` (rollback path or explicit opt-out)
        keeps the kwarg out of the payload even when tools are present."""
        provider = LiteLLMProvider(context_management=None)
        tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]

        await provider.acomplete_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "u"}],
            tools=tools,
        )

        assert len(patched_litellm.calls) == 1
        assert "context_management" not in patched_litellm.calls[0]

    async def test_context_management_persists_across_loop_iterations(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        """Simulate the handler's ReAct loop: the same provider is invoked
        repeatedly with growing message history (assistant tool_call →
        tool_result → next call). ``context_management`` must travel on every
        tool-bearing iteration so the Anthropic server can apply the edit
        once the prefix exceeds the trigger threshold."""
        provider = LiteLLMProvider(context_management=DEFAULT_CONTEXT_MANAGEMENT)
        tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "find me a slot"},
        ]

        # Drive 4 loop iterations — the threshold for the doc's
        # ``test_clear_tool_uses_in_long_loop`` acceptance. Each iteration
        # appends an assistant message + a tool result to the thread; the
        # context_management arg must travel every single time.
        for i in range(4):
            await provider.acomplete_with_tools(
                tenant_id=uuid.uuid4(),
                role="book",
                model="anthropic/claude-sonnet-4-6",
                messages=messages,
                tools=tools,
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        }
                    ],
                }
            )
            messages.append(
                {"role": "tool", "tool_call_id": f"call_{i}", "content": "{}"}
            )

        assert len(patched_litellm.calls) == 4
        for idx, call in enumerate(patched_litellm.calls):
            assert "context_management" in call, (
                f"iteration {idx} dropped context_management"
            )
            assert (
                call["context_management"]["edits"][0]["type"]
                == "clear_tool_uses_20250919"
            )


class TestDefaultContextManagementFromEnv:
    def test_returns_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEXUS_CONTEXT_EDITING_ENABLED", raising=False)
        assert default_context_management_from_env() == DEFAULT_CONTEXT_MANAGEMENT

    @pytest.mark.parametrize("flag", ["0", "false", "FALSE", "no", "off", ""])
    def test_returns_none_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch, flag: str
    ) -> None:
        monkeypatch.setenv("NEXUS_CONTEXT_EDITING_ENABLED", flag)
        assert default_context_management_from_env() is None

    @pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes"])
    def test_returns_default_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch, flag: str
    ) -> None:
        monkeypatch.setenv("NEXUS_CONTEXT_EDITING_ENABLED", flag)
        assert default_context_management_from_env() == DEFAULT_CONTEXT_MANAGEMENT
