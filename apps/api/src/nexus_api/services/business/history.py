"""El historial de la ficha y el deshacer — spec 047, T069 (requisitos 13.3 y 13.4).

Cada escritura deja una fila en ``business_changes`` con ``before`` y ``after``
(la vista de la sección en el ClientSpec), su autor y su origen
(``writes.write_section``). Aquí:

- :func:`list_history`: los cambios, del más nuevo al más viejo, por sección o
  de toda la ficha, y si cada uno se puede deshacer;
- :func:`undo`: deshacer **el último** cambio de una sección. Aplica su
  ``before`` por el servicio de la sección (su adaptador de ``restore``), con
  ``kind="undo"`` y ``undo_of``, y marca el cambio como deshecho. Si alguien
  escribió la sección después, ``SectionRevisionConflict`` con lo que cambió: la
  ruta responde ``412`` y nadie pisa a nadie.

Un cambio sin ``before`` (lo primero que leyó la web, por ejemplo) no se puede
deshacer salvo el de las redes que la lectura añadió, que se deshace quitándolas.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import SECTIONS, BusinessChange
from nexus_api.services.business import client_spec
from nexus_api.services.business.writes import (
    NothingWritten,
    SectionRevisionConflict,
    SectionWritten,
    WriteContext,
    change_out,
    current_revision,
    section_adapter,
)


class AlreadyUndone(Exception):
    """Ese cambio ya se deshizo."""


class UndoNotAvailable(Exception):
    """Ese cambio no se puede deshacer (sin ``before``, o su sección aún no sabe)."""


@dataclass(frozen=True)
class ChangeView:
    row: BusinessChange
    undoable: bool


async def _latest(session: AsyncSession, section: str) -> BusinessChange | None:
    row: BusinessChange | None = await session.scalar(
        sa.select(BusinessChange)
        .where(
            BusinessChange.tenant_id == require_current_tenant(),
            BusinessChange.section == section,
        )
        .order_by(BusinessChange.at.desc(), BusinessChange.id.desc())
        .limit(1)
    )
    return row


def _target(
    row: BusinessChange, current_links: list[dict[str, Any]] | None
) -> Mapping[str, Any] | None:
    """La vista a la que volver. ``None`` si no hay a dónde."""
    if row.before is not None:
        return row.before
    after = row.after or {}
    if (
        row.section == "links"
        and isinstance(after.get("added"), list)
        and current_links is not None
    ):
        added = {
            (a.get("network"), (a.get("handle") or a.get("url") or "").lower())
            for a in after["added"]
        }
        keep = [
            link
            for link in current_links
            if (link.get("network"), (link.get("handle") or link.get("url") or "").lower())
            not in added
        ]
        return {"links": keep}
    return None


def _can_undo(row: BusinessChange, *, latest: bool) -> bool:
    if not latest or row.undone_at is not None or row.kind == "migration":
        return False
    if row.before is not None:
        return True
    after = row.after or {}
    return row.section == "links" and isinstance(after.get("added"), list)


async def list_history(
    session: AsyncSession, *, section: str | None = None, limit: int = 50
) -> list[ChangeView]:
    """Los cambios, del más nuevo al más viejo."""
    if section is not None and section not in SECTIONS:
        raise ValueError(f"unknown section: {section!r}")
    tenant_id = require_current_tenant()
    stmt = sa.select(BusinessChange).where(BusinessChange.tenant_id == tenant_id)
    if section is not None:
        stmt = stmt.where(BusinessChange.section == section)
    rows = (
        await session.scalars(
            stmt.order_by(BusinessChange.at.desc(), BusinessChange.id.desc()).limit(limit)
        )
    ).all()
    latest: dict[str, uuid.UUID] = {}
    for s in {r.section for r in rows}:
        last = await _latest(session, s)
        if last is not None:
            latest[s] = last.id
    return [
        ChangeView(row=r, undoable=_can_undo(r, latest=latest.get(r.section) == r.id)) for r in rows
    ]


async def undo(
    session: AsyncSession, change_id: uuid.UUID, *, ctx: WriteContext
) -> SectionWritten | None:
    """Deshace el cambio ``change_id`` (ver el módulo). ``None`` si deshacerlo
    no cambiaba nada (ya estaba así): el cambio queda marcado igual."""
    tenant_id = require_current_tenant()
    row = await session.scalar(
        sa.select(BusinessChange)
        .where(BusinessChange.tenant_id == tenant_id, BusinessChange.id == change_id)
        .with_for_update()
    )
    if row is None:
        raise LookupError("unknown change")
    if row.undone_at is not None:
        raise AlreadyUndone
    latest = await _latest(session, row.section)
    if latest is not None and latest.id != row.id:
        later = (
            await session.scalars(
                sa.select(BusinessChange)
                .where(
                    BusinessChange.tenant_id == tenant_id,
                    BusinessChange.section == row.section,
                    sa.or_(
                        BusinessChange.at > row.at,
                        sa.and_(BusinessChange.at == row.at, BusinessChange.id > row.id),
                    ),
                )
                .order_by(BusinessChange.at, BusinessChange.id)
            )
        ).all()
        raise SectionRevisionConflict(
            section=row.section,
            current=await current_revision(session, row.section),
            changes=[change_out(r) for r in later if r.id != row.id],
        )
    adapter = section_adapter(row.section)
    if adapter is None or adapter.restore is None or row.kind == "migration":
        raise UndoNotAvailable
    links = (
        (await client_spec.section_view(session, "links"))["links"]
        if row.section == "links"
        else None
    )
    target = _target(row, links)
    if target is None:
        raise UndoNotAvailable
    undo_ctx = WriteContext(
        actor=ctx.actor,
        source=ctx.source,
        kind="undo",
        review="confirmed",
        audit_actor=ctx.audit_actor,
        undo_of=row.id,
    )
    try:
        written: SectionWritten | None = await adapter.restore(session, target, undo_ctx)
    except NothingWritten:
        written = None
    row.undone_at = datetime.now(UTC)
    row.undone_by = ctx.actor.id
    await session.flush()
    return written


__all__ = [
    "AlreadyUndone",
    "ChangeView",
    "UndoNotAvailable",
    "list_history",
    "undo",
]
