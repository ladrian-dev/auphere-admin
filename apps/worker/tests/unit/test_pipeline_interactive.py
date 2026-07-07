"""Unit tests for the ``response.send_interactive`` capture path in
the handler ReAct loop.

The contract being tested:

- When the LLM emits a ``response.send_interactive`` tool call and
  the dispatch returns an ``ok`` envelope, the handler captures the
  tool args (minus ``conversation_id``) into ``state["interactive_payload"]``
  and breaks the ReAct loop without asking the LLM for another
  iteration.
- ``response.text`` emitted alongside the tool call survives into
  ``state["response"]``.
- The empty-response fallback does NOT fire when ``interactive_payload``
  is set (the agent's reply IS the component).
- A NON-``ok`` envelope (e.g. ``skipped:not_in_whitelist``,
  ``error``) leaves ``interactive_payload`` unset so the agent can
  fall back to plain text on the next iteration.

The dispatcher itself (``registry.dispatch``) is monkey-patched here
so the test is fast and DB-free.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from nexus_mcp import MCPRegistry
from nexus_mcp.servers.notification import SendInteractive

from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import LLMResponse, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import (
    _INTERACTIVE_TOOL_NAME,
    make_handler_node,
)


@dataclass
class _ScriptedProvider:
    """LLM provider that returns whatever the test scripts. Records
    each call so the test can assert how many round-trips happened
    (the capture path should require exactly one)."""

    responses: list[LLMResponse] = field(default_factory=list)
    calls: int = 0
    text_to_return: str = "ok"

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return self.text_to_return

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
        idx = self.calls
        self.calls += 1
        if idx < len(self.responses):
            return self.responses[idx]
        return LLMResponse(text="", tool_calls=())


def _bundle(*, tools: frozenset[str]) -> AgentBundle:
    return AgentBundle(
        tenant_id=uuid.uuid4(),
        version=1,
        version_id=uuid.uuid4(),
        system_prompt="be honest",
        tools=tools,
        policies={},
    )


def _router(provider: _ScriptedProvider) -> LLMRouter:
    return LLMRouter(
        provider=provider,
        classify_model="anthropic/haiku",
        respond_model="anthropic/sonnet",
        fallback_model="openai/gpt-4o",
    )


def _make_state(tenant_id: uuid.UUID) -> dict[str, Any]:
    return {
        "tenant_id": str(tenant_id),
        "customer_id": str(uuid.uuid4()),
        "channel_type": "whatsapp",
        "intent": "info",
        "user_message": "hola",
        "history": [],
    }


class _LoaderStub:
    def __init__(self, bundle: AgentBundle) -> None:
        self.bundle = bundle

    async def load(self, _tid: uuid.UUID) -> AgentBundle:
        return self.bundle

    async def prime(self, _b: AgentBundle) -> None:
        pass

    async def invalidate(self, _tid: uuid.UUID) -> None:
        pass


def _stub_dispatch(monkeypatch: pytest.MonkeyPatch, *, status: str = "ok") -> list[ToolCall]:
    """Replace ``_dispatch_tool`` so the test doesn't touch the DB.
    Returns a list the test reads to inspect what was dispatched."""
    seen: list[ToolCall] = []
    import nexus_worker.runtime.pipeline as pipeline

    async def _fake(
        registry: MCPRegistry,
        call: ToolCall,
        available_names: tuple[str, ...],
        intent: str,
    ) -> dict[str, Any]:
        seen.append(call)
        return {
            "tool": call.name,
            "intent": intent,
            "status": status,
            "result": {"message_id": str(uuid.uuid4()), "status": "captured"},
        }

    async def _empty_kg(_tid: uuid.UUID) -> str:
        return ""

    monkeypatch.setattr(pipeline, "_dispatch_tool", _fake)
    monkeypatch.setattr(pipeline, "_load_kg_snapshot_text", _empty_kg)
    return seen


@pytest.mark.asyncio
class TestCapture:
    async def test_buttons_call_is_captured_and_loop_breaks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _stub_dispatch(monkeypatch)
        provider = _ScriptedProvider(
            responses=[
                LLMResponse(
                    text="Encontré tu cita disponible.",
                    tool_calls=(
                        ToolCall(
                            id="call_1",
                            name=_INTERACTIVE_TOOL_NAME,
                            arguments={
                                "conversation_id": "11111111-1111-4111-8111-111111111111",
                                "body": "¿Confirmas la reserva?",
                                "buttons": [
                                    {"id": "yes", "title": "Sí"},
                                    {"id": "no", "title": "No"},
                                ],
                            },
                        ),
                    ),
                ),
            ]
        )
        bundle = _bundle(tools=frozenset({_INTERACTIVE_TOOL_NAME}))
        # Register the tool so ``get_openai_tools`` returns a non-empty
        # definition list; otherwise the handler short-circuits on the
        # very first iteration with ``not tools_arg``. The dispatch
        # itself is monkey-patched above so this never hits the DB.
        registry = MCPRegistry()
        registry.register(SendInteractive())
        handler = make_handler_node("info", _LoaderStub(bundle), _router(provider), registry)

        out = await handler(_make_state(bundle.tenant_id))

        # The capture path made exactly ONE LLM round-trip — the
        # terminal tool broke the ReAct loop without a follow-up call.
        assert provider.calls == 1
        # Both halves of the response landed in state.
        assert out["response"] == "Encontré tu cita disponible."
        payload = out["interactive_payload"]
        assert payload["body"] == "¿Confirmas la reserva?"
        assert [b["title"] for b in payload["buttons"]] == ["Sí", "No"]
        # The routing field is stripped (the ucm_formatter doesn't need it).
        assert "conversation_id" not in payload
        # The dispatcher saw exactly one call — the interactive one.
        assert len(seen) == 1
        assert seen[0].name == _INTERACTIVE_TOOL_NAME

    async def test_no_text_still_captures_and_skips_empty_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_dispatch(monkeypatch)
        provider = _ScriptedProvider(
            responses=[
                LLMResponse(
                    text="",  # the component IS the answer
                    tool_calls=(
                        ToolCall(
                            id="call_1",
                            name=_INTERACTIVE_TOOL_NAME,
                            arguments={
                                "conversation_id": "11111111-1111-4111-8111-111111111111",
                                "body": "Elige una opción:",
                                "list": {
                                    "button": "Ver",
                                    "items": [{"id": "a", "title": "Uno"}],
                                },
                            },
                        ),
                    ),
                ),
            ]
        )
        bundle = _bundle(tools=frozenset({_INTERACTIVE_TOOL_NAME}))
        # Register the tool so ``get_openai_tools`` returns a non-empty
        # definition list; otherwise the handler short-circuits on the
        # very first iteration with ``not tools_arg``. The dispatch
        # itself is monkey-patched above so this never hits the DB.
        registry = MCPRegistry()
        registry.register(SendInteractive())
        handler = make_handler_node("info", _LoaderStub(bundle), _router(provider), registry)
        out = await handler(_make_state(bundle.tenant_id))
        # No text was emitted and none was synthesized — the empty
        # fallback path is gated on ``interactive_payload is None``.
        assert out["response"] == ""
        assert out["interactive_payload"]["list"]["button"] == "Ver"

    async def test_skipped_envelope_does_not_capture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Whitelist violation: the dispatcher returns
        # ``status='skipped:not_in_whitelist'`` and our capture path
        # gates on ``status='ok'``. The agent then falls through to the
        # next iteration of the loop (which we cap with a 2-response
        # script so the test terminates).
        _stub_dispatch(monkeypatch, status="skipped:not_in_whitelist")
        provider = _ScriptedProvider(
            responses=[
                LLMResponse(
                    text="",
                    tool_calls=(
                        ToolCall(
                            id="call_1",
                            name=_INTERACTIVE_TOOL_NAME,
                            arguments={
                                "conversation_id": "11111111-1111-4111-8111-111111111111",
                                "body": "?",
                                "buttons": [{"id": "a", "title": "x"}],
                            },
                        ),
                    ),
                ),
                LLMResponse(text="Lo siento, opción no disponible.", tool_calls=()),
            ]
        )
        bundle = _bundle(tools=frozenset({_INTERACTIVE_TOOL_NAME}))
        # Register the tool so ``get_openai_tools`` returns a non-empty
        # definition list; otherwise the handler short-circuits on the
        # very first iteration with ``not tools_arg``. The dispatch
        # itself is monkey-patched above so this never hits the DB.
        registry = MCPRegistry()
        registry.register(SendInteractive())
        handler = make_handler_node("info", _LoaderStub(bundle), _router(provider), registry)
        out = await handler(_make_state(bundle.tenant_id))
        # Loop did not exit on the bad envelope: a second LLM call
        # produced the final text. Empty interactive_payload signals
        # the capture didn't happen.
        assert provider.calls >= 2
        assert out["interactive_payload"] == {}
        assert out["response"] == "Lo siento, opción no disponible."
