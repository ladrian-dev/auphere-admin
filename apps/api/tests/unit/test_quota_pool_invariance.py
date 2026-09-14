"""Spec 007 · agotar la bolsa cuesta lo mismo con cualquier cerebro — y ahora
también con cualquier mezcla.

La 004 compró esta propiedad y la documentó como garantía. La medición del
2026-09-14 mostró que sólo se cumplía **en su punto de calibración**:

    mezcla                          desviación entre modelos
    referencia (30 K / 24 K / 1,5 K)          0,03 %
    teammate   (5 K / 4 K / 3 K)             78,38 %
    salida pura(0 / 0 / 1 K)                106,88 %

Y el trabajo de teammate —el que la bolsa incluida paga— es justo el segundo.
Con un peso por carril la propiedad pasa de coincidencia calibrada a invariante.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.metering.quota import quota_tokens
from tests.unit.test_quota_margin import PRICES, lanes_of, provider_cost

MIXES = {
    "referencia": (30000, 24000, 1500),
    "teammate": (5000, 4000, 3000),
    "salida pura": (0, 0, 1000),
    "entrada pura": (10000, 0, 0),
}


def cost_per_million_quota(model: str, prompt: int, cache: int, out: int) -> Decimal:
    qty = quota_tokens(
        prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes_of(model)
    )
    assert qty > 0, "una mezcla sin cuota no mide nada: el test pasaría por vacío"
    return provider_cost(model, prompt, cache, out) / Decimal(qty) * Decimal(1_000_000)


@pytest.mark.parametrize("mix", list(MIXES))
def test_draining_a_pool_costs_the_same_whatever_the_brain(mix: str) -> None:
    """R4.1, R4.2 — menos del 2 % de desviación, en TODA mezcla."""
    prompt, cache, out = MIXES[mix]
    costs = [cost_per_million_quota(m, prompt, cache, out) for m in PRICES]
    spread = (max(costs) / min(costs) - 1) * 100
    assert spread < 2, f"mezcla {mix}: {spread:.2f} % de desviación entre modelos"


def test_the_output_heavy_mix_is_the_one_that_used_to_break() -> None:
    """El caso que motivó la spec, fijado como test para que no vuelva.

    Con el peso único de la 0115 esta mezcla desviaba un 78 %; el partner
    elegía el peor caso del plan al elegir modelo, que es exactamente lo que la
    004 quiso impedir.
    """
    costs = [cost_per_million_quota(m, 5000, 4000, 3000) for m in PRICES]
    spread = (max(costs) / min(costs) - 1) * 100
    assert spread < Decimal("0.5"), f"{spread:.2f} %"
