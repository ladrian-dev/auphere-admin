"""La procedencia de cada dato de la ficha — spec 047, T069 (requisitos 13.1 y 13.2).

``business_field_provenance`` guarda, por puntero del ClientSpec, la procedencia
**vigente** (la escribe ``writes.set_provenance`` con cada escritura). Aquí se
lee para enseñarla y se confirma:

- :func:`provenance_map`: cada dato con su fuente, su autor **con nombre**, desde
  dónde y cuándo. Es lo que pinta «Escrito por ti», «Leído de la web ·
  revísalo», «Migrado · revísalo», «Propuesto por el constructor» o «Editado por
  Marta desde la app · hace 2 h».
- :func:`confirm_section`: «Es correcto» sobre una sección leída (13.2): sus datos
  pendientes de revisar pasan a escritos por esa persona y la sección deja de
  salir como pendiente. No cambia ningún dato, así que no sube la revisión.

Los nombres salen de las membresías (``partner_memberships`` y
``client_memberships``, tablas de plataforma) en una sesión propia y acotada al
partner y al cliente: nunca se lee la persona de otro partner.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import BusinessFieldProvenance, BusinessSection
from nexus_api.services.business.client_spec import SECTION_KEYS, provenance_view
from nexus_api.services.business.sections import Actor, touch_section

#: La gente sin nombre que mostrar: el sistema y el lector.
_NAMELESS: Final = frozenset({"system", "builder"})


@dataclass(frozen=True)
class Person:
    kind: str
    id: str | None
    name: str | None


async def people_names(
    partner_id: uuid.UUID, tenant_id: uuid.UUID, people: Iterable[tuple[str | None, str | None]]
) -> dict[tuple[str, str], str]:
    """``(kind, id) → nombre visible`` de las personas del partner y del
    cliente. Una sesión de plataforma propia: la del llamante tiene el rol de
    la aplicación y el cliente puesto."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import ClientMembership, PartnerMembership

    wanted = {(k, i) for k, i in people if k and i and k not in _NAMELESS}
    members = {i for k, i in wanted if k == "partner_member"}
    clients = {i for k, i in wanted if k == "client_user"}
    out: dict[tuple[str, str], str] = {}
    if not members and not clients:
        return out
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        if members:
            rows = await session.execute(
                sa.select(
                    PartnerMembership.user_id,
                    PartnerMembership.display_name,
                    PartnerMembership.email,
                ).where(
                    PartnerMembership.partner_id == partner_id,
                    PartnerMembership.user_id.in_(members),
                )
            )
            for user_id, name, email in rows.all():
                out[("partner_member", user_id)] = name or email
        if clients:
            rows = await session.execute(
                sa.select(
                    ClientMembership.user_id, ClientMembership.display_name, ClientMembership.email
                ).where(
                    ClientMembership.tenant_id == tenant_id,
                    ClientMembership.partner_id == partner_id,
                    ClientMembership.user_id.in_(clients),
                )
            )
            for user_id, name, email in rows.all():
                out[("client_user", user_id)] = name or email
    return out


def person(
    kind: str | None, actor_id: str | None, names: dict[tuple[str, str], str]
) -> Person | None:
    if not kind:
        return None
    return Person(kind=kind, id=actor_id, name=names.get((kind, actor_id or "")))


async def provenance_map(
    session: AsyncSession, *, partner_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """La procedencia vigente de cada dato, con el nombre de quien lo escribió."""
    raw = await provenance_view(session)
    names = await people_names(
        partner_id,
        require_current_tenant(),
        [((e["by"] or {}).get("kind"), (e["by"] or {}).get("id")) for e in raw.values()],
    )
    for entry in raw.values():
        by = entry.get("by")
        entry["by"] = None if not by else person(by.get("kind"), by.get("id"), names)
    return raw


def section_prefix(section: str) -> str:
    return "/" + SECTION_KEYS[section]


def _in_section(pointer: str, section: str) -> bool:
    prefix = section_prefix(section)
    return pointer == prefix or pointer.startswith(prefix + "/")


async def confirm_section(session: AsyncSession, section: str, *, actor: Actor) -> int:
    """«Es correcto»: lo leído pendiente de revisar en la sección pasa a escrito
    por ``actor``. Devuelve cuántos datos confirmó."""
    if section not in SECTION_KEYS:
        raise ValueError(f"unknown section: {section!r}")
    tenant_id = require_current_tenant()
    rows = (
        await session.scalars(
            sa.select(BusinessFieldProvenance).where(
                BusinessFieldProvenance.tenant_id == tenant_id,
                BusinessFieldProvenance.review == "pending",
            )
        )
    ).all()
    confirmed = 0
    for row in rows:
        if not _in_section(row.pointer, section):
            continue
        row.source = "person"
        row.actor_kind = actor.kind
        row.actor_id = actor.id
        row.origin = actor.origin
        row.review = "confirmed"
        row.at = sa.func.now()
        confirmed += 1
    state = await session.scalar(
        sa.select(BusinessSection.state).where(
            BusinessSection.tenant_id == tenant_id, BusinessSection.section == section
        )
    )
    if state == "read_pending":
        await touch_section(session, section, actor=actor, state="complete", changed=False)
    await session.flush()
    return confirmed


__all__ = [
    "Person",
    "confirm_section",
    "people_names",
    "person",
    "provenance_map",
    "section_prefix",
]
