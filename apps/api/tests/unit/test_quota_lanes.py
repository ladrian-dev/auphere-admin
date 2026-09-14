"""Spec 007 · la fórmula de cuota, carril a carril.

El contrato es ``contracts/quota-unit-v2.md`` y sustituye al de la 004. Lo que
cambia no es un número: es que **el factor deja de ser uno**.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.metering.pricing_policy import LaneWeights
from nexus_api.metering.quota import billable_qty_for_meter, quota_tokens

# claude-sonnet-4-6 a 2,2x: 3,00 / 0,30 / 15,00 USD por millón.
SONNET = LaneWeights(input=Decimal("0.66"), cache_read=Decimal("0.066"), output=Decimal("3.3"))


def test_each_lane_is_charged_with_its_own_weight() -> None:
    """R1.3 — un factor por carril, no un factor al total."""
    qty = quota_tokens(prompt_tokens=5000, cache_read=4000, output_tokens=3000, weights=SONNET)
    # uncached 1000 x 0,66 + cache 4000 x 0,066 + salida 3000 x 3,3
    assert qty == 660 + 264 + 9900 == 10824


def test_the_flat_cache_discount_is_gone() -> None:
    """R1.4 — la caché se cobra con SU peso, no con el 0,1 global de la 004.

    Si alguien reintrodujera el descuento plano antes del peso, la caché
    valdría 0,1 x 0,66 = 0,066 por token **por casualidad** en sonnet — y 0,055
    en gpt-4o, donde el proveedor la cobra a la mitad y no a la décima parte.
    Este caso usa gpt-4o justamente porque ahí los dos caminos divergen.
    """
    gpt4o = LaneWeights(input=Decimal("0.55"), cache_read=Decimal("0.275"), output=Decimal("2.2"))
    qty = quota_tokens(prompt_tokens=1000, cache_read=1000, output_tokens=0, weights=gpt4o)
    assert qty == 275, "la caché de gpt-4o vale la mitad de su entrada, no una décima"


def test_cache_write_never_costs_quota() -> None:
    """R1.5 — se acepta para no olvidarlo, y vale cero. No gana un cuarto peso."""
    with_write = quota_tokens(
        prompt_tokens=1000, cache_read=0, output_tokens=0, cache_write=9_999_999, weights=SONNET
    )
    without = quota_tokens(prompt_tokens=1000, cache_read=0, output_tokens=0, weights=SONNET)
    assert with_write == without == 660


def test_uncached_input_never_goes_negative() -> None:
    """Suelo cero si el proveedor parte la cuenta y ``cache_read > prompt``."""
    assert quota_tokens(prompt_tokens=100, cache_read=500, output_tokens=0, weights=SONNET) == 33


def test_there_is_exactly_one_rounding_and_it_is_half_away_from_zero() -> None:
    """R1.3 — se suman los tres productos en Decimal y se cuantiza UNA vez.

    Con la fórmula vieja había dos redondeos encadenados (el aporte de la caché
    y luego el total ponderado). Tres productos homogéneos se pueden sumar antes
    de cuantizar, y eso es menos deriva, no más.

    El caso elegido cae exactamente en ,5: ``round()`` de Python es banker's y
    daría 2; ``ROUND_HALF_UP`` da 3, que es lo que el contrato exige.
    """
    half = LaneWeights(input=Decimal("0.25"), cache_read=Decimal("0"), output=Decimal("0"))
    assert quota_tokens(prompt_tokens=10, cache_read=0, output_tokens=0, weights=half) == 3


def test_weights_have_no_default_on_purpose() -> None:
    """Un defecto convertiría cada olvido en un cobro silencioso a la baja — el
    modo de fallo que esta spec elimina en todos los demás sitios. Que falte
    tiene que ser un ``TypeError`` en la primera ejecución."""
    with pytest.raises(TypeError):
        quota_tokens(prompt_tokens=1, cache_read=0, output_tokens=0)  # type: ignore[call-arg]


def test_the_breakdown_charges_each_native_row_with_its_lane() -> None:
    """R3.3 — el desglose por medidor no colapsa, y cada fila lleva su peso."""
    assert billable_qty_for_meter(
        "llm.input_tokens", 5000, weights=SONNET, prompt_tokens=5000, cache_read=4000
    ) == pytest.approx(660.0)
    assert billable_qty_for_meter("llm.cache_read", 4000, weights=SONNET) == pytest.approx(264.0)
    assert billable_qty_for_meter("llm.output_tokens", 3000, weights=SONNET) == pytest.approx(
        9900.0
    )
    assert billable_qty_for_meter("llm.cache_write", 9999, weights=SONNET) == 0.0


def test_a_meter_outside_the_llm_lanes_passes_through_untouched() -> None:
    """``media.image`` y compañía no llevan peso: se miden por unidades."""
    assert billable_qty_for_meter("media.image", 3, weights=SONNET) == 3.0
    assert billable_qty_for_meter("voice.minutes", 2.5, weights=SONNET) == 2.5
