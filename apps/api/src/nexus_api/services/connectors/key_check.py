"""Comprobar la clave de un conector por clave al conectarlo — spec 061 (requisito 1).

Hasta la 061, ningún conector ``api_key`` comprobaba su clave: la consola decía
«conectado» aunque el proveedor la rechazara, y el primer turno era el que lo
descubría (research D5). Aquí vive un registro ``slug → comprobador``; quien no
tiene comprobador sigue como siempre.

``check`` devuelve:
- ``"ok"``: el proveedor acepta la clave.
- ``"rejected"``: el proveedor la rechaza. ``mark_rejected`` deja la conexión en
  ``needs_reauth`` y marca la credencial.
- ``"unavailable"``: el proveedor no responde. La conexión se queda guardada sin
  comprobar (1.4).
- ``None``: el conector no tiene comprobador.

La clave solo se descifra aquí y viaja al cliente HTTP del proveedor. No se
registra ni se devuelve (1.8).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Connector, TenantConnector, TenantConnectorStatus, TenantCredentials

log = structlog.get_logger(__name__)

Outcome = Literal["ok", "rejected", "unavailable"]
#: ``(secretos, endpoint_meta)``: lo cifrado y lo que el cliente escribió sin cifrar.
Checker = Callable[[dict[str, Any], dict[str, Any]], Awaitable[Outcome]]


async def _check_quedate(secrets: dict[str, Any], meta: dict[str, Any]) -> Outcome:
    """``GET /agent/hosts?per_page=1`` en el entorno elegido (research D3).

    Lo responde cualquier clave de la API del agente, con o sin anfitriones. Un 403
    también es «rechazada»: la clave existe pero no puede usar esa API."""
    from nexus_mcp.servers.quedate.client import QuedateClient, environment_of
    from nexus_mcp.servers.quedate.errors import (
        QuedateAuthError,
        QuedateError,
        QuedateForbidden,
    )

    key = secrets.get("api_key")
    if not isinstance(key, str) or not key.strip():
        return "rejected"
    client = QuedateClient(
        environment=environment_of(meta.get("environment")), token=key.strip(), max_retries=1
    )
    try:
        await client.list_hosts(page=1, per_page=1)
    except (QuedateAuthError, QuedateForbidden):
        return "rejected"
    except QuedateError:
        return "unavailable"
    return "ok"


CHECKERS: dict[str, Checker] = {"quedate": _check_quedate}


async def check(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector: Connector
) -> Outcome | None:
    checker = CHECKERS.get(connector.slug)
    if checker is None or connector.auth_kind != "api_key":
        return None
    cred = await session.scalar(
        sa.select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == connector.slug,
        )
    )
    if cred is None:
        return "rejected"
    try:
        secrets = json.loads(bytes(cred.encrypted_payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "rejected"
    tc = await session.scalar(
        sa.select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id, TenantConnector.connector_id == connector.id
        )
    )
    ref: dict[str, Any] = (tc.credentials_ref if tc is not None else None) or {}
    meta = ref.get("endpoint_meta")
    outcome = await checker(
        secrets if isinstance(secrets, dict) else {}, meta if isinstance(meta, dict) else {}
    )
    log.info("connector.key_check", slug=connector.slug, tenant_id=str(tenant_id), outcome=outcome)
    return outcome


async def mark_rejected(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector: Connector
) -> None:
    """La conexión pasa a ``needs_reauth`` y la credencial queda marcada (1.3)."""
    tc = await session.scalar(
        sa.select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id, TenantConnector.connector_id == connector.id
        )
    )
    if tc is not None:
        tc.status = TenantConnectorStatus.NEEDS_REAUTH.value
    cred = await session.scalar(
        sa.select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == connector.slug,
        )
    )
    if cred is not None:
        cred.needs_reauth = True
    await session.flush()


__all__ = ["CHECKERS", "Outcome", "check", "mark_rejected"]
