"""Spec 059 (requisitos 3.12 y 4.4; T025) — el coste no avisa a nadie.

Lo que paga el partner sale de los pesos de venta, no del coste. Un precio de coste
nuevo solo mueve el margen de Auphere: no crea ``model.price_change`` ni al guardarlo
ni en la pasada del cron. Y no entra con una fecha pasada: el medidor no revalora
lo que ya pasó, así que esa fecha engañaría.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime import model_resolver

from nexus_api.core import respond_catalog
from nexus_api.db.base import get_sessionmaker
from nexus_api.services import model_lifecycle
from nexus_api.services.router_catalog import Price

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

KEY = "c59-c/priced"
ACTOR = "operator:luis@auphere.com"


@pytest_asyncio.fixture
async def priced() -> AsyncIterator[None]:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_profiles (provider, model_id, display_name, route, status, "
                "capabilities, supports_tools, price_input_per_mtok, price_output_per_mtok, "
                "quota_weight_input, quota_weight_cache_read, quota_weight_output) VALUES "
                "('c59', :k, :k, :k, 'active', CAST(:c AS jsonb), true, 1, 5, 0.22, 0.022, 1.1)"
            ),
            {"k": KEY, "c": json.dumps({"tools": True})},
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, output, source_url) "
                "SELECT id, DATE '2026-10-28', 1, 5, 'https://example.invalid' "
                "FROM model_profiles WHERE model_id = :k"
            ),
            {"k": KEY},
        )
    model_resolver.invalidate_catalog()
    try:
        yield
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c59-%'"))
        model_resolver.invalidate_catalog()
        respond_catalog.reset()


async def _notices() -> int:
    async with get_sessionmaker()() as session:
        return int(
            await session.scalar(
                sa.text(
                    "SELECT count(*) FROM console_notifications WHERE kind = 'model.price_change'"
                )
            )
            or 0
        )


def _price(valid_from: date, input_: str) -> Price:
    return Price(
        valid_from=valid_from,
        input=Decimal(input_),
        cache_read=None,
        cache_write=None,
        output=Decimal(input_) * 5,
        audio_minute=None,
        image=None,
        surcharge=None,
        source_url="https://example.invalid/pricing",
        currency="USD",
        unit="per_million_tokens",
    )


async def test_a_big_cost_rise_notifies_no_partner(priced) -> None:
    before = await _notices()
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    result = await model_lifecycle.add_price(KEY, _price(tomorrow, "9"), actor=ACTOR)
    assert result is None, "add_price ya no devuelve avisos"
    assert await _notices() == before
    report = await model_lifecycle.run_lifecycle()
    assert not hasattr(report, "price_notices")
    assert await _notices() == before


async def test_a_cost_dated_in_the_past_is_refused(priced) -> None:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    with pytest.raises(model_lifecycle.LifecycleError) as caught:
        await model_lifecycle.add_price(KEY, _price(yesterday, "2"), actor=ACTOR)
    assert caught.value.code == "in_the_past"


async def test_a_cost_dated_today_is_accepted(priced) -> None:
    today = datetime.now(UTC).date()
    await model_lifecycle.add_price(KEY, _price(today, "2"), actor=ACTOR)
    async with get_sessionmaker()() as session:
        count = await session.scalar(
            sa.text(
                "SELECT count(*) FROM model_prices p JOIN model_profiles m ON m.id = p.deployment_id "
                "WHERE m.model_id = :k AND p.valid_from = :d"
            ),
            {"k": KEY, "d": today},
        )
    assert count == 1
