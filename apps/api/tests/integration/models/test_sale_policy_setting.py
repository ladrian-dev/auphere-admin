"""Spec 059 (requisitos 3.6, 3.7 y 3.10; T021) — el multiplicador objetivo es un
ajuste de la plataforma (``platform_settings.sale_multiplier``, migración 0231).

Se lee con caché, se invalida con el cambio de catálogo y, si no se puede leer, es
``None``: nunca un número inventado.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker
from nexus_api.metering import sale_policy

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest_asyncio.fixture(autouse=True)
async def _restore() -> AsyncIterator[None]:
    sale_policy.invalidate()
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO platform_settings (key, value, updated_by) "
                "VALUES ('sale_multiplier', '2.2'::jsonb, 'test') "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            )
        )
    sale_policy.invalidate()


async def test_the_seed_is_two_point_two() -> None:
    assert await sale_policy.target_multiplier() == Decimal("2.2")


async def test_a_change_is_seen_after_invalidating() -> None:
    async with get_sessionmaker()() as session, session.begin():
        assert await sale_policy.target_multiplier() == Decimal("2.2")  # calienta la caché
        await sale_policy.store_target(session, Decimal("2.5"), actor="operator:x")
    assert await sale_policy.target_multiplier() == Decimal("2.2"), "la caché manda"
    sale_policy.invalidate()
    assert await sale_policy.target_multiplier() == Decimal("2.5")


async def test_a_missing_setting_is_none_not_a_guess() -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text("DELETE FROM platform_settings WHERE key = 'sale_multiplier'")
        )
    assert await sale_policy.target_multiplier() is None


async def test_storing_under_the_floor_is_refused() -> None:
    async with get_sessionmaker()() as session, session.begin():
        with pytest.raises(sale_policy.SalePolicyError):
            await sale_policy.store_target(session, Decimal("1.2"), actor="operator:x")
