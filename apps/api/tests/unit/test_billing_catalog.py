"""Spec 005 · el catálogo, y el múltiplo que se publica en vez de la cifra.

El múltiplo **se calcula**. Si fuera una columna habría que acordarse de
actualizarla al cambiar un pool, y el día que se olvide la pantalla de planes
mentiría sobre lo que se está vendiendo. Derivado, no se puede desfasar
(research D9).
"""

from __future__ import annotations

import pytest

from nexus_api.billing.catalog import consumption_multiple

pytestmark = [pytest.mark.asyncio]


async def test_the_base_paid_tier_is_one() -> None:
    assert consumption_multiple(pool=500_000, base_pool=500_000) == 1


async def test_a_bigger_tier_is_its_multiple() -> None:
    assert consumption_multiple(pool=2_000_000, base_pool=500_000) == 4
    assert consumption_multiple(pool=6_000_000, base_pool=500_000) == 12


async def test_the_free_tier_has_no_multiple() -> None:
    """«0,2x el de Pro» no le dice nada a nadie. Mejor no decir nada."""
    assert consumption_multiple(pool=100_000, base_pool=500_000) is None


async def test_it_survives_a_capacity_adjustment() -> None:
    """La propiedad entera de D9: se ajusta el pool y el múltiplo se ajusta solo.

    Si Auphere dobla la capacidad de todos los niveles, lo que el partner ve
    **no cambia** — que es justo lo que R7.3 de la Spec A pide.
    """
    before = [
        consumption_multiple(pool=p, base_pool=500_000) for p in (500_000, 2_000_000, 6_000_000)
    ]
    after = [
        consumption_multiple(pool=p, base_pool=1_000_000)
        for p in (1_000_000, 4_000_000, 12_000_000)
    ]
    assert before == after == [1, 4, 12]


async def test_a_non_integer_ratio_does_not_invent_precision() -> None:
    """Si las proporciones dejan de ser enteras hay que decidir qué se enseña.

    Redondear en silencio diría «4x» de algo que es 3,7x, y eso es una promesa
    comercial falsa. Se devuelve ``None``: mejor no decir nada que mentir.
    """
    assert consumption_multiple(pool=1_850_000, base_pool=500_000) is None


async def test_a_base_of_zero_does_not_explode() -> None:
    assert consumption_multiple(pool=500_000, base_pool=0) is None
