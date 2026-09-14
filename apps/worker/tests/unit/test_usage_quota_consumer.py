"""El consumidor desglosa en NATIVO y no deja ``billable_qty`` = bruto.

**Qué cambió con la spec 007.** ``rows_from_entry`` es síncrona y no puede pedir
el catálogo; con un peso único global se podía ponderar aquí mismo, con un peso
por carril y por modelo ya no. Así que el trabajo se parte en dos: **este paso
mide** (uncached para input, nativo para caché y salida, cero para cache_write)
y ``_apply_lane_weights`` pondera después, en ``persist_rows``, donde el
catálogo ya está leído para valorar en dólares.

Por eso los casos de abajo afirman **nativos** y no cuotas. El caso que afirma
que las dos mitades coinciden con lo que debita el Companion vive en
``test_turn_quota_lanes.py``, que es donde puede inyectar pesos.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

from nexus_api.metering.pricing_policy import LaneWeights
from nexus_api.metering.quota import quota_tokens

from nexus_worker.metering import consumer


def _entry(*, events: list[dict], source: str = "channel") -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "turn_id": "t1",
        "source": source,
        "events": json.dumps(events),
    }


def _event(
    meter: str, quantity: int, *, seq: int = 1, at: str = "2026-08-22T10:00:00+00:00"
) -> dict:
    return {
        "meter": meter,
        "quantity": quantity,
        "idempotency_key": f"t1:{seq}:{meter}",
        "occurred_at": at,
        "provider": "anthropic",
        "model": "anthropic/claude-sonnet-4-6",
    }


def test_input_billable_is_uncached_and_the_cache_row_stays_native() -> None:
    """El 0,1 plano desapareció: la caché se pondera después, con SU peso."""
    _, rows = consumer.rows_from_entry(
        _entry(
            events=[
                _event("llm.input_tokens", 10_000),
                _event("llm.output_tokens", 100),
                _event("llm.cache_read", 9_000),
                _event("llm.cache_write", 400),
            ]
        )
    )
    by_meter = {r["meter"]: r for r in rows}
    assert by_meter["llm.input_tokens"]["quantity"] == 10_000
    assert by_meter["llm.input_tokens"]["billable_qty"] == 1_000.0
    assert by_meter["llm.cache_read"]["quantity"] == 9_000
    assert by_meter["llm.cache_read"]["billable_qty"] == 9_000.0
    assert by_meter["llm.output_tokens"]["billable_qty"] == 100.0
    assert by_meter["llm.cache_write"]["billable_qty"] == 0.0


def test_summing_input_billable_plus_cache_native_is_not_quota() -> None:
    _, rows = consumer.rows_from_entry(
        _entry(
            events=[
                _event("llm.input_tokens", 10_000),
                _event("llm.output_tokens", 100),
                _event("llm.cache_read", 9_000),
            ]
        )
    )
    by_meter = {r["meter"]: r for r in rows}
    wrong = by_meter["llm.input_tokens"]["billable_qty"] + by_meter["llm.cache_read"]["quantity"]
    # Pesos neutros: lo que este test compara es la unidad, no la ponderación.
    # El argumento es obligatorio a propósito — sin él, olvidarlo en producción
    # sería un cobro silencioso a la baja.
    neutral = LaneWeights(input=Decimal(1), cache_read=Decimal(1), output=Decimal(1))
    right = quota_tokens(prompt_tokens=10_000, cache_read=9_000, output_tokens=100, weights=neutral)
    assert wrong != right


def test_companion_quota_matches_channel_billable_for_the_same_call() -> None:
    """Con pesos neutros, el desglose nativo suma lo mismo que la cuota.

    Es la comprobación de que las dos mitades hablan de lo mismo antes de
    ponderar. La versión con pesos reales —y por tanto la que vigila que
    arreglar un lado sin el otro se vea— está en ``test_turn_quota_lanes.py``.
    """
    prompt, cache, output, write = 10_000, 9_000, 100, 400
    neutral = LaneWeights(input=Decimal(1), cache_read=Decimal(1), output=Decimal(1))
    companion = quota_tokens(
        prompt_tokens=prompt,
        cache_read=cache,
        output_tokens=output,
        cache_write=write,
        weights=neutral,
    )
    _, rows = consumer.rows_from_entry(
        _entry(
            source="companion",
            events=[
                _event("llm.input_tokens", prompt),
                _event("llm.output_tokens", output),
                _event("llm.cache_read", cache),
                _event("llm.cache_write", write),
            ],
        )
    )
    channel = sum(r["billable_qty"] for r in rows)
    assert companion == int(channel)
    # Debitar companion.runs Y usage_records de la misma llamada es 2x.
    assert companion + int(channel) == 2 * companion


def test_two_calls_in_one_turn_do_not_share_cache() -> None:
    _, rows = consumer.rows_from_entry(
        _entry(
            events=[
                _event("llm.input_tokens", 700, seq=1),
                _event("llm.output_tokens", 20, seq=1),
                _event("llm.input_tokens", 5_000, seq=2),
                _event("llm.output_tokens", 300, seq=2),
                _event("llm.cache_read", 4_200, seq=2),
            ]
        )
    )
    inputs = [r for r in rows if r["meter"] == "llm.input_tokens"]
    assert sorted(r["billable_qty"] for r in inputs) == [700.0, 800.0]


def test_non_llm_meters_keep_quantity_as_billable() -> None:
    _, rows = consumer.rows_from_entry(
        _entry(
            events=[
                {
                    "meter": "channel.message",
                    "quantity": 1.0,
                    "idempotency_key": "wamid:channel",
                    "occurred_at": "2026-08-22T10:00:00+00:00",
                    "provider": "meta",
                }
            ]
        )
    )
    assert rows[0]["billable_qty"] == 1.0
