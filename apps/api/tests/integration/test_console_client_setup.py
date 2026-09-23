"""Spec 017 (R1.1-R1.3, R5.2, R9.1): the record and the list say what stands
between a client and «atendiendo», with the quota next to it.

``setup`` is a READING of things that already exist (active version, a
customer-facing channel, the ledger, the tenant status), never a new state
machine; ``next`` is the first pending step in the fixed order agent →
channel → quota → activation. The Playground channel is not a channel.
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
    Tenant,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


def _agent(tenant_id: uuid.UUID, *, seed: str | None, status=AgentConfigStatus.ACTIVE, version=1):
    return AgentConfig(
        tenant_id=tenant_id,
        version=version,
        status=status,
        system_prompt_rendered="x",
        tools=[],
        seed_template_ref=seed,
    )


def _channel(tenant_id: uuid.UUID, *, provider: str = "meta", type_=ChannelType.WHATSAPP):
    return Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=type_,
        provider=provider,
        provider_identifier=f"+3460017{uuid.uuid4().int % 10000:04d}",
        config={},
        status=ChannelStatus.ACTIVE,
    )


async def test_the_record_reads_sector_setup_and_quota(client, console_world, db_session) -> None:
    a = console_world["a"]
    # World: active tenant, allocation 500 000, no agent, no channel.
    r = await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sector"] is None
    assert body["setup"] == {
        "agent": False,
        "channel": False,
        "quota": True,
        "active": True,
        "next": "agent",
    }
    assert body["quota"] == {"cap": 500_000, "remaining": 500_000}
    assert body["health"]["missing"] == ["agent", "whatsapp"]  # the 016 reading stays

    # An active agent seeded from the bakery template → sector; a Playground
    # channel does NOT count as a channel.
    db_session.add(_agent(a["tenant_id"], seed="panaderia_v1"))
    db_session.add(_channel(a["tenant_id"], provider="qa_playground", type_=ChannelType.WEB))
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())).json()
    assert body["sector"] == "panaderia"
    assert body["setup"]["agent"] is True
    assert body["setup"]["channel"] is False
    assert body["setup"]["next"] == "channel"

    # A real channel → next is None: the client is serving.
    db_session.add(_channel(a["tenant_id"]))
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())).json()
    assert body["setup"]["channel"] is True
    assert body["setup"]["next"] is None


async def test_sector_comes_from_the_draft_when_there_is_no_active_version(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    db_session.add(_agent(a["tenant_id"], seed="restaurante_v2", status=AgentConfigStatus.STAGED))
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())).json()
    assert body["sector"] == "restaurante"
    assert body["setup"]["agent"] is False


async def test_quota_step_and_next_follow_the_ledger(client, console_world, db_session) -> None:
    a = console_world["a"]
    db_session.add(_agent(a["tenant_id"], seed=None))
    db_session.add(_channel(a["tenant_id"]))
    await db_session.execute(
        sa.update(PartnerAllocation)
        .where(PartnerAllocation.tenant_id == a["tenant_id"])
        .values(remaining=0)
    )
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())).json()
    assert body["setup"]["quota"] is False
    assert body["setup"]["next"] == "quota"
    assert body["quota"] == {"cap": 500_000, "remaining": 0}
    assert body["out_of_quota"] is True

    # No allocation row at all → «sin cupo asignado»: quota is null and the
    # step is pending, the same reading as the channel gate (spec 016 R2.1).
    await db_session.execute(
        sa.delete(PartnerAllocation).where(PartnerAllocation.tenant_id == a["tenant_id"])
    )
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())).json()
    assert body["quota"] is None
    assert body["setup"]["quota"] is False


async def test_activation_is_the_last_step(client, console_world, db_session) -> None:
    a = console_world["a"]
    db_session.add(_agent(a["tenant_id"], seed=None))
    db_session.add(_channel(a["tenant_id"]))
    await db_session.execute(
        sa.update(Tenant).where(Tenant.id == a["tenant_id"]).values(status=TenantStatus.PAUSED)
    )
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())).json()
    assert body["setup"]["active"] is False
    assert body["setup"]["next"] == "activation"


async def test_the_list_carries_setup_quota_and_seven_day_conversations(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    db_session.add(_agent(a["tenant_id"], seed="panaderia_v1"))
    ch = _channel(a["tenant_id"])
    qa = _channel(a["tenant_id"], provider="qa_playground", type_=ChannelType.WEB)
    db_session.add_all([ch, qa])
    cust = Customer(
        id=uuid.uuid4(), tenant_id=a["tenant_id"], identifier="+34600111222", preferences={}
    )
    db_session.add(cust)
    await db_session.flush()
    now = datetime.now(UTC)
    for channel, age_days in ((ch, 1), (ch, 3), (ch, 10), (qa, 1)):
        db_session.add(
            Conversation(
                id=uuid.uuid4(),
                tenant_id=a["tenant_id"],
                channel_id=channel.id,
                customer_id=cust.id,
                status=ConversationStatus.OPEN,
                created_at=now - timedelta(days=age_days),
            )
        )
    await db_session.commit()

    r = await client.get("/console/clients", headers=a["headers"]())
    assert r.status_code == 200, r.text
    row = next(i for i in r.json()["items"] if i["external_client_ref"] == a["ref"])
    assert row["setup"] == {"agent": True, "channel": True, "quota": True, "active": True}
    assert "next" not in row["setup"]
    assert row["quota"] == {"cap": 500_000, "remaining": 500_000}
    # Two conversations in the last 7 days on the real channel; the 10-day-old
    # one and the Playground one do not count.
    assert row["conversations_7d"] == 2
    assert row["out_of_quota"] is False


async def test_the_list_never_shows_another_partners_figures(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    db_session.add(_agent(b["tenant_id"], seed="panaderia_v1"))
    db_session.add(_channel(b["tenant_id"]))
    await db_session.commit()
    r = await client.get("/console/clients", headers=a["headers"]())
    refs = {i["external_client_ref"] for i in r.json()["items"]}
    assert b["ref"] not in refs
    row = next(i for i in r.json()["items"] if i["external_client_ref"] == a["ref"])
    assert row["setup"]["agent"] is False and row["setup"]["channel"] is False
