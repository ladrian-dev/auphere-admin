"""Spec 030 T095 — el cliente ve cada agente por separado (R4.2, R5.3, R14.7).

Con **más de un agente**:

- el Panel desglosa el gasto del mes por agente y la suma es el total **al
  céntimo** (lo que el cliente ve arriba);
- el Consumo da por agente gasto, conversaciones y cuota;
- la Bandeja etiqueta cada conversación con el agente de su número y filtra
  por agente.

Con **uno** nada de eso aparece (``None``): no se inventa un desglose de una
sola fila. Lo gastado antes de que hubiera agentes (asientos sin agente) es
del principal.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Agent, Channel, ChannelType, Conversation, UsageLedger
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio


async def _second_agent(
    db_session, w: dict[str, Any], inbox: dict[str, Any]
) -> tuple[uuid.UUID, uuid.UUID]:
    """Principal (from the trigger) + «Ventas», which answers on a second number
    with one of the conversations moved to it."""
    principal = (
        await db_session.execute(sa.select(Agent.id).where(Agent.tenant_id == w["tenant_id"]))
    ).scalar_one_or_none()
    if principal is None:
        principal = uuid.uuid4()
        db_session.add(
            Agent(
                id=principal,
                tenant_id=w["tenant_id"],
                name="Agente principal",
                created_at=datetime.now(UTC) - timedelta(days=30),
            )
        )
    sales = uuid.uuid4()
    db_session.add(Agent(id=sales, tenant_id=w["tenant_id"], name="Ventas"))
    await db_session.flush()
    number = Channel(
        id=uuid.uuid4(),
        tenant_id=w["tenant_id"],
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3461{uuid.uuid4().int % 10**7:07d}",
        config={"phone_number_id": "PN2"},
        agent_id=sales,
    )
    db_session.add(number)
    await db_session.flush()
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == inbox["conversations"][1])
        .values(channel_id=number.id)
    )
    await db_session.commit()
    return principal, sales


async def _ledger(db_session, w, agent_id: uuid.UUID | None, qty: int) -> None:
    db_session.add(
        UsageLedger(
            partner_id=w["partner_id"],
            tenant_id=w["tenant_id"],
            qty=qty,
            bucket="purchased",
            idempotency_key=f"t:{uuid.uuid4()}",
            agent_id=agent_id,
        )
    )
    await db_session.commit()


async def test_one_agent_has_no_breakdown(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    home = (await client.get("/console/lite/home", headers=inbox["headers"]())).json()
    assert home["spend_month"]["by_agent"] is None
    usage = (await client.get("/console/lite/usage/summary", headers=inbox["headers"]())).json()
    assert usage["by_agent"] is None
    items = (
        await client.get("/console/lite/inbox/conversations", headers=inbox["headers"]())
    ).json()["items"]
    assert all(i["agent"] is None for i in items)


async def test_two_agents_split_the_spend_to_the_cent(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    principal, sales = await _second_agent(db_session, w, inbox)
    # 1 cent = 1000 credits; odd amounts so the rounding has to be decided.
    await _ledger(db_session, w, principal, 123_456)
    await _ledger(db_session, w, None, 10_501)  # before agents existed → the principal's
    await _ledger(db_session, w, sales, 77_777)

    home = (await client.get("/console/lite/home", headers=inbox["headers"]())).json()
    split = home["spend_month"]["by_agent"]
    assert [s["name"] for s in split] == ["Agente principal", "Ventas"]
    assert sum(s["cents"] for s in split) == home["spend_month"]["total_cents"]
    assert split[0]["cents"] > split[1]["cents"]

    usage = (await client.get("/console/lite/usage/summary", headers=inbox["headers"]())).json()
    rows = usage["by_agent"]
    assert sum(r["spent_cents"] for r in rows) == usage["month"]["spent_cents"]
    assert sum(r["share_pct"] for r in rows) in (99, 100, 101)


async def test_the_inbox_labels_and_filters_by_agent(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    principal, sales = await _second_agent(db_session, w, inbox)
    url = "/console/lite/inbox/conversations"
    items = (await client.get(url, headers=inbox["headers"]())).json()["items"]
    labels = {i["id"]: i["agent"] for i in items}
    assert labels[str(inbox["conversations"][0])] == {
        "id": str(principal),
        "name": "Agente principal",
    }
    assert labels[str(inbox["conversations"][1])] == {"id": str(sales), "name": "Ventas"}

    only_sales = (
        await client.get(url, headers=inbox["headers"](), params={"agent": str(sales)})
    ).json()
    assert [i["id"] for i in only_sales["items"]] == [str(inbox["conversations"][1])]
    detail = (
        await client.get(f"{url}/{inbox['conversations'][1]}", headers=inbox["headers"]())
    ).json()
    assert detail["agent"] == {"id": str(sales), "name": "Ventas"}


async def test_me_lists_the_active_agents(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    principal, sales = await _second_agent(db_session, w, inbox)
    me = (await client.get("/console/lite/me", headers=inbox["headers"]())).json()
    assert me["agents"] == [
        {"id": str(principal), "name": "Agente principal"},
        {"id": str(sales), "name": "Ventas"},
    ]


async def test_the_daily_spend_filters_by_agent(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    principal, sales = await _second_agent(db_session, w, inbox)
    await _ledger(db_session, w, principal, 100_000)
    await _ledger(db_session, w, None, 50_000)  # before agents → the principal's
    await _ledger(db_session, w, sales, 30_000)
    url = "/console/lite/usage/spend"

    async def month(params: dict[str, str] | None = None) -> int:
        r = await client.get(url, headers=inbox["headers"](), params=params or {})
        assert r.status_code == 200, r.text
        assert sum(r.json()["series_cents"]) == r.json()["month_cents"]
        return int(r.json()["month_cents"])

    total = await month()
    only_sales = await month({"agent": str(sales)})
    only_principal = await month({"agent": str(principal)})
    assert only_sales == 30
    assert only_principal == 150
    assert total == only_sales + only_principal

    ghost = await client.get(url, headers=inbox["headers"](), params={"agent": str(uuid.uuid4())})
    assert ghost.status_code == 404


async def test_the_neighbours_real_agent_is_nobody_here(client, db_session, console_world) -> None:
    """Not a random id: the real agent of another client of the same partner."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _second_agent(db_session, w, inbox)
    neighbour = console_world["b"]
    foreign = uuid.uuid4()
    db_session.add(Agent(id=foreign, tenant_id=neighbour["tenant_id"], name="Ventas"))
    await db_session.commit()

    spend = await client.get(
        "/console/lite/usage/spend", headers=inbox["headers"](), params={"agent": str(foreign)}
    )
    assert spend.status_code == 404
    listed = await client.get(
        "/console/lite/inbox/conversations",
        headers=inbox["headers"](),
        params={"agent": str(foreign)},
    )
    assert listed.status_code == 200
    assert listed.json()["items"] == []
