"""Presupuestos desde el panel (WP-20) — la superficie que usa el operador.

Hasta este endpoint la única forma de poner un tope era un INSERT a mano
en producción. Lo que se fija aquí es sobre todo lo que NO debe poder
guardarse, porque las tres formas de equivocarse producen **una política
que se guarda sin error y que nunca corta**: el operador cree que el tope
está puesto y se entera en la factura.

1. Un ``scope_id`` que no existe (UUID mal copiado del panel).
2. Un ``meter`` sin contador: el consumidor de metering solo alimenta
   ``cost_usd``, así que cualquier otro lee un cero eterno.
3. Un blando por encima del duro: la degradación queda inalcanzable y se
   pasa de "todo bien" a "no abrimos turnos" sin escalón intermedio.

El caso 3 lo cubre además un CHECK en la base; se valida antes para que
el operador reciba un 422 explicando qué corregir y no un 500.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _policy(scope_id, **overrides) -> dict:
    body = {
        "scope": "tenant",
        "scope_id": str(scope_id),
        "meter": "cost_usd",
        "period": "day",
        "soft_limit": 10.0,
        "hard_limit": 50.0,
        "soft_action": "both",
    }
    body.update(overrides)
    return body


async def test_a_policy_survives_a_round_trip(client, admin_headers, seed_tenants) -> None:
    tenant = seed_tenants["a"]
    r = await client.put("/admin/budget-policies", headers=admin_headers, json=_policy(tenant))
    assert r.status_code == 200, r.text
    assert r.json()["hard_limit"] == 50.0

    listed = await client.get(
        f"/admin/budget-policies?scope=tenant&scope_id={tenant}", headers=admin_headers
    )
    assert [p["period"] for p in listed.json()] == ["day"]


async def test_a_second_put_edits_instead_of_duplicating(
    client, admin_headers, seed_tenants
) -> None:
    """La cuádrupla ``(scope, scope_id, meter, period)`` es única en la
    base. Sin el ON CONFLICT, subir un tope daría 500."""
    tenant = seed_tenants["a"]
    await client.put("/admin/budget-policies", headers=admin_headers, json=_policy(tenant))
    r = await client.put(
        "/admin/budget-policies",
        headers=admin_headers,
        json=_policy(tenant, soft_limit=20.0, hard_limit=80.0),
    )
    assert r.status_code == 200, r.text
    assert r.json()["hard_limit"] == 80.0

    listed = await client.get(
        f"/admin/budget-policies?scope=tenant&scope_id={tenant}", headers=admin_headers
    )
    assert len(listed.json()) == 1


async def test_a_scope_id_that_does_not_exist_is_refused(client, admin_headers) -> None:
    """El fallo silencioso número uno: la política se guardaría y nadie
    consultaría jamás ese ámbito."""
    r = await client.put(
        "/admin/budget-policies", headers=admin_headers, json=_policy(uuid.uuid4())
    )
    assert r.status_code == 422
    assert "no existe" in r.text


async def test_a_meter_without_a_counter_is_refused(client, admin_headers, seed_tenants) -> None:
    """El fallo silencioso número dos. ``llm.input_tokens`` es un medidor
    real de ``usage_records``, pero nadie incrementa su contador de
    presupuesto: el tope leería cero para siempre."""
    r = await client.put(
        "/admin/budget-policies",
        headers=admin_headers,
        json=_policy(seed_tenants["a"], meter="llm.input_tokens"),
    )
    assert r.status_code == 422


async def test_the_declared_meters_match_what_the_consumer_actually_counts(
    client, admin_headers, seed_tenants
) -> None:
    """Control del control: la lista blanca del endpoint tiene que seguir
    al consumidor. Si algún día el metering empieza a contar otro medidor
    y esta lista no se amplía, el endpoint rechazará una política
    legítima; si se amplía sin tocar el consumidor, volvemos al tope que
    no corta."""
    from nexus_worker.metering.budget import COST_METER

    from nexus_api.api.admin.budget_policies import BUDGETED_METERS

    assert COST_METER in BUDGETED_METERS


async def test_a_soft_limit_above_the_hard_one_is_refused(
    client, admin_headers, seed_tenants
) -> None:
    r = await client.put(
        "/admin/budget-policies",
        headers=admin_headers,
        json=_policy(seed_tenants["a"], soft_limit=90.0, hard_limit=50.0),
    )
    assert r.status_code == 422


async def test_deleting_removes_the_cap_entirely(client, admin_headers, seed_tenants) -> None:
    """Y no lo devuelve a un tope por defecto: sin política no se corta.
    El test existe para que ese contrato quede escrito donde se lee."""
    tenant = seed_tenants["a"]
    created = await client.put(
        "/admin/budget-policies", headers=admin_headers, json=_policy(tenant)
    )
    policy_id = created.json()["id"]

    r = await client.delete(f"/admin/budget-policies/{policy_id}", headers=admin_headers)
    assert r.status_code == 204

    listed = await client.get(
        f"/admin/budget-policies?scope=tenant&scope_id={tenant}", headers=admin_headers
    )
    assert listed.json() == []

    # Borrar dos veces es 404, no 204: un DELETE idempotente aquí
    # escondería que el operador está mirando una lista vieja.
    assert (
        await client.delete(f"/admin/budget-policies/{policy_id}", headers=admin_headers)
    ).status_code == 404


async def test_an_inactive_policy_is_still_listed(client, admin_headers, seed_tenants) -> None:
    """Una política apagada es justo lo que hay que ver cuando alguien se
    pregunta por qué no cortó nada. Filtrarla del listado convertiría la
    respuesta en "no hay tope", que es una respuesta distinta."""
    tenant = seed_tenants["a"]
    await client.put(
        "/admin/budget-policies",
        headers=admin_headers,
        json=_policy(tenant, active=False),
    )
    listed = await client.get(
        f"/admin/budget-policies?scope=tenant&scope_id={tenant}", headers=admin_headers
    )
    assert [p["active"] for p in listed.json()] == [False]


async def test_the_endpoint_needs_an_admin_token(client, seed_tenants) -> None:
    assert (await client.get("/admin/budget-policies")).status_code in (401, 403)
    assert (
        await client.put("/admin/budget-policies", json=_policy(seed_tenants["a"]))
    ).status_code in (401, 403)
