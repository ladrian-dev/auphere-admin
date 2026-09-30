"""Capacidades del catálogo de Meta (spec 022, Historia 3 · R3.1, R3.2).

Con un número que tiene catálogo enlazado, «Buscar en el catálogo» y «Enviar
productos del catálogo» aparecen con nombre de negocio y encendidas en las
plantillas de venta. Sin catálogo, **no aparecen**: no hay botón apagado que
explique lo que no tienes (constitución §V).
"""

from __future__ import annotations

import pytest

from tests.integration.test_console_capabilities import _seed
from tests.unit.test_endpoint_console_channels import _channel

pytestmark = pytest.mark.asyncio

CATALOG_KEYS = {"catalog.search_products", "catalog.get_product"}


async def _items(client, who) -> dict[str, dict]:
    r = await client.get(f"/console/clients/{who['ref']}/capabilities", headers=who["headers"]())
    assert r.status_code == 200, r.text
    return {i["key"]: i for g in r.json()["groups"] for i in g["items"]}


async def test_without_a_catalog_the_capabilities_do_not_exist(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"])
    db_session.add(_channel(a["tenant_id"], waba_id="W-1"))  # número vivo, sin catálogo
    await db_session.commit()
    items = await _items(client, a)
    assert not (CATALOG_KEYS & set(items)), "sin catálogo la capacidad no debe aparecer"


async def test_with_a_catalog_they_appear_with_business_names(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"])
    db_session.add(
        _channel(a["tenant_id"], waba_id="W-1", catalog_id="CAT_FLORES", catalog_name="Flores")
    )
    await db_session.commit()
    items = await _items(client, a)
    assert set(items) >= CATALOG_KEYS
    buscar = items["catalog.search_products"]
    assert buscar["business_name"] == "Buscar en el catálogo"
    assert items["catalog.get_product"]["business_name"] == "Enviar productos del catálogo"
    assert buscar["connector"]["slug"] == "channel_catalog"
    assert buscar["connector"]["status"] == "connected"
    assert buscar["read_only"] is True and buscar["destructive"] is False
    assert buscar["mode"]["effective"] == "always"


async def test_a_disconnected_number_with_a_catalog_does_not_count(
    client, console_world, db_session
) -> None:
    from nexus_api.db.models import ChannelStatus

    a = console_world["a"]
    await _seed(db_session, a["tenant_id"])
    suelto = _channel(a["tenant_id"], waba_id="W-1", catalog_id="CAT_FLORES")
    suelto.status = ChannelStatus.DISCONNECTED
    db_session.add(suelto)
    await db_session.commit()
    items = await _items(client, a)
    assert not (CATALOG_KEYS & set(items))
