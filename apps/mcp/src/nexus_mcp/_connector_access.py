"""¿Puede este cliente usar la conexión de un conector? — spec 060 (requisito 5.4).

Los cargadores de credenciales (`_load_*_client`) lo comprueban después de
encontrar la conexión viva. Por ellos pasan las herramientas del turno y también
los procesos programados (los recordatorios de cobranza, el sondeo de ventas):
si el partner del cliente perdió el conector, fallan como «sin conexión», que
es lo que esos procesos ya saben saltar.

Un barrido (`apps/api/tests/unit/test_060_sweeps.py`) exige que toda lectura de
`TenantConnector` en `apps/mcp` y `apps/worker` pase por aquí o tenga su razón.
"""

from __future__ import annotations

import uuid

from nexus_api.services.connectors.availability import normalize, unavailable_slugs_for_tenant
from sqlalchemy.ext.asyncio import AsyncSession


async def connection_is_available(session: AsyncSession, tenant_id: uuid.UUID, slug: str) -> bool:
    """``False`` si el conector no está disponible para el partner del cliente.
    Dentro de la sesión del cliente; un fallo de lectura se propaga (cierra)."""
    return normalize(slug) not in await unavailable_slugs_for_tenant(session, tenant_id)


__all__ = ["connection_is_available"]
