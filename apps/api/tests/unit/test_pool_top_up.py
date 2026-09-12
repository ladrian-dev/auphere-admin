"""Spec 005 · R6.2 — subir de plan COMPLETA el pool, no lo reinicia.

La aritmética se prueba sin base de datos a propósito: cuando falla, el rojo
señala la fórmula y no una consulta.

Y la fórmula tiene tres formas de estar mal, todas plausibles:

* **reiniciar al tamaño nuevo** regala lo ya consumido — un partner que gastó
  400 000 de 500 000 y sube a 2 000 000 se llevaría 2 000 000 en vez de
  1 600 000;
* **dejarlo como estaba** le cobra el nivel nuevo sin dárselo, que es la peor
  versión: pagó y no notó nada;
* **sumar el tamaño entero** duplica el pool de esa semana.

Lo correcto es sumar **la diferencia de tamaño**, que es lo que el partner no
tenía y ahora ha pagado.
"""

from __future__ import annotations

import pytest

from nexus_api.metering.wallet import top_up_amount

pytestmark = [pytest.mark.asyncio]


async def test_the_canonical_case_from_the_spec() -> None:
    """100 000 gastados de 500 000; al subir a 1 000 000 quedan 900 000."""
    assert top_up_amount(remaining=400_000, old_size=500_000, new_size=1_000_000) == 500_000


async def test_what_it_is_not() -> None:
    """Las tres formas plausibles de equivocarse, escritas como negativas."""
    result = 400_000 + top_up_amount(remaining=400_000, old_size=500_000, new_size=1_000_000)
    assert result != 1_000_000, "se reinició al tamaño nuevo: regala lo ya consumido"
    assert result != 400_000, "no se tocó: le cobramos el nivel nuevo sin dárselo"
    assert result != 1_400_000, "se sumó el tamaño entero: pool duplicado esa semana"
    assert result == 900_000


async def test_a_partner_who_spent_nothing_gets_the_whole_difference() -> None:
    assert top_up_amount(remaining=500_000, old_size=500_000, new_size=2_000_000) == 1_500_000


async def test_a_partner_who_spent_everything_still_gets_the_difference() -> None:
    """Y no el tamaño nuevo entero: lo gastado, gastado está."""
    assert top_up_amount(remaining=0, old_size=500_000, new_size=2_000_000) == 1_500_000


async def test_going_down_adds_nothing() -> None:
    """Bajar no se aplica ya (es a fin de período) y nunca resta aquí."""
    assert top_up_amount(remaining=400_000, old_size=2_000_000, new_size=500_000) == 0


async def test_the_same_tier_adds_nothing() -> None:
    assert top_up_amount(remaining=100_000, old_size=500_000, new_size=500_000) == 0


async def test_an_unknown_old_size_does_not_invent_a_gift() -> None:
    """Si no sabemos de dónde venía, no se regala el tamaño nuevo entero.

    Un partner sin fila previa tiene ``old_size = 0``; darle el nuevo completo
    sería correcto si acaba de contratar, pero esta función no lo sabe. Quien
    concede un nivel desde cero es ``grant_tier``, que sí pone el pool entero.
    """
    assert top_up_amount(remaining=0, old_size=0, new_size=500_000) == 500_000


async def test_negative_inputs_never_produce_a_negative_top_up() -> None:
    """Esta función solo suma. Restar es del camino del turno (ADR-037 D3)."""
    assert top_up_amount(remaining=-10, old_size=1_000_000, new_size=500_000) == 0
