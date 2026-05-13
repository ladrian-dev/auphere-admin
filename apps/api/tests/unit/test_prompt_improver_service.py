"""Block N — pure-Python tests for the prompt improver service.

These tests do NOT touch the DB or the FastAPI client. They drive the
service directly with the ``FakePromptImproverProvider`` so the
contract of meta-prompt building + response parsing is locked in.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.services.prompt_improver import (
    SUPPORTED_MODES,
    AgentContext,
    FakePromptImproverProvider,
    MalformedResponseError,
    PromptImproverError,
    PromptTooLongError,
    build_meta_messages,
    improve_prompt,
)
from nexus_api.services.prompt_improver.meta_prompt import META_PROMPT_VERSION

# Async tests are decorated individually below; we keep the module
# free of a global ``pytestmark`` so the synchronous helpers above
# don't trip the asyncio plugin's "test marked async but not async"
# warning.
_async = pytest.mark.asyncio


def _ctx(**over: object) -> AgentContext:
    defaults: dict[str, object] = {
        "tenant_name": "Test Tenant",
        "use_case": "barbershop_v1",
        "channel": "whatsapp",
        "language": "es-CL",
        "available_tools": ("booking.create_appointment", "client.get_history"),
        "business_hours": "Lun-Vie 10-19",
        "agent_name": "Alex",
        "timezone": "America/Santiago",
        "market": "CL",
    }
    defaults.update(over)
    return AgentContext(**defaults)  # type: ignore[arg-type]


def test_supported_modes_include_general_and_focused() -> None:
    assert "general" in SUPPORTED_MODES
    assert "shorter" in SUPPORTED_MODES
    assert "edge_cases" in SUPPORTED_MODES
    assert "english" in SUPPORTED_MODES


def test_build_meta_messages_carries_cache_control_on_system() -> None:
    """Prompt caching saves ~90% on input tokens after the first call;
    that only works if cache_control is set on the system block. If a
    future refactor drops it, this test catches it."""
    messages = build_meta_messages(
        draft_prompt="hola",
        mode="general",
        feedback=None,
        context=_ctx().to_block(),
    )
    assert messages[0]["role"] == "system"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    # The version marker is embedded in the system text so Langfuse
    # traces can correlate output quality with meta-prompt revisions.
    assert META_PROMPT_VERSION in content[0]["text"]


def test_build_meta_messages_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unsupported mode"):
        build_meta_messages(
            draft_prompt="hola",
            mode="hallucinate",
            feedback=None,
            context=_ctx().to_block(),
        )


def test_user_block_includes_context_tools_and_mode() -> None:
    messages = build_meta_messages(
        draft_prompt="Sos el asistente.",
        mode="shorter",
        feedback="más conciso",
        context=_ctx().to_block(),
    )
    user_text = messages[1]["content"]
    assert isinstance(user_text, str)
    assert "<tenant_name>Test Tenant</tenant_name>" in user_text
    assert "<channel>whatsapp</channel>" in user_text
    assert "<mode>shorter</mode>" in user_text
    assert "<feedback>más conciso</feedback>" in user_text
    assert "booking.create_appointment" in user_text
    assert "<draft_prompt>" in user_text and "Sos el asistente." in user_text


@_async
async def test_improve_prompt_happy_path_parses_default_xml() -> None:
    provider = FakePromptImproverProvider()
    result = await improve_prompt(
        tenant_id=uuid.uuid4(),
        draft_prompt="Sos el asistente.",
        mode="general",
        feedback=None,
        context=_ctx(),
        provider=provider,
        model="anthropic/claude-sonnet-4-6",
        timeout_s=30.0,
        max_input_chars=20_000,
        max_output_tokens=4_000,
    )
    assert "Test Tenant" in result.improved_prompt
    assert len(result.summary_of_changes) == 3
    assert result.mode == "general"
    assert result.meta_prompt_version == META_PROMPT_VERSION
    assert result.latency_ms >= 0
    assert result.input_tokens == 3120
    assert result.output_tokens == 820
    assert len(provider.calls) == 1


@_async
async def test_improve_prompt_too_long_raises() -> None:
    provider = FakePromptImproverProvider()
    huge = "x" * 21_000
    with pytest.raises(PromptTooLongError):
        await improve_prompt(
            tenant_id=uuid.uuid4(),
            draft_prompt=huge,
            mode="general",
            feedback=None,
            context=_ctx(),
            provider=provider,
            model="anthropic/claude-sonnet-4-6",
            timeout_s=30.0,
            max_input_chars=20_000,
            max_output_tokens=4_000,
        )
    assert provider.calls == [], "must not call the LLM when over the limit"


@_async
async def test_improve_prompt_empty_draft_raises() -> None:
    provider = FakePromptImproverProvider()
    with pytest.raises(PromptImproverError):
        await improve_prompt(
            tenant_id=uuid.uuid4(),
            draft_prompt="   ",
            mode="general",
            feedback=None,
            context=_ctx(),
            provider=provider,
            model="anthropic/claude-sonnet-4-6",
            timeout_s=30.0,
            max_input_chars=20_000,
            max_output_tokens=4_000,
        )


@_async
async def test_improve_prompt_unsupported_mode_raises() -> None:
    provider = FakePromptImproverProvider()
    with pytest.raises(PromptImproverError):
        await improve_prompt(
            tenant_id=uuid.uuid4(),
            draft_prompt="ok",
            mode="hallucinate",
            feedback=None,
            context=_ctx(),
            provider=provider,
            model="anthropic/claude-sonnet-4-6",
            timeout_s=30.0,
            max_input_chars=20_000,
            max_output_tokens=4_000,
        )


@_async
async def test_improve_prompt_malformed_response_raises() -> None:
    """Missing <improved_prompt> block must surface as MalformedResponseError
    with the raw text preserved for log forensics."""
    provider = FakePromptImproverProvider(
        responder=lambda messages, mode: "I don't feel like complying today."
    )
    with pytest.raises(MalformedResponseError) as exc_info:
        await improve_prompt(
            tenant_id=uuid.uuid4(),
            draft_prompt="hola",
            mode="general",
            feedback=None,
            context=_ctx(),
            provider=provider,
            model="anthropic/claude-sonnet-4-6",
            timeout_s=30.0,
            max_input_chars=20_000,
            max_output_tokens=4_000,
        )
    assert "I don't feel like complying" in exc_info.value.raw


@_async
async def test_improve_prompt_summary_can_be_empty() -> None:
    """The summary block is informational. If the model omits it the
    improver still returns successfully — the operator sees the diff and
    decides."""
    provider = FakePromptImproverProvider(
        responder=lambda messages, mode: "<improved_prompt>\nNueva versión.\n</improved_prompt>"
    )
    result = await improve_prompt(
        tenant_id=uuid.uuid4(),
        draft_prompt="hola",
        mode="shorter",
        feedback=None,
        context=_ctx(),
        provider=provider,
        model="anthropic/claude-sonnet-4-6",
        timeout_s=30.0,
        max_input_chars=20_000,
        max_output_tokens=4_000,
    )
    assert result.improved_prompt == "Nueva versión."
    assert result.summary_of_changes == ()
