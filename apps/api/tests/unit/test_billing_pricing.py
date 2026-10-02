"""Spec 005 · la tarifa del crédito comprado.

**10 $ por millón de unidades de cuota**, de `concept.md` §La tarifa: coste
3,52 $ al fondo contra 10 $ de venta, 65 % de margen objetivo. Mismo precio
que el pool incluido — Lovable cobra la recarga un 20 % más cara y Cursor la
cobra igual; se eligió igual porque **la membresía no es un descuento por
volumen**, es acceso a la aplicación.

La conversión importa más de lo que parece: se hace en enteros y se redondea
**hacia abajo**. Redondear hacia arriba regalaría unidades en cada compra, y
a escala eso es margen que se va sin que nadie lo decida.
"""

from __future__ import annotations

import pytest

from nexus_api.billing.pricing import CREDIT_USD_PER_MILLION, units_for_cents

pytestmark = [pytest.mark.asyncio]


async def test_the_rate_is_the_one_the_assessment_decided() -> None:
    assert CREDIT_USD_PER_MILLION == 10


async def test_ten_dollars_buys_a_million_units() -> None:
    assert units_for_cents(1_000) == 1_000_000


async def test_fifty_dollars_buys_five_million() -> None:
    assert units_for_cents(5_000) == 5_000_000


async def test_the_conversion_rounds_down() -> None:
    """Nunca hacia arriba: regalar unidades en cada compra es margen que se va."""
    assert units_for_cents(1) == 1_000
    assert units_for_cents(7) == 7_000
    # Un importe que no cae en un múltiplo exacto no inventa unidades.
    assert units_for_cents(333) == 333_000


async def test_zero_and_negative_buy_nothing() -> None:
    assert units_for_cents(0) == 0
    assert units_for_cents(-500) == 0


async def test_the_result_is_always_a_whole_number_of_units() -> None:
    """El libro es de enteros: una unidad fraccionaria no se puede debitar."""
    for cents in (1, 99, 1_000, 4_999, 123_456):
        value = units_for_cents(cents)
        assert isinstance(value, int)
        assert value >= 0


# ── Spec 027: el partner ve dinero, el libro sigue en créditos ──────────────


async def test_money_to_credits_is_exact_for_any_amount_with_two_decimals() -> None:
    from nexus_api.billing.pricing import CREDITS_PER_CENT, cents_to_credits

    assert CREDITS_PER_CENT == 1_000
    assert cents_to_credits(2_550) == 2_550_000  # 25,50 US$
    assert cents_to_credits(1) == 1_000
    assert cents_to_credits(0) == 0


async def test_negative_money_is_refused_not_floored() -> None:
    """Un tope negativo es un error del que escribe, no un cero silencioso."""
    from nexus_api.billing.pricing import cents_to_credits

    with pytest.raises(ValueError):
        cents_to_credits(-1)


async def test_a_balance_never_shows_money_that_is_not_there() -> None:
    """Saldos y restantes se redondean hacia abajo: 999 créditos no son un céntimo."""
    from nexus_api.billing.pricing import credits_to_cents

    assert credits_to_cents(1_234_567) == 1_234
    assert credits_to_cents(999) == 0
    assert credits_to_cents(1_000) == 1


async def test_spend_rounds_to_the_nearest_cent() -> None:
    from nexus_api.billing.pricing import credits_to_cents

    assert credits_to_cents(1_500, nearest=True) == 2
    assert credits_to_cents(1_499, nearest=True) == 1


async def test_whatever_the_partner_writes_comes_back_the_same() -> None:
    """CE-002: asignar un importe y volver a leerlo da el mismo importe."""
    from nexus_api.billing.pricing import cents_to_credits, credits_to_cents

    for cents in (0, 1, 99, 2_550, 4_000, 123_456, 50_000_000):
        assert credits_to_cents(cents_to_credits(cents)) == cents


async def test_the_purchase_uses_the_same_conversion() -> None:
    from nexus_api.billing.pricing import cents_to_credits

    for cents in (500, 5_000, 123_456):
        assert units_for_cents(cents) == cents_to_credits(cents)
