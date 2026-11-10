"""Spec 047, T102 — la coexistencia con la app WhatsApp Business (historia 10;
requisitos 30.8, 30.11 y 30.12).

De punta a punta: el webhook firmado deja el evento en su stream, el consumidor
de la familia runner lo aplica y la base queda como pide la spec.

- **Un eco** se guarda como mensaje de una persona del negocio, pone «La lleva
  una persona» durante 2 h y el agente calla; pasado el plazo, vuelve a contestar.
- **``account_update``** con desconexión pasa el canal a «Con problemas» con su
  motivo y avisa al partner; los mensajes se siguen guardando.
- **El historial** se importa solo si el negocio lo aceptó, sin despertar al agente.
- **Los contactos** se sincronizan como clientes, sin pisar un nombre puesto.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from nexus_worker.streams.meta_coexistence import drain_once
from nexus_worker.streams.meta_echoes_consumer import STREAM as ECHOES
from nexus_worker.streams.meta_echoes_consumer import handle_echo
from nexus_worker.streams.meta_history_consumer import STREAM as HISTORY
from nexus_worker.streams.meta_history_consumer import handle_history
from nexus_worker.streams.meta_state_sync_consumer import STREAM as STATE_SYNC
from nexus_worker.streams.meta_state_sync_consumer import handle_state_sync
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ConsoleNotification,
    Conversation,
    Customer,
    Message,
    MessageDirection,
)

from ..business._business_world import Biz
from ._channel_world import _channel, _published, _say

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

META_APP_SECRET = "dev-meta-app-secret-change-me"
CUSTOMER = "34600222333"


def _envelope(field: str, business: str, pnid: str, value: dict[str, Any]) -> bytes:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_COEX",
                "changes": [
                    {
                        "field": field,
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business,
                                "phone_number_id": pnid,
                            },
                            **value,
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode()


async def _post(client: Any, body: bytes) -> None:
    resp = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )
    assert resp.status_code == 200, resp.text


async def _coexistence_line(
    db_session: AsyncSession, biz: Biz, number: str, **config: Any
) -> tuple[uuid.UUID, str]:
    agent_id = await _published(db_session, biz, f"Recepción {number[-3:]}")
    channel_id = await _channel(db_session, biz, agent_id, f"+{number}")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = await db_session.get(Channel, channel_id)
        assert channel is not None
        channel.audience_mode = "everyone"
        channel.coexistence = True
        channel.config = {**(channel.config or {}), "mode": "coexistence", **config}
        pnid = str(channel.config["phone_number_id"])
    await db_session.commit()
    return channel_id, pnid


async def _conversation(db_session: AsyncSession, biz: Biz, channel_id: uuid.UUID) -> Conversation:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        row = await db_session.scalar(
            sa.select(Conversation).where(Conversation.channel_id == channel_id),
            execution_options={"populate_existing": True},
        )
    assert row is not None
    return row


# ── ecos ───────────────────────────────────────────────────────────────────


async def test_an_echo_is_a_business_persons_message_and_silences_the_agent_for_two_hours(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    number = "34911000201"
    channel_id, pnid = await _coexistence_line(db_session, biz, number)
    echo = _envelope(
        "smb_message_echoes",
        number,
        pnid,
        {
            "messages": [
                {
                    "id": "wamid.echo-047",
                    "from": number,
                    "to": CUSTOMER,
                    "timestamp": "1761580800",
                    "type": "text",
                    "text": {"body": "Te lo miro yo, Lucía"},
                }
            ]
        },
    )
    await _post(client, echo)
    await _post(client, echo)  # Meta reintenta: el mismo wamid
    assert await drain_once(fake_redis, ECHOES, handle_echo, consumer_name="t") == 2

    async with tenant_scoped_session(db_session, biz.tenant_id):
        saved = (
            await db_session.scalars(
                sa.select(Message).where(Message.provider_message_id == "wamid.echo-047")
            )
        ).all()
    assert len(saved) == 1, "un eco repetido no se guarda dos veces"
    assert saved[0].origin == "business_app_echo"
    assert saved[0].direction is MessageDirection.OUTBOUND
    assert saved[0].status.value == "sent", "ya salió desde la app: no se vuelve a mandar"

    conversation = await _conversation(db_session, biz, channel_id)
    assert conversation.agent_active is False
    assert conversation.waiting_reason == "human_takeover"
    assert conversation.takeover_until is not None
    left = conversation.takeover_until - datetime.now(UTC)
    assert timedelta(hours=1, minutes=59) < left <= timedelta(hours=2)

    quiet = await _say(biz, channel_id, CUSTOMER, "¿me confirmas?")
    assert quiet.calls == [], "la lleva una persona: el agente calla"

    # Pasan las 2 h: el siguiente mensaje lo atiende el agente.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(Conversation)
            .where(Conversation.id == conversation.id)
            .values(takeover_until=datetime.now(UTC) - timedelta(minutes=1))
        )
    await db_session.commit()
    back = await _say(biz, channel_id, CUSTOMER, "¿sigues ahí?")
    assert len(back.calls) == 1
    after = await _conversation(db_session, biz, channel_id)
    assert after.agent_active is True and after.takeover_until is None


# ── account_update ─────────────────────────────────────────────────────────


async def test_an_account_update_marks_the_channel_with_problems_and_keeps_the_messages(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    number = "34911000202"
    channel_id, _pnid = await _coexistence_line(db_session, biz, number)
    body = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_COEX",
                    "changes": [
                        {
                            "field": "account_update",
                            "value": {"phone_number": number, "event": "ACCOUNT_OFFBOARDED"},
                        }
                    ],
                }
            ],
        }
    ).encode()
    await _post(client, body)
    await _post(client, body)  # repetido: un solo aviso

    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = await db_session.get(Channel, channel_id, populate_existing=True)
    assert channel is not None
    assert (channel.status, channel.problem_reason) == (
        ChannelStatus.DEGRADED,
        "coexistence_inactive",
    )
    page = await client.get(
        f"/console/clients/{biz.ref}/channels/{channel_id}", headers=biz.headers()
    )
    assert page.json()["visible_state"] == {
        "code": "problem",
        "tone": "danger",
        "reason": "coexistence_inactive",
    }
    notices = (
        await db_session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.partner_id == biz.partner_id,
                ConsoleNotification.kind == "channel.problem",
            )
        )
    ).all()
    # Uno al partner y otro a las personas del cliente (events.md §3).
    assert sorted(n.audience for n in notices) == ["client", "partner"]
    assert all(n.payload["reason"] == "coexistence_inactive" for n in notices)
    await db_session.commit()

    await _say(biz, channel_id, CUSTOMER, "hola, ¿estáis?")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        kept = await db_session.scalar(
            sa.select(Message).where(Message.content == "hola, ¿estáis?")
        )
    assert kept is not None, "los mensajes se siguen guardando"


# ── historial ──────────────────────────────────────────────────────────────


def _history(number: str, pnid: str) -> bytes:
    return _envelope(
        "history",
        number,
        pnid,
        {
            "history": [
                {
                    "metadata": {"phase": 0, "chunk_order": 1, "progress": 100},
                    "threads": [
                        {
                            "id": CUSTOMER,
                            "messages": [
                                {
                                    "from": CUSTOMER,
                                    "id": "wamid.h1",
                                    "timestamp": "1750000000",
                                    "type": "text",
                                    "text": {"body": "¿Tenéis hora el viernes?"},
                                },
                                {
                                    "from": number,
                                    "id": "wamid.h2",
                                    "timestamp": "1750000100",
                                    "type": "text",
                                    "text": {"body": "Sí, a las 18:00"},
                                },
                                {
                                    "from": CUSTOMER,
                                    "id": "wamid.h3",
                                    "timestamp": "1750000200",
                                    "type": "image",
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )


async def test_history_is_imported_only_when_the_business_accepted_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    refused_number = "34911000203"
    _refused, refused_pnid = await _coexistence_line(db_session, biz, refused_number)
    await _post(client, _history(refused_number, refused_pnid))
    await drain_once(fake_redis, HISTORY, handle_history, consumer_name="t")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        none = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(Message.origin == "history_import")
        )
    assert none == 0, "sin aceptarlo, no se importa"

    accepted_number = "34911000204"
    channel_id, pnid = await _coexistence_line(
        db_session, biz, accepted_number, history_import=True
    )
    await _post(client, _history(accepted_number, pnid))
    await _post(client, _history(accepted_number, pnid))
    await drain_once(fake_redis, HISTORY, handle_history, consumer_name="t")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.channel_id == channel_id)
                .order_by(Message.created_at)
            )
        ).all()
    assert [(m.direction.value, m.content, m.origin) for m in rows] == [
        ("inbound", "¿Tenéis hora el viernes?", "history_import"),
        ("outbound", "Sí, a las 18:00", "history_import"),
        ("inbound", "[image]", "history_import"),
    ]
    assert rows[0].created_at == datetime.fromtimestamp(1750000000, UTC), "con su hora original"
    conversation = await _conversation(db_session, biz, channel_id)
    assert conversation.agent_active is True and conversation.waiting_reason is None, (
        "el historial no despierta al agente ni abre una espera"
    )


# ── contactos ──────────────────────────────────────────────────────────────


async def test_contacts_sync_as_customers_without_overwriting_a_name(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    number = "34911000205"
    _channel_id, pnid = await _coexistence_line(db_session, biz, number)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            Customer(
                tenant_id=biz.tenant_id, identifier="34600999001", name="Ana (VIP)", preferences={}
            )
        )
    await db_session.commit()
    await _post(
        client,
        _envelope(
            "smb_app_state_sync",
            number,
            pnid,
            {
                "state_sync": [
                    {
                        "type": "contact",
                        "action": "add",
                        "contact": {"full_name": "Ana García", "phone_number": "34600999001"},
                    },
                    {
                        "type": "contact",
                        "action": "add",
                        "contact": {"full_name": "Pedro Ruiz", "phone_number": "+34 600 999 002"},
                    },
                    {
                        "type": "contact",
                        "action": "remove",
                        "contact": {"full_name": "Borrado", "phone_number": "34600999003"},
                    },
                ]
            },
        ),
    )
    await drain_once(fake_redis, STATE_SYNC, handle_state_sync, consumer_name="t")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        names = dict(
            (
                await db_session.execute(
                    sa.select(Customer.identifier, Customer.name).where(
                        Customer.identifier.in_(["34600999001", "34600999002", "34600999003"])
                    )
                )
            ).all()
        )
    assert names == {"34600999001": "Ana (VIP)", "34600999002": "Pedro Ruiz"}
