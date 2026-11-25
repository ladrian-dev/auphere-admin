"""Spec 071, T002 — la lista «Lo que te necesita» (requisitos 1.1, 1.3, 1.4 y 4.4;
``contracts/api.md``).

``GET /console/attention`` da la lista del partner de peor a mejor, con lo suyo (el tope
de construcción, la cuenta, el cobro) y lo de cada cliente; cada fila con su alcance, su
gravedad, su arreglo y lo justo para el texto. El Panel (``/console/home`` → ``panel``)
devuelve **la misma lista**, de la misma función. Cada fila respeta los permisos y los
módulos de quien mira.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Partner
from tests.integration.clients._client_world import add_agent

from ._attention_world import (
    UNIT,
    MoneyWorld,
    assign,
    billing_state,
    build_spent,
    money,
    money_world,
    set_purchased,
)

pytestmark = [pytest.mark.integration]


async def _needy(client: Any, db_session: Any) -> MoneyWorld:
    """España sin saldo y sin agentes; EE. UU. con saldo y un agente cuyo único número
    tiene un problema; la partida al 84 %; la cuenta con 2 de lo cargado en el mes (12);
    el último cobro, fallido."""
    world = await money_world(db_session)
    await assign(client, world, world.us.ref, 10 * UNIT)
    await add_agent(db_session, world.us.tenant_id, "Recepción", channel="degraded")
    await db_session.commit()
    assert await build_spent(db_session, world, 42 * UNIT) == ["build.budget.warning"]
    await set_purchased(db_session, world, 2 * UNIT)
    await billing_state(db_session, world.partner_id, "payment_failed")
    return world


def _rows(items: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    return [(i["code"], i["external_client_ref"]) for i in items]


async def test_the_list_is_the_partners_and_its_clients_worst_first(
    client: Any, db_session: Any
) -> None:
    world = await _needy(client, db_session)
    resp = await client.get("/console/attention", headers=world.headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["errors"] == []
    assert _rows(body["items"]) == [
        ("billing_payment_failed", None),
        ("no_balance", world.es.ref),
        ("channel_problem", world.us.ref),
        ("build_cap_warning", None),
        ("account_low", None),
        ("agent_without_channel", world.us.ref),
        ("no_agents", world.es.ref),
    ]
    by_code = {i["code"]: i for i in body["items"]}

    billing = by_code["billing_payment_failed"]
    assert billing == {
        "scope": "partner",
        "severity": "critical",
        "code": "billing_payment_failed",
        "external_client_ref": None,
        "client_name": None,
        "count": 1,
        "action": "fix_billing",
        "href": "/billing",
        "data": {},
    }
    build = by_code["build_cap_warning"]
    assert (build["scope"], build["severity"], build["action"]) == (
        "partner",
        "warning",
        "request_build_extension",
    )
    assert build["data"] == {
        "pct": 84,
        "spent": money(42 * UNIT, "USD"),
        "cap": money(50 * UNIT, "USD"),
    }
    account = by_code["account_low"]
    assert (account["action"], account["href"]) == ("buy_balance", "/billing")
    assert account["data"] == {"available": money(2 * UNIT, "USD"), "days_left": None}

    no_balance = by_code["no_balance"]
    assert (no_balance["scope"], no_balance["severity"], no_balance["client_name"]) == (
        "client",
        "critical",
        "Cliente ES",
    )
    assert (no_balance["action"], no_balance["href"]) == (
        "assign_balance",
        f"/clients/{world.es.ref}?assign=1",
    )
    assert no_balance["data"] == {}, "sin bolsa todavía no hay cifra que dar"
    assert by_code["channel_problem"]["severity"] == "critical"
    assert by_code["no_agents"]["severity"] == "warning"


async def test_the_panel_lists_the_very_same(client: Any, db_session: Any) -> None:
    world = await _needy(client, db_session)
    listed = (await client.get("/console/attention", headers=world.headers())).json()
    panel = (await client.get("/console/home", headers=world.headers())).json()["panel"]
    assert panel["attention"] == listed["items"]
    assert panel["all_serving"] is False


async def test_nothing_needs_you_is_an_empty_list_without_errors(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=())
    for ref in (world.es.ref, world.us.ref):
        await assign(client, world, ref, 10 * UNIT)
    await add_agent(db_session, world.es.tenant_id, "Recepción")
    await add_agent(db_session, world.us.tenant_id, "Recepción")
    await db_session.commit()
    listed = (await client.get("/console/attention", headers=world.headers())).json()
    assert listed == {"items": [], "errors": []}
    panel = (await client.get("/console/home", headers=world.headers())).json()["panel"]
    assert panel["attention"] == [] and panel["all_serving"] is True


async def test_each_row_respects_who_looks(client: Any, db_session: Any) -> None:
    world = await _needy(client, db_session)

    builder = (await client.get("/console/attention", headers=world.as_role("builder"))).json()
    codes = {i["code"] for i in builder["items"]}
    assert "billing_payment_failed" not in codes, "sin billing:read"
    assert {"build_cap_warning", "account_low", "no_balance"} <= codes
    no_balance = next(i for i in builder["items"] if i["code"] == "no_balance")
    assert no_balance["action"] == "request_balance", "quien no asigna, pide"

    billing = (await client.get("/console/attention", headers=world.as_role("billing"))).json()
    assert {i["scope"] for i in billing["items"]} == {"partner"}, "sin clients:read"
    assert {i["code"] for i in billing["items"]} == {
        "billing_payment_failed",
        "build_cap_warning",
        "account_low",
    }


async def test_a_row_whose_fix_the_partner_does_not_have_is_not_listed(
    client: Any, db_session: Any
) -> None:
    world = await _needy(client, db_session)
    async with db_session.begin():
        await db_session.execute(
            sa.update(Partner)
            .where(Partner.id == world.partner_id)
            .values(console_modules=["panel", "clients"])
        )
    codes = [
        i["code"]
        for i in (await client.get("/console/attention", headers=world.headers())).json()["items"]
    ]
    assert not {"billing_payment_failed", "build_cap_warning", "account_low"} & set(codes)
    assert "no_balance" in codes

    async with db_session.begin():
        await db_session.execute(
            sa.update(Partner)
            .where(Partner.id == world.partner_id)
            .values(console_modules=["panel", "usage", "billing"])
        )
    items = (await client.get("/console/attention", headers=world.headers())).json()["items"]
    assert {i["scope"] for i in items} == {"partner"}, "sin el módulo de clientes"


async def test_a_low_bag_says_its_days_and_what_is_left(client: Any, db_session: Any) -> None:
    from nexus_api.services.wallet.turns import charge_turn

    world = await money_world(db_session, roles=())
    await assign(client, world, world.us.ref, 10 * UNIT)
    await add_agent(db_session, world.us.tenant_id, "Recepción")
    await db_session.commit()
    await charge_turn(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=9 * UNIT,
        usage_ref="channel:attention-low",
    )
    items = (await client.get("/console/attention", headers=world.headers())).json()["items"]
    low = next(i for i in items if i["code"] == "low_balance")
    assert low["external_client_ref"] == world.us.ref
    assert low["data"] == {"available": money(UNIT, "USD"), "days_left": None}


async def test_the_old_console_has_no_build_line(client: Any, console_world: Any) -> None:
    a = console_world["a"]
    resp = await client.get("/console/attention", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    assert not [i for i in resp.json()["items"] if i["code"].startswith("build_cap")]
