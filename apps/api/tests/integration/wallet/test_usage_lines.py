"""Spec 047, T154 — Consumo por partidas (requisitos 46.1 a 46.8).

Arriba, tres cifras en la moneda de la cuenta (lo asignable sin el pool, lo que hay
en bolsas con «aprox.» si hay otra moneda, y el gasto del mes con su proyección);
la tabla por cliente; la gráfica por día y partida; las cuatro partidas con quién
las paga; la partida «Construcción y pruebas» con su tope en dinero; y el detalle
técnico. Todo sale del libro, con la misma cifra en todas partes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import UsageLedger, UsageRecord
from nexus_api.db.models.daily_cost_snapshot import DailyCostSnapshot
from nexus_api.services.wallet import build_budget, fx
from nexus_api.services.wallet.turns import charge_turn

from ._wallet_world import EUR_USD, UNIT, MoneyWorld, money, money_world

pytestmark = [pytest.mark.integration]


async def _seed(client: Any, db_session: Any) -> MoneyWorld:
    """10 USD en EE. UU. y 10 EUR en España; una conversación en cada uno, una
    del Companion, una construcción y la estimación de Meta del día."""
    world = await money_world(db_session, pool=30 * UNIT, roles=())
    for client_, currency in ((world.us, "USD"), (world.es, "EUR")):
        resp = await client.post(
            f"/console/clients/{client_.ref}/bag/assign",
            json={"amount": money(10 * UNIT, currency)},
            headers=world.headers(),
        )
        assert resp.status_code == 200, resp.text
    for client_ in (world.us, world.es):
        await charge_turn(
            partner_id=world.partner_id,
            tenant_id=client_.tenant_id,
            agent_id=None,
            amount_usd=2 * UNIT,
            usage_ref=f"channel:{uuid.uuid4().hex}",
        )
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        db_session.add(
            UsageLedger(
                partner_id=world.partner_id,
                tenant_id=None,
                qty=UNIT // 2,
                bucket="included",
                kind="debit",
                idempotency_key=f"companion:{uuid.uuid4().hex}",
            )
        )
        await build_budget.record(db_session, world.partner_id, 22_000)
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        db_session.add(
            UsageRecord(
                tenant_id=world.us.tenant_id,
                partner_id=world.partner_id,
                occurred_at=datetime.now(UTC),
                meter="llm.input_tokens",
                quantity=Decimal(1000),
                billable_qty=Decimal(1000),
                cost_usd=Decimal("0.10"),
                idempotency_key=f"build:{uuid.uuid4().hex}",
                source="builder",
                line="build",
            )
        )
        db_session.add(
            UsageRecord(
                tenant_id=world.us.tenant_id,
                partner_id=world.partner_id,
                occurred_at=datetime.now(UTC),
                meter="media.image",
                quantity=Decimal(1),
                billable_qty=Decimal(1),
                cost_usd=None,
                idempotency_key=f"chan:{uuid.uuid4().hex}",
                source="channel",
            )
        )
        db_session.add(
            DailyCostSnapshot(
                tenant_id=world.us.tenant_id,
                day=datetime.now(UTC).date(),
                cost_usd_total=Decimal("0.50"),
                message_count=40,
            )
        )
    await db_session.commit()
    return world


async def test_the_three_figures_the_lines_and_the_table(client: Any, db_session: Any) -> None:
    world = await _seed(client, db_session)
    resp = await client.get("/console/usage/summary", headers=world.headers())
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["currency"] == "USD"
    spent_es_usd = fx.convert(fx.convert(2 * UNIT, Decimal(1) / EUR_USD), EUR_USD)
    assigned = 10 * UNIT + int(10 * UNIT * EUR_USD)
    assert out["available"] == money(100 * UNIT - assigned, "USD"), "sin el pool incluido"
    in_bags = 8 * UNIT + fx.convert(10 * UNIT - fx.convert(2 * UNIT, Decimal(1) / EUR_USD), EUR_USD)
    assert out["in_bags"] == money(in_bags, "USD")
    assert out["in_bags_approx"] is True, "hay una bolsa en euros"
    conversations = 2 * UNIT + spent_es_usd
    assert out["month_spend"] == money(conversations + UNIT // 2, "USD")
    assert out["projected"]["amount_micros"] >= out["month_spend"]["amount_micros"]

    lines = {line["line"]: line for line in out["lines"]}
    assert set(lines) == {"conversations", "meta", "build", "companion"}
    assert {k: v["payer"] for k, v in lines.items()} == {
        "conversations": "client_bag",
        "meta": "business_meta",
        "build": "auphere",
        "companion": "account",
    }
    assert lines["conversations"]["amount"] == money(conversations, "USD")
    assert lines["companion"]["amount"] == money(UNIT // 2, "USD")
    assert lines["meta"]["amount"] == money(50_000, "USD") and lines["meta"]["approx"] is True
    assert lines["build"]["amount"] == money(22_000, "USD")
    assert lines["build"]["cap"] == money(50 * UNIT, "USD"), "50 por defecto, en dinero"

    rows = {row["ref"]: row for row in out["clients"]}
    assert rows[world.us.ref]["bag"] == money(8 * UNIT, "USD")
    assert rows[world.us.ref]["month_spent"] == money(2 * UNIT, "USD")
    assert rows[world.us.ref]["empty"] is False
    assert rows[world.es.ref]["bag"]["currency"] == "EUR", "cada bolsa en su moneda"


async def test_the_same_figure_everywhere(client: Any, db_session: Any) -> None:
    world = await _seed(client, db_session)
    summary = (await client.get("/console/usage/summary", headers=world.headers())).json()
    daily = (
        await client.get(
            f"/console/usage/daily?days=7&client={world.us.ref}&line=conversations",
            headers=world.headers(),
        )
    ).json()
    bags_list = (await client.get("/console/wallet/bags", headers=world.headers())).json()
    row = next(r for r in summary["clients"] if r["ref"] == world.us.ref)
    assert sum(daily["series"]["conversations"]) == row["month_spent"]["amount_micros"]
    bag = next(b for b in bags_list if b["ref"] == world.us.ref)
    assert bag["balance"] == row["bag"], "la bolsa se lee igual en Consumo y en la lista"
    budget = (await client.get("/console/usage/build-budget", headers=world.headers())).json()
    build = next(line for line in summary["lines"] if line["line"] == "build")
    assert budget["spent"] == build["amount"]
    # La lista de clientes y la consola lite leen la misma bolsa (46.7).
    from nexus_api.services.lite_home import bag_balance

    listed = (await client.get("/console/clients", headers=world.headers())).json()
    rows = listed["items"]
    es_row = next(r for r in rows if r["external_client_ref"] == world.es.ref)
    es_bag = next(b for b in bags_list if b["ref"] == world.es.ref)
    assert es_row["bag"]["balance"]["currency"] == "EUR"
    assert (
        es_row["bag"]["balance"]["amount_micros"]
        == es_bag["balance"]["amount_micros"] // 1000 * 1000
    )
    lite = await bag_balance(world.partner_id, world.es.tenant_id, datetime.now(UTC))
    assert lite is not None and lite.currency == "EUR"
    assert lite.remaining_cents == es_bag["balance"]["amount_micros"] // 1000


async def test_the_daily_chart_is_7_30_or_90_days_filterable(client: Any, db_session: Any) -> None:
    world = await _seed(client, db_session)
    for days in (7, 30, 90):
        resp = await client.get(f"/console/usage/daily?days={days}", headers=world.headers())
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert len(out["days"]) == days and len(out["total"]) == days
        assert set(out["series"]) == {"conversations", "meta", "build", "companion"}
        assert out["total"][-1] == sum(v[-1] for v in out["series"].values())
    assert (
        await client.get("/console/usage/daily?days=14", headers=world.headers())
    ).status_code == 422
    one = (
        await client.get("/console/usage/daily?days=7&line=meta", headers=world.headers())
    ).json()
    assert list(one["series"]) == ["meta"] and one["approx_lines"] == ["meta"]
    foreign = await client.get("/console/usage/daily?days=7&client=nope", headers=world.headers())
    assert foreign.status_code == 404


async def test_the_build_line_has_a_money_cap_warns_at_80_and_stops_at_100(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=("builder",))
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        assert await build_budget.record(db_session, world.partner_id, 40 * UNIT) == [
            "build.budget.warning"
        ]
        assert await build_budget.record(db_session, world.partner_id, UNIT) == []
        assert await build_budget.record(db_session, world.partner_id, 9 * UNIT) == [
            "build.budget.exhausted"
        ]
    state = (await client.get("/console/usage/build-budget", headers=world.headers())).json()
    assert state["state"] == "exhausted" and state["paid_by"] == "auphere"
    assert "tokens" not in str(state), "nunca en tokens"
    stopped = await client.post(
        f"/console/clients/{world.us.ref}/agents/draft-jobs",
        json={"name": "Ventas", "start": "blank"},
        headers=world.headers(),
    )
    assert stopped.status_code == 402
    assert stopped.json()["detail"] == {"code": "build_budget_exhausted"}
    url = "/console/usage/build-budget/extension-request"
    assert (await client.post(url, headers=world.as_role("builder"))).status_code == 201
    assert (await client.post(url, headers=world.headers())).status_code == 429, "una al día"


async def test_the_technical_detail_and_the_csv(client: Any, db_session: Any) -> None:
    world = await _seed(client, db_session)
    detail = await client.get("/console/usage/detail?days=7", headers=world.headers())
    assert detail.status_code == 200, detail.text
    rows = detail.json()["rows"]
    build = next(r for r in rows if r["meter"] == "llm.input_tokens")
    assert "agent_name" in build
    assert (build["ref"], build["line"], build["source"]) == (world.us.ref, "build", "builder")
    image = next(r for r in rows if r["meter"] == "media.image")
    assert image["line"] == "conversations", "sin partida guardada, la del origen"
    assert image["unpriced"] == 1, "lo que aún no tiene precio, marcado"
    assert "cost_usd" not in detail.text, "el partner ve precios, nunca costes"
    csv = await client.get("/console/usage/export.csv?days=7&lang=es", headers=world.headers())
    assert csv.status_code == 200
    assert world.us.ref in csv.text
