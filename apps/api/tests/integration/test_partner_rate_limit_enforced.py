"""El límite de partner EXISTE en las tres superficies (WP-30).

Antes de la Fase 3, ``partners.rate_limit_mint_per_min`` era una columna
que el panel dejaba configurar, la API devolvía y **nadie leía**:
``mint_bucket_key`` solo aparecía en un test que comprobaba cómo se
escribe la clave. Una clave de partner podía crear tenants sin freno con
un tope de 60/min a la vista en la ficha. Eso es peor que fail-open: un
límite que se enseña y no está.

Estos tests son de CABLEADO. La aritmética del cubo ya la fija
``test_rate_limit.py``; lo que aquí importa es que la reja está delante
de la puerta, y que sigue estándolo cuando alguien añada un endpoint
nuevo — porque el límite se aplica en ``require_partner_key``, no en cada
handler.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.core import rate_limit
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import Partner, PartnerApiKey

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clean_fallback():
    rate_limit.reset_fallback_for_tests()
    yield
    rate_limit.reset_fallback_for_tests()


async def _partner_with_key(
    db_session: Any,
    *,
    mint_per_min: int = 60,
    embed_per_min: int = 600,
) -> str:
    partner_id = uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Partner(
            id=partner_id,
            name="Rate Limited Partner",
            slug=f"rl-{partner_id.hex[:6]}",
            rate_limit_mint_per_min=mint_per_min,
            rate_limit_embed_per_min=embed_per_min,
        )
    )
    db_session.add(
        PartnerApiKey(
            partner_id=partner_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=["provision", "broadcasts"],
        )
    )
    await db_session.commit()
    return generated.plaintext


def _provision_body(ref: str) -> dict[str, Any]:
    return {"external_client_ref": ref, "name": f"Cliente {ref}", "timezone": "America/Caracas"}


async def test_provisioning_is_rate_limited(client, db_session, fake_redis) -> None:
    """La superficie que crea tenants. Sin esto, una integración con un
    bucle mal escrito abre clientes hasta que alguien lo mira."""
    key = await _partner_with_key(db_session, mint_per_min=2)
    headers = {"Authorization": f"Bearer {key}"}

    codes = [
        (
            await client.post(
                "/v1/partners/clients", headers=headers, json=_provision_body(f"c{i}")
            )
        ).status_code
        for i in range(4)
    ]

    assert codes[:2] != [429, 429], "las dos primeras no deberían estar limitadas"
    assert codes[-1] == 429, f"la cuarta llamada debería ser 429, fue {codes}"


async def test_the_configured_mint_limit_is_the_one_applied(client, db_session, fake_redis) -> None:
    """Control del control: si el límite se hubiera cableado a la columna
    equivocada (``rate_limit_embed_per_min``, 600 por defecto), el test
    de arriba pasaría igual con un tope diez veces mayor y nadie lo
    notaría."""
    key = await _partner_with_key(db_session, mint_per_min=1, embed_per_min=10_000)
    headers = {"Authorization": f"Bearer {key}"}

    first = await client.post(
        "/v1/partners/clients", headers=headers, json=_provision_body("solo-uno")
    )
    second = await client.post(
        "/v1/partners/clients", headers=headers, json=_provision_body("y-basta")
    )

    assert first.status_code != 429
    assert second.status_code == 429


async def test_the_mint_and_broadcast_buckets_do_not_share_tokens(
    client, db_session, fake_redis
) -> None:
    """Un partner que agota su cuota de aprovisionamiento tiene que poder
    seguir operando: son capacidades distintas con topes distintos, y
    compartir cubo convertiría un pico de altas en una caída de servicio
    de su mensajería."""
    key = await _partner_with_key(db_session, mint_per_min=1, embed_per_min=600)
    headers = {"Authorization": f"Bearer {key}"}

    await client.post("/v1/partners/clients", headers=headers, json=_provision_body("uno"))
    assert (
        await client.post("/v1/partners/clients", headers=headers, json=_provision_body("dos"))
    ).status_code == 429

    # El cubo de difusión sigue intacto: 404 (cliente desconocido) es un
    # rechazo del handler, no del limitador — que es exactamente lo que
    # se quiere comprobar.
    resp = await client.get(
        "/v1/partners/clients/no-existe/templates",
        headers=headers,
    )
    assert resp.status_code != 429


async def test_an_unauthenticated_request_is_401_not_429(client, fake_redis) -> None:
    """El cubo es por partner, así que el límite solo puede aplicarse
    después de saber quién llama. Una credencial mala tiene que seguir
    dando 401 — si diera 429, un atacante sabría que la clave es válida."""
    resp = await client.post(
        "/v1/partners/clients",
        headers={"Authorization": "Bearer ak_live_basura"},
        json=_provision_body("x"),
    )
    assert resp.status_code == 401


async def test_a_redis_outage_still_limits_provisioning(client, db_session, monkeypatch) -> None:
    """El caso que motivó WP-30, extremo a extremo: con Redis caído la
    superficie sigue teniendo techo en vez de quedarse abierta."""
    key = await _partner_with_key(db_session, mint_per_min=6)
    headers = {"Authorization": f"Bearer {key}"}

    async def _boom(*args, **kwargs):
        raise ConnectionError("redis down")

    # Se rompe el reloj de Redis, que es la primera llamada del camino
    # feliz del limitador — no el cliente entero, que otras partes del
    # handler también usan.
    monkeypatch.setattr("fakeredis.aioredis.FakeRedis.time", _boom)

    codes = [
        (
            await client.post(
                "/v1/partners/clients", headers=headers, json=_provision_body(f"down{i}")
            )
        ).status_code
        for i in range(4)
    ]
    # 6/min entre 6 réplicas = 1 por réplica: la primera pasa, el resto no.
    assert codes[0] != 429
    assert codes[1:] == [429, 429, 429]
