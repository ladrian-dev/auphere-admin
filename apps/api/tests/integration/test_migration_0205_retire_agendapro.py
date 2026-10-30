"""Spec 048, T001 — la 0205 retira AgendaPro (requisitos 1.5, 1.6 y 2.2).

Primero se asegura de que nadie lo usa: si un cliente tiene la URL pública de
AgendaPro puesta o una conexión de AgendaPro sin borrar, la migración falla,
nombra a ese cliente y **no cambia nada**. Borrar en silencio la configuración
de un cliente rompería su agente; el operador la quita antes, a sabiendas.

Sin nadie que lo use, borra el conector y sus ``tenant_connectors``, las filas
``agendapro.*`` del catálogo (también las dos que la 0021 olvidó), la columna
``tenants.agendapro_public_url``, la columna ``appointments.public_booking_status``
con su índice y su restricción, cancela los ``scheduled_jobs`` pendientes de
``no_show_scrape`` y ``async_booking``, y marca ``booking.*`` como retiradas
(``deprecated``: el runtime las sigue ejecutando, nadie las ofrece).

Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0204_console_v2_for_all"
_BOOKING = (
    "booking.check_availability",
    "booking.create_appointment",
    "booking.modify_appointment",
    "booking.cancel_appointment",
    "booking.get_appointments",
)


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _has_column(table: str, column: str) -> bool:
    rows = await _exec(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c",
        t=table,
        c=column,
    )
    return bool(rows)


async def _version() -> str:
    (row,) = await _exec("SELECT version_num FROM alembic_version")
    return str(row[0])


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    # Si el test se queda a medias, lo que bloquea la migración se quita aquí
    # para que la base vuelva a head y el resto de la suite no lo pague.
    if await _has_column("tenants", "agendapro_public_url"):
        await _exec("UPDATE tenants SET agendapro_public_url = NULL")
        await _exec(
            "DELETE FROM tenant_connectors WHERE connector_id IN "
            "(SELECT id FROM connectors WHERE slug = 'agendapro')"
        )
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


async def _tenant(name: str) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
        "VALUES (:i, :n, :s, 'pro', 'active', 'America/Santiago')",
        i=tenant_id,
        n=name,
        s=f"m205-{tenant_id.hex[:10]}",
    )
    return tenant_id


async def _agendapro_connector() -> uuid.UUID:
    """The seed ``release.sh`` used to apply. ``connectors`` is not emptied
    between tests, so it may still be there from another one."""
    (row,) = await _exec(
        "INSERT INTO connectors (slug, display_name, vendor, category, auth_kind, "
        "mcp_server_ref) VALUES ('agendapro', 'AgendaPro', 'AgendaPro', 'booking', "
        "'browser_credentials', 'internal:agendapro_browser_mcp') "
        "ON CONFLICT (slug) DO UPDATE SET display_name = EXCLUDED.display_name RETURNING id"
    )
    return uuid.UUID(str(row[0]))


async def _install(tenant_id: uuid.UUID, connector_id: uuid.UUID, status: str) -> None:
    await _exec(
        "INSERT INTO tenant_connectors (tenant_id, connector_id, status) VALUES (:t, :c, :s)",
        t=tenant_id,
        c=connector_id,
        s=status,
    )


async def _job(tenant_id: uuid.UUID, kind: str, status: str) -> uuid.UUID:
    job_id = uuid.uuid4()
    await _exec(
        "INSERT INTO scheduled_jobs (id, tenant_id, kind, run_at, status) "
        "VALUES (:i, :t, CAST(:k AS scheduled_job_kind), now(), "
        "CAST(:s AS scheduled_job_status))",
        i=job_id,
        t=tenant_id,
        k=kind,
        s=status,
    )
    return job_id


async def _job_status(job_id: uuid.UUID) -> str:
    (row,) = await _exec("SELECT status::text FROM scheduled_jobs WHERE id = :i", i=job_id)
    return str(row[0])


async def _pending_appointment(tenant_id: uuid.UUID) -> None:
    customer_id = uuid.uuid4()
    await _exec(
        "INSERT INTO customers (id, tenant_id, identifier, preferences) "
        "VALUES (:c, :t, :i, '{}'::jsonb)",
        c=customer_id,
        t=tenant_id,
        i=f"m205-{customer_id.hex[:8]}",
    )
    await _exec(
        "INSERT INTO appointments (tenant_id, customer_id, service_name, service_duration_min, "
        "starts_at, ends_at, status, public_booking_status) VALUES (:t, :c, 'Corte', 30, "
        "now() + interval '1 day', now() + interval '1 day 30 minutes', 'booked', 'pending')",
        t=tenant_id,
        c=customer_id,
    )


async def test_it_refuses_while_a_client_uses_agendapro_and_changes_nothing(
    at_head_afterwards: Any,
) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    connector_id = await _agendapro_connector()
    with_url = await _tenant("Barbería Cultor")
    await _exec(
        "UPDATE tenants SET agendapro_public_url = 'https://cultor.site.agendapro.com/cl' "
        "WHERE id = :t",
        t=with_url,
    )
    connected = await _tenant("Clínica Boreal")
    await _install(connected, connector_id, "connected")
    # Una conexión ya desconectada no usa AgendaPro: no bloquea.
    left = await _tenant("Spa Que Se Fue")
    await _install(left, connector_id, "disconnected")
    nobody = await _tenant("Sin Agenda")
    job = await _job(nobody, "async_booking", "pending")

    up = _alembic("upgrade", "head")
    assert up.returncode != 0
    out = up.stderr + up.stdout
    assert "Barbería Cultor" in out and "Clínica Boreal" in out
    assert "Spa Que Se Fue" not in out and "Sin Agenda" not in out

    # No cambió nada: sigue en 0204, con todo lo de AgendaPro dentro.
    assert await _version() == _BEFORE
    assert await _has_column("tenants", "agendapro_public_url")
    assert await _has_column("appointments", "public_booking_status")
    assert await _exec("SELECT 1 FROM connectors WHERE id = :c", c=connector_id)
    assert (
        len(await _exec("SELECT 1 FROM tenant_connectors WHERE connector_id = :c", c=connector_id))
        == 2
    )
    assert await _job_status(job) == "pending"
    statuses = await _exec(
        "SELECT DISTINCT status::text FROM tool_catalog WHERE name LIKE 'booking.%'"
    )
    assert statuses == [("active",)]


async def test_without_users_it_removes_agendapro_and_retires_booking(
    at_head_afterwards: Any,
) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    connector_id = await _agendapro_connector()
    left = await _tenant("Spa Que Se Fue")
    await _install(left, connector_id, "disconnected")
    # Lo que la 0019 pudo dejar en una base de larga vida: booking.* enlazadas al conector.
    await _exec(
        "UPDATE tool_catalog SET connector_id = :c WHERE name LIKE 'booking.%'", c=connector_id
    )
    tenant_id = await _tenant("Barbería Cultor")
    scrape = await _job(tenant_id, "no_show_scrape", "pending")
    booking = await _job(tenant_id, "async_booking", "pending")
    sent = await _job(tenant_id, "async_booking", "sent")
    reminder = await _job(tenant_id, "reminder", "pending")
    await _pending_appointment(tenant_id)

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    assert not await _exec("SELECT 1 FROM connectors WHERE slug = 'agendapro'")
    assert not await _exec(
        "SELECT 1 FROM tenant_connectors WHERE connector_id = :c", c=connector_id
    )
    assert not await _exec("SELECT 1 FROM tool_catalog WHERE name LIKE 'agendapro%'")
    assert not await _has_column("tenants", "agendapro_public_url")
    assert not await _has_column("appointments", "public_booking_status")
    assert not await _exec(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_appointments_public_pending'"
    )
    assert not await _exec(
        "SELECT 1 FROM pg_constraint WHERE conname = 'ck_appointments_public_booking_status'"
    )
    assert await _job_status(scrape) == "cancelled"
    assert await _job_status(booking) == "cancelled"
    assert await _job_status(sent) == "sent"
    assert await _job_status(reminder) == "pending"

    booking_rows = await _exec(
        "SELECT name, status::text, connector_id FROM tool_catalog WHERE name LIKE 'booking.%' "
        "ORDER BY name"
    )
    assert sorted(r[0] for r in booking_rows) == sorted(_BOOKING)
    assert {(r[1], r[2]) for r in booking_rows} == {("deprecated", None)}
    # El informe del paso a Reservas se lee en la auditoría.
    assert await _exec(
        "SELECT 1 FROM console_audit_vocabulary WHERE action = 'reservations.passed'"
    )

    # Y la vuelta atrás deja las columnas (no los datos ni el conector).
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert await _has_column("tenants", "agendapro_public_url")
    assert await _has_column("appointments", "public_booking_status")
    statuses = await _exec(
        "SELECT DISTINCT status::text FROM tool_catalog WHERE name LIKE 'booking.%'"
    )
    assert statuses == [("active",)]
