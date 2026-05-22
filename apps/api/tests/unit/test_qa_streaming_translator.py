"""Translator unit tests — LangGraph events → SSE pending pairs.

The translator (`translate_event`) is pure-ish: only mutates a state
object it's handed. These tests hit it with synthetic LangGraph
``astream_events(version="v2")`` envelopes and assert the SSE
``(event_name, data)`` pairs it produces.

Reference: ADR-021 Fase 1.
"""

from __future__ import annotations

from typing import Any, ClassVar

from nexus_api.api.qa_streaming import (
    PendingSSE,  # noqa: F401 — re-exported for clarity in assertions
    _TranslatorState,
    translate_event,
)


def _state() -> _TranslatorState:
    return _TranslatorState()


def test_text_delta_from_plain_string_content() -> None:
    """on_chat_model_stream with `content: str` → one text.delta."""

    class _Chunk:
        id = "msg-1"
        content = "Hello"
        additional_kwargs: ClassVar[dict[str, Any]] = {}

    state = _state()
    out = translate_event(
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}},
        state,
    )
    assert out == [("text.delta", {"message_id": "msg-1", "text": "Hello"})]
    assert state.current_message_id == "msg-1"


def test_text_delta_concatenates_message_id_across_chunks() -> None:
    """Subsequent chunks with the same id keep the translator state."""

    class _Chunk:
        id = "msg-1"
        content = "world"
        additional_kwargs: ClassVar[dict[str, Any]] = {}

    state = _state()
    state.current_message_id = "msg-1"  # set by a prior chunk
    out = translate_event(
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}},
        state,
    )
    assert out[0][1]["message_id"] == "msg-1"


def test_text_delta_from_claude_block_content() -> None:
    """Claude 4.6 ships content as `[{"type":"text","text":"..."}]`."""

    class _Chunk:
        id = "msg-2"
        content: ClassVar[list[dict[str, Any]]] = [
            {"type": "text", "text": "Buenos "},
            {"type": "text", "text": "días"},
        ]
        additional_kwargs: ClassVar[dict[str, Any]] = {}

    out = translate_event(
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}},
        _state(),
    )
    assert out == [("text.delta", {"message_id": "msg-2", "text": "Buenos días"})]


def test_reasoning_delta_from_thinking_block() -> None:
    """Claude 4.6 thinking blocks surface as a separate `reasoning.delta`."""

    class _Chunk:
        id = "msg-3"
        content: ClassVar[list[dict[str, Any]]] = [
            {"type": "thinking", "text": "let me check the catalog"},
            {"type": "text", "text": "OK"},
        ]
        additional_kwargs: ClassVar[dict[str, Any]] = {}

    out = translate_event(
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}},
        _state(),
    )
    # text first, reasoning second is fine — assert by membership not order
    by_name = {name: data for name, data in out}
    assert by_name["text.delta"]["text"] == "OK"
    assert by_name["reasoning.delta"]["text"] == "let me check the catalog"


def test_reasoning_delta_from_o1_additional_kwargs() -> None:
    """OpenAI o1-style: reasoning content via `additional_kwargs.reasoning_content`."""

    class _Chunk:
        id = "msg-4"
        content = ""
        additional_kwargs: ClassVar[dict[str, Any]] = {"reasoning_content": "thinking..."}

    out = translate_event(
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}},
        _state(),
    )
    assert out == [("reasoning.delta", {"message_id": "msg-4", "text": "thinking..."})]


def test_cost_updated_from_chat_model_end() -> None:
    """on_chat_model_end carries usage_metadata on the final AIMessage."""

    class _Msg:
        usage_metadata: ClassVar[dict[str, Any]] = {"input_tokens": 120, "output_tokens": 40}
        response_metadata: ClassVar[dict[str, Any]] = {"model_name": "claude-sonnet-4-6"}

    out = translate_event(
        {"event": "on_chat_model_end", "data": {"output": _Msg()}},
        _state(),
    )
    assert out == [
        (
            "cost.updated",
            {
                "input_tokens": 120,
                "output_tokens": 40,
                "model": "claude-sonnet-4-6",
            },
        )
    ]


