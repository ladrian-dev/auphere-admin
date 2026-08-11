"""Selector de modelo por rol (WP-19) — la superficie que usa el operador.

Es el mecanismo que hace que elegir modelo por cliente sea real: sin
estos endpoints la tabla solo se toca por SQL, y una tabla que solo se
edita por SQL en producción acaba divergiendo de lo que cree el equipo.

Lo que se fija aquí es sobre todo lo que NO debe pasar: atar un cliente a
un modelo que no existe, o a un rol inventado. Los dos fallarían de
verdad en el primer turno del cliente, no en el PUT — y un turno que no
resuelve modelo es una conversación sin responder.
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_catalog_exposes_prices(client, admin_headers) -> None:
    r = await client.get("/admin/model-profiles", headers=admin_headers)
    assert r.status_code == 200
    by_id = {p["model_id"]: p for p in r.json()}

    sonnet = by_id["anthropic/claude-sonnet-4-6"]
    assert sonnet["price_input_per_mtok"] == 3.0
    assert sonnet["price_output_per_mtok"] == 15.0
    # El mínimo cacheable viaja al panel: es lo que permite avisar de que
    # el prompt de un cliente queda por debajo y su caché no se activa.
    assert sonnet["cache_min_tokens"] == 1024
    assert by_id["anthropic/claude-haiku-4-5"]["cache_min_tokens"] == 4096


async def test_roles_without_a_binding_are_listed_as_inherited(
    client, admin_headers, seed_tenants
) -> None:
    """Un selector que solo muestra lo configurado deja al operador sin
    saber qué pasa en los demás roles."""
    r = await client.get(
        f"/admin/tenants/{seed_tenants['a']}/model-bindings", headers=admin_headers
    )
    assert r.status_code == 200
    roles = {b["role"]: b for b in r.json()}
    assert "respond" in roles and "classify" in roles
    assert all(b["is_bound"] is False for b in roles.values())


async def test_binding_a_role_survives_a_round_trip(client, admin_headers, seed_tenants) -> None:
    tenant = seed_tenants["a"]
    r = await client.put(
        f"/admin/tenants/{tenant}/model-bindings/respond",
        headers=admin_headers,
        json={
            "model_id": "anthropic/claude-haiku-4-5",
            "fallback_chain": ["anthropic/claude-sonnet-4-6"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["model_id"] == "anthropic/claude-haiku-4-5"

    listed = await client.get(f"/admin/tenants/{tenant}/model-bindings", headers=admin_headers)
    respond = next(b for b in listed.json() if b["role"] == "respond")
    assert respond["is_bound"] is True
    assert respond["fallback_chain"] == ["anthropic/claude-sonnet-4-6"]

    # Segundo PUT: reasignar, no duplicar. El UNIQUE (tenant, role) lo
    # impide en la base, pero el endpoint tiene que responder 200, no 500.
    r2 = await client.put(
        f"/admin/tenants/{tenant}/model-bindings/respond",
        headers=admin_headers,
        json={"model_id": "anthropic/claude-sonnet-4-6"},
    )
    assert r2.status_code == 200
    assert r2.json()["model_id"] == "anthropic/claude-sonnet-4-6"


async def test_unbinding_returns_the_role_to_the_global_config(
    client, admin_headers, seed_tenants
) -> None:
    tenant = seed_tenants["a"]
    await client.put(
        f"/admin/tenants/{tenant}/model-bindings/classify",
        headers=admin_headers,
        json={"model_id": "anthropic/claude-haiku-4-5"},
    )
    r = await client.delete(
        f"/admin/tenants/{tenant}/model-bindings/classify", headers=admin_headers
    )
    assert r.status_code == 204

    listed = await client.get(f"/admin/tenants/{tenant}/model-bindings", headers=admin_headers)
    classify = next(b for b in listed.json() if b["role"] == "classify")
    assert classify["is_bound"] is False


async def test_a_model_outside_the_catalog_is_rejected(client, admin_headers, seed_tenants) -> None:
    """Se rechaza en el PUT y no al resolver: un binding a un modelo
    inexistente no daría error hasta el primer turno del cliente."""
    r = await client.put(
        f"/admin/tenants/{seed_tenants['a']}/model-bindings/respond",
        headers=admin_headers,
        json={"model_id": "anthropic/claude-que-no-existe"},
    )
    assert r.status_code == 422
    assert "catálogo" in r.json()["detail"]


async def test_an_unknown_role_is_rejected(client, admin_headers, seed_tenants) -> None:
    """Un rol con typo crearía una fila que nadie resuelve nunca: el
    cliente seguiría en el modelo global y el panel diría otra cosa."""
    r = await client.put(
        f"/admin/tenants/{seed_tenants['a']}/model-bindings/respomd",
        headers=admin_headers,
        json={"model_id": "anthropic/claude-haiku-4-5"},
    )
    assert r.status_code == 422


async def test_binding_endpoints_require_the_admin_token(client, seed_tenants) -> None:
    r = await client.get(f"/admin/tenants/{seed_tenants['a']}/model-bindings")
    assert r.status_code in (401, 403)
    r = await client.get("/admin/model-profiles")
    assert r.status_code in (401, 403)


async def test_an_unknown_tenant_is_a_404_not_an_empty_list(client, admin_headers) -> None:
    """Devolver la lista de roles heredados para un tenant que no existe
    haría que un id mal escrito pareciera un cliente recién creado sin
    configurar. El 404 sale de ``scoped_session_from_path``, igual que en
    el resto del panel."""
    r = await client.get(f"/admin/tenants/{uuid.uuid4()}/model-bindings", headers=admin_headers)
    assert r.status_code == 404
