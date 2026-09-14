"""Spec 007 · el margen, en euros y por plan.

**Por qué los precios están escritos aquí y no leídos del catálogo.** Éste es un
test de la FÓRMULA, y una fórmula se comprueba contra cifras de referencia
fijadas en la spec. El que vigila el catálogo real es
``tests/integration/test_quota_floor.py``, y ése no lleva ninguna lista: si
alguien añade un modelo, el que tiene que enterarse es aquél.

Las cifras salen de las migraciones 0072, 0076, 0114 (tarifas), 0116 (planes y
bolsas) y de ``billing/pricing.py`` (precio de venta).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from nexus_api.metering.pricing_policy import LaneWeights
from nexus_api.metering.quota import quota_tokens

SELL_USD_PER_MILLION = Decimal(10)
TARGET = Decimal("2.2")
FLOOR = Decimal("1.50")

#: modelo -> (entrada, lectura de caché, salida) en USD por millón.
PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "openai/gpt-5.6-sol": (Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
    "anthropic/claude-sonnet-4-6": (Decimal("3.00"), Decimal("0.30"), Decimal("15.00")),
    "openai/gpt-4o": (Decimal("2.50"), Decimal("1.25"), Decimal("10.00")),
    "openai/gpt-5.6-terra": (Decimal("2.00"), Decimal("0.20"), Decimal("12.00")),
    "anthropic/claude-haiku-4-5": (Decimal("1.00"), Decimal("0.10"), Decimal("5.00")),
    "openai/gpt-5.6-luna": (Decimal("0.20"), Decimal("0.02"), Decimal("1.20")),
}

#: code -> (precio mensual en USD, bolsa semanal). Migración 0116.
TIERS = {
    "Pro": (Decimal(20), Decimal(500_000)),
    "Team": (Decimal(60), Decimal(2_000_000)),
    "Business": (Decimal(150), Decimal(6_000_000)),
}

#: Semanas por mes. La 0115 usa 7/30,44 para convertir en la otra dirección.
WEEKS_PER_MONTH = Decimal("30.44") / 7

#: El turno de teammate: pesado en salida, que es el carril que se regalaba.
TEAMMATE_TURN = (5000, 4000, 3000)


def lanes_of(model: str) -> LaneWeights:
    pin, pc, pout = PRICES[model]
    q = lambda x: (TARGET * x / SELL_USD_PER_MILLION).quantize(  # noqa: E731
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return LaneWeights(input=q(pin), cache_read=q(pc), output=q(pout))


def provider_cost(model: str, prompt: int, cache: int, out: int) -> Decimal:
    pin, pc, pout = PRICES[model]
    return ((prompt - cache) * pin + cache * pc + out * pout) / Decimal(1_000_000)


def test_no_lane_of_any_model_is_sold_below_the_floor() -> None:
    """R2.1 — por carril y por modelo, **nunca en promedio**."""
    for model, (pin, pc, pout) in PRICES.items():
        lanes = lanes_of(model)
        for name, weight, price in (
            ("entrada", lanes.input, pin),
            ("caché", lanes.cache_read, pc),
            ("salida", lanes.output, pout),
        ):
            multiplier = weight * SELL_USD_PER_MILLION / price
            assert multiplier >= FLOOR, f"{model} carril {name}: {multiplier:.3f}x"


def test_every_paid_tier_keeps_a_positive_margin_when_the_pool_is_drained() -> None:
    """R4.1 — con la bolsa agotada todas las semanas del mes.

    Antes de esta spec: Pro 11 %, Team **-18 %**, Business **-42 %**.
    """
    model = "anthropic/claude-sonnet-4-6"
    lanes = lanes_of(model)
    prompt, cache, out = TEAMMATE_TURN
    per_turn_quota = quota_tokens(
        prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes
    )
    per_turn_cost = provider_cost(model, prompt, cache, out)

    expected = {"Pro": 51, "Team": 34, "Business": 21}
    for tier, (price, pool) in TIERS.items():
        turns = (pool / per_turn_quota) * WEEKS_PER_MONTH
        margin = (price - turns * per_turn_cost) / price * 100
        assert margin > 0, f"{tier} sigue siendo deficitario: {margin:.0f}%"
        assert round(margin) == expected[tier], f"{tier}: {margin:.1f}% != {expected[tier]}%"


def test_the_margin_is_the_same_whatever_the_mix() -> None:
    """La propiedad entera: el margen **no depende de la mezcla**.

    Es lo que la 004 creía tener y sólo tenía en su punto de calibración.
    """
    model = "anthropic/claude-sonnet-4-6"
    lanes = lanes_of(model)
    for prompt, cache, out in (
        (30000, 24000, 1500),
        (5000, 4000, 3000),
        (1000, 0, 0),
        (0, 0, 1000),
    ):
        qty = quota_tokens(prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes)
        charged = Decimal(qty) * SELL_USD_PER_MILLION / Decimal(1_000_000)
        cost = provider_cost(model, prompt, cache, out)
        multiplier = charged / cost
        assert abs(multiplier - TARGET) < Decimal("0.01"), (
            f"mezcla {prompt}/{cache}/{out}: {multiplier:.4f}x"
        )
