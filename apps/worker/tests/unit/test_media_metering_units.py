"""CP-23 (0083): un adjunto es una unidad medible Y valorada.

Emisión (``record_media_unit``): un adjunto → ``media.<kind>`` con clave de
idempotencia estable por ``provider_message_id``; audio con duración →
además ``media.audio_seconds``; sin id de proveedor o con un tipo fuera del
vocabulario, nada. Valoración (``price_row`` + ``meter_prices``): las filas
``media.*`` salen con ``cost_usd`` calculado por unidad, sin modelo, y un
medidor sin tarifa cargada sigue saliendo NULL. Aceptación del plan: una
conversación con imagen + audio + documento genera ≥ 3 filas ``media.*``
valoradas.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

from nexus_worker.metering import collector
from nexus_worker.metering.pricing import price_row

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    async def xadd(self, stream, fields, **kwargs):
        self.entries.append((stream, dict(fields)))
        return b"1-1"


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr("nexus_api.core.redis_client.get_redis", lambda: redis)
    return redis


def _events_of(redis: _FakeRedis) -> list[dict]:
    out: list[dict] = []
    for _stream, fields in redis.entries:
        out.extend(json.loads(fields["events"]))
    return out


UNIT_PRICES = {
    "media.image": Decimal("0.002"),
    "media.audio": Decimal("0.002"),
    "media.audio_seconds": Decimal("0"),
    "media.document": Decimal("0.003"),
}


async def test_image_audio_document_emit_three_priced_media_rows(fake_redis) -> None:
    tenant_id = uuid.uuid4()
    for kind, wamid, seconds in (
        ("image", "wamid.IMG", None),
        ("audio", "wamid.AUD", 42.0),
        ("document", "wamid.DOC", None),
    ):
        await collector.record_media_unit(
            tenant_id=tenant_id,
            kind=kind,
            provider="meta",
            provider_message_id=wamid,
            audio_seconds=seconds,
        )
    events = _events_of(fake_redis)
    keys = {e["idempotency_key"]: e for e in events}
    assert {
        "wamid.IMG:media.image",
        "wamid.AUD:media.audio",
        "wamid.AUD:media.audio_seconds",
        "wamid.DOC:media.document",
    } == set(keys)
    assert keys["wamid.AUD:media.audio_seconds"]["quantity"] == 42.0
    assert all(e["quantity"] == 1.0 for k, e in keys.items() if not k.endswith("seconds"))
    # Todas las entradas son tráfico de canal (facturable).
    assert {f["source"] for _s, f in fake_redis.entries} == {"channel"}

    # Valoración: por unidad, sin modelo, y ≥ 3 filas media.* con precio.
    priced = [
        price_row({"meter": e["meter"], "quantity": e["quantity"], "model": None}, {}, UNIT_PRICES)
        for e in events
        if e["meter"] in {"media.image", "media.audio", "media.document"}
    ]
    assert len(priced) == 3
    assert priced == [Decimal("0.00200000"), Decimal("0.00200000"), Decimal("0.00300000")]
    # Los segundos valen 0 (coste ya en voice.minutes), NO NULL: es un precio real.
    assert price_row(
        {"meter": "media.audio_seconds", "quantity": 42.0, "model": None}, {}, UNIT_PRICES
    ) == Decimal("0")


async def test_media_without_provider_id_or_unknown_kind_is_not_measured(fake_redis) -> None:
    await collector.record_media_unit(
        tenant_id=uuid.uuid4(), kind="image", provider="meta", provider_message_id=None
    )
    await collector.record_media_unit(
        tenant_id=uuid.uuid4(), kind="gif", provider="meta", provider_message_id="wamid.X"
    )
    assert fake_redis.entries == []


async def test_audio_without_duration_emits_only_the_unit(fake_redis) -> None:
    await collector.record_media_unit(
        tenant_id=uuid.uuid4(), kind="audio", provider="meta", provider_message_id="wamid.A"
    )
    assert [e["meter"] for e in _events_of(fake_redis)] == ["media.audio"]


def test_unpriced_media_meter_stays_null() -> None:
    """Un medidor sin tarifa cargada entra con NULL, no con 0."""
    assert (
        price_row({"meter": "media.video", "quantity": 1, "model": None}, {}, UNIT_PRICES) is None
    )
    # Sin catálogo de unidades tampoco se inventa nada.
    assert price_row({"meter": "media.image", "quantity": 1, "model": None}, {}, None) is None
