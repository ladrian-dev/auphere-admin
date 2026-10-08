"""Spec 030 — el Panel de un solo cliente (Requisito 4).

``GET /console/lite/home`` calcula con LAS MISMAS funciones que el Inicio del
partner, acotadas al cliente de quien entra. Lo que fija este archivo:

- cada cifra coincide al céntimo con la que el partner ve de ese cliente
  (CE-003): conversaciones de 7 días, gasto del mes, tope que queda;
- la ausencia se diseña: sin Bandeja no hay «esperan a una persona»; con un
  agente no hay desglose; sin semana anterior no hay variación inventada; sin
  gasto no hay días inventados; sin tope no hay saldo inventado;
- «Necesita tu atención» dice lo que pasa con el saldo, sin botón de compra.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    PartnerAllocation,
)
from tests.conftest import add_client_member, make_client_access, spend_from_wallet

pytestmark = pytest.mark.asyncio

HOME = "/console/lite/home"


async def _seed_activity(db_session, tenant_id: uuid.UUID, *, escalated: bool = True) -> None:
    now = datetime.now(UTC)
    ch = Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
        config={"phone_number_id": "PN"},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="x",
            tools=[],
        )
    )
    await db_session.flush()
    for i in range(3):
        cust = Customer(id=uuid.uuid4(), tenant_id=tenant_id, identifier=f"5691234{i:04d}")
        db_session.add(cust)
        await db_session.flush()
        db_session.add(
            Conversation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                customer_id=cust.id,
                channel_id=ch.id,
                status=ConversationStatus.ESCALATED
                if (escalated and i == 0)
                else ConversationStatus.OPEN,
                last_inbound_at=now,
                created_at=now - timedelta(days=i),
            )
        )
    await db_session.commit()


async def _fund(db_session, partner_id: uuid.UUID, credits: int) -> None:
    await db_session.execute(
        sa.text("UPDATE partner_wallets SET purchased_remaining = :c WHERE partner_id = :p"),
        {"c": credits, "p": partner_id},
    )
    await db_session.commit()


async def _member(db_session, w, modules=("panel", "inbox", "usage")):
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=modules
    )
    return await add_client_member(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


async def test_every_figure_matches_what_the_partner_sees(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    await _seed_activity(db_session, w["tenant_id"])
    await _fund(db_session, w["partner_id"], 2_000_000)
    await spend_from_wallet(
        partner_id=w["partner_id"], qty=123_457, lane="channel", tenant_id=w["tenant_id"]
    )
    member = await _member(db_session, w)

    lite = await client.get(HOME, headers=member["headers"]())
    assert lite.status_code == 200, lite.text
    partner = (await client.get("/console/home", headers=w["headers"]())).json()
    body = lite.json()
    assert body["errors"] == []

    row = next(r for r in partner["portfolio"] if r["external_client_ref"] == w["ref"])
    assert body["conversations"]["last_7d"] == row["conversations_7d"]
    assert [d["count"] for d in body["conversations"]["daily"]] == row["series_7d"]
    assert body["balance"]["remaining_cents"] == row["credit_remaining_cents"]
    assert body["balance"]["cap_cents"] == row["credit_cap_cents"]
    share = next(s for s in partner["spend"]["by_client"] if s["external_client_ref"] == w["ref"])
    assert body["spend_month"]["total_cents"] == share["cents"]
    assert body["spend_month"]["by_agent"] is None
    assert body["waiting"]["count"] == partner["to_review"]["escalated"] == 1
    assert body["waiting"]["first_conversation_id"] is not None


async def test_without_inbox_there_is_no_waiting_block(client, db_session, console_world) -> None:
    w = console_world["a"]
    await _seed_activity(db_session, w["tenant_id"])
    member = await _member(db_session, w, modules=("panel",))
    body = (await client.get(HOME, headers=member["headers"]())).json()
    assert body["waiting"] is None
    assert all(a["kind"] != "waiting" for a in body["attention"])


async def test_nothing_is_invented(client, db_session, console_world) -> None:
    w = console_world["a"]
    member = await _member(db_session, w)
    body = (await client.get(HOME, headers=member["headers"]())).json()
    # Sin semana anterior, sin gasto: ni variación ni días inventados.
    assert body["conversations"]["prev_7d"] is None
    assert body["balance"]["days_left"] is None
    assert body["attention"] == []


async def test_no_allocation_reads_as_unassigned(client, db_session, console_world) -> None:
    w = console_world["a"]
    await db_session.execute(
        sa.delete(PartnerAllocation).where(PartnerAllocation.tenant_id == w["tenant_id"])
    )
    await db_session.commit()
    member = await _member(db_session, w)
    body = (await client.get(HOME, headers=member["headers"]())).json()
    assert body["balance"]["assigned"] is False
    assert body["balance"]["remaining_cents"] is None


async def test_attention_says_the_balance_is_out(client, db_session, console_world) -> None:
    w = console_world["a"]
    await db_session.execute(
        sa.update(PartnerAllocation)
        .where(PartnerAllocation.tenant_id == w["tenant_id"])
        .values(remaining=0)
    )
    await db_session.commit()
    member = await _member(db_session, w)
    body = (await client.get(HOME, headers=member["headers"]())).json()
    assert {"kind": "balance_out", "count": None, "days_left": None} in body["attention"]


async def test_attention_warns_when_the_balance_will_not_last(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    await _fund(db_session, w["partner_id"], 5_000_000)
    # Gasta 70 000 en la semana (10 000/día) y le quedan 20 000: dos días.
    await db_session.execute(
        sa.update(PartnerAllocation)
        .where(PartnerAllocation.tenant_id == w["tenant_id"])
        .values(cap=500_000, remaining=90_000)
    )
    await db_session.commit()
    await spend_from_wallet(
        partner_id=w["partner_id"], qty=70_000, lane="channel", tenant_id=w["tenant_id"]
    )
    member = await _member(db_session, w)
    body = (await client.get(HOME, headers=member["headers"]())).json()
    low = [a for a in body["attention"] if a["kind"] == "balance_low"]
    assert low and low[0]["days_left"] is not None
    assert body["balance"]["days_left"] == pytest.approx(low[0]["days_left"], abs=0.1)


async def test_never_another_clients_data(client, db_session, console_world) -> None:
    w, b = console_world["a"], console_world["b"]
    await _seed_activity(db_session, b["tenant_id"])
    member = await _member(db_session, w)
    body = (await client.get(HOME, headers=member["headers"]())).json()
    assert body["conversations"]["last_7d"] == 0
    assert body["waiting"]["count"] == 0
