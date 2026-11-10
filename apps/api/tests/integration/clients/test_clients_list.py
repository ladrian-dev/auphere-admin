"""Spec 047, T064 — la lista de clientes dice quién necesita algo (historia 15, requisito 7).

``GET /console/clients?q=&filter=all|attention|active|archived`` con la consola nueva:

- **las columnas**: el nombre y el nicho, el estado con su motivo, un punto por
  agente con su ``visible_state`` y un resumen, la bolsa (lo que queda de lo
  asignado, los días y el porcentaje) y las acciones;
- **la regla única** (``services/attention.py``): la misma en la lista y en el
  Panel del cliente;
- **el orden**: primero los que necesitan algo y, dentro de cada grupo, de menos
  a más días de saldo;
- **la búsqueda** por nombre y por nicho, y **los filtros** con sus contadores;
- **bolsas de monedas distintas**: se comparan por días y porcentaje, nunca por
  el importe;
- **las acciones según el permiso**: lo que no se puede no aparece, salvo
  «Asignar saldo», que pasa a «Pedir saldo».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Tenant, TenantStatus
from tests.conftest import add_console_member

from ._client_world import add_agent, add_spend, new_client, roomy, set_bag, tenant_of

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: 1 US$ = 100 000 créditos.
USD = 100_000


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    await roomy(db_session, console_world)
    return console_world


def _yesterday(n: int) -> datetime:
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    return today - timedelta(days=n)


async def _client(
    client: Any,
    db_session: AsyncSession,
    world: dict[str, Any],
    name: str,
    niche: str,
    *,
    cap: int,
    remaining: int,
    daily_spend: int = 0,
    agents: tuple[tuple[str, bool, str | None], ...] = (("Recepción", True, "active"),),
) -> dict[str, Any]:
    a = world["a"]
    created = await new_client(client, a["headers"](), name=name, niche=niche)
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    await set_bag(db_session, a["partner_id"], tenant_id, cap=cap, remaining=remaining)
    for agent_name, published, channel in agents:
        await add_agent(db_session, tenant_id, agent_name, published=published, channel=channel)
    if daily_spend:
        for n in range(1, 8):
            await add_spend(db_session, a["partner_id"], tenant_id, daily_spend, at=_yesterday(n))
    return {"ref": created["ref"], "tenant_id": tenant_id}


async def _list(client: Any, headers: dict[str, str], **params: str) -> dict[str, Any]:
    resp = await client.get("/console/clients", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _portfolio(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # Sin saldo: la bolsa a cero.
    out["empty"] = await _client(
        client,
        db_session,
        world,
        "Floristería Lirio",
        "Floristería",
        cap=10 * USD,
        remaining=0,
        daily_spend=USD,
    )
    # Saldo bajo: menos del 20 % (y para 4 días).
    out["low"] = await _client(
        client,
        db_session,
        world,
        "Clínica Sonrisa",
        "Clínica dental",
        cap=50 * USD,
        remaining=8 * USD,
        daily_spend=2 * USD,
    )
    # Un agente guardado sin canal.
    out["no_channel"] = await _client(
        client,
        db_session,
        world,
        "Café Origen",
        "Cafetería de especialidad",
        cap=100 * USD,
        remaining=90 * USD,
        agents=(("Pedidos", True, None),),
    )
    # Todo bien: mucho saldo, mucho ritmo.
    out["ok_fast"] = await _client(
        client,
        db_session,
        world,
        "Barbería Cultor",
        "Barbería de barrio",
        cap=200 * USD,
        remaining=150 * USD,
        daily_spend=5 * USD,
    )
    out["ok_slow"] = await _client(
        client,
        db_session,
        world,
        "Óptica Luz",
        "Óptica",
        cap=20 * USD,
        remaining=18 * USD,
        daily_spend=USD // 10,
    )
    return out


async def test_the_rows_carry_niche_state_agents_bag_and_actions(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    p = await _portfolio(client, db_session, world)
    body = await _list(client, world["a"]["headers"]())
    rows = {r["external_client_ref"]: r for r in body["items"]}
    empty = rows[p["empty"]["ref"]]
    assert empty["niche"] == "Floristería" and empty["lifecycle"] == "active"
    assert empty["attention"]["needs"] is True
    assert empty["attention"]["reasons"][0] == {"code": "no_balance", "count": 1}
    assert empty["bag"]["state"] == "empty"
    assert empty["bag"]["balance"] == {"amount_micros": 0, "currency": "USD"}

    low = rows[p["low"]["ref"]]
    assert low["attention"]["reasons"][0]["code"] == "low_balance"
    assert low["bag"]["pct_left"] == 16.0
    assert low["bag"]["days_left"] == 4.0
    assert low["bag"]["balance"] == {"amount_micros": 8 * USD, "currency": "USD"}
    assert low["bag"]["assigned"] == {"amount_micros": 50 * USD, "currency": "USD"}

    no_channel = rows[p["no_channel"]["ref"]]
    assert {"code": "agent_without_channel", "count": 1} in no_channel["attention"]["reasons"]
    (agent,) = no_channel["agents"]
    assert agent["name"] == "Pedidos" and agent["visible_state"]["code"] == "ready_no_channel"
    assert no_channel["agents_summary"] == {
        "total": 1,
        "serving": 0,
        "testing": 0,
        "ready_no_channel": 1,
        "draft": 0,
        "paused": 0,
    }
    # Sin consumo no hay ritmo: los días no se estiman.
    assert no_channel["bag"]["days_left"] is None and no_channel["bag"]["pct_left"] == 90.0

    ok = rows[p["ok_fast"]["ref"]]
    assert ok["attention"] == {"needs": False, "reasons": []}
    assert ok["agents"][0]["visible_state"]["code"] == "serving"
    assert set(ok["allowed"]) == {"edit", "assign_balance", "new_agent", "archive", "delete"}
    # Lo que no lleva la lista: ni ids internos ni costes.
    assert "tenant_id" not in str(body) and "cost" not in str(body)


async def test_the_order_puts_attention_first_then_the_fewest_days(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    p = await _portfolio(client, db_session, world)
    body = await _list(client, world["a"]["headers"](), filter="all")
    order = [r["external_client_ref"] for r in body["items"]]
    # La bolsa a cero, la primera; después los que necesitan algo; luego el
    # resto, de menos a más días (no por importe: 150 US$ duran 30 días; 18, 180).
    assert order[0] == p["empty"]["ref"]
    assert order.index(p["low"]["ref"]) < order.index(p["ok_fast"]["ref"])
    assert order.index(p["no_channel"]["ref"]) < order.index(p["ok_fast"]["ref"])
    assert order.index(p["ok_fast"]["ref"]) < order.index(p["ok_slow"]["ref"])
    # El cliente de ``console_world`` no tiene agentes: también necesita algo.
    seeded = next(r for r in body["items"] if r["external_client_ref"] == world["a"]["ref"])
    assert {"code": "no_agents", "count": 1} in seeded["attention"]["reasons"]


async def test_search_by_name_or_niche_and_filters_with_counters(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    p = await _portfolio(client, db_session, world)
    a = world["a"]
    async with db_session.begin():
        tenant = await db_session.get(Tenant, p["ok_slow"]["tenant_id"])
        assert tenant is not None
        tenant.status = TenantStatus.ARCHIVED
    everything = await _list(client, a["headers"]())
    assert everything["counts"] == {"all": 6, "attention": 4, "active": 5, "archived": 1}
    attention = await _list(client, a["headers"](), filter="attention")
    assert {r["external_client_ref"] for r in attention["items"]} == {
        p["empty"]["ref"],
        p["low"]["ref"],
        p["no_channel"]["ref"],
        a["ref"],
    }
    archived = await _list(client, a["headers"](), filter="archived")
    (row,) = archived["items"]
    assert row["external_client_ref"] == p["ok_slow"]["ref"]
    assert row["attention"]["needs"] is False  # archivar es apartarlo a propósito
    assert "restore" in row["allowed"] and "archive" not in row["allowed"]

    by_niche = await _list(client, a["headers"](), q="dental")
    assert [r["external_client_ref"] for r in by_niche["items"]] == [p["low"]["ref"]]
    accents = await _list(client, a["headers"](), q="optica")
    assert [r["external_client_ref"] for r in accents["items"]] == [p["ok_slow"]["ref"]]
    # Los contadores, sobre lo buscado.
    assert accents["counts"] == {"all": 1, "attention": 0, "active": 0, "archived": 1}


async def test_actions_follow_the_permission_and_ask_for_balance_instead(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    p = await _portfolio(client, db_session, world)
    a = world["a"]
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    as_builder = {
        r["external_client_ref"]: r for r in (await _list(client, builder["headers"]()))["items"]
    }
    assert set(as_builder[p["low"]["ref"]]["allowed"]) == {
        "edit",
        "request_balance",
        "new_agent",
        "archive",
    }
    as_analyst = {
        r["external_client_ref"]: r for r in (await _list(client, analyst["headers"]()))["items"]
    }
    assert as_analyst[p["low"]["ref"]]["allowed"] == ["request_balance"]


async def test_the_list_and_the_panel_say_the_same(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    p = await _portfolio(client, db_session, world)
    a = world["a"]
    rows = {r["external_client_ref"]: r for r in (await _list(client, a["headers"]()))["items"]}
    for key in ("empty", "low", "no_channel", "ok_fast"):
        ref = p[key]["ref"]
        panel = await client.get(f"/console/clients/{ref}/panel", headers=a["headers"]())
        assert panel.status_code == 200, panel.text
        assert panel.json()["attention"] == rows[ref]["attention"], key
        assert panel.json()["bag"]["days_left"] == rows[ref]["bag"]["days_left"], key


async def test_todays_console_keeps_its_list(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """El partner B no tiene la consola nueva: la lista de siempre, con su ``status``."""
    b = world["b"]
    body = await _list(client, b["headers"](), status="active")
    assert body["total"] == 1
    assert body["items"][0]["external_client_ref"] == b["ref"]
    assert "counts" not in body or body["counts"] is None
