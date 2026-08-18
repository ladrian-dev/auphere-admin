"""El parámetro ``thinking`` llega verbatim al cuerpo de Anthropic (C3).

``test_companion_graph.py`` comprueba que el grafo se lo pasa al proveedor.
Esto comprueba el tramo siguiente, que es donde de verdad se podía perder:
**LiteLLM**. Sin esto, un cambio de nombre del parámetro o una versión que
lo descarte por no reconocerlo dejaría el pensamiento vacío sin que ningún
test se pusiera rojo — y el síntoma aparecería en CO-03, construyendo la
interfaz sobre un evento que nunca trae texto.

Lo que NO se puede probar aquí, y por eso existe
``scripts/companion_thinking_smoke.py``: si Anthropic devuelve resúmenes
con texto. Eso exige una clave y una llamada real.
"""

from __future__ import annotations

import pytest
from nexus_worker.runtime.companion.prompt import COMPANION_THINKING

pytestmark = pytest.mark.unit

MODEL = "claude-sonnet-4-6"


def _anthropic_config():
    from litellm.llms.anthropic.chat.transformation import AnthropicConfig

    return AnthropicConfig()


def test_litellm_declares_thinking_as_a_supported_anthropic_param() -> None:
    """Si dejara de estar en la lista, LiteLLM lo descartaría en silencio
    (o lanzaría con ``drop_params=False``). Las dos cosas son un fallo."""
    import litellm

    supported = litellm.get_supported_openai_params(model=MODEL, custom_llm_provider="anthropic")
    assert supported is not None
    assert "thinking" in supported


def test_the_parameter_survives_the_mapping_untouched() -> None:
    mapped = _anthropic_config().map_openai_params(
        non_default_params={"thinking": dict(COMPANION_THINKING), "stream": True},
        optional_params={},
        model=MODEL,
        drop_params=False,
    )
    assert mapped["thinking"] == COMPANION_THINKING


def test_the_parameter_reaches_the_request_body() -> None:
    """El contrato completo: lo que sale por el cable lleva ``adaptive`` y
    ``summarized``, no una versión reescrita ni ``disabled``."""
    cfg = _anthropic_config()
    optional = cfg.map_openai_params(
        non_default_params={"thinking": dict(COMPANION_THINKING), "stream": True},
        optional_params={},
        model=MODEL,
        drop_params=False,
    )
    body = cfg.transform_request(
        model=MODEL,
        messages=[
            {"role": "system", "content": "S"},
            {"role": "user", "content": "hola"},
        ],
        optional_params=optional,
        litellm_params={},
        headers={},
    )
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
