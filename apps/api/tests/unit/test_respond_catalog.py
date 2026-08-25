"""F0: closed catalog, Sol defaults, hop gate, human errors."""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from nexus_worker.config import WorkerSettings
from nexus_worker.runtime.llm import _proxied_acompletion

from nexus_api.api.console import companion as companion_api
from nexus_api.api.console import playground as playground_api
from nexus_api.api.qa import QA_CLASSIFY_MODEL, QA_RESPOND_MODEL
from nexus_api.config import Settings
from nexus_api.core.respond_catalog import (
    HUMAN_TURN_ERROR,
    RESPOND_MODEL_ID_SET,
    SOL_MODEL_ID,
    UnknownCatalogModel,
    hop_models_in_catalog,
    require_hop_model,
)


def test_sol_terra_luna_are_the_closed_catalog() -> None:
    assert SOL_MODEL_ID == "openai/gpt-5.6-sol"
    assert {
        "openai/gpt-5.6-sol",
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
    } == RESPOND_MODEL_ID_SET
    assert hop_models_in_catalog(SOL_MODEL_ID, "openai/gpt-5.6-terra")
    assert not hop_models_in_catalog("anthropic/claude-sonnet-4-6")
    assert hop_models_in_catalog("")  # empty ids are ignored


def test_companion_respond_and_classify_defaults_are_sol() -> None:
    assert Settings.model_fields["llm_companion_model"].default == SOL_MODEL_ID
    assert WorkerSettings.model_fields["llm_respond_model"].default == SOL_MODEL_ID
    assert WorkerSettings.model_fields["llm_classify_model"].default == SOL_MODEL_ID
    assert Settings.model_fields["llm_companion_model"].default in RESPOND_MODEL_ID_SET
    assert WorkerSettings.model_fields["llm_respond_model"].default in RESPOND_MODEL_ID_SET
    assert WorkerSettings.model_fields["llm_classify_model"].default in RESPOND_MODEL_ID_SET


def test_playground_classify_and_respond_are_sol() -> None:
    assert QA_CLASSIFY_MODEL == SOL_MODEL_ID
    assert QA_RESPOND_MODEL == SOL_MODEL_ID
    assert hop_models_in_catalog(QA_CLASSIFY_MODEL, QA_RESPOND_MODEL)


def test_companion_catalog_miss_is_a_human_409(monkeypatch) -> None:
    monkeypatch.setattr(
        companion_api,
        "get_settings",
        lambda: type("S", (), {"llm_companion_model": "anthropic/claude-sonnet-4-6"})(),
    )
    try:
        companion_api._require_catalog_model()
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == HUMAN_TURN_ERROR
        assert "litellm" not in str(exc.detail).lower()
        assert "sk-" not in str(exc.detail)
    else:
        raise AssertionError("expected 409")


def test_companion_catalog_sol_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(
        companion_api,
        "get_settings",
        lambda: type("S", (), {"llm_companion_model": SOL_MODEL_ID})(),
    )
    companion_api._require_catalog_model()


@pytest.mark.asyncio
async def test_unknown_id_never_calls_acompletion() -> None:
    called: list[object] = []

    class _Litellm:
        async def acompletion(self, **kwargs: object) -> object:
            called.append(kwargs)
            raise AssertionError("vendor acompletion must not run")

    with pytest.raises(UnknownCatalogModel):
        require_hop_model("anthropic/claude-sonnet-4-6")

    with pytest.raises(UnknownCatalogModel):
        await _proxied_acompletion(_Litellm(), {"model": "anthropic/claude-sonnet-4-6"})
    assert called == []


def test_env_override_does_not_skip_the_catalog(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LLM_COMPANION_MODEL", "anthropic/claude-sonnet-4-6")
    assert "anthropic/claude-sonnet-4-6" not in RESPOND_MODEL_ID_SET
    with pytest.raises(UnknownCatalogModel):
        require_hop_model("anthropic/claude-sonnet-4-6")


def test_companion_does_not_read_tenant_model_bindings() -> None:
    from nexus_worker.runtime.companion import graph

    src = inspect.getsource(companion_api._get_companion_graph) + inspect.getsource(graph)
    assert "load_bindings" not in src
    assert "chain_for" not in src


@pytest.mark.asyncio
async def test_playground_scrubs_vendor_stack_from_the_stream() -> None:
    leak = (
        'event: run.completed\ndata: {"error": "litellm.BadRequestError Anthropic '
        'claude-sonnet-4-6 NEXUS_LLM_RESPOND_MODEL LITELLM_PROXY_API_BASE sk-ant-x",'
        '"status":"error"}\n\n'
    )

    async def _source():
        yield leak

    frames = [frame async for frame in playground_api._scrub_stream(_source())]
    blob = "".join(frames)
    assert HUMAN_TURN_ERROR in blob
    for needle in ("litellm", "Anthropic", "claude-", "NEXUS_", "LITELLM_", "sk-"):
        assert needle.lower() not in blob.lower()
