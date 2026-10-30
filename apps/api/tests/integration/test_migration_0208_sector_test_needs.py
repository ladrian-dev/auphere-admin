"""Spec 047, enmienda del 2026-10-30, T224 — la 0208 sube y baja.

Escribe en la versión 1 del catálogo de pruebas del sector lo que necesita cada
prueba (``needs``, requisito 65.8): las de pedir cita, la agenda. No toca una
versión que haya publicado Auphere desde el panel, y al bajar lo quita sin tocar
nada más.

Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import json
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
_BEFORE = "0207_sector_guides"
_HEAD = "0208_sector_test_needs"


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


async def _needs(sector: str, version: int = 1) -> dict[str, Any]:
    rows = await _exec(
        "SELECT tests FROM sector_test_catalog WHERE sector_key = :k AND version = :v",
        k=sector,
        v=version,
    )
    assert rows, (sector, version)
    tests = rows[0][0]
    if isinstance(tests, str):
        tests = json.loads(tests)
    return {t["key"]: t.get("needs", "absent") for t in tests}


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


@pytest.mark.usefixtures("at_head_afterwards")
async def test_0208_goes_up_and_down() -> None:
    start = _alembic("downgrade", _BEFORE)
    assert start.returncode == 0, start.stderr
    # Como estaba antes de la 0208: la versión 1 sin ``needs``.
    await _exec(
        "UPDATE sector_test_catalog SET tests = ("
        "  SELECT jsonb_agg(t - 'needs') FROM jsonb_array_elements(tests) AS t"
        ") WHERE version = 1 AND published_by = 'auphere:spec-047'"
    )
    # Una versión publicada desde el panel no se toca.
    await _exec(
        "INSERT INTO sector_test_catalog (sector_key, version, tests, published_by) "
        "SELECT sector_key, 2, tests, 'operator:a@b.c' FROM sector_test_catalog "
        "WHERE sector_key = 'restaurante' AND version = 1"
    )
    up = _alembic("upgrade", _HEAD)
    assert up.returncode == 0, up.stderr
    barber = await _needs("barberia_peluqueria")
    assert barber["book"] == ["book"] and barber["closed_day"] == ["book"]
    assert barber["hours"] == []
    assert (await _needs("restaurante"))["book_table"] == ["book"]
    assert (await _needs("clinica"))["book"] == ["book"]
    assert (await _needs("restaurante", 2))["book_table"] == "absent"

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert set((await _needs("barberia_peluqueria")).values()) == {"absent"}
    await _exec("DELETE FROM sector_test_catalog WHERE published_by = 'operator:a@b.c'")

    again = _alembic("upgrade", "head")
    assert again.returncode == 0, again.stderr
