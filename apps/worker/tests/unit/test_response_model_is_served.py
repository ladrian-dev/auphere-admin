"""Spec 065, T041 (requisitos 3.1, 5.3 y 5.4): el turno dice con qué modelo respondió de verdad.

- ``LLMResponse`` lleva el modelo que respondió (``model``), si fue una reserva
  (``fell_back``) y el ``finish_reason`` del proveedor;
- ``response_model`` del estado es ese modelo, también con elección del agente, y
  ``response_fell_back`` dice si el turno acabó en la reserva;
- ``handler.turn_complete`` y ``llm.respond_fell_back`` nombran modelos, nunca texto;
  ``llm.respond_fell_back`` lleva los campos del contrato (contracts/api.md, data-model.md
  §7): ``chosen``, ``served`` y ``reason`` (``error``, ``timeout``, ``refusal`` o
  ``rate_limit``), sacado de la clase original del último error antes de la reserva;
- la reescritura del juez va por la cadena del agente, no por el modelo global;
- ``llm.attempt_failed`` lleva la clase del error original aunque se mapee a
  ``LLMProxyUnavailable``.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

import pytest
from nexus_api.core.llm_proxy import LLMProxyUnavailable
from structlog.testing import capture_logs

import nexus_worker.runtime.llm as llm_module
import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime.llm import CooldownBook, LLMRouter
from tests.unit.test_pipeline_router import (  # noqa: F401
    _bundle,
    _provider,
    _turn,
    world,
)

TERRA = "openai/gpt-5.6-terra"
FALLBACK = "legacy/fallback"
TEXT = "Abrimos de 10 a 14."
MESSAGES = [{"role": "user", "content": "¿Abren el sábado?"}]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "_RETRY_BACKOFF_S", 0.0)


def _router(provider: Any, respond_model: str = "m/first") -> LLMRouter:
    return LLMRouter(
        provider=provider,
        classify_model="legacy/classify",
        respond_model=respond_model,
        fallback_model="m/second",
        cooldowns=CooldownBook(),
        retry_backoff_s=0.0,
    )


async def test_the_response_says_which_model_answered_and_if_it_fell_back() -> None:
    fell = await _router(_provider(down=frozenset({"m/first"}))).respond_with_tools(
        tenant_id=uuid.uuid4(), role="info", messages=MESSAGES, tools=[]
    )
    assert (fell.model, fell.fell_back) == ("m/second", True)
    first = await _router(_provider()).respond_with_tools(
        tenant_id=uuid.uuid4(), role="info", messages=MESSAGES, tools=[]
    )
    assert (first.model, first.fell_back) == ("m/first", False)


async def test_attempt_failed_names_the_original_class() -> None:
    provider = _provider()

    async def mapped(**_kwargs: Any) -> Any:
        original = type("RateLimitError", (Exception,), {})("429")
        raise LLMProxyUnavailable("proxy unreachable") from original

    provider.acomplete_with_tools = mapped  # type: ignore[method-assign]
    with capture_logs() as logs, pytest.raises(LLMProxyUnavailable):
        await _router(provider).respond_with_tools(
            tenant_id=uuid.uuid4(), role="info", messages=MESSAGES, tools=[]
        )
    failed = [e for e in logs if e["event"] == "llm.attempt_failed"]
    assert failed
    assert all(e["error_class"] == "RateLimitError" for e in failed)
    assert all(e["mapped_to"] == "LLMProxyUnavailable" for e in failed)


def _chosen(model_id: str) -> Any:
    return dataclasses.replace(_bundle(), respond_model=model_id, respond_model_set_by="partner")


def _no_text(event: dict[str, Any]) -> None:
    for key in ("response", "text", "messages", "content", "draft"):
        assert key not in event, (event["event"], key)
    assert TEXT not in repr(event)


async def test_response_model_is_the_one_that_answered_with_an_agent_choice(
    world: Any,  # noqa: F811
) -> None:
    world.catalog = None
    with capture_logs() as logs:
        out = await _turn(_chosen(TERRA), _provider(down=frozenset({TERRA})))
    assert out["response"] == TEXT
    assert out["response_model"] == FALLBACK
    assert out["response_fell_back"] is True

    [fell] = [e for e in logs if e["event"] == "llm.respond_fell_back"]
    assert (fell["chosen"], fell["served"], fell["reason"]) == (TERRA, FALLBACK, "error")
    assert "intended" not in fell
    _no_text(fell)
    [complete] = [e for e in logs if e["event"] == "handler.turn_complete"]
    assert complete["respond_model"] == FALLBACK
    assert complete["fell_back"] is True
    _no_text(complete)


def _failing(error: Exception) -> Any:
    """``_provider`` cuyo modelo elegido (Terra) falla con ``error`` cada vez."""
    provider = _provider()
    original = provider.acomplete_with_tools
    tried: list[str] = []

    async def failing(**kwargs: Any) -> Any:
        tried.append(kwargs["model"])
        if kwargs["model"] == TERRA:
            raise error
        return await original(**kwargs)

    provider.acomplete_with_tools = failing  # type: ignore[method-assign]
    provider.tried = tried  # type: ignore[attr-defined]
    return provider


@pytest.mark.parametrize(
    ("error", "reason", "attempts"),
    [
        (type("Timeout", (Exception,), {})("plazo agotado"), "timeout", 2),
        (llm_module.ProviderRefused(TERRA), "refusal", 1),
    ],
    ids=["timeout", "refusal"],
)
async def test_the_fall_back_says_why(
    world: Any,  # noqa: F811
    error: Exception,
    reason: str,
    attempts: int,
) -> None:
    world.catalog = None
    provider = _failing(error)
    with capture_logs() as logs:
        out = await _turn(_chosen(TERRA), provider)
    assert out["response_model"] == FALLBACK
    [fell] = [e for e in logs if e["event"] == "llm.respond_fell_back"]
    assert (fell["chosen"], fell["served"], fell["reason"]) == (TERRA, FALLBACK, reason)
    _no_text(fell)
    assert provider.tried.count(TERRA) == attempts, "un rechazo no se reintenta"


async def test_a_mapped_rate_limit_reads_as_rate_limit() -> None:
    """La razón sale de la clase original: un 429 que el proxy convierte en
    ``LLMProxyUnavailable`` sigue siendo ``rate_limit``."""
    provider = _provider()
    original = provider.acomplete_with_tools

    async def mapped(**kwargs: Any) -> Any:
        if kwargs["model"] == "m/first":
            cause = type("RateLimitError", (Exception,), {})("429")
            raise LLMProxyUnavailable("proxy unreachable") from cause
        return await original(**kwargs)

    provider.acomplete_with_tools = mapped  # type: ignore[method-assign]
    got = await _router(provider).respond_with_tools(
        tenant_id=uuid.uuid4(), role="info", messages=MESSAGES, tools=[]
    )
    assert (got.model, got.fell_back, got.fallback_reason) == ("m/second", True, "rate_limit")


async def test_without_a_fallback_it_is_the_chosen_model(world: Any) -> None:  # noqa: F811
    world.catalog = None
    with capture_logs() as logs:
        out = await _turn(_chosen(TERRA), _provider())
    assert (out["response_model"], out["response_fell_back"]) == (TERRA, False)
    assert not [e for e in logs if e["event"] == "llm.respond_fell_back"]


async def test_the_rewrite_goes_through_the_agents_chain() -> None:
    calls: list[dict[str, Any]] = []

    class Router:
        async def respond(self, **kwargs: Any) -> str:
            calls.append(kwargs)
            return "Reescrito."

    got = await pipeline._ask_agent_to_rewrite(
        llm_router=Router(),  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        intent="info",
        original="Borrador",
        feedback="Más corto",
        model=TERRA,
    )
    assert got == "Reescrito."
    assert calls[0]["model_override"] == TERRA
