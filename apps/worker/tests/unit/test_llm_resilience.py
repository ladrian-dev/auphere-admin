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
    _drop_openai_unsupported,
    _usage_fields,
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

    def test_cache_tail_marks_the_last_message(self) -> None:
        """Con ``cache_tail`` el último mensaje gana el segundo punto de corte.

        Como un punto cachea *todo lo anterior a él*, ponerlo en la cola
        convierte el historial de la pasada N en prefijo cacheado de la N+1.
        Medido contra Anthropic: con la misma cola, la tercera llamada leyó
        13.148 de 13.151 tokens desde caché.
        """
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "prev"},
            {"role": "tool", "tool_call_id": "t1", "name": "x", "content": "resultado"},
        ]
        out = _with_prompt_caching(messages, cache_tail=True)
        assert out[0]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        assert out[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
        # Dos y solo dos: Anthropic admite cuatro por petición, y gastarlos
        # sin motivo deja sin sitio a quien los necesite después.
        assert _count_breakpoints(out) == 2

    def test_cache_tail_leaves_non_text_content_alone(self) -> None:
        """Un mensaje sin bloque de texto final no es sitio para un corte, y
        forzarlo es un 400."""
        messages = [
            {"role": "system", "content": "S"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t1"}]},
        ]
        out = _with_prompt_caching(messages, cache_tail=True)
        assert out[-1]["content"] == ""
        assert _count_breakpoints(out) == 1

    def test_cache_tail_without_leading_system_still_marks_the_tail(self) -> None:
        messages = [{"role": "user", "content": "hola"}]
        out = _with_prompt_caching(messages, cache_tail=True)
        assert out[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}

    def test_noop_without_leading_system(self) -> None:
        messages = [{"role": "user", "content": "hola"}]
        assert _with_prompt_caching(messages) == messages

    def test_history_after_system_stays_uncached(self) -> None:
        """Sin ``cache_tail`` el historial NO gana punto de corte.

        Es el comportamiento del agente de cliente y de los dos playgrounds,
        que son carga viva: encender el segundo corte para todos, para
        arreglar un problema del Companion, es como se rompe algo que
        funcionaba."""
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
        extra: dict[str, Any] | None = None,
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


# ── fast retry on transient connection errors (no backoff) ───────────────────


class _NamedError(Exception):
    """Exception whose *class name* is what ``_is_fast_retry_error`` matches on.

    Subclasses below reproduce the class names litellm raises for a dead
    pooled socket (``Timeout``) vs a rate limit (``RateLimitError``) without
    importing litellm into the test.
    """


class Timeout(_NamedError):
    """Mirrors ``litellm.Timeout`` — the class the stale-connection storm hit."""


class RateLimitError(_NamedError):
    """Mirrors ``litellm.RateLimitError`` — must still back off."""


@dataclass
class _ExcThenOkProvider:
    """Raises ``exc`` on the first call, then succeeds. Records call count."""

    exc: Exception
    calls: int = 0

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        self.calls += 1
        if self.calls == 1:
            raise self.exc
        return "ok"

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
        self.calls += 1
        if self.calls == 1:
            raise self.exc
        return LLMResponse(text="ok", tool_calls=())


class TestFastRetryNoBackoff:
    async def test_connection_error_retries_without_backoff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale-socket ``Timeout`` retries on a fresh connection with NO
        sleep — killing the 0.5s latency every post-idle turn used to pay."""
        sleeps: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr("nexus_worker.runtime.llm.asyncio.sleep", _fake_sleep)

        provider = _ExcThenOkProvider(exc=Timeout("Connection timed out"))
        router = LLMRouter(
            provider=provider,  # type: ignore[arg-type]
            classify_model="primary",
            respond_model="primary",
            fallback_model="fallback",
        )

        out = await router.classify(tenant_id=uuid.uuid4(), messages=[])

        assert out == "ok"
        assert provider.calls == 2  # failed once, retried once, succeeded
        assert sleeps == []  # no backoff for a transient connection error

    async def test_rate_limit_still_backs_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A rate limit is NOT a dead socket — it must keep the backoff so the
        immediate retry doesn't just re-trip the limit."""
        sleeps: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr("nexus_worker.runtime.llm.asyncio.sleep", _fake_sleep)

        provider = _ExcThenOkProvider(exc=RateLimitError("429"))
        router = LLMRouter(
            provider=provider,  # type: ignore[arg-type]
            classify_model="primary",
            respond_model="primary",
            fallback_model="fallback",
        )

        out = await router.classify(tenant_id=uuid.uuid4(), messages=[])

        assert out == "ok"
        assert sleeps == [0.5]  # backoff preserved for non-connection errors


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
    @pytest.fixture(autouse=True)
    def _proxy(self, litellm_proxy_partner: uuid.UUID) -> uuid.UUID:
        return litellm_proxy_partner

    async def test_context_management_emitted_with_tools(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        """Provider attached to a default config emits ``context_management``
        on Anthropic hops. On openai/G1 hops the gate strips it so LiteLLM 1.83 does not raise UnsupportedParamsError."""
        provider = LiteLLMProvider(context_management=DEFAULT_CONTEXT_MANAGEMENT)
        tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]

        await provider.acomplete_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            model="openai/gpt-5.6-sol",
            messages=[
                {"role": "system", "content": "S"},
                {"role": "user", "content": "u"},
            ],
            tools=tools,
        )

        assert len(patched_litellm.calls) == 1
        kw = patched_litellm.calls[0]
        # G1 hops are openai/*; LiteLLM 1.83 raises UnsupportedParamsError
        # for Anthropic context_management on that prefix. The hop gate strips it.
        assert "context_management" not in kw

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
            model="openai/gpt-5.6-sol",
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
            model="openai/gpt-5.6-sol",
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
                model="openai/gpt-5.6-sol",
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
            messages.append({"role": "tool", "tool_call_id": f"call_{i}", "content": "{}"})

        assert len(patched_litellm.calls) == 4
        for idx, call in enumerate(patched_litellm.calls):
            assert "context_management" not in call, (
                f"iteration {idx} leaked context_management on openai hop"
            )


class TestDropOpenaiUnsupported:
    def test_openai_hops_drop_thinking_and_context_management(self) -> None:
        kw = {
            "model": "openai/gpt-5.6-terra",
            "thinking": {"type": "adaptive", "display": "summarized"},
            "context_management": DEFAULT_CONTEXT_MANAGEMENT,
        }
        out = _drop_openai_unsupported(kw)
        assert "thinking" not in out
        assert "context_management" not in out
        assert out["model"] == "openai/gpt-5.6-terra"

    def test_anthropic_hops_keep_context_management_with_tools(self) -> None:
        """Catalog hops are openai/* today; the gate must still leave the
        Anthropic payload intact so a future Anthropic id keeps
        ``clear_tool_uses_20250919``."""
        kw = {
            "model": "anthropic/claude-sonnet-4-6",
            "thinking": {"type": "adaptive", "display": "summarized"},
            "context_management": DEFAULT_CONTEXT_MANAGEMENT,
        }
        out = _drop_openai_unsupported(kw)
        assert out["thinking"]["type"] == "adaptive"
        assert out["context_management"] == DEFAULT_CONTEXT_MANAGEMENT
        assert out["context_management"]["edits"][0]["type"] == ("clear_tool_uses_20250919")


class TestDefaultContextManagementFromEnv:
    def test_returns_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEXUS_CONTEXT_EDITING_ENABLED", raising=False)
        assert default_context_management_from_env() == DEFAULT_CONTEXT_MANAGEMENT

    @pytest.mark.parametrize("flag", ["0", "false", "FALSE", "no", "off", ""])
    def test_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
        monkeypatch.setenv("NEXUS_CONTEXT_EDITING_ENABLED", flag)
        assert default_context_management_from_env() is None

    @pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes"])
    def test_returns_default_when_enabled(self, monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
        monkeypatch.setenv("NEXUS_CONTEXT_EDITING_ENABLED", flag)
        assert default_context_management_from_env() == DEFAULT_CONTEXT_MANAGEMENT


# ── usage / cache telemetry ──────────────────────────────────────────────────


class TestUsageFields:
    def test_extracts_tokens_and_cache_read(self) -> None:
        """Dict-shaped LiteLLM usage with an explicit cache-read field — the
        signal that tells us the Anthropic prompt cache actually hit."""
        response = {
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 90,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 0,
            }
        }
        assert _usage_fields(response) == {
            "prompt_tokens": 1200,
            "completion_tokens": 90,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 0,
        }

    def test_cache_read_from_prompt_tokens_details(self) -> None:
        """Some responses report the cache hit under
        ``prompt_tokens_details.cached_tokens`` — read it as the fallback."""
        response = {
            "usage": {
                "prompt_tokens": 800,
                "prompt_tokens_details": {"cached_tokens": 640},
            }
        }
        out = _usage_fields(response)
        assert out["prompt_tokens"] == 800
        assert out["cache_read_input_tokens"] == 640

    def test_missing_usage_is_empty_not_error(self) -> None:
        """Instrumentation must never raise — a response without usage yields
        an empty dict, not an exception."""
        assert _usage_fields({"choices": []}) == {}
        assert _usage_fields(None) == {}


def _count_breakpoints(messages: list[dict[str, Any]]) -> int:
    """Puntos de corte de caché en una petición. Anthropic admite cuatro."""
    import json

    return json.dumps(messages).count("cache_control")
