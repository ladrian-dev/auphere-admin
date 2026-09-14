"""Spec 007 · la misma llamada, la misma cifra, en los dos sitios que debitan.

``billable_qty_for_meter`` (API) y ``_turn_quota`` (worker) tocan la misma
fórmula. El encargo lo dijo con estas palabras: *no arregles uno solo*. Este
fichero es lo que hace que arreglar uno solo se vea.
"""

from __future__ import annotations

from decimal import Decimal

from nexus_api.metering.pricing_policy import LaneWeights
from nexus_api.metering.quota import quota_tokens

from nexus_worker.metering.consumer import _turn_quota

SONNET = LaneWeights(input=Decimal("0.66"), cache_read=Decimal("0.066"), output=Decimal("3.3"))
WEIGHTS = {
    "anthropic/claude-sonnet-4-6": {
        "input": Decimal("0.66"),
        "cache_read": Decimal("0.066"),
        "output": Decimal("3.3"),
    }
}


def _rows(turn: str, model: str, prompt: int, cache: int, out: int, seq: int = 1) -> list[dict]:
    """Filas nativas de UNA llamada, como las emite el colector.

    ``_llm_call_key`` agrupa por ``idempotency_key`` sin el sufijo del medidor, y
    el turno es lo que queda al quitar el último segmento: de
    ``t1:1:llm.output_tokens`` sale la llamada ``t1:1`` y el turno ``t1``.
    """
    return [
        {
            "model": model,
            "meter": meter,
            "quantity": qty,
            "idempotency_key": f"{turn}:{seq}:{meter}",
        }
        for meter, qty in (
            ("llm.input_tokens", prompt),
            ("llm.cache_read", cache),
            ("llm.output_tokens", out),
        )
    ]


def test_worker_and_api_agree_on_the_same_call() -> None:
    """R3.1, R3.2 — si una mitad cambia sin la otra, esto se pone rojo."""
    rows = _rows("t1", "anthropic/claude-sonnet-4-6", 5000, 4000, 3000)
    from_worker = _turn_quota(rows, WEIGHTS)["t1"]
    from_api = quota_tokens(prompt_tokens=5000, cache_read=4000, output_tokens=3000, weights=SONNET)
    assert from_worker == from_api == 10824


def test_a_model_with_no_lane_weights_is_measured_and_not_debited() -> None:
    """El turno ya ocurrió: negarse a asentarlo no impediría nada y sólo dejaría
    de cobrarlo en silencio. Se registra con su motivo y se omite del débito —
    el mismo criterio que la 004 fijó para el peso único."""
    rows = _rows("t2", "openai/unknown-model", 1000, 0, 500)
    assert _turn_quota(rows, WEIGHTS) == {}


def test_each_call_of_a_turn_is_weighted_with_its_own_model() -> None:
    """El peso es del MODELO de la llamada. Una tarea que encadena cerebros
    distintos no se puede ponderar turno a turno: cobraría mal la mitad."""
    weights = dict(WEIGHTS)
    weights["anthropic/claude-haiku-4-5"] = {
        "input": Decimal("0.22"),
        "cache_read": Decimal("0.022"),
        "output": Decimal("1.1"),
    }
    rows = _rows("t3", "anthropic/claude-sonnet-4-6", 1000, 0, 1000, seq=1)
    rows += _rows("t3", "anthropic/claude-haiku-4-5", 1000, 0, 1000, seq=2)
    total = _turn_quota(rows, weights)["t3"]
    assert total == (660 + 3300) + (220 + 1100)
