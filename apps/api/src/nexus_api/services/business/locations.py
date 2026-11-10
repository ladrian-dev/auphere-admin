"""Las sedes del negocio — spec 047, T057 (requisito 9).

Cada sede tiene nombre (obligatorio), dirección, teléfono y, si quiere, su
propio horario (``hours.save_week`` con su ``location_id``); sin él, vale el del
negocio (9.2). «Eliminar» una sede la archiva, y se puede deshacer (9.4). Sin
sedes, la compilación le dice al agente que no invente una dirección (9.3).

Cada escritura pasa por ``section_write.guarded_write`` (un *savepoint*, el antes
y el después del ClientSpec y ``writes.write_section``). El adaptador de la
sección (deshacer y aplicar propuestas o lo leído) llama a estas mismas
funciones.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import BusinessLocation, BusinessSchedule
from nexus_api.services.business import hours, section_write, writes
from nexus_api.services.business.sections import Actor

NAME_MAX: Final = 80
ADDRESS_MAX: Final = 300
PHONE: Final = re.compile(r"^\+[1-9][0-9]{6,14}$")
#: Como mucho (``client-spec.schema.json``).
MAX_LOCATIONS: Final = 50


class LocationError(ValueError):
    """Una sede que no se puede guardar: ``422`` con ``code`` y ``field``."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"{field}: {code}")
        self.code = code
        self.field = field


@dataclass(frozen=True)
class LocationData:
    name: str
    address: str | None = None
    phone_e164: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def validate(data: LocationData) -> LocationData:
    name = _clean(data.name)
    if not name:
        raise LocationError("name_required", "name")
    if len(name) > NAME_MAX:
        raise LocationError("name_too_long", "name")
    address = _clean(data.address)
    if address and len(address) > ADDRESS_MAX:
        raise LocationError("address_too_long", "address")
    phone = (data.phone_e164 or "").replace(" ", "") or None
    if phone and not PHONE.match(phone):
        raise LocationError("phone_invalid", "phone_e164")
    return LocationData(name=name, address=address, phone_e164=phone)


async def list_locations(
    session: AsyncSession, *, archived: bool = False
) -> list[BusinessLocation]:
    """Las sedes del cliente del contexto, en su orden. ``archived`` incluye las
    archivadas."""
    stmt = sa.select(BusinessLocation).where(BusinessLocation.tenant_id == require_current_tenant())
    if not archived:
        stmt = stmt.where(BusinessLocation.archived_at.is_(None))
    rows = await session.scalars(
        stmt.order_by(BusinessLocation.position, BusinessLocation.created_at)
    )
    return list(rows.all())


async def with_own_hours(session: AsyncSession) -> set[uuid.UUID]:
    """Las sedes que tienen horario propio."""
    rows = await session.scalars(
        sa.select(BusinessSchedule.location_id).where(
            BusinessSchedule.tenant_id == require_current_tenant(),
            BusinessSchedule.location_id.is_not(None),
        )
    )
    return {r for r in rows.all() if r is not None}


async def _get(session: AsyncSession, location_id: uuid.UUID) -> BusinessLocation:
    loc = await session.get(BusinessLocation, location_id)
    if loc is None or loc.tenant_id != require_current_tenant():
        raise LookupError("unknown location")
    return loc


async def create_location(
    session: AsyncSession,
    data: LocationData,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
    location_id: uuid.UUID | None = None,
) -> tuple[BusinessLocation, writes.SectionWritten | None]:
    clean = validate(data)
    tenant_id = require_current_tenant()
    existing = await list_locations(session, archived=True)
    if len([loc for loc in existing if loc.archived_at is None]) >= MAX_LOCATIONS:
        raise LocationError("too_many_locations", "name")
    loc = BusinessLocation(
        id=location_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name=clean.name,
        address=clean.address,
        phone_e164=clean.phone_e164,
        position=max((x.position for x in existing), default=-1) + 1,
    )

    async def change() -> None:
        session.add(loc)

    written = await section_write.guarded_write(
        session,
        "locations",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/locations/{loc.id}"],
        expected_revision=expected_revision,
    )
    return loc, written


