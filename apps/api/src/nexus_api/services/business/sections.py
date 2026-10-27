"""Las secciones de la ficha: su revisión y su estado — spec 047, T047 (requisitos 8.5 y 13).

Una fila por cliente y sección (``business_sections``):

- la **revisión** sube con cada escritura de la sección y es lo que compara
  ``If-Match``: dos personas editando secciones distintas no chocan;
- el **estado** es lo que enseña Negocio (requisito 8.5): ``complete``,
  ``read_pending`` («Leído de la web · revísalo»), ``pending`` u ``optional``.

Y ``business_profiles.content_rev``, que sube con **cualquier** cambio de la
ficha y entra en la clave de compilación del agente (research D4).

Todo corre dentro de la transacción del llamante, con el cliente puesto (RLS):
ninguna función confirma.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import (
    ACTOR_KINDS,
    ORIGINS,
    SECTION_STATES,
    SECTIONS,
    BusinessProfile,
    BusinessSection,
)


@dataclass(frozen=True)
class Actor:
    """Quién escribe en la ficha y desde dónde (requisito 13.5)."""

    kind: str
    id: str | None
    origin: str

    def __post_init__(self) -> None:
        if self.kind not in ACTOR_KINDS:
            raise ValueError(f"unknown actor kind: {self.kind!r}")
        if self.origin not in ORIGINS:
            raise ValueError(f"unknown origin: {self.origin!r}")


#: La lectura de la web en segundo plano.
READER: Final = Actor(kind="system", id="reader", origin="system")

#: Cómo nace cada sección de un cliente nuevo. Lo imprescindible para que un
#: agente atienda está ``pending`` y sale en «lo primero que le falta» del Panel
#: (horario, servicios, sedes, documentos y redes, requisito 14.5); lo demás es
#: ``optional`` hasta que alguien lo rellena.
INITIAL_STATES: Final[dict[str, str]] = {
    "basics": "complete",
    "locations": "pending",
    "hours": "pending",
    "special_dates": "optional",
    "services": "pending",
    "policies": "optional",
    "faqs": "optional",
    "sources": "pending",
    "links": "pending",
}
assert set(INITIAL_STATES) == set(SECTIONS)
assert set(INITIAL_STATES.values()) <= set(SECTION_STATES)


async def init_sections(session: AsyncSession, *, actor: Actor, links: bool) -> None:
    """Las nueve secciones de un cliente nuevo. ``links``: si ya tiene web o redes."""
    tenant_id = require_current_tenant()
    for section, state in INITIAL_STATES.items():
        if section == "links" and links:
            state = "complete"
        session.add(
            BusinessSection(
                tenant_id=tenant_id,
                section=section,
                revision=1 if section == "basics" or (section == "links" and links) else 0,
                state=state,
                updated_by_kind=actor.kind,
                updated_by_id=actor.id,
                updated_origin=actor.origin,
            )
        )
    await session.flush()


async def touch_section(
    session: AsyncSession,
    section: str,
    *,
    actor: Actor,
    state: str | None = None,
    changed: bool = True,
) -> int:
    """Anota una escritura en la sección: sube su revisión si ``changed`` y, si
    se da, cambia su estado. Devuelve la revisión que queda."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section: {section!r}")
    if state is not None and state not in SECTION_STATES:
        raise ValueError(f"unknown section state: {state!r}")
    tenant_id = require_current_tenant()
    values: dict[str, object] = {
        "updated_at": sa.func.now(),
        "updated_by_kind": actor.kind,
        "updated_by_id": actor.id,
        "updated_origin": actor.origin,
    }
    if changed:
        values["revision"] = BusinessSection.revision + 1
    if state is not None:
        values["state"] = state
    revision = await session.scalar(
        sa.update(BusinessSection)
        .where(BusinessSection.tenant_id == tenant_id, BusinessSection.section == section)
        .values(**values)
        .returning(BusinessSection.revision)
        .execution_options(synchronize_session=False)
    )
    if revision is None:
        # Un cliente de antes de la ficha: la sección nace aquí.
        row = BusinessSection(
            tenant_id=tenant_id,
            section=section,
            revision=1 if changed else 0,
            state=state or INITIAL_STATES[section],
            updated_by_kind=actor.kind,
            updated_by_id=actor.id,
            updated_origin=actor.origin,
        )
        session.add(row)
        await session.flush()
        return row.revision
    return int(revision)


async def bump_content_rev(session: AsyncSession) -> int:
    """``content_rev`` + 1: cualquier cambio de la ficha recompila al agente."""
    tenant_id = require_current_tenant()
    rev = await session.scalar(
        sa.update(BusinessProfile)
        .where(BusinessProfile.tenant_id == tenant_id)
        .values(content_rev=BusinessProfile.content_rev + 1, updated_at=sa.func.now())
        .returning(BusinessProfile.content_rev)
        .execution_options(synchronize_session=False)
    )
    if rev is None:
        raise LookupError("this client has no business profile")
    return int(rev)


async def section_states(session: AsyncSession) -> dict[str, str]:
    """El estado de cada sección del cliente del contexto."""
    tenant_id = require_current_tenant()
    rows = await session.execute(
        sa.select(BusinessSection.section, BusinessSection.state).where(
            BusinessSection.tenant_id == tenant_id
        )
    )
    return {section: state for section, state in rows.all()}


__all__ = [
    "INITIAL_STATES",
    "READER",
    "Actor",
    "bump_content_rev",
    "init_sections",
    "section_states",
    "touch_section",
]
