"""Spec 047, enmienda del 2026-10-29, T199 — la 0206 sube y baja.

Sube:
- ``business_profiles.sector`` (JSONB, con su forma comprobada en la base);
- ``generated_guides`` y ``suggested_agents``, tablas de cliente con RLS FORCE y FK
  compuestas hacia ``jobs``;
- ``agent_tests.generated_guide_id`` (FK compuesta) y ``agent_test_results.stop``;
- el tipo de trabajo ``sector_identify``.

Baja sin dejar restos (``test_migration_reversibility`` lo exige a todas) y quita
antes los trabajos del tipo que desaparece.

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
_BEFORE = "0205_retire_agendapro"
_HEAD = "0206_sector_guides_builder"


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
    return bool(
        await _exec(
            "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c",
            t=table,
            c=column,
        )
    )


async def _forced(table: str) -> bool | None:
    rows = await _exec(
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = :t", t=table
    )
    return bool(rows[0][0]) if rows else None


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


async def _tenant() -> uuid.UUID:
    tenant_id = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
        "VALUES (:i, 'M206', :s, 'pro', 'active', 'Europe/Madrid')",
        i=tenant_id,
        s=f"m206-{tenant_id.hex[:10]}",
    )
    return tenant_id


@pytest.mark.usefixtures("at_head_afterwards")
async def test_0206_goes_up_and_down() -> None:
    # Desde cualquier head posterior (la 0207 ya existe): primero a la 0205.
    start = _alembic("downgrade", _BEFORE)
    assert start.returncode == 0, start.stderr
    up = _alembic("upgrade", _HEAD)
    assert up.returncode == 0, up.stderr
    assert await _has_column("business_profiles", "sector")
    assert await _has_column("agent_tests", "generated_guide_id")
    assert await _has_column("agent_test_results", "stop")
    assert await _forced("generated_guides") is True
    assert await _forced("suggested_agents") is True

    tenant_id = await _tenant()
    # La forma del sector la comprueba la base, no solo la API.
    await _exec(
        "INSERT INTO business_profiles (tenant_id, niche, timezone, sector) VALUES "
        "(:t, 'Barbería', 'Europe/Madrid', CAST(:s AS jsonb))",
        t=tenant_id,
        s='{"key": "barberia_peluqueria", "label": "Barbería", "confidence": 0.9, '
        '"source": "niche", "decided_by": "system"}',
    )
    with pytest.raises(Exception, match="ck_business_profiles_sector"):
        await _exec(
            "UPDATE business_profiles SET sector = CAST(:s AS jsonb) WHERE tenant_id = :t",
            t=tenant_id,
            s='{"key": "otro", "label": "' + "x" * 41 + '"}',
        )
    await _exec(
        "INSERT INTO jobs (tenant_id, kind, status) VALUES (:t, 'sector_identify', 'queued')",
        t=tenant_id,
    )

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert not await _has_column("business_profiles", "sector")
    assert not await _has_column("agent_tests", "generated_guide_id")
    assert not await _has_column("agent_test_results", "stop")
    assert await _forced("generated_guides") is None
    assert await _forced("suggested_agents") is None
    assert not await _exec("SELECT 1 FROM jobs WHERE kind = 'sector_identify'")

    again = _alembic("upgrade", "head")
    assert again.returncode == 0, again.stderr
