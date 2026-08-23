"""Fase 1 — resolver, console isolation, operator 503 vs companion 409."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest
from fastapi import HTTPException

from nexus_api.core.llm_proxy import (
    LLM_PROXY_UNAVAILABLE,
    LLMProxyUnavailable,
    apply_litellm_proxy_kwargs,
    llm_proxy_partner_scope,
    resolve_litellm_proxy,
    virtual_key_for,
)
from nexus_api.services.prompt_improver.service import LiteLLMPromptImproverProvider

PARTNER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1")
PARTNER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2")
KEY_A = "sk-vk-partner-a"
KEY_B = "sk-vk-partner-b"
BASE = "http://litellm.proxy.test"
VENDOR_ANTHROPIC = "sk-ant-should-never-be-used"


@pytest.fixture
def proxy_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", BASE)
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        json.dumps({str(PARTNER_A): KEY_A, str(PARTNER_B): KEY_B}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", VENDOR_ANTHROPIC)
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy._settings_base_and_keys",
        lambda: (BASE, json.dumps({str(PARTNER_A): KEY_A, str(PARTNER_B): KEY_B})),
    )


def test_partner_a_cannot_spend_partner_b_virtual_key(proxy_map: None) -> None:
    """Veto 1 — resolver returns only A's key for A."""
    target = resolve_litellm_proxy(PARTNER_A)
    assert target.api_key == KEY_A
    assert target.api_key != KEY_B
    assert target.partner_id == PARTNER_A
    assert virtual_key_for(PARTNER_A) == KEY_A
    assert virtual_key_for(PARTNER_A) != virtual_key_for(PARTNER_B)
    assert resolve_litellm_proxy(PARTNER_B).api_key == KEY_B


def test_console_injected_fields_stripped(proxy_map: None) -> None:
    """Veto 3 — prepare path: no partner_id; tenant_id stripped; no inject."""
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
                    "role": "companion",
                    "partner_id": str(PARTNER_B),
                    "api_key": KEY_B,
                },
            }
        )
    assert "partner_id" not in kwargs
    assert kwargs["api_key"] == KEY_A
    assert kwargs["api_base"] == BASE
    assert kwargs["api_key"] != KEY_B
    assert kwargs["api_key"] != VENDOR_ANTHROPIC
    extra_body = kwargs.get("extra_body") or {}
    assert "partner_id" not in extra_body
    assert "api_key" not in extra_body
    assert "api_base" not in extra_body
    meta = kwargs.get("metadata") or {}
    assert "tenant_id" not in meta
    assert "partner_id" not in meta
    assert "api_key" not in meta
    assert meta.get("role") == "companion"


def test_missing_base_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.delenv("NEXUS_LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.setenv("LITELLM_PROXY_VIRTUAL_KEYS", json.dumps({str(PARTNER_A): KEY_A}))
    monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
    with pytest.raises(LLMProxyUnavailable, match="LITELLM_PROXY_API_BASE"):
        resolve_litellm_proxy(PARTNER_A)


def test_codes_are_distinct() -> None:
    assert LLMProxyUnavailable("x").code == LLM_PROXY_UNAVAILABLE
    assert LLM_PROXY_UNAVAILABLE != "wallet_empty"


def test_companion_http_is_409_llm_proxy_unavailable_not_wallet_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus_api.api.console import companion as companion_api

    monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.delenv("NEXUS_LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
    companion_api._provider = None
    companion_api._graph = None
    with pytest.raises(HTTPException) as exc:
        companion_api._require_proxy(PARTNER_A)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == LLM_PROXY_UNAVAILABLE
    assert exc.value.detail["code"] != "wallet_empty"
    companion_api.reset_graph_cache_for_tests()


def test_inmemory_companion_skips_preflight() -> None:
    from nexus_worker.runtime.llm import InMemoryProvider

    from nexus_api.api.console import companion as companion_api

    companion_api.set_provider_for_tests(InMemoryProvider())
    companion_api._require_proxy(PARTNER_A)  # does not raise
    companion_api.reset_graph_cache_for_tests()


def _patch_acompletion(monkeypatch: pytest.MonkeyPatch, impl: Any) -> Any:
    import litellm

    monkeypatch.setattr(litellm, "acompletion", impl)
    return impl


async def test_missing_api_base_does_not_call_vendor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Veto 2 — missing api_base: acompletion never runs, vendor env unused."""
    import litellm

    called: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> Any:
        called.append(kwargs)
        raise AssertionError("vendor must not be called")

    monkeypatch.delenv("LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.delenv("NEXUS_LITELLM_PROXY_API_BASE", raising=False)
    monkeypatch.setenv("LITELLM_PROXY_VIRTUAL_KEYS", json.dumps({str(PARTNER_A): KEY_A}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", VENDOR_ANTHROPIC)
    monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
    _patch_acompletion(monkeypatch, _fake)
    provider = LiteLLMPromptImproverProvider()
    with llm_proxy_partner_scope(PARTNER_A), pytest.raises(LLMProxyUnavailable):
        await provider.acomplete(
            tenant_id=uuid.uuid4(),
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hola"}],
            max_output_tokens=16,
            timeout_s=5.0,
        )
    assert called == []
    assert not any((kw.get("api_key") == os.environ["ANTHROPIC_API_KEY"]) for kw in called)
    assert litellm.acompletion is _fake


async def test_timeout_does_not_use_vendor_env(
    monkeypatch: pytest.MonkeyPatch, proxy_map: None
) -> None:
    """Veto 2 — timeout stays on proxy; never ANTHROPIC_API_KEY."""

    class Timeout(Exception):
        pass

    captured: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> Any:
        captured.append(kwargs)
        raise Timeout("dns/timeout")

    _patch_acompletion(monkeypatch, _fake)
    provider = LiteLLMPromptImproverProvider()
    with llm_proxy_partner_scope(PARTNER_A), pytest.raises(LLMProxyUnavailable):
        await provider.acomplete(
            tenant_id=uuid.uuid4(),
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hola"}],
            max_output_tokens=16,
            timeout_s=5.0,
        )
    assert captured
    for kw in captured:
        assert kw["api_base"] == BASE
        assert kw["api_key"] == KEY_A
        assert kw["api_key"] != os.environ["ANTHROPIC_API_KEY"]
        assert "partner_id" not in kw


async def test_improver_invoke_strips_tenant_and_never_sends_partner_id(
    monkeypatch: pytest.MonkeyPatch, proxy_map: None
) -> None:
    """Veto 3 — invoke path kwargs never include partner_id."""
    captured: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> Any:
        captured.append(kwargs)
        msg = type(
            "Msg", (), {"content": "<improved_prompt>x</improved_prompt><summary>- a</summary>"}
        )()
        choice = type("Choice", (), {"message": msg})()
        return type("Resp", (), {"choices": [choice], "usage": None})()

    _patch_acompletion(monkeypatch, _fake)
    provider = LiteLLMPromptImproverProvider()
    with llm_proxy_partner_scope(PARTNER_A):
        await provider.acomplete(
            tenant_id=uuid.uuid4(),
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hola"}],
            max_output_tokens=16,
            timeout_s=5.0,
        )
    assert captured
    assert captured[0]["api_key"] == KEY_A
    assert captured[0]["api_base"] == BASE
    assert "tenant_id" not in (captured[0].get("metadata") or {})
    assert "partner_id" not in captured[0]
