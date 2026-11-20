"""Spec 065, T032 (requisitos 12.1, 12.2 y 12.6): la 0240 pasa el modelo de cada cliente a sus agentes.

Baja a la 0239, siembra clientes con su asignación de respuesta y vuelve a subir:

- cada agente activo sin elección de un cliente con asignación ``respond`` recibe ese modelo;
  uno archivado no recibe nada y uno con elección propia no cambia;
- ``set_by = 'partner'`` si la última ``console.model.update`` del cliente apunta a ese mismo
  modelo; si no (la puso Auphere desde el panel, como a Jemma), ``'operator'``;
- una línea ``model.respond_binding.migrated`` por cliente con lo de antes (modelo,
  ``fallback_chain``, tope) y los agentes que lo recibieron;
- no falla con ``fallback_chain`` ni tope, y no borra las filas de asignación;
- deja escritos los recuentos (``RAISE NOTICE``) para compararlos con la comprobación previa;
- ``downgrade`` deja las elecciones migradas como estaban.

Corre con ``row_security = off`` dentro del bloque: con el rol de migraciones, que salta la
RLS, escribe; con uno que no la saltara, fallaría en voz alta en lugar de escribir 0 filas.
Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[3]
_BEFORE = "0239_cache_write_lane_default"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
SONNET46 = "anthropic/claude-sonnet-4-6"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest.fixture
def at_head_afterwards() -> Iterator[None]:
    yield
    _alembic("upgrade", "head")


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("SET LOCAL row_security = off"))
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _tenant() -> uuid.UUID:
    tenant_id = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
        "VALUES (:i, 'T', :s, 'pro', 'active', 'America/Caracas')",
        i=tenant_id,
        s=f"m240-{tenant_id.hex[:10]}",
    )
    return tenant_id


async def _agent(
    tenant_id: uuid.UUID, *, status: str = "active", chosen: str | None = None
) -> uuid.UUID:
    agent_id = uuid.uuid4()
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status) VALUES (:i, :t, :n, :s)",
        i=agent_id,
        t=tenant_id,
        n=f"Agente {agent_id.hex[:4]}",
        s=status,
    )
    if chosen:
        await _exec(
            "UPDATE agents SET respond_model_profile_id = "
            "(SELECT id FROM model_profiles WHERE model_id = :m), "
            "respond_model_set_by = 'partner', respond_model_set_at = now() WHERE id = :i",
            m=chosen,
            i=agent_id,
        )
    return agent_id


async def _bind(tenant_id: uuid.UUID, model_id: str, *, chain: list[str], cap: str | None) -> None:
    await _exec(
        "INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id, fallback_chain, "
        "max_cost_per_turn_usd) SELECT :t, 'respond', id, CAST(:c AS jsonb), CAST(:cap AS numeric) "
        "FROM model_profiles WHERE model_id = :m",
        t=tenant_id,
        m=model_id,
        c=json.dumps(chain),
        cap=cap,
    )


async def _console_choice(tenant_id: uuid.UUID, model_id: str) -> None:
    await _exec(
        "INSERT INTO audit_log (tenant_id, actor, action, target, before_json, after_json) "
        "VALUES (:t, 'console:ana@example.com', 'console.model.update', :tg, "
        "CAST('{}' AS jsonb), CAST(:after AS jsonb))",
        t=tenant_id,
        tg=f"tenant:{tenant_id}",
        after=json.dumps({"model_id": model_id}),
    )


async def _choice(agent_id: uuid.UUID) -> tuple[Any, Any]:
    (row,) = await _exec(
        "SELECT p.model_id, a.respond_model_set_by FROM agents a "
        "LEFT JOIN model_profiles p ON p.id = a.respond_model_profile_id WHERE a.id = :i",
        i=agent_id,
    )
    return row[0], row[1]


async def test_each_clients_model_moves_to_its_agents(at_head_afterwards: None) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr[-2000:]

    # Jemma: Terra puesto por Auphere desde el panel, con su reserva y su tope de antes.
    jemma = await _tenant()
    j1, j2 = await _agent(jemma), await _agent(jemma)
    archived = await _agent(jemma, status="archived")
    own = await _agent(jemma, chosen=LUNA)
    await _bind(jemma, TERRA, chain=[LUNA], cap="0.50")

    # Un cliente que eligió Luna desde la consola.
    partner = await _tenant()
    p1 = await _agent(partner)
    await _console_choice(partner, LUNA)
    await _bind(partner, LUNA, chain=[], cap=None)

    # Un cliente que eligió en la consola y después Auphere le cambió el modelo.
    later = await _tenant()
    l1 = await _agent(later)
    await _console_choice(later, LUNA)
    await _bind(later, SONNET46, chain=[], cap=None)

    # Un cliente sin asignación: no cambia nada.
    none = await _tenant()
    n1 = await _agent(none)

    up = _alembic("upgrade", "0240_respond_bindings_to_agents")
    assert up.returncode == 0, up.stderr[-3000:]
    assert "0240" in up.stderr and "agentes" in up.stderr, "deja escritos los recuentos"

    assert await _choice(j1) == (TERRA, "operator")
    assert await _choice(j2) == (TERRA, "operator")
    assert await _choice(archived) == (None, None)
    assert await _choice(own) == (LUNA, "partner"), "una elección propia no cambia"
    assert await _choice(p1) == (LUNA, "partner")
    assert await _choice(l1) == (SONNET46, "operator")
    assert await _choice(n1) == (None, None)

    bindings = await _exec(
        "SELECT count(*) FROM tenant_model_bindings WHERE tenant_id = ANY(:t) AND role = 'respond'",
        t=[jemma, partner, later],
    )
    assert bindings[0][0] == 3, "no borra las filas"

    (audit,) = await _exec(
        "SELECT before_json, after_json, actor FROM audit_log "
        "WHERE tenant_id = :t AND action = 'model.respond_binding.migrated'",
        t=jemma,
    )
    before, after, actor = audit
    assert before["model_id"] == TERRA
    assert before["fallback_chain"] == [LUNA]
    assert str(before["max_cost_per_turn_usd"]) in {"0.50", "0.5", "0.500000"}
    assert sorted(after["agents"]) == sorted([str(j1), str(j2)])
    assert actor == "migration:0240"
    assert not await _exec(
        "SELECT 1 FROM audit_log WHERE tenant_id = :t AND action = 'model.respond_binding.migrated'",
        t=none,
    )

    back = _alembic("downgrade", _BEFORE)
    assert back.returncode == 0, back.stderr[-2000:]
    assert await _choice(j1) == (None, None)
    assert await _choice(p1) == (None, None)
    assert await _choice(own) == (LUNA, "partner"), "la elección propia sigue"


async def test_with_a_role_that_does_not_bypass_rls_it_fails_loudly() -> None:
    """La base de pruebas corre con un superusuario: aquí se fija que con el rol de la
    aplicación (sujeto a la RLS forzada de ``agents``) la migración falla en voz alta en lugar
    de no ver a nadie y escribir 0 filas."""
    import importlib.util

    path = _API / "alembic" / "versions" / "0240_respond_bindings_to_agents.py"
    spec = importlib.util.spec_from_file_location("m0240", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    tenant = await _tenant()
    agent = await _agent(tenant)
    await _bind(tenant, TERRA, chain=[], cap=None)
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SET ROLE nexus_app"))
            with pytest.raises(sa.exc.DBAPIError, match="row-level security"):
                await conn.execute(sa.text(migration.UPGRADE))
            await conn.rollback()
    finally:
        await engine.dispose()
    assert await _choice(agent) == (None, None), "no escribió nada"
