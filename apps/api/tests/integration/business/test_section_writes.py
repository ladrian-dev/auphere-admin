"""Spec 047, bloque C — la única vía para escribir una sección de la ficha.

``services/business/writes.write_section`` es lo que comparten las secciones (el
horario, las sedes, los servicios…, de la T056 a la T058) y el historial y la procedencia
(T068 y T069). Fija las cinco cosas de cada escritura (requisitos 8.4, 13.1, 13.3,
13.4):

- el ``412`` por sección con lo que cambió desde la revisión leída, y que otra
  sección no choca;
- la fila del historial con su antes, su después y su autor;
- la procedencia vigente de los punteros escritos;
- la revisión de la sección y ``content_rev``;
- la recompilación de los agentes del cliente.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    BusinessChange,
    BusinessFieldProvenance,
    BusinessProfile,
    BusinessSection,
    Tenant,
    TenantPlan,
)
from nexus_api.services.business import compilation
from nexus_api.services.business.sections import Actor, init_sections
from nexus_api.services.business.writes import SectionRevisionConflict, write_section

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ANA = Actor(kind="partner_member", id="ana@ladrian.test", origin="console")
MARTA = Actor(kind="client_user", id="marta@florencanto.test", origin="app")


async def _client(db_session: AsyncSession) -> uuid.UUID:
    tid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Tenant(id=tid, name="Flor y Encanto", slug=f"fe-{tid.hex[:8]}", plan=TenantPlan.PRO)
        )
    async with tenant_scoped_session(db_session, tid):
        db_session.add(
            BusinessProfile(tenant_id=tid, niche="Floristería", timezone="America/Santiago")
        )
        await db_session.flush()
        await init_sections(db_session, actor=ANA, links=False)
    return tid


async def test_a_write_records_history_provenance_and_revisions(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = await _client(db_session)
    compiled: list[int] = []

    async def _recompile(session: Any, *, content_rev: int) -> None:
        compiled.append(content_rev)

    monkeypatch.setattr(compilation, "recompile_active_versions", _recompile)

    async with tenant_scoped_session(db_session, tid):
        written = await write_section(
            db_session,
            "hours",
            actor=MARTA,
            before=None,
            after={
                "layout": "blocks",
                "blocks": [{"days": [0, 1, 2, 3, 4], "shifts": [[540, 1200]]}],
            },
            pointers=["/hours/blocks"],
            expected_revision=0,
            state="complete",
        )

    assert written.revision == 1
    assert written.content_rev == 2
    assert compiled == [2]
    async with tenant_scoped_session(db_session, tid):
        change = await db_session.get(BusinessChange, written.change_id)
        assert change is not None
        assert (change.section, change.kind, change.actor_id, change.origin) == (
            "hours",
            "edit",
            "marta@florencanto.test",
            "app",
        )
        assert change.before is None and change.after is not None
        provenance = await db_session.get(BusinessFieldProvenance, (tid, "/hours/blocks"))
        assert provenance is not None
        assert (provenance.source, provenance.actor_kind, provenance.review) == (
            "person",
            "client_user",
            "confirmed",
        )
        section = await db_session.get(BusinessSection, (tid, "hours"))
        assert section is not None and section.state == "complete"


async def test_a_stale_revision_is_a_conflict_with_what_changed(db_session: AsyncSession) -> None:
    tid = await _client(db_session)
    async with tenant_scoped_session(db_session, tid):
        await write_section(
            db_session, "services", actor=ANA, before=None, after={"items": [{"name": "Ramo"}]}
        )
        with pytest.raises(SectionRevisionConflict) as conflict:
            await write_section(
                db_session,
                "services",
                actor=MARTA,
                before=None,
                after={"items": []},
                expected_revision=0,
            )
        assert conflict.value.current == 1
        assert [c["by"] for c in conflict.value.changes] == ["ana@ladrian.test"]

        # Another section does not collide: two people editing at once do not clash.
        hours = await write_section(
            db_session, "hours", actor=MARTA, before=None, after={}, expected_revision=0
        )
        assert hours.revision == 1
        changes = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(BusinessChange)
            .where(BusinessChange.tenant_id == tid)
        )
        assert changes == 2  # the refused write left nothing


async def test_another_client_never_sees_the_history(db_session: AsyncSession) -> None:
    a, b = await _client(db_session), await _client(db_session)
    async with tenant_scoped_session(db_session, a):
        await write_section(db_session, "faqs", actor=ANA, before=None, after={"items": []})
    async with tenant_scoped_session(db_session, b):
        seen = await db_session.scalar(sa.select(sa.func.count()).select_from(BusinessChange))
        assert seen == 0
