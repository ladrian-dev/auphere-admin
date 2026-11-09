"""Spec 057, T001 — la 0229 admite el trabajo ``agenda_text`` y el motivo ``agenda_not_ready``.

Baja sin dejar restos (``test_migration_reversibility`` lo exige a todas) y quita antes
los trabajos del tipo que desaparece. Corre en su propio proceso de Alembic y deja la
base en head pase lo que pase.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0228_staff_calendar_connections"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_API,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "NEXUS_DATABASE_URL": TEST_DB_URL},
    )


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _constraint(name: str) -> str:
    """Lo que dice la restricción de la base, no el modelo."""
    rows = await _exec(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n", n=name
    )
    assert rows, f"{name} no existe"
    return str(rows[0][0])


async def _accepts(kind: str) -> bool:
    return f"'{kind}'" in await _constraint("ck_jobs_kind")


async def _waits(reason: str) -> bool:
    return f"'{reason}'" in await _constraint("ck_conversations_waiting_reason")


async def test_it_goes_up_and_down(test_engine) -> None:
    try:
        assert await _accepts("agenda_text")
        assert await _waits("agenda_not_ready")
        down = _alembic("downgrade", _BEFORE)
        assert down.returncode == 0, down.stderr
        assert not await _accepts("agenda_text")
        assert not await _waits("agenda_not_ready")
        assert await _accepts("agent_draft")
        assert await _waits("booking_unbacked")
    finally:
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
    assert await _accepts("agenda_text")
    assert await _waits("agenda_not_ready")
