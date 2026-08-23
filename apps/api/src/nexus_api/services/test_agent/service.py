"""Block O — Test Agent sandbox service.

Drives a single turn of the agent without any side effects (no DB
writes, no tool dispatch). The flow per turn:

1. LLM call with the operator's system prompt + history + new user
   message + tool definitions (cache_control on the system block).
2. If the model returned text only → done, return that as the
   assistant message.
3. If the model returned tool_use blocks → capture them as
   :class:`PlannedToolCall` entries with synthetic "dry-run"
   results, append those results to the messages and call the LLM
   once more so the operator sees what the agent WOULD say after
   the tool calls.
4. If the second call still requests tools → capture those too but
   stop iterating; the operator gets whatever text the second call
   produced (possibly empty). Two LLM calls per turn is the cap.

The provider Protocol mirrors :mod:`services.prompt_improver` so
tests can inject a Fake without touching litellm.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from nexus_api.core.llm_proxy import (
    LLMProxyUnavailable,
    apply_litellm_proxy_kwargs,
    raise_mapped_proxy_failure,
    require_current_llm_proxy_partner,
)

log = structlog.get_logger(__name__)


# ── public dataclasses ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlannedToolCall:
    """One tool the model wanted to invoke. The sandbox captures it for
    the operator to inspect but **does NOT execute it**.

    ``dry_run_result`` is the synthetic string we feed back to the
    model so it can produce a follow-up response. The model sees this
    as the tool's output; the operator never sees it unless they open
    the trace.
    """

    name: str
    arguments: dict[str, Any]
    tool_call_id: str  # passed back to the model on the synthetic result
    dry_run_result: str
    iteration: int  # 0 = first LLM call, 1 = follow-up call


@dataclass(frozen=True)
class TestTurnResult:
    # Pytest collection skip — see :class:`TestAgentError` for context.
    __test__ = False
    assistant_message: str
    planned_tool_calls: tuple[PlannedToolCall, ...]
    model: str
    iterations: int  # LLM calls actually made (1 or 2)
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None


# ── errors ──────────────────────────────────────────────────────────────────


class TestAgentError(Exception):
    """Base error for the sandbox service. Endpoint maps to 400 unless
    a subtype overrides."""

    # Pytest tries to collect any class whose name starts with "Test" as
    # a test class; the marker below tells it to skip this one.
    __test__ = False


# ── provider protocol + impls ───────────────────────────────────────────────


@dataclass(frozen=True)
class _ToolCallEnvelope:
    """Normalised tool_call shape (matches OpenAI's structured output;
    LiteLLM translates Anthropic's tool_use blocks to this form)."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class _LLMReply:
    text: str
    tool_calls: tuple[_ToolCallEnvelope, ...]
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None


class TestAgentProvider(Protocol):
    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_output_tokens: int,
        timeout_s: float,
    ) -> _LLMReply: ...


class LiteLLMTestAgentProvider:
    """Production provider — same path Improve Prompt uses, but with
    ``tools`` in the request so the model can emit function calls."""

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_output_tokens: int,
        timeout_s: float,
    ) -> _LLMReply:
        import json

        import litellm  # local import — heavy dep

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "timeout": timeout_s,
            "metadata": {"role": "test_agent"},
        }
        if tools:
            kwargs["tools"] = tools
        apply_litellm_proxy_kwargs(kwargs, partner_id=require_current_llm_proxy_partner())
        try:
            response = await litellm.acompletion(**kwargs)
        except LLMProxyUnavailable:
            raise
        except Exception as exc:
            raise_mapped_proxy_failure(exc)
            raise
        choice = response.choices[0]
        text = getattr(choice.message, "content", None) or ""
        raw_tool_calls = getattr(choice.message, "tool_calls", None) or []
        envelopes: list[_ToolCallEnvelope] = []
        for tc in raw_tool_calls:
            # LiteLLM returns tool_calls in OpenAI shape:
            # {id, type, function: {name, arguments (json string)}}.
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            try:
                args = json.loads(getattr(fn, "arguments", "{}") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": getattr(fn, "arguments", "")}
            envelopes.append(
                _ToolCallEnvelope(
                    id=getattr(tc, "id", "") or "",
                    name=getattr(fn, "name", "") or "",
                    arguments=args,
                )
            )

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached = getattr(details, "cached_tokens", None) if details else None

        return _LLMReply(
            text=str(text) if text else "",
            tool_calls=tuple(envelopes),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
        )


@dataclass
class FakeTestAgentProvider:
    """Test provider — scripted responses.

    Tests register a ``responder(messages, tools, call_index)`` callback
    that returns ``(text, tool_calls)``. ``call_index`` lets a single
    test produce different replies on the first vs second LLM call
    (e.g. first call emits a tool, second call emits the final text).
    """

    responder: Any = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_output_tokens: int,
        timeout_s: float,
    ) -> _LLMReply:
        call_index = len(self.calls)
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "model": model,
                "messages": messages,
                "tools": tools,
            }
        )
        if self.responder is None:
            text = "Hola, soy el asistente de prueba."
            tool_calls: list[_ToolCallEnvelope] = []
        else:
            raw = self.responder(messages, tools, call_index)
            if isinstance(raw, tuple):
                text, tcs = raw
            else:
                text, tcs = raw, []
            tool_calls = [
                _ToolCallEnvelope(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                for tc in tcs
            ]
        return _LLMReply(
            text=text,
            tool_calls=tuple(tool_calls),
            input_tokens=1200 + call_index * 200,
            output_tokens=240,
            cached_input_tokens=0,
        )


# ── orchestrator ────────────────────────────────────────────────────────────


_DRY_RUN_RESULT: str = (
    "SANDBOX_DRY_RUN: el sandbox no ejecuta tools. Asumí que la llamada "
    "tuvo éxito y respondé al usuario como si los datos volvieran bien. "
    "Mantené el tono y respetá las instrucciones del system prompt."
)

_MAX_ITERATIONS: int = 2


def _build_initial_messages(
    *,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
) -> list[dict[str, Any]]:
    """Anthropic-style messages with ``cache_control`` on the system
    block (same shape Improve Prompt uses). The user-facing history is
    plain text per role; tool_use round-trips happen later inside the
    loop."""
    return [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        },
        *({"role": m["role"], "content": m["content"]} for m in history),
        {"role": "user", "content": user_message},
    ]


