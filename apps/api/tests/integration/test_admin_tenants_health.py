"""Spec 036 — the health of every client, for the client list.

Read client by client under each client's GUC: every row carries its own
client, and the Playground's channel and conversations never count.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, Channel, ChannelStatus, ChannelType
from nexus_api.db.models.agent import AgentConfigStatus
from nexus_api.db.models.conversation import Conversation, ConversationStatus, Customer

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _channel(
    tenant_id: uuid.UUID,
    *,
    identifier: str,
    status: ChannelStatus = ChannelStatus.ACTIVE,
    provider: str = "meta",
) -> uuid.UUID:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        row = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP if provider != "qa_playground" else ChannelType.WEB,
            provider=provider,
            provider_identifier=identifier,
            config={"display_phone_number": identifier},
            status=status,
        )
        s.add(row)
        await s.flush()
        return row.id


async def _conversation(
    tenant_id: uuid.UUID, channel_id: uuid.UUID, *, status: ConversationStatus, at: datetime
) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        customer = Customer(tenant_id=tenant_id, identifier=f"+5690{uuid.uuid4().int % 10**7:07d}")
        s.add(customer)
        await s.flush()
        s.add(
            Conversation(
                tenant_id=tenant_id,
                channel_id=channel_id,
                customer_id=customer.id,
                status=status,
                last_message_at=at,
            )
        )


async def _publish(tenant_id: uuid.UUID, version: int) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        s.add(
            AgentConfig(
                tenant_id=tenant_id,
                version=version,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Atiende a los clientes.",
                tools=[],
                policies={},
            )
        )


async def test_each_client_gets_its_own_health(client, console_world, admin_headers) -> None:
    a, b = console_world["a"], console_world["b"]
    now = datetime.now(UTC)
    ch = await _channel(a["tenant_id"], identifier="+56911111111")
    await _channel(a["tenant_id"], identifier="+56922222222", status=ChannelStatus.DEGRADED)
    qa = await _channel(
        a["tenant_id"], identifier=f"qa_playground:{a['tenant_id']}", provider="qa_playground"
    )
    await _conversation(a["tenant_id"], ch, status=ConversationStatus.OPEN, at=now)
    await _conversation(
        a["tenant_id"], ch, status=ConversationStatus.CLOSED, at=now - timedelta(days=2)
    )
    # The Playground's conversations are not the client's.
    await _conversation(a["tenant_id"], qa, status=ConversationStatus.OPEN, at=now)
    await _publish(a["tenant_id"], 3)

    res = await client.get("/admin/tenants-health", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["unreadable"] == []
    rows = {r["tenant_id"]: r for r in body["clients"]}

    ra = rows[str(a["tenant_id"])]
    assert ra["channels_active"] == 1
    assert ra["channels_attention"] == 1
    assert ra["primary_channel"] == {
        "type": "whatsapp",
        "identifier": "+56911111111",
        "status": "active",
    }
    assert ra["agent_version"] == 3
    assert ra["open_conversations"] == 1
    assert ra["conversations_7d"] == 2
    assert ra["last_message_at"] is not None
    assert ra["connectors_attention"] == 0

    rb = rows[str(b["tenant_id"])]
    assert rb["channels_active"] == 0
    assert rb["primary_channel"] is None
    assert rb["open_conversations"] == 0
    assert rb["last_message_at"] is None


async def test_the_health_view_requires_the_admin_token(client) -> None:
    assert (await client.get("/admin/tenants-health")).status_code in (401, 403)


async def test_one_clients_health_and_its_conversations_name_people(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    ch = await _channel(a["tenant_id"], identifier="+56933333333")
    await _conversation(a["tenant_id"], ch, status=ConversationStatus.OPEN, at=datetime.now(UTC))

    one = await client.get(f"/admin/tenants-health/{a['tenant_id']}", headers=admin_headers)
    assert one.status_code == 200, one.text
    assert one.json()["open_conversations"] == 1

    page = await client.get(f"/admin/tenants/{a['tenant_id']}/conversations", headers=admin_headers)
    assert page.status_code == 200, page.text
    item = page.json()["items"][0]
    assert item["customer_identifier"].startswith("+5690")
    assert item["last_message_at"] is not None
