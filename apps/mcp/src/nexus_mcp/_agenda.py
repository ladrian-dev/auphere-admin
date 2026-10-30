"""Las dos agendas de un cliente, leídas como una — spec 048 (requisito 4).

Tras «Pasar a Reservas» las citas de un cliente viven en ``reservations`` (las
nuevas y las importadas) y en ``appointments`` (las de antes que no se
importaron). Una cita importada deja su reserva con la clave
``appointment:<id>``: quien lee las dos cuenta la reserva y salta la cita, así
nada se cuenta dos veces. Hasta el borrado final de ``appointments``
(requisito 5) los lectores —el historial y las comisiones— usan esto.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Final

import sqlalchemy as sa
from nexus_api.db.models import Appointment, KGNode, Reservation, ReservationStaff
from nexus_api.services.reservations.passing import IMPORT_KEY, name_key
from sqlalchemy.ext.asyncio import AsyncSession

#: Las reservas que cuentan como hechas o por hacer (sin canceladas ni ausencias).
COUNTED: Final = ("confirmed", "arrived", "done")
#: La etiqueta del nodo del grafo que lleva el modelo de comisión.
BARBER_LABEL: Final = "Barber"


def not_imported() -> sa.ColumnElement[bool]:
    """Una cita de ``appointments`` que ningún paso a Reservas importó."""
    return ~sa.exists().where(
        Reservation.idempotency_key == sa.literal(IMPORT_KEY) + sa.cast(Appointment.id, sa.String)
    )


async def staff_names(
    session: AsyncSession, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(
        sa.select(ReservationStaff.id, ReservationStaff.name).where(ReservationStaff.id.in_(wanted))
    )
    return {sid: str(name) for sid, name in rows.all()}


def _node_name(node: KGNode) -> str:
    props: dict[str, Any] = node.properties or {}
    return str(props.get("name") or "")


async def barbers_by_name(session: AsyncSession) -> dict[str, KGNode]:
    """Los nodos ``Barber`` del cliente por su nombre, para casarlos con la
    persona del equipo de Reservas (sin tildes ni mayúsculas)."""
    rows = await session.execute(sa.select(KGNode).where(KGNode.label == BARBER_LABEL))
    out: dict[str, KGNode] = {}
    for node in rows.scalars():
        key = name_key(_node_name(node))
        if key:
            out.setdefault(key, node)
    return out


async def staff_of_barber(session: AsyncSession, barber: KGNode | None) -> list[uuid.UUID]:
    """Las personas del equipo de Reservas que son ese barbero (por nombre)."""
    if barber is None:
        return []
    key = name_key(_node_name(barber))
    if not key:
        return []
    rows = await session.execute(sa.select(ReservationStaff.id, ReservationStaff.name))
    return [sid for sid, name in rows.all() if name_key(str(name)) == key]


__all__ = [
    "BARBER_LABEL",
    "COUNTED",
    "barbers_by_name",
    "not_imported",
    "staff_names",
    "staff_of_barber",
]
