"""El historial de la app WhatsApp Business — spec 047, T110 (requisito 30.8).

Al conectar en coexistencia, Meta puede mandar hasta seis meses de chats
(``history``), en trozos y durante horas. Se importa **solo si el negocio lo
aceptó** (``channels.config.history_import``); si no, se descarta y queda en el
log. Al conectar, la consola avisa de lo que se pierde al no aceptarlo.

Cada mensaje entra en la conversación de su contacto con ``origin =
history_import`` y su hora original. No despierta al agente: no pasa por el
despachador. Meta no manda los adjuntos del historial; un mensaje sin texto queda
con su tipo entre corchetes. Un ``wamid`` repetido no se importa dos veces.

El cuerpo admite las dos formas que se ven: ``history[].threads[].messages[]``
(la de la documentación) e ``history[].messages[]`` con el contacto en ``id``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Message, MessageDirection, MessageStatus

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

STREAM: Final = "nexus:meta:history"


def threads_of(value: dict[str, Any]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """``(contacto, mensajes)`` de cada hilo del trozo."""
    for item in value.get("history") or []:
        if not isinstance(item, dict):
            continue
        threads = item.get("threads")
        if isinstance(threads, list):
            for thread in threads:
                if isinstance(thread, dict):
                    msgs = thread.get("messages")
                    yield digits(thread.get("id")), [m for m in msgs or [] if isinstance(m, dict)]
        elif isinstance(item.get("messages"), list):
            yield digits(item.get("id")), [m for m in item["messages"] if isinstance(m, dict)]


def _text(msg: dict[str, Any]) -> str:
    body = msg.get("text")
    if isinstance(body, dict) and body.get("body"):
        return str(body["body"])
    return f"[{msg.get('type') or 'mensaje'}]"


async def handle_history(fields: dict[str, str]) -> str:
    tenant_id = tenant_of(fields)
    if fields.get("error_code"):
        # El negocio no compartió el historial, o Meta no pudo mandarlo.
        log.info(
            "coexistence.history_unavailable",
            tenant_id=str(tenant_id),
            error_code=fields["error_code"],
        )
        return "unavailable"
    value: dict[str, Any] = json.loads(fields.get("raw_value") or "{}") or {}
    imported = 0
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        channel = await find_channel(session, phone_number_id=fields.get("phone_number_id"))
        if channel is None:
            return "no_channel"
        if (channel.config or {}).get("history_import") is not True:
            log.info(
                "coexistence.history_not_accepted",
                tenant_id=str(tenant_id),
                channel_id=str(channel.id),
            )
            return "not_accepted"
        for contact, messages in threads_of(value):
            if not contact or not messages:
                continue
            customer = await upsert_customer(session, identifier=contact, **identity_of(contact))
            conversation = await upsert_conversation_for_customer(
                session, channel_id=channel.id, customer_id=customer.id, reopened_by="history"
            )
            wamids = [str(m.get("id")) for m in messages if m.get("id")]
            seen = set(
                (
                    await session.scalars(
                        sa.select(Message.provider_message_id).where(
                            Message.provider_message_id.in_(wamids)
                        )
                    )
                ).all()
            )
            for msg in messages:
                wamid = str(msg.get("id") or "")
                if not wamid or wamid in seen:
                    continue
                seen.add(wamid)
                inbound = digits(msg.get("from")) == contact
                session.add(
                    Message(
                        tenant_id=tenant_id,
                        conversation_id=conversation.id,
                        direction=MessageDirection.INBOUND
                        if inbound
                        else MessageDirection.OUTBOUND,
                        status=MessageStatus.SENT,
                        content=_text(msg),
                        tool_calls=[],
                        provider_message_id=wamid,
                        origin="history_import",
                        created_at=parse_ts(msg.get("timestamp")) or datetime.now(UTC),
                    )
                )
                imported += 1
    log.info("coexistence.history_imported", tenant_id=str(tenant_id), messages=imported)
    return f"imported:{imported}"


async def run_meta_history_consumer(redis: Any, *, stop: asyncio.Event, consumer_name: str) -> None:
    await run_consumer(redis, STREAM, handle_history, stop=stop, consumer_name=consumer_name)


__all__ = ["STREAM", "handle_history", "run_meta_history_consumer", "threads_of"]
