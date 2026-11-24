"""Spec 076, requisito 1.1 — el origen de anuncio pasa del webhook al stream.

Meta manda en el primer mensaje desde un anuncio un objeto ``referral``. El
adaptador lo copia entero; aquí se filtra antes de que salga del proceso: solo
las claves de la lista blanca, cada una con su tope, y un ``source_type`` que no
sea ``ad`` o ``post`` descarta el anuncio entero (contracts §1). Lo que sobrevive
viaja como JSON en la clave ``referral_json`` del stream.
"""

from __future__ import annotations

import json

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request

from nexus_api.services.ad_referrals import (
    REFERRAL_LIMITS,
    clean_referral,
    parse_referral_field,
    referral_stream_field,
)

FULL = {
    "source_url": "https://fb.me/ad",
    "source_id": "120200000000000",
    "source_type": "ad",
    "headline": "Corte + barba",
    "body": "20% esta semana",
    "media_type": "image",
    "image_url": "https://scontent.example/img.jpg",
    "video_url": "https://scontent.example/v.mp4",
    "thumbnail_url": "https://scontent.example/t.jpg",
    "ctwa_clid": "ARAkLkA8rmlFeiCktEJ",
    "ref": "promo-nov",
    "welcome_message": {"text": "hola"},
}


def test_only_whitelisted_keys_survive() -> None:
    out = clean_referral(FULL)
    assert out is not None
    assert set(out) == {
        "source_url",
        "source_id",
        "source_type",
        "headline",
        "body",
        "media_type",
        "ctwa_clid",
        "ref",
    }
    assert out["ctwa_clid"] == "ARAkLkA8rmlFeiCktEJ"


@pytest.mark.parametrize(("key", "limit"), sorted(REFERRAL_LIMITS.items()))
def test_each_key_is_capped(key: str, limit: int) -> None:
    if key == "source_type":
        return
    out = clean_referral({"source_type": "post", key: "x" * (limit + 50)})
    assert out is not None
    assert len(out[key]) == limit


def test_limits_match_the_contract() -> None:
    assert REFERRAL_LIMITS == {
        "source_type": 8,
        "source_id": 64,
        "source_url": 512,
        "headline": 200,
        "body": 500,
        "media_type": 16,
        "ctwa_clid": 256,
        "ref": 128,
    }


@pytest.mark.parametrize("source_type", ["story", "", None, 3, "AD"])
def test_unknown_source_type_drops_everything(source_type: object) -> None:
    assert clean_referral({**FULL, "source_type": source_type}) is None


@pytest.mark.parametrize("raw", [None, {}, {"source_type": "ad"}, "not-a-dict", ["ad"]])
def test_nothing_useful_means_no_field(raw: object) -> None:
    # Solo el tipo no dice nada: sin anuncio, enlace, titular ni clic no hay origen.
    assert referral_stream_field(raw) is None


def test_non_string_values_are_dropped() -> None:
    out = clean_referral({"source_type": "ad", "source_id": 12345, "headline": {"x": 1}})
    assert out == {"source_type": "ad", "source_id": "12345"}


def test_stream_field_round_trip() -> None:
    field = referral_stream_field(FULL)
    assert field is not None
    assert parse_referral_field(field) == clean_referral(FULL)


@pytest.mark.parametrize("value", [None, "", "{not json", '"a string"', "[1,2]"])
def test_parse_rejects_garbage(value: str | None) -> None:
    assert parse_referral_field(value) is None


def test_parse_re_cleans_what_it_reads() -> None:
    # El worker no se fía de lo que viene en el stream: vuelve a filtrar.
    raw = json.dumps({"source_type": "ad", "ctwa_clid": "c" * 900, "evil": "x"})
    out = parse_referral_field(raw)
    assert out == {"source_type": "ad", "ctwa_clid": "c" * 256}


# ── El webhook escribe la clave ──────────────────────────────────────────────

META_APP_SECRET = "dev-meta-app-secret-change-me"


async def _seed_meta_channel(db_session, tenant_id, business_phone: str) -> None:
    from sqlalchemy import text

    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=business_phone,
                status=ChannelStatus.ACTIVE,
                config={"waba_id": "WABA1", "phone_number_id": "PN1"},
            )
        )


def _envelope(business_phone: str, sender: str, message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN1",
                            },
                            "contacts": [{"profile": {"name": "Ana"}, "wa_id": sender}],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


async def _entries(fake_redis) -> list[dict[str, str]]:
    out = []
    for _id, fields in await fake_redis.xrange("nexus:inbound:standard", count=50):
        out.append(
            {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in fields.items()
            }
        )
    return out


@pytest.mark.asyncio
async def test_webhook_puts_referral_on_the_stream(client, db_session, fake_redis, seed_tenants):
    tenant_id = seed_tenants["a"]
    await _seed_meta_channel(db_session, tenant_id, "+56999997701")
    message = {
        "from": "56911110001",
        "id": "wamid.ad-1",
        "timestamp": "1716300000",
        "type": "text",
        "text": {"body": "Vi su anuncio"},
        "referral": FULL,
    }
    body = json.dumps(_envelope("+56999997701", "56911110001", message)).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )
    assert r.status_code == 200, r.text
    (mine,) = [e for e in await _entries(fake_redis) if e["provider_message_id"] == "wamid.ad-1"]
    assert json.loads(mine["referral_json"]) == clean_referral(FULL)


@pytest.mark.asyncio
async def test_webhook_without_referral_writes_no_field(
    client, db_session, fake_redis, seed_tenants
):
    tenant_id = seed_tenants["a"]
    await _seed_meta_channel(db_session, tenant_id, "+56999997702")
    message = {
        "from": "56911110002",
        "id": "wamid.plain-1",
        "timestamp": "1716300000",
        "type": "text",
        "text": {"body": "hola"},
    }
    body = json.dumps(_envelope("+56999997702", "56911110002", message)).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )
    assert r.status_code == 200, r.text
    (mine,) = [e for e in await _entries(fake_redis) if e["provider_message_id"] == "wamid.plain-1"]
    assert "referral_json" not in mine