async def update_location(
    session: AsyncSession,
    location_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """``changes``: solo lo que llega (``name``, ``address``, ``phone_e164``)."""
    loc = await _get(session, location_id)
    clean = validate(
        LocationData(
            name=changes.get("name", loc.name),
            address=changes.get("address", loc.address),
            phone_e164=changes.get("phone_e164", loc.phone_e164),
        )
    )

    async def change() -> None:
        loc.name, loc.address, loc.phone_e164 = clean.name, clean.address, clean.phone_e164

    return await section_write.guarded_write(
        session,
        "locations",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/locations/{location_id}/{key}" for key in changes],
        expected_revision=expected_revision,
    )


async def archive_location(
    session: AsyncSession,
    location_id: uuid.UUID,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    restore: bool = False,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """Archivar (o deshacerlo, ``restore``). La sede y su horario propio se
    quedan: restaurarla la devuelve como estaba."""
    loc = await _get(session, location_id)

    async def change() -> None:
        if restore:
            loc.archived_at, loc.archived_by = None, None
        elif loc.archived_at is None:
            loc.archived_at, loc.archived_by = datetime.now(UTC), actor.id

    return await section_write.guarded_write(
        session,
        "locations",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/locations/{location_id}"],
        expected_revision=expected_revision,
    )


# ── adaptadores: deshacer y aplicar propuestas o lo leído ──────────────────


def _data(item: Mapping[str, Any]) -> LocationData:
    return LocationData(
        name=str(item.get("name") or ""),
        address=item.get("address"),
        phone_e164=item.get("phone_e164"),
    )


def _uuid(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


async def _set_hours(
    session: AsyncSession,
    location_id: uuid.UUID,
    view: Mapping[str, Any] | None,
    ctx: writes.WriteContext,
) -> writes.SectionWritten | None:
    return await hours.save_week(
        session,
        hours.week_of_view(view) if view is not None else None,
        actor=ctx.actor,
        location_id=location_id,
        ctx=ctx,
    )


async def _restore(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: writes.WriteContext
) -> writes.SectionWritten:
    """La sección vuelve a ``view``: lo que no está, se archiva (nada se borra)."""
    target = list((view or {}).get("locations") or [])
    wanted = {_uuid(item.get("id")): item for item in target if _uuid(item.get("id"))}
    last: writes.SectionWritten | None = None
    for loc in await list_locations(session, archived=True):
        item = wanted.pop(loc.id, None)
        if item is None:
            if loc.archived_at is None:
                last = await archive_location(session, loc.id, actor=ctx.actor, ctx=ctx) or last
            continue
        changes = {k: item.get(k) for k in ("name", "address", "phone_e164")}
        last = await update_location(session, loc.id, changes, actor=ctx.actor, ctx=ctx) or last
        archived = bool(item.get("archived"))
        if archived != (loc.archived_at is not None):
            last = (
                await archive_location(
                    session, loc.id, actor=ctx.actor, ctx=ctx, restore=not archived
                )
                or last
            )
        last = await _set_hours(session, loc.id, item.get("hours"), ctx) or last
    for location_id, item in wanted.items():
        _loc, written = await create_location(
            session, _data(item), actor=ctx.actor, ctx=ctx, location_id=location_id
        )
        last = written or last
        if item.get("hours"):
            last = await _set_hours(session, _loc.id, item["hours"], ctx) or last
    if last is None:
        raise writes.NothingWritten
    return last


async def _apply(
    session: AsyncSession, ops: Sequence[writes.Op], ctx: writes.WriteContext
) -> writes.SectionWritten:
    last: writes.SectionWritten | None = None
    for op in ops:
        parts = op.path.split("/")[1:]
        if parts[:1] != ["locations"]:
            raise LocationError("invalid_pointer", op.path)
        value = op.value if isinstance(op.value, Mapping) else {}
        if op.op == "add" and parts[1:] == ["-"]:
            loc, written = await create_location(session, _data(value), actor=ctx.actor, ctx=ctx)
            last = written or last
            if value.get("hours"):
                last = await _set_hours(session, loc.id, value["hours"], ctx) or last
            continue
        location_id = _uuid(parts[1]) if len(parts) > 1 else None
        if location_id is None:
            raise LocationError("invalid_pointer", op.path)
        if op.op == "archive":
            last = await archive_location(session, location_id, actor=ctx.actor, ctx=ctx) or last
        elif op.op == "replace" and parts[2:] == ["hours"]:
            last = await _set_hours(session, location_id, op.value, ctx) or last
        elif op.op == "replace" and len(parts) == 3:
            last = (
                await update_location(
                    session, location_id, {parts[2]: op.value}, actor=ctx.actor, ctx=ctx
                )
                or last
            )
        elif op.op == "replace" and len(parts) == 2:
            changes = {k: value.get(k) for k in ("name", "address", "phone_e164") if k in value}
            last = (
                await update_location(session, location_id, changes, actor=ctx.actor, ctx=ctx)
                or last
            )
        else:
            raise LocationError("invalid_pointer", op.path)
    if last is None:
        raise writes.NothingWritten
    return last


writes.register_section_adapter("locations", restore=_restore, apply=_apply)


__all__ = [
    "LocationData",
    "LocationError",
    "archive_location",
    "create_location",
    "list_locations",
    "update_location",
    "validate",
    "with_own_hours",
]
