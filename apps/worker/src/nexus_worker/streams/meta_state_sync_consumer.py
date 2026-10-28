"""Los contactos de la app WhatsApp Business — spec 047, T110 (requisito 30.12).

En coexistencia Meta sincroniza la agenda de la app (``smb_app_state_sync``): al
conectar y cada vez que cambia. Cada contacto entra como cliente del negocio con
su nombre; uno que ya existe gana el nombre si no lo tenía, y el que puso una
persona no se pisa. Quitar un contacto en la app no borra nada aquí: el cliente
puede tener conversaciones.

El cuerpo admite las dos formas que se ven: ``state_sync[].contact`` (la de la
documentación, con ``phone_number`` y ``full_name``) y ``contacts[]`` (con
``wa_id`` y ``profile.name``).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any, Final

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

from nexus_worker.persistence.messages import upsert_customer
from nexus_worker.streams.meta_coexistence import digits, run_consumer, tenant_of

log = structlog.get_logger(__name__)

STREAM: Final = "nexus:meta:state_sync"


def contacts_of(value: dict[str, Any]) -> Iterator[tuple[str, str | None]]:
    """``(número, nombre)`` de cada contacto que se añade o cambia."""
    for item in value.get("state_sync") or []:
        if not isinstance(item, dict) or item.get("type", "contact") != "contact":
            continue
        if str(item.get("action") or "add").lower() == "remove":
            continue
        contact = item.get("contact") or {}
        if isinstance(contact, dict):
            name = contact.get("full_name") or contact.get("first_name")
            yield digits(contact.get("phone_number")), (str(name) if name else None)
    for contact in value.get("contacts") or []:
        if isinstance(contact, dict):
            profile = contact.get("profile") or {}
            name = profile.get("name") if isinstance(profile, dict) else None
            yield (
                digits(contact.get("wa_id") or contact.get("phone_number")),
                (str(name) if name else None),
            )


async def handle_state_sync(fields: dict[str, str]) -> str:
    tenant_id = tenant_of(fields)
    value: dict[str, Any] = json.loads(fields.get("raw_value") or "{}") or {}
    synced = 0
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        for phone, name in contacts_of(value):
            if len(phone) < 7:
                continue
            customer = await upsert_customer(session, identifier=phone, name=name)
            if name and not customer.name:
                customer.name = name
            synced += 1
    log.info("coexistence.contacts_synced", tenant_id=str(tenant_id), contacts=synced)
    return f"synced:{synced}"


async def run_meta_state_sync_consumer(
    redis: Any, *, stop: asyncio.Event, consumer_name: str
) -> None:
    await run_consumer(redis, STREAM, handle_state_sync, stop=stop, consumer_name=consumer_name)


__all__ = ["STREAM", "contacts_of", "handle_state_sync", "run_meta_state_sync_consumer"]
