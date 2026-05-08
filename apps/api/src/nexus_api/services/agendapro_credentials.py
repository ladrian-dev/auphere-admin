"""Servicio para leer/escribir las credenciales AgendaPro de un tenant.

Las credenciales viven en ``tenant_credentials`` con ``integration='agendapro'``.
``encrypted_payload`` es un blob Fernet-encriptado cuyo plaintext es JSON:

    {
      "login": "...",
      "password": "...",
      "context_id": "<browserbase-context-id>",
      "business_url": "https://..." | null
    }

El ``FernetEncrypted`` TypeDecorator (en ``nexus_api.db.types``) ya
maneja encrypt/decrypt al persistir/leer la columna. Esta capa solo
sabe del shape JSON adentro.

Bloque E uso:
- Endpoint admin ``/integrations/agendapro/bootstrap`` escribe la fila.
- Booking facade ``CreateAppointment.run`` lee el payload para obtener
  ``context_id`` antes de delegar al server subprocess.
- Endpoint ``/integrations/agendapro/health-check`` lee + actualiza
  ``last_health_check_at`` + flippea ``needs_reauth`` si re-login falla.

Las consultas se hacen con la sesión RLS-scoped — no se acepta
``tenant_id`` como parámetro.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import TenantCredentials

INTEGRATION_NAME = "agendapro"


@dataclass(frozen=True)
class AgendaProCredentials:
    login: str
    password: str
    context_id: str
    business_url: str | None
    needs_reauth: bool
    last_health_check_at: datetime | None


def _serialize(*, login: str, password: str, context_id: str, business_url: str | None) -> bytes:
    payload = {
        "login": login,
        "password": password,
        "context_id": context_id,
        "business_url": business_url,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _deserialize(raw: bytes) -> dict[str, Any]:
    parsed: Any = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"agendapro credentials payload is not an object: {parsed!r}")
    return parsed


async def get_agendapro_credentials(
    session: AsyncSession,
) -> AgendaProCredentials | None:
    """Lee + decrypt. Retorna None si no hay row para este tenant.

    Lo invoca: booking-server (antes de cada delegate), endpoint
    /health-check, endpoint /bootstrap (para detectar update vs insert).
    """
    require_current_tenant()  # garantiza contexto activo
    stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_NAME)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    payload = _deserialize(row.encrypted_payload)
    return AgendaProCredentials(
        login=payload["login"],
        password=payload["password"],
        context_id=payload["context_id"],
        business_url=payload.get("business_url"),
        needs_reauth=row.needs_reauth,
        last_health_check_at=row.last_health_check_at,
    )


async def upsert_agendapro_credentials(
    session: AsyncSession,
    *,
    login: str,
    password: str,
    context_id: str,
    business_url: str | None = None,
) -> uuid.UUID:
    """Insert-or-update la fila de credenciales. Resetea ``needs_reauth=False``
    porque un bootstrap nuevo o re-bootstrap cuenta como "ahora todo está OK".
    """
    tenant_id = require_current_tenant()
    raw = _serialize(
        login=login,
        password=password,
        context_id=context_id,
        business_url=business_url,
    )
    stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_NAME)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = TenantCredentials(
            tenant_id=tenant_id,
            integration=INTEGRATION_NAME,
            encrypted_payload=raw,
            needs_reauth=False,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
    else:
        row.encrypted_payload = raw
        row.needs_reauth = False
        await session.flush()
    return row.id


async def update_agendapro_context_id(
    session: AsyncSession,
    *,
    new_context_id: str,
) -> None:
    """Después de re-login auto, persiste el context_id nuevo sin tocar
    login/password/business_url. Resetea ``needs_reauth=False``."""
    require_current_tenant()
    stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_NAME)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    payload = _deserialize(row.encrypted_payload)
    payload["context_id"] = new_context_id
    row.encrypted_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    row.needs_reauth = False
    await session.flush()


async def mark_agendapro_health_check(
    session: AsyncSession,
    *,
    needs_reauth: bool,
    checked_at: datetime,
) -> None:
    """Actualiza ``last_health_check_at`` y opcionalmente flippea
    ``needs_reauth``."""
    require_current_tenant()
    stmt = select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_NAME)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.last_health_check_at = checked_at
    row.needs_reauth = needs_reauth
    await session.flush()
