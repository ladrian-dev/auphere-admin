"""El roster de teammates, bajo la RLS de partner (spec 003, Requisitos 1 y 2).

Todo método exige que la transacción lleve ``app.partner_id`` puesto
(``apply_partner_to_session``): sin él la tabla no devuelve filas, y eso es
lo que se quiere. **No hay ``delete``** — y no es un olvido: la base revoca
``DELETE`` a ``nexus_app`` y ``test_31`` lo afirma.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.teammate import (
    CHANGED_FIELDS,
    TEAMMATE_ACTIVE,
    TEAMMATE_ARCHIVED,
    Teammate,
    TeammateChange,
)


class TeammateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, *, include_archived: bool = False) -> Sequence[Teammate]:
        stmt = select(Teammate).order_by(Teammate.created_at)
        if not include_archived:
            stmt = stmt.where(Teammate.status == TEAMMATE_ACTIVE)
        return (await self._session.execute(stmt)).scalars().all()

    async def get(self, teammate_id: uuid.UUID) -> Teammate | None:
        return await self._session.get(Teammate, teammate_id)

    async def get_active(self, teammate_id: uuid.UUID) -> Teammate | None:
        row = await self.get(teammate_id)
        return row if row is not None and row.is_active else None

    async def create(
        self,
        *,
        partner_id: uuid.UUID,
        name: str,
        job: str,
        model: str,
        tool_names: list[str],
        permissions: dict[str, Any],
        local_exec: bool,
        created_by: str,
    ) -> Teammate:
        row = Teammate(
            id=uuid.uuid4(),
            partner_id=partner_id,
            name=name,
            job=job,
            model=model,
            tool_names=list(tool_names),
            permissions=dict(permissions),
            local_exec=local_exec,
            status=TEAMMATE_ACTIVE,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(self, teammate: Teammate, **changes: Any) -> Teammate:
        for key, value in changes.items():
            setattr(teammate, key, value)
        teammate.updated_at = datetime.now(UTC)
        await self._session.flush()
        return teammate

    async def archive(self, teammate: Teammate) -> Teammate:
        """Archivar, nunca borrar (R2.6). Idempotente."""
        if teammate.status != TEAMMATE_ARCHIVED:
            teammate.status = TEAMMATE_ARCHIVED
            teammate.archived_at = datetime.now(UTC)
            teammate.updated_at = teammate.archived_at
            await self._session.flush()
        return teammate


class TeammateChangeRepository:
    """El registro de «este teammate cambió» (R2.4, migración 0113).

    Se lee bajo ``app.partner_id``: cualquier miembro ve los cambios de los
    teammates de su partner, que es exactamente lo que hace falta para que el
    hilo de **cada** persona pinte la nota sin que nadie escriba en el hilo de
    nadie. Solo hay ``add`` y ``for_teammate``: una nota es un hecho ocurrido y
    la base revoca ``UPDATE`` y ``DELETE``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        partner_id: uuid.UUID,
        teammate_id: uuid.UUID,
        fields: Sequence[str],
        changed_by: str,
        changed_by_label: str | None = None,
    ) -> TeammateChange | None:
        """Deja la nota, o ninguna si no cambió nada que se note.

        Devolver ``None`` en vez de escribir una fila vacía no es un detalle:
        una nota que dice «cambió» sin que cambiase nada que el teammate pueda
        hacer es una pantalla que miente en pequeño.
        """
        worth = [f for f in fields if f in CHANGED_FIELDS]
        if not worth:
            return None
        row = TeammateChange(
            id=uuid.uuid4(),
            partner_id=partner_id,
            teammate_id=teammate_id,
            fields=sorted(worth),
            changed_by=changed_by,
            changed_by_label=changed_by_label,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def for_teammate(self, teammate_id: uuid.UUID) -> Sequence[TeammateChange]:
        """Del más viejo al más nuevo: el hilo las intercala por hora."""
        stmt = (
            select(TeammateChange)
            .where(TeammateChange.teammate_id == teammate_id)
            .order_by(TeammateChange.changed_at)
        )
        return (await self._session.execute(stmt)).scalars().all()
