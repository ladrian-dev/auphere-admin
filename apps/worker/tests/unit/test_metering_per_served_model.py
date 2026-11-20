"""Spec 065, T040 (requisitos 5.1 y 5.2): se cobra por el modelo que respondió cada llamada.

Un turno que empieza en Terra y lo termina la reserva de la otra familia (Claude Sonnet 5.5)
tiene dos llamadas de dos modelos: cada una se cobra con los pesos de **su** modelo, leídos
del catálogo de la base como en producción. Opus 5.5 y Sonnet 5.5 tienen todos sus pesos: ni
uno ni otro deja ``metering.unweighted_model`` (una llamada medida y sin cobrar).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from structlog.testing import capture_logs

from nexus_worker.metering.consumer import _turn_quota
from nexus_worker.metering.pricing import lane_weights_from, load_catalog

TERRA = "openai/gpt-5.6-terra"
OPUS = "anthropic/claude-opus-5-5"
SONNET = "anthropic/claude-sonnet-5-5"


def _rows(turn: str, model: str, prompt: int, out: int, seq: int) -> list[dict[str, Any]]:
    return [
        {
            "model": model,
            "meter": meter,
            "quantity": qty,
            "idempotency_key": f"{turn}:{seq}:{meter}",
        }
        for meter, qty in (
            ("llm.input_tokens", prompt),
            ("llm.cache_read", 0),
            ("llm.output_tokens", out),
        )
    ]


def _by_hand(prompt: int, out: int, lanes: dict[str, Any]) -> int:
    total = Decimal(prompt) * Decimal(lanes["input"]) + Decimal(out) * Decimal(lanes["output"])
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def test_the_reserve_call_is_billed_with_its_own_weights() -> None:
    # Una sola lectura del catálogo: el motor de la base queda atado al bucle de la prueba.
    weights = lane_weights_from(await load_catalog())
    for model in (OPUS, SONNET):
        assert model in weights, model
        assert all(v is not None for v in weights[model].values()), (model, weights[model])

    rows = _rows("t1", TERRA, 5000, 300, seq=1) + _rows("t1", SONNET, 6000, 200, seq=2)
    with capture_logs() as logs:
        got = _turn_quota(rows, weights)["t1"]
    assert not [e for e in logs if str(e["event"]).startswith("metering.unweighted_model")]
    expected = _by_hand(5000, 300, weights[TERRA]) + _by_hand(6000, 200, weights[SONNET])
    assert got == expected
    assert got != _by_hand(11000, 500, weights[TERRA]), "no se cobra todo como Terra"
