"""Los ecos de la app WhatsApp Business — spec 047, T110 (requisito 30.11).

En coexistencia el negocio sigue escribiendo desde su app. Meta nos manda cada
mensaje que sale de ella (``smb_message_echoes``). Aquí:

- se guarda en la conversación del contacto como mensaje **de una persona del
  negocio** (``origin = business_app_echo``), ya enviado: el despachador de salida
  no lo vuelve a mandar;
- la conversación pasa a «La lleva una persona» durante **2 horas** desde el último
  eco (``takeover_until``): el agente calla para no pisar a quien está
  contestando. Pasado el plazo, el siguiente mensaje del contacto lo atiende el
  agente otra vez (el despachador lo devuelve).

Un eco repetido (mismo ``wamid``) no se guarda dos veces.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Message, MessageDirection, MessageStatus
from nexus_api.services import conversation_control

from nexus_worker.persistence.messages import (
    identity_of,
    upsert_conversation_for_customer,
    upsert_customer,
)
from nexus_worker.streams.meta_coexistence import (
    digits,
    find_channel,
    parse_ts,
    run_consumer,
    tenant_of,
)

log = structlog.get_logger(__name__)

STREAM: Final = "nexus:meta:echoes"
#: Cuánto dura el relevo de una persona que escribió desde la app (D12).
TAKEOVER: Final = timedelta(hours=2)
#: Quién figura en ``takeover_context`` (lo lee el aviso al agente al volver).
BUSINESS_APP: Final = "business_app"


async def handle_echo(fields: dict[str, str]) -> str:
    wamid = fields.get("provider_message_id") or ""
    recipient = digits(fields.get("recipient_identifier"))
    if not wamid or not recipient:
        return "ignored"
    tenant_id = tenant_of(fields)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        if await session.scalar(
            sa.select(Message.id).where(Message.provider_message_id == wamid).limit(1)
        ):
            return "duplicate"
        channel = await find_channel(
            session,
            phone_number_id=fields.get("phone_number_id"),
            business_phone=fields.get("sender_identifier"),
        )
        if channel is None:
            return "no_channel"
        customer = await upsert_customer(session, identifier=recipient, **identity_of(recipient))
        conversation = await upsert_conversation_for_customer(
            session, channel_id=channel.id, customer_id=customer.id, reopened_by=BUSINESS_APP
        )
        sent_at = parse_ts(fields.get("received_at")) or datetime.now(UTC)
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.SENT,
                content=fields.get("text") or "",
                tool_calls=[],
                provider_message_id=wamid,
                origin="business_app_echo",
                created_at=sent_at,
            )
        )
        until = datetime.now(UTC) + TAKEOVER
        if conversation.agent_active:
            conversation_control.pause(
                conversation, reason="business_app_echo", notes=None, operator_label=BUSINESS_APP
            )
            conversation.waiting_reason = "human_takeover"
            conversation.takeover_until = until
        elif conversation.takeover_until is not None:
            # Ya la llevaba alguien desde la app: el plazo cuenta desde el último eco.
            # Si la tomó una persona desde la Bandeja (sin plazo), sigue sin plazo.
            conversation.takeover_until = max(conversation.takeover_until, until)
        if conversation.last_message_at is None or sent_at > conversation.last_message_at:
            conversation.last_message_at = sent_at
    log.info("coexistence.echo_saved", tenant_id=str(tenant_id), wamid=wamid)
    return "saved"


async def run_meta_echoes_consumer(redis: Any, *, stop: asyncio.Event, consumer_name: str) -> None:
    await run_consumer(redis, STREAM, handle_echo, stop=stop, consumer_name=consumer_name)


__all__ = ["STREAM", "TAKEOVER", "handle_echo", "run_meta_echoes_consumer"]
