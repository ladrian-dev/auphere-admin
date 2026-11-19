"""Spec 064 — la migración 0236: desde cuándo lee el agente y el cierre por inactividad.

Dos columnas en ``conversations`` (``context_from`` y ``cut_on_reopen``) y una en
``client_access`` (``inbox_autoclose_hours``, con su ``CHECK``). Las filas que ya
existen quedan como estaban: sin corte y sin plazo (requisitos 4.8 y 5.1).

Baja a 0235 y vuelve a subir en su propio proceso de Alembic, y deja la base en
head pase lo que pase.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0235_quedate_listing_catalog_ids"

_COLUMNS = """
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE (table_name = 'conversations' AND column_name IN ('context_from', 'cut_on_reopen'))
   OR (table_name = 'client_access' AND column_name = 'inbox_autoclose_hours')
ORDER BY table_name, column_name
"""


_WORDS = """
SELECT summary_es, summary_en FROM console_audit_vocabulary
WHERE action = 'inbox.settings_changed'
"""


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest.fixture
def at_head_afterwards() -> Any:
    yield
    _alembic("upgrade", "head")


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _client_with_access() -> uuid.UUID:
    pid, tid = uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO partners (id, name, slug) VALUES (:i, 'P', :s)", i=pid, s=f"p-{pid.hex[:10]}"
    )
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'T', :s, 'pro', 'active')",
        i=tid,
        s=f"ac-{tid.hex[:10]}",
    )
    await _exec(
        "INSERT INTO client_access (tenant_id, partner_id, enabled, modules) "
        "VALUES (:t, :p, true, ARRAY['inbox']::varchar[])",
        t=tid,
        p=pid,
    )
    return tid


async def test_0236_adds_the_columns_and_takes_them_back(at_head_afterwards) -> None:
    tid = await _client_with_access()

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert await _exec(_COLUMNS) == []
    assert await _exec(_WORDS) == []

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    cols = {
        (t, c): (kind, nullable, default) for t, c, kind, nullable, default in await _exec(_COLUMNS)
    }
    assert cols[("conversations", "context_from")][:2] == ("timestamp with time zone", "YES")
    kind, nullable, default = cols[("conversations", "cut_on_reopen")]
    assert (kind, nullable) == ("boolean", "NO") and default == "false"
    assert cols[("client_access", "inbox_autoclose_hours")][:2] == ("integer", "YES")

    # El cambio del plazo tiene su frase en la auditoría de la consola, con las
    # dos variables que la consola sabe rellenar.
    ((es, en),) = await _exec(_WORDS)
    assert "{actor}" in es and "{client}" in es and "{actor}" in en and "{client}" in en

    # Lo que ya existía queda sin plazo.
    rows = await _exec(
        "SELECT inbox_autoclose_hours FROM client_access WHERE tenant_id = :t", t=tid
    )
    assert rows[0][0] is None


@pytest.mark.parametrize("hours", [24, 72, 168, 720, None])
async def test_0236_takes_the_four_terms_and_never(hours: int | None) -> None:
    tid = await _client_with_access()
    await _exec(
        "UPDATE client_access SET inbox_autoclose_hours = :h WHERE tenant_id = :t", h=hours, t=tid
    )
    rows = await _exec(
        "SELECT inbox_autoclose_hours FROM client_access WHERE tenant_id = :t", t=tid
    )
    assert rows[0][0] == hours


@pytest.mark.parametrize("hours", [0, 1, 48, 1000])
async def test_0236_refuses_another_term(hours: int) -> None:
    tid = await _client_with_access()
    with pytest.raises(IntegrityError, match="ck_client_access_inbox_autoclose"):
        await _exec(
            "UPDATE client_access SET inbox_autoclose_hours = :h WHERE tenant_id = :t",
            h=hours,
            t=tid,
        )
