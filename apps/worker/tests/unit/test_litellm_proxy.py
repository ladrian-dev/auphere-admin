"""Fase 1 — worker hops go through the LiteLLM OSS proxy, fail-closed."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from nexus_api.core.llm_proxy import (
    LLM_PROXY_UNAVAILABLE,
    LLMProxyUnavailable,
    apply_litellm_proxy_kwargs,
    llm_proxy_partner_scope,
    resolve_litellm_proxy,
)

from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound
from nexus_worker.runtime.llm import InMemoryProvider, LiteLLMProvider, LLMCall

PARTNER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1")
PARTNER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2")
KEY_A = "sk-vk-partner-a"
KEY_B = "sk-vk-partner-b"
BASE = "http://litellm.proxy.test"


def _keys(**pairs: str) -> str:
    return json.dumps(pairs)


@pytest.fixture
def proxy_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", BASE)
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        _keys(**{str(PARTNER_A): KEY_A, str(PARTNER_B): KEY_B}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-should-never-be-used")
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy._settings_base_and_keys",
        lambda: (BASE, _keys(**{str(PARTNER_A): KEY_A, str(PARTNER_B): KEY_B})),
    )


class _RecordingAcompletion:
    def __init__(self, *, exc: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.exc = exc

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return {"choices": [{"message": {"content": "ok"}}]}


@pytest.fixture
def patched_litellm(monkeypatch: pytest.MonkeyPatch, proxy_map: None) -> _RecordingAcompletion:
    import litellm

    stub = _RecordingAcompletion()
    monkeypatch.setattr(litellm, "acompletion", stub)
    return stub


class TestPartnerKeyIsolation:
    def test_a_cannot_spend_b_key(self, proxy_map: None) -> None:
        a = resolve_litellm_proxy(PARTNER_A)
        b = resolve_litellm_proxy(PARTNER_B)
        assert a.api_key == KEY_A
        assert b.api_key == KEY_B
        assert a.api_key != b.api_key
        with llm_proxy_partner_scope(PARTNER_A):
            kwargs = apply_litellm_proxy_kwargs({"model": "anthropic/claude-sonnet-4-6"})
        assert kwargs["api_key"] == KEY_A
        assert kwargs["api_key"] != KEY_B


class TestNoVendorFallback:
    async def test_missing_base_does_not_call_vendor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import litellm

        monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
        monkeypatch.delenv("NEXUS_LITELLM_PROXY_API_BASE", raising=False)
        monkeypatch.setenv("LITELLM_PROXY_VIRTUAL_KEYS", _keys(**{str(PARTNER_A): KEY_A}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-used")
        monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
        stub = _RecordingAcompletion()
        monkeypatch.setattr(litellm, "acompletion", stub)
        provider = LiteLLMProvider(context_management=None)
        with llm_proxy_partner_scope(PARTNER_A), pytest.raises(LLMProxyUnavailable):
            await provider.acomplete(
                tenant_id=uuid.uuid4(),
                role="respond",
                model="anthropic/claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hola"}],
            )
        assert stub.calls == []

    async def test_timeout_retries_same_base_never_vendor_key(
        self, monkeypatch: pytest.MonkeyPatch, proxy_map: None
    ) -> None:
        import litellm

        class Timeout(Exception):
            pass

        stub = _RecordingAcompletion(exc=Timeout("dns/timeout"))
        monkeypatch.setattr(litellm, "acompletion", stub)
        provider = LiteLLMProvider(context_management=None)
        with llm_proxy_partner_scope(PARTNER_A), pytest.raises(LLMProxyUnavailable):
            await provider.acomplete(
                tenant_id=uuid.uuid4(),
                role="respond",
                model="anthropic/claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hola"}],
            )
        assert stub.calls
        for kw in stub.calls:
            assert kw["api_base"] == BASE
            assert kw["api_key"] == KEY_A
            assert kw["api_key"] != os.environ["ANTHROPIC_API_KEY"]


class TestConsoleCannotInjectAuth:
    async def test_extra_partner_id_and_api_key_are_stripped(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        provider = LiteLLMProvider(context_management=None)
        with llm_proxy_partner_scope(PARTNER_A):
            await provider.acomplete_with_tools(
                tenant_id=uuid.uuid4(),
                role="companion",
                model="anthropic/claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hola"}],
                tools=[],
                extra={
                    "partner_id": str(PARTNER_B),
                    "api_key": KEY_B,
                    "api_base": "https://api.anthropic.com",
                },
            )
        kw = patched_litellm.calls[0]
        assert "partner_id" not in kw
        assert kw["api_key"] == KEY_A
        assert kw["api_base"] == BASE

    def test_prepare_kwargs_strip_console_and_tenant(self, proxy_map: None) -> None:
        with llm_proxy_partner_scope(PARTNER_A):
            kwargs = apply_litellm_proxy_kwargs(
                {
                    "model": "anthropic/claude-sonnet-4-6",
                    "partner_id": str(PARTNER_B),
                    "api_key": KEY_B,
                    "api_base": "https://api.anthropic.com",
                    "extra_body": {
                        "partner_id": str(PARTNER_B),
                        "api_key": KEY_B,
                        "api_base": "https://api.anthropic.com",
                    },
                    "metadata": {
                        "tenant_id": "c0a1",
                        "role": "respond",
                        "partner_id": str(PARTNER_B),
                    },
                }
            )
        assert "partner_id" not in kwargs
        assert kwargs["api_key"] == KEY_A
        assert kwargs["api_base"] == BASE
        extra_body = kwargs.get("extra_body") or {}
        assert "partner_id" not in extra_body
        assert "api_key" not in extra_body
        assert "api_base" not in extra_body
        assert "tenant_id" not in (kwargs.get("metadata") or {})
        assert "partner_id" not in (kwargs.get("metadata") or {})


class TestNoTenantMetadata:
    async def test_metadata_tenant_id_is_stripped(
        self, patched_litellm: _RecordingAcompletion
    ) -> None:
        provider = LiteLLMProvider(context_management=None)
        tenant = uuid.uuid4()
        with llm_proxy_partner_scope(PARTNER_A):
            await provider.acomplete(
                tenant_id=tenant,
                role="respond",
                model="anthropic/claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hola"}],
            )
        meta = patched_litellm.calls[0].get("metadata") or {}
        assert "tenant_id" not in meta
        assert meta.get("role") == "respond"


class TestInMemoryUnchanged:
    async def test_inmemory_still_records_tenant_and_skips_proxy(self) -> None:
        provider = InMemoryProvider()
        tenant = uuid.uuid4()
        text = await provider.acomplete(
            tenant_id=tenant,
            role="respond",
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hola"}],
        )
        assert text
        assert isinstance(provider.calls[0], LLMCall)
        assert provider.calls[0].tenant_id == tenant


class _Pipeline:
    def __init__(self) -> None:
        self.called = False

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.called = True
        return {"intent": "info", "response": "ok", "tool_calls": []}


class TestWalletVsProxySkip:
    async def test_wallet_empty_wins_over_missing_proxy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "nexus_api.metering.wallet.allow_channel_turn",
            AsyncMock(return_value=False),
        )
        monkeypatch.setattr(
            "nexus_api.core.llm_proxy.partner_id_for_tenant_standalone",
            AsyncMock(return_value=PARTNER_A),
        )
        monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
        monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
        pipeline = _Pipeline()
        result = await process_inbound(
            InboundEvent(
                tenant_id=uuid.uuid4(),
                channel_id=uuid.uuid4(),
                user_id="u1",
                content="hola",
                provider="whatsapp",
            ),
            pipeline=pipeline,
        )
        assert result["skipped"] == "wallet_empty"
        assert pipeline.called is False

    async def test_proxy_unavailable_is_distinct_skip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "nexus_api.metering.wallet.allow_channel_turn",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            "nexus_api.core.llm_proxy.partner_id_for_tenant_standalone",
            AsyncMock(return_value=PARTNER_A),
        )
        monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
        monkeypatch.delenv("NEXUS_LITELLM_PROXY_API_BASE", raising=False)
        monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
        pipeline = _Pipeline()
        result = await process_inbound(
            InboundEvent(
                tenant_id=uuid.uuid4(),
                channel_id=uuid.uuid4(),
                user_id="u1",
                content="hola",
                provider="whatsapp",
            ),
            pipeline=pipeline,
        )
        assert result["skipped"] == LLM_PROXY_UNAVAILABLE
        assert result["skipped"] != "wallet_empty"
        assert pipeline.called is False
