"""La consola nueva — spec 047 (requisito 55.2), para todos los partners.

La spec la activaba partner a partner desde el panel de operador (research D38),
con ensayo, activación y vuelta atrás. Desde el 2026-10-29 es la consola de todos
(Andrés): lo que el panel enciende o apaga por partner son los módulos (spec 032).
La 0204 la encendió a los que no la tenían, con lo que hacía activarla (la
audiencia de cada número y su fila de auditoría), y un partner nuevo nace con ella.

La versión sigue saliendo de una sola columna, ``partners.console_v2_enabled_at``,
porque la leen el cobro por bolsas, la puerta de publicar, los canales y el
Panel: con fecha, ``v2``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final, Literal

from nexus_api.db.models import Partner

ConsoleVersion = Literal["v1", "v2"]

ENABLED_ACTION: Final = "partner.console_v2_enabled"
#: Quién encendió la consola nueva a un partner que nace (el alta, no una persona).
BORN_ACTOR: Final = "auphere:alta"


def console_version(partner: Partner) -> ConsoleVersion:
    """La consola que ve el partner: la nueva, que tienen todos desde la 0204."""
    return "v2" if partner.console_v2_enabled_at is not None else "v1"


def born_on_new_console(partner: Partner) -> Partner:
    """Un partner que nace (desde el panel o dándose de alta solo) ya tiene la
    consola nueva: no hay nada que activar después.

    Una hora de Python y no ``now()`` de SQL: con la expresión, el atributo queda
    caducado tras el ``flush`` y leerlo después pide un viaje a la base fuera del
    ``await`` (``MissingGreenlet`` en los scripts de semilla)."""
    partner.console_v2_enabled_at = datetime.now(UTC)
    partner.console_v2_enabled_by = BORN_ACTOR
    return partner


__all__ = [
    "BORN_ACTOR",
    "ENABLED_ACTION",
    "ConsoleVersion",
    "born_on_new_console",
    "console_version",
]
