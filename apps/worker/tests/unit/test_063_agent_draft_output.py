"""Spec 063, requisito 3 — el borrador no se pierde por el formato.

El 2026-11-18, ``gpt-5.6-sol`` devolvió dos veces un JSON que no se pudo leer
(``bad_json``) y nada dijo dónde. La llamada del constructor pide ahora la salida en
JSON cuando el modelo lo admite, distingue la salida cortada y registra cómo terminó
el modelo, sin una sola palabra de lo escrito. Sin reintentos: cada llamada se paga.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

import pytest
from nexus_api.services.builder.agent_draft import BuilderUnavailable
from structlog.testing import capture_logs

from nexus_worker.jobs.handlers import agent_draft
from nexus_worker.runtime import llm

pytestmark = pytest.mark.unit

SECRET = "Texto del borrador que no puede salir en ningún registro"


class _Provider:
    calls: ClassVar[list[dict[str, Any]]] = []
    answer: ClassVar[Any] = llm.Completion(
        text='{"voice": {}}', finish_reason="stop", output_tokens=5400
    )

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def acomplete_detailed(self, **kwargs: Any) -> llm.Completion:
        type(self).calls.append(kwargs)
        return type(self).answer


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> type[_Provider]:
    from nexus_worker import config

    _Provider.calls = []
    _Provider.answer = llm.Completion(
        text='{"voice": {}}', finish_reason="stop", output_tokens=5400
    )
    monkeypatch.setattr(llm, "LiteLLMProvider", _Provider)
    monkeypatch.setattr(config.get_worker_settings(), "llm_use_inmemory", False)
    return _Provider


async def _call(json_mode: bool, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(llm, "supports_json_object", lambda model: json_mode)
    complete = agent_draft.default_complete(uuid.uuid4())
    assert complete is not None
    return await complete([{"role": "user", "content": "Describe el agente en JSON"}])


async def test_it_asks_for_json_when_the_model_takes_it(
    provider: type[_Provider], monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_logs() as logs:
        text = await _call(True, monkeypatch)
    assert text == '{"voice": {}}'
    (call,) = provider.calls
    assert call["extra"] == {"response_format": {"type": "json_object"}}
    (out,) = [e for e in logs if e["event"] == "builder.model_output"]
    assert out["json_mode"] is True and out["finish_reason"] == "stop"
    assert out["output_tokens"] == 5400


async def test_without_json_support_it_asks_as_before(
    provider: type[_Provider], monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_logs() as logs:
        await _call(False, monkeypatch)
    (call,) = provider.calls
    assert not call.get("extra")
    (out,) = [e for e in logs if e["event"] == "builder.model_output"]
    assert out["json_mode"] is False


async def test_a_cut_output_is_truncated_not_bad_json(
    provider: type[_Provider], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider.answer = llm.Completion(
        text='{"voice": {"tone": "' + SECRET, finish_reason="length", output_tokens=16000
    )
    with capture_logs() as logs, pytest.raises(BuilderUnavailable) as raised:
        await _call(True, monkeypatch)
    assert str(raised.value) == "truncated"
    assert len(provider.calls) == 1, "sin reintentos"
    assert SECRET not in repr(logs)


async def test_the_last_output_is_there_for_the_failure_log(
    provider: type[_Provider], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "supports_json_object", lambda model: True)
    complete = agent_draft.default_complete(uuid.uuid4())
    assert complete is not None
    await complete([{"role": "user", "content": "JSON"}])
    assert agent_draft.last_output(complete) == {
        "json_mode": True,
        "finish_reason": "stop",
        "output_tokens": 5400,
    }
    assert agent_draft.last_output(None) == {}
