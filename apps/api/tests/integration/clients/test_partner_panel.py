"""Spec 047, T163 — el Panel del partner con la consola nueva (requisitos 48.1 a
48.4).

Los bloques dicen su periodo; para el mismo periodo cuadran con Consumo; «Necesita
tu atención» es la regla única, de más a menos grave, con el arreglo que toca a
quien mira; y nada sale de los cuerpos de mensaje.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.services.wallet.turns import charge_turn
from tests.integration.wallet._wallet_world import UNIT, money, money_world

from ._client_world import add_agent

pytestmark = [pytest.mark.integration]


async def test_the_panel_blocks_say_their_period_and_match_consumo(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=("builder",))
    await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(10 * UNIT, "USD")},
        headers=world.headers(),
    )
    await charge_turn(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=3 * UNIT,
        usage_ref="channel:panel-1",
    )
    home = await client.get("/console/home", headers=world.headers())
    assert home.status_code == 200, home.text
    panel = home.json()["panel"]
    assert panel is not None
    assert panel["spend"]["period"] == "month"
    assert panel["clients"]["period"] == "now"
    assert panel["conversations_per_day"]["period"] == "7d"
    assert len(panel["conversations_per_day"]["days"]) == 7

    summary = (await client.get("/console/usage/summary", headers=world.headers())).json()
    assert panel["spend"]["total"] == summary["month_spend"], "la misma cifra que Consumo"
    assert panel["balance"]["available"] == summary["available"]
    assert panel["balance"]["in_bags"] == summary["in_bags"]
    (top,) = [s for s in panel["spend"]["shares"] if s["kind"] == "client"]
    assert top["external_client_ref"] == world.us.ref
    assert top["amount"] == money(3 * UNIT, "USD")
    assert "content" not in home.text and "body" not in home.text


async def test_attention_is_the_single_rule_with_the_fix_for_who_looks(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=("builder",))
    await add_agent(db_session, world.us.tenant_id, "Recepción")
    await db_session.commit()
    owner = (await client.get("/console/home", headers=world.headers())).json()["panel"]
    rows = owner["attention"]
    assert owner["all_serving"] is False
    by_ref: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_ref.setdefault(row["external_client_ref"], []).append(row)
    # España: sin saldo y sin agentes; EE. UU.: sin saldo, con un agente.
    assert [r["code"] for r in by_ref[world.es.ref]] == ["no_balance", "no_agents"]
    assert by_ref[world.es.ref][0]["action"] == "assign_balance"
    assert by_ref[world.es.ref][1]["action"] == "new_agent"
    assert rows[0]["code"] == "no_balance", "de más a menos grave"
    assert all(r["href"].startswith(f"/clients/{r['external_client_ref']}") for r in rows)

    builder = (await client.get("/console/home", headers=world.as_role("builder"))).json()["panel"]
    no_balance = [r for r in builder["attention"] if r["code"] == "no_balance"]
    assert {r["action"] for r in no_balance} == {"request_balance"}, "quien no asigna, pide"


async def test_the_panel_is_only_for_the_new_console(
    client: Any, db_session: Any, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    home = await client.get("/console/home", headers=a["headers"]())
    assert home.status_code == 200
    assert home.json()["panel"] is None
