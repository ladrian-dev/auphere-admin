"""Spec 059, T037 (requisito 5.7) — el Playground QA responde con los modelos del runtime.

Antes, ``api/qa.py`` fijaba a mano el modelo de clasificar y el de responder. Ahora
los saca del registro de la plataforma (``default_models()``) al construir su grafo:
si el despliegue cambia el modelo de responder, el Playground cambia con él.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.api import qa as qa_api


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """El registro de siempre, con los dos modelos del Playground cambiados por el
    despliegue."""
    import nexus_worker.platform_models as platform_models

    real = platform_models.default_models
    changed = {"qa_classify": "mistral/clasifica-059", "qa_respond": "mistral/responde-059"}
    monkeypatch.setattr(platform_models, "default_models", lambda: {**real(), **changed})
    return changed


def test_the_graph_is_built_with_the_registry_s_models(
    registry: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus_worker.runtime.agent_loader as agent_loader
    import nexus_worker.runtime.llm as llm
    import nexus_worker.runtime.qa_pipeline as qa_pipeline

    import nexus_api.core.qa_checkpointer as qa_checkpointer

    seen: dict[str, Any] = {}

    class FakeRouter:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(llm, "LLMRouter", FakeRouter)
    monkeypatch.setattr(llm, "LiteLLMProvider", lambda *a, **k: object())
    monkeypatch.setattr(agent_loader, "AgentLoader", lambda *a, **k: object())
    monkeypatch.setattr(qa_pipeline, "build_qa_pipeline", lambda **_k: "graph")
    monkeypatch.setattr(qa_checkpointer, "get_qa_checkpointer", lambda: None)
    monkeypatch.setattr(qa_api, "_qa_pipeline_dry", None)

    assert qa_api._get_qa_pipeline(live=False) == "graph"
    assert seen["classify_model"] == registry["qa_classify"]
    assert seen["respond_model"] == registry["qa_respond"]
    assert seen["classify_fallback_model"] == registry["qa_respond"]


def test_the_names_the_console_checks_are_the_registry_s(registry: dict[str, str]) -> None:
    """La consola comprueba ``QA_CLASSIFY_MODEL`` y ``QA_RESPOND_MODEL`` contra el
    catálogo antes de cada turno (``console/playground.py``): tienen que ser los
    mismos con los que se construye el grafo."""
    assert registry["qa_classify"] == qa_api.QA_CLASSIFY_MODEL
    assert registry["qa_respond"] == qa_api.QA_RESPOND_MODEL
    with pytest.raises(AttributeError):
        _ = qa_api.QA_NOT_A_THING  # type: ignore[attr-defined]