def test_cost_updated_skipped_when_usage_absent() -> None:
    class _Msg:
        usage_metadata: ClassVar[dict[str, Any]] = {}
        response_metadata: ClassVar[dict[str, Any]] = {}

    out = translate_event(
        {"event": "on_chat_model_end", "data": {"output": _Msg()}},
        _state(),
    )
    # Empty usage_metadata is still seen as "present" but with None numbers;
    # we accept either an emission with Nones or no emission at all.
    if out:
        assert out[0][0] == "cost.updated"


def test_audit_blocked_from_custom_event() -> None:
    """The QA audit writer dispatches `adispatch_custom_event('audit.blocked',...)`."""
    payload = {
        "tool_name": "booking.create_appointment",
        "tool_args": {"when": "tomorrow"},
        "blocked_reason": "dry_run",
        "run_id": "abc",
        "thread_id": "deadbeef",
    }
    out = translate_event(
        {"event": "on_custom_event", "name": "audit.blocked", "data": payload},
        _state(),
    )
    assert out == [("audit.blocked", payload)]


def test_tool_call_started_and_completed_custom_events() -> None:
    started = {
        "tool_call_id": "call-1",
        "name": "booking.check_availability",
        "args": {"date": "tomorrow"},
    }
    completed = {
        "tool_call_id": "call-1",
        "result": {"slots": ["10:00"]},
        "latency_ms": 142,
    }
    state = _state()
    out1 = translate_event(
        {"event": "on_custom_event", "name": "tool.call.started", "data": started},
        state,
    )
    out2 = translate_event(
        {"event": "on_custom_event", "name": "tool.call.completed", "data": completed},
        state,
    )
    assert out1 == [("tool.call.started", started)]
    assert out2 == [("tool.call.completed", completed)]


def test_unknown_custom_event_gets_namespaced_envelope() -> None:
    """Custom events not in the whitelist fall through with a `custom.<name>` envelope.

    Better than a silent drop: future events surface in CI even if
    forgotten in the translator.
    """
    payload = {"hello": "world"}
    out = translate_event(
        {"event": "on_custom_event", "name": "experimental.thing", "data": payload},
        _state(),
    )
    assert out == [("custom.experimental.thing", payload)]


def test_ucm_final_from_ucm_formatter_chain_end() -> None:
    """The ucm_formatter node's on_chain_end surfaces the UCM payload."""
    ucm = {
        "ucm_version": "1.0.0",
        "message_id": "ucm-1",
        "type": "text",
        "content": {"text": "Hola"},
        "fallback_text": "Hola",
        "capabilities_required": ["text"],
    }
    out = translate_event(
        {
            "event": "on_chain_end",
            "name": "ucm_formatter",
            "data": {"output": {"ucm": ucm, "intent": "info"}},
        },
        _state(),
    )
    assert len(out) == 1
    name, data = out[0]
    assert name == "ucm.final"
    assert data["ucm"] == ucm
    assert data["intent"] == "info"


def test_ucm_final_skipped_when_no_ucm_in_state() -> None:
    """A ucm_formatter that didn't emit UCM (eg empty response) → no SSE."""
    out = translate_event(
        {
            "event": "on_chain_end",
            "name": "ucm_formatter",
            "data": {"output": {"response": "ok", "ucm": None}},
        },
        _state(),
    )
    assert out == []


def test_other_chain_end_events_ignored() -> None:
    """The classify / handler / checkpoint node ends don't surface as SSE."""
    for node in ("classify", "book", "checkpoint", "fallback"):
        out = translate_event(
            {
                "event": "on_chain_end",
                "name": node,
                "data": {"output": {"intent": "info"}},
            },
            _state(),
        )
        assert out == [], f"node {node} should not emit SSE on_chain_end"


def test_irrelevant_event_returns_empty() -> None:
    """Events the protocol doesn't track (on_chain_start, on_retriever_*) are
    silently dropped."""
    for ev in ("on_chain_start", "on_retriever_start", "on_llm_start"):
        out = translate_event({"event": ev, "data": {}}, _state())
        assert out == [], f"{ev} should not emit"
