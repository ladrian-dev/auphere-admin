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

from nexus_api.db.models.teammate import TEAMMATE_ACTIVE, TEAMMATE_ARCHIVED, Teammate


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
