"""Presencia del dispositivo — Requisito 4.

**No hay columna de estado, y es lo que hace honesta a la pantalla.** Un booleano
almacenado se queda diciendo «conectada» el día que muere el proceso que debía
apagarlo; derivar del último latido cuesta un cálculo por lectura y paga con que
esa mentira sea **imposible**, no improbable. §V no pide que la pantalla acierte
casi siempre.

Las cadencias siguen la convención de Kubernetes y Consul —latido cada 10 s,
caducidad a los 30— y caben holgadas dentro del minuto que exige CE-004. Los 30
dejan margen para perder dos latidos: con uno solo, una red con hipo se vería como
una máquina que se va.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

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
    nunca ejecutó (Requisito 4.2).
    """
    return presence == "presente"


__all__ = [
    "HEARTBEAT_INTERVAL",
    "PRESENCE_EXPIRY",
    "Presence",
    "catalog_includes_local_tools",
    "derive_presence",
]
