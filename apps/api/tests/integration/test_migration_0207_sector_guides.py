"""Spec 047, enmienda del 2026-10-29, T201 — la 0207 sube y baja.

Sube ``sector_guides``, la tabla de plataforma de las guías que Auphere convierte
desde una guía generada (requisito 58.5, D66): sin ``tenant_id``, con la clave y la
etiqueta normalizada únicas y comprobadas por la base, y que ``nexus_app`` solo lee.
Baja sin dejar restos.

Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import subprocess
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
_BEFORE = "0206_sector_guides_builder"
_HEAD = "0207_sector_guides"


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


async def _exists(table: str) -> bool:
    return bool(await _exec("SELECT 1 FROM pg_class WHERE relname = :t", t=table))


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


@pytest.mark.usefixtures("at_head_afterwards")
async def test_0207_goes_up_and_down() -> None:
    start = _alembic("downgrade", _BEFORE)
    assert start.returncode == 0, start.stderr
    up = _alembic("upgrade", _HEAD)
    assert up.returncode == 0, up.stderr
    assert await _exists("sector_guides")
    columns = {
        row[0]
        for row in await _exec(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'sector_guides'"
        )
    }
    assert "tenant_id" not in columns, "de plataforma: nada apunta a un cliente"
    privileges = {
        row[0]
        for row in await _exec(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name = 'sector_guides' AND grantee = 'nexus_app'"
        )
    }
    assert privileges == {"SELECT"}

    await _exec(
        "INSERT INTO sector_guides (key, label, label_key, guide, published_by) "
        "VALUES ('gimnasio', 'Gimnasio', 'gimnasio', '{}'::jsonb, 'operator:a@b.c')"
    )
    with pytest.raises(Exception, match="uq_sector_guides_label_key"):
        await _exec(
            "INSERT INTO sector_guides (key, label, label_key, guide, published_by) "
            "VALUES ('gym', 'Gimnasio', 'gimnasio', '{}'::jsonb, 'operator:a@b.c')"
        )
    with pytest.raises(Exception, match="ck_sector_guides_key"):
        await _exec(
            "INSERT INTO sector_guides (key, label, label_key, guide, published_by) "
            "VALUES ('Óptica 1', 'Óptica', 'optica', '{}'::jsonb, 'operator:a@b.c')"
        )

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert not await _exists("sector_guides")

    again = _alembic("upgrade", "head")
    assert again.returncode == 0, again.stderr
