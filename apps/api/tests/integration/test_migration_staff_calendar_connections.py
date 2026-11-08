"""Spec 043, requisito 12 — la migración de los calendarios por profesional, con datos.

La migración toca filas que ya existen: las de antes se quedan en permiso perdido, dos personas
con un calendario se separan y al bajar se va lo que la versión anterior no sabe leer. Se prueba
en una base aparte, porque subir y bajar en la de las pruebas pisaría a las demás. El nombre de
la revisión se lee del archivo: al fusionar cambia de número y esto sigue valiendo.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

API_ROOT = Path(__file__).resolve().parents[2]


def _revisions() -> tuple[str, str]:
    source = next((API_ROOT / "alembic" / "versions").glob("*_staff_calendar_connections.py"))
    text = source.read_text(encoding="utf-8")
    revision = re.search(r'^revision: str = "([^"]+)"', text, re.M)
    down = re.search(r'^down_revision: .* = "([^"]+)"', text, re.M)
    assert revision and down
    return revision.group(1), down.group(1)


def _alembic(url: str, *args: str) -> None:
    subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=API_ROOT,
        env={**os.environ, "NEXUS_DATABASE_URL": url},
        check=True,
        capture_output=True,
    )


async def test_the_rows_that_were_there_survive_going_up_and_down() -> None:
    revision, before = _revisions()
    url = make_url(TEST_DB_URL)
    name = f"nexus_mig_{uuid.uuid4().hex[:10]}"
    scratch = url.set(database=name).render_as_string(hide_password=False)
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(sa.text(f"CREATE DATABASE {name}"))
    engine = create_async_engine(scratch)

    async def run(sql: str, **params: Any) -> list[Any]:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []

    try:
        _alembic(scratch, "upgrade", before)
        tenant = uuid.uuid4()
        staff = [uuid.uuid4() for _ in range(3)]
        await run(
            "INSERT INTO tenants (id, slug, name) VALUES (:t, :s, 'Peluquería')",
            t=tenant,
            s=f"p-{tenant.hex[:8]}",
        )
        for n, member in enumerate(staff):
            await run(
                "INSERT INTO reservation_staff (id, tenant_id, name) VALUES (:i, :t, :n)",
                i=member,
                t=tenant,
                n=f"Persona {n}",
            )
        await run(
            "INSERT INTO reservation_staff_calendars (tenant_id, staff_id, calendar_id, "
            "calendar_name, created_at) VALUES "
            "(:t, :a, 'compartido@g', 'Compartido', now() - interval '2 days'), "
            "(:t, :b, 'compartido@g', 'Compartido', now() - interval '1 day'), "
            "(:t, :c, 'propio@g', 'Propio', now())",
            t=tenant,
            a=staff[0],
            b=staff[1],
            c=staff[2],
        )

        service = uuid.uuid4()
        gone = uuid.uuid4()
        await run(
            "INSERT INTO reservation_staff (id, tenant_id, name, archived_at) "
            "VALUES (:i, :t, 'Archivada', now())",
            i=gone,
            t=tenant,
        )
        await run(
            "INSERT INTO reservation_services (id, tenant_id, name, duration_minutes) "
            "VALUES (:i, :t, 'Corte', 30)",
            i=service,
            t=tenant,
        )
        for member in (staff[0], gone):
            await run(
                "INSERT INTO reservation_service_staff (tenant_id, service_id, staff_id) "
                "VALUES (:t, :s, :m)",
                t=tenant,
                s=service,
                m=member,
            )

        _alembic(scratch, "upgrade", revision)

        offered = await run("SELECT staff_id FROM reservation_service_staff")
        assert [r.staff_id for r in offered] == [staff[0]], "nobody archived stays on a list"
        rows = {
            r.staff_id: r
            for r in await run(
                "SELECT staff_id, calendar_id, calendar_name, connection_status, connection_id, "
                "previous_connection_id FROM reservation_staff_calendars"
            )
        }
        assert len(rows) == 3
        assert {r.connection_status for r in rows.values()} == {"needs_reauth"}
        assert {r.connection_id for r in rows.values()} == {None}
        assert rows[staff[0]].calendar_id == "compartido@g", "the first one keeps it"
        assert rows[staff[1]].calendar_id is None, "two on one calendar are mixed calendars"
        assert rows[staff[2]].calendar_id == "propio@g"
        with pytest.raises(Exception, match="uq_staff_calendars_calendar"):
            await run(
                "UPDATE reservation_staff_calendars SET calendar_id = 'propio@g' "
                "WHERE staff_id = :s",
                s=staff[0],
            )
        now = "now() + interval '1 day'"
        await run(
            "INSERT INTO reservation_busy (tenant_id, staff_id, starts_at, ends_at, source) "
            f"VALUES (:t, :s, {now}, {now} + interval '1 hour', 'business'), "
            f"(:t, :s, {now} + interval '2 hours', {now} + interval '3 hours', 'google')",
            t=tenant,
            s=staff[2],
        )
        new_rows = await run(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'reservation_staff_calendars' "
            "AND column_name = 'connection_status'"
        )
        assert "pending" in new_rows[0].column_default, "a new row starts waiting"

        _alembic(scratch, "downgrade", before)

        left = await run(
            "SELECT staff_id, calendar_id FROM reservation_staff_calendars ORDER BY calendar_id"
        )
        assert {r.staff_id for r in left} == {staff[0], staff[2]}, "without a calendar, no row"
        columns = {
            r.column_name
            for r in await run(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'reservation_staff_calendars'"
            )
        }
        assert not columns & {
            "connection_id",
            "connection_status",
            "previous_connection_id",
            "account_label",
        }
        busy = await run("SELECT source FROM reservation_busy")
        assert [b.source for b in busy] == ["google"], "the previous code would not read the other"

        _alembic(scratch, "upgrade", revision)
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(sa.text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        await admin.dispose()
