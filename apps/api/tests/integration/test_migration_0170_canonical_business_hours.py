"""Bug ``horario-del-negocio-en-tres-formas`` — la migración 0170 deja una forma.

Baja a 0169, siembra las formas que hay en la base y vuelve a subir. Fija:

- la forma del asistente del admin y la de la semilla pasan a la canónica;
- la canónica no se toca;
- una fila que no se entiende se deja como estaba (el lector la lee igual);
- repetirla no cambia nada.

Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0169_client_phone_audit_vocab"


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


async def _tenant(hours: Any) -> uuid.UUID:
    tid = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, business_hours) "
        "VALUES (:i, 'H', :s, 'pro', 'active', CAST(:h AS jsonb))",
        i=tid,
        s=f"h-{tid.hex[:10]}",
        h=json.dumps(hours),
    )
    return tid


async def _hours(tid: uuid.UUID) -> Any:
    rows = await _exec("SELECT business_hours FROM tenants WHERE id = :i", i=tid)
    return rows[0][0]


ADMIN = {
    "monday": "09:00-18:00",
    "tuesday": "09:00-18:00",
    "wednesday": "09:00-18:00",
    "thursday": "09:00-18:00",
    "friday": "09:00-18:00",
    "saturday": "10:00-14:00",
    "sunday": "closed",
}
SEED = {
    "monday": {"open": "09:00", "close": "18:00"},
    "saturday": {"open": "09:00", "close": "14:00"},
    "sunday": None,
}


async def test_0170_normalises_and_leaves_what_it_cannot_read(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    admin = await _tenant(ADMIN)
    seed = await _tenant(SEED)
    garbage_raw = {"monday": "9 a 18"}
    garbage = await _tenant(garbage_raw)
    label_only = await _tenant({"label": "Lun-Sáb 10-19"})

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    a = await _hours(admin)
    assert a["monday"] == [{"from": "09:00", "to": "18:00"}]
    assert a["saturday"] == [{"from": "10:00", "to": "14:00"}]
    assert a["sunday"] == []

    s = await _hours(seed)
    assert s["monday"] == [{"from": "09:00", "to": "18:00"}]
    assert s["tuesday"] == []  # un día que no se nombraba sale cerrado
    assert s["sunday"] == []

    assert await _hours(garbage) == garbage_raw
    assert await _hours(label_only) == {"label": "Lun-Sáb 10-19"}

    # Idempotente: bajar y subir otra vez no cambia la forma canónica.
    assert _alembic("downgrade", _BEFORE).returncode == 0
    assert _alembic("upgrade", "head").returncode == 0
    assert await _hours(admin) == a
