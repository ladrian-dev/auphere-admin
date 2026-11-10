"""Servicios y personas por nombre — fallo ``la-reserva-del-turno-siguiente-pierde-los-ids``.

Por WhatsApp se reserva en varios mensajes, y entre turnos el agente solo conserva
el texto: los ids que dio ``reservas.services`` o ``reservas.find_slots`` en un
turno ya no están en el siguiente. Lo que sí tiene es lo que dijo el cliente
(«un corte con Lucía»), así que las herramientas aceptan el nombre.

Aquí solo se compara texto, sin base ni negocio: lo usan la herramienta de verdad
(``tools.py``, contra lo que el agente del turno ofrece) y la agenda simulada del
Playground (``nexus_worker.simulation``), que así eligen igual.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

#: Lo que la herramienta devuelve cuando un nombre o un id no se resuelve.
UNKNOWN_SERVICE = "unknown_service"
UNKNOWN_STAFF = "unknown_staff"
AMBIGUOUS_SERVICE = "ambiguous_service"
AMBIGUOUS_STAFF = "ambiguous_staff"


def fold(text: str) -> str:
    """Sin mayúsculas, sin acentos y sin espacios de más: «  LUCÍA » es ``lucia``."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.split())


def matches(wanted: str, items: Sequence[T], name: Callable[[T], str]) -> list[T]:
    """Los de ``items`` que nombra ``wanted``, por orden de confianza: el nombre
    igual; si no hay, los que empiezan por él; si no, los que lo contienen. Uno es
    ese; varios, un empate que decide el cliente; ninguno, un nombre que no está."""
    key = fold(wanted)
    if not key:
        return []
    folded = [(item, fold(name(item))) for item in items]
    for hit in (
        lambda n: n == key,
        lambda n: n.startswith(key),
        lambda n: key in n,
    ):
        found = [item for item, n in folded if hit(n)]
        if found:
            return found
    return []


__all__ = [
    "AMBIGUOUS_SERVICE",
    "AMBIGUOUS_STAFF",
    "UNKNOWN_SERVICE",
    "UNKNOWN_STAFF",
    "fold",
    "matches",
]
