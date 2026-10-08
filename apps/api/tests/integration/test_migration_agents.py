"""Spec 030 T090 — el relleno de agentes (0152 y 0153, R14.1, R14.2, R14.8).

Baja la base a 0151, siembra lo que hay en producción hoy (un tenant con
versiones —una activa, una archivada, un borrador—, un número que contesta,
una línea solo de envío y el canal del Playground) y vuelve a subir. Fija:

- un agente «Agente principal» por tenant **con** versiones, y ninguno para
  el que no tiene;
- todas las versiones con su agente, una sola activa por agente;
- el número que contesta asignado al agente; la línea solo de envío y el
  Playground sin agente (el despachador usa el principal);
- los números de versión intactos.

Corre en su propio proceso de Alembic (como ``test_migration_reversibility``)
y deja la base en head pase lo que pase.
"""

from __future__ import annotations

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
_BEFORE = "0151_inbox_audit_vocab"


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


async def test_every_tenant_with_versions_gets_its_principal_agent(
    console_world, at_head_afterwards
) -> None:
    with_agent, without = console_world["a"]["tenant_id"], console_world["b"]["tenant_id"]
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    for version, status in ((1, "archived"), (2, "active"), (3, "staged")):
        await _exec(
            "INSERT INTO agent_configs (tenant_id, version, status, system_prompt_rendered) "
            "VALUES (:t, :v, CAST(:s AS agent_config_status), 'p')",
            t=with_agent,
            v=version,
            s=status,
        )
    answering, send_only, playground = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for cid, provider, config in (
        (answering, "meta", '{"phone_number_id": "PN1"}'),
        (
            send_only,
            "meta",
            '{"phone_number_id": "PN2", "role": "notifications", "agent_enabled": false}',
        ),
        (playground, "qa_playground", "{}"),
    ):
        await _exec(
            "INSERT INTO channels (id, tenant_id, type, provider, provider_identifier, config) "
            "VALUES (:id, :t, 'whatsapp', :p, :pi, CAST(:c AS jsonb))",
            id=cid,
            t=with_agent,
            p=provider,
            pi=f"+34{uuid.uuid4().int % 10**9:09d}",
            c=config,
        )

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    agents = await _exec("SELECT id, tenant_id, name, status FROM agents ORDER BY created_at")
    mine = [a for a in agents if a.tenant_id == with_agent]
    assert [(a.name, a.status) for a in mine] == [("Agente principal", "active")]
    assert not [a for a in agents if a.tenant_id == without]
    principal = mine[0].id

    configs = await _exec(
        "SELECT version, status::text AS status, agent_id FROM agent_configs "
        "WHERE tenant_id = :t ORDER BY version",
        t=with_agent,
    )
    assert [(c.version, c.status) for c in configs] == [
        (1, "archived"),
        (2, "active"),
        (3, "staged"),
    ]
    assert {c.agent_id for c in configs} == {principal}

    channels = {
        r.id: r.agent_id
        for r in await _exec("SELECT id, agent_id FROM channels WHERE tenant_id = :t", t=with_agent)
    }
    assert channels[answering] == principal
    assert channels[send_only] is None
    assert channels[playground] is None


async def test_the_agents_table_is_tenant_isolated() -> None:
    rows = await _exec(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'agents'"
    )
    assert rows == [(True, True)]
    policies = await _exec("SELECT policyname FROM pg_policies WHERE tablename = 'agents'")
    assert [p.policyname for p in policies] == ["agents_tenant_isolation"]
