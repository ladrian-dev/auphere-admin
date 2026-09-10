"""La política de ejecución local, resuelta — spec 003, Requisito 10.

Tres capas, y **ninguna puede ampliar la de abajo**:

1. **La lista blanca de ejecutables** (001): del cliente, se toca solo desde la
   consola, y un ejecutable ausente no es aprobable en caliente. No está aquí:
   la aplica el gate, antes que nada de esto.
2. **El techo del partner**: lo ponen owner y admin. Ausente = ``ask``.
3. **La preferencia de la persona**: global o por ejecutable, la más específica
   gana entre ellas dos.

Y entre el techo y la preferencia gana **la más restrictiva** — la misma regla
que Grok Bot enuncia como «si ambas coinciden, gana Require Approval», y por la
misma razón: una capa que pudiera relajar a la de arriba dejaría de ser un techo.

``capped`` existe para que la pantalla pueda decir la verdad: «guardaste
*permitir siempre*, pero el techo del partner manda» es una frase distinta de
«prefieres que te pregunten» (Requisito 10.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.local_workstation import (
    EXEC_ALWAYS,
    EXEC_ASK,
    PartnerLocalExecPolicy,
    PrincipalLocalExecPref,
    most_restrictive,
)


def effective_mode(
    *, ceiling: str | None, global_pref: str | None, executable_pref: str | None
) -> str:
    """Lo que de verdad pasa con esta invocación."""
    preference = executable_pref if executable_pref is not None else global_pref
    return most_restrictive(ceiling, preference)


@dataclass(frozen=True)
class ResolvedPolicy:
    mode: str
    #: La preferencia que la persona guardó, aunque el techo la haya bajado.
    preference: str
    ceiling: str
    #: ``True`` cuando el techo bajó lo que la persona pidió.
    capped: bool


def resolve(
    *, ceiling: str | None, global_pref: str | None, executable_pref: str | None
) -> ResolvedPolicy:
    preference = executable_pref if executable_pref is not None else global_pref
    # Lo que la persona no ha decidido se pregunta. Es el defecto seguro y es
    # el que trae Grok Bot: «ask every time».
    preference = preference if preference is not None else EXEC_ASK
    # Un techo **ausente no restringe**. El techo es una restricción que un
    # administrador pone; leerlo como ``ask`` haría que nadie pudiera elegir
    # «permitir siempre» hasta que alguien tocara una pantalla de equipo, y
    # convertiría la ausencia de una decisión en una decisión. El defecto
    # seguro ya lo pone la preferencia: sin restricción y sin preferencia, se
    # pregunta igual.
    roof = ceiling if ceiling is not None else EXEC_ALWAYS
    mode = most_restrictive(roof, preference)
    return ResolvedPolicy(mode=mode, preference=preference, ceiling=roof, capped=mode != preference)


class LocalExecPolicyRepository:
    """Lee y escribe las dos capas. Exige los GUC de partner y persona puestos."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ceiling(self, partner_id: uuid.UUID) -> str | None:
        row = await self._session.get(PartnerLocalExecPolicy, partner_id)
        return row.ceiling if row is not None else None

    async def set_ceiling(self, partner_id: uuid.UUID, *, ceiling: str, by: str) -> str:
        row = await self._session.get(PartnerLocalExecPolicy, partner_id)
        if row is None:
            row = PartnerLocalExecPolicy(partner_id=partner_id, ceiling=ceiling, updated_by=by)
            self._session.add(row)
        else:
            row.ceiling = ceiling
            row.updated_by = by
            row.updated_at = sa.func.now()
        await self._session.flush()
        return ceiling

    async def prefs(self, *, principal_id: str) -> list[PrincipalLocalExecPref]:
        rows = await self._session.execute(
            sa.select(PrincipalLocalExecPref)
            .where(PrincipalLocalExecPref.principal_id == principal_id)
            .order_by(PrincipalLocalExecPref.executable.nulls_first())
        )
        return list(rows.scalars().all())

    async def set_pref(
        self,
        *,
        partner_id: uuid.UUID,
        principal_id: str,
        executable: str | None,
        mode: str,
    ) -> PrincipalLocalExecPref:
        existing = (
            await self._session.execute(
                sa.select(PrincipalLocalExecPref).where(
                    PrincipalLocalExecPref.principal_id == principal_id,
                    PrincipalLocalExecPref.executable.is_(None)
                    if executable is None
                    else PrincipalLocalExecPref.executable == executable,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.mode = mode
            existing.updated_at = sa.func.now()
            await self._session.flush()
            return existing
        row = PrincipalLocalExecPref(
            id=uuid.uuid4(),
            partner_id=partner_id,
            principal_id=principal_id,
            executable=executable,
            mode=mode,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def for_invocation(
        self, *, partner_id: uuid.UUID, principal_id: str, executable: str
    ) -> ResolvedPolicy:
        """Lo que aplica a **esta** invocación, con las tres claves puestas."""
        ceiling = await self.ceiling(partner_id)
        rows = await self.prefs(principal_id=principal_id)
        by_key = {row.executable: row.mode for row in rows}
        return resolve(
            ceiling=ceiling,
            global_pref=by_key.get(None),
            executable_pref=by_key.get(executable),
        )


__all__ = [
    "LocalExecPolicyRepository",
    "ResolvedPolicy",
    "effective_mode",
    "resolve",
]