def _tool_call_to_assistant_message(
    envs: tuple[_ToolCallEnvelope, ...], text: str
) -> dict[str, Any]:
    """Build the assistant message that records the tool_calls we just
    captured, so the LLM can see its own previous output when we feed
    back the synthetic results."""
    import json

    return {
        "role": "assistant",
        "content": text or "",
        "tool_calls": [
            {
                "id": e.id,
                "type": "function",
                "function": {
                    "name": e.name,
                    "arguments": json.dumps(e.arguments),
                },
            }
            for e in envs
        ],
    }


async def run_test_turn(
    *,
    tenant_id: uuid.UUID,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
    tool_defs: list[dict[str, Any]],
    provider: TestAgentProvider,
    model: str,
    timeout_s: float,
    max_output_tokens: int,
) -> TestTurnResult:
    """Run one operator turn. At most two LLM calls — the first emits
    text and/or tool_use; if tools were requested we feed back synthetic
    results and call once more to capture the follow-up text."""
    if not system_prompt.strip():
        raise TestAgentError("system_prompt is empty — stage or apply a seed template first")
    if not user_message.strip():
        raise TestAgentError("user_message is empty")

    messages = _build_initial_messages(
        system_prompt=system_prompt,
        history=history,
        user_message=user_message,
    )
    tools = tool_defs if tool_defs else None

    planned: list[PlannedToolCall] = []
    started = time.perf_counter()

    iterations = 0
    final_text = ""
    input_tokens_total: int = 0
    output_tokens_total: int = 0
    cached_total: int = 0

    while iterations < _MAX_ITERATIONS:
        reply = await provider.acomplete(
            tenant_id=tenant_id,
            model=model,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
            timeout_s=timeout_s,
        )
        iterations += 1
        input_tokens_total += reply.input_tokens or 0
        output_tokens_total += reply.output_tokens or 0
        cached_total += reply.cached_input_tokens or 0

        # Always keep the latest text — even if the model also requested
        # tools, the text it produced before the call is useful for the
        # operator (the agent's "thinking aloud" preamble).
        if reply.text:
            final_text = reply.text

        if not reply.tool_calls:
            break

        # Capture each tool call and append synthetic results so the
        # next iteration can produce a final answer.
        messages.append(_tool_call_to_assistant_message(reply.tool_calls, reply.text))
        for env in reply.tool_calls:
            planned.append(
                PlannedToolCall(
                    name=env.name,
                    arguments=env.arguments,
                    tool_call_id=env.id,
                    dry_run_result=_DRY_RUN_RESULT,
                    iteration=iterations - 1,
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": env.id,
                    "content": _DRY_RUN_RESULT,
                }
            )
        # Loop to next iteration to fetch the follow-up text.

    latency_ms = int((time.perf_counter() - started) * 1000)

    log.info(
        "test_agent.turn",
        tenant_id=str(tenant_id),
        model=model,
        iterations=iterations,
        planned_tool_calls=len(planned),
        latency_ms=latency_ms,
        input_tokens=input_tokens_total,
        output_tokens=output_tokens_total,
        cached_input_tokens=cached_total,
    )

    return TestTurnResult(
        assistant_message=final_text,
        planned_tool_calls=tuple(planned),
        model=model,
        iterations=iterations,
        latency_ms=latency_ms,
        input_tokens=input_tokens_total or None,
        output_tokens=output_tokens_total or None,
        cached_input_tokens=cached_total or None,
    )
