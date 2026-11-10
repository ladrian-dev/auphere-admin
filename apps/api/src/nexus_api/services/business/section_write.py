"""Lo común de las escrituras de sedes, horario, fechas especiales, servicios y
preguntas frecuentes — spec 047, T056 a T058.

Cada servicio de sección valida su dominio y escribe sus filas; esto lo envuelve:

- un *savepoint*: si la revisión leída ya no es la de la sección
  (``writes.SectionRevisionConflict``), no queda nada escrito;
- el antes y el después, con la vista de la sección en el ClientSpec
  (``client_spec.section_view``): es lo que guarda el historial y lo que el
  deshacer devuelve;
- ``writes.write_section`` con la procedencia que llega (``writes.WriteContext``:
  una persona, una lectura, un deshacer, una propuesta aceptada).

Una escritura que no cambia nada no deja historial: devuelve ``None``.

Y :func:`ensure_profile`: la ficha de un cliente de antes de la 047 nace la
primera vez que algo escribe en ella.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import AgentConfig, Tenant
from nexus_api.db.models.business import BusinessProfile, BusinessSection
from nexus_api.services.business import client_spec, writes
from nexus_api.services.business.profile import COUNTRIES, TEMPLATE_NICHES
from nexus_api.services.business.sections import Actor, init_sections

#: Quien escribe cuando no escribe una persona (un cliente de antes, la migración).
SYSTEM: Final = Actor(kind="system", id="ficha", origin="system")
#: El nicho de un cliente de antes de la ficha sin plantilla conocida.
LEGACY_NICHE: Final = "Negocio"
#: Lo leído (``source``) que se aplica con «revísalo».
READ_SOURCES: Final = frozenset({"web", "document", "social"})


def context(actor: Actor, ctx: writes.WriteContext | None) -> writes.WriteContext:
    return ctx if ctx is not None else writes.WriteContext(actor=actor)


async def ensure_profile(
    session: AsyncSession, tenant_id: uuid.UUID | None = None
) -> BusinessProfile:
    """La ficha del cliente; la de un cliente de antes de la 047 nace aquí, con
    lo que ya se sabe de él (su zona, su mercado y el nicho de su plantilla),
    marcada «Migrado». Sin ella no hay ``content_rev`` que subir."""
    tid = tenant_id or require_current_tenant()
    profile = await session.get(BusinessProfile, tid)
    if profile is not None:
        return profile
    tenant = await session.get(Tenant, tid)
    if tenant is None:
        raise LookupError("unknown client")
    template = await session.scalar(
        sa.select(AgentConfig.seed_template_ref)
        .where(AgentConfig.tenant_id == tid, AgentConfig.seed_template_ref.is_not(None))
        .order_by(AgentConfig.version.desc())
        .limit(1)
    )
    niche = next((n.words[0] for n in TEMPLATE_NICHES if n.template == template), LEGACY_NICHE)
    market = (tenant.market or "").upper()
    country = market if market in COUNTRIES else None
    known = COUNTRIES.get(country) if country else None
    profile = BusinessProfile(
        tenant_id=tid,
        niche=niche,
        timezone=tenant.timezone or "UTC",
        country=country,
        price_currency=known.currency if known else None,
        eu_only=bool(known and known.eu_eea),
        policies={},
        content_rev=1,
    )
    session.add(profile)
    await session.flush()
    has_sections = await session.scalar(
        sa.select(sa.func.count())
        .select_from(BusinessSection)
        .where(BusinessSection.tenant_id == tid)
    )
    if not has_sections:
        await init_sections(session, actor=SYSTEM, links=False)
    await writes.set_provenance(
        session, ["/business/niche", "/business/timezone"], source="migrated", actor=SYSTEM
    )
    return profile


async def guarded_write(
    session: AsyncSession,
    section: str,
    *,
    ctx: writes.WriteContext,
    change: Callable[[], Awaitable[None]],
    pointers: Iterable[str] = (),
    expected_revision: int | None = None,
    state: str | None = None,
    view: Callable[[], Awaitable[dict[str, Any]]] | None = None,
) -> writes.SectionWritten | None:
    """Hace ``change`` y lo anota, todo en un *savepoint* (ver el módulo).
    ``view``: la vista del antes y el después, si no es la del ClientSpec."""
    await ensure_profile(session)
    if state is None:
        state = "read_pending" if ctx.review == "pending" else "complete"

    async def snapshot() -> dict[str, Any]:
        if view is not None:
            return await view()
        return await client_spec.section_view(session, section)

    async with session.begin_nested():
        before = await snapshot()
        await change()
        await session.flush()
        after = await snapshot()
        if before == after and ctx.kind != "undo":
            if expected_revision is not None:
                current = await writes.current_revision(session, section)
                if current != expected_revision:
                    raise writes.SectionRevisionConflict(section=section, current=current)
            return None
        return await writes.write_section(
            session,
            section,
            actor=ctx.actor,
            before=before,
            after=after,
            pointers=list(pointers),
            source=ctx.source,
            kind=ctx.kind,
            expected_revision=expected_revision,
            state=state,
            source_url=ctx.source_url,
            translated_from=ctx.translated_from,
            review=ctx.review,
            audit_actor=ctx.audit_actor,
            undo_of=ctx.undo_of,
        )


__all__ = [
    "LEGACY_NICHE",
    "READ_SOURCES",
    "SYSTEM",
    "context",
    "ensure_profile",
    "guarded_write",
]
