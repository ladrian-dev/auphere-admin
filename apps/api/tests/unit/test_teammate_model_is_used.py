"""El cerebro que el partner elige para un teammate tiene que usarse.

Era decorativo. El formulario de alta llama «Cerebro» a una de sus cuatro
decisiones, la API lo valida contra la lista de modelos del partner
(`teammates.py:_check_model`), el cambio se anota en el hilo de cada persona
—`CHANGED_FIELDS` incluye `model`— y el run compilaba el grafo con
`settings.llm_companion_model`, siempre el mismo para todos.

O sea: el partner elegía un modelo más caro para su teammate de investigación,
veía la etiqueta de coste, leía en el hilo «cambió el cerebro», y corría el
mismo modelo que los demás. Una pantalla que miente (§V) en la palanca de
mejora más directa que tiene.

Este test mira el único sitio donde se decide: con qué modelo se compila el
grafo del turno.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _compiled_with(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Captura el modelo con el que se compila el grafo, sin tocar LiteLLM."""
    from nexus_api.api.console import companion

    seen: list[str] = []

    def _fake_build(**kwargs: Any) -> str:
        seen.append(str(kwargs.get("model")))
        return "grafo-de-mentira"

    import nexus_worker.runtime.companion as runtime

    from nexus_api.core import qa_checkpointer

    monkeypatch.setattr(runtime, "build_companion_graph", _fake_build)
    monkeypatch.setattr(companion, "_get_provider", lambda: object())
    # El checkpointer es de otro asunto: aquí solo se mira con qué modelo se
    # compila el grafo, y exigir el arranque completo escondería eso.
    monkeypatch.setattr(qa_checkpointer, "get_qa_checkpointer", lambda: object())
    monkeypatch.setattr(companion, "_graph", None)
    return seen


def test_a_teammates_brain_is_the_one_that_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_api.api.console import companion

    seen = _compiled_with(monkeypatch)

    companion._get_companion_graph(toolbelt=object(), model="anthropic/claude-opus-5")

    assert seen == ["anthropic/claude-opus-5"], (
        "el grafo se compiló con otro modelo: el cerebro del teammate se ignoró"
    )


def test_without_a_teammate_the_companion_model_still_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El Companion clásico —sin teammate— no cambia de comportamiento."""
    from nexus_api.api.console import companion
    from nexus_api.config import get_settings

    seen = _compiled_with(monkeypatch)

    companion._get_companion_graph(toolbelt=object(), model=None)

    assert seen == [get_settings().llm_companion_model]


def test_a_graph_built_for_one_teammate_is_not_cached_for_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La caché es del grafo genérico, no del de un teammate.

    Sin esta guarda, el primer teammate en pedir turno dejaría su modelo
    cacheado y los siguientes correrían con el suyo — un fallo que solo
    aparecería en producción, con varios teammates y bajo carga.
    """
    from nexus_api.api.console import companion

    seen = _compiled_with(monkeypatch)

    companion._get_companion_graph(toolbelt=None, model="anthropic/claude-opus-5")
    companion._get_companion_graph(toolbelt=None, model="openai/gpt-5.6-sol")

    assert seen == ["anthropic/claude-opus-5", "openai/gpt-5.6-sol"]
