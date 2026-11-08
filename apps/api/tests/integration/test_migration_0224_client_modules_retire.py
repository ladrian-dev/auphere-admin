"""La 0224 retira Agentes y Negocio de la consola del cliente (spec 056, requisitos 2.1 y 2.2).

Baja a 0223, siembra el acceso de cuatro clientes y vuelve a subir:

- ``{panel, agents, business}`` queda en ``{panel}``, encendido, firmado por la spec;
- ``{agents}`` queda vacío y apagado, porque encendido exige al menos un módulo;
- ``{agents, business}`` apagado queda vacío y apagado;
- ``{inbox, usage}`` no se toca, ni quién lo cambió por última vez.

Después el CHECK rechaza ``agents``. La bajada vuelve a admitir los seis
módulos, pero no devuelve los que quitó. Corre en su propio proceso de Alembic y
deja la base en head pase lo que pase.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from nexus_api.db.models.client_access import (
    CLIENT_MODULES,
    RETIRED_CLIENT_MODULES,
    ClientAccess,
)
from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0223_booking_unbacked_reason"


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


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


async def _partner() -> uuid.UUID:
    pid = uuid.uuid4()
    await _exec(
        "INSERT INTO partners (id, name, slug, status) VALUES (:i, 'P', :s, 'active')",
        i=pid,
        s=f"m224-{pid.hex[:10]}",
    )
    return pid


async def _access(partner_id: uuid.UUID, modules: list[str], *, enabled: bool) -> uuid.UUID:
    tid = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'T', :s, 'pro', 'active')",
        i=tid,
        s=f"m224-{tid.hex[:10]}",
    )
    await _exec(
        "INSERT INTO client_access (tenant_id, partner_id, enabled, modules, updated_by) "
        "VALUES (:t, :p, :e, CAST(:m AS varchar[]), 'operator:ana@auphere.com')",
        t=tid,
        p=partner_id,
        e=enabled,
        m=modules,
    )
    return tid


async def _read(tenant_id: uuid.UUID) -> tuple[bool, list[str], str]:
    (row,) = await _exec(
        "SELECT enabled, modules, updated_by FROM client_access WHERE tenant_id = :t", t=tenant_id
    )
    return row[0], list(row[1]), row[2]


async def test_agents_and_business_leave_every_client(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    partner = await _partner()
    mixed = await _access(partner, ["panel", "agents", "business"], enabled=True)
    only_agents = await _access(partner, ["agents"], enabled=True)
    off = await _access(partner, ["agents", "business"], enabled=False)
    untouched = await _access(partner, ["inbox", "usage"], enabled=True)

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    assert await _read(mixed) == (True, ["panel"], "system:spec_056")
    assert await _read(only_agents) == (False, [], "system:spec_056")
    assert await _read(off) == (False, [], "system:spec_056")
    assert await _read(untouched) == (True, ["inbox", "usage"], "operator:ana@auphere.com")

    with pytest.raises(IntegrityError, match="ck_client_access_modules"):
        await _exec(
            "UPDATE client_access SET modules = ARRAY['panel','agents']::varchar[] "
            "WHERE tenant_id = :t",
            t=mixed,
        )


async def test_the_model_exposes_four_modules_and_keeps_the_retired_names() -> None:
    assert CLIENT_MODULES == ("panel", "inbox", "reservas", "usage")
    assert RETIRED_CLIENT_MODULES == ("agents", "business")
    stored = ClientAccess(modules=["usage", "business", "agents", "panel", "reservas", "inbox"])
    assert stored.ordered_modules() == ("panel", "inbox", "reservas", "usage")


async def test_downgrade_takes_the_six_again_without_giving_them_back(
    at_head_afterwards: Any,
) -> None:
    partner = await _partner()
    client = await _access(partner, ["panel"], enabled=True)

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    assert await _read(client) == (True, ["panel"], "operator:ana@auphere.com")
    await _exec(
        "UPDATE client_access SET modules = ARRAY['panel','agents','business']::varchar[] "
        "WHERE tenant_id = :t",
        t=client,
    )

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert await _read(client) == (True, ["panel"], "system:spec_056")
