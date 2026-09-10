"""Presencia del dispositivo — 001-Requisito 4, con la máquina del partner (spec 002).

**No hay columna de estado, y es lo que hace honesta a la pantalla.** Un booleano
almacenado se queda diciendo «conectada» el día que muere el proceso que debía
apagarlo; derivar del último latido cuesta un cálculo por lectura y paga con que
esa mentira sea **imposible**, no improbable.

**La presencia de un tenant pasa por sus vínculos** (spec 002, D14): el cliente X
tiene herramientas locales si alguna máquina del partner está vinculada a X **con
directorio declarado**, late dentro de la ventana y no está archivada. Cerrar
sesión para el latido; la presencia decae en 30 s; las herramientas salen del
catálogo sin ninguna pieza nueva (Requisito 11.1).

Las cadencias siguen la convención de Kubernetes y Consul —latido cada 10 s,
caducidad a los 30— y caben holgadas dentro del minuto que exige CE-004.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.local_workstation import DeviceClientLink, PartnerDevice

HEARTBEAT_INTERVAL = timedelta(seconds=10)
PRESENCE_EXPIRY = timedelta(seconds=30)

Presence = Literal["presente", "ausente"]


def derive_presence(last_heartbeat_at: datetime | None, *, now: datetime | None = None) -> Presence:
    """Deriva la presencia. ``None`` es «nunca se ha conectado», no «ausente hace mucho»."""
    if last_heartbeat_at is None:
        return "ausente"
    reference = now or datetime.now(UTC)
    beat = last_heartbeat_at if last_heartbeat_at.tzinfo else last_heartbeat_at.replace(tzinfo=UTC)
    return "presente" if reference - beat < PRESENCE_EXPIRY else "ausente"


def catalog_includes_local_tools(presence: Presence) -> bool:
    """Sin máquina, las herramientas locales **no están** en el catálogo del turno.

    No están deshabilitadas ni fallan al usarse: no existen. Que el agente no
    pueda ni intentarlo es lo que impide que afirme resultados de comandos que
    nunca ejecutó (001-Requisito 4.2).
    """
    return presence == "presente"


async def tenant_presence(session: AsyncSession, *, now: datetime | None = None) -> Presence:
    """La presencia del tenant en contexto, a través de sus vínculos.

    Corre bajo ``app.tenant_id``: los vínculos los filtra la RLS de tenant y la
    máquina se lee por su id, que la RLS de partner no filtra aquí porque esta
    consulta va con el rol dueño de la transacción tenant-scoped.
    """
    require_current_tenant()
    rows = (
        (
            await session.execute(
                select(PartnerDevice.last_heartbeat_at)
                .join(DeviceClientLink, DeviceClientLink.device_id == PartnerDevice.id)
                .where(
                    DeviceClientLink.removed_at.is_(None),
                    DeviceClientLink.workdir.is_not(None),
                    PartnerDevice.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for beat in rows:
        if derive_presence(beat, now=now) == "presente":
            return "presente"
    return "ausente"


__all__ = [
    "HEARTBEAT_INTERVAL",
    "PRESENCE_EXPIRY",
    "Presence",
    "catalog_includes_local_tools",
    "derive_presence",
    "tenant_presence",
]
