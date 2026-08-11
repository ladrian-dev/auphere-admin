"""Cubo de fichas por partner (ADR-028) y su degradación (WP-30).

Lo que cambia en la Fase 3 es la rama de excepción. Antes, una caída de
Redis dejaba a todos los partners sin límite y se anotaba en un log —
fail-open documentado, aceptable con un partner conocido y no con la API
abierta, donde el limitador es lo único entre una integración con un
bucle mal escrito y la factura de LLM de Auphere.

Ahora, sin Redis, el cubo se lleva en memoria y por réplica. No es el
límite configurado y no pretende serlo: la cuota se divide entre el
máximo de réplicas del autoescalado, así que en el peor caso el techo
global se parece al configurado y en el normal es más estricto. Lo que
se prueba aquí es que la dirección del error es la correcta —frenar de
más— y que la degradación se anuncia aunque no rechace nada.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from nexus_api.core import rate_limit


class BrokenRedis:
    """Redis que falla en la primera llamada del camino feliz."""

    async def time(self):
        raise ConnectionError("redis down")


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def _clean_fallback():
    rate_limit.reset_fallback_for_tests()
    yield
    rate_limit.reset_fallback_for_tests()


async def test_allows_up_to_capacity_then_rejects(redis) -> None:
    results = [await rate_limit.allow(redis, key="rl:t1", per_minute=3) for _ in range(4)]
    assert results == [True, True, True, False]


async def test_buckets_are_independent(redis) -> None:
    assert await rate_limit.allow(redis, key="rl:a", per_minute=1)
    assert not await rate_limit.allow(redis, key="rl:a", per_minute=1)
    # Partner B's bucket is untouched by A's exhaustion.
    assert await rate_limit.allow(redis, key="rl:b", per_minute=1)


async def test_zero_limit_rejects_without_redis(redis) -> None:
    assert not await rate_limit.allow(redis, key="rl:z", per_minute=0)


# ── degradación (WP-30) ───────────────────────────────────────────────


async def test_a_redis_outage_no_longer_lets_everything_through() -> None:
    """El cambio de la Fase 3, en una línea. Antes esto era ``all(True)``
    hasta el infinito."""
    # 60/min repartido entre 6 réplicas = 10 por réplica.
    results = [
        await rate_limit.allow(BrokenRedis(), key="rl:down", per_minute=60) for _ in range(15)
    ]
    assert results[:10] == [True] * 10
    assert results[10:] == [False] * 5


async def test_the_degraded_limit_is_stricter_than_the_configured_one() -> None:
    """Es lo que hace que la degradación sea segura: con menos réplicas
    de las máximas —el caso normal— el techo global queda POR DEBAJO del
    configurado. Al revés, una caída de Redis multiplicaría el límite por
    el número de réplicas."""
    allowed = 0
    for _ in range(120):
        if await rate_limit.allow(BrokenRedis(), key="rl:strict", per_minute=60):
            allowed += 1
    assert allowed < 60


async def test_a_tiny_limit_does_not_round_down_to_zero() -> None:
    """Con ``per_minute=3`` y 6 réplicas, la división daría 0 y una caída
    de Redis cerraría la superficie entera. Frenar de más, no cortar."""
    assert await rate_limit.allow(BrokenRedis(), key="rl:tiny", per_minute=3)


async def test_the_degradation_is_announced_even_when_nothing_is_rejected(
    monkeypatch,
) -> None:
    """La métrica que tiene que alarmar. Mientras Redis esté caído, el
    número que se aplica ya no es el configurado — y eso hay que saberlo
    aunque ningún partner llegue a tocar el techo."""
    seen: list[str] = []
    monkeypatch.setattr(
        rate_limit,
        "record_rate_limit_degraded",
        lambda *, surface: seen.append(surface),
    )
    assert await rate_limit.allow(BrokenRedis(), key="rl:quiet", per_minute=600, surface="mint")
    assert seen == ["mint"]


async def test_a_healthy_redis_never_touches_the_in_memory_bucket(redis) -> None:
    """Control negativo del control: si el camino feliz consumiera del
    cubo local, los tests de degradación pasarían por el motivo
    equivocado y el límite real sería la mitad del configurado."""
    for _ in range(3):
        await rate_limit.allow(redis, key="rl:healthy", per_minute=10)
    assert rate_limit._fallback == {}


async def test_the_fallback_bucket_refills(monkeypatch) -> None:
    """Sin recarga, una caída de Redis de diez minutos dejaría al partner
    bloqueado hasta que alguien reiniciase el proceso."""
    clock = {"t": 1_000.0}
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock["t"])

    for _ in range(10):
        assert await rate_limit.allow(BrokenRedis(), key="rl:refill", per_minute=60)
    assert not await rate_limit.allow(BrokenRedis(), key="rl:refill", per_minute=60)

    clock["t"] += 60.0
    assert await rate_limit.allow(BrokenRedis(), key="rl:refill", per_minute=60)


def test_bucket_key_shapes() -> None:
    assert rate_limit.mint_bucket_key("p1") == "rl:partner:p1:mint"
    assert rate_limit.embed_bucket_key("p1") == "rl:partner:p1:embed"
    assert rate_limit.broadcast_bucket_key("p1") == "rl:partner:p1:broadcast"
