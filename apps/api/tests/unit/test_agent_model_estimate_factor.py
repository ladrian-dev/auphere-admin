"""Spec 065, T103 (requisitos 1.5 y 1.6): el factor de gasto de cada modelo en el precio estimado.

El selector estima lo que costaría una respuesta con cada modelo a partir de los tokens que gasta
hoy el agente. Para el mismo trabajo, los modelos no gastan los mismos tokens. Claude cuenta el
mismo texto con más tokens y su razonamiento se cobra como salida, así que la estimación
multiplica por el ``estimate_factor`` de su perfil.

Hasta la primera batería real los seis estaban a 1,0, y la consola habría enseñado Claude más
barato de lo que es. Los valores son **provisionales**, medidos el 2026-11-20 con el agente de
prueba (quickstart.md §3). Se revisan con un agente de tamaño real antes de habilitar Claude en
prod.

Los tokens y los pesos son los mismos para todos, para que la diferencia sea solo el factor:
2.000 no leídos a 1,25 (escritura), 8.000 leídos a 0,1 y 300 de salida a 5. Eso da 4.800
unidades: 4.800 / 1.000.000 x 10 USD = 0,048 USD, que son 4.800 cien milésimas.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.db.models.model_profile import ModelProfile
from nexus_api.services.agent_model import TokenProfile, _estimate

TOKENS = TokenProfile(
    conversation={
        "llm.input_tokens": Decimal(10_000),
        "llm.cache_read": Decimal(8_000),
        "llm.output_tokens": Decimal(300),
    },
    classify={},
    basis="agent_7d",
)
#: 0,048 USD en cien milésimas.
BASE = 4_800


def _profile(model_id: str) -> ModelProfile:
    return ModelProfile(
        model_id=model_id,
        quota_weight_input=Decimal("1"),
        quota_weight_cache_read=Decimal("0.1"),
        quota_weight_cache_write=Decimal("1.25"),
        quota_weight_output=Decimal("5"),
    )


@pytest.mark.parametrize(
    ("model_id", "amount"),
    [
        ("openai/gpt-5.6-sol", BASE),
        ("openai/gpt-5.6-terra", BASE),
        ("openai/gpt-5.6-luna", BASE),
        ("anthropic/claude-opus-5-5", 9_120),  # 4.800 x 1,9
        ("anthropic/claude-sonnet-5-5", 8_640),  # 4.800 x 1,8
        ("anthropic/claude-haiku-5-5", 12_480),  # 4.800 x 2,6
    ],
)
def test_each_model_is_estimated_with_its_spend_factor(model_id: str, amount: int) -> None:
    estimate = _estimate(model_id, TOKENS, {model_id: _profile(model_id)})
    assert estimate is not None
    assert estimate["amount_micros"] == amount
