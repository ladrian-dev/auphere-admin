"""Spec 047, T217 (revisión de seguridad del 2026-10-30) — la 0210 sube y baja.

Sube: ``nexus_app`` solo lee ``sector_test_catalog``, como ``sector_guides``
(0207). Baja: vuelve a los permisos de la 0187.

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
_BEFORE = "0209_audit_words_sector_guides"
_HEAD = "0210_sector_tests_read_only"


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


async def _privileges() -> set[str]:
    return {
        row[0]
        for row in await _exec(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name = 'sector_test_catalog' AND grantee = 'nexus_app'"
        )
    }


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


@pytest.mark.usefixtures("at_head_afterwards")
async def test_0210_goes_up_and_down() -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= await _privileges()
    up = _alembic("upgrade", _HEAD)
    assert up.returncode == 0, up.stderr
    assert await _privileges() == {"SELECT"}
    # Las pruebas de los seis sectores (0188) siguen ahí: solo cambian los permisos.
    rows = await _exec("SELECT count(DISTINCT sector_key) FROM sector_test_catalog")
    assert rows[0][0] >= 6
