"""Spec 005 · lo que `/console/billing/membership` dice, y lo que calla.

Dos contratos en uno, y el segundo es el que se rompe solo:

* **La forma**: nivel, estado, uso y catálogo, todo en una llamada — para que
  la pantalla no tenga que pedir la lista de teammates solo para saber si el
  botón va apagado, y no haya un instante en que muestra un botón que va a
  fallar (§V).
* **Lo que NO sale**: ninguna cifra de pool ni de saldo. El saldo lo da el
  medidor único de la Spec A; publicar el tamaño del pool convertiría cada
  ajuste de capacidad en un recorte o un regalo visible (research D9).
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PATH = "/console/billing/membership"


async def test_the_object_has_its_shape(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get(_PATH, headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["tier"]["code"] in {"free", "pro", "team", "business"}
    assert isinstance(body["tier"]["max_teammates"], int)
    assert isinstance(body["tier"]["max_members"], int)
    assert body["state"] in {"current", "payment_failed", "unpaid", "canceled"}
    assert "usage" in body and {"teammates", "members"} <= set(body["usage"])
    assert isinstance(body["catalog"], list) and body["catalog"]


async def test_the_pool_figure_never_leaves_the_server(client, console_world) -> None:
    """V58. Ni en ``tier`` ni en ``catalog``, ni con otro nombre."""
    a = console_world["a"]
    resp = await client.get(_PATH, headers=a["headers"]())
    blob = json.dumps(resp.json())

    assert "weekly_pool_tokens" not in blob
    # Y las cifras concretas del catálogo, por si alguien las renombra.
    for figure in ("100000", "500000", "2000000", "6000000"):
        assert figure not in blob.replace("_", ""), (
            f"la cifra {figure} salió por la API: el partner ve el tamaño del "
            "pool y cada ajuste de capacidad pasa a ser un recorte visible"
        )


async def test_what_the_partner_sees_instead_is_caps_and_a_multiple(
    client, console_world
) -> None:
    a = console_world["a"]
    resp = await client.get(_PATH, headers=a["headers"]())
    catalog = {entry["code"]: entry for entry in resp.json()["catalog"]}

    assert catalog["free"]["consumption_multiple"] is None, (
        "«0,2x el de Pro» no le dice nada a quien todavía no tiene plan"
    )
    assert catalog["pro"]["consumption_multiple"] == 1
    assert catalog["team"]["consumption_multiple"] == 4
    assert catalog["business"]["consumption_multiple"] == 12
    # Los topes, que son lo estable, sí van tal cual.
    assert catalog["team"]["max_teammates"] == 6
    assert catalog["business"]["max_members"] == 8


async def test_the_multiple_follows_a_capacity_change_on_its_own(
    client, console_world
) -> None:
    """La propiedad entera de D9: se calcula, no se guarda.

    Se dobla la capacidad de todos los niveles y lo que el partner ve **no
    cambia** — que es justo lo que R7.3 de la Spec A pide.
    """
    a = console_world["a"]
    async with get_sessionmaker()() as s:
        await s.execute(sa.text("UPDATE membership_tiers SET weekly_pool_tokens = weekly_pool_tokens * 2"))
        await s.commit()
    try:
        resp = await client.get(_PATH, headers=a["headers"]())
        catalog = {e["code"]: e for e in resp.json()["catalog"]}
        assert catalog["team"]["consumption_multiple"] == 4
        assert catalog["business"]["consumption_multiple"] == 12
    finally:
        async with get_sessionmaker()() as s:
            await s.execute(
                sa.text("UPDATE membership_tiers SET weekly_pool_tokens = weekly_pool_tokens / 2")
            )
            await s.commit()


async def test_usage_comes_with_the_object(client, console_world) -> None:
    """Sin esto, la pantalla pinta un botón que va a fallar."""
    a = console_world["a"]
    resp = await client.get(_PATH, headers=a["headers"]())
    usage = resp.json()["usage"]
    assert usage["members"] >= 1, "el partner tiene al menos a quien está mirando"


async def test_a_partner_only_ever_sees_its_own_membership(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text(
                "UPDATE partner_subscriptions SET tier_code = 'pro' WHERE partner_id = :p"
            ),
            {"p": str(b["partner_id"])},
        )
        await s.commit()

    resp = await client.get(_PATH, headers=a["headers"]())
    assert resp.status_code == 200
    assert resp.json()["tier"]["code"] == "business", (
        "el partner A ve el nivel de B"
    )


async def test_without_a_token_there_is_no_membership(client) -> None:
    resp = await client.get(_PATH)
    assert resp.status_code == 401
