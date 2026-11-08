"""El calendario de un profesional, ya conectado: lo que deja la autorización (spec 043,
requisito 12). Las pruebas del camino de autorizar están en
``test_calendario_por_profesional.py``."""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker


async def connected(
    tenant_id: uuid.UUID,
    staff_id: uuid.UUID,
    *,
    calendar_id: str | None = None,
    name: str | None = None,
    status: str = "connected",
    account: str | None = None,
) -> None:
    """Una fila como la deja una autorización terminada, con su propia conexión."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(
                "INSERT INTO reservation_staff_calendars (tenant_id, staff_id, calendar_id, "
                "calendar_name, connection_id, connection_user_id, connection_status, "
                "account_label) VALUES (:t, :s, :c, :n, :ca, :u, :st, :a)"
            ),
            {
                "t": tenant_id,
                "s": staff_id,
                "c": calendar_id,
                "n": name or calendar_id,
                "ca": f"ca_{staff_id}",
                "u": f"tenant_x_staff_{staff_id}",
                "st": status,
                "a": account,
            },
        )


async def set_state(tenant_id: uuid.UUID, staff_id: uuid.UUID, **values: object) -> None:
    sm = get_sessionmaker()
    fields = ", ".join(f"{k} = :{k}" for k in values)
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(f"UPDATE reservation_staff_calendars SET {fields} WHERE staff_id = :s"),
            {"s": staff_id, **values},
        )


__all__ = ["connected", "set_state"]
