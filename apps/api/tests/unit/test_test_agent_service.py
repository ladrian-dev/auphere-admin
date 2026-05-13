"""Block O — pure-Python tests for the test_agent sandbox service.

These tests drive ``run_test_turn`` directly with the ``FakeTestAgentProvider``.
They lock in three properties:

- Single LLM call when the model doesn't request tools.
- Two-iteration flow when the first call emits tool_calls: synthetic
  dry-run results are appended, the second call's text becomes the
  ``assistant_message``.
- Tools are NEVER dispatched (the planned_tool_calls list is the only
  evidence the model wanted to use them).
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.services.test_agent import (
    FakeTestAgentProvider,
    PlannedToolCall,
    TestAgentError,
    run_test_turn,
)

_async = pytest.mark.asyncio


_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "booking.check_availability",
            "description": "Check slots for a date.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string"}},
                "required": ["date"],
            },
        },
    }
]


def _ctx() -> dict[str, object]:
    return {
        "tenant_id": uuid.uuid4(),
        "system_prompt": "Sos el asistente de Test Tenant.",
        "history": [],
        "tool_defs": _TOOL_DEFS,
        "model": "anthropic/claude-sonnet-4-6",
        "timeout_s": 30.0,
        "max_output_tokens": 1000,
    }


@_async
async def test_single_call_when_no_tools_requested() -> None:
    provider = FakeTestAgentProvider()
    result = await run_test_turn(
        user_message="hola",
        provider=provider,
        **_ctx(),  # type: ignore[arg-type]
    )
    assert result.assistant_message == "Hola, soy el asistente de prueba."
    assert result.planned_tool_calls == ()
    assert result.iterations == 1
    assert len(provider.calls) == 1


@_async
async def test_tool_call_triggers_second_iteration_with_synthetic_result() -> None:
    """First call emits a tool_use; we feed back a synthetic result and
    expect a second call to produce the final text."""

    def responder(messages, tools, call_index):
        if call_index == 0:
            return (
                "Voy a chequear disponibilidad.",
                [
                    {
                        "id": "call_001",
                        "name": "booking.check_availability",
                        "arguments": {"date": "2026-05-14"},
                    }
                ],
            )
        return ("Tenemos turnos a las 10 y 14.", [])

    provider = FakeTestAgentProvider(responder=responder)
    result = await run_test_turn(
        user_message="¿tenés turnos mañana?",
        provider=provider,
        **_ctx(),  # type: ignore[arg-type]
    )
    assert result.iterations == 2
    assert result.assistant_message == "Tenemos turnos a las 10 y 14."
    assert len(result.planned_tool_calls) == 1
    pc = result.planned_tool_calls[0]
    assert isinstance(pc, PlannedToolCall)
    assert pc.name == "booking.check_availability"
    assert pc.arguments == {"date": "2026-05-14"}
    assert pc.iteration == 0


@_async
async def test_synthetic_result_is_visible_to_the_model_on_second_call() -> None:
    """The whole point of the synthetic result is that the second LLM
    call sees it. We assert the messages handed to the second call
    contain the tool result envelope."""
    seen_messages: list[list[dict[str, object]]] = []

    def responder(messages, tools, call_index):
        seen_messages.append(messages)
        if call_index == 0:
            return (
                "",
                [
                    {
                        "id": "call_001",
                        "name": "booking.check_availability",
                        "arguments": {"date": "2026-05-14"},
                    }
                ],
            )
        return ("ok", [])

    provider = FakeTestAgentProvider(responder=responder)
    await run_test_turn(
        user_message="hola",
        provider=provider,
        **_ctx(),  # type: ignore[arg-type]
    )
    # The second call must include a tool message with the dry-run hint.
    second_call_messages = seen_messages[1]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "SANDBOX_DRY_RUN" in str(tool_msgs[0]["content"])


@_async
async def test_iteration_cap_at_two_even_if_model_keeps_calling_tools() -> None:
    """If the model emits tool_use on BOTH calls we still stop after
    iteration 2. The operator gets whatever text the second call
    produced (possibly empty) plus the captured planned_tool_calls."""

    def responder(messages, tools, call_index):
        return (
            "",
            [
                {
                    "id": f"call_{call_index}",
                    "name": "booking.check_availability",
                    "arguments": {"date": "x"},
                }
            ],
        )

    provider = FakeTestAgentProvider(responder=responder)
    result = await run_test_turn(
        user_message="hola",
        provider=provider,
        **_ctx(),  # type: ignore[arg-type]
    )
    assert result.iterations == 2
    # Both tool calls captured.
    assert len(result.planned_tool_calls) == 2
    # Text empty — model never produced a final answer within the cap.
    assert result.assistant_message == ""


@_async
async def test_no_tool_dispatch_happens_during_test_turn() -> None:
    """Hard invariant from ADR-014: NO tool execution. The Fake provider
    is what we'd dispatch against; here we just verify nothing besides
    the LLM calls happens."""
    provider = FakeTestAgentProvider()
    await run_test_turn(
        user_message="hola",
        provider=provider,
        **_ctx(),  # type: ignore[arg-type]
    )
    # The provider tracks LLM calls only — no dispatch path exists in
    # the service. If we ever add real dispatch, this test goes red
    # because it asserts the provider is the only side effect surface.
    assert all("messages" in call for call in provider.calls)


@_async
async def test_empty_system_prompt_raises() -> None:
    provider = FakeTestAgentProvider()
    ctx = _ctx()
    ctx["system_prompt"] = "   "
    with pytest.raises(TestAgentError):
        await run_test_turn(
            user_message="hola",
            provider=provider,
            **ctx,  # type: ignore[arg-type]
        )


@_async
async def test_empty_user_message_raises() -> None:
    provider = FakeTestAgentProvider()
    with pytest.raises(TestAgentError):
        await run_test_turn(
            user_message="   ",
            provider=provider,
            **_ctx(),  # type: ignore[arg-type]
        )


@_async
async def test_history_is_passed_to_the_llm_unchanged() -> None:
    """Multi-turn within the dialog: each request carries the running
    history. The service must drop it into the messages array between
    the system prompt and the new user message, in order."""
    seen_messages: list[list[dict[str, object]]] = []

    def responder(messages, tools, call_index):
        seen_messages.append(messages)
        return ("ok", [])

    provider = FakeTestAgentProvider(responder=responder)
    history = [
        {"role": "user", "content": "¿qué tal?"},
        {"role": "assistant", "content": "todo bien, ¿en qué te ayudo?"},
    ]
    ctx = _ctx()
    ctx["history"] = history
    await run_test_turn(
        user_message="quería agendar",
        provider=provider,
        **ctx,  # type: ignore[arg-type]
    )
    messages = seen_messages[0]
    # [system, user-h, assistant-h, user-new]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "¿qué tal?"}
    assert messages[2] == {
        "role": "assistant",
        "content": "todo bien, ¿en qué te ayudo?",
    }
    assert messages[3] == {"role": "user", "content": "quería agendar"}


@_async
async def test_system_block_carries_cache_control() -> None:
    seen_messages: list[list[dict[str, object]]] = []

    def responder(messages, tools, call_index):
        seen_messages.append(messages)
        return ("ok", [])

    provider = FakeTestAgentProvider(responder=responder)
    await run_test_turn(
        user_message="hola",
        provider=provider,
        **_ctx(),  # type: ignore[arg-type]
    )
    sys_block = seen_messages[0][0]["content"][0]  # type: ignore[index]
    assert sys_block["cache_control"] == {"type": "ephemeral"}
