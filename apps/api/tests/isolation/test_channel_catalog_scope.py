"""Aislamiento del catálogo del número (spec 022, puerta §I).

El catálogo cuelga del canal y el canal de su tenant. Lo que hay que dejar
escrito: que un tenant no lista, no enlaza ni averigua el catálogo de otro,
y que la lista de catálogos que recibe sale **solo** del token de su canal.
"""

from __future__ import annotations

import pytest

from nexus_api.api.console import channels as ch_router
from nexus_api.main import app
from tests.unit.test_endpoint_console_catalog import FLORES, _canal, _CatalogSim, _url
from tests.unit.test_endpoint_console_channels import _reload

pytestmark = pytest.mark.asyncio


def _sim(monkeypatch, **kw) -> _CatalogSim:
    sim = _CatalogSim(**kw)
    monkeypatch.setattr(ch_router, "build_meta_client", lambda: sim)
    return sim


async def test_another_tenant_cannot_list_link_or_clear_and_meta_is_never_asked(
    client, console_world, db_session, monkeypatch
) -> None:
    a, b = console_world["a"], console_world["b"]
    sim = _sim(monkeypatch, catalogs=[FLORES], linked=None)
    canal_a = await _canal(db_session, a["tenant_id"])

    r = await client.get(
        _url(a, canal_a, "catalogs").replace(a["ref"], b["ref"]), headers=b["headers"]()
    )
    assert r.status_code == 404
    r = await client.put(
        _url(a, canal_a, "catalog").replace(a["ref"], b["ref"]),
        json={"catalog_id": "CAT_FLORES"},
        headers=b["headers"](),
    )
    assert r.status_code == 404
    r = await client.delete(
        _url(a, canal_a, "catalog").replace(a["ref"], b["ref"]), headers=b["headers"]()
    )
    assert r.status_code == 404
    assert sim.calls == [], "se preguntó a Meta por un canal ajeno"
    fila = await _reload(db_session, canal_a.id)
    assert "catalog_id" not in fila.config


async def test_the_list_comes_from_the_channels_own_token(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES])
    canal_a = await _canal(db_session, a["tenant_id"])
    r = await client.get(_url(a, canal_a, "catalogs"), headers=a["headers"]())
    assert r.status_code == 200, r.text
    (llamada,) = sim.calls
    assert llamada[1]["access_token"] == "EAA-canal"
    assert llamada[1]["business_id"] == "BIZ-1"


async def test_the_new_routes_take_no_tenant_partner_or_token() -> None:
    schema = app.openapi()
    rutas = [
        (path, spec)
        for path, spec in schema["paths"].items()
        if path.startswith("/console/clients/{ref}/channels/{channel_id}/catalog")
    ]
    assert len(rutas) == 2, [p for p, _ in rutas]
    prohibidos = {"tenant_id", "partner_id", "access_token", "bisuat"}
    for path, spec in rutas:
        for method, op in spec.items():
            if method not in {"get", "put", "delete"}:
                continue
            for prm in op.get("parameters", []):
                assert prm["name"] not in prohibidos, f"{method} {path} acepta {prm['name']}"
            body = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            ref = body.get("$ref", "")
            if ref:
                props = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]].get(
                    "properties", {}
                )
                assert not (set(props) & prohibidos), (
                    f"{method} {path} acepta {set(props) & prohibidos}"
                )
