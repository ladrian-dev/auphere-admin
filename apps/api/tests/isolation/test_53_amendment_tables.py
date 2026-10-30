"""Garantía 1 en las tablas de la enmienda del 2026-10-29 (spec 047, T199).

``test_43`` las barre solas (las crea la 0206: FORCE, la política canónica y FK
compuestas, sin inventario). Aquí, el caso adversarial de cada una, como lo haría
quien escribe con el GUC de un cliente y conoce un id del otro:

- ``suggested_agents`` y ``generated_guides`` no apuntan a un trabajo de otro
  cliente (la FK es ``(tenant_id, job_id)``: la comprobación de una FK no pasa por
  la RLS, así que de una sola columna dejaría hacerlo);
- una prueba no apunta a la guía generada de otro cliente;
- nadie escribe una fila con el ``tenant_id`` de otro ni lee las suyas;
- el sector de la ficha de otro cliente no se ve.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

from nexus_api.db.base import get_sessionmaker

from .conftest import set_tenant
from .test_43_force_and_composite_fk_sweep import _sweep, client_tables, spec_047_tables

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

TABLES = ("generated_guides", "suggested_agents")


async def _as(tenant_id: uuid.UUID, sql: str, **params: object) -> list[object]:
    async with get_sessionmaker()() as session, session.begin():
        await set_tenant(session, tenant_id)
        result = await session.execute(sa.text(sql), params)
        return list(result.all()) if result.returns_rows else []


async def _world(tenants_ab: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    """Cada cliente con un trabajo, una guía generada, un agente sugerido, una
    suite y su ficha con sector."""
    ids: dict[str, uuid.UUID] = {}
    for label, tenant_id in tenants_ab.items():
        job, guide, agent, suite = (uuid.uuid4() for _ in range(4))
        await _as(
            tenant_id,
            "INSERT INTO jobs (id, tenant_id, kind, status) "
            "VALUES (:j, :t, 'sector_identify', 'queued')",
            j=job,
            t=tenant_id,
        )
        await _as(
            tenant_id,
            "INSERT INTO generated_guides (id, tenant_id, sector_label, label_key, job_id) "
            "VALUES (:g, :t, 'Gimnasio', 'gimnasio', :j)",
            g=guide,
            t=tenant_id,
            j=job,
        )
        await _as(
            tenant_id,
            "INSERT INTO suggested_agents (tenant_id, name, name_key, description, job_id) "
            "VALUES (:t, 'Recepción', 'recepcion', 'Atiende las citas por WhatsApp.', :j)",
            t=tenant_id,
            j=job,
        )
        await _as(tenant_id, "INSERT INTO agents (id, tenant_id, name) VALUES (:a, :t, 'R')",
                  a=agent, t=tenant_id)  # fmt: skip
        await _as(
            tenant_id,
            "INSERT INTO agent_test_suites (id, tenant_id, agent_id) VALUES (:s, :t, :a)",
            s=suite,
            t=tenant_id,
            a=agent,
        )
        await _as(
            tenant_id,
            "INSERT INTO business_profiles (tenant_id, niche, timezone, sector) VALUES "
            "(:t, 'Gimnasio', 'Europe/Madrid', CAST(:s AS jsonb))",
            t=tenant_id,
            s='{"key": "otro", "label": "Gimnasio", "confidence": 0.8, "source": "niche", '
            '"decided_by": "system"}',
        )
        ids.update({f"{label}_job": job, f"{label}_guide": guide, f"{label}_suite": suite})
    return ids


async def test_the_new_tables_are_swept_and_clean() -> None:
    created = spec_047_tables()
    assert set(TABLES) <= created
    async with get_sessionmaker()() as session:
        tables = await client_tables(session)
    assert set(TABLES) <= tables.keys()
    found = await _sweep()
    dirty = sorted(msg for (table, _rule), msg in found.items() if table in TABLES)
    assert not dirty, dirty
    for table in TABLES:
        fks = [fk for fk in tables[table].foreign_keys if fk.target in tables]
        assert fks and all(fk.is_composite_by_tenant for fk in fks), table
    tests_fks = {fk.name: fk for fk in tables["agent_tests"].foreign_keys}
    assert tests_fks["fk_agent_tests_generated_guide"].is_composite_by_tenant


async def test_a_row_never_points_at_another_clients_job_or_guide(tenants_ab) -> None:
    ids = await _world(tenants_ab)
    a = tenants_ab["a"]
    with pytest.raises(IntegrityError):
        await _as(
            a,
            "INSERT INTO suggested_agents (tenant_id, name, name_key, description, job_id) "
            "VALUES (:t, 'Ventas', 'ventas', 'Vende bonos y productos por WhatsApp.', :j)",
            t=a,
            j=ids["b_job"],
        )
    with pytest.raises(IntegrityError):
        await _as(
            a,
            "INSERT INTO generated_guides (tenant_id, sector_label, label_key, job_id) "
            "VALUES (:t, 'Óptica', 'optica', :j)",
            t=a,
            j=ids["b_job"],
        )
    with pytest.raises(IntegrityError):
        await _as(
            a,
            "INSERT INTO agent_tests (tenant_id, suite_id, kind, name, first_message, "
            "criteria, critical, generated_guide_id) VALUES (:t, :s, 'sector', 'x', 'hola', "
            "'[]'::jsonb, false, :g)",
            t=a,
            s=ids["a_suite"],
            g=ids["b_guide"],
        )


async def test_nobody_writes_or_reads_the_other_clients_rows(tenants_ab) -> None:
    await _world(tenants_ab)
    a, b = tenants_ab["a"], tenants_ab["b"]
    for sql in (
        "INSERT INTO suggested_agents (tenant_id, name, name_key, description) "
        "VALUES (:t, 'Ventas', 'ventas', 'Vende bonos y productos por WhatsApp.')",
        "INSERT INTO generated_guides (tenant_id, sector_label, label_key) "
        "VALUES (:t, 'Óptica', 'optica')",
    ):
        with pytest.raises(DBAPIError, match="row-level security"):
            await _as(a, sql, t=b)
    for table in (*TABLES, "business_profiles"):
        seen = await _as(a, f"SELECT DISTINCT tenant_id FROM {table}")
        assert {row[0] for row in seen} == {a}, table
    (row,) = await _as(a, "SELECT sector->>'label' FROM business_profiles")
    assert row[0] == "Gimnasio"  # type: ignore[index]
