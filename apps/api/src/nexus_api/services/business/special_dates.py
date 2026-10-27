"""Las fechas especiales — spec 047, T057 (requisito 10.3).

Un cierre o un horario distinto, para una fecha o un rango, con un nombre
opcional («Navidad»), del negocio entero o de una sede. Lo valida el motor
(``hours.SpecialDay``): un rango que termina antes de empezar, una fecha
abierta sin turnos o una cerrada con ellos no se guardan. Manda desde la
apertura del turno de ese día (casos límite), y la usan por igual el agente,
«¿abierto ahora?» y los huecos de Reservas.

Archivar es borrar: la fila se queda con ``archived_at``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import (
    BusinessLocation,
    BusinessSpecialDate,
    BusinessSpecialShift,
)
from nexus_api.services.business import hours, section_write, writes
from nexus_api.services.business.sections import Actor

#: Como mucho (``client-spec.schema.json``).
MAX_SPECIAL_DATES: Final = 200


async def list_special_dates(
    session: AsyncSession, *, archived: bool = False
) -> list[tuple[BusinessSpecialDate, hours.SpecialDay | None]]:
    """Todas las del cliente (del negocio y de cada sede), por fecha."""
    tenant_id = require_current_tenant()
    stmt = sa.select(BusinessSpecialDate).where(BusinessSpecialDate.tenant_id == tenant_id)
    if not archived:
        stmt = stmt.where(BusinessSpecialDate.archived_at.is_(None))
    rows = list(
        (
            await session.scalars(
                stmt.order_by(BusinessSpecialDate.date_from, BusinessSpecialDate.created_at)
            )
        ).all()
    )
    parsed = {sp.id: sp for sp in await hours.specials_of(session, rows, tenant_id=tenant_id)}
    return [(row, parsed.get(row.id)) for row in rows]


async def _location(session: AsyncSession, location_id: uuid.UUID | None) -> None:
    if location_id is None:
        return
    loc = await session.get(BusinessLocation, location_id)
    if loc is None or loc.tenant_id != require_current_tenant():
        raise hours.HoursError("unknown_location", "the location is not one of this client's")


def build(
    *,
    date_from: date,
    date_to: date,
    closed: bool,
    shifts: Sequence[Mapping[str, Any]] = (),
    name: str | None = None,
    location_id: uuid.UUID | None = None,
) -> hours.SpecialDay:
    """Lo que llega por la API (turnos en ``HH:MM``) → una fecha validada."""
    parsed = tuple(
        sorted(hours.parse_shift(str(s.get("open")), str(s.get("close"))) for s in shifts)
    )
    return hours.SpecialDay(
        date_from=date_from,
        date_to=date_to,
        closed=closed,
        shifts=() if closed else parsed,
        name=" ".join((name or "").split()),
        location_id=location_id,
    )


async def _replace_shifts(
    session: AsyncSession, row: BusinessSpecialDate, special: hours.SpecialDay
) -> None:
    await session.execute(
        sa.delete(BusinessSpecialShift).where(
            BusinessSpecialShift.tenant_id == row.tenant_id,
            BusinessSpecialShift.special_date_id == row.id,
        )
    )
    for s in special.shifts:
        session.add(
            BusinessSpecialShift(
                tenant_id=row.tenant_id,
                special_date_id=row.id,
                open_min=s.open_min,
                close_min=s.close_min,
            )
        )


async def create_special_date(
    session: AsyncSession,
    special: hours.SpecialDay,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
    special_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, writes.SectionWritten | None]:
    await _location(session, special.location_id)
    live = await list_special_dates(session)
    if len(live) >= MAX_SPECIAL_DATES:
        raise hours.HoursError("too_many_special_dates", "200 special dates at most")
    row = BusinessSpecialDate(
        id=special_id or uuid.uuid4(),
        tenant_id=require_current_tenant(),
        location_id=special.location_id,
        name=special.name,
        date_from=special.date_from,
        date_to=special.date_to,
        closed=special.closed,
    )

    async def change() -> None:
        session.add(row)
        await session.flush()
        await _replace_shifts(session, row, special)

    written = await section_write.guarded_write(
        session,
        "special_dates",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/special_dates/{row.id}"],
        expected_revision=expected_revision,
    )
    return row.id, written


async def _get(session: AsyncSession, special_id: uuid.UUID) -> BusinessSpecialDate:
    row = await session.get(BusinessSpecialDate, special_id)
    if row is None or row.tenant_id != require_current_tenant():
        raise LookupError("unknown special date")
    return row


async def update_special_date(
    session: AsyncSession,
    special_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """``changes``: ``name``, ``from``, ``to``, ``closed``, ``shifts`` o
    ``location_id``; lo que no llega se queda. También deshace un archivado
    (``archived: false``)."""
    row = await _get(session, special_id)
    parsed = await hours.specials_of(session, [row], tenant_id=row.tenant_id)
    current = parsed[0] if parsed else None
    shifts = changes.get("shifts")
    if shifts is None:
        shifts = [
            {"open": s.hhmm()[0], "close": s.hhmm()[1]} for s in (current.shifts if current else ())
        ]
    special = build(
        date_from=_as_date(changes.get("from", row.date_from)),
        date_to=_as_date(changes.get("to", row.date_to)),
        closed=bool(changes.get("closed", row.closed)),
        shifts=shifts,
        name=changes.get("name", row.name),
        location_id=_as_uuid(changes.get("location_id", row.location_id)),
    )
    await _location(session, special.location_id)

    async def change() -> None:
        row.name, row.date_from, row.date_to = special.name, special.date_from, special.date_to
        row.closed, row.location_id = special.closed, special.location_id
        if changes.get("archived") is False:
            row.archived_at = None
        await _replace_shifts(session, row, special)

    return await section_write.guarded_write(
        session,
        "special_dates",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/special_dates/{special_id}"],
        expected_revision=expected_revision,
    )


def _as_date(raw: Any) -> date:
    return raw if isinstance(raw, date) else date.fromisoformat(str(raw))


def _as_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None or isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


async def archive_special_date(
    session: AsyncSession,
    special_id: uuid.UUID,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    row = await _get(session, special_id)

    async def change() -> None:
        if row.archived_at is None:
            row.archived_at = datetime.now(UTC)

    return await section_write.guarded_write(
        session,
        "special_dates",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/special_dates/{special_id}"],
        expected_revision=expected_revision,
    )


# ── adaptadores: deshacer y aplicar propuestas ─────────────────────────────


def _from_view(item: Mapping[str, Any]) -> hours.SpecialDay:
    return build(
        date_from=_as_date(item["from"]),
        date_to=_as_date(item["to"]),
        closed=bool(item.get("closed")),
        shifts=list(item.get("shifts") or []),
        name=item.get("name"),
        location_id=_as_uuid(item.get("location_id")),
    )


async def _restore(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: writes.WriteContext
) -> writes.SectionWritten:
    target = list((view or {}).get("special_dates") or [])
    wanted = {_as_uuid(item.get("id")): item for item in target if item.get("id")}
    last: writes.SectionWritten | None = None
    for row, _sp in await list_special_dates(session, archived=True):
        item = wanted.pop(row.id, None)
        if item is None:
            if row.archived_at is None:
                last = await archive_special_date(session, row.id, actor=ctx.actor, ctx=ctx) or last
            continue
        changes = {**dict(item), "archived": False}
        last = await update_special_date(session, row.id, changes, actor=ctx.actor, ctx=ctx) or last
    for special_id, item in wanted.items():
        _id, written = await create_special_date(
            session, _from_view(item), actor=ctx.actor, ctx=ctx, special_id=special_id
        )
        last = written or last
    if last is None:
        raise writes.NothingWritten
    return last


async def _apply(
    session: AsyncSession, ops: Sequence[writes.Op], ctx: writes.WriteContext
) -> writes.SectionWritten:
    last: writes.SectionWritten | None = None
    for op in ops:
        parts = op.path.split("/")[1:]
        if parts[:1] != ["special_dates"]:
            raise hours.HoursError("invalid_pointer", op.path)
        if op.op == "add" and parts[1:] == ["-"]:
            _id, written = await create_special_date(
                session, _from_view(op.value or {}), actor=ctx.actor, ctx=ctx
            )
            last = written or last
        elif len(parts) == 2 and op.op == "archive":
            last = (
                await archive_special_date(session, uuid.UUID(parts[1]), actor=ctx.actor, ctx=ctx)
                or last
            )
        elif len(parts) == 2 and op.op == "replace":
            last = (
                await update_special_date(
                    session, uuid.UUID(parts[1]), dict(op.value or {}), actor=ctx.actor, ctx=ctx
                )
                or last
            )
        else:
            raise hours.HoursError("invalid_pointer", op.path)
    if last is None:
        raise writes.NothingWritten
    return last


writes.register_section_adapter("special_dates", restore=_restore, apply=_apply)


__all__ = [
    "MAX_SPECIAL_DATES",
    "archive_special_date",
    "build",
    "create_special_date",
    "list_special_dates",
    "update_special_date",
]
