"""Spec 005 · `POST /console/billing/credit` — abrir la compra, no acreditarla.

Lo que la ruta hace es abrir la página del proveedor. **No acredita nada**:
eso ocurre cuando el pago se confirma, y por eso la puerta que un partner
podía usar para acreditarse solo ya no existe.

Los límites por compra no son ceremonia: un máximo protege de un cero de más
tecleado, y un mínimo evita compras cuya comisión se come el importe.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PATH = "/console/billing/credit"


async def _purchased(pid) -> int:
    async with get_sessionmaker()() as s:
        value = await s.scalar(
            sa.text("SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    return int(value or 0)


async def test_opening_a_purchase_credits_nothing(client, console_world) -> None:
    """R3.2: ni por una intención de pago, ni por una sesión abierta."""
    a = console_world["a"]
    before = await _purchased(a["partner_id"])
    await client.post(_PATH, headers=a["headers"](), json={"amount_cents": 5_000})
    assert await _purchased(a["partner_id"]) == before


async def test_an_amount_below_the_minimum_is_refused(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.post(_PATH, headers=a["headers"](), json={"amount_cents": 1})
    assert resp.status_code == 422, resp.text


async def test_an_absurd_amount_is_refused(client, console_world) -> None:
    """Un cero de más tecleado no puede convertirse en un cargo real."""
    a = console_world["a"]
    resp = await client.post(_PATH, headers=a["headers"](), json={"amount_cents": 99_999_999})
    assert resp.status_code == 422, resp.text


async def test_a_non_integer_amount_is_refused(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.post(_PATH, headers=a["headers"](), json={"amount_cents": "mucho"})
    assert resp.status_code == 422


async def test_without_a_token_there_is_no_purchase(client) -> None:
    resp = await client.post(_PATH, json={"amount_cents": 5_000})
    assert resp.status_code == 401


async def test_the_response_never_carries_a_provider_secret(client, console_world) -> None:
    """La consola no debe recibir nada con lo que hablar con el proveedor."""
    a = console_world["a"]
    resp = await client.post(_PATH, headers=a["headers"](), json={"amount_cents": 5_000})
    body = resp.text
    for needle in ("sk_test", "sk_live", "whsec_"):
        assert needle not in body, f"la respuesta lleva «{needle}»"
