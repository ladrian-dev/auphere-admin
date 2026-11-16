"""La conexión del negocio y el anfitrión de la persona del turno (spec 061, enmienda
del 2026-11-16).

- ``require_connection`` devuelve la clave del cliente y su entorno (``Connection``).
  Comprueba que el negocio tiene Quédate conectado y que su partner puede usarlo
  (spec 060). Lo llaman las 27 herramientas: todas fallan cerrado. La clave solo
  existe dentro de ``Connection`` y del cliente HTTP.
- ``load``, ``save``, ``mark_review`` y ``save_state`` manejan el **vínculo** de un
  cliente final con su anfitrión. No hay credencial por persona: el vínculo guarda
  el id del anfitrión.
- ``linked_to_other`` dice si un anfitrión ya es de otra persona del negocio.
- ``lock`` ordena las escrituras de una misma persona.
- ``customer_phone`` da el teléfono del cliente final, para el alta (3.2).

``set_test_store`` deja a las pruebas unitarias sustituir la base de datos. La
persona la pasa la herramienta desde ``current_customer_or_refuse``, nunca un
argumento del modelo (garantía 8).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelType,
    Connector,
    Conversation,
    Customer,
    CustomerConnectorAccount,
    TenantConnector,
    TenantConnectorStatus,
    TenantCredentials,
)
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nexus_mcp._connector_access import connection_is_available
from nexus_mcp.base import ToolError
from nexus_mcp.servers.quedate.client import Environment, environment_of

log = structlog.get_logger(__name__)

SLUG = "quedate"


class QuedateNotConfigured(ToolError):
    """El negocio no tiene Quédate conectado, o su partner no puede usarlo."""


@dataclass(frozen=True)
class Connection:
    """La conexión del negocio. ``token`` no sale de aquí ni del cliente HTTP."""

    environment: Environment
    token: str = field(repr=False)


@dataclass
class Link:
    """El anfitrión vinculado a la persona del turno."""

    host_id: str
    state: dict[str, Any] = field(default_factory=dict)
    needs_review: bool = False


class AccountStore(Protocol):
    async def require_connection(self, tenant_id: uuid.UUID) -> Connection: ...

    async def load(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Link | None: ...

    async def save(self, tenant_id: uuid.UUID, customer_id: uuid.UUID, *, host_id: str) -> None: ...

    async def linked_to_other(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, host_id: str
    ) -> bool: ...

    async def mark_review(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None: ...

    async def save_state(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, state: dict[str, Any]
    ) -> None: ...

    async def audit(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        action: str,
        operation: str | None = None,
    ) -> None: ...

    async def customer_phone(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> str | None: ...

    def lock(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Any: ...


def _lock_key(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> int:
    digest = hashlib.blake2b(f"{tenant_id}:{customer_id}:{SLUG}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _where(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> tuple[Any, ...]:
    return (
        CustomerConnectorAccount.tenant_id == tenant_id,
        CustomerConnectorAccount.customer_id == customer_id,
        CustomerConnectorAccount.connector_slug == SLUG,
    )


class _DbStore:
    """La implementación de verdad: tablas de tenant bajo su RLS."""

    async def require_connection(self, tenant_id: uuid.UUID) -> Connection:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            row = (
                await session.execute(
                    select(TenantConnector)
                    .join(Connector, Connector.id == TenantConnector.connector_id)
                    .where(
                        TenantConnector.tenant_id == tenant_id,
                        Connector.slug == SLUG,
                        TenantConnector.status.in_(
                            [
                                TenantConnectorStatus.CONNECTED.value,
                                TenantConnectorStatus.PARTIAL.value,
                            ]
                        ),
                    )
                )
            ).first()
            if row is None:
                raise QuedateNotConfigured("Quédate no está conectado para este negocio.")
            # Spec 060 (5.4): si el partner del cliente perdió el conector, «sin conexión».
            if not await connection_is_available(session, tenant_id, SLUG):
                raise QuedateNotConfigured("Quédate no está disponible para este negocio.")
            tc: TenantConnector = row[0]
            ref: dict[str, Any] = tc.credentials_ref or {}
            environment = environment_of((ref.get("endpoint_meta") or {}).get("environment"))
            cred = await session.scalar(
                select(TenantCredentials).where(
                    TenantCredentials.tenant_id == tenant_id,
                    TenantCredentials.integration == SLUG,
                )
            )
            try:
                payload = json.loads(bytes(cred.encrypted_payload).decode("utf-8")) if cred else {}
            except (ValueError, UnicodeDecodeError):
                payload = {}
            token = payload.get("api_key") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token.strip():
                raise QuedateNotConfigured("La conexión de Quédate no tiene clave.")
            return Connection(environment=environment, token=token.strip())

    async def load(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Link | None:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            row = await session.scalar(
                select(CustomerConnectorAccount).where(*_where(tenant_id, customer_id))
            )
            if row is None:
                return None
            return Link(
                host_id=row.external_user_id,
                state=dict(row.state or {}),
                needs_review=row.needs_review,
            )

    async def save(self, tenant_id: uuid.UUID, customer_id: uuid.UUID, *, host_id: str) -> None:
        """Vincula o sustituye, y lo audita, en una transacción propia."""
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            stmt = pg_insert(CustomerConnectorAccount).values(
                tenant_id=tenant_id,
                customer_id=customer_id,
                connector_slug=SLUG,
                external_user_id=host_id,
                state={},
                needs_review=False,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_customer_connector_accounts",
                set_={
                    "external_user_id": stmt.excluded.external_user_id,
                    "state": stmt.excluded.state,
                    "needs_review": False,
                    "updated_at": text("now()"),
                },
            )
            await session.execute(stmt)
            session.add(_audit_row(tenant_id, customer_id, "connector.customer_account_linked"))
            await session.commit()

    async def linked_to_other(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, host_id: str
    ) -> bool:
        """¿Ese anfitrión ya es de otra persona del negocio? (/cso del 2026-11-16)."""
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            other = await session.scalar(
                select(CustomerConnectorAccount.id).where(
                    CustomerConnectorAccount.tenant_id == tenant_id,
                    CustomerConnectorAccount.connector_slug == SLUG,
                    CustomerConnectorAccount.external_user_id == host_id,
                    CustomerConnectorAccount.customer_id != customer_id,
                )
            )
            return other is not None

    async def mark_review(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await session.execute(
                update(CustomerConnectorAccount)
                .where(*_where(tenant_id, customer_id))
                .values(needs_review=True, updated_at=text("now()"))
            )
            await session.commit()

    async def save_state(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, state: dict[str, Any]
    ) -> None:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await session.execute(
                update(CustomerConnectorAccount)
                .where(*_where(tenant_id, customer_id))
                .values(state=state, updated_at=text("now()"))
            )
            await session.commit()

    async def audit(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        action: str,
        operation: str | None = None,
    ) -> None:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            session.add(_audit_row(tenant_id, customer_id, action, operation))
            await session.commit()

    async def customer_phone(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> str | None:
        """El teléfono del canal: ``phone`` si Meta lo dio; si no, ``identifier``, que
        solo es un teléfono en WhatsApp (en Instagram y Messenger es el id de Meta, y
        puede ser un BSUID). Nunca lo escribe la persona."""
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            c = await session.get(Customer, customer_id)
            if c is None:
                return None
            raw = c.phone
            if not raw and (c.identifier or "").isdigit():
                on_whatsapp = await session.scalar(
                    select(Conversation.id)
                    .join(Channel, Channel.id == Conversation.channel_id)
                    .where(
                        Conversation.customer_id == customer_id,
                        Channel.type == ChannelType.WHATSAPP,
                    )
                    .limit(1)
                )
                raw = c.identifier if on_whatsapp is not None else None
            digits = "".join(ch for ch in (raw or "") if ch.isdigit())
            return f"+{digits}" if len(digits) >= 7 else None

    @asynccontextmanager
    async def lock(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> AsyncIterator[None]:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _lock_key(tenant_id, customer_id)}
            )
            yield


def _audit_row(
    tenant_id: uuid.UUID, customer_id: uuid.UUID, action: str, operation: str | None = None
) -> AuditLog:
    """Sin nombre, correo, documento, ids externos ni clave (6.4)."""
    after: dict[str, Any] = {"customer_id": str(customer_id)}
    if operation:
        after["operation"] = operation
    return AuditLog(
        tenant_id=tenant_id,
        actor=f"customer:{customer_id}",
        action=action,
        target=f"connector:{SLUG}",
        after_json=after,
    )


_store_override: AccountStore | None = None


def set_test_store(store: AccountStore | None) -> None:
    """Sustituye la base de datos. Solo pruebas."""
    global _store_override
    _store_override = store


def store() -> AccountStore:
    return _store_override if _store_override is not None else _DbStore()


__all__ = [
    "SLUG",
    "AccountStore",
    "Connection",
    "Link",
    "QuedateNotConfigured",
    "set_test_store",
    "store",
]
